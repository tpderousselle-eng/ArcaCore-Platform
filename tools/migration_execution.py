"""Controlled PostgreSQL execution for validated ArcaCore migrations."""

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import time

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from tools.alembic_migration import MigrationPolicy, generate_alembic_migration
from tools.core.engine import write_text_atomic, write_text_atomic_exclusive
from tools.core.module_definition import ModuleDefinition
from tools.schema_evolution import plan_schema_evolution
from tools.schema_lifecycle import (LifecycleState, MigrationManifest, SchemaLifecycle,
    SchemaRevision, _digest, load_manifest, load_revision, schema_digest)


class ExecutionState(str, Enum):
    STARTED = "EXECUTION_STARTED"
    DATABASE_COMMITTED = "DATABASE_COMMITTED"
    COMPLETE = "COMPLETE"
    ROLLBACK_STARTED = "ROLLBACK_STARTED"
    ROLLBACK_DATABASE_COMMITTED = "ROLLBACK_DATABASE_COMMITTED"


@dataclass(frozen=True)
class ExecutionStatus:
    state: ExecutionState
    module: str
    migration_revision: str
    manifest_identity: str


def _execute(migration, connection, direction):
    # The payload was regenerated from validated typed objects in this process;
    # no caller-supplied source is executed.
    namespace = {"__name__": f"arcacore_migration_{migration.revision}"}
    exec(compile(migration.content, migration.filename, "exec"), namespace)
    namespace["op"] = Operations(MigrationContext.configure(connection))
    namespace[direction]()


