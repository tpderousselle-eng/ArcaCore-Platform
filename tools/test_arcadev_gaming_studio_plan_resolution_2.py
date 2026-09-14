"""Deterministic production planning replay, bounded decisions and approval stop."""

from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, parse_authority
from arcadev.gaming_studio_plan import production_plan_inputs
from arcadev.gaming_studio_plan_resolution import ORDER, RESPONSES, VALUES, PLAN_ID
from arcadev.gaming_studio_plan_finalization import (
    replay_plan_authorization, plan_resolution_review, production_plan_resolution_state,
)
from arcadev.plan_clarification import PlanFinalization, PlanClarificationAnswer


class ProductionPlanFinalizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = AUTHORITY_DIRECTORY / "production_plan/plan_resolution"
        cls.data = (cls.area / "clarification_authorization.json").read_bytes()
        cls.handoff = production_plan_inputs()
        cls.finalization = replay_plan_authorization(cls.data)

    def test_persisted_state_and_deterministic_replay(self):
        state = production_plan_resolution_state()
        self.assertEqual(set(state), {"plan_finalization.json", "resolution_review.json"})
        for name, data in state.items():
            self.assertEqual(data, (self.area / name).read_bytes())
        self.assertEqual(state["plan_finalization.json"], self.finalization.canonical_json().encode())
        replayed = replay_plan_authorization(self.data)
        self.assertEqual(self.finalization.canonical_json(), replayed.canonical_json())

    def test_three_accepted_decisions_and_computed_readiness(self):
        result = self.finalization
        self.assertEqual(result.schema, "arcadev.plan_finalization")
        self.assertEqual(result.schema_version, 1)
        self.assertEqual(result.original_plan.plan_id, PLAN_ID)
        self.assertEqual(result.finalization_id, "arcadev_plan_final_d9698e456e67fae47ef46dbd11880dd2")
        self.assertEqual(len(result.decisions), 3)
        self.assertEqual(len(result.history), 3)
        self.assertEqual([entry.answer.target_question_id for entry in result.history], list(ORDER))
        self.assertEqual([entry.outcome.value for entry in result.history], ["accepted"] * 3)
        self.assertEqual([entry.readiness_before for entry in result.history], [False, False, False])
        self.assertEqual([entry.readiness_after for entry in result.history], [False, False, True])
        self.assertEqual([len(entry.unresolved_after) for entry in result.history], [2, 1, 0])
        self.assertFalse(result.unresolved_questions)
        self.assertFalse(result.conflicts)
        self.assertTrue(result.effective_ready_for_architecture)
        self.assertFalse(result.original_plan.readiness.ready_for_architecture)
        self.assertEqual(result.original_plan.canonical_json().encode(),
                         (AUTHORITY_DIRECTORY / "production_plan/software_plan.json").read_bytes())

    def test_public_roundtrip_rejects_history_decision_and_readiness_forgery(self):
        result = self.finalization
        self.assertEqual(result, PlanFinalization.from_json(result.canonical_json(), handoff=self.handoff))
        for change in (
            lambda v: v["history"][1]["answer"].update(target_finalization_id=v["history"][0]["answer"]["target_finalization_id"]),
            lambda v: v["history"][2].update(readiness_after=False),
            lambda v: v["decisions"][0]["accepted_values"].append("Unlimited marketplace storage"),
            lambda v: v.update(effective_ready_for_architecture=False),
            lambda v: v["history"].pop(),
        ):
            value = deepcopy(result.canonical_dict())
            change(value)
            with self.assertRaises(ValueError):
                PlanFinalization.from_dict(value, handoff=self.handoff)

    def test_storage_isolation_and_publishing_remain_exactly_bounded(self):
        for i, entry in enumerate(self.finalization.history):
            self.assertEqual(set(entry.accepted_values), set(VALUES[i]))
            self.assertEqual(entry.answer.user_answer, RESPONSES[i])
            self.assertEqual(entry.answer.provenance, "explicit_user")
            decision = next(d for d in self.finalization.decisions if d.question_id == ORDER[i])
            self.assertEqual(decision.idea_source_requirements, decision.source_question.source_requirements)
            self.assertEqual(set(decision.accepted_values), set(VALUES[i]))
        platforms = tuple(item.value for item in self.handoff.snapshot.intake.platform_targets)
        for target in ("PC", "Web", "Android", "iOS"):
            self.assertIn(f"Created games: {target}", platforms)
        text = self.finalization.canonical_json()
        for name in ("ArcaCreator Marketplace", "ArcaIP Guard", "Studio Transfer / Creator Exit", "Gaming Studio Mature Content Framework"):
            self.assertNotIn(name, text)
        self.assertIn("Consoles are outside initial scope", VALUES[2])

    def test_review_reports_ready_for_approval_without_granting_it(self):
        review = plan_resolution_review(self.finalization, handoff=self.handoff)
        self.assertEqual(review, parse_authority((self.area / "resolution_review.json").read_bytes()))
        self.assertEqual(review["accepted_decision_ids"], [e.resulting_decision_id for e in self.finalization.history])
        self.assertEqual(review["unresolved_question_count"], 0)
        self.assertEqual(review["conflict_count"], 0)
        self.assertTrue(review["effective_ready_for_architecture"])
        self.assertEqual(review["current_stage"], "PLAN")
        self.assertEqual(review["project_status"], "IN_PROGRESS")
        self.assertEqual(review["status"], "PLAN_READY_FOR_APPROVAL")
        self.assertEqual(review["next_authorized_action"], "REQUEST_EXPLICIT_PLAN_APPROVAL")
        self.assertFalse(review["complete_plan_approved"])
        self.assertFalse(review["architecture_authorized"])

    def test_actual_partial_and_conflicted_public_results_remain_blocked(self):
        initial = PlanFinalization.start(self.finalization.original_plan, handoff=self.handoff)
        partial = initial.resolve(self.finalization.history[0].answer, handoff=self.handoff)
        review = plan_resolution_review(partial, handoff=self.handoff)
        self.assertFalse(review["effective_ready_for_architecture"])
        self.assertEqual(review["unresolved_question_count"], 2)
        self.assertEqual(review["status"], "BLOCKED_PENDING_PLAN_CLARIFICATION")
        # A hostile candidate exercises the real frozen-IDEA conflict contract;
        # it is never added to the production authorization package.
        raw = self.finalization.history[1].answer.canonical_dict()
        raw["normalized_values"] = ["platform: consoles"]
        blocked = partial.resolve(PlanClarificationAnswer.from_dict(raw), handoff=self.handoff)
        review = plan_resolution_review(blocked, handoff=self.handoff)
        self.assertEqual(review["conflict_count"], 1)
        self.assertFalse(review["effective_ready_for_architecture"])
        self.assertEqual(review["status"], "BLOCKED_PENDING_PLAN_CONFLICT_RESOLUTION")
        self.assertNotEqual(review["next_authorized_action"], "REQUEST_EXPLICIT_PLAN_APPROVAL")

    def test_no_approval_handoff_execution_generation_or_strategy_dependency(self):
        from arcadev import ApprovedPlan, PlanArchitectureHandoff, architecture_engine, domain_model_engine, backend_generation
        from tools import generate
        original_read = Path.read_text
        def guarded_read(path, *args, **kwargs):
            if path.name == "GAMING_STUDIO_FUTURE_STRATEGY.md":
                raise AssertionError("Future strategy entered production authority")
            return original_read(path, *args, **kwargs)
        with ExitStack() as stack:
            for owner, name in (
                (ApprovedPlan, "create"), (PlanArchitectureHandoff, "create"),
                (architecture_engine, "generate_baseline_architecture"),
                (domain_model_engine, "generate_baseline_domain_model"),
                (backend_generation, "generate_backend"), (generate, "generate_module"),
                (socket, "socket"), (subprocess, "Popen"),
                (Path, "write_bytes"), (Path, "write_text"),
            ):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            stack.enter_context(patch.object(Path, "read_text", guarded_read))
            self.assertEqual(replay_plan_authorization(self.data), self.finalization)


if __name__ == "__main__":
    unittest.main()
