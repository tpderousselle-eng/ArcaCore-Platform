"""5.1 contract certification. Gaming Studio choices are TEST FIXTURE ONLY."""
from dataclasses import replace
from functools import lru_cache
import unittest
from unittest.mock import patch

from arcadev import create_models_backend_handoff, BuildStage
from arcadev.backend_specification import (
    BackendSpecification, BackendFact, BackendComponent, BackendDataBinding,
    BackendOperation, BackendPolicy, BackendQuestion, BackendArea, BackendRole,
    backend_architecture, backend_owners, backend_operation_entities, backend_policy_entities,
    identify_backend_record, validate_backend_specification,
)
from tools.test_arcadev_model_approval import approved_model


@lru_cache(maxsize=1)
def backend_fixture_handoff():
    approved = approved_model()
    return create_models_backend_handoff(source_project=approved.package.architecture_handoff.resulting_project,
                                        approved_domain_model=approved)


def contract_fixture(handoff=None, *, groups=None):
    """Assemble typed authority for 5.1 representability; no product decisions."""
    h = handoff or backend_fixture_handoff()
    owners, entities = backend_owners(h), h.frozen_approved_domain_model.package.resolved_model.entities
    fact = lambda sources, rule=None: BackendFact.create(handoff=h, source_ids=tuple(sorted(sources)), derivation=rule)
    roles = {"service": BackendRole.APPLICATION_SERVICE, "storage": BackendRole.PERSISTENCE,
             "identity": BackendRole.IDENTITY_BOUNDARY, "adapter": BackendRole.INTEGRATION_ADAPTER,
             "worker": BackendRole.EXTERNAL_WORKER}
    components = []
    for group in groups or [(s,) for s in owners]:
        caps = tuple(sorted({cap for s in group for cap in owners[s].owned_capabilities}))
        mids = tuple(sorted(e.entity_id for e in entities if set(caps) & set(e.owned_capabilities)))
        interfaces = tuple(sorted({i for s in group for i in owners[s].exposed_interfaces}))
        c = BackendComponent("", " + ".join(owners[s].name for s in group), fact(group, "capability_implementation"),
            tuple(sorted(group)), caps, mids, roles[owners[group[0]].category], (), interfaces)
        components.append(identify_backend_record(c, "component", "component_id", exclude=("name", "dependencies")))
    mapping = {s: c.component_id for c in components for s in c.architecture_source_ids}
    components = [replace(c, dependencies=tuple(sorted({mapping[d] for s in c.architecture_source_ids
        for d in owners[s].dependencies if d in mapping and mapping[d] != c.component_id}))) for c in components]
    bindings = [identify_backend_record(BackendDataBinding("", e.entity_id,
        mapping[e.architecture_source_requirements[0]], fact((e.entity_id,), "persistence_binding")), "binding", "binding_id") for e in entities]
    operations = []
    for s, owner in owners.items():
        for cap in owner.owned_capabilities:
            mids = backend_operation_entities(h, s, cap)
            op = BackendOperation("", owner.name, mapping[s], cap,
                "integration_action" if owner.category == "adapter" else "workflow_action", mids, mids, (), (), (),
                fact((s,), "operation_from_requirement"))
            operations.append(identify_backend_record(op, "operation", "operation_id",
                exclude=("name", "authorization_ids", "transaction_ids", "failure_ids")))
    policies = []
    kinds = {"authentication": "authorization", "integration": "integration", "storage": "storage", "background": "background"}
    for a in backend_architecture(h).original_architecture.aspects:
        if a.area.value not in kinds:
            continue
        kind = kinds[a.area.value]
        cids = tuple(sorted({mapping[s] for s in a.component_ids if s in mapping}))
        mids = backend_policy_entities(h, a, kind, components)
        oids = tuple(sorted(o.operation_id for o in operations if kind == "authorization" or o.component_id in cids))
        policy = BackendPolicy("", kind, cids, oids, mids, fact((a.aspect_id,)), (a.aspect_id,), mids, (a.aspect_id,))
        policies.append(identify_backend_record(policy, "policy", "policy_id"))
    auth = tuple(sorted(p.policy_id for p in policies if p.kind == "authorization"))
    operations = [replace(o, authorization_ids=auth) for o in operations]
    q = BackendQuestion.create(handoff=h, question="Which physical mapping preserves this approved logical model?",
        blocking=True, area=BackendArea.PERSISTENCE_MAPPING, architecture_source_ids=(h.architecture_id,),
        model_source_ids=tuple(e.entity_id for e in entities), component_ids=tuple(c.component_id for c in components))
    return BackendSpecification.create(handoff=h, objective=fact((h.architecture_id,), "backend_objective"),
        components=components, data_bindings=bindings, operations=operations, policies=policies, open_backend_questions=(q,))


