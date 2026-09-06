from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from tools.alembic_migration import MigrationPolicy
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.migration_execution import ExecutionState, MigrationExecutor
from tools.postgresql_test_server import postgresql_test_server
from tools.schema_lifecycle import SchemaLifecycle, load_revision


def module(fields): return ModuleDefinition("item", "Item", "item", "items", parse_fields("item", fields))


class MigrationExecutionPostgreSQLTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = postgresql_test_server(); cls.server = cls.ctx.__enter__()

    @classmethod
    def tearDownClass(cls): cls.ctx.__exit__(None, None, None)

    def setUp(self):
        self.temp = TemporaryDirectory(); self.root = Path(self.temp.name)
        self.v1 = module(["name:str"]); self.v2 = module(["name:str", "note:text:nullable"])
        self.lifecycle = SchemaLifecycle(self.root); self.lifecycle.initialize(self.v1); self.lifecycle.render(self.v1, self.v2)
        self.engine = create_engine(self.server.url, poolclass=NullPool)
        with self.engine.begin() as c:
            c.execute(text("DROP TABLE IF EXISTS arcacore_migration_state")); c.execute(text("DROP TABLE IF EXISTS items"));
            c.execute(text("CREATE TABLE items (id SERIAL PRIMARY KEY, name VARCHAR NOT NULL)")); c.execute(text("INSERT INTO items(name) VALUES ('a')"))
        self.executor = MigrationExecutor(self.root, self.server.url, lock_timeout=.2)

    def tearDown(self): self.engine.dispose(); self.temp.cleanup()

    def test_preflight_apply_data_state_rollback_and_reapply(self):
        self.executor.preflight(self.v1, self.v2)
        result = self.executor.apply(self.v1, self.v2); self.assertEqual(result.state, ExecutionState.COMPLETE)
        self.assertIn("note", {c["name"] for c in inspect(self.engine).get_columns("items")})
        self.assertEqual(self.lifecycle.accepted("item").schema_digest, __import__("tools.schema_lifecycle", fromlist=["schema_digest"]).schema_digest(self.v2))
        self.executor.rollback(self.v2, self.v1)
        self.assertNotIn("note", {c["name"] for c in inspect(self.engine).get_columns("items")})
        # Render a fresh pending artifact and apply it again.
        self.lifecycle._path("item", "manifest").unlink(); self.lifecycle._path("item", "execution").unlink()
        self.lifecycle.render(self.v1, self.v2); self.executor.apply(self.v1, self.v2)

    def test_database_failure_never_accepts_pending_state(self):
        with self.engine.begin() as c: c.execute(text("DROP TABLE items"))
        old = self.lifecycle.accepted("item").schema_digest
        with self.assertRaises(RuntimeError): self.executor.apply(self.v1, self.v2)
        self.assertEqual(self.lifecycle.accepted("item").schema_digest, old)

    def test_commit_before_finalization_recovers_without_rerun(self):
        with self.assertRaises(InterruptedError): self.executor.apply(self.v1, self.v2, interrupt_after_commit=True)
        self.assertEqual(self.executor.status("item").state, ExecutionState.DATABASE_COMMITTED)
        self.assertEqual(self.executor.recover(self.v1, self.v2), "FINALIZED")
        self.assertEqual(self.executor.status("item").state, ExecutionState.COMPLETE)

    def test_invalid_database_revision_forgery_and_stale_manifest_fail(self):
        with self.engine.begin() as c:
            c.execute(text("CREATE TABLE arcacore_migration_state (module VARCHAR(63) PRIMARY KEY, revision VARCHAR(12), manifest_identity VARCHAR(64) NOT NULL)"))
            c.execute(text("INSERT INTO arcacore_migration_state VALUES ('item','aaaaaaaaaaaa',:i)"), {"i": "0"*64})
        with self.assertRaisesRegex(ValueError, "Database revision"): self.executor.preflight(self.v1, self.v2)
        path = self.lifecycle._path("item", "manifest"); value = __import__("json").loads(path.read_text()); value["migration_content_digest"] = "0"*64; path.write_text(__import__("json").dumps(value))
        with self.assertRaises(ValueError): self.executor.preflight(self.v1, self.v2)

    def test_lock_contention_times_out_and_releases(self):
        key = self.executor._lock_id("item")
        blocker = self.engine.connect(); transaction = blocker.begin(); blocker.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
        try:
            with self.assertRaises(TimeoutError): self.executor.preflight(self.v1, self.v2)
        finally: transaction.rollback(); blocker.close()
        self.executor.preflight(self.v1, self.v2)

    def test_started_journal_recovery_marks_retry_safe_after_interruption(self):
        from tools.migration_execution import ExecutionStatus
        manifest = self.executor.preflight(self.v1, self.v2)
        self.executor._write_journal(ExecutionStatus(ExecutionState.STARTED, "item", manifest.migration_revision, manifest.manifest_identity))
        self.assertEqual(self.executor.recover(self.v1, self.v2), "RETRY_SAFE")

    def test_rollback_commit_interruption_is_recoverable(self):
        self.executor.apply(self.v1, self.v2)
        with self.assertRaises(InterruptedError):
            self.executor.rollback(self.v2, self.v1, interrupt_after_commit=True)
        self.assertEqual(self.executor.recover(self.v2, self.v1), "ROLLBACK_FINALIZED")
        self.assertEqual(self.lifecycle.accepted("item").schema_digest,
                         __import__("tools.schema_lifecycle", fromlist=["schema_digest"]).schema_digest(self.v1))

    def test_forged_journal_is_rejected(self):
        manifest = self.executor.preflight(self.v1, self.v2)
        from tools.migration_execution import ExecutionStatus
        self.executor._write_journal(ExecutionStatus(ExecutionState.STARTED, "item", manifest.migration_revision, manifest.manifest_identity))
        path = self.executor._journal_path("item"); value = __import__("json").loads(path.read_text()); value["state"] = "COMPLETE"; path.write_text(__import__("json").dumps(value))
        with self.assertRaisesRegex(ValueError, "digest mismatch"): self.executor.status("item")

    def test_unsafe_rollback_refuses(self):
        manifest_path = self.lifecycle._path("item", "manifest"); value = __import__("json").loads(manifest_path.read_text()); value["reversible"] = False
        from tools.schema_lifecycle import _digest
        body = dict(value); body.pop("manifest_identity"); value["manifest_identity"] = _digest("arcacore-migration-manifest/v1", body); manifest_path.write_text(__import__("json").dumps(value))
        with self.assertRaisesRegex(ValueError, "not honestly reversible"): self.executor.rollback(self.v1, self.v1)

    def test_credentials_are_not_disclosed(self):
        secret_url = "postgresql://postgres:secret-password@127.0.0.1:1/postgres"
        executor = MigrationExecutor(self.root, secret_url)
        try: executor.preflight(self.v1, self.v2)
        except Exception as error: self.assertNotIn("secret-password", str(error))


if __name__ == "__main__": unittest.main()
