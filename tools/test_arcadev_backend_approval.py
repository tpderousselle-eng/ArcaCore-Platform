"""5.4 certification; Gaming Studio decisions are explicit TEST FIXTURES."""
from dataclasses import FrozenInstanceError, replace
from functools import lru_cache
from pathlib import Path
import hashlib
import os
import unittest
from unittest.mock import patch

from arcadev import (
    ApprovedBackend, BackendFinalization, BuildStage, ProjectStatus,
    approve_backend, reject_backend, evaluate_backend_consistency, validate_approved_backend,
)
from tools.test_arcadev_backend_clarification import resolved_backend, answer_for, fixture_choice
from tools.test_arcadev_backend_specification import backend_fixture_handoff


def source_snapshot():
    root = Path(__file__).resolve().parents[1]
    result = {}
    for name in ("backend", "frontend", "shared", "tools"):
        for directory, dirs, files in os.walk(root / name):
            dirs[:] = [d for d in dirs if d not in {".venv", "__pycache__", "node_modules"}]
            for name in files:
                p = Path(directory) / name
                result[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


@lru_cache(maxsize=1)
def approved_backend():
    state = resolved_backend()
    return approve_backend(handoff=backend_fixture_handoff(), backend=state.original_backend,
        finalization=state, approval_statement="TEST FIXTURE ONLY: I explicitly approve the Gaming Studio backend.")


class BackendApprovalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = backend_fixture_handoff()
        cls.state = resolved_backend()
        cls.backend = cls.state.original_backend
        cls.approved = approved_backend()

    def approve(self, **changes):
        args = dict(handoff=self.handoff, backend=self.backend, finalization=self.state, approval_statement="Explicitly approved.")
        args.update(changes)
        return approve_backend(**args)

    def test_gaming_studio_explicit_approval(self):
        self.assertEqual(len(self.state.decisions), 10)
        self.assertTrue(self.approved.approved)
        self.assertTrue(self.approved.package.consistency.consistent)
        self.assertFalse(self.state.unresolved_questions)
        self.assertFalse(self.state.conflicts)
        self.assertEqual(self.approved.schema, "arcadev.approved_backend")
        self.assertEqual(self.approved.schema_version, 1)

    def test_readiness_is_not_approval(self):
        self.assertTrue(self.state.effective_ready_for_approval)
        self.assertFalse(hasattr(self.state, "approved"))
        for statement in (None, "", "   "):
            with self.assertRaises(ValueError): self.approve(approval_statement=statement)
        with self.assertRaises(TypeError):
            approve_backend(handoff=self.handoff, backend=self.backend, finalization=self.state)

    def test_rejection_preserves_sources(self):
        result = reject_backend(handoff=self.handoff, backend=self.backend, finalization=self.state, approval_statement="Rejected.")
        self.assertFalse(result.approved)
        self.assertTrue(result.approval_eligible)
        self.assertEqual(result.package.backend_finalization, self.state)
        self.assertEqual(result.package.original_backend, self.backend)
        self.assertEqual(result, ApprovedBackend.from_json(result.canonical_json()))

    def test_unresolved_blockers(self):
        start = BackendFinalization.start(self.backend, handoff=self.handoff)
        result = evaluate_backend_consistency(self.handoff, self.backend, start)
        self.assertFalse(result.consistent)
        with self.assertRaises(ValueError): self.approve(finalization=start)

    def test_active_conflict_and_unsupported_scope(self):
        start = BackendFinalization.start(self.backend, handoff=self.handoff)
        q = start.unresolved_questions[0]
        state = start.resolve(answer_for(start, q, raw="Add billing and subscriptions; " + fixture_choice(q)[0]), handoff=self.handoff)
        self.assertTrue(state.conflicts)
        with self.assertRaises(ValueError): self.approve(finalization=state)

    def test_forged_finalization_history_and_claim(self):
        for state in (replace(self.state, history=()), replace(self.state, decisions=()),
                      replace(self.state, finalization_id="forged")):
            with self.assertRaises(ValueError): self.approve(finalization=state)

    def test_forged_backend_id(self):
        with self.assertRaises(ValueError): self.approve(backend=replace(self.backend, backend_id="forged"))

    def test_invalid_component_and_binding_references(self):
        component = self.backend.components[0]
        for backend in (
            replace(self.backend, components=(replace(component, owned_capabilities=("new_scope",)),) + self.backend.components[1:]),
            replace(self.backend, data_bindings=(replace(self.backend.data_bindings[0], component_id="missing"),) + self.backend.data_bindings[1:]),
            replace(self.backend, resolved_model=replace(self.backend.resolved_model, entities=())),
        ):
            with self.assertRaises(ValueError): self.approve(backend=backend)

    def test_missing_authorization_and_invalid_operation_model(self):
        operation = next(o for o in self.backend.operations if o.authorization_ids)
        for changes in ({"authorization_ids": ()}, {"output_entity_ids": ("missing",)}):
            backend = replace(self.backend, operations=tuple(replace(o, **changes) if o == operation else o for o in self.backend.operations))
            with self.assertRaises(ValueError): self.approve(backend=backend)

    def test_contradictory_claim_forgery(self):
        decision = self.state.decisions[0]
        claim = replace(decision.claims[0], values=("invented",))
        forged = replace(decision, claims=(claim,))
        with self.assertRaises(ValueError):
            self.approve(finalization=replace(self.state, decisions=(forged,) + self.state.decisions[1:]))

    def test_stale_complete_handoff_content(self):
        stale = replace(self.handoff, source_project_id="different")
        with self.assertRaises(ValueError): validate_approved_backend(self.approved, handoff=stale)

    def test_stale_complete_backend_content(self):
        stale = replace(self.backend, components=())
        with self.assertRaises(ValueError): validate_approved_backend(self.approved, backend=stale)

    def test_stale_complete_finalization_content(self):
        stale = replace(self.state, history=())
        with self.assertRaises(ValueError): validate_approved_backend(self.approved, finalization=stale)

    def test_deterministic_identity_and_round_trip(self):
        self.assertEqual(self.approve(), self.approve())
        self.assertNotEqual(self.approve().approval_id, self.approve(approval_statement="Another explicit approval.").approval_id)
        self.assertEqual(self.approved, ApprovedBackend.from_json(self.approved.canonical_json()))
        self.assertEqual(self.approved, validate_approved_backend(self.approved, handoff=self.handoff,
            backend=self.backend, finalization=self.state, source_project=self.handoff.resulting_project))

    def test_immutable_package(self):
        with self.assertRaises(FrozenInstanceError): self.approved.package.original_backend = None
        raw = self.approved.canonical_dict()
        raw["package"]["resolved_backend"]["components"].clear()
        self.assertTrue(self.approved.package.resolved_backend.components)

    def test_exact_provenance_and_frozen_structure(self):
        view = self.approved.package.resolved_backend
        self.assertEqual({(c.decision_id, c.question_id, c.claim) for c in view.accepted_choices},
            {(d.decision_id, d.question_id, c) for d in self.state.decisions for c in d.claims})
        for name in ("components", "data_bindings", "operations", "policies"):
            self.assertEqual(getattr(view, name), getattr(self.backend, name))
        self.assertEqual(self.approved.package.backend_finalization.history, self.state.history)

    def test_reconstruct_consistency_and_resolved_authority(self):
        self.assertEqual(self.approved.package.consistency, evaluate_backend_consistency(self.handoff, self.backend, self.state))
        for key in ("consistency", "resolved_backend"):
            raw = self.approved.canonical_dict(); raw["package"][key] = {}
            with self.assertRaises(ValueError): ApprovedBackend.from_dict(raw)

    def test_credentials_forbidden(self):
        for statement in ("password=super-secret-value", "ghp_" + "a" * 36):
            with self.assertRaises(ValueError): self.approve(approval_statement=statement)

    def test_malformed_envelope(self):
        for changes in ({"approved": False}, {"schema_version": 2}, {"schema_version": True}, {"extra": 1}):
            raw = self.approved.canonical_dict(); raw.update(changes)
            with self.assertRaises(ValueError): ApprovedBackend.from_dict(raw)
        with self.assertRaises(ValueError): ApprovedBackend.from_json('{"schema":1,"schema":2}')

    def test_backend_stage_no_generation_or_artifacts(self):
        before = source_snapshot()
        with patch("tools.generate.generate_module", side_effect=AssertionError("No generation")):
            result = self.approve()
        project = result.package.models_backend_handoff.resulting_project
        self.assertEqual(project.current_build_stage, BuildStage.BACKEND)
        self.assertEqual(project.project_status, ProjectStatus.IN_PROGRESS)
        self.assertEqual(before, source_snapshot())
        with self.assertRaises(ValueError): self.approve(source_project=replace(project, current_build_stage=BuildStage.FRONTEND))


if __name__ == "__main__":
    unittest.main()