def rebuild(spec, **changes):
    args = {key: getattr(spec, key) for key in ("objective", "components", "data_bindings", "operations", "policies", "open_backend_questions")}
    args.update(changes)
    return BackendSpecification.create(handoff=backend_fixture_handoff(), **args)


class BackendSpecificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = backend_fixture_handoff()
        cls.spec = contract_fixture(cls.handoff)

    def load(self, raw):
        return validate_backend_specification(raw, handoff=self.handoff)

    def test_gaming_studio_representability(self):
        self.assertEqual(len(self.spec.components), 9)
        self.assertEqual(len(self.spec.operations), 7)
        self.assertEqual(len(self.spec.data_bindings), 5)
        for term in ("project", "asset", "build", "testing", "publishing", "GitHub", "Authentication"):
            self.assertTrue(any(term.casefold() in c.name.casefold() for c in self.spec.components))

    def test_deterministic_identity_and_canonical_ordering(self):
        self.assertEqual(self.spec, rebuild(self.spec, components=tuple(reversed(self.spec.components))))
        self.assertEqual(self.spec.canonical_json(), contract_fixture().canonical_json())

    def test_canonical_roundtrip(self):
        self.assertEqual(self.spec, self.load(self.spec.canonical_json()))
        self.assertEqual(self.spec, self.load(dict(reversed(list(self.spec.canonical_dict().items())))))

    def test_complete_upstream_binding_and_resolved_authority(self):
        self.assertEqual(self.spec.models_backend_handoff_id, self.handoff.handoff_id)
        for field in ("source_project_id", "approved_domain_model_id", "model_id", "model_finalization_id",
                      "approved_architecture_id", "architecture_id", "architecture_finalization_id"):
            self.assertEqual(getattr(self.spec, field), getattr(self.handoff, field))
        self.assertEqual(self.spec.resolved_model, self.handoff.frozen_approved_domain_model.package.resolved_model)
        self.assertEqual(len(self.spec.approved_architecture_decisions), 8)
        self.assertIn("PostgreSQL", " ".join(f.value for f in self.spec.approved_architecture_decisions))

    def test_deep_immutability(self):
        with self.assertRaises(AttributeError):
            self.spec.components[0].name = "changed"
        raw = self.spec.canonical_dict()
        raw["resolved_model"]["entities"].clear()
        self.assertEqual(len(self.spec.resolved_model.entities), 5)

    def test_readiness_recomputed(self):
        self.assertTrue(self.spec.readiness.structurally_valid)
        self.assertFalse(self.spec.readiness.ready_for_approval)
        self.assertTrue(rebuild(self.spec, open_backend_questions=()).readiness.ready_for_approval)

    def test_authorization_and_async_authority(self):
        self.assertTrue(all(o.authorization_ids for o in self.spec.operations))
        worker = next(p for p in self.spec.policies if p.kind == "background")
        self.assertTrue(worker.input_authority_ids)
        self.assertTrue(worker.resulting_entity_ids)
        self.assertIsNone(worker.retry_semantics)
        self.assertIn("external_principal_id", self.spec.resolved_model.canonical_json())

    def test_outcome_review_context_does_not_transfer_model_ownership(self):
        model = self.spec.resolved_model
        build = next(e for e in model.entities if e.name == "build management state")
        testing = next(o for o in self.spec.operations if "testing" in o.name)
        self.assertEqual(testing.output_entity_ids, (build.entity_id,))
        for operation in self.spec.operations:
            owned = tuple(sorted(e.entity_id for e in model.entities if operation.capability_id in e.owned_capabilities))
            if owned:
                self.assertEqual(operation.input_entity_ids, owned)
                self.assertEqual(operation.output_entity_ids, owned)

    def test_component_names_are_inert_presentation(self):
        renamed = replace(self.spec.components[0], name="SQL DROP TABLE x; __import__('os'); rm -rf /")
        with patch("builtins.eval", side_effect=AssertionError("executed")), patch("os.system", side_effect=AssertionError("executed")):
            result = rebuild(self.spec, components=(renamed, *self.spec.components[1:]))
            self.assertEqual(result.components[0].component_id, renamed.component_id)

    def test_forged_bindings_stage_schema_and_readiness(self):
        for key, value in (("backend_id", "forged"), ("models_backend_handoff_id", "forged"),
            ("upstream_authority_id", "forged"), ("source_project_id", "wrong"), ("project_stage", "FRONTEND"),
            ("schema", "other"), ("schema_version", True), ("schema_version", 2), ("provider", "vendor")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                raw = self.spec.canonical_dict(); raw[key] = value; self.load(raw)
        raw = self.spec.canonical_dict(); raw["readiness"]["ready_for_approval"] = True
        with self.assertRaises(ValueError): self.load(raw)

    def test_invalid_dependencies_roles_names_and_capabilities(self):
        c = self.spec.components[0]
        for altered in (replace(c, dependencies=("bad",)), replace(c, implementation_role="arbitrary"),
                        replace(c, owned_capabilities=("billing",)), replace(c, model_entity_ids=("invented",)),
                        replace(c, name=self.spec.components[1].name)):
            with self.subTest(altered=altered.name), self.assertRaises(ValueError):
                rebuild(self.spec, components=(altered, *self.spec.components[1:]))

    def test_missing_capability_and_persistence_rejected(self):
        for key in ("components", "data_bindings", "operations", "policies"):
            with self.subTest(key=key), self.assertRaises(ValueError): rebuild(self.spec, **{key: getattr(self.spec, key)[1:]})

    def test_operation_ownership_model_and_duplicate_rejected(self):
        op = self.spec.operations[0]
        for bad in (replace(op, component_id="bad"), replace(op, input_entity_ids=("invented",)),
                    replace(op, authorization_ids=()), replace(op, kind="create"), replace(op, operation_id="forged")):
            with self.assertRaises(ValueError): rebuild(self.spec, operations=(bad, *self.spec.operations[1:]))
        with self.assertRaises(ValueError): rebuild(self.spec, operations=(*self.spec.operations, op))

    def test_invalid_binding_and_proposed_fields_rejected(self):
        binding = self.spec.data_bindings[0]
        with self.assertRaises(ValueError): rebuild(self.spec, data_bindings=(replace(binding, entity_id="bad"), *self.spec.data_bindings[1:]))
        raw = self.spec.canonical_dict(); raw["resolved_model"]["entities"][0]["approved_fields"] = [{"name": "password"}]
        with self.assertRaises(ValueError): self.load(raw)

    def test_invalid_authorization_work_and_provenance_rejected(self):
        for key, value in (("component_ids", ("bad",)), ("resulting_entity_ids", ("bad",)),
                           ("external_boundary_ids", ("bad",)), ("kind", "integration_unsupported")):
            with self.assertRaises(ValueError):
                rebuild(self.spec, policies=(replace(self.spec.policies[0], **{key: value}), *self.spec.policies[1:]))
        with self.assertRaises(ValueError): rebuild(self.spec, objective=replace(self.spec.objective, provenance="model_provider"))
        with self.assertRaises(ValueError): rebuild(self.spec, objective=replace(self.spec.objective, source_ids=("bad",)))

    def test_question_identity_scope_and_source_validation(self):
        q = self.spec.open_backend_questions[0]
        for bad in (replace(q, question_id="forged"), replace(q, component_ids=("bad",)),
                    replace(q, architecture_source_ids=("bad",)), replace(q, model_source_ids=(self.handoff.architecture_id,))):
            with self.assertRaises(ValueError): rebuild(self.spec, open_backend_questions=(bad,))

    def test_unknown_fields_and_executable_objects_rejected(self):
        for key in ("components", "operations", "policies", "data_bindings", "open_backend_questions"):
            raw = self.spec.canonical_dict(); raw[key][0]["unknown"] = "x"
            with self.assertRaises(ValueError): self.load(raw)
        for value in (object(), lambda: None, b"pickle", {"__reduce__": "os.system"}):
            with self.assertRaises(ValueError): self.load(value)

    def test_json_duplicates_malformed_and_limits(self):
        for value in ('{"schema":1,"schema":2}', "{", "[]", '"\\ud800"', " " * 5_000_001):
            with self.assertRaises(ValueError): self.load(value)

    def test_credentials_controls_and_unicode(self):
        for name in ("password=x", "refresh_token=x", "ghp_abcdefghijklmnopqrst", "-----BEGIN PRIVATE KEY-----",
                     "sk-12345678901234567890", "bad\x00text", "\ud800", "a" * 100_001):
            with self.subTest(name=repr(name)), self.assertRaises(ValueError):
                rebuild(self.spec, components=(replace(self.spec.components[0], name=name), *self.spec.components[1:]))

    def test_wrong_handoff(self):
        with self.assertRaises(ValueError):
            validate_backend_specification(self.spec, handoff=replace(self.handoff, handoff_id="forged"))

    def test_no_generation_or_stage_transition(self):
        with patch("tools.generate.generate_module", side_effect=AssertionError("generator invoked")), \
             patch("subprocess.run", side_effect=AssertionError("command invoked")):
            self.load(self.spec)
        self.assertEqual(self.handoff.resulting_project.current_build_stage, BuildStage.BACKEND)
        self.assertEqual(self.spec.project_stage, BuildStage.BACKEND)


if __name__ == "__main__":
    unittest.main()
