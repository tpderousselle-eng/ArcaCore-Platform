"""Canonical first production plan and frozen-IDEA-only provenance."""

from contextlib import ExitStack
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcadev.gaming_studio_authority import validate_production_authority
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, parse_authority
from arcadev.gaming_studio_plan import production_plan_inputs, production_software_plan
from arcadev.planning_engine import generate_baseline_plan, validate_plan_candidate
from arcadev.software_plan import SoftwarePlan, validate_software_plan_candidate


class ProductionPlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = production_plan_inputs()
        cls.plan = production_software_plan()

    def test_complete_lineage_and_exact_identity(self):
        self.assertTrue(validate_production_authority(require_current=True)["valid"])
        self.assertEqual(self.handoff.handoff_id, "arcadev_handoff_2d8411540b13ce1eecd8c480e0f5a692")
        self.assertEqual(self.plan.handoff_id, self.handoff.handoff_id)
        self.assertEqual(self.plan.project_id, "arcadev_969321c8959864fe18393b9d2b551063")
        self.assertEqual(self.plan.project_stage.value, "PLAN")
        self.assertEqual(self.handoff.resulting_project.current_build_stage.value, "PLAN")
        self.assertEqual(self.plan.plan_id, "arcadev_plan_9aed1a01dad6e95cb75b6db67730dd5b")

    def test_public_baseline_determinism_and_canonical_roundtrip(self):
        plan = self.plan
        self.assertEqual(plan, generate_baseline_plan(self.handoff))
        self.assertEqual(plan, SoftwarePlan.from_dict(plan.canonical_dict(), handoff=self.handoff))
        self.assertEqual(plan, SoftwarePlan.from_json(plan.canonical_json(), handoff=self.handoff))
        self.assertEqual(plan, validate_software_plan_candidate(plan, handoff=self.handoff))
        self.assertEqual(plan, validate_plan_candidate(self.handoff, plan))
        self.assertEqual(plan.canonical_json().encode(),
                         (AUTHORITY_DIRECTORY / "production_plan/software_plan.json").read_bytes())

    def test_every_source_is_frozen_idea_and_no_future_scope_or_assumptions(self):
        intake = self.handoff.snapshot.intake
        approved = {intake.original_user_request}
        for value in vars(intake).values():
            if hasattr(value, "value"):
                approved.add(value.value)
            elif isinstance(value, tuple):
                approved.update(item.value for item in value if hasattr(item, "value"))
        def walk(value):
            if isinstance(value, dict):
                if "source_requirements" in value:
                    self.assertTrue(set(value["source_requirements"]) <= approved)
                if "provenance" in value:
                    self.assertIn(value["provenance"], ("approved_idea", "deterministic_planning_derivation"))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(self.plan.canonical_dict())
        self.assertEqual(self.plan.assumptions, ())
        text = self.plan.canonical_json().casefold()
        for future in ("arcacreator marketplace", "arcaip guard", "studio transfer", "mature content framework", "community", "showcase"):
            self.assertNotIn(future, text)

    def test_blockers_preserve_all_matching_feature_sources(self):
        for keyword, phrase in (("asset", "asset storage"), ("build", "build execution"), ("publish", "publishing targets")):
            question = next(q for q in self.plan.open_planning_questions if phrase in q.question)
            sources = {item.value for item in self.handoff.snapshot.intake.requested_features if keyword in item.value.casefold()}
            self.assertEqual(set(question.source_requirements), sources)
            self.assertTrue(question.blocking)
        self.assertFalse(self.plan.readiness.ready_for_architecture)
        self.assertEqual(self.plan.readiness.blocking_reasons, ("blocking_planning_questions",))
        candidate = self.plan.canonical_dict()
        candidate["readiness"]["ready_for_architecture"] = True
        with self.assertRaises(ValueError):
            validate_plan_candidate(self.handoff, candidate)

    def test_altered_upstream_cannot_supply_planning_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "authority"
            shutil.copytree(AUTHORITY_DIRECTORY, directory)
            path = directory / "idea_resolution/project.json"
            value = parse_authority(path.read_bytes())
            from arcadev.gaming_studio_intent import canonical_bytes
            value["current_build_stage"] = "ARCHITECTURE"
            path.write_bytes(canonical_bytes(value))
            with self.assertRaises(ValueError):
                production_software_plan(directory)

    def test_no_answers_approval_transition_execution_network_or_writes(self):
        from arcadev import plan_clarification, plan_approval, plan_architecture_handoff, backend_generation
        from tools import generate
        with ExitStack() as stack:
            for owner, name in ((plan_clarification.PlanFinalization, "start"),
                                (plan_clarification.PlanningDecision, "create"),
                                (plan_clarification.PlanClarificationAnswer, "create"),
                                (plan_approval.ApprovedPlan, "create"),
                                (plan_architecture_handoff.PlanArchitectureHandoff, "create"),
                                (backend_generation, "generate_backend"), (generate, "generate_module"),
                                (socket, "socket"), (subprocess, "Popen"),
                                (Path, "write_bytes"), (Path, "write_text")):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            self.assertEqual(production_software_plan(), self.plan)


if __name__ == "__main__":
    unittest.main()
