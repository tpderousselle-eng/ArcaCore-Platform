import json
import unittest

from arcadev import (
    ApprovalDecision,
    ApprovedPlan,
    BuildStage,
    PlanClarificationAnswer,
    PlanFinalization,
    PlanScope,
    SoftwarePlan,
    approve_plan,
    create_idea_plan_handoff,
    evaluate_plan_consistency,
    generate_baseline_plan,
    planning_question_id,
    reject_plan,
)
from tools.test_arcadev_idea_plan_handoff import finalized


class ArcaDevPlanApprovalTest(unittest.TestCase):
    def setup_flow(self):
        idea, project = finalized()
        handoff = create_idea_plan_handoff(project, idea)
        plan = generate_baseline_plan(handoff)
        return handoff, plan

    def resolve(self, handoff, plan):
        state = PlanFinalization.start(plan, handoff=handoff)
        decisions = {
            "asset storage": "Use explicit per-project storage policy and deliberate deletion controls.",
            "build execution": "Use isolated build workers and environments.",
            "publishing targets": "Require user-controlled release targets and explicit release actions.",
            "repository synchronization": "Use user-authorized repository synchronization with explicit sync behavior.",
        }
        for question in plan.open_planning_questions:
            value = next(value for fragment, value in decisions.items() if fragment in question.question.casefold())
            answer = PlanClarificationAnswer.create(target_plan_id=plan.plan_id, target_finalization_id=state.finalization_id,
                target_question_id=planning_question_id(question), user_answer=value, normalized_values=[value], evidence=[value])
            state = state.resolve(answer, handoff=handoff)
        return state

    def complete(self):
        handoff, plan = self.setup_flow()
        return handoff, plan, self.resolve(handoff, plan)

    def altered(self, handoff, plan, **changes):
        values = {field: getattr(plan, field) for field in (
            "product_objective", "user_problem_statement", "scope", "in_scope_capabilities", "user_roles", "user_journeys",
            "functional_requirements", "non_functional_requirements", "milestones", "dependencies", "integrations", "assumptions",
            "risks", "open_planning_questions", "acceptance_criteria", "planning_constraints",
        )}
        values.update(changes)
        return SoftwarePlan.create(handoff=handoff, **values)

    def test_valid_explicit_gaming_studio_approval(self):
        handoff, plan, finalization = self.complete()
        approved = approve_plan(handoff=handoff, finalization=finalization, approval_statement="I explicitly approve this Gaming Studio plan.")
        self.assertTrue(finalization.effective_ready_for_architecture)
        self.assertTrue(approved.package.consistency.consistent)
        self.assertTrue(approved.approval_eligible)
        self.assertTrue(approved.approved)
        self.assertEqual(approved.decision, ApprovalDecision.APPROVED)
        self.assertEqual(approved.package.plan_finalization.original_plan, plan)
        self.assertEqual(handoff.resulting_project.current_build_stage, BuildStage.PLAN)
        self.assertFalse(hasattr(approved, "architecture"))

    def test_explicit_statement_required_and_rejection_preserves_state(self):
        handoff, plan, finalization = self.complete()
        with self.assertRaisesRegex(ValueError, "empty"):
            approve_plan(handoff=handoff, finalization=finalization, approval_statement=" ")
        rejected = reject_plan(handoff=handoff, finalization=finalization, approval_statement="I do not approve this plan yet.")
        self.assertFalse(rejected.approved)
        self.assertEqual(rejected.decision, ApprovalDecision.REJECTED)
        self.assertEqual(rejected.package.plan_finalization, finalization)
        self.assertEqual(rejected.package.plan_finalization.original_plan, plan)

    def test_deterministic_identity_frozen_package_and_round_trip(self):
        handoff, plan, finalization = self.complete()
        first = approve_plan(handoff=handoff, finalization=finalization, approval_statement="Approved for architecture preparation.")
        second = approve_plan(handoff=handoff, finalization=finalization, approval_statement="Approved for architecture preparation.")
        self.assertEqual(first.approval_id, second.approval_id)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(ApprovedPlan.from_json(first.canonical_json()), first)
        self.assertEqual(first.package.plan_finalization.original_plan.canonical_json(), plan.canonical_json())

    def test_readiness_unresolved_questions_and_conflicts_block_approval(self):
        handoff, plan = self.setup_flow()
        initial = PlanFinalization.start(plan, handoff=handoff)
        with self.assertRaisesRegex(ValueError, "cannot be approved"):
            approve_plan(handoff=handoff, finalization=initial, approval_statement="Approve despite blockers.")
        question = initial.unresolved_questions[0]
        conflict_value = "platform=iOS only"
        answer = PlanClarificationAnswer.create(target_plan_id=plan.plan_id, target_finalization_id=initial.finalization_id,
            target_question_id=planning_question_id(question), user_answer=conflict_value, normalized_values=[conflict_value], evidence=[conflict_value])
        conflicted = initial.resolve(answer, handoff=handoff)
        with self.assertRaisesRegex(ValueError, "cannot be approved"):
            approve_plan(handoff=handoff, finalization=conflicted, approval_statement="Approve despite conflict.")

    def test_consistency_checks_scope_integration_auth_platform_and_deployment(self):
        handoff, plan = self.setup_flow()
        cases = {}
        cases["scope_capability_mismatch"] = self.altered(handoff, plan, scope=PlanScope.create(plan.scope.in_scope[:-1], plan.scope.out_of_scope, handoff=handoff))
        cases["integration_consistency"] = self.altered(handoff, plan, integrations=())
        for code, removed in (
            ("authentication_consistency", "Email/password"),
            ("platform_consistency", "Desktop web"),
            ("deployment_consistency", "ArcaCentum managed cloud"),
        ):
            cases[code] = self.altered(handoff, plan, planning_constraints=tuple(item for item in plan.planning_constraints if item.value != removed))
        for code, candidate in cases.items():
            with self.subTest(code=code):
                finalization = self.resolve(handoff, candidate)
                evaluation = evaluate_plan_consistency(handoff, finalization)
                self.assertFalse(evaluation.consistent)
                self.assertIn(code, [item.code for item in evaluation.blocking_findings])
                with self.assertRaisesRegex(ValueError, "cannot be approved"):
                    approve_plan(handoff=handoff, finalization=finalization, approval_statement="Approve inconsistent plan.")

    def test_unknown_decision_semantics_are_warning_not_blocker(self):
        handoff, _, finalization = self.complete()
        evaluation = evaluate_plan_consistency(handoff, finalization)
        self.assertTrue(evaluation.consistent)
        self.assertIn("decision_semantics_not_machine_classified", [item.code for item in evaluation.warnings])

    def test_identity_binding_and_tampered_frozen_state_rejected(self):
        handoff, _, finalization = self.complete()
        approved = approve_plan(handoff=handoff, finalization=finalization, approval_statement="Approved.")
        mutations = (
            ("source_project_id", "arcadev_" + "0" * 32),
            ("idea_handoff_id", "arcadev_handoff_" + "0" * 32),
            ("software_plan_id", "arcadev_plan_" + "0" * 32),
            ("plan_finalization_id", "arcadev_plan_final_" + "0" * 32),
            ("approval_id", "arcadev_approved_plan_" + "0" * 32),
        )
        for field, replacement in mutations:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "forged"):
                value = approved.canonical_dict()
                value[field] = replacement
                ApprovedPlan.from_dict(value)
        value = approved.canonical_dict()
        value["package"]["plan_finalization"]["effective_ready_for_architecture"] = False
        with self.assertRaisesRegex(ValueError, "forged"):
            ApprovedPlan.from_dict(value)

    def test_forged_eligibility_decision_and_result_rejected(self):
        handoff, _, finalization = self.complete()
        approved = approve_plan(handoff=handoff, finalization=finalization, approval_statement="Approved.")
        for field, replacement in (("approval_eligible", False), ("approved", False), ("decision", "rejected")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "forged"):
                value = approved.canonical_dict()
                value[field] = replacement
                ApprovedPlan.from_dict(value)

    def test_unknown_duplicate_malformed_schema_oversize_and_secret_rejected(self):
        handoff, _, finalization = self.complete()
        approved = approve_plan(handoff=handoff, finalization=finalization, approval_statement="Approved.")
        value = approved.canonical_dict()
        value["provider"] = "model"
        with self.assertRaisesRegex(ValueError, "shape"):
            ApprovedPlan.from_dict(value)
        value = approved.canonical_dict()
        value["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported"):
            ApprovedPlan.from_dict(value)
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            ApprovedPlan.from_json('{"schema":"a","schema":"b"}')
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            ApprovedPlan.from_json("{")
        with self.assertRaisesRegex(ValueError, "safety limit"):
            ApprovedPlan.from_json(" " * 10_000_001)
        with self.assertRaisesRegex(ValueError, "secret"):
            approve_plan(handoff=handoff, finalization=finalization, approval_statement="api_key=real-secret-value")


if __name__ == "__main__":
    unittest.main()
