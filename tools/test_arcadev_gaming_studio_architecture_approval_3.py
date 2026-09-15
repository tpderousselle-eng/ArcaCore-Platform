"""Complete MODELS-entry lineage, tamper rejection, and absence of later authority."""

from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from arcadev import gaming_studio_models_entry_checkpoint as checkpoint
from arcadev.gaming_studio_architecture_approval import APPROVAL_AREA, APPROVAL_STATEMENT_DIGEST
from arcadev.gaming_studio_authority import validate_fixture_independence
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes


class ModelsEntryCheckpointTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "authority"
        shutil.copytree(AUTHORITY_DIRECTORY, self.root)
        self.area = self.root / APPROVAL_AREA

    def test_full_public_replay_complete_lineage_without_generation_or_effects(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with ExitStack() as stack:
            for target in ("arcadev.domain_model_engine.generate_baseline_domain_model",
                    "arcadev.domain_model_specification.DomainModelSpecification.create",
                    "arcadev.model_approval.approve_domain_model",
                    "arcadev.models_backend_handoff.ModelsBackendHandoff.create",
                    "arcadev.backend_generation.generate_backend",
                    "subprocess.Popen", "socket.socket", "os.system", "builtins.eval",
                    "pathlib.Path.write_bytes", "pathlib.Path.write_text"):
                stack.enter_context(patch(target, side_effect=AssertionError(target)))
            cp = checkpoint.validate_models_entry_checkpoint(self.root)
        self.assertEqual(cp, json.loads((self.area / "checkpoint.json").read_bytes()))
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(cp["schema"], checkpoint.MODELS_ENTRY_SCHEMA)
        self.assertEqual(cp["schema_version"], 1)
        self.assertEqual(cp["package_version"], 3)
        self.assertEqual(cp["current_stage"], "MODELS")
        self.assertEqual(cp["project_status"], "IN_PROGRESS")
        self.assertIsNone(cp["domain_model_id"])
        for flag in ("domain_model_generated", "domain_model_generation_authorized", "models_approved", "backend_authorized", "frontend_authorized"):
            self.assertIs(cp[flag], False)
        self.assertEqual(cp["status"], checkpoint.MODELS_ENTRY_STATUS)
        self.assertEqual(cp["next_authorized_action"], checkpoint.NEXT_AUTHORIZED_ACTION)
        self.assertEqual(cp["architecture_approval_statement_digest"], APPROVAL_STATEMENT_DIGEST)
        self.assertEqual(set(cp["authority_digests"]), {str(p).replace("\\", "/") for p in before} - {APPROVAL_AREA + "/checkpoint.json"})
        self.assertEqual(cp["authority_digests"], {name: digest_bytes((self.root / name).read_bytes()) for name in cp["authority_digests"]})
        approved = json.loads((self.area / "approved_architecture.json").read_bytes())
        handoff = json.loads((self.area / "architecture_models_handoff.json").read_bytes())
        self.assertEqual(cp["approved_architecture_id"], approved["approval_id"])
        self.assertEqual(cp["architecture_models_handoff_id"], handoff["handoff_id"])
        self.assertEqual(handoff["frozen_approved_architecture"], approved)
        self.assertEqual(cp["architecture_finalization_id"], approved["architecture_finalization_id"])
        self.assertEqual(cp["consistency"], approved["package"]["consistency"])
        self.assertEqual(cp["consistency_warnings"], cp["consistency"]["warnings"])

    def test_every_historical_and_current_authority_byte_is_bound(self):
        cp = json.loads((self.area / "checkpoint.json").read_bytes())
        for name in cp["authority_digests"]:
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            try:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "digests"):
                    checkpoint.validate_models_entry_checkpoint(self.root)
            finally:
                path.write_bytes(original)

    def test_changed_decision_approval_source_handoff_rehash_cannot_authorize(self):
        path = self.area / "checkpoint.json"
        original_cp = path.read_bytes()
        mutations = (
            ("production_architecture/architecture_resolution/architecture_finalization.json", lambda v: v["decisions"][0].update(user_answer="Changed.")),
            (APPROVAL_AREA + "/approval_authorization.json", lambda v: v.update(approval_statement="Changed.")),
            (APPROVAL_AREA + "/approved_architecture.json", lambda v: v.update(architecture_id="another", approval_eligible=True)),
            (APPROVAL_AREA + "/architecture_models_handoff.json", lambda v: v.update(approved_architecture_id="forged")),
            ("production_plan/plan_approval/project.json", lambda v: v.update(current_build_stage="MODELS")),
        )
        for name, mutate in mutations:
            artifact = self.root / name
            original = artifact.read_bytes()
            value = json.loads(original)
            mutate(value)
            artifact.write_bytes(canonical_bytes(value))
            cp = json.loads(original_cp)
            cp["authority_digests"][name] = digest_bytes(artifact.read_bytes())
            path.write_bytes(canonical_bytes(cp))
            try:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "exact approved bytes"):
                    checkpoint.validate_models_entry_checkpoint(self.root)
            finally:
                artifact.write_bytes(original)
                path.write_bytes(original_cp)

    def test_forged_checkpoint_fields_and_paths_rejected(self):
        path = self.area / "checkpoint.json"
        original = path.read_bytes()
        for key, value in (("domain_model_id", "fake"), ("domain_model_generated", True),
                ("models_approved", True), ("backend_authorized", True), ("frontend_authorized", True),
                ("current_stage", "BACKEND"), ("approval_eligible", False), ("consistency_warnings", []),
                ("architecture_finalization_id", "stale"), ("architecture_models_handoff_id", "fake"),
                ("authority_digests", {"//untrusted/share": "fake"}), ("unknown", True)):
            cp = json.loads(original)
            cp[key] = value
            path.write_bytes(canonical_bytes(cp))
            with self.subTest(key=key), self.assertRaises(ValueError):
                checkpoint.validate_models_entry_checkpoint(self.root)
        path.write_bytes(original)

    def test_unknown_fake_models_approvals_backend_frontend_and_fixtures_rejected(self):
        for parent in (self.root, self.root / "production_plan", self.root / "production_architecture", self.area):
            for name in ("domain_model.json", "domain_model_specification.json", "approved_domain_model.json",
                    "models_backend_handoff.json", "backend.json", "frontend.json", "fixture.json", "unknown.json"):
                path = parent / name
                path.write_bytes(b"{}\n")
                try:
                    with self.subTest(parent=parent, name=name), self.assertRaises(ValueError):
                        checkpoint.validate_models_entry_checkpoint(self.root)
                finally:
                    path.unlink()
        validate_fixture_independence()

    def test_missing_files_links_duplicate_noncanonical_and_oversized_rejected(self):
        for name in checkpoint.MODELS_ENTRY_FILES:
            path = self.area / name
            original = path.read_bytes()
            path.unlink()
            try:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    checkpoint.validate_models_entry_checkpoint(self.root)
            finally:
                path.write_bytes(original)
        original_link = Path.is_symlink
        with patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p == self.area or original_link(p)):
            with self.assertRaisesRegex(ValueError, "links"):
                checkpoint.validate_models_entry_checkpoint(self.root)
        path = self.area / "checkpoint.json"
        for raw in (b'{"schema":1,"schema":2}\n', b'{}', b' ' * 100_001, b'\xff'):
            path.write_bytes(raw)
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                checkpoint.validate_models_entry_checkpoint(self.root)


if __name__ == "__main__":
    unittest.main()
