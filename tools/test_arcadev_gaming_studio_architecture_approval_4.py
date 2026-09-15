"""Current MODELS entry, explicit gate, historical modes and no downgrade."""

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from arcadev import gaming_studio_authority as authority
from arcadev.gaming_studio_architecture_approval import APPROVAL_AREA
from arcadev.gaming_studio_models_entry_checkpoint import MODELS_ENTRY_FILES
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, digest_bytes


class ModelsEntryAuthorityTest(unittest.TestCase):
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

    def test_unqualified_current_selects_models_and_preserves_complete_history(self):
        result = authority.validate_production_authority(self.root)
        raw = (self.root / APPROVAL_AREA / "checkpoint.json").read_bytes()
        self.assertTrue(result["valid"] and result["fixture_independent"])
        self.assertEqual(result["checkpoint"], json.loads(raw))
        self.assertEqual(result["checkpoint_digest"], digest_bytes(raw))
        self.assertEqual(result["checkpoint"]["current_stage"], "MODELS")
        self.assertEqual(result["checkpoint"]["project_status"], "IN_PROGRESS")
        self.assertIsNone(result["checkpoint"]["domain_model_id"])
        self.assertFalse(result["checkpoint"]["domain_model_generated"])
        for key, stage in (("seed_checkpoint", "IDEA"), ("idea_checkpoint", "PLAN"),
                ("unanswered_plan_checkpoint", "PLAN"), ("ready_for_approval_checkpoint", "PLAN"),
                ("pre_architecture_checkpoint", "ARCHITECTURE"),
                ("unresolved_architecture_checkpoint", "ARCHITECTURE"),
                ("ready_for_architecture_approval_checkpoint", "ARCHITECTURE")):
            self.assertEqual(result[key]["current_stage"], stage)
        self.assertFalse(result["ready_for_architecture_approval_checkpoint"]["architecture_approved"])

    def test_explicit_cli_current_gate_reports_models_with_warning(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(authority.main([str(self.root), "--require-models-entry"]), 0)
        cp = json.loads(output.getvalue())["checkpoint"]
        self.assertTrue(cp["architecture_approved"] and cp["approval_eligible"] and cp["transition_eligible"])
        self.assertEqual(cp["transition_decision"], "transitioned")
        self.assertEqual([w["code"] for w in cp["consistency_warnings"]], ["implementation_compatibility_not_proven"])
        self.assertFalse(cp["domain_model_generation_authorized"])

    def test_missing_current_area_and_every_file_cannot_downgrade(self):
        area = self.root / APPROVAL_AREA
        for name in MODELS_ENTRY_FILES:
            path = area / name
            original = path.read_bytes()
            path.unlink()
            try:
                for options in ({}, {"require_models_entry": True}):
                    with self.subTest(name=name, options=options), self.assertRaises(ValueError):
                        authority.validate_production_authority(self.root, **options)
            finally:
                path.write_bytes(original)
        self.remove_area(APPROVAL_AREA)
        for options in ({}, {"require_models_entry": True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                authority.validate_production_authority(self.root, **options)
        with patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit) as raised:
            authority.main([str(self.root), "--require-models-entry"])
        self.assertEqual(raised.exception.code, 1)

    def test_historical_seed_idea_plan_resolution_and_approval_modes_remain_usable(self):
        self.remove_area("production_architecture")
        cases = (
            ("require_plan_approval", "production_plan/plan_approval/checkpoint.json", "production_plan/plan_approval"),
            ("require_plan_resolution", "production_plan/plan_resolution/checkpoint.json", "production_plan/plan_resolution"),
            ("require_plan", "production_plan/checkpoint.json", "production_plan"),
            ("require_current", "idea_resolution/checkpoint.json", "idea_resolution"),
            ("seed_only", "checkpoint.json", None),
        )
        for option, relative, remove in cases:
            expected = json.loads((self.root / relative).read_bytes())
            with self.subTest(option=option):
                result = authority.validate_production_authority(self.root, **{option: True})
                self.assertEqual(result["checkpoint"], expected)
            if remove:
                self.remove_area(remove)

    def test_fake_domain_model_models_backend_and_application_authority_rejected(self):
        for parent in (self.root, self.root / "production_architecture", self.root / APPROVAL_AREA):
            for name in ("domain_model_specification.json", "approved_domain_model.json",
                    "models_backend_handoff.json", "backend.json", "frontend.json"):
                path = parent / name
                path.write_bytes(b"{}\n")
                try:
                    for options in ({}, {"require_models_entry": True}):
                        with self.subTest(parent=parent, name=name, options=options), self.assertRaises(ValueError):
                            authority.validate_production_authority(self.root, **options)
                finally:
                    path.unlink()

    def test_seed_and_current_gate_incompatible(self):
        with self.assertRaises(ValueError):
            authority.validate_production_authority(self.root, seed_only=True, require_models_entry=True)


if __name__ == "__main__":
    unittest.main()
