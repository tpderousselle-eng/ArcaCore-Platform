import json
from dataclasses import replace
import unittest

from arcadev import (
    ArchitectureTransitionDecision,
    BuildStage,
    PlanArchitectureHandoff,
    ProjectStatus,
    approve_plan,
    create_plan_architecture_handoff,
    reject_plan,
    validate_plan_architecture_handoff,
)
from tools import test_arcadev_plan_approval as approval_helpers


class ArcaDevPlanArchitectureHandoffTest(unittest.TestCase):
    def approved(self, statement="I explicitly approve the Gaming Studio plan."):
        helper = approval_helpers.ArcaDevPlanApprovalTest()
        handoff, plan, finalization = helper.complete()
        approved = approve_plan(handoff=handoff, finalization=finalization, approval_statement=statement)
        return handoff.resulting_project, approved

    def test_valid_gaming_studio_transition(self):
        source, approved = self.approved()
        handoff = create_plan_architecture_handoff(source_project=source, approved_plan=approved)
        self.assertTrue(handoff.transition_eligible)
        self.assertEqual(handoff.decision, ArchitectureTransitionDecision.TRANSITIONED)
        self.assertEqual(handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        self.assertEqual(handoff.resulting_project.current_build_stage, BuildStage.ARCHITECTURE)
        self.assertEqual(source.project_status, ProjectStatus.IN_PROGRESS)
        self.assertEqual(source.current_build_stage, BuildStage.PLAN)

    def test_deterministic_identity_frozen_snapshot_and_round_trip(self):
        source, approved = self.approved()
        first = create_plan_architecture_handoff(source_project=source, approved_plan=approved)
        second = create_plan_architecture_handoff(source_project=source, approved_plan=approved)
        self.assertEqual(first.handoff_id, second.handoff_id)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(PlanArchitectureHandoff.from_json(first.canonical_json()), first)
        self.assertEqual(first.frozen_approved_plan.canonical_json(), approved.canonical_json())

    def test_identity_binding_across_every_contract(self):
        source, approved = self.approved()
        handoff = create_plan_architecture_handoff(source_project=source, approved_plan=approved)
        self.assertEqual(handoff.source_project_id, source.project_id)
        self.assertEqual(handoff.idea_handoff_id, approved.idea_handoff_id)
        self.assertEqual(handoff.approved_plan_id, approved.approval_id)
        self.assertEqual(handoff.software_plan_id, approved.software_plan_id)
        self.assertEqual(handoff.plan_finalization_id, approved.plan_finalization_id)

    def test_explicit_approval_readiness_and_consistency_required(self):
        helper = approval_helpers.ArcaDevPlanApprovalTest()
        idea_handoff, _, finalization = helper.complete()
        rejected = reject_plan(handoff=idea_handoff, finalization=finalization, approval_statement="Not approved.")
        with self.assertRaisesRegex(ValueError, "explicit approved-plan"):
            create_plan_architecture_handoff(source_project=idea_handoff.resulting_project, approved_plan=rejected)
        self.assertTrue(finalization.effective_ready_for_architecture)
        self.assertTrue(idea_handoff.resulting_project.current_build_stage is BuildStage.PLAN)

    def test_wrong_project_and_wrong_stage_rejected(self):
        source, approved = self.approved()
        forged = replace(source, project_id="arcadev_" + "0" * 32)
        with self.assertRaisesRegex(ValueError, "forged|stale"):
            create_plan_architecture_handoff(source_project=forged, approved_plan=approved)
        wrong_stage = replace(source, current_build_stage=BuildStage.ARCHITECTURE)
        with self.assertRaisesRegex(ValueError, "forged|stale|PLAN"):
            create_plan_architecture_handoff(source_project=wrong_stage, approved_plan=approved)

    def test_stale_plan_finalization_approval_and_replay_rejected(self):
        source, approved = self.approved()
        handoff = create_plan_architecture_handoff(source_project=source, approved_plan=approved)
        _, other_approval = self.approved("A different explicit approval statement.")
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_plan_architecture_handoff(handoff, approved_plan=other_approval)
        with self.assertRaisesRegex(ValueError, "still-current PLAN"):
            validate_plan_architecture_handoff(handoff, source_project=handoff.resulting_project)
        value = approved.canonical_dict()
        value["software_plan_id"] = "arcadev_plan_" + "0" * 32
        with self.assertRaisesRegex(ValueError, "forged"):
            PlanArchitectureHandoff.from_dict({**handoff.canonical_dict(), "frozen_approved_plan": value})

    def test_forged_eligibility_result_and_identifiers_rejected(self):
        source, approved = self.approved()
        handoff = create_plan_architecture_handoff(source_project=source, approved_plan=approved)
        for field, replacement in (
            ("transition_eligible", False),
            ("decision", "blocked"),
            ("handoff_id", "arcadev_arch_handoff_" + "0" * 32),
            ("source_project_id", "arcadev_" + "0" * 32),
            ("approved_plan_id", "arcadev_approved_plan_" + "0" * 32),
            ("software_plan_id", "arcadev_plan_" + "0" * 32),
            ("plan_finalization_id", "arcadev_plan_final_" + "0" * 32),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "forged"):
                value = handoff.canonical_dict()
                value[field] = replacement
                PlanArchitectureHandoff.from_dict(value)
        value = handoff.canonical_dict()
        value["resulting_project"]["current_build_stage"] = "PLAN"
        with self.assertRaisesRegex(ValueError, "forged"):
            PlanArchitectureHandoff.from_dict(value)

    def test_unknown_duplicate_malformed_schema_and_oversize_rejected(self):
        source, approved = self.approved()
        handoff = create_plan_architecture_handoff(source_project=source, approved_plan=approved)
        value = handoff.canonical_dict()
        value["provider"] = "model"
        with self.assertRaisesRegex(ValueError, "shape"):
            PlanArchitectureHandoff.from_dict(value)
        value = handoff.canonical_dict()
        value["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported"):
            PlanArchitectureHandoff.from_dict(value)
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            PlanArchitectureHandoff.from_json('{"schema":"a","schema":"b"}')
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            PlanArchitectureHandoff.from_json("{")
        with self.assertRaisesRegex(ValueError, "safety limit"):
            PlanArchitectureHandoff.from_json(" " * 15_000_001)

    def test_no_architecture_or_generation_content(self):
        source, approved = self.approved()
        handoff = create_plan_architecture_handoff(source_project=source, approved_plan=approved)
        self.assertFalse(hasattr(handoff, "architecture"))
        self.assertFalse(hasattr(handoff, "models"))
        self.assertFalse(hasattr(handoff, "backend"))
        self.assertFalse(hasattr(handoff, "frontend"))
        self.assertEqual(handoff.frozen_approved_plan, approved)


if __name__ == "__main__":
    unittest.main()
