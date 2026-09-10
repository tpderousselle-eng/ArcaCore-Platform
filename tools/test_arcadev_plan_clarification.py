import json
import unittest

from arcadev import (
    BuildStage,
    PlanClarificationAnswer,
    PlanFinalization,
    PlanResolutionAction,
    PlanResolutionOutcome,
    create_idea_plan_handoff,
    generate_baseline_plan,
    planning_question_id,
    resolve_plan_clarification,
)
from tools.test_arcadev_idea_plan_handoff import finalized


class ArcaDevPlanClarificationTest(unittest.TestCase):
    def setup_flow(self):
        idea_finalization, idea_project = finalized()
        handoff = create_idea_plan_handoff(idea_project, idea_finalization)
        plan = generate_baseline_plan(handoff)
        return handoff, plan, PlanFinalization.start(plan, handoff=handoff)

    def question(self, state, contains):
        return next(item for item in state.original_plan.open_planning_questions if contains.casefold() in item.question.casefold())

    def answer(self, state, question, value, *, action=PlanResolutionAction.ANSWER, prior=()):
        return PlanClarificationAnswer.create(
            target_plan_id=state.original_plan.plan_id,
            target_finalization_id=state.finalization_id,
            target_question_id=planning_question_id(question),
            user_answer=value,
            normalized_values=[value],
            evidence=[value],
            action=action,
            expected_prior_values=prior,
        )

    def resolve_gaming(self):
        handoff, plan, state = self.setup_flow()
        fixtures = {
            "asset storage": "Use explicit per-project storage policy and deliberate deletion controls.",
            "build execution": "Use isolated build workers and environments.",
            "publishing targets": "Require user-controlled release targets and explicit release actions.",
            "repository synchronization": "Use user-authorized repository synchronization with explicit sync behavior.",
        }
        for fragment, value in fixtures.items():
            question = self.question(state, fragment)
            state = state.resolve(self.answer(state, question, value), handoff=handoff)
        return handoff, plan, state

    def test_one_resolution_only_changes_target_question(self):
        handoff, plan, state = self.setup_flow()
        question = self.question(state, "asset storage")
        before = {planning_question_id(item) for item in state.unresolved_questions}
        result = resolve_plan_clarification(state, self.answer(state, question, "Use per-project quotas."), handoff=handoff)
        after = {planning_question_id(item) for item in result.unresolved_questions}
        self.assertEqual(before - after, {planning_question_id(question)})
        self.assertEqual(len(result.decisions), 1)
        self.assertEqual(result.decisions[0].provenance, "explicit_user")
        self.assertEqual(result.history[0].outcome, PlanResolutionOutcome.ACCEPTED)
        self.assertFalse(result.effective_ready_for_architecture)

    def test_gaming_studio_complete_flow_and_effective_readiness(self):
        handoff, plan, state = self.resolve_gaming()
        self.assertFalse(plan.readiness.ready_for_architecture)
        self.assertTrue(state.effective_ready_for_architecture)
        self.assertEqual(state.unresolved_questions, ())
        self.assertEqual(state.conflicts, ())
        self.assertEqual(len(state.decisions), 4)
        self.assertEqual(len(state.history), 4)
        self.assertEqual(state.original_plan, plan)
        self.assertEqual(handoff.resulting_project.current_build_stage, BuildStage.PLAN)
        self.assertFalse(hasattr(state, "architecture"))

    def test_question_and_decision_identities_are_deterministic(self):
        handoff, _, state = self.setup_flow()
        question = self.question(state, "build execution")
        self.assertEqual(planning_question_id(question), planning_question_id(question))
        first = state.resolve(self.answer(state, question, "Use isolated workers."), handoff=handoff)
        _, _, second_state = self.setup_flow()
        second_question = self.question(second_state, "build execution")
        second = second_state.resolve(self.answer(second_state, second_question, "Use isolated workers."), handoff=handoff)
        self.assertEqual(first.decisions[0].decision_id, second.decisions[0].decision_id)

    def test_frozen_idea_and_base_plan_are_byte_equivalent(self):
        handoff, plan, state = self.resolve_gaming()
        self.assertEqual(state.original_plan.canonical_json(), plan.canonical_json())
        self.assertEqual(handoff.snapshot.finalization.canonical_json(), handoff.snapshot.finalization.canonical_json())

    def test_stale_replay_already_resolved_and_nonexistent_rejected(self):
        handoff, _, state = self.setup_flow()
        question = self.question(state, "build execution")
        answer = self.answer(state, question, "Use isolated workers.")
        resolved = state.resolve(answer, handoff=handoff)
        with self.assertRaisesRegex(ValueError, "stale"):
            resolved.resolve(answer, handoff=handoff)
        fresh = self.answer(resolved, question, "Use another worker pool.")
        with self.assertRaisesRegex(ValueError, "already resolved"):
            resolved.resolve(fresh, handoff=handoff)
        missing = fresh.canonical_dict()
        missing["target_question_id"] = "arcadev_question_" + "0" * 32
        with self.assertRaisesRegex(ValueError, "nonexistent"):
            resolved.resolve(PlanClarificationAnswer.from_dict(missing), handoff=handoff)

    def test_deliberate_decision_replacement_requires_exact_prior_value(self):
        handoff, _, state = self.setup_flow()
        question = self.question(state, "build execution")
        state = state.resolve(self.answer(state, question, "Use isolated workers."), handoff=handoff)
        replacement = self.answer(state, question, "Use isolated container workers.", action=PlanResolutionAction.REPLACE_DECISION, prior=["Use isolated workers."])
        result = state.resolve(replacement, handoff=handoff)
        self.assertEqual(result.decisions[0].accepted_values, ("Use isolated container workers.",))
        self.assertEqual(result.history[-1].previous_values, ("Use isolated workers.",))

    def test_conflict_with_frozen_idea_is_explicit_and_does_not_rewrite_it(self):
        handoff, plan, state = self.setup_flow()
        question = self.question(state, "build execution")
        result = state.resolve(self.answer(state, question, "platform=iOS only"), handoff=handoff)
        self.assertEqual(result.history[-1].outcome, PlanResolutionOutcome.CONFLICT)
        self.assertEqual(result.conflicts[0].code, "frozen_idea_conflict")
        self.assertIn(question, result.unresolved_questions)
        self.assertEqual(result.original_plan, plan)
        self.assertEqual([item.value for item in handoff.snapshot.intake.platform_targets], ["Desktop web", "Mobile web"])

    def test_conflict_with_accepted_decision_is_explicit(self):
        handoff, _, state = self.setup_flow()
        question = self.question(state, "build execution")
        state = state.resolve(self.answer(state, question, "Use isolated workers."), handoff=handoff)
        conflict = self.answer(state, question, "Use shared workers.", action=PlanResolutionAction.REPLACE_DECISION, prior=["Unexpected prior"])
        result = state.resolve(conflict, handoff=handoff)
        self.assertEqual(result.conflicts[0].code, "accepted_decision_conflict")
        self.assertFalse(result.effective_ready_for_architecture)
        self.assertEqual(result.decisions[0].accepted_values, ("Use isolated workers.",))

    def test_history_finalization_identity_and_round_trip_are_deterministic(self):
        handoff, _, state = self.resolve_gaming()
        rebuilt = PlanFinalization.from_json(state.canonical_json(), handoff=handoff)
        self.assertEqual(rebuilt, state)
        _, _, second = self.resolve_gaming()
        self.assertEqual(second.finalization_id, state.finalization_id)
        self.assertEqual(second.canonical_json(), state.canonical_json())

    def test_forged_readiness_history_and_identity_rejected(self):
        handoff, _, state = self.resolve_gaming()
        value = json.loads(state.canonical_json())
        value["effective_ready_for_architecture"] = False
        with self.assertRaisesRegex(ValueError, "forged"):
            PlanFinalization.from_dict(value, handoff=handoff)
        value = json.loads(state.canonical_json())
        value["history"][0]["accepted_values"] = ["forged"]
        with self.assertRaisesRegex(ValueError, "history is forged"):
            PlanFinalization.from_dict(value, handoff=handoff)
        value = json.loads(state.canonical_json())
        value["finalization_id"] = "arcadev_plan_final_" + "0" * 32
        with self.assertRaisesRegex(ValueError, "forged"):
            PlanFinalization.from_dict(value, handoff=handoff)

    def test_malformed_unknown_duplicate_schema_secret_and_oversize_rejected(self):
        handoff, _, state = self.setup_flow()
        question = self.question(state, "asset storage")
        answer = self.answer(state, question, "Use per-project quotas.")
        value = answer.canonical_dict()
        value["provider"] = "model"
        with self.assertRaisesRegex(ValueError, "shape"):
            PlanClarificationAnswer.from_dict(value)
        value = answer.canonical_dict()
        value["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported"):
            PlanClarificationAnswer.from_dict(value)
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            PlanClarificationAnswer.from_json('{"schema":"a","schema":"b"}')
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            PlanClarificationAnswer.from_json("{")
        for unsafe in ("api_key=real-secret-value", "bad\x00answer", "\ud800"):
            with self.subTest(unsafe=unsafe), self.assertRaisesRegex(ValueError, "secret|control|Unicode"):
                self.answer(state, question, unsafe)
        with self.assertRaisesRegex(ValueError, "safety limit"):
            PlanFinalization.from_json(" " * 5_000_001, handoff=handoff)
        with self.assertRaisesRegex(ValueError, "duplicate normalized"):
            PlanClarificationAnswer.create(target_plan_id=state.original_plan.plan_id, target_finalization_id=state.finalization_id,
                target_question_id=planning_question_id(question), user_answer="same same", normalized_values=["same", "Same"], evidence=["same"])

    def test_hostile_commands_remain_inert(self):
        handoff, _, state = self.setup_flow()
        question = self.question(state, "asset storage")
        payload = "Document rm -rf / and python payload.py as inert examples."
        result = state.resolve(self.answer(state, question, payload), handoff=handoff)
        self.assertIn("rm -rf /", result.decisions[0].accepted_values[0])


if __name__ == "__main__":
    unittest.main()