class MigrationExecutor:
    def __init__(self, root: Path, database_url: str, *, lock_timeout=5.0):
        self.lifecycle = SchemaLifecycle(root)
        self.root = self.lifecycle.root
        if not isinstance(database_url, str) or not database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
            raise ValueError("A PostgreSQL database URL is required.")
        if type(lock_timeout) not in (int, float) or not 0 < lock_timeout <= 60:
            raise ValueError("Lock timeout must be between zero and 60 seconds.")
        self._database_url = database_url
        self.lock_timeout = float(lock_timeout)

    def _journal_path(self, module): return self.lifecycle._path(module, "execution")
    def _history_path(self, digest):
        path = (self.lifecycle.state_dir / "history" / f"{digest}.json").resolve(); path.relative_to(self.root); return path

    def _write_journal(self, status):
        body = {"version": 1, "state": status.state.value, "module": status.module,
                 "migration_revision": status.migration_revision,
                 "manifest_identity": status.manifest_identity}
        value = dict(body); value["journal_digest"] = _digest("arcacore-execution-journal/v1", body)
        write_text_atomic(self._journal_path(status.module), json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")

    def status(self, module):
        path = self._journal_path(module)
        if not path.exists(): return None
        try: value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error: raise ValueError("Execution journal is invalid.") from error
        keys = {"version", "state", "module", "migration_revision", "manifest_identity", "journal_digest"}
        if not isinstance(value, dict) or set(value) != keys or value["version"] != 1:
            raise ValueError("Execution journal is invalid.")
        body = dict(value); journal_digest = body.pop("journal_digest")
        if journal_digest != _digest("arcacore-execution-journal/v1", body):
            raise ValueError("Execution journal digest mismatch.")
        try: state = ExecutionState(value["state"])
        except (ValueError, TypeError) as error: raise ValueError("Execution journal state is invalid.") from error
        if value["module"] != module or len(value["migration_revision"]) != 12 or len(value["manifest_identity"]) != 64:
            raise ValueError("Execution journal provenance is invalid.")
        return ExecutionStatus(state, module, value["migration_revision"], value["manifest_identity"])

    def _validated(self, current, proposed, policy):
        accepted = self.lifecycle.verify_current(current)
        pending = load_revision(self.lifecycle._path(current.name, "pending"))
        manifest = load_manifest(self.lifecycle._path(current.name, "manifest"))
        plan = plan_schema_evolution(current, proposed)
        migration = generate_alembic_migration(plan, policy=policy, down_revision=accepted.migration_revision)
        manifest.validate_content(migration.content)
        plan_digest = sha256(plan.canonical_json().encode("utf-8")).hexdigest()
        policy_digest = _digest("arcacore-migration-policy/v1", policy.canonical_dict())
        checks = (manifest.old_schema_digest == accepted.schema_digest,
                  manifest.new_schema_digest == schema_digest(proposed),
                  manifest.evolution_plan_digest == plan_digest,
                  manifest.policy_digest == policy_digest,
                  manifest.migration_revision == migration.revision,
                  manifest.predecessor_revision == accepted.migration_revision,
                  pending.parent_schema_digest == accepted.schema_digest,
                  pending.schema_digest == manifest.new_schema_digest,
                  pending.migration_revision == manifest.migration_revision,
                  pending.lifecycle_state == LifecycleState.PENDING_EXECUTION)
        if not all(checks): raise ValueError("Migration lifecycle provenance mismatch.")
        return accepted, pending, manifest, migration

    @staticmethod
    def _lock_id(module):
        return int.from_bytes(sha256(b"arcacore-migration-lock/v1\0" + module.encode("ascii")).digest()[:8], "big", signed=True)

    def _lock(self, connection, module):
        deadline = time.monotonic() + self.lock_timeout
        while time.monotonic() < deadline:
            if connection.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": self._lock_id(module)}): return
            time.sleep(min(0.05, self.lock_timeout))
        raise TimeoutError("Timed out acquiring the migration execution lock.")

    @staticmethod
    def _db_state(connection, module):
        connection.execute(text("CREATE TABLE IF NOT EXISTS arcacore_migration_state (module VARCHAR(63) PRIMARY KEY, revision VARCHAR(12), manifest_identity VARCHAR(64) NOT NULL)"))
        return connection.execute(text("SELECT revision, manifest_identity FROM arcacore_migration_state WHERE module=:module"), {"module": module}).first()

    def preflight(self, current: ModuleDefinition, proposed: ModuleDefinition, policy=None):
        policy = policy or MigrationPolicy()
        accepted, pending, manifest, migration = self._validated(current, proposed, policy)
        if not manifest.transactional_ddl:
            raise ValueError("Migration is outside the supported transactional DDL model.")
        prior = self.status(current.name)
        if prior is not None and prior.state != ExecutionState.COMPLETE:
            raise ValueError("A conflicting migration execution requires recovery.")
        engine = create_engine(self._database_url, poolclass=NullPool)
        try:
            with engine.begin() as connection:
                self._lock(connection, current.name)
                row = self._db_state(connection, current.name)
                expected = accepted.migration_revision
                if (None if row is None else row[0]) != expected:
                    raise ValueError("Database revision does not match accepted schema state.")
        except (ValueError, TimeoutError): raise
        except Exception as error: raise RuntimeError("Migration preflight failed.") from error
        finally: engine.dispose()
        return manifest

    def apply(self, current, proposed, policy=None, *, interrupt_after_commit=False):
        policy = policy or MigrationPolicy()
        accepted, pending, manifest, migration = self._validated(current, proposed, policy)
        if self.status(current.name) not in (None, ExecutionStatus(ExecutionState.COMPLETE, current.name, migration.revision, manifest.manifest_identity)):
            raise ValueError("A conflicting migration execution requires recovery.")
        status = ExecutionStatus(ExecutionState.STARTED, current.name, migration.revision, manifest.manifest_identity)
        self._write_journal(status)
        engine = create_engine(self._database_url, poolclass=NullPool)
        try:
            with engine.begin() as connection:
                self._lock(connection, current.name)
                row = self._db_state(connection, current.name)
                if (None if row is None else row[0]) != accepted.migration_revision:
                    raise ValueError("Database revision does not match accepted schema state.")
                _execute(migration, connection, "upgrade")
                connection.execute(text("INSERT INTO arcacore_migration_state(module,revision,manifest_identity) VALUES (:m,:r,:i) ON CONFLICT(module) DO UPDATE SET revision=excluded.revision, manifest_identity=excluded.manifest_identity"), {"m": current.name, "r": migration.revision, "i": manifest.manifest_identity})
        except Exception as error:
            # STARTED is retained for an explicit, auditable recovery decision.
            if isinstance(error, (ValueError, TimeoutError)): raise
            raise RuntimeError("Migration database execution failed.") from error
        finally: engine.dispose()
        committed = ExecutionStatus(ExecutionState.DATABASE_COMMITTED, current.name, migration.revision, manifest.manifest_identity)
        self._write_journal(committed)
        if interrupt_after_commit: raise InterruptedError("Simulated interruption after database commit.")
        self._finalize(accepted, pending, committed)
        return self.status(current.name)

    def _finalize(self, accepted, pending, status):
        history = self._history_path(accepted.schema_digest)
        if not history.exists(): write_text_atomic_exclusive(history, accepted.canonical_json())
        final = SchemaRevision(pending.module, pending.schema, pending.schema_digest,
            pending.parent_schema_digest, pending.evolution_plan_digest, pending.migration_revision,
            pending.policy_digest, LifecycleState.ACCEPTED, pending.reversible,
            "", pending.version)
        body = final.canonical_dict(); body.pop("revision_identity")
        final = SchemaRevision(final.module, final.schema, final.schema_digest, final.parent_schema_digest,
            final.evolution_plan_digest, final.migration_revision, final.policy_digest,
            final.lifecycle_state, final.reversible, _digest("arcacore-schema-revision/v1", body), final.version)
        write_text_atomic(self.lifecycle._path(final.module, "accepted"), final.canonical_json())
        self.lifecycle._path(final.module, "pending").unlink(missing_ok=True)
        self._write_journal(ExecutionStatus(ExecutionState.COMPLETE, final.module, status.migration_revision, status.manifest_identity))

    def recover(self, current, proposed, policy=None):
        status = self.status(current.name)
        if status is None: raise ValueError("No migration execution requires recovery.")
        # Finalization may have advanced accepted state before the journal write.
        accepted_on_disk = self.lifecycle.accepted(current.name)
        if (accepted_on_disk.schema_digest == schema_digest(proposed)
                and status.state == ExecutionState.DATABASE_COMMITTED):
            self.lifecycle._path(current.name, "pending").unlink(missing_ok=True)
            self._write_journal(ExecutionStatus(ExecutionState.COMPLETE, current.name,
                                                status.migration_revision, status.manifest_identity))
            return "FINALIZED"
        if status.state in (ExecutionState.ROLLBACK_STARTED, ExecutionState.ROLLBACK_DATABASE_COMMITTED):
            policy = policy or MigrationPolicy()
            accepted = self.lifecycle.verify_current(current)
            manifest = load_manifest(self.lifecycle._path(current.name, "manifest"))
            migration = generate_alembic_migration(
                plan_schema_evolution(proposed, current), policy=policy,
                down_revision=manifest.predecessor_revision)
            manifest.validate_content(migration.content)
            engine = create_engine(self._database_url, poolclass=NullPool)
            try:
                with engine.begin() as connection:
                    self._lock(connection, current.name); row = self._db_state(connection, current.name)
                    if (None if row is None else row[0]) == manifest.predecessor_revision:
                        historical = load_revision(self._history_path(manifest.old_schema_digest))
                        if historical.schema_digest != schema_digest(proposed):
                            raise ValueError("Rollback schema provenance mismatch.")
                        write_text_atomic(self.lifecycle._path(current.name, "accepted"), historical.canonical_json())
                        self._write_journal(ExecutionStatus(ExecutionState.COMPLETE, current.name, migration.revision, manifest.manifest_identity))
                        return "ROLLBACK_FINALIZED"
                    if row is not None and row[0] == migration.revision:
                        self._write_journal(ExecutionStatus(ExecutionState.COMPLETE, current.name, migration.revision, manifest.manifest_identity))
                        return "ROLLBACK_RETRY_SAFE"
                    raise ValueError("Rollback database state cannot be reconciled safely.")
            finally: engine.dispose()
        policy = policy or MigrationPolicy(); accepted, pending, manifest, migration = self._validated(current, proposed, policy)
        engine = create_engine(self._database_url, poolclass=NullPool)
        try:
            with engine.begin() as connection:
                self._lock(connection, current.name); row = self._db_state(connection, current.name)
                if row is not None and row[0] == migration.revision and row[1] == manifest.manifest_identity:
                    committed = ExecutionStatus(ExecutionState.DATABASE_COMMITTED, current.name, migration.revision, manifest.manifest_identity)
                elif (None if row is None else row[0]) == accepted.migration_revision:
                    self._write_journal(ExecutionStatus(ExecutionState.COMPLETE, current.name, migration.revision, manifest.manifest_identity)); return "RETRY_SAFE"
                else: raise ValueError("Database state cannot be reconciled safely.")
        finally: engine.dispose()
        self._finalize(accepted, pending, committed); return "FINALIZED"

    def rollback(self, current, previous, policy=None, *, interrupt_after_commit=False):
        policy = policy or MigrationPolicy(); accepted = self.lifecycle.verify_current(current)
        manifest = load_manifest(self.lifecycle._path(current.name, "manifest"))
        if not manifest.reversible or accepted.migration_revision != manifest.migration_revision:
            raise ValueError("Migration is not honestly reversible.")
        plan = plan_schema_evolution(previous, current)
        migration = generate_alembic_migration(plan, policy=policy, down_revision=manifest.predecessor_revision)
        manifest.validate_content(migration.content)
        historical = load_revision(self._history_path(manifest.old_schema_digest))
        if historical.schema_digest != schema_digest(previous): raise ValueError("Rollback schema provenance mismatch.")
        engine = create_engine(self._database_url, poolclass=NullPool)
        self._write_journal(ExecutionStatus(ExecutionState.ROLLBACK_STARTED, current.name, migration.revision, manifest.manifest_identity))
        try:
            with engine.begin() as connection:
                self._lock(connection, current.name); row = self._db_state(connection, current.name)
                if row is None or row[0] != migration.revision or row[1] != manifest.manifest_identity:
                    raise ValueError("Database revision does not permit rollback.")
                _execute(migration, connection, "downgrade")
                connection.execute(text("UPDATE arcacore_migration_state SET revision=:r, manifest_identity=:i WHERE module=:m"),
                                   {"r": manifest.predecessor_revision, "i": "0" * 64, "m": current.name})
        finally: engine.dispose()
        self._write_journal(ExecutionStatus(ExecutionState.ROLLBACK_DATABASE_COMMITTED, current.name, migration.revision, manifest.manifest_identity))
        if interrupt_after_commit: raise InterruptedError("Simulated interruption after rollback database commit.")
        write_text_atomic(self.lifecycle._path(current.name, "accepted"), historical.canonical_json())
        self._write_journal(ExecutionStatus(ExecutionState.COMPLETE, current.name, migration.revision, manifest.manifest_identity))
        return historical
