import json
import unittest

from arcadev import (
    ARCADEV_CLARIFICATION_ANSWER_SCHEMA,
    ARCADEV_IDEA_FINALIZATION_SCHEMA,
    BuildStage,
    ClarificationAnswer,
    IdeaFinalization,
    IntentProvenance,
    ProjectMetadata,
    ProjectStatus,
    ResolutionAction,
    ResolutionOutcome,
    idea_intake_id,
    normalize_idea,
    resolve_clarification,
    validate_resolution_candidate,
)


GAMING_STUDIO = (
    "Build me a Gaming Studio where users can create and manage game projects, assets, builds, "
    "testing, and publishing."
)

COMPLETE_WEB = (
    "Build a web application called Service Atlas for operations teams to monitor services and manage incidents. "
    "Include a health dashboard and incident timeline. Require SSO. No external integrations. "
    "Deploy to Kubernetes."
)


class ArcaDevClarificationTest(unittest.TestCase):
    def gaming(self):
        return IdeaFinalization.start(normalize_idea(GAMING_STUDIO))

    def answer(
        self,
        state,
        requirement,
        user_answer,
        values=(),
        *,
        action=ResolutionAction.ANSWER,
        target_assumption=None,
        expected_previous_values=(),
    ):
        return ClarificationAnswer.create(
            target_intake_id=state.current_intake_id,
            requirement=requirement,
            user_answer=user_answer,
            action=action,
            normalized_values=values,
            evidence=[user_answer],
            target_assumption=target_assumption,
            expected_previous_values=expected_previous_values,
        )

    def resolve_gaming(self):
        state = self.gaming()
        assumption = state.current_intake.assumptions[0].value
        answers = (
            self.answer(
                state,
                "proposed_project_name",
                "Gaming Studio is the confirmed project name.",
                ["Gaming Studio"],
                action=ResolutionAction.CONFIRM_ASSUMPTION,
                target_assumption=assumption,
            ),
        )
        state = state.resolve(answers[0])
        for requirement, user_answer, values in (
            ("project_type", "Make it a web_application.", ["web_application"]),
            ("platform_targets", "Support Desktop web and Mobile web.", ["Desktop web", "Mobile web"]),
            (
                "authentication_requirements",
                "Use Email/password and Google OAuth authentication.",
                ["Email/password", "Google OAuth"],
            ),
            ("integration_requirements", "Integrate with GitHub.", ["GitHub"]),
            (
                "deployment_requirements",
                "Deploy to ArcaCentum managed cloud.",
                ["ArcaCentum managed cloud"],
            ),
        ):
            state = state.resolve(self.answer(state, requirement, user_answer, values))
        return state

    def test_single_resolution_targets_only_unresolved_requirement(self):
        state = self.gaming()
        before = state.current_intake
        answer = self.answer(state, "project_type", "Use web_application.", ["web_application"])
        result = resolve_clarification(state, answer)
        self.assertEqual(result.current_intake.project_type.value, "web_application")
        self.assertEqual(result.current_intake.target_users, before.target_users)
        self.assertEqual(result.current_intake.requested_features, before.requested_features)
        self.assertNotIn("project_type", [item.requirement for item in result.current_intake.unresolved_requirements])
        self.assertFalse(result.current_intake.readiness.ready_for_plan)

    def test_multi_value_platform_authentication_integrations_and_deployment(self):
        state = self.gaming()
        state = state.resolve(
            self.answer(
                state,
                "platform_targets",
                "Use Mobile web and Desktop web.",
                ["Mobile web", "Desktop web"],
            )
        )
        self.assertEqual(
            [item.value for item in state.current_intake.platform_targets],
            ["Desktop web", "Mobile web"],
        )
        state = state.resolve(
            self.answer(
                state,
                "authentication_requirements",
                "Use Google OAuth and Email/password.",
                ["Google OAuth", "Email/password"],
            )
        )
        state = state.resolve(
            self.answer(state, "integration_requirements", "Integrate with GitHub.", ["GitHub"])
        )
        state = state.resolve(
            self.answer(
                state,
                "deployment_requirements",
                "Deploy to ArcaCentum managed cloud.",
                ["ArcaCentum managed cloud"],
            )
        )
        self.assertEqual(
            [item.value for item in state.current_intake.authentication_requirements],
            ["Email/password", "Google OAuth"],
        )
        self.assertEqual([item.value for item in state.current_intake.integration_requirements], ["GitHub"])
        self.assertEqual(
            [item.value for item in state.current_intake.deployment_requirements],
            ["ArcaCentum managed cloud"],
        )

    def test_gaming_studio_end_to_end_finalizes_at_idea(self):
        initial = self.gaming()
        self.assertFalse(initial.current_intake.readiness.ready_for_plan)
        state = self.resolve_gaming()
        intake = state.current_intake
        self.assertTrue(intake.readiness.ready_for_plan)
        self.assertEqual(intake.readiness.blocking_requirements, ())
        self.assertEqual(intake.assumptions, ())
        self.assertEqual(intake.unresolved_requirements, ())
        self.assertEqual(state.conflicts, ())
        self.assertEqual(len(state.history), 6)
        self.assertTrue(all(item.provenance is IntentProvenance.EXPLICIT for item in intake.platform_targets))
        project = state.to_project(
            metadata=ProjectMetadata.create(created_at="2026-09-10T08:00:00Z")
        )
        self.assertEqual(project.project_status, ProjectStatus.READY)
        self.assertEqual(project.current_build_stage, BuildStage.IDEA)
        self.assertEqual(project.project_name, "Gaming Studio")
        self.assertEqual(project.specification.project_type, "web_application")

    def test_assumption_confirmation_makes_value_explicit(self):
        state = self.gaming()
        assumption = state.current_intake.assumptions[0].value
        state = state.resolve(
            self.answer(
                state,
                "proposed_project_name",
                "Yes, Gaming Studio is the project name.",
                ["Gaming Studio"],
                action=ResolutionAction.CONFIRM_ASSUMPTION,
                target_assumption=assumption,
            )
        )
        self.assertEqual(state.current_intake.assumptions, ())
        self.assertEqual(
            state.current_intake.proposed_project_name.provenance,
            IntentProvenance.EXPLICIT,
        )
        self.assertEqual(
            state.history[0].answer.action,
            ResolutionAction.CONFIRM_ASSUMPTION,
        )

    def test_assumption_rejection_removes_tentative_value_but_keeps_requirement_open(self):
        state = self.gaming()
        assumption = state.current_intake.assumptions[0].value
        state = state.resolve(
            self.answer(
                state,
                "proposed_project_name",
                "No, that is not the project name.",
                action=ResolutionAction.REJECT_ASSUMPTION,
                target_assumption=assumption,
            )
        )
        self.assertEqual(state.current_intake.assumptions, ())
        self.assertIsNone(state.current_intake.proposed_project_name)
        self.assertIn("proposed_project_name", state.current_intake.readiness.blocking_requirements)
        self.assertEqual(state.history[0].accepted_values, ())

    def test_assumption_replacement_records_corrected_value(self):
        state = self.gaming()
        assumption = state.current_intake.assumptions[0].value
        state = state.resolve(
            self.answer(
                state,
                "proposed_project_name",
                "Use Arcade Forge as the corrected name.",
                ["Arcade Forge"],
                action=ResolutionAction.REPLACE_ASSUMPTION,
                target_assumption=assumption,
            )
        )
        self.assertEqual(state.current_intake.proposed_project_name.value, "Arcade Forge")
        self.assertEqual(state.current_intake.proposed_project_name.provenance, IntentProvenance.EXPLICIT)
        self.assertEqual(state.history[0].previous_values, ("Gaming Studio",))
        self.assertEqual(state.history[0].accepted_values, ("Arcade Forge",))

    def test_conflict_is_explicit_and_requires_deliberate_replacement(self):
        state = IdeaFinalization.start(normalize_idea(COMPLETE_WEB))
        self.assertTrue(state.current_intake.readiness.ready_for_plan)
        unchanged_platforms = state.current_intake.platform_targets
        conflict_answer = self.answer(
            state, "project_type", "Actually make it mobile_application only.", ["mobile_application"]
        )
        conflicted = state.resolve(conflict_answer)
        self.assertEqual(conflicted.current_intake.project_type.value, "web_application")
        self.assertEqual(conflicted.current_intake.platform_targets, unchanged_platforms)
        self.assertEqual(conflicted.history[-1].outcome, ResolutionOutcome.CONFLICT)
        self.assertEqual(conflicted.history[-1].rejected_values, ("mobile_application",))
        self.assertEqual(len(conflicted.conflicts), 1)
        self.assertFalse(conflicted.current_intake.readiness.ready_for_plan)
        with self.assertRaisesRegex(ValueError, "deliberate"):
            conflicted.resolve(
                self.answer(
                    conflicted,
                    "project_type",
                    "Use mobile_application.",
                    ["mobile_application"],
                )
            )

        replacement = self.answer(
            conflicted,
            "project_type",
            "Deliberately replace web_application with mobile_application.",
            ["mobile_application"],
            action=ResolutionAction.REPLACE_EXPLICIT,
            expected_previous_values=["web_application"],
        )
        resolved = conflicted.resolve(replacement)
        self.assertEqual(resolved.current_intake.project_type.value, "mobile_application")
        self.assertEqual(resolved.current_intake.platform_targets, unchanged_platforms)
        self.assertEqual(resolved.conflicts, ())
        self.assertTrue(resolved.current_intake.readiness.ready_for_plan)

    def test_history_preserves_answers_values_assumptions_and_readiness(self):
        state = self.resolve_gaming()
        first = state.history[0]
        last = state.history[-1]
        self.assertEqual(first.answer.answer_provenance, IntentProvenance.EXPLICIT)
        self.assertEqual(first.previous_values, ("Gaming Studio",))
        self.assertFalse(first.readiness_before)
        self.assertFalse(first.readiness_after)
        self.assertEqual(len(first.assumptions_before), 1)
        self.assertEqual(first.assumptions_after, ())
        self.assertFalse(last.readiness_before)
        self.assertTrue(last.readiness_after)
        self.assertEqual(last.unresolved_after, ())
        self.assertEqual(state.initial_intake.original_user_request, GAMING_STUDIO)
        self.assertTrue(state.current_intake.original_user_request.startswith(GAMING_STUDIO))

    def test_deterministic_resolution_unordered_values_and_round_trip(self):
        first = self.resolve_gaming()
        second = self.resolve_gaming()
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertEqual(IdeaFinalization.from_json(first.canonical_json()), first)
        self.assertEqual(first.schema, ARCADEV_IDEA_FINALIZATION_SCHEMA)

        state = self.gaming()
        one = self.answer(
            state,
            "platform_targets",
            "Desktop web and Mobile web.",
            ["Desktop web", "Mobile web"],
        )
        two = self.answer(
            state,
            "platform_targets",
            "Desktop web and Mobile web.",
            ["Mobile web", "Desktop web"],
        )
        self.assertEqual(one.canonical_json(), two.canonical_json())
        self.assertEqual(one.schema, ARCADEV_CLARIFICATION_ANSWER_SCHEMA)

    def test_stale_replay_forged_identity_and_nonexistent_requirement_fail(self):
        state = self.gaming()
        answer = self.answer(state, "project_type", "Use web_application.", ["web_application"])
        resolved = state.resolve(answer)
        with self.assertRaisesRegex(ValueError, "different or stale"):
            resolved.resolve(answer)
        forged = answer.canonical_dict()
        forged["target_intake_id"] = "arcadev_idea_" + "0" * 32
        with self.assertRaisesRegex(ValueError, "different or stale"):
            validate_resolution_candidate(state.current_intake, forged)
        nonexistent = self.answer(state, "database_choice", "Use PostgreSQL.", ["PostgreSQL"])
        with self.assertRaisesRegex(ValueError, "nonexistent"):
            state.resolve(nonexistent)

    def test_invalid_unknown_duplicate_and_schema_confused_candidates_fail(self):
        state = self.gaming()
        answer = self.answer(state, "project_type", "Use web_application.", ["web_application"])
        value = answer.canonical_dict()
        value["provider"] = "untrusted-model"
        with self.assertRaisesRegex(ValueError, "shape"):
            validate_resolution_candidate(state.current_intake, value)
        value = answer.canonical_dict()
        value["answer_provenance"] = IntentProvenance.DERIVED.value
        with self.assertRaisesRegex(ValueError, "explicit"):
            validate_resolution_candidate(state.current_intake, value)
        value = answer.canonical_dict()
        value["schema"] = "attacker.resolution"
        with self.assertRaisesRegex(ValueError, "schema"):
            validate_resolution_candidate(state.current_intake, value)
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            ClarificationAnswer.from_json('{"schema":"one","schema":"two"}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.answer(
                state,
                "platform_targets",
                "Use web twice.",
                ["Web", "web"],
            )

    def test_secret_control_oversize_and_invalid_cardinality_fail(self):
        state = self.gaming()
        for text in (
            "password=hunter2",
            "api_key: sk-live-secretvalue",
            "-----BEGIN PRIVATE KEY----- payload",
            "Bad\x00answer",
        ):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "secret|credential|control"):
                self.answer(state, "project_type", text, ["web_application"])
        with self.assertRaisesRegex(ValueError, "size"):
            self.answer(state, "project_type", "x" * 20_001, ["web_application"])
        multiple = self.answer(
            state,
            "project_type",
            "Use web_application and mobile_application.",
            ["web_application", "mobile_application"],
        )
        with self.assertRaisesRegex(ValueError, "exactly one"):
            state.resolve(multiple)

    def test_hostile_command_and_code_text_remain_inert(self):
        state = IdeaFinalization.start(normalize_idea("Make me an app."))
        answer = self.answer(
            state,
            "requested_features",
            "Display rm -rf / and python payload.py as inert educational text.",
            ["Display rm -rf / and python payload.py as inert educational text"],
        )
        state = state.resolve(answer)
        self.assertIn("rm -rf /", state.current_intake.requested_features[0].value)
        self.assertIn("python payload.py", state.history[0].answer.user_answer)
        self.assertFalse(state.current_intake.readiness.ready_for_plan)

    def test_forged_finalization_result_or_readiness_cannot_round_trip(self):
        state = self.resolve_gaming()
        value = json.loads(state.canonical_json())
        value["current_intake_id"] = "arcadev_idea_" + "0" * 32
        with self.assertRaisesRegex(ValueError, "forged"):
            IdeaFinalization.from_dict(value)
        value = json.loads(state.canonical_json())
        value["current_intake"]["readiness"]["ready_for_plan"] = False
        with self.assertRaisesRegex(ValueError, "readiness"):
            IdeaFinalization.from_dict(value)


if __name__ == "__main__":
    unittest.main()
