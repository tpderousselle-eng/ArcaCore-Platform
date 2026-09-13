"""5.5 public capability certification; no generator is invoked."""
from dataclasses import FrozenInstanceError, replace
from functools import lru_cache
import unittest
from unittest.mock import patch

from arcadev import (
    ArcaCoreGenerationRequest, ArcaCoreCapability, ArcaCoreCapabilityStatus,
    validate_arcacore_generation_request, BuildStage,
)
from arcadev.arcacore_generation_request import module_definition, _translate_entity
from tools.fixture_arcadev_module_backend import minimal_approved_backend
from tools.test_arcadev_backend_approval import approved_backend, source_snapshot


@lru_cache(maxsize=1)
def gaming_request():
    return ArcaCoreGenerationRequest.create(approved_backend())


@lru_cache(maxsize=1)
def eligible_request():
    return ArcaCoreGenerationRequest.create(minimal_approved_backend())


class ArcaCoreGenerationRequestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gaming, cls.eligible = gaming_request(), eligible_request()

    def test_actual_gaming_studio_result_is_ineligible(self):
        r = self.gaming
        self.assertFalse(r.eligible_for_generation)
        self.assertTrue(r.blocking_findings)
        self.assertTrue(r.unsupported_mappings)
        self.assertTrue(r.required_certification_mappings)
        self.assertEqual(r.module_requests, ())
        self.assertTrue({ArcaCoreCapability.EXTERNAL_INTEGRATION, ArcaCoreCapability.PUBLISHING,
            ArcaCoreCapability.ISOLATED_WORKER} <= {m.capability for m in r.unsupported_mappings})

    def test_minimal_complete_scope_is_eligible(self):
        r = self.eligible
        self.assertTrue(r.eligible_for_generation, r.blocking_findings)
        self.assertFalse(r.blocking_findings)
        self.assertTrue(all(m.status is ArcaCoreCapabilityStatus.SUPPORTED for m in r.capability_mappings))
        self.assertEqual(len(r.module_requests), 1)

    def test_no_authentication_authority_is_incompatible_with_generated_router(self):
        result = ArcaCoreGenerationRequest.create(minimal_approved_backend("No authentication"))
        self.assertFalse(result.eligible_for_generation)
        self.assertTrue(result.blocking_findings)

    def test_exact_approved_backend_binding(self):
        r = self.gaming
        self.assertEqual(r.approved_backend.canonical_json(), approved_backend().canonical_json())
        self.assertEqual(r, validate_arcacore_generation_request(r, approved_backend=approved_backend()))
        with self.assertRaises(ValueError): validate_arcacore_generation_request(r, approved_backend=minimal_approved_backend())

    def test_determinism_and_canonical_roundtrip(self):
        for r in (self.gaming, self.eligible):
            self.assertEqual(r, ArcaCoreGenerationRequest.create(r.approved_backend))
            self.assertEqual(r, ArcaCoreGenerationRequest.from_json(r.canonical_json()))

    def test_public_module_translation_and_provenance(self):
        m = self.eligible.module_requests[0]
        self.assertEqual(m.module_name, "record_state")
        self.assertEqual(m.field_declarations, ("external_principal_id:str", "id:str:pk", "title:str"))
        definition = module_definition(m)
        self.assertEqual((definition.class_name, definition.module_name, definition.table_name), ("Record_state", "record_state", "record_states"))
        self.assertEqual(definition.primary_key_name, "id")
        entity = self.eligible.approved_backend.package.original_backend.resolved_model.entities[0]
        self.assertEqual(set(m.source_field_ids), {f.field_id for f in entity.approved_fields})
        self.assertEqual(len(m.generator_managed_field_ids), 2)
        self.assertTrue({c.decision_id for c in entity.choices} <= set(m.source_decision_ids))
        self.assertIn(m.naming_decision_id, {d.decision_id for d in self.eligible.approved_backend.package.backend_finalization.decisions})

    def test_every_responsibility_is_mapped(self):
        r = self.gaming
        spec = r.approved_backend.package.original_backend
        expected = {e.entity_id for e in spec.resolved_model.entities}
        expected.update(c.component_id for c in spec.components)
        expected.update(b.binding_id for b in spec.data_bindings)
        expected.update(o.operation_id for o in spec.operations)
        expected.update(p.policy_id for p in spec.policies)
        expected.update(d.decision_id for d in r.approved_backend.package.backend_finalization.decisions)
        expected.update(s for f in spec.approved_architecture_decisions for s in f.source_ids)
        self.assertTrue(expected <= {m.responsibility_id for m in r.capability_mappings})

    def test_forged_support_and_eligibility_rejected(self):
        for changes in ({"eligible_for_generation": True}, {"blocking_findings": []}):
            raw = self.gaming.canonical_dict(); raw.update(changes)
            with self.assertRaises(ValueError): ArcaCoreGenerationRequest.from_dict(raw)
        raw = self.gaming.canonical_dict()
        raw["capability_mappings"][0]["status"] = "SUPPORTED"
        raw["capability_mappings"][0]["reason"] = "Forged certification"
        with self.assertRaises(ValueError): ArcaCoreGenerationRequest.from_dict(raw)

    def test_omitted_responsibilities_and_partial_generation_rejected(self):
        for key in ("capability_mappings", "module_requests"):
            raw = self.eligible.canonical_dict(); raw[key] = []
            with self.assertRaises(ValueError): ArcaCoreGenerationRequest.from_dict(raw)
        raw = self.gaming.canonical_dict(); raw["capability_mappings"] = [m.canonical_dict() for m in self.gaming.supported_mappings]
        raw["eligible_for_generation"] = True; raw["blocking_findings"] = []
        with self.assertRaises(ValueError): ArcaCoreGenerationRequest.from_dict(raw)

    def test_forged_approval_and_stale_upstream_rejected(self):
        with self.assertRaises(ValueError): ArcaCoreGenerationRequest.create(replace(approved_backend(), approved=False))
        with self.assertRaises(ValueError): ArcaCoreGenerationRequest.create(replace(approved_backend(), approval_id="forged"))
        with self.assertRaises(ValueError):
            validate_arcacore_generation_request(self.gaming, backend=replace(approved_backend().package.original_backend, components=()))
        with self.assertRaises(ValueError):
            validate_arcacore_generation_request(self.gaming, finalization=replace(approved_backend().package.backend_finalization, history=()))

    def test_module_path_and_command_injection(self):
        m = self.eligible.module_requests[0]
        for name in ("../escape", "C:/output", "x;cmd", "$(whoami)", "__import__", "class", "x\\y"):
            with self.assertRaises(ValueError): module_definition(replace(m, module_name=name))
            raw = self.eligible.canonical_dict(); raw["module_requests"][0]["module_name"] = name
            with self.assertRaises(ValueError): ArcaCoreGenerationRequest.from_dict(raw)

    def test_executable_declaration_and_output_path_rejected(self):
        m = self.eligible.module_requests[0]
        for declaration in ("x:str:default=__import__('os')", "x:str; whoami", "x:str:fk=../../x", "../x:str"):
            with self.assertRaises(ValueError): module_definition(replace(m, field_declarations=(declaration,)))
        raw = self.eligible.canonical_dict(); raw["output_path"] = "C:/Projects/ArcaCore/backend"
        with self.assertRaises(ValueError): ArcaCoreGenerationRequest.from_dict(raw)

    def test_unknown_capability_and_schema(self):
        raw = self.gaming.canonical_dict(); raw["capability_mappings"][0]["capability"] = "universal_generator"
        with self.assertRaises(ValueError): ArcaCoreGenerationRequest.from_dict(raw)
        for changes in ({"schema": "unknown"}, {"schema_version": 2}, {"schema_version": True}, {"unknown": []}):
            raw = self.gaming.canonical_dict(); raw.update(changes)
            with self.assertRaises(ValueError): ArcaCoreGenerationRequest.from_dict(raw)

    def test_malformed_duplicate_and_oversized_json(self):
        for text in ("{", '{"schema":1,"schema":2}', " " * 5_000_001, "[" * 1000):
            with self.assertRaises(ValueError): ArcaCoreGenerationRequest.from_json(text)

    def test_secret_values_rejected(self):
        for value in ("password=x", "ghp_" + "a" * 36, "-----BEGIN PRIVATE KEY-----"):
            raw = self.gaming.canonical_dict()
            raw["application_manifest_plan"]["environment_requirement_names"] = [value]
            with self.assertRaises(ValueError): ArcaCoreGenerationRequest.from_dict(raw)

    def test_no_silent_loss_of_model_choices(self):
        a = self.eligible.approved_backend
        entity = a.package.original_backend.resolved_model.entities[0]
        changed = replace(entity, lifecycle_domain_ids=("unmapped",))
        module, reason = _translate_entity(a, changed, True)
        self.assertIsNone(module)
        self.assertIn("certification", reason)
        module, reason = _translate_entity(a, entity, False)
        self.assertIsNone(module)
        self.assertIn("timestamp", reason)

    def test_timestamp_mutability_must_match_generator_behavior(self):
        a = self.eligible.approved_backend
        entity = a.package.original_backend.resolved_model.entities[0]
        changed = replace(entity, approved_fields=tuple(replace(f, mutable=False) if f.name == "updated_at" else f for f in entity.approved_fields))
        module, reason = _translate_entity(a, changed, True)
        self.assertIsNone(module)
        self.assertIn("Timestamp authority", reason)

    def test_no_fabricated_post_generation_manifest(self):
        plan = self.eligible.application_manifest_plan
        self.assertIn("observed_generation_manifest", plan.pending_authority)
        self.assertIn("accepted_schema_revision", plan.pending_authority)
        self.assertIn("trusted_principal_scope_middleware", plan.runtime_requirements)
        self.assertFalse(hasattr(plan, "generation_manifest_digest"))

    def test_immutable_nonexecuting_and_backend_stage(self):
        before = source_snapshot()
        with patch("tools.generate.generate_module", side_effect=AssertionError("No generator")), patch("subprocess.Popen", side_effect=AssertionError("No subprocess")):
            for r in (self.gaming, self.eligible):
                self.assertEqual(r, ArcaCoreGenerationRequest.create(r.approved_backend))
                self.assertEqual(r.approved_backend.package.models_backend_handoff.resulting_project.current_build_stage, BuildStage.BACKEND)
        self.assertEqual(before, source_snapshot())
        with self.assertRaises(FrozenInstanceError): self.eligible.eligible_for_generation = False


if __name__ == "__main__":
    unittest.main()
