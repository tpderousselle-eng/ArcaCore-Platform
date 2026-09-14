"""Current architecture gate, historical packages, and downgrade prevention."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from arcadev import gaming_studio_authority as authority
from arcadev.gaming_studio_architecture import ARCHITECTURE_AREA
from arcadev.gaming_studio_architecture_checkpoint import ARCHITECTURE_PACKAGE_FILES
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes


class ProductionArchitectureAuthorityTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "authority"
        shutil.copytree(AUTHORITY_DIRECTORY, self.root)

    def remove_temporary_area(self, relative):
        target = (self.root / relative).resolve()
        self.assertTrue(target.is_relative_to(self.root.resolve()))
        self.assertNotEqual(target, self.root.resolve())
        shutil.rmtree(target)

    def test_explicit_historical_validation_selects_architecture_and_keeps_history(self):
        result = authority.validate_production_authority(self.root, require_architecture=True)
        raw = (self.root / ARCHITECTURE_AREA / "checkpoint.json").read_bytes()
        self.assertTrue(result["valid"])
        self.assertEqual(result["checkpoint"], json.loads(raw))
        self.assertEqual(result["checkpoint_digest"], digest_bytes(raw))
        self.assertEqual(result["pre_architecture_checkpoint"]["status"], "ARCHITECTURE_READY_FOR_GENERATION")
        self.assertEqual(result["ready_for_approval_checkpoint"]["status"], "PLAN_READY_FOR_APPROVAL")
        self.assertEqual(result["unanswered_plan_checkpoint"]["status"], "BLOCKED_PENDING_PLAN_CLARIFICATION")
        self.assertEqual(result["idea_checkpoint"]["status"], "PLAN_READY_FOR_GENERATION")
        self.assertEqual(result["seed_checkpoint"]["current_stage"], "IDEA")

    def test_cli_requires_architecture_and_reports_unapproved_state(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(authority.main([str(self.root), "--require-architecture"]), 0)
        cp = json.loads(output.getvalue())["checkpoint"]
        self.assertEqual(cp["status"], "BLOCKED_PENDING_ARCHITECTURE_CLARIFICATION")
        self.assertFalse(cp["architecture_approved"])
        self.assertFalse(cp["models_authorized"])

    def test_explicit_gate_rejects_missing_architecture_and_incompatible_seed(self):
        self.remove_temporary_area(ARCHITECTURE_AREA)
        for options in ({}, {"require_architecture": True}):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, "architecture authority is required"):
                authority.validate_production_authority(self.root, **options)
        with self.assertRaises(ValueError):
            authority.validate_production_authority(self.root, seed_only=True, require_architecture=True)
        with patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit) as raised:
            authority.main([str(self.root), "--require-architecture"])
        self.assertEqual(raised.exception.code, 1)

    def test_present_incomplete_architecture_cannot_silently_fall_back(self):
        (self.root / ARCHITECTURE_AREA / "checkpoint.json").unlink()
        with self.assertRaisesRegex(ValueError, "unknown or missing"):
            authority.validate_production_authority(self.root)

    def test_explicit_historical_seed_and_plan_approval_packages_still_validate(self):
        seed = authority.validate_production_authority(self.root, seed_only=True)
        self.assertEqual(seed["checkpoint"], json.loads((self.root / "checkpoint.json").read_bytes()))
        self.remove_temporary_area(ARCHITECTURE_AREA)
        previous = authority.validate_production_authority(self.root, require_plan_approval=True)
        self.assertEqual(previous["checkpoint"]["status"], "ARCHITECTURE_READY_FOR_GENERATION")

    def test_required_architecture_implies_approved_plan(self):
        self.remove_temporary_area("production_plan/plan_approval")
        with self.assertRaisesRegex(ValueError, "PLAN approval authority is required"):
            authority.validate_production_authority(self.root, require_architecture=True)

    def test_later_authority_rejected_at_root_and_architecture_area(self):
        for parent in (self.root, self.root / ARCHITECTURE_AREA):
            for name in ("approved_architecture.json", "architecture_models_handoff.json",
                         "domain_model.json", "backend.json", "frontend.json"):
                path = parent / name
                path.write_bytes(b"{}\n")
                with self.subTest(parent=parent, name=name), self.assertRaises(ValueError):
                    authority.validate_production_authority(self.root)
                path.unlink()


if __name__ == "__main__":
    unittest.main()
