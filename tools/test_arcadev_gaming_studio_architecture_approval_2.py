"""Production handoff certification: exact approved sources and strict MODELS stop."""

from contextlib import ExitStack
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from arcadev.architecture_approval import reject_architecture
from arcadev.architecture_models_handoff import ArchitectureModelsHandoff, validate_architecture_models_handoff
from arcadev.gaming_studio_architecture_approval import APPROVAL_AREA
from arcadev.gaming_studio_architecture_transition import validate_architecture_transition_state
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY
from arcadev.project import BuildStage, ProjectStatus


class ProductionArchitectureTransitionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = ArchitectureModelsHandoff.from_json((AUTHORITY_DIRECTORY / APPROVAL_AREA /
            "architecture_models_handoff.json").read_text(encoding="utf-8"))
        cls.approved = cls.handoff.frozen_approved_architecture
        cls.package = cls.approved.package
        cls.source = cls.package.plan_handoff.resulting_project

    def transition(self, **changes):
        args = dict(source_project=self.source, approved_architecture=self.approved,
            handoff=self.package.plan_handoff, architecture=self.package.original_architecture,
            finalization=self.package.architecture_finalization)
        args.update(changes)
        return ArchitectureModelsHandoff.create(**args)

    def test_full_production_replay_source_history_and_no_domain_model(self):
        before = {p.relative_to(AUTHORITY_DIRECTORY): p.read_bytes() for p in AUTHORITY_DIRECTORY.rglob("*") if p.is_file()}
        with ExitStack() as stack:
            for target in ("arcadev.domain_model_engine.generate_baseline_domain_model",
                    "arcadev.domain_model_specification.DomainModelSpecification.create",
                    "arcadev.model_approval.approve_domain_model",
                    "subprocess.Popen", "socket.socket", "builtins.eval", "os.system",
                    "pathlib.Path.write_bytes", "pathlib.Path.write_text"):
                stack.enter_context(patch(target, side_effect=AssertionError(target)))
            self.assertEqual(validate_architecture_transition_state(), self.handoff)
        self.assertEqual(before, {p.relative_to(AUTHORITY_DIRECTORY): p.read_bytes() for p in AUTHORITY_DIRECTORY.rglob("*") if p.is_file()})
        self.assertEqual(self.source.current_build_stage, BuildStage.ARCHITECTURE)
        self.assertEqual(self.source.project_status, ProjectStatus.IN_PROGRESS)
        source_raw = (AUTHORITY_DIRECTORY / "production_plan/plan_approval/project.json").read_bytes()
        self.assertEqual(source_raw, self.source.canonical_json().encode())
        self.assertFalse(any("domain_model" in p.name for p in AUTHORITY_DIRECTORY.rglob("*")))

    def test_eligibility_warning_exact_binding_and_result(self):
        h, a = self.handoff, self.approved
        self.assertTrue(a.approved and a.approval_eligible and a.package.consistency.consistent)
        self.assertTrue(a.effective_ready_for_approval)
        self.assertEqual(a.decision.value, "approved")
        self.assertEqual([w.code for w in a.package.consistency.warnings], ["implementation_compatibility_not_proven"])
        self.assertEqual(a.package.architecture_finalization.unresolved_questions, ())
        self.assertEqual(a.package.architecture_finalization.conflicts, ())
        self.assertTrue(h.transition_eligible)
        self.assertEqual(h.decision.value, "transitioned")
        self.assertEqual(h.approved_architecture_id, a.approval_id)
        self.assertEqual(h.source_project_id, self.source.project_id)
        self.assertEqual(h.resulting_project.project_id, self.source.project_id)
        self.assertEqual(h.resulting_project.current_build_stage, BuildStage.MODELS)
        self.assertEqual(h.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        self.assertEqual(replace(h.resulting_project, current_build_stage=BuildStage.ARCHITECTURE), self.source)
        self.assertEqual(json.loads((AUTHORITY_DIRECTORY / APPROVAL_AREA / "project.json").read_bytes()), h.resulting_project.canonical_dict())

    def test_deterministic_identity_and_public_canonical_roundtrip(self):
        self.assertEqual(self.transition(), self.handoff)
        self.assertEqual(ArchitectureModelsHandoff.from_json(self.handoff.canonical_json()), self.handoff)
        self.assertEqual(validate_architecture_models_handoff(self.handoff, source_project=self.source,
            approved_architecture=self.approved, handoff=self.package.plan_handoff,
            architecture=self.package.original_architecture, finalization=self.package.architecture_finalization), self.handoff)

    def test_modified_approval_stale_source_and_wrong_bindings_rejected(self):
        for changes in (
                dict(approved_architecture=replace(self.approved, approval_statement="Changed.")),
                dict(approved_architecture=replace(self.approved, approval_eligible=False)),
                dict(approved_architecture=replace(self.approved, approved=False)),
                dict(source_project=self.handoff.resulting_project),
                dict(source_project=replace(self.source, project_id="stale")),
                dict(source_project=replace(self.source, project_status=ProjectStatus.BLOCKED)),
                dict(finalization=replace(self.package.architecture_finalization, finalization_id="stale"))):
            with self.subTest(changes=tuple(changes)), self.assertRaises(ValueError):
                self.transition(**changes)

    def test_rejected_architecture_cannot_transition(self):
        rejected = reject_architecture(handoff=self.package.plan_handoff,
            architecture=self.package.original_architecture, finalization=self.package.architecture_finalization,
            source_project=self.source, approval_statement="Rejected for test review.")
        with self.assertRaises(ValueError):
            self.transition(approved_architecture=rejected)


if __name__ == "__main__":
    unittest.main()
