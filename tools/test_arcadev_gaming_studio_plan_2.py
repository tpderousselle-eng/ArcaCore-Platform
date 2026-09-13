"""Exact unanswered review and isolated, non-authoritative future strategy."""

from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, parse_authority
from arcadev.gaming_studio_plan import (
    production_plan_inputs, production_planning_review, production_software_plan,
    validate_production_plan_package,
)
from arcadev.plan_clarification import planning_question_id


class ProductionPlanningReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = production_plan_inputs()
        cls.plan = production_software_plan()
        cls.review = production_planning_review(cls.plan, handoff=cls.handoff)

    def test_exact_reconstruction_question_identity_text_and_sources(self):
        self.assertEqual(canonical_bytes(self.review),
                         (AUTHORITY_DIRECTORY / "production_plan/planning_review.json").read_bytes())
        self.assertEqual(self.review, production_planning_review(self.plan, handoff=self.handoff))
        self.assertEqual(self.review["plan_id"], self.plan.plan_id)
        self.assertEqual(self.review["handoff_id"], self.handoff.handoff_id)
        self.assertEqual(self.review["project_id"], self.plan.project_id)
        for row, question in zip(self.review["questions"], self.plan.open_planning_questions, strict=True):
            self.assertEqual(row["question_id"], planning_question_id(question))
            for key, value in question.canonical_dict().items():
                self.assertEqual(row[key], value)
            self.assertTrue(row["why_unresolved"])
            self.assertIsNone(row["current_accepted_planning_decision"])

    def test_readiness_classification_and_status_are_exact(self):
        self.assertEqual(self.review["ready_for_architecture"], self.plan.readiness.ready_for_architecture)
        self.assertEqual(self.review["blocking_reasons"], list(self.plan.readiness.blocking_reasons))
        for blocking, key in ((True, "blocking_question_ids"), (False, "non_blocking_question_ids")):
            self.assertEqual(self.review[key], [planning_question_id(q) for q in self.plan.open_planning_questions if q.blocking is blocking])
        self.assertEqual(self.review["assumption_count"], 0)
        self.assertEqual(self.review["unresolved_question_count"], 3)
        self.assertEqual(self.review["current_stage"], "PLAN")
        self.assertEqual(self.review["status"], "BLOCKED_PENDING_PLAN_CLARIFICATION")
        self.assertEqual(self.review["next_authorized_action"], "COLLECT_EXPLICIT_PLAN_CLARIFICATIONS")

    def test_answer_and_question_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "authority"
            shutil.copytree(AUTHORITY_DIRECTORY, root)
            path = root / "production_plan/planning_review.json"
            for field, value in (("question_id", "fake"), ("question", "Rewritten?"),
                                 ("blocking", False), ("source_requirements", []),
                                 ("current_accepted_planning_decision", "invented answer")):
                with self.subTest(field=field):
                    candidate = deepcopy(self.review)
                    candidate["questions"][0][field] = value
                    path.write_bytes(canonical_bytes(candidate))
                    with self.assertRaises(ValueError):
                        validate_production_plan_package(root)

    def test_future_strategy_is_documentation_only_and_cannot_affect_plan(self):
        note = Path(__file__).resolve().parents[1] / "docs/GAMING_STUDIO_FUTURE_STRATEGY.md"
        text = note.read_text(encoding="utf-8")
        self.assertIn("FUTURE STRATEGIC EXPANSION — NOT CURRENT PLAN AUTHORITY", text)
        for name in ("ArcaCreator Marketplace", "ArcaIP Guard", "Studio Transfer / Creator Exit", "Gaming Studio Mature Content Framework"):
            self.assertIn(name, text)
            self.assertNotIn(name, self.plan.canonical_json())
        # A changed external strategy document must never be read as authority.
        original_read = Path.read_text
        def guarded_read(path, *args, **kwargs):
            if path.resolve() == note.resolve():
                raise AssertionError("strategy entered authority")
            return original_read(path, *args, **kwargs)
        with patch.object(Path, "read_text", guarded_read):
            self.assertEqual(self.plan.canonical_json(), production_software_plan().canonical_json())

    def test_review_does_not_create_decisions_finalization_or_approval(self):
        from arcadev import PlanClarificationAnswer, PlanningDecision, PlanFinalization, ApprovedPlan, PlanArchitectureHandoff
        with ExitStack() as stack:
            for owner, method in ((PlanClarificationAnswer, "create"), (PlanningDecision, "create"),
                                  (PlanFinalization, "start"), (ApprovedPlan, "create"),
                                  (PlanArchitectureHandoff, "create")):
                stack.enter_context(patch.object(owner, method, side_effect=AssertionError(method)))
            self.assertEqual(self.review, production_planning_review(self.plan, handoff=self.handoff))


if __name__ == "__main__":
    unittest.main()
