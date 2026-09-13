"""Refinement 3 certification. All Gaming Studio authority is TEST FIXTURE ONLY."""
from dataclasses import replace
from functools import lru_cache
import unittest
from unittest.mock import patch

from arcadev import (
    ApprovedDomainModelRevision, DownstreamAuthorityInvalidation, approve_domain_model_revision,
    reject_domain_model_revision, evaluate_model_revision_consistency, validate_approved_domain_model_revision,
    ModelAmendmentRequest, ModelAmendmentFinalization, ArcaCoreGenerationRequest, BuildStage,
)
from arcadev.backend_generation import BackendGenerationRun, GenerationDisposition
from arcadev.backend_approval import ApprovedBackend
from tools.test_arcadev_model_amendment_finalization import fixture_finalization, fixture_answer
from tools.test_arcadev_model_amendment_request import fixture_request
from tools.test_arcadev_backend_approval import approved_backend
from tools.fixture_arcadev_module_backend import minimal_approved_backend


@lru_cache(maxsize=1)
def fixture_revision():
    request = fixture_request()
    return approve_domain_model_revision(parent=request.parent, request=request, finalization=fixture_finalization(),
        approval_statement="TEST FIXTURE ONLY: I explicitly approve this complete logical model revision.")


@lru_cache(maxsize=1)
def fixture_downstream():
    approved = approved_backend()
    request = ArcaCoreGenerationRequest.create(approved)
    # Construct only inert evidence of an incompatible historical TEST FIXTURE.
    # No generator entrypoint or subprocess is invoked to create this record.
    run = BackendGenerationRun._build(request, GenerationDisposition.BLOCKED_INCOMPATIBLE)
    return dict(models_backend_handoff=approved.package.models_backend_handoff,
        backend_specification=approved.package.original_backend,
        backend_finalization=approved.package.backend_finalization,
        approved_backend=approved, generation_request=request, generation_run=run)


class ModelRevisionApprovalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = fixture_request()
        cls.complete = fixture_finalization()
        cls.revision = fixture_revision()

    def approve(self, **changes):
        args = dict(parent=self.request.parent, request=self.request, finalization=self.complete,
            approval_statement="TEST FIXTURE ONLY: approve revised logical state.")
        args.update(changes)
        return approve_domain_model_revision(**args)

    def test_explicit_approval_and_complete_frozen_package(self):
        r = self.revision
        self.assertTrue(r.approved and r.approval_eligible and r.effective_ready_for_approval)
        self.assertTrue(r.package.consistency.consistent)
        self.assertEqual(r.package.parent, self.request.parent)
        self.assertEqual(r.package.amendment_request, self.request)
        self.assertEqual(r.package.amendment_finalization, self.complete)
        self.assertEqual(len(r.package.revised_model.amendment_decisions), 14)

    def test_entity_ids_ownership_and_original_choices_preserved(self):
        original = self.request.parent.package.resolved_model
        revised = self.revision.package.revised_model
        self.assertEqual([e.entity_id for e in revised.entities], [e.entity_id for e in original.entities])
        for before, after in zip(original.entities, revised.entities):
            self.assertEqual((before.name, before.owned_capabilities, before.architecture_source_requirements, before.choices),
                (after.name, after.owned_capabilities, after.architecture_source_requirements, after.choices))
        self.assertEqual((original.relationships, original.constraints, original.access_requirements),
            (revised.relationships, revised.constraints, revised.access_requirements))

    def test_fields_identity_and_lifecycle_bindings(self):
        revised = self.revision.package.revised_model
        self.assertEqual(sum(len(e.approved_fields) for e in revised.entities), 14)
        self.assertEqual(sum(len(e.identity_field_ids) for e in revised.entities), 5)
        self.assertEqual(sum(len(e.lifecycle_domain_ids) for e in revised.entities), 2)
        self.assertEqual(len(revised.value_domains), 2)
        for entity in revised.entities:
            self.assertEqual(len(entity.identity_field_ids), 1)
            self.assertTrue(set(entity.identity_field_ids) <= {f.field_id for f in entity.approved_fields})
        self.assertEqual({f.field_id for e in revised.entities for f in e.approved_fields}, {d.field.field_id for d in self.complete.decisions})

    def test_parent_history_is_immutable(self):
        before = self.request.parent.canonical_json()
        self.approve()
        self.assertEqual(before, self.request.parent.canonical_json())
        self.assertTrue(all(not e.approved_fields for e in self.request.parent.package.resolved_model.entities))

    def test_existing_nonempty_parent_fields_are_preserved(self):
        parent = minimal_approved_backend().package.models_backend_handoff.frozen_approved_domain_model
        request = ModelAmendmentRequest.create(parent)
        state = ModelAmendmentFinalization.start(request)
        # A rejection still freezes the complete unchanged source view. It does
        # not require inventing amendments when the source needs none.
        revision = reject_domain_model_revision(parent=parent, request=request, finalization=state,
            approval_statement="TEST FIXTURE ONLY: reject this incomplete or unnecessary amendment.")
        self.assertTrue(any(e.approved_fields for e in parent.package.resolved_model.entities))
        for old, new in zip(parent.package.resolved_model.entities, revision.package.revised_model.entities):
            self.assertEqual({f.field_id: f for f in old.approved_fields}, {f.field_id: f for f in new.approved_fields})
            self.assertEqual(old.identity_field_ids, new.identity_field_ids)

    def test_determinism_and_statement_identity(self):
        self.assertEqual(self.approve(), self.approve())
        one = self.approve(approval_statement="TEST FIXTURE ONLY: another explicit approval statement.")
        self.assertNotEqual(one.revision_id, self.revision.revision_id)
        self.assertEqual(one.package.revised_model, self.revision.package.revised_model)

    def test_readiness_does_not_approve_and_incomplete_cannot_approve(self):
        self.assertTrue(self.complete.effective_ready_for_approval)
        self.assertFalse(hasattr(self.complete, "approved"))
        initial = ModelAmendmentFinalization.start(self.request)
        self.assertFalse(evaluate_model_revision_consistency(parent=self.request.parent, request=self.request, finalization=initial).consistent)
        with self.assertRaises(ValueError): self.approve(finalization=initial)
        with self.assertRaises(ValueError): self.approve(approval_statement=" ")

    def test_explicit_rejection(self):
        rejected = reject_domain_model_revision(parent=self.request.parent, request=self.request, finalization=self.complete,
            approval_statement="TEST FIXTURE ONLY: I reject this revision.")
        self.assertFalse(rejected.approved)
        self.assertTrue(rejected.approval_eligible)
        self.assertEqual(rejected, ApprovedDomainModelRevision.from_json(rejected.canonical_json()))

    def test_stale_parent_request_and_finalization_rejected(self):
        with self.assertRaises(ValueError): self.approve(parent=replace(self.request.parent, approval_statement="stale"))
        with self.assertRaises(ValueError): self.approve(request=replace(self.request, request_id="stale"))
        with self.assertRaises(ValueError): self.approve(finalization=replace(self.complete, history=()))
        with self.assertRaises(ValueError): validate_approved_domain_model_revision(self.revision, finalization=ModelAmendmentFinalization.start(self.request))

    def test_forged_revised_model_and_consistency_rejected(self):
        for section, key, value in (("revised_model", "entities", []), ("revised_model", "value_domains", []),
                ("revised_model", "amendment_decisions", []), ("consistency", "consistent", False)):
            raw = self.revision.canonical_dict()
            raw["package"][section][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): ApprovedDomainModelRevision.from_dict(raw)
        raw = self.revision.canonical_dict()
        raw["package"]["revised_model"]["entities"][0]["entity_id"] = "new_entity"
        with self.assertRaises(ValueError): ApprovedDomainModelRevision.from_dict(raw)

    def test_canonical_roundtrip_and_malformed_envelopes(self):
        self.assertEqual(self.revision, validate_approved_domain_model_revision(self.revision.canonical_json(),
            parent=self.request.parent, request=self.request, finalization=self.complete))
        for changes in ({"schema_version": True}, {"schema": "unknown"}, {"approved": False}, {"provider": "untrusted"}):
            raw = self.revision.canonical_dict()
            raw.update(changes)
            with self.assertRaises(ValueError): ApprovedDomainModelRevision.from_dict(raw)
        for text in ('{', '{"x":1,"x":2}', ' ' * 5_000_001):
            with self.assertRaises(ValueError): ApprovedDomainModelRevision.from_json(text)

    def test_no_backend_rebuild_or_generator_call(self):
        with patch("arcadev.models_backend_handoff.ModelsBackendHandoff.create", side_effect=AssertionError("No handoff")), patch(
                "arcadev.backend_engine.generate_baseline_backend_specification", side_effect=AssertionError("No rebuild")), patch(
                "arcadev.backend_generation.generate_backend", side_effect=AssertionError("No generation")):
            self.assertTrue(self.approve().approved)


class DownstreamAuthorityInvalidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.revision = fixture_revision()
        cls.downstream = fixture_downstream()
        cls.record = DownstreamAuthorityInvalidation.create(cls.revision, **cls.downstream)

    def test_all_six_exact_stale_bindings(self):
        self.assertEqual(len(self.record.reason_codes), 7)
        self.assertIn("approved_domain_model_superseded", self.record.reason_codes)
        for name, value in self.downstream.items():
            with self.subTest(name=name):
                self.assertEqual(getattr(self.record, name).canonical_json(), value.canonical_json())
                self.assertIn(name + "_stale", self.record.reason_codes)

    def test_only_supplied_contracts_receive_reasons(self):
        parent_only = DownstreamAuthorityInvalidation.create(self.revision)
        self.assertEqual(parent_only.reason_codes, ("approved_domain_model_superseded",))
        for name in ("models_backend_handoff", "approved_backend", "generation_request", "generation_run"):
            record = DownstreamAuthorityInvalidation.create(self.revision, **{name: self.downstream[name]})
            self.assertEqual(set(record.reason_codes), {"approved_domain_model_superseded", name + "_stale"})
        for name in ("backend_specification", "backend_finalization"):
            with self.assertRaises(ValueError): DownstreamAuthorityInvalidation.create(self.revision, **{name: self.downstream[name]})
            record = DownstreamAuthorityInvalidation.create(self.revision,
                models_backend_handoff=self.downstream["models_backend_handoff"], **{name: self.downstream[name]})
            self.assertEqual(len(record.reason_codes), 3)

    def test_deterministic_roundtrip(self):
        self.assertEqual(self.record, DownstreamAuthorityInvalidation.create(self.revision, **self.downstream))
        self.assertEqual(self.record, DownstreamAuthorityInvalidation.from_json(self.record.canonical_json(), revision=self.revision))

    def test_unrelated_downstream_rejected(self):
        other = minimal_approved_backend()
        with self.assertRaises(ValueError): DownstreamAuthorityInvalidation.create(self.revision, approved_backend=other)
        with self.assertRaises(ValueError): DownstreamAuthorityInvalidation.create(self.revision,
            models_backend_handoff=self.downstream["models_backend_handoff"], approved_backend=other)

    def test_forged_downstream_rejected(self):
        for name, obj in self.downstream.items():
            raw = self.record.canonical_dict()
            key = next(key for key in obj.canonical_dict() if key.endswith("_id"))
            raw[name][key] = "forged"
            with self.subTest(name=name), self.assertRaises(ValueError): DownstreamAuthorityInvalidation.from_dict(raw)

    def test_rejected_revision_cannot_invalidate(self):
        request = fixture_request()
        rejected = reject_domain_model_revision(parent=request.parent, request=request, finalization=fixture_finalization(),
            approval_statement="TEST FIXTURE ONLY: reject revision.")
        with self.assertRaises(ValueError): DownstreamAuthorityInvalidation.create(rejected, **self.downstream)
        with self.assertRaises(ValueError): DownstreamAuthorityInvalidation.from_json(self.record.canonical_json(), revision=rejected)

    def test_forged_invalidation_reasons_and_schema(self):
        for changes in ({"reason_codes": []}, {"stale_for_future_execution": False}, {"schema_version": 2},
                {"parent_approval_id": "other"}, {"provider": "untrusted"}):
            raw = self.record.canonical_dict()
            raw.update(changes)
            with self.assertRaises(ValueError): DownstreamAuthorityInvalidation.from_dict(raw)

    def test_future_execution_guard_fails_closed(self):
        for name, authority in self.downstream.items():
            with self.assertRaisesRegex(ValueError, "stale for future execution"):
                self.record.assert_current(name, authority)
        with self.assertRaises(ValueError): self.record.assert_current("unknown", self.downstream["generation_request"])
        with self.assertRaises(ValueError): self.record.assert_current("approved_backend", minimal_approved_backend())

    def test_history_and_project_stage_unchanged_without_rebuild(self):
        before = {name: value.canonical_json() for name, value in self.downstream.items()}
        with patch("arcadev.models_backend_handoff.ModelsBackendHandoff.create", side_effect=AssertionError("No handoff")), patch(
                "arcadev.backend_generation.generate_backend", side_effect=AssertionError("No generation")):
            DownstreamAuthorityInvalidation.create(self.revision, **self.downstream)
        self.assertEqual(before, {name: value.canonical_json() for name, value in self.downstream.items()})
        self.assertEqual(self.downstream["models_backend_handoff"].resulting_project.current_build_stage, BuildStage.BACKEND)
        self.assertEqual(self.revision.package.parent.package.architecture_handoff.resulting_project.current_build_stage, BuildStage.MODELS)
        self.assertTrue(ApprovedBackend.from_json(self.downstream["approved_backend"].canonical_json()).approved)
        request = self.downstream["generation_request"]
        self.assertEqual((len(request.blocking_findings), len(request.unsupported_mappings), len(request.required_certification_mappings)), (57, 6, 51))
        self.assertFalse(request.module_requests)
        self.assertEqual(self.downstream["generation_run"].invocation_count, 0)


if __name__ == "__main__":
    unittest.main()
