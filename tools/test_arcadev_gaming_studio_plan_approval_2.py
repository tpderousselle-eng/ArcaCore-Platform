"""Exact production source and approved-plan binding through the public gate."""

from contextlib import ExitStack
from dataclasses import replace
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcadev import (
    ApprovedPlan, BuildStage, PlanArchitectureHandoff, PlanFinalization,
    ProjectStatus, reject_plan,
)
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes
from arcadev.gaming_studio_plan_approval import APPROVAL_AREA, APPROVAL_STATEMENT
from arcadev.gaming_studio_plan_transition import (
    PLAN_TRANSITION_FILES, production_plan_transition_state, validate_plan_transition_state,
)


class ProductionPlanTransitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.area = AUTHORITY_DIRECTORY / APPROVAL_AREA
        cls.approved = ApprovedPlan.from_json((cls.area / "approved_plan.json").read_text(encoding="utf-8"))
        cls.source = cls.approved.package.idea_handoff.resulting_project
        cls.handoff = PlanArchitectureHandoff.from_json((cls.area / "plan_architecture_handoff.json").read_text(encoding="utf-8"))

    def test_public_prerequisites_and_result(self):
        self.assertEqual(self.source.current_build_stage, BuildStage.PLAN)
        self.assertEqual(self.source.project_status, ProjectStatus.IN_PROGRESS)
        self.assertIs(self.approved.approved, True)
        self.assertIs(self.approved.approval_eligible, True)
        self.assertIs(self.approved.effective_ready_for_architecture, True)
        self.assertIs(self.approved.package.consistency.consistent, True)
        finalization = self.approved.package.plan_finalization
        self.assertEqual(finalization.unresolved_questions, ())
        self.assertEqual(finalization.conflicts, ())
        self.assertIs(self.handoff.transition_eligible, True)
        self.assertEqual(self.handoff.decision.value, "transitioned")
        self.assertEqual(self.handoff.resulting_project.current_build_stage, BuildStage.ARCHITECTURE)
        self.assertEqual(self.handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        self.assertEqual(self.handoff.resulting_project.project_id, self.source.project_id)
        self.assertEqual(self.handoff.frozen_approved_plan, self.approved)
        self.assertEqual(self.handoff.approved_plan_id, self.approved.approval_id)
        self.assertEqual(self.handoff.source_project_id, self.source.project_id)

    def test_deterministic_public_handoff_and_canonical_roundtrip(self):
        replay = PlanArchitectureHandoff.create(source_project=self.source, approved_plan=self.approved)
        self.assertEqual(replay, self.handoff)
        self.assertEqual(replay.handoff_id, self.handoff.handoff_id)
        self.assertEqual(PlanArchitectureHandoff.from_json(replay.canonical_json()), replay)
        self.assertEqual(replay.canonical_json().encode("utf-8"), (self.area / "plan_architecture_handoff.json").read_bytes())

    def test_complete_production_transition_replay(self):
        self.assertEqual(validate_plan_transition_state(), self.handoff)
        self.assertEqual(self.handoff.resulting_project.canonical_json().encode("utf-8"), (self.area / "project.json").read_bytes())

    def test_source_is_immutable_plan_history(self):
        before = (AUTHORITY_DIRECTORY / "idea_resolution/project.json").read_bytes()
        self.assertEqual(before, self.source.canonical_json().encode("utf-8"))
        PlanArchitectureHandoff.create(source_project=self.source, approved_plan=self.approved)
        self.assertEqual(before, (AUTHORITY_DIRECTORY / "idea_resolution/project.json").read_bytes())
        self.assertEqual(self.source.current_build_stage, BuildStage.PLAN)
        self.assertEqual(replace(self.handoff.resulting_project, current_build_stage=BuildStage.PLAN), self.source)

    def test_stale_or_wrong_source_stage_status_metadata_and_identity_rejected(self):
        for candidate in (
                replace(self.source, current_build_stage=BuildStage.ARCHITECTURE),
                replace(self.source, project_status=ProjectStatus.BLOCKED),
                replace(self.source, project_id="arcadev_" + "0" * 32),
                replace(self.source, metadata=replace(self.source.metadata, updated_at="2099-01-01T00:00:00Z"))):
            with self.subTest(source=candidate), self.assertRaises(ValueError):
                PlanArchitectureHandoff.create(source_project=candidate, approved_plan=self.approved)

    def test_modified_approved_plan_and_forged_handoff_rejected(self):
        for candidate in (replace(self.approved, approval_eligible=False),
                          replace(self.approved, approval_statement="Approve a different plan."),
                          replace(self.approved, approved=False)):
            with self.assertRaises(ValueError):
                PlanArchitectureHandoff.create(source_project=self.source, approved_plan=candidate)
        for field, value in (("transition_eligible", False), ("approved_plan_id", self.approved.approval_id + "0"),
                              ("source_project_id", self.source.project_id + "0"), ("handoff_id", self.handoff.handoff_id + "0")):
            candidate = self.handoff.canonical_dict()
            candidate[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                PlanArchitectureHandoff.from_dict(candidate)

    def test_rejected_and_ineligible_plans_cannot_transition_even_with_forged_flags(self):
        idea = self.approved.package.idea_handoff
        resolved = self.approved.package.plan_finalization
        initial = PlanFinalization.start(resolved.original_plan, handoff=idea)
        for finalization in (resolved, initial):
            rejected = reject_plan(handoff=idea, finalization=finalization, approval_statement=APPROVAL_STATEMENT)
            self.assertFalse(rejected.approved)
            self.assertEqual(rejected.approval_eligible, finalization is resolved)
            for candidate in (rejected, replace(rejected, approved=True, approval_eligible=True)):
                with self.assertRaises(ValueError):
                    PlanArchitectureHandoff.create(source_project=self.source, approved_plan=candidate)

    def test_persisted_modified_approval_and_source_rejected(self):
        with tempfile.TemporaryDirectory(prefix="gaming-plan-transition-") as temporary:
            root = Path(temporary) / "authority"
            shutil.copytree(AUTHORITY_DIRECTORY, root)
            for relative in (APPROVAL_AREA + "/approved_plan.json", "idea_resolution/project.json"):
                path = root / relative
                original = path.read_bytes()
                candidate = json.loads(original)
                candidate["unapproved"] = True
                path.write_bytes(canonical_bytes(candidate))
                try:
                    with self.assertRaises(ValueError):
                        production_plan_transition_state(root)
                finally:
                    path.write_bytes(original)

    def test_transition_stops_without_architecture_generation_execution_network_or_writes(self):
        from arcadev import architecture_engine, domain_model_engine, backend_generation
        from tools import generate
        with ExitStack() as stack:
            for owner, name in ((architecture_engine, "generate_baseline_architecture"),
                    (domain_model_engine, "generate_baseline_domain_model"),
                    (backend_generation, "generate_backend"), (generate, "generate_module"),
                    (socket, "socket"), (subprocess, "Popen"), (Path, "write_bytes"), (Path, "write_text")):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            result = production_plan_transition_state()
        self.assertEqual(set(result), PLAN_TRANSITION_FILES)
        self.assertFalse((self.area / "architecture_specification.json").exists())
        self.assertFalse((self.area / "approved_architecture.json").exists())
        self.assertFalse((self.area / "architecture_models_handoff.json").exists())


if __name__ == "__main__":
    unittest.main()
