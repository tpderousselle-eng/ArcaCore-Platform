import json
from dataclasses import replace
import unittest

from arcadev import (
    ARCADEV_IDEA_PLAN_HANDOFF_SCHEMA,
    BuildStage,
    Confidence,
    IdeaFinalization,
    IdeaIntake,
    IdeaPlanHandoff,
    IntentProvenance,
    IntentValue,
    ProjectMetadata,
    ProjectStatus,
    TransitionDecision,
    create_idea_plan_handoff,
    evaluate_idea_consistency,
    validate_idea_plan_handoff,
)


def _intent(value, transcript, *, scalar=False):
    return IntentValue.create(
        value=value,
        provenance=IntentProvenance.EXPLICIT,
        confidence=Confidence.HIGH,
        evidence=[value],
        original_user_request=transcript,
        maximum=8_000 if scalar else 512,
    )


def finalized(
    *,
    project_type="web_application",
    platforms=("Desktop web", "Mobile web"),
    authentication=("Email/password", "Google OAuth"),
    integrations=("GitHub",),
    deployment=("ArcaCentum managed cloud",),
):
    all_values = (
        "Gaming Studio", project_type, "A studio for game projects", "users",
        "Manage game development projects", "asset management", "build management",
        "game project management", "publishing workflow", "testing workflow",
        *platforms, *authentication, *integrations, *deployment,
    )
    transcript = "Approved IDEA: " + "; ".join(all_values)
    intake = IdeaIntake.create(
        original_user_request=transcript,
        proposed_project_name=_intent("Gaming Studio", transcript, scalar=True),
        project_type=_intent(project_type, transcript, scalar=True),
        product_description=_intent("A studio for game projects", transcript, scalar=True),
        target_users=[_intent("users", transcript)],
        primary_goal=_intent("Manage game development projects", transcript, scalar=True),
        requested_features=[_intent(value, transcript) for value in (
            "asset management", "build management", "game project management",
            "publishing workflow", "testing workflow",
        )],
        platform_targets=[_intent(value, transcript) for value in platforms],
        authentication_requirements=[_intent(value, transcript) for value in authentication],
        integration_requirements=[_intent(value, transcript) for value in integrations],
        deployment_requirements=[_intent(value, transcript) for value in deployment],
    )
    state = IdeaFinalization.start(intake)
    project = state.to_project(metadata=ProjectMetadata.create(created_at="2026-09-10T08:00:00Z"))
    return state, project


