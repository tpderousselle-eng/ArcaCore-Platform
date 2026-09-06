import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.alembic_migration import BackfillPolicy, DataTransform, MigrationPolicy, TransformKind, UnsafeMigrationError
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.schema_lifecycle import (LifecycleClassification, LifecycleState, MigrationManifest,
    SchemaLifecycle, SchemaRevision, load_manifest, load_revision, schema_digest)


def module(fields):
    return ModuleDefinition("item", "Item", "item", "items", parse_fields("item", fields))


class SchemaLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.root = Path(self.temp.name)
        self.lifecycle = SchemaLifecycle(self.root)
        self.v1 = module(["name:str"])

    def tearDown(self): self.temp.cleanup()

    def test_first_snapshot_is_canonical_and_deterministic(self):
        state = self.lifecycle.initialize(self.v1)
        self.assertEqual(state.lifecycle_state, LifecycleState.ACCEPTED)
        self.assertIsNone(state.parent_schema_digest)
        self.assertEqual(state.canonical_json(), load_revision(self.lifecycle._path("item", "accepted")).canonical_json())
        self.assertNotIn(str(self.root), state.canonical_json())

    def test_unchanged_regeneration(self):
        self.lifecycle.initialize(self.v1)
        self.assertEqual(self.lifecycle.render(self.v1, self.v1)[0], LifecycleClassification.UNCHANGED)

    def test_safe_additive_render_stays_pending(self):
        accepted = self.lifecycle.initialize(self.v1)
        classification, pending, manifest = self.lifecycle.render(self.v1, module(["name:str", "note:str:nullable"]))
        self.assertEqual(classification, LifecycleClassification.SAFE_ADDITIVE)
        self.assertEqual(pending.lifecycle_state, LifecycleState.PENDING_EXECUTION)
        self.assertEqual(self.lifecycle.accepted("item").schema_digest, accepted.schema_digest)
        content = next(self.lifecycle.migration_dir.iterdir()).read_text(encoding="utf-8")
        load_manifest(self.lifecycle._path("item", "manifest")).validate_content(content)

    def test_policy_required_transition(self):
        self.lifecycle.initialize(self.v1); v2 = module(["name:str", "code:str"])
        policy = MigrationPolicy(backfills=(BackfillPolicy("code", DataTransform(TransformKind.LITERAL, "x")),))
        classification, _, _ = self.lifecycle.render(self.v1, v2, policy=policy)
        self.assertEqual(classification, LifecycleClassification.REQUIRES_POLICY)

    def test_destructive_and_unsupported_fail_without_state_change(self):
        accepted = self.lifecycle.initialize(self.v1).canonical_json()
        for proposed in (module([]), module(["name:int"])):
            with self.assertRaises(UnsafeMigrationError): self.lifecycle.render(self.v1, proposed)
            self.assertEqual(self.lifecycle.accepted("item").canonical_json(), accepted)

    def test_drift_is_actionable(self):
        self.lifecycle.initialize(self.v1)
        with self.assertRaisesRegex(ValueError, "DRIFTED"): self.lifecycle.plan(module(["name:str", "x:str:nullable"]), self.v1)

    def test_forged_state_and_hostile_metadata_rejected(self):
        state = self.lifecycle.initialize(self.v1); value = state.canonical_dict(); value["schema"]["table_name"] = "forged"
        with self.assertRaisesRegex(ValueError, "digest mismatch"): SchemaRevision.from_dict(value)
        with self.assertRaises(ValueError): SchemaLifecycle(self.root)._path("../../escape", "accepted")

    def test_forged_manifest_and_content_rejected(self):
        self.lifecycle.initialize(self.v1)
        _, _, manifest = self.lifecycle.render(self.v1, module(["name:str", "note:str:nullable"]))
        value = manifest.canonical_dict(); value["new_schema_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "identity mismatch"): MigrationManifest.from_dict(value)
        with self.assertRaisesRegex(ValueError, "content digest mismatch"): manifest.validate_content("forged")

    def test_lineage_rejects_missing_forged_duplicate_and_fork(self):
        root = SchemaRevision.create(self.v1)
        v2 = SchemaRevision.create(module(["name:str", "x:str:nullable"]), parent_schema_digest=root.schema_digest)
        self.assertTrue(self.lifecycle.validate_lineage([root, v2]))
        with self.assertRaises(ValueError): self.lifecycle.validate_lineage([v2])
        with self.assertRaises(ValueError): self.lifecycle.validate_lineage([root, root])
        bad = SchemaRevision.create(module(["name:str", "y:str:nullable"]), parent_schema_digest="0" * 64)
        with self.assertRaises(ValueError): self.lifecycle.validate_lineage([root, bad])

    def test_multiple_sequential_revisions_are_stable(self):
        root = SchemaRevision.create(self.v1)
        second = SchemaRevision.create(module(["name:str", "x:str:nullable"]), parent_schema_digest=root.schema_digest)
        third = SchemaRevision.create(module(["name:str", "x:str:nullable", "y:str:nullable"]), parent_schema_digest=second.schema_digest)
        self.assertTrue(self.lifecycle.validate_lineage([root, second, third]))
        self.assertEqual(schema_digest(self.v1), schema_digest(self.v1))

    def test_failed_or_interrupted_render_preserves_state_and_artifacts(self):
        accepted = self.lifecycle.initialize(self.v1).canonical_json(); v2 = module(["name:str", "x:str:nullable"])
        with patch("tools.schema_lifecycle.write_text_atomic_exclusive", side_effect=[None, OSError("interrupted")]):
            with self.assertRaises(OSError): self.lifecycle.render(self.v1, v2)
        self.assertEqual(self.lifecycle.accepted("item").canonical_json(), accepted)
        self.assertFalse(self.lifecycle._path("item", "pending").exists())

    def test_pending_revision_prevents_fork_and_stale_proposal(self):
        self.lifecycle.initialize(self.v1); self.lifecycle.render(self.v1, module(["name:str", "x:str:nullable"]))
        with self.assertRaisesRegex(ValueError, "pending.*fork"):
            self.lifecycle.render(self.v1, module(["name:str", "y:str:nullable"]))


if __name__ == "__main__": unittest.main()
