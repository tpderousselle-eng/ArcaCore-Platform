"""Production IDEA evidence and fail-closed readiness checks."""

import ast
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

from arcadev import gaming_studio_idea as production
from arcadev.gaming_studio_intent import (
    AUTHORITY_DIRECTORY, ProductionIntent, canonical_bytes, load_production_intent,
)
from arcadev.idea_intake import IdeaIntake, IntentProvenance, normalize_idea
from arcadev.project import ArcaDevProject, ProjectMetadata


class GamingStudioIdeaTest(unittest.TestCase):
    def setUp(self):
        self.intent = load_production_intent()
        self.intake = production.materialize_idea(self.intent)

    def test_exact_request_and_canonical_persisted_roundtrip(self):
        data = (AUTHORITY_DIRECTORY / "idea_intake.json").read_bytes()
        self.assertEqual(data, self.intake.canonical_json().encode("utf-8"))
        self.assertEqual(IdeaIntake.from_json(data.decode("utf-8")), self.intake)
        self.assertEqual(self.intake.original_user_request, self.intent.approved_intent)

    def test_materialization_is_deterministic(self):
        self.assertEqual(production.materialize_idea(self.intent), self.intake)
        self.assertEqual(production.validate_production_idea(self.intent, self.intake), self.intake)

    def test_all_values_are_explicit_exact_quotes_with_no_assumptions(self):
        review = production.clarification_review(self.intent, self.intake)
        normalized = review["normalized_values"]
        self.assertEqual(normalized[IntentProvenance.DERIVED.value], [])
        self.assertEqual(normalized[IntentProvenance.ASSUMED.value], [])
        self.assertEqual(self.intake.assumptions, ())
        self.assertTrue(normalized[IntentProvenance.EXPLICIT.value])
        for item in normalized[IntentProvenance.EXPLICIT.value]:
            self.assertIn(item["value"], self.intent.approved_intent)
            self.assertTrue(item["evidence"])
            for quote in item["evidence"]:
                self.assertIn(quote, self.intent.approved_intent)

    def test_material_choices_remain_blocking_questions(self):
        self.assertEqual(self.intake.readiness.blocking_requirements, (
            "authentication_requirements", "deployment_requirements", "platform_targets",
            "project_type", "target_users",
        ))
        self.assertIsNone(self.intake.project_type)
        self.assertEqual(self.intake.platform_targets, ())
        self.assertEqual(self.intake.deployment_requirements, ())
        self.assertEqual([v.value for v in self.intake.target_users], ["a user"])
        self.assertEqual([v.value for v in self.intake.authentication_requirements], [production.AUTHENTICATION])
        for question in self.intake.unresolved_requirements:
            self.assertTrue(question.blocking)
            self.assertTrue(question.question.endswith("?"))
            self.assertTrue(question.evidence)

    def test_readiness_is_certified_and_not_a_serialized_claim(self):
        self.assertFalse(self.intake.readiness.ready_for_plan)
        raw = self.intake.canonical_dict()
        raw["readiness"]["ready_for_plan"] = True
        with self.assertRaises(ValueError):
            IdeaIntake.from_dict(raw)

    def test_blocked_intake_cannot_create_project(self):
        with patch.object(ArcaDevProject, "create", side_effect=AssertionError("project construction")):
            with self.assertRaisesRegex(ValueError, "Only a ready"):
                self.intake.to_project(metadata=None)

    def test_ready_public_contract_requires_complete_separate_test_intent(self):
        # TEST FIXTURE ONLY: this is unrelated to Gaming Studio production.
        request = (
            "TEST FIXTURE ONLY. Build a web application called Test Board for editors to track tasks. "
            "Include a task list. Require SSO. Integrate with Slack. Deploy to Kubernetes."
        )
        complete = normalize_idea(request)
        self.assertTrue(complete.readiness.ready_for_plan)
        self.assertFalse(complete.readiness.blocking_requirements)
        self.assertFalse(complete.assumptions)
        with self.assertRaisesRegex(ValueError, "metadata"):
            complete.to_project(metadata=None)
        project = complete.to_project(metadata=ProjectMetadata.create(created_at="2026-01-01T00:00:00Z"))
        self.assertEqual(project.original_user_request, request)
        self.assertNotEqual(project.original_user_request, self.intent.approved_intent)
        self.assertFalse((AUTHORITY_DIRECTORY / "project.json").exists())

    def test_exact_source_binding_rejects_forged_root(self):
        with self.assertRaises(ValueError):
            production.materialize_idea(ProductionIntent(self.intent.approved_intent + " Extra."))

    def test_quote_alone_cannot_promote_excluded_feature(self):
        raw = self.intake.canonical_dict()
        raw["requested_features"].append({
            "value": "multiplayer services", "evidence": ["multiplayer services"],
            "confidence": "high", "provenance": "explicitly_stated",
        })
        forged = IdeaIntake.from_dict(raw)
        with self.assertRaisesRegex(ValueError, "reconstruction"):
            production.validate_production_idea(self.intent, forged)

    def test_removing_clarifications_cannot_gain_production_authority(self):
        raw = self.intake.canonical_dict()
        raw["unresolved_requirements"] = []
        raw["readiness"]["blocking_requirements"] = ["deployment_requirements", "platform_targets", "project_type"]
        forged = IdeaIntake.from_dict(raw)
        with self.assertRaises(ValueError):
            production.checkpoint_manifest(self.intent, forged)

    def test_review_and_checkpoint_determinism_and_persistence(self):
        for filename, builder in (("clarification_review.json", production.clarification_review),
                                  ("checkpoint.json", production.checkpoint_manifest)):
            first = canonical_bytes(builder(self.intent, self.intake))
            self.assertEqual(first, canonical_bytes(builder(self.intent, self.intake)))
            self.assertEqual(first, (AUTHORITY_DIRECTORY / filename).read_bytes())
        review = production.clarification_review(self.intent, self.intake)
        for requirement in review["unresolved_requirements"]:
            self.assertTrue(requirement["why_unresolved"])
            self.assertEqual(requirement["question"], production.CLARIFICATIONS[requirement["requirement"]][0])
        checkpoint = production.checkpoint_manifest(self.intent, self.intake)
        self.assertIsNone(checkpoint["project_id"])
        self.assertEqual(checkpoint["current_stage"], "IDEA")
        self.assertEqual(checkpoint["status"], "BLOCKED_PENDING_IDEA_CLARIFICATION")
        self.assertEqual(checkpoint["next_authorized_action"], "COLLECT_EXPLICIT_IDEA_CLARIFICATIONS")

    def test_all_five_persistent_areas_and_exclusions_are_retained(self):
        features = {value.value: value.evidence for value in self.intake.requested_features}
        for area in production.STATE_AREAS:
            self.assertIn(production.PERSISTENCE, features[area])
        constraints = {value.value for value in self.intake.explicit_constraints}
        self.assertIn(production.CONSTRAINTS[-1], constraints)
        self.assertIn(production.ORCHESTRATION, constraints)
        self.assertIn(production.ISOLATION, {value.value for value in self.intake.non_functional_requirements})

    def test_no_fixture_or_generator_imports(self):
        tree = ast.parse(Path(production.__file__).read_text(encoding="utf-8"))
        modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertEqual(modules, {"gaming_studio_intent", "idea_intake"})
        self.assertFalse(any(isinstance(node, ast.Import) for node in ast.walk(tree)))

    def test_no_project_generation_execution_network_or_application_writes(self):
        root = AUTHORITY_DIRECTORY.parents[1]
        def snapshot():
            result = {}
            for name in ("backend", "frontend", "shared"):
                for directory, dirs, files in os.walk(root / name):
                    dirs[:] = [d for d in dirs if d not in {".venv", "__pycache__", "node_modules"}]
                    for filename in files:
                        path = Path(directory) / filename
                        result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
            return result
        before = snapshot()
        with patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("execution")), \
             patch.object(ArcaDevProject, "create", side_effect=AssertionError("project")), \
             patch.object(IdeaIntake, "to_project", side_effect=AssertionError("project")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("write")), \
             patch.object(Path, "write_text", side_effect=AssertionError("write")):
            intake = production.materialize_idea(self.intent)
            production.clarification_review(self.intent, intake)
            production.checkpoint_manifest(self.intent, intake)
        self.assertEqual(before, snapshot())


if __name__ == "__main__":
    unittest.main()
