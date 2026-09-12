"""5.2 deterministic authority and hostile candidate certification."""
from dataclasses import replace
from functools import lru_cache
from types import MappingProxyType
import unittest
from unittest.mock import patch

from arcadev import (
    BackendSpecificationCandidateAdapter, generate_baseline_backend_specification,
    validate_backend_specification_candidate, validate_backend_specification_adapter_candidate,
    BackendQuestion, BackendArea, BuildStage,
)
from arcadev.backend_specification import backend_owners
from tools.test_arcadev_backend_specification import backend_fixture_handoff, contract_fixture, rebuild


@lru_cache(maxsize=1)
def backend_baseline():
    return generate_baseline_backend_specification(backend_fixture_handoff())


def grouped_candidate(baseline):
    h = backend_fixture_handoff()
    owners = backend_owners(h)
    services = tuple(s for s, c in owners.items() if c.category == "service")
    grouped = contract_fixture(groups=[services, *((s,) for s in owners if s not in services)])
    old_components = {c.component_id: c for c in baseline.components}
    targets = {s: c.component_id for c in grouped.components for s in c.architecture_source_ids}
    old_operations = {o.operation_id: o for o in baseline.operations}
    target_operations = {o.capability_id: o.operation_id for o in grouped.operations}
    questions = []
    for q in baseline.open_backend_questions:
        questions.append(BackendQuestion.create(handoff=h, question=q.question, blocking=q.blocking, area=q.area,
            architecture_source_ids=q.architecture_source_ids, model_source_ids=q.model_source_ids,
            component_ids=tuple(sorted({targets[s] for cid in q.component_ids for s in old_components[cid].architecture_source_ids})),
            operation_ids=tuple(target_operations[old_operations[oid].capability_id] for oid in q.operation_ids)))
    return rebuild(grouped, open_backend_questions=questions)


class BackendEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = backend_fixture_handoff()
        cls.spec = backend_baseline()

    def validate(self, raw):
        return validate_backend_specification_candidate(self.handoff, raw)

    def test_deterministic_generation(self):
        self.assertEqual(self.spec.canonical_json(), generate_baseline_backend_specification(self.handoff).canonical_json())
        self.assertEqual(self.spec, self.validate(self.spec.canonical_json()))

    def test_complete_capability_ownership_and_minimal_backend(self):
        expected = {cap for c in backend_owners(self.handoff).values() for cap in c.owned_capabilities}
        self.assertEqual({cap for c in self.spec.components for cap in c.owned_capabilities}, expected)
        self.assertEqual({o.capability_id for o in self.spec.operations}, expected)
        self.assertEqual((len(self.spec.components), len(self.spec.operations), len(self.spec.data_bindings)), (9, 7, 5))
        self.assertEqual({o.kind for o in self.spec.operations}, {"workflow_action", "integration_action"})

    def test_frozen_model_and_architecture_choices_preserved(self):
        self.assertEqual(self.spec.resolved_model, self.handoff.frozen_approved_domain_model.package.resolved_model)
        for text in ("PostgreSQL", "OCI container", "leased worker", "explicit user", "Managed object storage"):
            self.assertIn(text, " ".join(f.value for f in self.spec.approved_architecture_decisions))

    def test_gaming_studio_operations_and_authentication(self):
        for word in ("project", "asset", "build", "testing", "publishing", "GitHub", "Authentication"):
            self.assertTrue(any(word.casefold() in o.name.casefold() for o in self.spec.operations))
        self.assertTrue(all(o.authorization_ids for o in self.spec.operations))
        self.assertIn("external_principal_id", self.spec.resolved_model.canonical_json())

    def test_material_questions_and_prior_choices_not_reopened(self):
        self.assertFalse(self.spec.readiness.ready_for_approval)
        self.assertEqual(len(self.spec.open_backend_questions), 10)
        areas = {q.area for q in self.spec.open_backend_questions}
        self.assertTrue({BackendArea.ASYNC_EXECUTION, BackendArea.PERSISTENCE_MAPPING,
            BackendArea.API_BOUNDARY, BackendArea.IMPLEMENTATION_TECHNOLOGY} <= areas)
        for q in self.spec.open_backend_questions:
            self.assertTrue(q.blocking)
            self.assertNotIn("whether", q.question.casefold())
            self.assertNotIn("which primary persistence", q.question.casefold())
            self.assertNotIn("which worker isolation", q.question.casefold())
        for q in self.spec.open_backend_questions:
            if q.area is BackendArea.IDEMPOTENCY:
                affected = [o for o in self.spec.operations if o.operation_id in q.operation_ids]
                self.assertFalse(any("build" in o.name for o in affected))

    def test_compatibility_is_a_precondition_not_a_support_claim(self):
        q = next(q for q in self.spec.open_backend_questions if q.area is BackendArea.IMPLEMENTATION_TECHNOLOGY)
        self.assertIn("certification precondition", q.question)
        self.assertTrue(q.blocking)
        self.assertEqual(set(q.component_ids), {c.component_id for c in self.spec.components})

    def test_provider_neutral_adapter_json_and_mapping(self):
        raw = self.spec.canonical_dict()
        class Adapter:
            def create_candidate(self, handoff):
                return MappingProxyType(raw)
        self.assertIsInstance(Adapter(), BackendSpecificationCandidateAdapter)
        self.assertEqual(self.spec, validate_backend_specification_adapter_candidate(self.handoff, Adapter()))
        class JsonAdapter:
            def create_candidate(self, handoff):
                return self_json
        self_json = self.spec.canonical_json()
        self.assertEqual(self.spec, validate_backend_specification_adapter_candidate(self.handoff, JsonAdapter()))
        with self.assertRaises(ValueError): validate_backend_specification_adapter_candidate(self.handoff, object())

    def test_semantically_equivalent_rename(self):
        renamed = rebuild(self.spec, components=(replace(self.spec.components[0], name="Repository connector"), *self.spec.components[1:]))
        self.assertNotEqual(renamed.backend_id, self.spec.backend_id)
        self.assertEqual(renamed, self.validate(renamed))

    def test_grouping_preserves_exact_frozen_ownership(self):
        grouped = grouped_candidate(self.spec)
        self.assertLess(len(grouped.components), len(self.spec.components))
        self.assertEqual(grouped, self.validate(grouped))
        self.assertEqual(grouped.resolved_model, self.spec.resolved_model)
        originals = {p.authority.source_ids: p for p in self.spec.policies}
        base_ops = {o.operation_id: o.capability_id for o in self.spec.operations}
        grouped_ops = {o.operation_id: o.capability_id for o in grouped.operations}
        for policy in grouped.policies:
            original = originals[policy.authority.source_ids]
            self.assertEqual(policy.model_entity_ids, original.model_entity_ids)
            self.assertEqual({grouped_ops[oid] for oid in policy.operation_ids},
                             {base_ops[oid] for oid in original.operation_ids})

    def test_missing_or_reworded_material_question_rejected(self):
        for questions in ((), self.spec.open_backend_questions[1:]):
            with self.assertRaises(ValueError): self.validate(rebuild(self.spec, open_backend_questions=questions))
        q = self.spec.open_backend_questions[0]
        altered = BackendQuestion.create(handoff=self.handoff, question="Should GitHub exist?", blocking=q.blocking,
            area=q.area, architecture_source_ids=q.architecture_source_ids, model_source_ids=q.model_source_ids,
            component_ids=q.component_ids, operation_ids=q.operation_ids)
        with self.assertRaises(ValueError): self.validate(rebuild(self.spec, open_backend_questions=(altered, *self.spec.open_backend_questions[1:])))

    def test_grouped_storage_policy_cannot_adopt_unrelated_state(self):
        grouped = grouped_candidate(self.spec)
        policy = next(p for p in grouped.policies if p.kind == "storage" and len(p.model_entity_ids) == 1)
        component = next(c for c in grouped.components if c.component_id in policy.component_ids)
        self.assertGreater(len(component.model_entity_ids), len(policy.model_entity_ids))
        expanded = replace(policy, model_entity_ids=component.model_entity_ids, resulting_entity_ids=component.model_entity_ids)
        with self.assertRaises(ValueError):
            rebuild(grouped, policies=tuple(expanded if p.policy_id == policy.policy_id else p for p in grouped.policies))

    def test_required_question_cannot_be_downgraded(self):
        q = self.spec.open_backend_questions[0]
        advisory = BackendQuestion.create(handoff=self.handoff, question=q.question, blocking=False, area=q.area,
            architecture_source_ids=q.architecture_source_ids, model_source_ids=q.model_source_ids,
            component_ids=q.component_ids, operation_ids=q.operation_ids)
        with self.assertRaises(ValueError): self.validate(rebuild(self.spec, open_backend_questions=(advisory, *self.spec.open_backend_questions[1:])))

    def test_advisory_refinement_has_no_authority(self):
        q = next(q for q in self.spec.open_backend_questions if q.area is BackendArea.API_BOUNDARY)
        extra = BackendQuestion.create(handoff=self.handoff, question="Advisory review: " + q.question,
            blocking=False, area=q.area, architecture_source_ids=q.architecture_source_ids,
            model_source_ids=q.model_source_ids, component_ids=q.component_ids, operation_ids=q.operation_ids[:1])
        candidate = rebuild(self.spec, open_backend_questions=(*self.spec.open_backend_questions, extra))
        self.assertEqual(candidate, self.validate(candidate))
        self.assertFalse(candidate.readiness.ready_for_approval)

    def test_advisory_question_cannot_reopen_frozen_scope(self):
        q = next(q for q in self.spec.open_backend_questions if q.area is BackendArea.API_BOUNDARY)
        for wording in ("Should GitHub exist?", "Should payment processing be added?"):
            extra = BackendQuestion.create(handoff=self.handoff, question=wording, blocking=False,
                area=q.area, architecture_source_ids=q.architecture_source_ids, model_source_ids=q.model_source_ids,
                component_ids=q.component_ids, operation_ids=q.operation_ids)
            with self.assertRaises(ValueError):
                self.validate(rebuild(self.spec, open_backend_questions=(*self.spec.open_backend_questions, extra)))

    def test_invented_and_missing_capabilities_rejected(self):
        for mutation in (lambda raw: raw["components"][0]["owned_capabilities"].append("payments"),
                         lambda raw: raw["components"].pop(), lambda raw: raw["operations"].pop()):
            raw = self.spec.canonical_dict(); mutation(raw)
            with self.assertRaises(ValueError): self.validate(raw)

    def test_invented_or_missing_persistent_state_rejected(self):
        for mutation in (lambda raw: raw["data_bindings"].pop(),
                         lambda raw: raw["data_bindings"][0].update(entity_id="invented"),
                         lambda raw: raw["resolved_model"]["entities"].pop()):
            raw = self.spec.canonical_dict(); mutation(raw)
            with self.assertRaises(ValueError): self.validate(raw)

    def test_wrong_handoff_identity_and_readiness_rejected(self):
        for key, value in (("models_backend_handoff_id", "forged"), ("backend_id", "forged"), ("provider", "vendor")):
            raw = self.spec.canonical_dict(); raw[key] = value
            with self.assertRaises(ValueError): self.validate(raw)
        raw = self.spec.canonical_dict(); raw["readiness"]["ready_for_approval"] = True
        with self.assertRaises(ValueError): self.validate(raw)

    def test_invalid_graph_operations_and_boundaries(self):
        for collection, key, value in (("components", "dependencies", ["bad"]), ("operations", "component_id", "bad"),
            ("operations", "output_entity_ids", ["bad"]), ("operations", "authorization_ids", []),
            ("policies", "external_boundary_ids", ["unsupported_integration"]), ("policies", "resulting_entity_ids", ["invented"])):
            raw = self.spec.canonical_dict(); raw[collection][0][key] = value
            with self.assertRaises(ValueError): self.validate(raw)

    def test_unknown_fields_duplicates_malformed_and_oversized(self):
        for raw in ("{", '{"schema":1,"schema":2}', " " * 5_000_001, object()):
            with self.assertRaises(ValueError): self.validate(raw)
        for collection in ("components", "operations", "policies", "open_backend_questions"):
            raw = self.spec.canonical_dict(); raw[collection][0]["model_provider"] = "untrusted"
            with self.assertRaises(ValueError): self.validate(raw)

    def test_credential_input_rejected(self):
        for token in ("access_token=x", "password=x", "ghp_abcdefghijklmnop", "Bearer opaque", "-----BEGIN PRIVATE KEY-----"):
            raw = self.spec.canonical_dict(); raw["components"][0]["name"] = token
            with self.assertRaises(ValueError): self.validate(raw)

    def test_no_generation_network_execution_or_stage_change(self):
        before = self.handoff.canonical_json()
        with patch("tools.generate.generate_module", side_effect=AssertionError("generator")), \
             patch("subprocess.Popen", side_effect=AssertionError("execution")), \
             patch("socket.create_connection", side_effect=AssertionError("network")):
            self.assertEqual(self.spec, generate_baseline_backend_specification(self.handoff))
            self.validate(self.spec)
        self.assertEqual(before, self.handoff.canonical_json())
        self.assertEqual(self.handoff.resulting_project.current_build_stage, BuildStage.BACKEND)

    def test_hostile_presentation_text_is_inert(self):
        op = replace(self.spec.operations[0], name="DROP TABLE x; __import__('os'); $(echo inert)")
        candidate = rebuild(self.spec, operations=(op, *self.spec.operations[1:]))
        with patch("os.system", side_effect=AssertionError("execution")), patch("builtins.eval", side_effect=AssertionError("eval")):
            self.assertEqual(candidate, self.validate(candidate))


if __name__ == "__main__":
    unittest.main()
