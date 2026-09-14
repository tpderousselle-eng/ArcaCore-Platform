"""Eight public resolutions, sequential lineage, and tamper-resistant resolved state."""

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from arcadev.architecture_clarification import ArchitectureClarificationAnswer, ArchitectureFinalization
from arcadev.gaming_studio_architecture_resolution import (
    ARCHITECTURE_ID, INITIAL_FINALIZATION_ID, ORDER, RESOLUTION_AREA, RESPONSES, VALUES,
)
from arcadev import gaming_studio_architecture_resolution_finalization as production
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes
from arcadev.plan_architecture_handoff import PlanArchitectureHandoff


class ArchitectureResolutionStateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = AUTHORITY_DIRECTORY / RESOLUTION_AREA
        cls.raw = (cls.area / "architecture_finalization.json").read_bytes()
        cls.state = json.loads(cls.raw)
        cls.review = json.loads((cls.area / "resolution_review.json").read_bytes())
        cls.authorization = json.loads((cls.area / "clarification_authorization.json").read_bytes())

    def test_complete_state_reconstructed_from_public_answers(self):
        actual = production.validate_architecture_resolution_state()
        self.assertEqual(actual["architecture_finalization.json"], self.raw)
        self.assertEqual(actual["resolution_review.json"], canonical_bytes(self.review))

    def test_eight_decisions_and_history_all_explicit_and_accepted(self):
        self.assertEqual(len(self.state["decisions"]), 8)
        self.assertEqual(len(self.state["history"]), 8)
        self.assertEqual([d["question_id"] for d in self.state["decisions"]], list(ORDER))
        for index, (decision, history) in enumerate(zip(self.state["decisions"], self.state["history"], strict=True)):
            self.assertEqual(decision["provenance"], "explicit_user")
            self.assertEqual(decision["user_answer"], RESPONSES[index])
            self.assertEqual(set(decision["accepted_values"]), set(VALUES[index]))
            self.assertEqual(decision["evidence"], [RESPONSES[index]])
            self.assertEqual(history["outcome"], "accepted")
            self.assertEqual(history["resulting_decision_id"], decision["decision_id"])
            self.assertEqual(history["rejected_values"], [])
            self.assertEqual(history["conflicts_after"], [])

    def test_exact_sequential_finalization_lineage(self):
        parent = INITIAL_FINALIZATION_ID
        for approval, history in zip(self.authorization["approvals"], self.state["history"], strict=True):
            self.assertEqual(history["answer"], approval["answer"])
            self.assertEqual(history["answer"]["target_finalization_id"], parent)
            parent = approval["resulting_finalization_id"]
        self.assertEqual(self.state["finalization_id"], parent)
        self.assertEqual(self.review["architecture_finalization_id"], parent)

    def test_unresolved_conflicts_and_ready_endpoint_never_grant_approval(self):
        self.assertEqual(self.state["unresolved_questions"], [])
        self.assertEqual(self.state["conflicts"], [])
        self.assertIs(self.state["effective_ready_for_approval"], True)
        for key, expected in {"accepted_decision_count": 8, "history_count": 8,
            "unresolved_question_count": 0, "conflict_count": 0, "effective_ready_for_approval": True,
            "status": "ARCHITECTURE_READY_FOR_APPROVAL", "current_stage": "ARCHITECTURE",
            "project_status": "IN_PROGRESS", "next_authorized_action": "REQUEST_EXPLICIT_ARCHITECTURE_APPROVAL",
            "architecture_approved": False, "models_authorized": False,
            "backend_authorized": False, "frontend_authorized": False}.items():
            self.assertEqual(self.review[key], expected, key)
        self.assertEqual(self.review["accepted_decision_ids"], [d["decision_id"] for d in self.state["decisions"]])
        names = {p.name for p in self.area.rglob("*")}
        self.assertFalse(names & {"approved_architecture.json", "architecture_models_handoff.json", "domain_model.json"})

    def test_source_architecture_and_plan_authority_unchanged(self):
        original = json.loads((AUTHORITY_DIRECTORY / "production_architecture/architecture_specification.json").read_bytes())
        self.assertEqual(self.state["original_architecture"], original)
        self.assertEqual(original["architecture_id"], ARCHITECTURE_ID)
        initial = json.loads((AUTHORITY_DIRECTORY / "production_architecture/architecture_finalization.json").read_bytes())
        self.assertEqual(initial["finalization_id"], INITIAL_FINALIZATION_ID)
        self.assertEqual(initial["decisions"], [])
        self.assertEqual(len(initial["unresolved_questions"]), 8)
        plan = json.loads((AUTHORITY_DIRECTORY / "production_plan/plan_approval/plan_architecture_handoff.json").read_bytes())
        self.assertEqual(original["handoff_id"], plan["handoff_id"])
        self.assertEqual(original["approved_plan_id"], plan["approved_plan_id"])

    def test_public_contract_rejects_stale_and_duplicate_answers(self):
        handoff = PlanArchitectureHandoff.from_json((AUTHORITY_DIRECTORY /
            "production_plan/plan_approval/plan_architecture_handoff.json").read_text(encoding="utf-8"))
        initial = ArchitectureFinalization.from_json((AUTHORITY_DIRECTORY /
            "production_architecture/architecture_finalization.json").read_text(encoding="utf-8"), handoff=handoff)
        answer = ArchitectureClarificationAnswer.from_dict(self.authorization["approvals"][0]["answer"])
        current = initial.resolve(answer, handoff=handoff)
        with self.assertRaisesRegex(ValueError, "stale"):
            current.resolve(answer, handoff=handoff)
        duplicate = answer.canonical_dict()
        duplicate["target_finalization_id"] = current.finalization_id
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            current.resolve(ArchitectureClarificationAnswer.from_dict(duplicate), handoff=handoff)

    def test_modified_decisions_values_evidence_and_lineage_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "authority"
            shutil.copytree(AUTHORITY_DIRECTORY, root)
            path = root / RESOLUTION_AREA / "architecture_finalization.json"
            for change in (
                lambda v: v["decisions"][0].update(decision_id="forged"),
                lambda v: v["decisions"][0].update(accepted_values=["AWS S3"]),
                lambda v: v["decisions"][0].update(evidence=["AWS S3"]),
                lambda v: v["decisions"].pop(),
                lambda v: v["decisions"].append(copy.deepcopy(v["decisions"][0])),
                lambda v: v["history"].reverse(),
                lambda v: v["history"][1]["answer"].update(target_finalization_id=INITIAL_FINALIZATION_ID),
                lambda v: v.update(effective_ready_for_approval=False),
            ):
                value = copy.deepcopy(self.state)
                change(value)
                path.write_bytes(canonical_bytes(value))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    production.validate_architecture_resolution_state(root)
            path.write_bytes(self.raw)
            review_path = root / RESOLUTION_AREA / "resolution_review.json"
            review = copy.deepcopy(self.review)
            review["architecture_approved"] = True
            review_path.write_bytes(canonical_bytes(review))
            with self.assertRaises(ValueError):
                production.validate_architecture_resolution_state(root)


if __name__ == "__main__":
    unittest.main()
