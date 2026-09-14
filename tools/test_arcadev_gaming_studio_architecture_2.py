"""Initial production architecture finalization, with no clarification authority."""

from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from arcadev.architecture_clarification import ArchitectureFinalization
from arcadev.architecture_engine import generate_baseline_architecture
from arcadev.architecture_specification import architecture_question_id
from arcadev.gaming_studio_architecture import ARCHITECTURE_AREA
from arcadev import gaming_studio_architecture_finalization as production
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes
from arcadev.gaming_studio_plan_approval import APPROVAL_AREA
from arcadev.plan_architecture_handoff import PlanArchitectureHandoff


class ProductionArchitectureFinalizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = PlanArchitectureHandoff.from_json(
            (AUTHORITY_DIRECTORY / APPROVAL_AREA / "plan_architecture_handoff.json").read_text(encoding="utf-8"))
        cls.architecture = generate_baseline_architecture(cls.handoff)
        cls.finalization = ArchitectureFinalization.start(cls.architecture, handoff=cls.handoff)

    def test_exact_public_initial_state_and_canonical_roundtrip(self):
        actual = production.validate_production_architecture_finalization()
        self.assertEqual(actual, self.finalization)
        self.assertEqual(ArchitectureFinalization.from_json(actual.canonical_json(), handoff=self.handoff), actual)

    def test_all_original_questions_and_ids_preserved(self):
        expected = {architecture_question_id(q): q for q in self.architecture.open_architecture_questions}
        actual = {architecture_question_id(q): q for q in self.finalization.unresolved_questions}
        self.assertEqual(actual, expected)
        self.assertEqual(list(actual), sorted(actual))
        self.assertFalse(self.finalization.decisions)
        self.assertFalse(self.finalization.history)
        self.assertFalse(self.finalization.conflicts)

    def test_review_is_exact_projection_of_public_readiness(self):
        review = production.architecture_clarification_review(self.handoff, self.finalization)
        self.assertEqual(review["architecture_id"], self.architecture.architecture_id)
        self.assertEqual(review["architecture_finalization_id"], self.finalization.finalization_id)
        self.assertEqual(review["handoff_id"], self.handoff.handoff_id)
        self.assertEqual(review["project_id"], self.architecture.project_id)
        self.assertEqual(review["unresolved_question_count"], len(self.finalization.unresolved_questions))
        self.assertEqual(review["conflict_count"], 0)
        self.assertIs(review["effective_ready_for_approval"], self.finalization.effective_ready_for_approval)
        self.assertFalse(review["effective_ready_for_approval"])
        self.assertEqual(review["status"], "BLOCKED_PENDING_ARCHITECTURE_CLARIFICATION")
        self.assertEqual(review["next_authorized_action"], "COLLECT_EXPLICIT_ARCHITECTURE_CLARIFICATIONS")
        self.assertEqual(review["current_stage"], "ARCHITECTURE")
        self.assertEqual(review["project_status"], "IN_PROGRESS")
        self.assertIs(review["architecture_approved"], False)
        self.assertIs(review["models_authorized"], False)

    def test_forged_finalization_missing_and_rewritten_questions_rejected_publicly(self):
        for change in (lambda v: v.update(finalization_id="forged"),
                       lambda v: v["unresolved_questions"].pop(),
                       lambda v: v["unresolved_questions"][0].update(question="Choose an invented implementation"),
                       lambda v: v.update(effective_ready_for_approval=True),
                       lambda v: v["decisions"].append({"accepted_values": ["invented"]}),
                       lambda v: v["history"].append({"answer": "fabricated"})):
            value = self.finalization.canonical_dict()
            change(value)
            with self.subTest(change=change), self.assertRaises(ValueError):
                ArchitectureFinalization.from_dict(value, handoff=self.handoff)

    def test_persisted_finalization_and_review_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "authority"
            shutil.copytree(AUTHORITY_DIRECTORY, root)
            # These unit mutations isolate child validation; the first test replays full history.
            with patch.object(production, "production_architecture_inputs", return_value=self.handoff):
                for name in production.FINALIZATION_FILES:
                    path = root / ARCHITECTURE_AREA / name
                    before = path.read_bytes()
                    for key, value in (("effective_ready_for_approval", True), ("fabricated_evidence", ["yes"])):
                        forged = json.loads(before)
                        forged[key] = value
                        path.write_bytes(canonical_bytes(forged))
                        with self.subTest(name=name, key=key), self.assertRaises(ValueError):
                            production.validate_production_architecture_finalization(root)
                    path.write_bytes(before)

    def test_start_contract_owns_initialization_without_answer_or_approval_calls(self):
        from arcadev.architecture_clarification import ArchitectureClarificationAnswer, ArchitectureDecision
        from arcadev.architecture_approval import ApprovedArchitecture
        from arcadev.architecture_models_handoff import ArchitectureModelsHandoff
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.object(production, "production_architecture_inputs", return_value=self.handoff))
            for owner in (ArchitectureClarificationAnswer, ArchitectureDecision, ApprovedArchitecture, ArchitectureModelsHandoff):
                stack.enter_context(patch.object(owner, "create", side_effect=AssertionError("later authority")))
            stack.enter_context(patch.object(ArchitectureFinalization, "resolve", side_effect=AssertionError("resolution")))
            start = stack.enter_context(patch.object(ArchitectureFinalization, "start", wraps=ArchitectureFinalization.start))
            _, actual = production.production_architecture_initial_state()
        start.assert_called_once()
        self.assertEqual(actual, self.finalization)


if __name__ == "__main__":
    unittest.main()
