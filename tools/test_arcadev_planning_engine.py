import unittest

from arcadev import (
    BuildStage,
    PlanItem,
    PlanProvenance,
    PlanScope,
    SoftwarePlan,
    create_idea_plan_handoff,
    generate_baseline_plan,
    validate_adapter_candidate,
    validate_plan_candidate,
)
from tools.test_arcadev_idea_plan_handoff import finalized


class CandidateAdapter:
    def __init__(self, candidate):
        self.candidate = candidate

    def create_candidate(self, handoff):
        return self.candidate


class ArcaDevPlanningEngineTest(unittest.TestCase):
    def handoff(self):
        state, project = finalized()
        return create_idea_plan_handoff(project, state)

    def test_deterministic_gaming_studio_plan_generation(self):
        handoff = self.handoff()
        first = generate_baseline_plan(handoff)
        second = generate_baseline_plan(handoff)
        self.assertEqual(first.plan_id, second.plan_id)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        capabilities = {item.value for item in first.in_scope_capabilities}
        self.assertTrue({"game project management", "asset management", "build management", "testing workflow", "publishing workflow", "Authentication", "GitHub integration"} <= capabilities)

    def test_feature_requirements_milestones_dependencies_and_acceptance(self):
        plan = generate_baseline_plan(self.handoff())
        requirements = " ".join(item.value for item in plan.functional_requirements)
        self.assertIn("asset management", requirements)
        self.assertIn("build management", requirements)
        self.assertIn("testing workflow", requirements)
        self.assertTrue(plan.milestones)
        self.assertEqual([item.value for item in plan.integrations], ["GitHub"])
        self.assertIn("GitHub", plan.dependencies[0].value)
        self.assertGreaterEqual(len(plan.acceptance_criteria), 7)

    def test_preserves_platform_authentication_deployment_and_integration(self):
        plan = generate_baseline_plan(self.handoff())
        constraints = {item.value for item in plan.planning_constraints}
        self.assertTrue({"Desktop web", "Mobile web", "Email/password", "Google OAuth", "ArcaCentum managed cloud"} <= constraints)
        self.assertEqual([item.value for item in plan.integrations], ["GitHub"])

    def test_planning_questions_are_genuine_and_do_not_reopen_idea(self):
        plan = generate_baseline_plan(self.handoff())
        questions = " ".join(item.question for item in plan.open_planning_questions)
        self.assertIn("build execution", questions)
        self.assertIn("asset storage", questions)
        self.assertIn("publishing targets", questions)
        self.assertIn("repository synchronization", questions)
        for resolved in ("project name", "project type", "authentication method", "platform target", "deployment target"):
            self.assertNotIn(resolved, questions.casefold())
        self.assertFalse(plan.readiness.ready_for_architecture)

    def test_exact_handoff_binding_project_stays_plan_and_no_generation_boundary_crossing(self):
        handoff = self.handoff()
        plan = generate_baseline_plan(handoff)
        self.assertEqual(plan.handoff_id, handoff.handoff_id)
        self.assertEqual(plan.project_id, handoff.source_project_id)
        self.assertEqual(plan.project_stage, BuildStage.PLAN)
        self.assertFalse(hasattr(plan, "architecture"))
        self.assertFalse(hasattr(plan, "backend"))
        self.assertFalse(hasattr(plan, "frontend"))

    def test_candidate_and_model_style_adapter_validation(self):
        handoff = self.handoff()
        plan = generate_baseline_plan(handoff)
        self.assertEqual(validate_plan_candidate(handoff, plan.canonical_dict()), plan)
        self.assertEqual(validate_plan_candidate(handoff, plan.canonical_json()), plan)
        self.assertEqual(validate_adapter_candidate(handoff, CandidateAdapter(plan.canonical_dict())), plan)

    def test_candidate_unknown_duplicate_forged_identity_and_readiness_rejected(self):
        handoff = self.handoff()
        plan = generate_baseline_plan(handoff)
        value = plan.canonical_dict()
        value["provider"] = "untrusted-model"
        with self.assertRaisesRegex(ValueError, "shape"):
            validate_plan_candidate(handoff, value)
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            validate_plan_candidate(handoff, '{"schema":"a","schema":"b"}')
        value = plan.canonical_dict()
        value["plan_id"] = "arcadev_plan_" + "0" * 32
        with self.assertRaisesRegex(ValueError, "identity is forged"):
            validate_plan_candidate(handoff, value)
        value = plan.canonical_dict()
        value["readiness"]["ready_for_architecture"] = True
        with self.assertRaisesRegex(ValueError, "readiness is forged"):
            validate_plan_candidate(handoff, value)

    def test_wrong_handoff_and_oversized_or_secret_candidate_rejected(self):
        handoff = self.handoff()
        plan = generate_baseline_plan(handoff)
        other_state, other_project = finalized(project_type="mobile_application", platforms=("iOS",))
        other = create_idea_plan_handoff(other_project, other_state)
        with self.assertRaisesRegex(ValueError, "wrong approved"):
            validate_plan_candidate(other, plan.canonical_dict())
        with self.assertRaisesRegex(ValueError, "safety limit"):
            validate_plan_candidate(handoff, " " * 5_000_001)
        value = plan.canonical_dict()
        value["product_objective"]["value"] = "api_key=untrusted-secret-value"
        with self.assertRaisesRegex(ValueError, "secret"):
            validate_plan_candidate(handoff, value)

    def test_unsupported_invented_scope_is_rejected(self):
        handoff = self.handoff()
        plan = generate_baseline_plan(handoff)
        invented = PlanItem.create("Billing", PlanProvenance.DERIVED, ["GitHub"], handoff=handoff)
        value = plan.canonical_dict()
        value["scope"]["in_scope"].append(invented.canonical_dict())
        value["in_scope_capabilities"].append(invented.canonical_dict())
        # Rebuild a structurally valid, self-consistent candidate before grounding validation.
        base = SoftwarePlan.from_dict(plan.canonical_dict(), handoff=handoff)
        kwargs = {name: getattr(base, name) for name in (
            "product_objective", "user_problem_statement", "user_roles", "user_journeys", "functional_requirements",
            "non_functional_requirements", "milestones", "dependencies", "integrations", "assumptions", "risks",
            "open_planning_questions", "acceptance_criteria", "planning_constraints",
        )}
        candidate = SoftwarePlan.create(
            handoff=handoff,
            scope=PlanScope.create((*base.scope.in_scope, invented), base.scope.out_of_scope, handoff=handoff),
            in_scope_capabilities=(*base.in_scope_capabilities, invented),
            **kwargs,
        )
        with self.assertRaisesRegex(ValueError, "unsupported invented scope"):
            validate_plan_candidate(handoff, candidate)

    def test_hostile_commands_remain_inert_and_round_trip(self):
        handoff = self.handoff()
        plan = generate_baseline_plan(handoff)
        item = PlanItem.create("Document rm -rf / and python payload.py in documentation.", PlanProvenance.DERIVED, ["testing workflow"], handoff=handoff)
        self.assertIn("rm -rf /", item.value)
        self.assertEqual(SoftwarePlan.from_json(plan.canonical_json(), handoff=handoff), plan)


if __name__ == "__main__":
    unittest.main()
