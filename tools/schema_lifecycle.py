"""Content-addressed schema migration lifecycle state.

This layer records planning facts only.  Database execution is deliberately
outside this module and a rendered revision never advances accepted state.
"""

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from tools.alembic_migration import MigrationPolicy, generate_alembic_migration
from tools.core.engine import write_text_atomic, write_text_atomic_exclusive
from tools.core.module_definition import ModuleDefinition, valid_public_identifier, validate_module_definition
from tools.schema_evolution import SafetyClassification, _module_state, plan_schema_evolution


STATE_VERSION = 1
HEX64 = frozenset("0123456789abcdef")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _digest(domain: str, value: Any) -> str:
    return sha256(domain.encode("ascii") + b"\0" + _json(value).encode("utf-8")).hexdigest()


def _hex(value: Any, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and set(value) <= HEX64


def canonical_schema(module: ModuleDefinition) -> dict[str, Any]:
    validate_module_definition(module)
    return _module_state(module)


def schema_digest(module: ModuleDefinition) -> str:
    return _digest("arcacore-schema/v1", canonical_schema(module))


class LifecycleState(str, Enum):
    ACCEPTED = "ACCEPTED"
    PLANNED = "PLANNED"
    RENDERED = "RENDERED"
    PENDING_EXECUTION = "PENDING_EXECUTION"


class LifecycleClassification(str, Enum):
    UNCHANGED = "UNCHANGED"
    SAFE_ADDITIVE = "SAFE_ADDITIVE"
    REQUIRES_POLICY = "REQUIRES_POLICY"
    POTENTIALLY_DESTRUCTIVE = "POTENTIALLY_DESTRUCTIVE"
    UNSUPPORTED = "UNSUPPORTED"
    DRIFTED = "DRIFTED"


@dataclass(frozen=True)
class SchemaRevision:
    module: str
    schema: dict[str, Any]
    schema_digest: str
    parent_schema_digest: str | None
    evolution_plan_digest: str | None
    migration_revision: str | None
    policy_digest: str | None
    lifecycle_state: LifecycleState
    reversible: bool | None
    revision_identity: str
    version: int = STATE_VERSION

    @classmethod
    def create(cls, module: ModuleDefinition, *, parent_schema_digest=None,
               plan_digest=None, migration_revision=None, policy_digest=None,
               state=LifecycleState.ACCEPTED, reversible=None):
        schema = canonical_schema(module)
        digest = schema_digest(module)
        body = {"version": STATE_VERSION, "module": module.name, "schema": schema,
                "schema_digest": digest, "parent_schema_digest": parent_schema_digest,
                "evolution_plan_digest": plan_digest, "migration_revision": migration_revision,
                "policy_digest": policy_digest, "lifecycle_state": state.value,
                "reversible": reversible}
        return cls(module.name, schema, digest, parent_schema_digest, plan_digest,
                   migration_revision, policy_digest, state, reversible,
                   _digest("arcacore-schema-revision/v1", body))

    def canonical_dict(self):
        return {"version": self.version, "module": self.module, "schema": self.schema,
                "schema_digest": self.schema_digest, "parent_schema_digest": self.parent_schema_digest,
                "evolution_plan_digest": self.evolution_plan_digest,
                "migration_revision": self.migration_revision, "policy_digest": self.policy_digest,
                "lifecycle_state": self.lifecycle_state.value, "reversible": self.reversible,
                "revision_identity": self.revision_identity}

    def canonical_json(self):
        return _json(self.canonical_dict())

    @classmethod
    def from_dict(cls, value):
        keys = {"version", "module", "schema", "schema_digest", "parent_schema_digest",
                "evolution_plan_digest", "migration_revision", "policy_digest",
                "lifecycle_state", "reversible", "revision_identity"}
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError("Schema revision has an invalid shape.")
        try:
            state = LifecycleState(value["lifecycle_state"])
        except (ValueError, TypeError) as error:
            raise ValueError("Schema revision has an invalid lifecycle state.") from error
        if value["version"] != STATE_VERSION or not valid_public_identifier(value["module"]):
            raise ValueError("Schema revision metadata is invalid.")
        if not isinstance(value["schema"], dict) or value["schema"].get("name") != value["module"]:
            raise ValueError("Schema revision schema is invalid.")
        for key in ("schema_digest", "revision_identity"):
            if not _hex(value[key]): raise ValueError("Schema revision digest is invalid.")
        for key in ("parent_schema_digest", "evolution_plan_digest", "policy_digest"):
            if value[key] is not None and not _hex(value[key]): raise ValueError("Schema revision reference is invalid.")
        revision = value["migration_revision"]
        if revision is not None and (not isinstance(revision, str) or len(revision) != 12 or not _hex(revision, 12)):
            raise ValueError("Migration revision is invalid.")
        if value["reversible"] not in (True, False, None): raise ValueError("Reversibility is invalid.")
        expected_schema = _digest("arcacore-schema/v1", value["schema"])
        if value["schema_digest"] != expected_schema: raise ValueError("Schema state digest mismatch.")
        body = dict(value); identity = body.pop("revision_identity")
        if identity != _digest("arcacore-schema-revision/v1", body):
            raise ValueError("Schema revision identity mismatch.")
        return cls(value["module"], value["schema"], value["schema_digest"],
                   value["parent_schema_digest"], value["evolution_plan_digest"], revision,
                   value["policy_digest"], state, value["reversible"], identity, value["version"])


@dataclass(frozen=True)
class MigrationManifest:
    module: str
    old_schema_digest: str
    new_schema_digest: str
    evolution_plan_digest: str
    migration_revision: str
    migration_content_digest: str
    policy_digest: str
    predecessor_revision: str | None
    reversible: bool
    manifest_identity: str
    version: int = STATE_VERSION

    @classmethod
    def create(cls, *, module, old_schema_digest, new_schema_digest, plan_digest,
               migration, policy_digest, predecessor_revision, reversible):
        body = {"version": STATE_VERSION, "module": module,
                "old_schema_digest": old_schema_digest, "new_schema_digest": new_schema_digest,
                "evolution_plan_digest": plan_digest, "migration_revision": migration.revision,
                "migration_content_digest": sha256(migration.content.encode("utf-8")).hexdigest(),
                "policy_digest": policy_digest, "predecessor_revision": predecessor_revision,
                "reversible": reversible}
        return cls(module, old_schema_digest, new_schema_digest, plan_digest, migration.revision,
                   body["migration_content_digest"], policy_digest, predecessor_revision,
                   reversible, _digest("arcacore-migration-manifest/v1", body))

    def canonical_dict(self):
        return {"version": self.version, "module": self.module,
                "old_schema_digest": self.old_schema_digest, "new_schema_digest": self.new_schema_digest,
                "evolution_plan_digest": self.evolution_plan_digest,
                "migration_revision": self.migration_revision,
                "migration_content_digest": self.migration_content_digest,
                "policy_digest": self.policy_digest, "predecessor_revision": self.predecessor_revision,
                "reversible": self.reversible, "manifest_identity": self.manifest_identity}

    def canonical_json(self): return _json(self.canonical_dict())

    @classmethod
    def from_dict(cls, value):
        keys = {"version", "module", "old_schema_digest", "new_schema_digest",
                "evolution_plan_digest", "migration_revision", "migration_content_digest",
                "policy_digest", "predecessor_revision", "reversible", "manifest_identity"}
        if not isinstance(value, dict) or set(value) != keys or value["version"] != STATE_VERSION:
            raise ValueError("Migration manifest has an invalid shape.")
        if not valid_public_identifier(value["module"]) or type(value["reversible"]) is not bool:
            raise ValueError("Migration manifest metadata is invalid.")
        for key in ("old_schema_digest", "new_schema_digest", "evolution_plan_digest",
                    "migration_content_digest", "policy_digest", "manifest_identity"):
            if not _hex(value[key]): raise ValueError("Migration manifest digest is invalid.")
        if len(value["migration_revision"]) != 12 or not _hex(value["migration_revision"], 12):
            raise ValueError("Migration manifest revision is invalid.")
        predecessor = value["predecessor_revision"]
        if predecessor is not None and (not isinstance(predecessor, str) or len(predecessor) != 12 or not _hex(predecessor, 12)):
            raise ValueError("Migration predecessor is invalid.")
        body = dict(value); identity = body.pop("manifest_identity")
        if identity != _digest("arcacore-migration-manifest/v1", body):
            raise ValueError("Migration manifest identity mismatch.")
        return cls(value["module"], value["old_schema_digest"], value["new_schema_digest"],
                   value["evolution_plan_digest"], value["migration_revision"],
                   value["migration_content_digest"], value["policy_digest"], predecessor,
                   value["reversible"], identity, value["version"])

    def validate_content(self, content: str):
        if sha256(content.encode("utf-8")).hexdigest() != self.migration_content_digest:
            raise ValueError("Migration content digest mismatch.")


def load_revision(path: Path) -> SchemaRevision:
    try: value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error: raise ValueError("Cannot load schema revision.") from error
    return SchemaRevision.from_dict(value)


def load_manifest(path: Path) -> MigrationManifest:
    try: value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error: raise ValueError("Cannot load migration manifest.") from error
    return MigrationManifest.from_dict(value)


def classify_plan(plan) -> LifecycleClassification:
    if plan.is_empty: return LifecycleClassification.UNCHANGED
    safeties = {change.safety for change in plan.changes}
    if SafetyClassification.UNSUPPORTED in safeties: return LifecycleClassification.UNSUPPORTED
    if SafetyClassification.POTENTIALLY_DESTRUCTIVE in safeties: return LifecycleClassification.POTENTIALLY_DESTRUCTIVE
    if SafetyClassification.REQUIRES_DATA_MIGRATION in safeties: return LifecycleClassification.REQUIRES_POLICY
    return LifecycleClassification.SAFE_ADDITIVE


class SchemaLifecycle:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.state_dir = self.root / ".arcacore" / "schema"
        self.migration_dir = self.root / ".arcacore" / "migrations"

    def _path(self, module, suffix):
        if not valid_public_identifier(module): raise ValueError("Invalid lifecycle module.")
        path = (self.state_dir / f"{module}.{suffix}.json").resolve()
        path.relative_to(self.root)
        return path

    def initialize(self, module: ModuleDefinition):
        path = self._path(module.name, "accepted")
        if path.exists(): raise ValueError("Accepted schema already exists.")
        revision = SchemaRevision.create(module)
        write_text_atomic_exclusive(path, revision.canonical_json())
        return revision

    def accepted(self, module: str): return load_revision(self._path(module, "accepted"))

    def verify_current(self, current: ModuleDefinition):
        accepted = self.accepted(current.name)
        if accepted.lifecycle_state != LifecycleState.ACCEPTED or schema_digest(current) != accepted.schema_digest:
            raise ValueError("DRIFTED: current schema does not match accepted schema state.")
        return accepted

    def plan(self, current: ModuleDefinition, proposed: ModuleDefinition):
        self.verify_current(current)
        return plan_schema_evolution(current, proposed)

    def render(self, current: ModuleDefinition, proposed: ModuleDefinition, *, policy=None):
        accepted = self.verify_current(current)
        pending_path = self._path(current.name, "pending")
        if pending_path.exists(): raise ValueError("A pending schema revision already exists; refusing a fork.")
        plan = plan_schema_evolution(current, proposed)
        if plan.is_empty: return LifecycleClassification.UNCHANGED, None, None
        policy = policy or MigrationPolicy()
        migration = generate_alembic_migration(plan, policy=policy,
                                                down_revision=accepted.migration_revision)
        plan_digest = sha256(plan.canonical_json().encode("utf-8")).hexdigest()
        policy_digest = _digest("arcacore-migration-policy/v1", policy.canonical_dict())
        reversible = "raise RuntimeError(" not in migration.content.split("def downgrade():", 1)[1]
        manifest = MigrationManifest.create(module=proposed.name,
            old_schema_digest=accepted.schema_digest, new_schema_digest=schema_digest(proposed),
            plan_digest=plan_digest, migration=migration, policy_digest=policy_digest,
            predecessor_revision=accepted.migration_revision, reversible=reversible)
        pending = SchemaRevision.create(proposed, parent_schema_digest=accepted.schema_digest,
            plan_digest=plan_digest, migration_revision=migration.revision,
            policy_digest=policy_digest, state=LifecycleState.PENDING_EXECUTION,
            reversible=reversible)
        migration_path = (self.migration_dir / migration.filename).resolve()
        manifest_path = self._path(proposed.name, "manifest")
        created = []
        try:
            for path, content in ((migration_path, migration.content),
                                  (manifest_path, manifest.canonical_json()),
                                  (pending_path, pending.canonical_json())):
                path.relative_to(self.root)
                write_text_atomic_exclusive(path, content); created.append(path)
        except Exception:
            for path in reversed(created): path.unlink(missing_ok=True)
            raise
        return classify_plan(plan), pending, manifest

    def validate_lineage(self, revisions):
        seen = set(); previous = None
        for revision in revisions:
            if not isinstance(revision, SchemaRevision): raise ValueError("Invalid lineage member.")
            if revision.revision_identity in seen: raise ValueError("Duplicate schema revision identity.")
            if previous is None:
                if revision.parent_schema_digest is not None: raise ValueError("Root schema revision has a predecessor.")
            elif revision.parent_schema_digest != previous.schema_digest:
                raise ValueError("Missing or forged schema predecessor.")
            seen.add(revision.revision_identity); previous = revision
        return True
