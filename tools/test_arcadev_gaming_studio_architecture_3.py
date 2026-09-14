"""An inert deterministic request cannot act as architecture clarification authority."""

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from arcadev.architecture_clarification import (
    ArchitectureClarificationAnswer, ArchitectureFinalization, resolve_architecture_clarification,
)
from arcadev.architecture_specification import architecture_question_id
from arcadev.gaming_studio_architecture import ARCHITECTURE_AREA
from arcadev import gaming_studio_architecture_request as production
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes
from arcadev.gaming_studio_plan_approval import APPROVAL_AREA
from arcadev.plan_architecture_handoff import PlanArchitectureHandoff


class ProductionArchitectureRequestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = PlanArchitectureHandoff.from_json(
            (AUTHORITY_DIRECTORY / APPROVAL_AREA / "plan_architecture_handoff.json").read_text(encoding="utf-8"))
        cls.finalization = ArchitectureFinalization.from_json(
            (AUTHORITY_DIRECTORY / ARCHITECTURE_AREA / "architecture_finalization.json").read_text(encoding="utf-8"),
            handoff=cls.handoff)
        cls.request = production.architecture_clarification_request(cls.finalization)

    def test_full_production_request_validation(self):
        self.assertEqual(production.validate_production_architecture_request(), self.request)

    def test_exact_ordered_question_ids_text_areas_and_source_lineage(self):
        questions = sorted(self.finalization.unresolved_questions, key=architecture_question_id)
        self.assertEqual(self.request["question_count"], len(questions))
        self.assertEqual(self.request["project_id"], self.finalization.original_architecture.project_id)
        for ordinal, (question, entry) in enumerate(zip(questions, self.request["questions"], strict=True), 1):
            self.assertEqual(entry, {
                "ordinal": ordinal, "architecture_question_id": architecture_question_id(question),
                "question": question.question, "blocking": question.blocking, "area": question.area.value,
                "source_requirements": list(question.source_requirements),
                "architecture_id": self.finalization.original_architecture.architecture_id,
                "architecture_finalization_id": self.finalization.finalization_id,
            })

    def test_inert_exact_shape_has_no_answers_recommendations_or_decisions(self):
        self.assertEqual(set(self.request), {"schema", "schema_version", "product_key", "project_id",
            "question_count", "questions", "authority", "answers_present", "requires_explicit_user"})
        self.assertIs(self.request["authority"], False)
        self.assertIs(self.request["answers_present"], False)
        self.assertIs(self.request["requires_explicit_user"], True)
        forbidden = {"user_answer", "answers", "normalized_values", "evidence", "recommended_values",
                     "accepted_values", "decisions", "ArchitectureDecision"}
        for entry in [self.request, *self.request["questions"]]:
            self.assertFalse(set(entry) & forbidden)

    def test_request_and_individual_questions_cannot_be_public_answers_or_resolve(self):
        before = self.finalization.canonical_json()
        for value in (self.request, *self.request["questions"]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ArchitectureClarificationAnswer.from_dict(value)
            with self.assertRaises(ValueError):
                resolve_architecture_clarification(self.finalization, value, handoff=self.handoff)
        with self.assertRaises(ValueError):
            resolve_architecture_clarification(self.finalization, canonical_bytes(self.request).decode(), handoff=self.handoff)
        with self.assertRaises(ValueError):
            self.finalization.resolve(self.request, handoff=self.handoff)
        self.assertEqual(self.finalization.canonical_json(), before)

    def test_changed_text_ids_areas_sources_flags_and_order_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            area = root / ARCHITECTURE_AREA
            area.mkdir()
            path = area / "clarification_request.json"
            with patch.object(production, "validate_production_architecture_finalization", return_value=self.finalization):
                for change in (
                    lambda v: v["questions"][0].update(question="Rewritten question"),
                    lambda v: v["questions"][0].update(architecture_question_id="forged"),
                    lambda v: v["questions"][0].update(area="invented_area"),
                    lambda v: v["questions"][0].update(source_requirements=["invented"]),
                    lambda v: v["questions"].reverse(), lambda v: v["questions"].pop(),
                    lambda v: v.update(authority=True), lambda v: v.update(answers_present=True),
                    lambda v: v.update(requires_explicit_user=False),
                    lambda v: v["questions"][0].update(accepted_values=["invented"]),
                    lambda v: v["questions"][0].update(recommended_values=["invented"]),
                ):
                    value = copy.deepcopy(self.request)
                    change(value)
                    path.write_bytes(canonical_bytes(value))
                    with self.subTest(change=change), self.assertRaises(ValueError):
                        production.validate_production_architecture_request(root)

    def test_deterministic_canonical_bytes(self):
        again = production.architecture_clarification_request(self.finalization)
        self.assertEqual(canonical_bytes(again), canonical_bytes(self.request))
        self.assertEqual(json.loads(canonical_bytes(again)), self.request)


if __name__ == "__main__":
    unittest.main()
