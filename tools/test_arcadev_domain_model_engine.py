"""ArcaDev 4.2 certification; architecture/model choices are TEST FIXTURE ONLY."""
from dataclasses import replace
from functools import lru_cache
from types import MappingProxyType
import unittest
from unittest.mock import patch

from arcadev import (
    DomainModelSpecification, ModelEntity, ModelFact, ModelField, ModelQuestion,
    ModelValueDomain, ModelRelationship, ModelArea, LogicalType, DataClassification,
    DomainModelCandidateAdapter, generate_baseline_domain_model,
    validate_domain_model_candidate, validate_domain_model_adapter_candidate,
    model_element_id, persistent_model_capabilities, BuildStage, ProjectStatus,
    ArchitectureSpecification, ArchitectureFact, ArchitectureQuestion, ArchitectureFinalization,
    approve_architecture, create_architecture_models_handoff,
)
from arcadev.architecture_specification import _json
from tools.test_arcadev_domain_model_specification import models_handoff
from tools.test_arcadev_architecture_clarification import answer_for, fixture_choice


def altered(model, handoff, **changes):
    keys = ("objective", "entities", "value_domains", "relationships", "constraints", "access_requirements", "open_model_questions")
    args = {key: getattr(model, key) for key in keys}
    args.update(changes)
    return DomainModelSpecification.create(handoff=handoff, **args)


def rename_entity(model, handoff, entity, name):
    eid = model_element_id("entity", name=name, source_requirements=entity.responsibility.source_requirements, scope=entity.owned_capabilities)
    questions = tuple(ModelQuestion.create(handoff=handoff, question=q.question, blocking=q.blocking, area=q.area,
        source_requirements=q.source_requirements, entity_ids=tuple(eid if v == entity.entity_id else v for v in q.entity_ids),
        relationship_ids=q.relationship_ids) for q in model.open_model_questions)
    qids = {old.question_id: new.question_id for old, new in zip(model.open_model_questions, questions)}
    entities = tuple(replace(e, entity_id=eid if e == entity else e.entity_id, name=name if e == entity else e.name,
        identity_question_id=qids.get(e.identity_question_id)) for e in model.entities)
    return altered(model, handoff, entities=entities, open_model_questions=questions)


@lru_cache(maxsize=1)
def grouped_architecture_handoff():
    """Author an alternative frozen fixture using the certified public contracts."""
    original = models_handoff()
    package = original.frozen_approved_architecture.package
    handoff, spec = package.plan_handoff, package.original_architecture
    persistent = persistent_model_capabilities(original)
    target, removed = [c for c in spec.components if c.category == "service" and set(c.owned_capabilities) <= set(persistent)][:2]
    owned = target.owned_capabilities + removed.owned_capabilities
    responsibility = ArchitectureFact.create(handoff=handoff, source_requirements=owned, derivation="responsibility")
    def endpoint(value):
        return target.component_id if value == removed.component_id else value
    interfaces = tuple(replace(e, source=endpoint(e.source), destination=endpoint(e.destination)) for e in spec.interfaces)
    flows = tuple(replace(e, source=endpoint(e.source), destination=endpoint(e.destination)) for e in spec.data_flows)
    components = []
    ids = {c.component_id for c in spec.components if c != removed}
    for c in spec.components:
        if c == removed:
            continue
        if c == target:
            c = replace(c, name="Combined approved state", owned_capabilities=owned, responsibility=responsibility)
        deps = tuple(sorted({e.destination for e in interfaces if e.source == c.component_id and e.destination in ids}))
        exposed = tuple(e.connection_id for e in interfaces if c.component_id in (e.source, e.destination))
        components.append(replace(c, dependencies=deps, exposed_interfaces=exposed))
    aspects = tuple(replace(a, component_ids=tuple(sorted({endpoint(v) for v in a.component_ids}))) for a in spec.aspects)
    identity_question = ArchitectureQuestion.create("TEST ONLY: choose the logical identity field for these approved responsibilities",
        False, owned, "storage", handoff=handoff)
    keys = ("objective", "system_boundary", "style", "external_entities", "approved_constraints", "components", "interfaces", "data_flows", "aspects", "open_architecture_questions")
    args = {key: getattr(spec, key) for key in keys}
    args.update(components=components, interfaces=interfaces, data_flows=flows, aspects=aspects,
                open_architecture_questions=spec.open_architecture_questions + (identity_question,))
    spec = ArchitectureSpecification.create(handoff=handoff, **args)
    state = ArchitectureFinalization.start(spec, handoff=handoff)
    payload = _json(dict(name="id", logical_type="uuid", required=True, collection=False, mutable=False, unique=True,
                         classification="internal", value_domain_id=None, default_json=None)).strip()
    for q in tuple(state.unresolved_questions):
        state = state.resolve(answer_for(state, q, payload if q == identity_question else fixture_choice(q)), handoff=handoff)
    approved = approve_architecture(handoff=handoff, architecture=spec, finalization=state,
        approval_statement="TEST ONLY: approve grouped responsibilities and the explicit logical identifier declaration.")
    return create_architecture_models_handoff(source_project=handoff.resulting_project, approved_architecture=approved)


class ArcaDevDomainModelEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = models_handoff()
        cls.spec = generate_baseline_domain_model(cls.handoff)

    def validate(self, value):
        return validate_domain_model_candidate(self.handoff, value)

    def test_deterministic_generation_and_roundtrip(self):
        self.assertEqual(self.spec, generate_baseline_domain_model(self.handoff))
        self.assertEqual(self.spec.canonical_json(), generate_baseline_domain_model(self.handoff).canonical_json())
        self.assertEqual(self.spec, self.validate(self.spec.canonical_json()))

    def test_required_state_minimality_and_testing_uncertainty(self):
        self.assertEqual(len(self.spec.entities), 5)
        self.assertEqual({c for e in self.spec.entities for c in e.owned_capabilities}, set(persistent_model_capabilities(self.handoff)))
        names = " ".join(e.name for e in self.spec.entities)
        for token in ("project", "asset", "build", "publishing", "GitHub"):
            self.assertIn(token, names)
        self.assertNotIn("testing", names)
        self.assertTrue(any("testing workflow" in q.question for q in self.spec.open_model_questions))
        self.assertTrue(any(q.area is ModelArea.PRINCIPAL_REFERENCE for q in self.spec.open_model_questions))
        self.assertTrue(any(q.area is ModelArea.EXTERNAL_REFERENCE for q in self.spec.open_model_questions))
        self.assertFalse(any(e.fields for e in self.spec.entities))
        self.assertFalse(self.spec.relationships)
        self.assertFalse(self.spec.value_domains)

    def test_material_questions_do_not_reopen_implementation_decisions(self):
        self.assertEqual(len(self.spec.open_model_questions), 22)
        text = " ".join(q.question for q in self.spec.open_model_questions)
        for phrase in ("frontend implementation", "primary persistence implementation", "worker isolation implementation", "deployment-unit topology"):
            self.assertNotIn(phrase, text)
        self.assertNotIn("UUID", text)
        self.assertFalse(self.spec.readiness.ready_for_finalization)
        self.assertTrue(self.spec.readiness.structurally_valid)

    def test_provider_neutral_adapter_and_mapping_boundary(self):
        model = self.spec
        class Adapter:
            def create_candidate(self, handoff):
                return MappingProxyType(model.canonical_dict())
        self.assertIsInstance(Adapter(), DomainModelCandidateAdapter)
        self.assertEqual(self.spec, validate_domain_model_adapter_candidate(self.handoff, Adapter()))
        with self.assertRaises(ValueError):
            validate_domain_model_adapter_candidate(self.handoff, object())
        class Executable(dict):
            def items(self):
                raise AssertionError("Untrusted mapping must never execute")
        with self.assertRaises(ValueError):
            self.validate(Executable(self.spec.canonical_dict()))

    def test_entity_renaming_preserves_semantic_coverage(self):
        candidate = rename_entity(self.spec, self.handoff, self.spec.entities[0], "A different grounded logical label")
        self.assertNotEqual(candidate.model_id, self.spec.model_id)
        self.assertEqual(candidate, self.validate(candidate))

    def test_grouping_follows_frozen_ownership_and_prior_identity_is_not_reopened(self):
        handoff = grouped_architecture_handoff()
        model = generate_baseline_domain_model(handoff)
        self.assertEqual(len(model.entities), 4)
        grouped = next(e for e in model.entities if len(e.owned_capabilities) == 2)
        self.assertEqual(grouped.fields[0].logical_type, LogicalType.UUID)
        self.assertIsNone(grouped.identity_question_id)
        self.assertFalse(any(q.area is ModelArea.IDENTITY and grouped.entity_id in q.entity_ids for q in model.open_model_questions))
        self.assertEqual(model, validate_domain_model_candidate(handoff, model))

    def test_valid_grounded_external_reference_proposal(self):
        q = next(q for q in self.spec.open_model_questions if q.area is ModelArea.EXTERNAL_REFERENCE)
        entity = next(e for e in self.spec.entities if e.entity_id in q.entity_ids)
        fact = ModelFact.create(handoff=self.handoff, source_requirements=q.source_requirements, question_id=q.question_id,
                                value="TEST ONLY: proposed non-secret repository identifier")
        fid = model_element_id("field", name="repository_reference", source_requirements=fact.source_requirements, scope=(entity.entity_id,))
        field = ModelField(fid, "repository_reference", LogicalType.EXTERNAL_REFERENCE, True, False, None, None, DataClassification.EXTERNAL_IDENTIFIER, fact)
        candidate = altered(self.spec, self.handoff, entities=tuple(replace(e, fields=(field,)) if e == entity else e for e in self.spec.entities))
        self.assertEqual(candidate, self.validate(candidate))
        self.assertFalse(candidate.readiness.ready_for_finalization)
        for value in ("VARCHAR", "uuid"):
            raw = candidate.canonical_dict()
            next(e for e in raw["entities"] if e["fields"])["fields"][0]["logical_type"] = value
            with self.assertRaises(ValueError):
                self.validate(raw)

    def test_valid_proposed_lifecycle_and_invalid_value_domain(self):
        q = next(q for q in self.spec.open_model_questions if q.area is ModelArea.LIFECYCLE)
        entity = next(e for e in self.spec.entities if e.entity_id in q.entity_ids)
        fact = ModelFact.create(handoff=self.handoff, source_requirements=q.source_requirements, question_id=q.question_id, value="TEST ONLY: proposed states")
        did = model_element_id("domain", name="workflow_states", source_requirements=fact.source_requirements)
        domain = ModelValueDomain(did, "workflow_states", ("pending", "finished"), fact)
        fid = model_element_id("field", name="state", source_requirements=fact.source_requirements, scope=(entity.entity_id,))
        field = ModelField(fid, "state", LogicalType.ENUM, True, False, True, None, DataClassification.INTERNAL, fact, did)
        candidate = altered(self.spec, self.handoff, value_domains=(domain,),
            entities=tuple(replace(e, fields=(field,), lifecycle_domain_ids=(did,)) if e == entity else e for e in self.spec.entities))
        self.assertEqual(candidate, self.validate(candidate))
        raw = candidate.canonical_dict()
        next(e for e in raw["entities"] if e["fields"])["fields"][0]["value_domain_id"] = "missing"
        with self.assertRaises(ValueError):
            self.validate(raw)

    def test_relationship_proposal_and_broken_reference(self):
        q = next(q for q in self.spec.open_model_questions if q.area is ModelArea.RELATIONSHIP)
        source, target = q.entity_ids[:2]
        fact = ModelFact.create(handoff=self.handoff, source_requirements=q.source_requirements, question_id=q.question_id, value="TEST ONLY: proposed logical reference")
        rid = model_element_id("relationship", name="test_reference", source_requirements=q.source_requirements, scope=(source, target))
        edge = ModelRelationship(rid, "test_reference", source, target, "many", "one", True, fact)
        candidate = altered(self.spec, self.handoff, relationships=(edge,))
        self.assertEqual(candidate, self.validate(candidate))
        raw = candidate.canonical_dict()
        raw["relationships"][0]["target_entity_id"] = "missing"
        with self.assertRaises(ValueError):
            self.validate(raw)

    def test_invented_entity_and_required_state_removal(self):
        for entity in self.spec.entities:
            raw = self.spec.canonical_dict()
            raw["entities"] = [e for e in raw["entities"] if e["entity_id"] != entity.entity_id]
            with self.assertRaises(ValueError):
                self.validate(raw)
        raw = self.spec.canonical_dict()
        raw["entities"][0]["owned_capabilities"] = ["billing"]
        with self.assertRaises(ValueError):
            self.validate(raw)

    def test_material_question_removal_and_reinterpretation(self):
        q = next(q for q in self.spec.open_model_questions if q.area is ModelArea.LOOKUP)
        candidate = altered(self.spec, self.handoff, open_model_questions=tuple(v for v in self.spec.open_model_questions if v != q))
        with self.assertRaisesRegex(ValueError, "unresolved material"):
            self.validate(candidate)
        changed = ModelQuestion.create(handoff=self.handoff, question="What color should the UI be?", blocking=True,
            area=q.area, source_requirements=q.source_requirements, entity_ids=q.entity_ids)
        candidate = altered(self.spec, self.handoff, open_model_questions=tuple(changed if v == q else v for v in self.spec.open_model_questions))
        with self.assertRaises(ValueError):
            self.validate(candidate)

    def test_unrelated_question_cannot_launder_fields(self):
        entity = self.spec.entities[0]
        q = ModelQuestion.create(handoff=self.handoff, question="Invent an unrelated field?", blocking=True, area="field",
            source_requirements=entity.responsibility.source_requirements, entity_ids=(entity.entity_id,))
        fact = ModelFact.create(handoff=self.handoff, source_requirements=q.source_requirements, question_id=q.question_id, value="Unapproved arbitrary content")
        fid = model_element_id("field", name="arbitrary", source_requirements=q.source_requirements, scope=(entity.entity_id,))
        field = ModelField(fid, "arbitrary", LogicalType.STRING, False, False, None, None, DataClassification.INTERNAL, fact)
        candidate = altered(self.spec, self.handoff, open_model_questions=self.spec.open_model_questions + (q,),
            entities=tuple(replace(e, fields=(field,)) if e == entity else e for e in self.spec.entities))
        with self.assertRaisesRegex(ValueError, "launders"):
            self.validate(candidate)

    def test_forged_identity_handoff_readiness_and_metadata(self):
        for key, value in (("model_id", "forged"), ("handoff_id", "forged"), ("provider", "vendor"), ("schema", "wrong"), ("schema_version", 2),
                           ("readiness", {"structurally_valid": True, "ready_for_finalization": True, "blocking_reasons": []})):
            raw = self.spec.canonical_dict()
            raw[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate(raw)

    def test_malformed_oversized_unicode_and_secret_inputs(self):
        for text in ("{", '{"schema":1,"schema":2}', " " * 5_000_001, "[" * 1000, object()):
            with self.assertRaises(ValueError):
                self.validate(text)
        for text in ("password=x", "access_token=abcdefghijkl", "-----BEGIN PRIVATE KEY-----", "\ud800", "bad\x01"):
            raw = self.spec.canonical_dict()
            raw["entities"][0]["name"] = text
            with self.assertRaises(ValueError):
                self.validate(raw)

    def test_generation_and_hostile_labels_are_inert_and_stay_models(self):
        before = self.handoff.canonical_json()
        candidate = rename_entity(self.spec, self.handoff, self.spec.entities[0], "DROP TABLE; __import__('os'); $(echo inert); C:/inert/path")
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), patch("builtins.eval", side_effect=AssertionError("eval")), patch("socket.create_connection", side_effect=AssertionError("network")), patch("builtins.open", side_effect=AssertionError("filesystem")):
            self.assertEqual(candidate, self.validate(candidate))
            self.assertEqual(self.spec, generate_baseline_domain_model(self.handoff))
        self.assertEqual(before, self.handoff.canonical_json())
        self.assertEqual(candidate.project_stage, BuildStage.MODELS)
        self.assertEqual(self.handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        for key in ("sql", "tables", "orm", "migrations", "apis", "backend", "frontend", "generated_artifacts"):
            self.assertNotIn(key, candidate.canonical_dict())


if __name__ == "__main__":
    unittest.main()
