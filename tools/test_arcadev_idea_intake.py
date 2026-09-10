import json
import unittest

from arcadev import (
    ARCADEV_IDEA_INTAKE_SCHEMA,
    ArcaDevProject,
    BuildStage,
    ClarificationRequirement,
    Confidence,
    IdeaIntake,
    IntentProvenance,
    IntentValue,
    ProjectMetadata,
    ProjectStatus,
    normalize_idea,
    validate_candidate,
)


COMPLETE_IDEA = (
    "Build a web application called Service Atlas for operations teams to monitor services and manage incidents. "
    "Include a health dashboard, incident timeline, and audit export. Require SSO and MFA. "
    "Integrate with Slack. Deploy to Kubernetes. Must meet WCAG 2.2 AA. Use PostgreSQL."
)


class ArcaDevIdeaIntakeTest(unittest.TestCase):
    def explicit(self, value, evidence, request=COMPLETE_IDEA):
        return IntentValue.create(
            value=value,
            provenance=IntentProvenance.EXPLICIT,
            confidence=Confidence.HIGH,
            evidence=[evidence],
            original_user_request=request,
        )

    def complete_intake(self, **changes):
        request = changes.pop("original_user_request", COMPLETE_IDEA)
        values = {
            "original_user_request": request,
            "proposed_project_name": self.explicit("Service Atlas", "called Service Atlas", request),
            "project_type": IntentValue.create(
                value="web_application",
                provenance=IntentProvenance.DERIVED,
                confidence=Confidence.HIGH,
                evidence=["web application"],
                original_user_request=request,
            ),
            "product_description": IntentValue.create(
                value="A service monitoring workspace.",
                provenance=IntentProvenance.DERIVED,
                confidence=Confidence.HIGH,
                evidence=["monitor services and manage incidents"],
                original_user_request=request,
            ),
            "target_users": [self.explicit("operations teams", "for operations teams", request)],
            "primary_goal": IntentValue.create(
                value="Monitor services and manage incidents",
                provenance=IntentProvenance.DERIVED,
                confidence=Confidence.HIGH,
                evidence=["to monitor services and manage incidents"],
                original_user_request=request,
            ),
            "requested_features": [
                self.explicit("Health dashboard", "health dashboard", request),
                self.explicit("Incident timeline", "incident timeline", request),
            ],
            "platform_targets": [
                IntentValue.create(
                    value="Web",
                    provenance=IntentProvenance.DERIVED,
                    confidence=Confidence.HIGH,
                    evidence=["web application"],
                    original_user_request=request,
                )
            ],
            "authentication_requirements": [self.explicit("Single sign-on", "SSO", request)],
            "integration_requirements": [self.explicit("Slack", "Integrate with Slack", request)],
            "deployment_requirements": [self.explicit("Kubernetes", "Deploy to Kubernetes", request)],
            "explicit_constraints": [self.explicit("Must meet WCAG 2.2 AA", "Must meet WCAG 2.2 AA", request)],
            "non_functional_requirements": [
                IntentValue.create(
                    value="Accessibility: WCAG 2.2 AA",
                    provenance=IntentProvenance.DERIVED,
                    confidence=Confidence.HIGH,
                    evidence=["WCAG 2.2 AA"],
                    original_user_request=request,
                )
            ],
            "technology_preferences": [self.explicit("PostgreSQL", "Use PostgreSQL", request)],
        }
        values.update(changes)
        return IdeaIntake.create(**values)

    def test_complete_software_idea_normalization_and_readiness(self):
        intake = normalize_idea(COMPLETE_IDEA)
        self.assertEqual(intake.schema, ARCADEV_IDEA_INTAKE_SCHEMA)
        self.assertEqual(intake.proposed_project_name.value, "Service Atlas")
        self.assertEqual(intake.project_type.value, "web_application")
        self.assertEqual([item.value for item in intake.target_users], ["operations teams"])
        self.assertIn("Health dashboard", [item.value for item in intake.requested_features])
        self.assertEqual([item.value for item in intake.platform_targets], ["Web"])
        self.assertEqual(
            [item.value for item in intake.authentication_requirements],
            ["Multi-factor authentication", "Single sign-on"],
        )
        self.assertEqual([item.value for item in intake.integration_requirements], ["Slack"])
        self.assertEqual([item.value for item in intake.deployment_requirements], ["Kubernetes"])
        self.assertTrue(intake.readiness.ready_for_plan)
        self.assertEqual(intake.readiness.blocking_requirements, ())

    def test_minimal_underspecified_idea_is_not_ready(self):
        intake = normalize_idea("Make me an app.")
        self.assertFalse(intake.readiness.ready_for_plan)
        for requirement in (
            "proposed_project_name",
            "project_type",
            "target_users",
            "primary_goal",
            "requested_features",
            "platform_targets",
            "authentication_requirements",
            "integration_requirements",
            "deployment_requirements",
        ):
            self.assertIn(requirement, intake.readiness.blocking_requirements)
        self.assertTrue(all(item.provenance is IntentProvenance.UNRESOLVED for item in intake.unresolved_requirements))

    def test_gaming_studio_example_preserves_uncertainty(self):
        request = (
            "Build me a Gaming Studio where users can create and manage game projects, assets, builds, "
            "testing, and publishing."
        )
        intake = normalize_idea(request)
        self.assertEqual(intake.original_user_request, request)
        self.assertEqual(intake.proposed_project_name.value, "Gaming Studio")
        self.assertEqual([item.value for item in intake.target_users], ["users"])
        self.assertIn("Create and manage game projects", [item.value for item in intake.requested_features])
        self.assertEqual(intake.assumptions[0].provenance, IntentProvenance.ASSUMED)
        self.assertIn("project_type", intake.readiness.blocking_requirements)
        self.assertIn("platform_targets", intake.readiness.blocking_requirements)
        self.assertIn("authentication_requirements", intake.readiness.blocking_requirements)
        self.assertFalse(intake.readiness.ready_for_plan)

    def test_web_and_mobile_application_normalization(self):
        web = normalize_idea(COMPLETE_IDEA)
        self.assertEqual(web.project_type.value, "web_application")
        self.assertEqual([item.value for item in web.platform_targets], ["Web"])

        mobile_request = (
            "Create a mobile app called Trail Mate for hikers to plan routes and save offline maps. "
            "No login required. Integrate with Mapbox. Publish to Apple App Store and Google Play. "
            "It must work offline."
        )
        mobile = normalize_idea(mobile_request)
        self.assertEqual(mobile.project_type.value, "mobile_application")
        self.assertEqual([item.value for item in mobile.target_users], ["hikers"])
        self.assertEqual([item.value for item in mobile.authentication_requirements], ["No authentication required"])
        self.assertEqual([item.value for item in mobile.integration_requirements], ["Mapbox"])
        self.assertEqual(
            [item.value for item in mobile.deployment_requirements],
            ["Apple App Store", "Google Play"],
        )
        self.assertIn("Offline operation", [item.value for item in mobile.non_functional_requirements])
        self.assertEqual([item.value for item in mobile.platform_targets], ["Mobile"])
        self.assertTrue(mobile.readiness.ready_for_plan)

    def test_provenance_assumptions_and_structured_clarification(self):
        request = "Build a web application for editors."
        clarification = ClarificationRequirement.create(
            requirement="primary_goal",
            question="What should editors accomplish?",
            blocking=True,
            evidence=["for editors"],
            original_user_request=request,
        )
        assumption = IntentValue.create(
            value="Editors may manage content.",
            provenance=IntentProvenance.ASSUMED,
            confidence=Confidence.LOW,
            evidence=["editors"],
            original_user_request=request,
        )
        intake = IdeaIntake.create(
            original_user_request=request,
            product_description=IntentValue.create(
                value=request,
                provenance=IntentProvenance.DERIVED,
                confidence=Confidence.HIGH,
                evidence=[request],
                original_user_request=request,
            ),
            unresolved_requirements=[clarification],
            assumptions=[assumption],
        )
        self.assertIn("primary_goal", intake.readiness.blocking_requirements)
        self.assertIn("assumptions", intake.readiness.blocking_requirements)
        with self.assertRaisesRegex(ValueError, "silently promote"):
            IdeaIntake.create(original_user_request=request, primary_goal=assumption)

    def test_deterministic_normalization_and_equivalent_unordered_input(self):
        first = normalize_idea(COMPLETE_IDEA)
        second = normalize_idea(COMPLETE_IDEA)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertTrue(first.canonical_json().endswith("\n"))

        constructed = self.complete_intake()
        reversed_input = self.complete_intake(
            requested_features=list(reversed(constructed.requested_features)),
            authentication_requirements=list(reversed(constructed.authentication_requirements)),
        )
        self.assertEqual(constructed.canonical_json(), reversed_input.canonical_json())

    def test_original_wording_and_round_trip_are_preserved(self):
        request = COMPLETE_IDEA.replace("Build a", "Please  build a\n")
        intake = normalize_idea(request)
        self.assertEqual(intake.original_user_request, request)
        restored = IdeaIntake.from_json(intake.canonical_json())
        self.assertEqual(restored, intake)
        self.assertEqual(validate_candidate(request, json.loads(intake.canonical_json())), intake)

    def test_invalid_candidate_unknown_fields_and_forged_readiness_fail(self):
        intake = self.complete_intake()
        value = intake.canonical_dict()
        value["provider"] = "untrusted-model"
        with self.assertRaisesRegex(ValueError, "shape"):
            validate_candidate(COMPLETE_IDEA, value)
        value = intake.canonical_dict()
        value["readiness"]["ready_for_plan"] = False
        with self.assertRaisesRegex(ValueError, "readiness"):
            validate_candidate(COMPLETE_IDEA, value)
        value = intake.canonical_dict()
        value["readiness"]["ready_for_plan"] = 1
        with self.assertRaisesRegex(ValueError, "boolean"):
            validate_candidate(COMPLETE_IDEA, value)
        value = intake.canonical_dict()
        value["target_users"] = "operators"
        with self.assertRaisesRegex(ValueError, "JSON array"):
            validate_candidate(COMPLETE_IDEA, value)
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            validate_candidate(COMPLETE_IDEA, '{"schema":"one","schema":"two"}')

    def test_secret_control_character_and_oversized_input_are_rejected(self):
        for request in (
            "Build an app. api_key: sk-live-secretvalue",
            "Build an app. password=hunter2",
            "-----BEGIN PRIVATE KEY----- payload",
            "Build\x00app",
        ):
            with self.subTest(request=request), self.assertRaisesRegex(ValueError, "secret|credential|control"):
                normalize_idea(request)
        with self.assertRaisesRegex(ValueError, "size"):
            normalize_idea("x" * 100_001)
        with self.assertRaisesRegex(ValueError, "safety limit"):
            IdeaIntake.from_json(" " * 1_000_001)
        with self.assertRaisesRegex(ValueError, "Unicode"):
            IdeaIntake.from_json("\ud800")

    def test_hostile_command_and_code_text_remains_inert(self):
        request = (
            "Build a web application called Command Museum for security students to study unsafe examples. "
            "Include displaying rm -rf / and python payload.py as inert educational text. Require SSO. "
            "No external integrations. Deploy to Kubernetes."
        )
        intake = normalize_idea(request)
        self.assertIn("rm -rf /", intake.original_user_request)
        self.assertTrue(any("rm -rf /" in item.value for item in intake.requested_features))
        self.assertEqual(intake.current_build_stage if hasattr(intake, "current_build_stage") else None, None)

    def test_ready_intake_converts_through_v11_contract_without_plan_transition(self):
        intake = self.complete_intake()
        self.assertTrue(intake.readiness.ready_for_plan)
        project = intake.to_project(metadata=ProjectMetadata.create(created_at="2026-09-10T08:00:00Z"))
        self.assertIsInstance(project, ArcaDevProject)
        self.assertEqual(project.project_status, ProjectStatus.READY)
        self.assertEqual(project.current_build_stage, BuildStage.IDEA)
        self.assertEqual(project.original_user_request, COMPLETE_IDEA)
        self.assertEqual(project.specification.project_type, "web_application")
        self.assertIn(
            "Non-functional requirement: Accessibility: WCAG 2.2 AA",
            project.specification.user_constraints,
        )
        incomplete = normalize_idea("Make me an app.")
        with self.assertRaisesRegex(ValueError, "ready"):
            incomplete.to_project(metadata=ProjectMetadata.create(created_at="2026-09-10T08:00:00Z"))


if __name__ == "__main__":
    unittest.main()
