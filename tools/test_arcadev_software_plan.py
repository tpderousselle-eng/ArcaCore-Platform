import json
import unittest

from arcadev import (
    ARCADEV_SOFTWARE_PLAN_SCHEMA,
    BuildStage,
    Milestone,
    PlanItem,
    PlanProvenance,
    PlanRisk,
    PlanScope,
    PlanningQuestion,
    SoftwarePlan,
    UserJourney,
    create_idea_plan_handoff,
    validate_software_plan_candidate,
)
from tools.test_arcadev_idea_plan_handoff import finalized


class ArcaDevSoftwarePlanTest(unittest.TestCase):
    def handoff(self):
        state, project = finalized()
        return create_idea_plan_handoff(project, state)

    def direct(self, handoff, value):
        return PlanItem.create(value, PlanProvenance.APPROVED_IDEA, [value], handoff=handoff)

    def derived(self, handoff, value, source="Manage game development projects"):
        return PlanItem.create(value, PlanProvenance.DERIVED, [source], handoff=handoff)

    def plan(self, *, handoff=None, questions=(), omit=None):
        handoff = handoff or self.handoff()
        feature_values = (
            "asset management", "build management", "game project management",
            "publishing workflow", "testing workflow",
        )
        capabilities = [self.direct(handoff, value) for value in feature_values]
        kwargs = {
            "handoff": handoff,
            "product_objective": self.derived(handoff, "Provide a workspace to manage game-development projects."),
            "user_problem_statement": self.derived(handoff, "Users need one workflow for game-development projects."),
            "scope": PlanScope.create(capabilities, [self.derived(handoff, "Architecture generation")], handoff=handoff),
            "in_scope_capabilities": capabilities,
            "user_roles": [self.direct(handoff, "users")],
            "user_journeys": [UserJourney.create("Game project lifecycle", [
                self.derived(handoff, "Create and manage a game project", "game project management"),
                self.derived(handoff, "Test and publish the project", "testing workflow"),
            ], handoff=handoff)],
            "functional_requirements": [self.derived(handoff, f"The product supports {value}.", value) for value in feature_values],
            "non_functional_requirements": [self.derived(handoff, "The experience supports desktop and mobile web.", "Desktop web")],
            "milestones": [Milestone.create("Core workflows", capabilities, handoff=handoff)],
            "dependencies": [self.derived(handoff, "GitHub connectivity", "GitHub")],
            "integrations": [self.direct(handoff, "GitHub")],
            "assumptions": [],
            "risks": [PlanRisk(
                self.derived(handoff, "Build workflow requirements may vary.", "build management"),
                self.derived(handoff, "Confirm build constraints before architecture.", "build management"),
            )],
            "open_planning_questions": list(questions),
            "acceptance_criteria": [self.derived(handoff, f"A user can complete {value}.", value) for value in feature_values],
            "planning_constraints": [
                self.direct(handoff, "Desktop web"), self.direct(handoff, "Mobile web"),
                self.direct(handoff, "ArcaCentum managed cloud"),
            ],
        }
        if omit:
            kwargs[omit] = []
        return SoftwarePlan.create(**kwargs)

    def test_valid_gaming_studio_plan_contract_and_readiness(self):
        plan = self.plan()
        self.assertTrue(plan.readiness.ready_for_architecture)
        self.assertEqual(plan.project_stage, BuildStage.PLAN)
        self.assertEqual(plan.schema, ARCADEV_SOFTWARE_PLAN_SCHEMA)
        self.assertIn("GitHub", [item.value for item in plan.integrations])
        self.assertFalse(hasattr(plan, "architecture"))

    def test_deterministic_identity_canonical_order_and_round_trip(self):
        first = self.plan()
        handoff = self.handoff()
        second = self.plan(handoff=handoff)
        self.assertEqual(first.plan_id, second.plan_id)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(SoftwarePlan.from_json(first.canonical_json(), handoff=handoff), first)

    def test_objective_scope_workflow_requirements_milestones_and_risks(self):
        plan = self.plan()
        self.assertIn("workspace", plan.product_objective.value)
        self.assertEqual(len(plan.scope.in_scope), 5)
        self.assertEqual(plan.user_journeys[0].name, "Game project lifecycle")
        self.assertEqual(len(plan.functional_requirements), 5)
        self.assertEqual(len(plan.non_functional_requirements), 1)
        self.assertEqual(plan.milestones[0].name, "Core workflows")
        self.assertTrue(plan.dependencies and plan.risks and plan.acceptance_criteria)

    def test_missing_required_sections_and_blocking_question_make_not_ready(self):
        for field in ("in_scope_capabilities", "user_journeys", "functional_requirements", "non_functional_requirements", "milestones", "dependencies", "risks", "acceptance_criteria"):
            with self.subTest(field=field):
                plan = self.plan(omit=field)
                self.assertFalse(plan.readiness.ready_for_architecture)
                expected = {
                    "in_scope_capabilities": "required_capabilities",
                    "user_journeys": "core_workflows",
                }.get(field, field)
                self.assertIn(expected, plan.readiness.blocking_reasons)
        handoff = self.handoff()
        question = PlanningQuestion.create("Which build execution environment is required?", True, ["build management"], handoff=handoff)
        plan = self.plan(handoff=handoff, questions=[question])
        self.assertFalse(plan.readiness.ready_for_architecture)
        self.assertIn("blocking_planning_questions", plan.readiness.blocking_reasons)

    def test_forged_identity_readiness_and_wrong_binding_rejected(self):
        handoff = self.handoff()
        plan = self.plan(handoff=handoff)
        value = plan.canonical_dict()
        value["plan_id"] = "arcadev_plan_" + "0" * 32
        with self.assertRaisesRegex(ValueError, "identity is forged"):
            SoftwarePlan.from_dict(value, handoff=handoff)
        value = plan.canonical_dict()
        value["readiness"]["ready_for_architecture"] = False
        with self.assertRaisesRegex(ValueError, "readiness is forged"):
            SoftwarePlan.from_dict(value, handoff=handoff)
        other = create_idea_plan_handoff(*reversed(finalized(project_type="mobile_application", platforms=("iOS",))))
        with self.assertRaisesRegex(ValueError, "wrong approved"):
            SoftwarePlan.from_dict(plan.canonical_dict(), handoff=other)

    def test_duplicate_scope_and_scope_contradiction_rejected(self):
        handoff = self.handoff()
        item = self.direct(handoff, "asset management")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            PlanScope.create([item, item], [], handoff=handoff)
        with self.assertRaisesRegex(ValueError, "in-scope and out-of-scope"):
            PlanScope.create([item], [item], handoff=handoff)

    def test_unknown_malformed_duplicate_keys_schema_secret_control_and_oversize(self):
        handoff = self.handoff()
        plan = self.plan(handoff=handoff)
        value = plan.canonical_dict()
        value["provider"] = "model"
        with self.assertRaisesRegex(ValueError, "shape"):
            SoftwarePlan.from_dict(value, handoff=handoff)
        value = plan.canonical_dict()
        value["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported"):
            SoftwarePlan.from_dict(value, handoff=handoff)
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            SoftwarePlan.from_json('{"schema":"a","schema":"b"}', handoff=handoff)
        for value in ("api_key=live-secret-value", "bad\x00value", "\ud800"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "secret|control|Unicode|invalid"):
                self.derived(handoff, value)
        with self.assertRaisesRegex(ValueError, "safety limit"):
            SoftwarePlan.from_json(" " * 5_000_001, handoff=handoff)

    def test_commands_are_inert_and_approved_sources_are_mandatory(self):
        handoff = self.handoff()
        item = self.derived(handoff, "Document rm -rf / and python payload.py as examples.")
        self.assertIn("rm -rf /", item.value)
        with self.assertRaisesRegex(ValueError, "not present"):
            PlanItem.create("Invent billing", PlanProvenance.DERIVED, ["billing"], handoff=handoff)


if __name__ == "__main__":
    unittest.main()
