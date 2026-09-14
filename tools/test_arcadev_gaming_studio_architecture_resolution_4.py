"""Current resolved authority, explicit required gate, historical selection, no downgrade."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from arcadev import gaming_studio_authority as authority
from arcadev.gaming_studio_architecture_resolution import RESOLUTION_AREA
from arcadev.gaming_studio_architecture_resolution_checkpoint import RESOLUTION_PACKAGE_FILES
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes


class ArchitectureResolutionAuthorityTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "authority"
        shutil.copytree(AUTHORITY_DIRECTORY, self.root)

    def remove_area(self, relative):
        target = (self.root / relative).resolve()
        self.assertTrue(target.is_relative_to(self.root.resolve()))
        self.assertNotEqual(target, self.root.resolve())
        shutil.rmtree(target)

    def test_unqualified_current_selects_resolved_checkpoint_and_retains_history(self):
        result = authority.validate_production_authority(self.root)
        raw = (self.root / RESOLUTION_AREA / "checkpoint.json").read_bytes()
        self.assertTrue(result["valid"])
        self.assertEqual(result["checkpoint"], json.loads(raw))
        self.assertEqual(result["checkpoint_digest"], digest_bytes(raw))
        self.assertEqual(result["checkpoint"]["status"], "ARCHITECTURE_READY_FOR_APPROVAL")
        self.assertEqual(result["unresolved_architecture_checkpoint"]["status"], "BLOCKED_PENDING_ARCHITECTURE_CLARIFICATION")
        self.assertEqual(result["pre_architecture_checkpoint"]["status"], "ARCHITECTURE_READY_FOR_GENERATION")
        self.assertEqual(result["ready_for_approval_checkpoint"]["status"], "PLAN_READY_FOR_APPROVAL")
        self.assertEqual(result["unanswered_plan_checkpoint"]["status"], "BLOCKED_PENDING_PLAN_CLARIFICATION")
        self.assertEqual(result["idea_checkpoint"]["status"], "PLAN_READY_FOR_GENERATION")
        self.assertEqual(result["seed_checkpoint"]["current_stage"], "IDEA")

    def test_explicit_cli_resolution_gate_reports_only_unapproved_architecture(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(authority.main([str(self.root), "--require-architecture-resolution"]), 0)
        cp = json.loads(output.getvalue())["checkpoint"]
        self.assertEqual(cp["accepted_decision_count"], 8)
        self.assertEqual(cp["unresolved_question_count"], 0)
        self.assertEqual(cp["conflict_count"], 0)
        self.assertTrue(cp["effective_ready_for_approval"])
        self.assertEqual(cp["next_authorized_action"], "REQUEST_EXPLICIT_ARCHITECTURE_APPROVAL")
        self.assertFalse(cp["architecture_approved"])
        self.assertFalse(cp["models_authorized"])

    def test_missing_entire_resolution_cannot_downgrade_current_validation(self):
        self.remove_area(RESOLUTION_AREA)
        for options in ({}, {"require_architecture_resolution": True}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, "unknown or missing"):
                authority.validate_production_authority(self.root, **options)
        with patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit) as raised:
            authority.main([str(self.root), "--require-architecture-resolution"])
        self.assertEqual(raised.exception.code, 1)

    def test_each_missing_resolution_file_rejected_without_fallback(self):
        for name in RESOLUTION_PACKAGE_FILES:
            path = self.root / RESOLUTION_AREA / name
            original = path.read_bytes()
            path.unlink()
            try:
                for options in ({}, {"require_architecture_resolution": True}):
                    with self.subTest(name=name, options=options), self.assertRaises(ValueError):
                        authority.validate_production_authority(self.root, **options)
            finally:
                path.write_bytes(original)

    def test_explicit_historical_architecture_and_seed_remain_usable(self):
        old = authority.validate_production_authority(self.root, require_architecture=True)
        self.assertEqual(old["checkpoint"], json.loads((self.root / "production_architecture/checkpoint.json").read_bytes()))
        self.assertEqual(old["checkpoint"]["unresolved_question_count"], 8)
        seed = authority.validate_production_authority(self.root, seed_only=True)
        self.assertEqual(seed["checkpoint"], json.loads((self.root / "checkpoint.json").read_bytes()))

    def test_incompatible_seed_and_required_resolution_rejected(self):
        with self.assertRaises(ValueError):
            authority.validate_production_authority(self.root, seed_only=True, require_architecture_resolution=True)

    def test_fake_approval_models_domain_model_and_application_authority_rejected(self):
        for parent in (self.root, self.root / "production_architecture", self.root / RESOLUTION_AREA):
            for name in ("approved_architecture.json", "architecture_models_handoff.json", "domain_model.json",
                         "backend.json", "frontend.json", "project.json", "unknown.json"):
                path = parent / name
                path.write_bytes(b"{}\n")
                try:
                    with self.subTest(parent=parent, name=name), self.assertRaises(ValueError):
                        authority.validate_production_authority(self.root)
                finally:
                    path.unlink()
        path = self.root / RESOLUTION_AREA / "checkpoint.json"
        original = path.read_bytes()
        for key, value in (("current_stage", "MODELS"), ("architecture_approved", True), ("models_authorized", True)):
            cp = json.loads(original)
            cp[key] = value
            path.write_bytes(canonical_bytes(cp))
            with self.subTest(key=key), self.assertRaises(ValueError):
                authority.validate_production_authority(self.root)

    def test_linked_resolution_and_noncanonical_current_checkpoint_rejected(self):
        area = self.root / RESOLUTION_AREA
        original = Path.is_symlink
        with patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p == area or original(p)):
            with self.assertRaisesRegex(ValueError, "links"):
                authority.validate_production_authority(self.root)
        (area / "checkpoint.json").write_bytes(b'{"schema":1,"schema":2}\n')
        with self.assertRaises(ValueError):
            authority.validate_production_authority(self.root)


if __name__ == "__main__":
    unittest.main()
