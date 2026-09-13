"""Refinement 1 certification. All Gaming Studio authority is TEST FIXTURE ONLY."""
from dataclasses import replace
from functools import lru_cache
import json
import unittest
from unittest.mock import patch

from arcadev.model_amendment_request import (
    ModelAmendmentRequest, ModelAmendmentFieldProposal, ModelAmendmentArea,
    suggest_model_amendment, model_amendment_review, validate_proposal,
)
from tools.test_arcadev_model_approval import approved_model


@lru_cache(maxsize=1)
def fixture_request():
    return ModelAmendmentRequest.create(approved_model())


def fixture_field(question, **changes):
    """TEST FIXTURE ONLY. Never called by production request or review functions."""
    claim = question.target.source_choice.claim
    area = question.target.area
    identity = area is ModelAmendmentArea.IDENTITY_BINDING
    lifecycle = area is ModelAmendmentArea.LIFECYCLE_FIELD
    names = {"identity": "record_id", "lifecycle": "state", "principal_reference": "principal_ref",
        "external_reference": "repository_ref", "field": "outcome_ref"}
    kind = claim.values[0] if identity else "enum" if lifecycle else "external_reference"
    raw = dict(entity_id=question.target.entity_id, name=names[claim.slot], logical_type=kind,
        required=True, collection=False, mutable=not identity, unique=identity,
        classification="internal" if identity or lifecycle else "external_identifier",
        value_domain_name="lifecycle_states" if lifecycle else None,
        value_domain_values=sorted(claim.values) if lifecycle else [], default_json=None,
        source_decision_id=question.target.source_choice.decision_id, source_claim=claim.canonical_dict())
    raw.update(changes)
    return raw


class ModelAmendmentRequestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = fixture_request()

    def test_determinism_roundtrip_and_parent_binding(self):
        r = self.request
        self.assertEqual(r, ModelAmendmentRequest.create(approved_model()))
        self.assertEqual(r, ModelAmendmentRequest.from_json(r.canonical_json(), parent=approved_model()))
        self.assertEqual(r.parent_model_id, approved_model().model_id)
        self.assertEqual(r.parent_model_finalization_id, approved_model().model_finalization_id)
        self.assertEqual(r.parent.package.architecture_handoff, approved_model().package.architecture_handoff)

    def test_five_entities_questions_and_no_automatic_fields(self):
        r = self.request
        self.assertEqual(len(r.parent.package.resolved_model.entities), 5)
        self.assertEqual({q.target.entity_id for q in r.questions}, {e.entity_id for e in r.parent.package.resolved_model.entities})
        self.assertEqual(sum(q.target.area is ModelAmendmentArea.IDENTITY_BINDING for q in r.questions), 5)
        self.assertEqual(len(r.questions), 14)
        self.assertEqual({a for q in r.questions for a in q.target.materialization_areas}, set(ModelAmendmentArea))
        self.assertTrue(all(not e.approved_fields and not e.identity_field_ids for e in r.parent.package.resolved_model.entities))
        self.assertFalse(r.candidates)

    def test_candidate_boundary(self):
        q = self.request.questions[0]
        class Adapter:
            def create_candidate(self, request):
                return {"candidates": [{"question_id": q.question_id, "field": fixture_field(q)}]}
        result = suggest_model_amendment(approved_model(), Adapter())
        self.assertNotEqual(result.request_id, self.request.request_id)
        self.assertEqual(result.parent, self.request.parent)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(ModelAmendmentRequest.from_json(result.canonical_json()), result)
        self.assertTrue(all(not e.approved_fields for e in result.parent.package.resolved_model.entities))

    def test_complete_field_and_unsupported_type(self):
        q = self.request.questions[0]
        for key in fixture_field(q):
            raw = fixture_field(q)
            del raw[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_proposal(raw, q)
        for changes in ({"logical_type": "sql_integer"}, {"mutable": None}, {"collection": 0},
                {"classification": "credential"}, {"default_json": '"value"'}, {"name": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_proposal(fixture_field(q, **changes), q)

    def test_wrong_entity_and_provenance(self):
        q = self.request.questions[0]
        for question_id in ([], {}, None, "nonexistent"):
            with self.assertRaises(ValueError):
                ModelAmendmentRequest.create(approved_model(), candidates=[{"question_id": question_id, "field": fixture_field(q)}])
        for changes in ({"entity_id": "missing_entity"}, {"source_decision_id": "unrelated"},
                {"source_claim": self.request.questions[-1].target.source_choice.claim.canonical_dict()}):
            with self.assertRaises(ValueError):
                validate_proposal(fixture_field(q, **changes), q)

    def test_forged_parent_and_stale_content(self):
        with self.assertRaises(ValueError):
            ModelAmendmentRequest.create(replace(approved_model(), approval_statement="forged"))
        with self.assertRaises(ValueError):
            ModelAmendmentRequest.from_json(self.request.canonical_json(), parent=replace(approved_model(), model_id="stale"))
        raw = self.request.canonical_dict()
        raw["parent"]["package"]["resolved_model"]["entities"] = []
        with self.assertRaises(ValueError):
            ModelAmendmentRequest.from_dict(raw)

    def test_untrusted_input_rejections(self):
        q = self.request.questions[0]
        for value in ("ghp_abcdefghijklmnopqrstuvwxyz", "password=literal", "C:\\tmp\\file", "/tmp/file", "../file",
                "CREATE TABLE state", "exec(payload)", "$(whoami)", "`whoami`", "access_token", "password", "api_key"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ModelAmendmentFieldProposal.from_dict(fixture_field(q, name=value))
        for key in ("provider", "automatic_approval", "sql_type", "table_name", "service_code"):
            raw = fixture_field(q)
            raw[key] = "untrusted"
            with self.assertRaises(ValueError):
                ModelAmendmentFieldProposal.from_dict(raw)

    def test_json_schema_shape_bounds(self):
        for text in ('{', '{"x":1,"x":2}', ' ' * 5_000_001):
            with self.assertRaises(ValueError):
                ModelAmendmentRequest.from_json(text)
        for changes in ({"schema": "other"}, {"schema_version": 2}, {"schema_version": True},
                {"unknown": 1}, {"questions": []}):
            raw = self.request.canonical_dict()
            raw.update(changes)
            with self.assertRaises(ValueError):
                ModelAmendmentRequest.from_dict(raw)
        raw = self.request.canonical_dict()
        raw["questions"][0]["target"]["area"] = "sql_type"
        with self.assertRaises(ValueError):
            ModelAmendmentRequest.from_dict(raw)

    def test_review_is_deterministic_inert_and_fixture_labeled(self):
        before = approved_model().canonical_json()
        with patch("arcadev.backend_generation.generate_backend", side_effect=AssertionError("No generation")), patch(
                "arcadev.models_backend_handoff.ModelsBackendHandoff.create", side_effect=AssertionError("No rebuild")):
            report = model_amendment_review(self.request)
            self.assertEqual(report, model_amendment_review(self.request))
        self.assertIn("TEST FIXTURE ONLY", report["parent_approval_statement"])
        self.assertEqual(before, approved_model().canonical_json())
        self.assertEqual(len(report["entities"]), 5)


if __name__ == "__main__":
    unittest.main()
