import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arcadev.project import (
    ARCADEV_PROJECT_SCHEMA,
    ArcaDevProject,
    BuildStage,
    ProjectMetadata,
    ProjectSpecification,
    ProjectStatus,
    load_project,
    save_project,
)


class ArcaDevProjectTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def specification(self, **changes):
        values = {
            "project_type": "web_application",
            "target_users": ["Operations teams", "Site owners"],
            "primary_goal": "Help teams understand service health",
            "requested_features": ["Health dashboard", "Incident timeline"],
            "platform_targets": ["Desktop web", "Mobile web"],
            "authentication_requirements": ["Organization sign-in"],
            "integration_requirements": ["PostgreSQL"],
            "deployment_targets": ["Kubernetes"],
            "user_constraints": ["Must meet WCAG 2.2 AA"],
        }
        values.update(changes)
        return ProjectSpecification.create(**values)

    def project(self, **changes):
        values = {
            "project_name": "Service Atlas",
            "project_description": "A service-health workspace for operations teams.",
            "original_user_request": "Build a service health dashboard for our operations team.\nKeep the original wording.",
            "specification": self.specification(),
            "metadata": ProjectMetadata.create(created_at="2026-09-10T08:00:00Z"),
        }
        values.update(changes)
        return ArcaDevProject.create(**values)

    def test_valid_project_creation_starts_at_idea(self):
        project = self.project()
        self.assertRegex(project.project_id, r"^arcadev_[0-9a-f]{32}$")
        self.assertEqual(project.project_status, ProjectStatus.DRAFT)
        self.assertEqual(project.current_build_stage, BuildStage.IDEA)
        self.assertEqual(project.metadata.schema, ARCADEV_PROJECT_SCHEMA)

    def test_required_fields_and_invalid_project_data_are_rejected(self):
        for key in ("project_name", "project_description", "original_user_request"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.project(**{key: ""})
        with self.assertRaises(ValueError):
            self.project(specification={})
        with self.assertRaises(ValueError):
            self.specification(project_type="Web App")
        with self.assertRaises(ValueError):
            self.specification(requested_features=[])

    def test_all_stages_and_statuses_are_canonical_and_invalid_values_fail(self):
        self.assertEqual(
            [stage.value for stage in BuildStage],
            ["IDEA", "PLAN", "ARCHITECTURE", "MODELS", "BACKEND", "FRONTEND", "TESTS", "SECURITY", "PREVIEW", "DEPLOYMENT"],
        )
        self.assertEqual(
            {status.value for status in ProjectStatus},
            {"DRAFT", "READY", "IN_PROGRESS", "BLOCKED", "FAILED", "COMPLETED"},
        )
        with self.assertRaisesRegex(ValueError, "stage"):
            self.project(current_build_stage="EXECUTE")
        with self.assertRaisesRegex(ValueError, "IDEA"):
            self.project(current_build_stage=BuildStage.PLAN)
        with self.assertRaisesRegex(ValueError, "status"):
            self.project(project_status="UNKNOWN")

    def test_deterministic_serialization_and_unordered_inputs(self):
        first = self.project()
        second = self.project(specification=self.specification(
            target_users=["Site owners", "Operations teams"],
            requested_features=["Incident timeline", "Health dashboard"],
        ))
        self.assertEqual(first.project_id, second.project_id)
        self.assertEqual(first.canonical_json(), second.canonical_json())
        self.assertTrue(first.canonical_json().endswith("\n"))

    def test_schema_name_version_and_unknown_fields_fail_closed(self):
        value = self.project().canonical_dict()
        value["metadata"]["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "version"):
            ArcaDevProject.from_dict(value)
        value = self.project().canonical_dict()
        value["metadata"]["schema"] = "attacker.project"
        with self.assertRaisesRegex(ValueError, "schema"):
            ArcaDevProject.from_dict(value)
        value = self.project().canonical_dict()
        value["command"] = "python payload.py"
        with self.assertRaisesRegex(ValueError, "shape"):
            ArcaDevProject.from_dict(value)

    def test_original_user_intent_is_preserved_verbatim(self):
        request = "Please build this exactly.\n\n  Preserve these spaces and wording."
        project = self.project(original_user_request=request)
        self.assertEqual(project.original_user_request, request)
        self.assertEqual(json.loads(project.canonical_json())["original_user_request"], request)

    def test_duplicate_input_has_same_identity_and_changed_intent_does_not(self):
        self.assertEqual(self.project().project_id, self.project().project_id)
        self.assertNotEqual(
            self.project().project_id,
            self.project(original_user_request="Build a different product.").project_id,
        )
        forged = self.project().canonical_dict()
        forged["project_id"] = "arcadev_" + "0" * 32
        with self.assertRaisesRegex(ValueError, "identity"):
            ArcaDevProject.from_dict(forged)

    def test_hostile_malformed_and_oversized_input_is_rejected(self):
        with self.assertRaises(ValueError):
            self.project(project_name="name\x00payload")
        with self.assertRaises(ValueError):
            self.project(project_description="x" * 8_001)
        with self.assertRaises(ValueError):
            self.specification(target_users=["same", "same"])
        path = self.root / "project.json"
        path.write_text('{"project_id":"one","project_id":"two"}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            load_project(path)
        path.write_bytes(b"x" * 1_000_001)
        with self.assertRaisesRegex(ValueError, "safety limit"):
            load_project(path)

    def test_secret_like_values_are_rejected_but_auth_intent_is_allowed(self):
        allowed = self.project(specification=self.specification(
            authentication_requirements=["Require password authentication and MFA"]
        ))
        self.assertIn("password authentication", allowed.specification.authentication_requirements[0])
        for value in (
            "password=hunter2",
            "api_key: sk-live-secretvalue",
            "-----BEGIN PRIVATE KEY----- abc",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "credential|secret"):
                self.project(original_user_request=value)

    def test_serialization_deserialization_round_trip_and_noncanonical_rejection(self):
        project = self.project()
        path = save_project(self.root, ".arcadev/project.json", project)
        self.assertEqual(load_project(path), project)
        first = path.read_bytes()
        save_project(self.root, ".arcadev/project.json", project)
        self.assertEqual(path.read_bytes(), first)
        path.write_text(json.dumps(project.canonical_dict(), indent=2), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not canonical"):
            load_project(path)

    def test_path_containment_symlink_and_atomic_failure(self):
        project = self.project()
        path = save_project(self.root, "project.json", project)
        previous = path.read_bytes()
        for unsafe in ("../escape.json", "/absolute.json", "dir\\project.json", "./project.json"):
            with self.subTest(unsafe=unsafe), self.assertRaises(ValueError):
                save_project(self.root, unsafe, project)
        original = Path.is_symlink
        with patch.object(Path, "is_symlink", lambda candidate: candidate.name == "link" or original(candidate)):
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                save_project(self.root, "link/project.json", project)
        with patch("arcadev.project.os.replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                save_project(self.root, "project.json", project)
        self.assertEqual(path.read_bytes(), previous)

    def test_metadata_must_be_explicit_canonical_and_monotonic(self):
        with self.assertRaises(ValueError):
            ProjectMetadata.create(created_at="now")
        with self.assertRaisesRegex(ValueError, "calendar"):
            ProjectMetadata.create(created_at="2026-02-31T08:00:00Z")
        with self.assertRaises(ValueError):
            ProjectMetadata.create(created_at="2026-09-10T08:00:00Z", updated_at="2026-09-09T08:00:00Z")
        metadata = ProjectMetadata.create(
            created_at="2026-09-10T08:00:00Z", updated_at="2026-09-10T09:00:00Z"
        )
        self.assertEqual(metadata.updated_at, "2026-09-10T09:00:00Z")


if __name__ == "__main__":
    unittest.main()