class ArcaDevIdeaPlanHandoffTest(unittest.TestCase):
    def test_valid_gaming_studio_handoff_and_transition(self):
        state, project = finalized()
        handoff = create_idea_plan_handoff(project, state)
        self.assertTrue(state.current_intake.readiness.ready_for_plan)
        self.assertTrue(handoff.snapshot.consistency.consistent)
        self.assertTrue(handoff.eligible)
        self.assertEqual(handoff.decision, TransitionDecision.TRANSITIONED)
        self.assertEqual(handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        self.assertEqual(handoff.resulting_project.current_build_stage, BuildStage.PLAN)
        self.assertEqual(project.project_status, ProjectStatus.READY)
        self.assertEqual(project.current_build_stage, BuildStage.IDEA)
        self.assertFalse(hasattr(handoff, "plan"))

    def test_deterministic_identity_frozen_snapshot_and_round_trip(self):
        state, project = finalized()
        first = create_idea_plan_handoff(project, state)
        second = create_idea_plan_handoff(project, state)
        self.assertEqual(first.handoff_id, second.handoff_id)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(IdeaPlanHandoff.from_json(first.canonical_json()), first)
        self.assertEqual(first.snapshot.project, project)
        self.assertEqual(first.snapshot.finalization, state)
        self.assertEqual(first.schema, ARCADEV_IDEA_PLAN_HANDOFF_SCHEMA)

    def test_web_and_mobile_platform_consistency_blockers(self):
        for project_type, platforms, code in (
            ("web_application", ("iOS", "Android"), "web_without_web_target"),
            ("mobile_application", ("Desktop web",), "mobile_without_mobile_target"),
        ):
            with self.subTest(project_type=project_type):
                state, project = finalized(project_type=project_type, platforms=platforms)
                handoff = create_idea_plan_handoff(project, state)
                self.assertFalse(handoff.eligible)
                self.assertEqual(handoff.decision, TransitionDecision.BLOCKED)
                self.assertIn(code, [item.code for item in handoff.snapshot.consistency.blocking_findings])
                self.assertEqual(handoff.resulting_project, project)

    def test_authentication_integration_and_deployment_contradictions(self):
        cases = (
            ({"authentication": ("No authentication required", "Email/password")}, "authentication_contradiction"),
            ({"integrations": ("No external integrations", "GitHub")}, "integration_contradiction"),
            ({"deployment": ("ArcaCentum managed cloud", "Self-hosted")}, "deployment_contradiction"),
        )
        for arguments, code in cases:
            with self.subTest(code=code):
                state, project = finalized(**arguments)
                handoff = create_idea_plan_handoff(project, state)
                self.assertFalse(handoff.eligible)
                self.assertIn(code, [item.code for item in handoff.snapshot.consistency.blocking_findings])

    def test_unknown_project_type_warns_without_blocking(self):
        state, project = finalized(project_type="embedded_system", platforms=("Custom hardware",))
        evaluation = evaluate_idea_consistency(state.current_intake)
        self.assertTrue(evaluation.consistent)
        self.assertEqual([item.code for item in evaluation.warnings], ["platform_compatibility_not_determined"])
        self.assertTrue(create_idea_plan_handoff(project, state).eligible)

    def test_ready_and_idea_stage_requirements(self):
        state, project = finalized()
        draft = replace(project, project_status=ProjectStatus.DRAFT)
        self.assertFalse(create_idea_plan_handoff(draft, state).eligible)
        progressed = replace(project, project_status=ProjectStatus.IN_PROGRESS, current_build_stage=BuildStage.PLAN)
        with self.assertRaisesRegex(ValueError, "begin at the IDEA"):
            create_idea_plan_handoff(progressed, state)

    def test_nonready_intake_and_unresolved_assumptions_block(self):
        transcript = "Make me an app called Maybe App for users. Maybe App"
        intake = IdeaIntake.create(original_user_request=transcript)
        state = IdeaFinalization.start(intake)
        _, unrelated_project = finalized()
        self.assertFalse(create_idea_plan_handoff(unrelated_project, state).eligible)

    def test_project_intake_identity_mismatch_blocks(self):
        state, _ = finalized()
        other_state, other_project = finalized(project_type="mobile_application", platforms=("iOS",))
        self.assertNotEqual(state.current_intake_id, other_state.current_intake_id)
        self.assertFalse(create_idea_plan_handoff(other_project, state).eligible)

    def test_forged_flags_result_and_identities_rejected(self):
        state, project = finalized()
        handoff = create_idea_plan_handoff(project, state)
        for key, value in (
            ("eligible", False),
            ("decision", "blocked"),
            ("handoff_id", "arcadev_handoff_" + "0" * 32),
            ("source_project_id", "arcadev_" + "0" * 32),
            ("source_intake_id", "arcadev_idea_" + "0" * 32),
        ):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "forged|stale|inconsistent"):
                value_dict = handoff.canonical_dict()
                value_dict[key] = value
                IdeaPlanHandoff.from_dict(value_dict)
        value_dict = handoff.canonical_dict()
        value_dict["resulting_project"]["project_status"] = "READY"
        with self.assertRaisesRegex(ValueError, "forged|stale|inconsistent"):
            IdeaPlanHandoff.from_dict(value_dict)

    def test_replay_and_stale_validation_rejected(self):
        state, project = finalized()
        handoff = create_idea_plan_handoff(project, state)
        _, other_project = finalized(project_type="mobile_application", platforms=("iOS",))
        with self.assertRaisesRegex(ValueError, "replay"):
            validate_idea_plan_handoff(handoff.canonical_dict(), project=other_project)
        other_state, _ = finalized(integrations=("GitLab",))
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_idea_plan_handoff(handoff.canonical_dict(), finalization=other_state)

    def test_malformed_unknown_duplicate_schema_and_oversize_rejected(self):
        state, project = finalized()
        handoff = create_idea_plan_handoff(project, state)
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            IdeaPlanHandoff.from_json("{")
        value = handoff.canonical_dict()
        value["provider"] = "model"
        with self.assertRaisesRegex(ValueError, "shape"):
            IdeaPlanHandoff.from_dict(value)
        value = handoff.canonical_dict()
        value["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported"):
            IdeaPlanHandoff.from_dict(value)
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            IdeaPlanHandoff.from_json('{"schema": "a", "schema": "b"}')
        with self.assertRaisesRegex(ValueError, "safety limit"):
            IdeaPlanHandoff.from_json(" " * 5_000_001)


if __name__ == "__main__":
    unittest.main()
