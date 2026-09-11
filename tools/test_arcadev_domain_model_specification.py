"""ArcaDev 4.1 certification. Proposed choices here are TEST FIXTURE ONLY."""
from dataclasses import replace
from functools import lru_cache
import json
import unittest
from unittest.mock import patch

from arcadev import (
    DomainModelSpecification, LogicalType, DataClassification, ModelArea, ModelProvenance,
    ModelFact, ModelQuestion, ModelEntity, ModelField, ModelValueDomain, ModelRelationship,
    ModelConstraint, ModelAccessRequirement, BuildStage, ProjectStatus,
    model_element_id, model_question_id, persistent_model_capabilities,
    validate_domain_model_specification, approve_architecture, create_architecture_models_handoff,
)
from tools.test_arcadev_architecture_approval import resolved_architecture


@lru_cache(maxsize=1)
def models_handoff():
    handoff, spec, initial, complete = resolved_architecture()
    approved = approve_architecture(handoff=handoff, architecture=spec, finalization=complete,
                                    approval_statement="TEST FIXTURE ONLY: explicitly approve Gaming Studio architecture.")
    return create_architecture_models_handoff(source_project=handoff.resulting_project, approved_architecture=approved)


def fixture(handoff, rich=False):
    """Manual 4.1 representation, deliberately independent of a model engine."""
    architecture = handoff.frozen_approved_architecture.package.original_architecture
    entities, questions, domains, relationships, constraints, access = [], [], [], [], [], []
    for component in architecture.components:
        if not component.owned_capabilities or component.category == "identity":
            continue
        sources = (component.component_id,)
        name = component.name.removesuffix(" boundary")
        eid = model_element_id("entity", name=name, source_requirements=sources, scope=component.owned_capabilities)
        q = ModelQuestion.create(handoff=handoff, question="TEST ONLY: choose the logical identifier type for " + name,
            blocking=True, area="identity", source_requirements=sources, entity_ids=(eid,))
        questions.append(q)
        entity = ModelEntity(eid, name, ModelFact.create(handoff=handoff, source_requirements=sources, derivation="capability_state"),
                             component.owned_capabilities, identity_question_id=q.question_id)
        if "testing" in name:
            questions.append(ModelQuestion.create(handoff=handoff, question="TEST ONLY: should test-run/result state persist?",
                blocking=True, area="lifecycle", source_requirements=sources, entity_ids=(eid,)))
        if component.category == "adapter":
            questions.append(ModelQuestion.create(handoff=handoff, question="TEST ONLY: choose safe external repository identifiers",
                blocking=True, area="external_reference", source_requirements=sources, entity_ids=(eid,)))
        entities.append(entity)
    if rich:
        entity = entities[0]
        sources = entity.responsibility.source_requirements
        q = ModelQuestion.create(handoff=handoff, question="TEST ONLY: review proposed field choices", blocking=True,
                                 area="field", source_requirements=sources, entity_ids=(entity.entity_id,))
        questions.append(q)
        fact = ModelFact.create(handoff=handoff, source_requirements=sources, question_id=q.question_id,
                                value="TEST ONLY: proposed logical fields; unresolved")
        did = model_element_id("domain", name="test_values", source_requirements=sources)
        domains.append(ModelValueDomain(did, "test_values", ("pending", "complete"), fact))
        model_fields = []
        for typ in LogicalType:
            fid = model_element_id("field", name=typ.value, source_requirements=sources, scope=(entity.entity_id,))
            model_fields.append(ModelField(fid, typ.value, typ, True, False, False, None, DataClassification.INTERNAL,
                                          fact, did if typ is LogicalType.ENUM else None))
        entity = replace(entity, fields=tuple(model_fields), lifecycle_domain_ids=(did,))
        entities[0] = entity
        ids = (model_fields[0].field_id,)
        cid = model_element_id("constraint", name="min_length", source_requirements=sources, scope=(entity.entity_id, *ids))
        constraints.append(ModelConstraint(cid, "min_length", entity.entity_id, ids, "1", fact))
        aid = model_element_id("access", name="logical_lookup", source_requirements=sources, scope=(entity.entity_id, *ids))
        access.append(ModelAccessRequirement(aid, "logical_lookup", entity.entity_id, ids, False, fact))
        endpoints = (entities[0].entity_id, entities[1].entity_id)
        edge_sources = tuple(sorted(set(entities[0].responsibility.source_requirements + entities[1].responsibility.source_requirements)))
        eq = ModelQuestion.create(handoff=handoff, question="TEST ONLY: review ownership and cardinality", blocking=True,
            area="relationship", source_requirements=edge_sources, entity_ids=endpoints)
        questions.append(eq)
        ef = ModelFact.create(handoff=handoff, source_requirements=edge_sources, question_id=eq.question_id, value="TEST ONLY: proposed reference")
        for source, target in (endpoints, tuple(reversed(endpoints))):
            name = "reference_from_" + source
            rid = model_element_id("relationship", name=name, source_requirements=edge_sources, scope=endpoints)
            relationships.append(ModelRelationship(rid, name, source, target, "many", "one", True, ef))
    return DomainModelSpecification.create(handoff=handoff,
        objective=ModelFact.create(handoff=handoff, source_requirements=(handoff.architecture_id,), derivation="model_objective"),
        entities=entities, value_domains=domains, relationships=relationships, constraints=constraints,
        access_requirements=access, open_model_questions=questions)


class ArcaDevDomainModelSpecificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = models_handoff()
        cls.spec = fixture(cls.handoff, rich=True)

    def load(self, value):
        return DomainModelSpecification.from_dict(value, handoff=self.handoff)

    def altered(self, **changes):
        keys = ("objective", "entities", "value_domains", "relationships", "constraints", "access_requirements", "open_model_questions")
        args = {key: getattr(self.spec, key) for key in keys}
        args.update(changes)
        return DomainModelSpecification.create(handoff=self.handoff, **args)

    def test_gaming_studio_representability(self):
        names = " ".join(e.name for e in self.spec.entities)
        for term in ("project", "asset", "build", "testing", "publishing", "GitHub"):
            self.assertIn(term, names)
        self.assertEqual(len(self.spec.entities), 6)
        self.assertEqual({f.logical_type for e in self.spec.entities for f in e.fields}, set(LogicalType))
        self.assertEqual(self.spec.project_stage, BuildStage.MODELS)
        self.assertEqual(self.handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)

    def test_deterministic_canonical_order_and_roundtrip(self):
        self.assertEqual(self.spec, fixture(self.handoff, rich=True))
        self.assertEqual(self.spec, DomainModelSpecification.from_json(self.spec.canonical_json(), handoff=self.handoff))
        self.assertEqual(self.spec, self.altered(entities=tuple(reversed(self.spec.entities)), open_model_questions=tuple(reversed(self.spec.open_model_questions))))
        value = self.spec.canonical_dict()
        value["entities"].reverse()
        self.assertEqual(self.spec, self.load(value))
        with self.assertRaises(AttributeError):
            self.spec.entities = ()

    def test_exact_identity_binding_and_forgery_rejection(self):
        for key in ("model_id", "handoff_id", "project_id", "plan_handoff_id", "approved_architecture_id", "architecture_id", "architecture_finalization_id", "project_stage"):
            value = self.spec.canonical_dict()
            value[key] = "forged"
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load(value)
        with self.assertRaises(ValueError):
            validate_domain_model_specification(self.spec, handoff=replace(self.handoff, handoff_id="forged"))

    def test_readiness_recomputed_and_questions_bound(self):
        self.assertTrue(self.spec.readiness.structurally_valid)
        self.assertFalse(self.spec.readiness.ready_for_finalization)
        for key in ("structurally_valid", "ready_for_finalization", "blocking_reasons"):
            value = self.spec.canonical_dict()
            value["readiness"][key] = [] if key == "blocking_reasons" else not value["readiness"][key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load(value)
        with self.assertRaises(ValueError):
            self.altered(open_model_questions=())
        for q in self.spec.open_model_questions:
            self.assertEqual(q.question_id, model_question_id(q))

    def test_entity_and_field_uniqueness(self):
        with self.assertRaises(ValueError):
            self.altered(entities=self.spec.entities + (self.spec.entities[0],))
        e = next(e for e in self.spec.entities if e.fields)
        for field in (e.fields[0], replace(e.fields[0], field_id="forged"), replace(e.fields[0], name=e.fields[1].name)):
            with self.subTest(field=field.name), self.assertRaises(ValueError):
                self.altered(entities=tuple(replace(v, fields=v.fields + (field,)) if v == e else v for v in self.spec.entities))

    def test_types_classification_and_boolean_semantics(self):
        for key, replacement in (("logical_type", "JSONB"), ("logical_type", "ARRAY(string)"), ("classification", "secret"),
                                 ("required", 1), ("mutable", "immutable"), ("unique", 0), ("collection", "false")):
            value = self.spec.canonical_dict()
            next(e for e in value["entities"] if e["fields"])["fields"][0][key] = replacement
            with self.subTest(key=key, replacement=replacement), self.assertRaises(ValueError):
                self.load(value)

    def test_enum_domains_duplicates_and_references(self):
        domain = self.spec.value_domains[0]
        for values in (("one", " ONE "), ("K", "K"), (), ("a", "a")):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.altered(value_domains=(replace(domain, values=values),))
        with self.assertRaises(ValueError):
            self.altered(value_domains=())

    def test_relationships_allow_cycles_but_reject_invalid_semantics(self):
        self.assertEqual(len(self.spec.relationships), 2)
        for key, value in (("target_entity_id", "missing"), ("source_cardinality", "foreign_key"), ("required", False), ("ownership", "SQL"), ("deletion_behavior", "eval")):
            edge = replace(self.spec.relationships[0], **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.altered(relationships=(edge,))

    def test_constraints_access_and_executable_expression_rejection(self):
        for key in ("constraints", "access_requirements"):
            original = getattr(self.spec, key)[0]
            for changes in ({"field_ids": ("missing",)}, {"entity_id": "missing"}, {"field_ids": ()}):
                with self.subTest(key=key, changes=changes), self.assertRaises(ValueError):
                    self.altered(**{key: (replace(original, **changes),)})
        for value in ("-1", '"__import__(\'os\')"', "true"):
            with self.assertRaises(ValueError):
                self.altered(constraints=(replace(self.spec.constraints[0], value_json=value),))

    def test_provenance_and_scope_are_not_free_text_assertions(self):
        for changes in ({"value": "Invented billing"}, {"provenance": "approved_architecture_decision"}, {"source_requirements": ["missing"]}, {"derivation": "infer_anything"}):
            value = self.spec.canonical_dict()
            value["entities"][0]["responsibility"].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.load(value)
        for entity in self.spec.entities:
            if set(entity.owned_capabilities) & persistent_model_capabilities(self.handoff).keys():
                with self.assertRaises(ValueError):
                    self.altered(entities=tuple(e for e in self.spec.entities if e != entity))

    def test_unapproved_defaults_and_credential_fields_rejected(self):
        for changes in ({"default_json": '"arbitrary"'}, {"name": "password"}, {"name": "oauth_token"}):
            value = self.spec.canonical_dict()
            next(e for e in value["entities"] if e["fields"])["fields"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.load(value)

    def test_json_schema_shape_and_resource_limits(self):
        for text in ("{", '{"schema":1,"schema":2}', " " * 5_000_001, "[" * 1000, object()):
            with self.subTest(text=str(text)[:20]), self.assertRaises(ValueError):
                DomainModelSpecification.from_json(text, handoff=self.handoff)
        for key, value in (("schema", "wrong"), ("schema_version", 2), ("schema_version", True), ("provider", "vendor"), ("entities", {})):
            candidate = self.spec.canonical_dict()
            candidate[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load(candidate)

    def test_secrets_unicode_controls_and_executable_objects(self):
        for content in ("password=abcdefgh", "password=x", "secret: a", "-----BEGIN PRIVATE KEY-----", "ghp_abcdefghijklmnop", "Bearer abcdefghijkl", "ya29.fixturetoken", "\ud800", "bad\x01"):
            candidate = self.spec.canonical_dict()
            candidate["entities"][0]["name"] = content
            with self.subTest(content=repr(content)), self.assertRaises(ValueError):
                self.load(candidate)
        class Executable(dict):
            def items(self):
                raise AssertionError("Must not execute")
        with self.assertRaises(ValueError):
            self.load(Executable(self.spec.canonical_dict()))

    def test_inert_hostile_content_no_generation_no_transition(self):
        before = self.handoff.canonical_json()
        entity = self.spec.entities[0]
        q = ModelQuestion.create(handoff=self.handoff, question="Review inert SQL DROP TABLE; __import__('os'); $(echo inert); C:/inert/path",
            blocking=True, area="field", source_requirements=entity.responsibility.source_requirements, entity_ids=(entity.entity_id,))
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), patch("builtins.eval", side_effect=AssertionError("eval")), patch("socket.create_connection", side_effect=AssertionError("network")), patch("builtins.open", side_effect=AssertionError("filesystem")):
            result = self.altered(open_model_questions=self.spec.open_model_questions + (q,))
            self.assertEqual(result, self.load(result.canonical_dict()))
        self.assertEqual(before, self.handoff.canonical_json())
        self.assertEqual(result.project_stage, BuildStage.MODELS)
        for name in ("tables", "sql", "migrations", "orm", "api_contracts", "generated_artifacts", "backend", "frontend"):
            self.assertNotIn(name, result.canonical_dict())


if __name__ == "__main__":
    unittest.main()
