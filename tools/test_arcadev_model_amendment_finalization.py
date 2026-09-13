"""Refinement 2. Every answer below is TEST FIXTURE ONLY, never production data."""
from dataclasses import replace
from functools import lru_cache
import json
import unittest
from unittest.mock import patch

from arcadev.model_amendment_request import ModelAmendmentArea, ModelAmendmentRequest, model_amendment_review
from arcadev.model_amendment_answer import ModelAmendmentAnswer
from arcadev.model_amendment_finalization import ModelAmendmentFinalization
from arcadev.domain_model_specification import model_element_id
from tools.test_arcadev_model_amendment_request import fixture_request, fixture_field


def fixture_answer(state, question, **changes):
    """TEST FIXTURE ONLY: explicit complete structured declarations for certification."""
    field = fixture_field(question, **changes)
    quote = json.dumps(field, sort_keys=True, separators=(",", ":"))
    return ModelAmendmentAnswer.create(request_id=state.request.request_id,
        parent_approval_id=state.request.parent.approval_id, target_finalization_id=state.finalization_id,
        question_id=question.question_id, entity_id=field["entity_id"],
        user_answer="TEST FIXTURE ONLY: I explicitly authorize this complete logical declaration " + quote,
        declaration_quote=quote, field=field, action="accept")


@lru_cache(maxsize=1)
def fixture_finalization():
    request = fixture_request()
    state = ModelAmendmentFinalization.start(request)
    for question in request.questions:
        state = state.resolve(fixture_answer(state, question), parent=request.parent)
    return state


class ModelAmendmentFinalizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = fixture_request()
        cls.start = ModelAmendmentFinalization.start(cls.request)
        cls.complete = fixture_finalization()

    def question(self, area):
        return next(q for q in self.request.questions if q.target.area.value == area)

    def resolve(self, question, **changes):
        return self.start.resolve(fixture_answer(self.start, question, **changes), parent=self.request.parent)

    def test_single_explicit_field_and_exact_user_provenance(self):
        q = self.request.questions[0]
        answer = fixture_answer(self.start, q)
        state = self.start.resolve(answer, parent=self.request.parent)
        decision = state.decisions[0]
        self.assertEqual(decision.answer, answer)
        self.assertEqual(decision.field.evidence.provenance, "explicit_user")
        self.assertEqual(decision.field.evidence.question_id, q.question_id)
        self.assertEqual(decision.field.evidence.amendment_decision_id, decision.decision_id)
        self.assertEqual(decision.source_choice, q.target.source_choice)
        self.assertIn("TEST FIXTURE ONLY", decision.answer.user_answer)
        self.assertIn(answer.declaration_quote, decision.answer.user_answer)
        self.assertFalse(state.effective_ready_for_approval)

    def test_identity_field_and_deterministic_ids(self):
        q = self.question("identity_binding")
        one, two = self.resolve(q), self.resolve(q)
        self.assertEqual(one, two)
        d = one.decisions[0]
        self.assertTrue(d.identity_binding)
        self.assertEqual(d.field.field_id, model_element_id("field", name=d.field.name,
            source_requirements=q.target.architecture_source_ids, scope=(q.target.entity_id,)))
        self.assertEqual((d.field.required, d.field.collection, d.field.mutable, d.field.unique), (True, False, False, True))

    def test_lifecycle_field_and_exact_value_domain(self):
        q = self.question("lifecycle_field")
        d = self.resolve(q).decisions[0]
        self.assertTrue(d.lifecycle_binding)
        self.assertEqual(d.field.logical_type.value, "enum")
        self.assertEqual(d.field.value_domain_id, d.value_domain.domain_id)
        self.assertEqual(d.value_domain.values, tuple(sorted(q.target.source_choice.claim.values)))

    def test_principal_external_and_outcome_references(self):
        for area in ("principal_reference_field", "external_reference_field", "outcome_reference_field"):
            q = self.question(area)
            with self.subTest(area=area):
                d = self.resolve(q).decisions[0]
                self.assertEqual(d.field.classification.value, "external_identifier")
                self.assertEqual(d.answer.entity_id, q.target.entity_id)
                self.assertEqual(d.field.logical_type.value, "external_reference")

    def test_wrong_entity_and_wrong_decision_rejected(self):
        q = self.request.questions[0]
        for changes in ({"entity_id": self.request.questions[-1].target.entity_id}, {"source_decision_id": "unrelated"}):
            # Pick a definitely nonexistent entity even when both endpoint questions share one.
            if "entity_id" in changes:
                changes = {"entity_id": "nonexistent"}
            with self.assertRaises(ValueError):
                self.resolve(q, **changes)

    def test_lifecycle_mismatch_and_classification_rejected(self):
        q = self.question("lifecycle_field")
        for changes in ({"value_domain_values": ["new_product_state", "draft"]}, {"classification": "external_identifier"}):
            with self.assertRaises(ValueError):
                self.resolve(q, **changes)
        with self.assertRaises(ValueError):
            self.resolve(self.question("principal_reference_field"), classification="internal")

    def test_identity_semantics_rejected(self):
        q = self.question("identity_binding")
        for changes in ({"required": False}, {"collection": True}, {"mutable": True}, {"unique": False}, {"logical_type": "string"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.resolve(q, **changes)

    def test_duplicate_normalized_fields_rejected(self):
        q = self.question("identity_binding")
        state = self.resolve(q)
        other = next(x for x in self.request.questions if x.target.entity_id == q.target.entity_id and x != q)
        for name in ("record_id", "RECORD_ID"):
            with self.assertRaises(ValueError):
                state.resolve(fixture_answer(state, other, name=name), parent=self.request.parent)

    def test_stale_parent_finalization_and_replay_rejected(self):
        q = self.request.questions[0]
        answer = fixture_answer(self.start, q)
        state = self.start.resolve(answer, parent=self.request.parent)
        with self.assertRaises(ValueError):
            state.resolve(answer, parent=self.request.parent)
        with self.assertRaises(ValueError):
            state.resolve(fixture_answer(state, q), parent=self.request.parent)
        with self.assertRaises(ValueError):
            self.start.resolve(answer, parent=replace(self.request.parent, approval_statement="stale"))

    def test_replacement_unsupported_and_history_preserved(self):
        answer = fixture_answer(self.start, self.request.questions[0]).canonical_dict()
        answer["action"] = "replace"
        with self.assertRaises(ValueError):
            ModelAmendmentAnswer.from_dict(answer)
        self.assertEqual(len(self.complete.history), 14)
        self.assertEqual(len({e.decision_id for e in self.complete.history}), 14)

    def test_forged_history_fields_readiness_and_schema_rejected(self):
        for key, value in (("decisions", []), ("history", []), ("effective_ready_for_approval", False),
                           ("schema_version", True), ("unresolved_question_ids", ["forged"])):
            raw = self.complete.canonical_dict()
            raw[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                ModelAmendmentFinalization.from_dict(raw)
        raw = self.complete.canonical_dict()
        raw["history"][0]["outcome"] = "rejected"
        with self.assertRaises(ValueError):
            ModelAmendmentFinalization.from_dict(raw)

    def test_unchanged_answer_and_complete_quoted_evidence(self):
        answer = fixture_answer(self.start, self.request.questions[0])
        self.assertEqual(answer, ModelAmendmentAnswer.from_json(answer.canonical_json()))
        for key, value in (("user_answer", "I approve something else"), ("provenance", "candidate"),
                           ("declaration_quote", '{}'), ("schema", "unknown")):
            raw = answer.canonical_dict()
            raw[key] = value
            with self.assertRaises(ValueError):
                ModelAmendmentAnswer.from_dict(raw)

    def test_complete_fixture_readiness_does_not_approve_parent(self):
        self.assertFalse(self.start.effective_ready_for_approval)
        self.assertTrue(self.complete.effective_ready_for_approval)
        self.assertFalse(self.complete.unresolved_question_ids)
        self.assertFalse(self.complete.conflicts)
        self.assertEqual(len(self.complete.decisions), 14)
        self.assertEqual(sum(d.identity_binding for d in self.complete.decisions), 5)
        self.assertEqual(sum(d.lifecycle_binding for d in self.complete.decisions), 2)
        self.assertEqual({d.answer.entity_id for d in self.complete.decisions}, {e.entity_id for e in self.request.parent.package.resolved_model.entities})
        self.assertTrue(all(not e.approved_fields for e in self.request.parent.package.resolved_model.entities))

    def test_roundtrip_history_and_request_exact_binding(self):
        self.assertEqual(self.complete, ModelAmendmentFinalization.from_json(self.complete.canonical_json(), parent=self.request.parent, request=self.request))
        q = self.request.questions[0]
        request = ModelAmendmentRequest.create(self.request.parent, candidates=[{"question_id": q.question_id, "field": fixture_field(q)}])
        suggested = ModelAmendmentFinalization.start(request)
        self.assertFalse(suggested.decisions)
        self.assertFalse(suggested.effective_ready_for_approval)
        with self.assertRaises(ValueError):
            ModelAmendmentFinalization.from_json(self.complete.canonical_json(), request=request)

    def test_duplicate_domains_rejected(self):
        questions = [q for q in self.request.questions if q.target.area is ModelAmendmentArea.LIFECYCLE_FIELD]
        state = self.resolve(questions[0], value_domain_name="shared_states")
        with self.assertRaises(ValueError):
            state.resolve(fixture_answer(state, questions[1], value_domain_name="SHARED_STATES"), parent=self.request.parent)

    def test_review_remains_unresolved_and_no_downstream_or_generation(self):
        parent = self.request.parent.canonical_json()
        with patch("arcadev.backend_generation.generate_backend", side_effect=AssertionError("No generation")), patch(
                "arcadev.models_backend_handoff.ModelsBackendHandoff.create", side_effect=AssertionError("No rebuild")):
            state = self.resolve(self.request.questions[0])
            self.assertEqual(state.request.parent.canonical_json(), parent)
            one = model_amendment_review(self.request)
            self.assertEqual(one, model_amendment_review(self.request))
            self.assertEqual(one["status"], "UNRESOLVED_REQUIRES_EXPLICIT_ANSWERS")


if __name__ == "__main__":
    unittest.main()
