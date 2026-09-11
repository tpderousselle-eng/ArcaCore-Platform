"""ArcaDev 4.3 certification. All Gaming Studio choices are TEST FIXTURE ONLY."""
from dataclasses import replace, FrozenInstanceError
from functools import lru_cache
import json
import unittest
from unittest.mock import patch

from arcadev import (
    ModelArea, ModelQuestion, ModelClarificationAnswer, ModelFinalization,
    ModelResolutionAction, ModelResolutionOutcome, model_question_id,
    generate_baseline_domain_model, resolve_model_clarification, BuildStage, ProjectStatus,
)
from arcadev.architecture_specification import _json
from tools.test_arcadev_domain_model_specification import models_handoff
from tools.test_arcadev_domain_model_engine import altered


def answer_for(state, question, values, *, raw=None, action="answer", prior=()):
    return ModelClarificationAnswer.create(target_model_id=state.original_model.model_id,
        target_finalization_id=state.finalization_id, target_question_id=question.question_id,
        user_answer=raw if raw is not None else "TEST FIXTURE ONLY: " + "; ".join(values),
        normalized_values=values, evidence=values, action=action, expected_prior_values=prior)


def fixture_choice(question, model):
    area = question.area
    if area is ModelArea.IDENTITY:
        return ("uuid",)
    if area is ModelArea.PRINCIPAL_REFERENCE:
        return ("external_principal_id",)
    if area is ModelArea.EXTERNAL_REFERENCE:
        return ("repository_id", "external_reference")
    if area is ModelArea.LIFECYCLE:
        entity = next(e for e in model.entities if e.entity_id in question.entity_ids)
        return ("pending", "running", "succeeded", "failed") if "build" in entity.responsibility.value.lower() else ("draft", "published", "failed")
    if area is ModelArea.RETENTION:
        return ("active", "deleted", "retained")
    if area is ModelArea.UNIQUENESS:
        return ("identity_only",)
    if area is ModelArea.LOOKUP:
        return ("identity",)
    if area is ModelArea.FIELD:
        build = next(e for e in model.entities if "build" in e.responsibility.value.lower())
        return (build.entity_id, "outcome_reference")
    if area is ModelArea.RELATIONSHIP:
        project = next(e for e in model.entities if "project" in e.responsibility.value.lower())
        return tuple(_json({"source_entity_id": project.entity_id, "target_entity_id": e.entity_id,
            "source_cardinality": "one", "target_cardinality": "many", "ownership": "source_owns_target",
            "deletion_behavior": "retain"}).strip() for e in model.entities if e != project)
    raise AssertionError("Fixture needs an explicit choice for " + area.value)


@lru_cache(maxsize=1)
def resolved_model():
    handoff = models_handoff()
    model = generate_baseline_domain_model(handoff)
    state = ModelFinalization.start(model, handoff=handoff)
    for question in model.open_model_questions:
        before = state
        answer = answer_for(state, question, fixture_choice(question, model))
        state = resolve_model_clarification(state, answer, handoff=handoff)
        assert state.history[-1].outcome is ModelResolutionOutcome.ACCEPTED
        assert len(state.unresolved_questions) == len(before.unresolved_questions) - 1
        assert set(state.unresolved_questions) == set(before.unresolved_questions) - {question}
        assert state.original_model == model
    return state


class ModelClarificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = models_handoff()
        cls.model = generate_baseline_domain_model(cls.handoff)
        cls.start = ModelFinalization.start(cls.model, handoff=cls.handoff)

    def question(self, area=ModelArea.IDENTITY):
        return next(q for q in self.start.unresolved_questions if q.area is area)

    def resolve(self, state, answer):
        return resolve_model_clarification(state, answer, handoff=self.handoff)

    def test_single_resolution_deterministic_traceable_and_unrelated_unchanged(self):
        q = self.question()
        answer = answer_for(self.start, q, ("uuid",), raw="  TEST FIXTURE ONLY: choose uuid.  ")
        state = self.resolve(self.start, answer)
        self.assertEqual(state.canonical_json(), self.resolve(self.start, answer.canonical_json()).canonical_json())
        decision = state.decisions[0]
        self.assertEqual(decision.user_answer, answer.user_answer)
        self.assertEqual(decision.source_question, q)
        self.assertEqual(decision.provenance, "explicit_user")
        self.assertEqual(decision.architecture_source_requirements, q.source_requirements)
        self.assertEqual(decision.affected_entity_ids, q.entity_ids)
        self.assertEqual(decision.claims[0].values, ("uuid",))
        self.assertEqual(set(state.unresolved_questions), set(self.start.unresolved_questions) - {q})
        self.assertFalse(state.effective_ready_for_approval)
        with self.assertRaises(FrozenInstanceError):
            decision.user_answer = "changed"

    def test_question_identity_uses_complete_content_and_canonical_order(self):
        q = self.question(ModelArea.RELATIONSHIP)
        equivalent = ModelQuestion.create(handoff=self.handoff, question=q.question, blocking=q.blocking,
            area=q.area, source_requirements=tuple(reversed(q.source_requirements)), entity_ids=tuple(reversed(q.entity_ids)))
        self.assertEqual(model_question_id(q), model_question_id(equivalent))
        for changes in ({"question": q.question + " Explicitly?"}, {"blocking": False}, {"area": ModelArea.LOOKUP}, {"entity_ids": q.entity_ids[:1]}):
            self.assertNotEqual(model_question_id(q), model_question_id(replace(q, **changes)))

    def test_complete_gaming_fixture_and_immutability(self):
        upstream, original = self.handoff.canonical_json(), self.model.canonical_json()
        state = resolved_model()
        self.assertFalse(self.start.effective_ready_for_approval)
        self.assertEqual(len(state.decisions), 22)
        self.assertEqual(len(state.history), 22)
        self.assertFalse(state.unresolved_questions)
        self.assertFalse(state.conflicts)
        self.assertTrue(state.effective_ready_for_approval)
        self.assertFalse(state.original_model.readiness.ready_for_finalization)
        self.assertEqual(state.original_model.canonical_json(), original)
        self.assertEqual(self.handoff.canonical_json(), upstream)
        self.assertEqual(state.original_model.project_stage, BuildStage.MODELS)
        self.assertEqual(self.handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        self.assertEqual(self.handoff.resulting_project.current_build_stage, BuildStage.MODELS)
        self.assertEqual(len(state.original_model.entities), 5)
        self.assertTrue(all(d.evidence and d.provenance == "explicit_user" for d in state.decisions))
        self.assertTrue(all(not h.readiness_after for h in state.history[:-1]))
        self.assertTrue(state.history[-1].readiness_after)

    def test_round_trip_replays_all_history_and_decisions(self):
        state = resolved_model()
        self.assertEqual(state, ModelFinalization.from_json(state.canonical_json(), handoff=self.handoff))
        self.assertEqual(self.start, ModelFinalization.from_dict(self.start.canonical_dict(), handoff=self.handoff))

    def test_stale_replay_and_already_resolved(self):
        q = self.question()
        answer = answer_for(self.start, q, ("uuid",))
        state = self.resolve(self.start, answer)
        for invalid in (answer, replace(answer, target_finalization_id=state.finalization_id), answer_for(state, q, ("string",))):
            with self.assertRaises(ValueError):
                self.resolve(state, invalid)

    def test_forged_targets_and_finalization_rejected(self):
        answer = answer_for(self.start, self.question(), ("uuid",))
        for key, prefix in (("target_model_id", "domain_model"), ("target_finalization_id", "model_final"), ("target_question_id", "model_question")):
            with self.assertRaises(ValueError):
                self.resolve(self.start, replace(answer, **{key: "arcadev_" + prefix + "_" + "f" * 32}))
        with self.assertRaises(ValueError):
            self.resolve(replace(self.start, effective_ready_for_approval=True), answer)

    def test_deliberate_replacement_and_exact_prior_conflict(self):
        q = self.question()
        state = self.resolve(self.start, answer_for(self.start, q, ("uuid",)))
        previous = state.decisions[0]
        wrong = answer_for(state, q, ("string",), action="replace_decision", prior=("integer",))
        conflict = self.resolve(state, wrong)
        self.assertEqual(conflict.decisions, state.decisions)
        self.assertEqual(conflict.history[-1].outcome, ModelResolutionOutcome.CONFLICT)
        correct = answer_for(conflict, q, ("string",), action="replace_decision", prior=("uuid",))
        replaced = self.resolve(conflict, correct)
        self.assertFalse(replaced.conflicts)
        self.assertEqual(replaced.decisions[0].replaces_decision_id, previous.decision_id)
        self.assertEqual(replaced.decisions[0].previous_values, ("uuid",))
        self.assertEqual(replaced.decisions[0].accepted_values, ("string",))
        self.assertEqual(replaced.unresolved_questions, state.unresolved_questions)
        self.assertEqual(replaced, ModelFinalization.from_json(replaced.canonical_json(), handoff=self.handoff))
        with self.assertRaises(ValueError):
            self.resolve(replaced, answer_for(replaced, q, ("string",), action="replace_decision", prior=("string",)))

    def test_invalid_actions_prior_values_and_evidence(self):
        q = self.question()
        for action, prior in (("approve", ()), ("answer", ("uuid",)), ("replace_decision", ())):
            with self.assertRaises(ValueError):
                answer_for(self.start, q, ("string",), action=action, prior=prior)
        with self.assertRaises(ValueError):
            self.resolve(self.start, answer_for(self.start, q, ("string",), action="replace_decision", prior=("uuid",)))
        for changes in ({"user_answer": "No quoted choice"}, {"evidence": ["missing"]}, {"provenance": "inferred"}):
            raw = answer_for(self.start, q, ("uuid",)).canonical_dict()
            raw.update(changes)
            with self.assertRaises(ValueError):
                self.resolve(self.start, raw)

    def test_architecture_contradictions_and_new_scope_are_blocking(self):
        q = self.question()
        for text in ("Remove RepositoryConnection because GitHub will not be supported", "Assets are never persisted and have no deletion state", "No build state is stored or tracked", "Add billing and subscriptions"):
            with self.subTest(text=text):
                state = self.resolve(self.start, answer_for(self.start, q, ("uuid",), raw=text + "; uuid"))
                self.assertFalse(state.decisions)
                self.assertEqual(state.unresolved_questions, self.start.unresolved_questions)
                self.assertFalse(state.effective_ready_for_approval)
                self.assertTrue(state.conflicts)
                self.assertEqual(state.original_model, self.model)

    def test_wrong_area_and_unsupported_choice_do_not_resolve(self):
        for values, code in ((("lookup: identity",), "question_area_conflict"), (("auto_increment",), "unsupported_model_choice"), (("DROP TABLE model",), "unsupported_model_choice")):
            state = self.resolve(self.start, answer_for(self.start, self.question(), values))
            self.assertEqual(state.conflicts[0].code, code)
            self.assertEqual(state.unresolved_questions, self.start.unresolved_questions)

    def test_accepted_decision_conflict_and_nonblocking_question(self):
        q = self.question()
        other = ModelQuestion.create(handoff=self.handoff, question="Confirm this identity representation explicitly?", blocking=False,
            area=q.area, source_requirements=q.source_requirements, entity_ids=q.entity_ids)
        model = altered(self.model, self.handoff, open_model_questions=self.model.open_model_questions + (other,))
        state = ModelFinalization.start(model, handoff=self.handoff)
        for original in model.open_model_questions:
            if original == other:
                continue
            state = self.resolve(state, answer_for(state, original, fixture_choice(original, model)))
        self.assertTrue(state.effective_ready_for_approval)
        conflict = self.resolve(state, answer_for(state, other, ("string",)))
        self.assertEqual(conflict.conflicts[0].code, "accepted_decision_conflict")
        self.assertFalse(conflict.effective_ready_for_approval)
        fixed = self.resolve(conflict, answer_for(conflict, other, ("uuid",)))
        self.assertTrue(fixed.effective_ready_for_approval)

    def test_relationship_scope_cardinality_and_nested_json_validation(self):
        q = self.question(ModelArea.RELATIONSHIP)
        choices = fixture_choice(q, self.model)
        raw = json.loads(choices[0])
        for changes in ({"target_entity_id": "foreign"}, {"target_cardinality": "unbounded_sql"}, {"ownership": "merge_architecture_owners"}, {"sql": "CREATE TABLE x"}):
            invalid = _json(dict(raw, **changes)).strip()
            state = self.resolve(self.start, answer_for(self.start, q, (invalid, *choices[1:])))
            self.assertTrue(state.conflicts)
            self.assertFalse(state.decisions)
        duplicate = choices[0][:-1] + ',"ownership":"independent"}'
        state = self.resolve(self.start, answer_for(self.start, q, (duplicate, *choices[1:])))
        self.assertTrue(state.conflicts)

    def test_independent_choice_conflicts_with_an_accepted_relationship(self):
        q = self.question(ModelArea.RELATIONSHIP)
        other = ModelQuestion.create(handoff=self.handoff, question="Confirm these records are independent?", blocking=False,
            area=q.area, source_requirements=q.source_requirements, entity_ids=q.entity_ids)
        model = altered(self.model, self.handoff, open_model_questions=self.model.open_model_questions + (other,))
        state = ModelFinalization.start(model, handoff=self.handoff)
        state = self.resolve(state, answer_for(state, q, fixture_choice(q, model)))
        conflict = self.resolve(state, answer_for(state, other, ("independent",)))
        self.assertEqual(conflict.conflicts[0].code, "accepted_decision_conflict")
        self.assertEqual(conflict.decisions, state.decisions)

    def test_outcome_reference_cannot_create_a_new_entity_or_store_credentials(self):
        q = self.question(ModelArea.FIELD)
        for values in (("new_test_run_entity", "outcome_reference"), (q.entity_ids[0], "password_field")):
            state = self.resolve(self.start, answer_for(self.start, q, values))
            self.assertTrue(state.conflicts)
            self.assertEqual(state.original_model, self.model)
        q = self.question(ModelArea.EXTERNAL_REFERENCE)
        state = self.resolve(self.start, answer_for(self.start, q, ("repository_id", "binary_reference")))
        self.assertTrue(state.conflicts)

    def test_forged_readiness_history_claims_and_original_rejected(self):
        state = resolved_model()
        for mutate in (
            lambda raw: raw.update(effective_ready_for_approval=False),
            lambda raw: raw.update(finalization_id="arcadev_model_final_" + "0" * 32),
            lambda raw: raw["history"][0].update(readiness_after=True),
            lambda raw: raw["history"].reverse(),
            lambda raw: raw["history"].pop(),
            lambda raw: raw["decisions"][0].update(provenance="inferred"),
            lambda raw: raw["decisions"][0]["claims"][0].update(values=["forged"]),
            lambda raw: raw["original_model"].update(model_id="forged"),
        ):
            raw = state.canonical_dict()
            mutate(raw)
            with self.assertRaises(ValueError):
                ModelFinalization.from_dict(raw, handoff=self.handoff)

    def test_schema_unknown_fields_and_malformed_json(self):
        answer = answer_for(self.start, self.question(), ("uuid",))
        for key, value in (("schema", "wrong"), ("schema_version", True), ("schema_version", 2), ("provider", "vendor"), ("normalized_values", "uuid")):
            raw = answer.canonical_dict()
            raw[key] = value
            with self.assertRaises(ValueError):
                self.resolve(self.start, raw)
        for raw in ("{", '{"schema":1,"schema":2}', "[]", "null", "[" * 1000, object()):
            with self.assertRaises(ValueError):
                self.resolve(self.start, raw)
        raw = self.start.canonical_dict()
        raw["extra"] = "no"
        with self.assertRaises(ValueError):
            ModelFinalization.from_dict(raw, handoff=self.handoff)

    def test_duplicates_unicode_control_secrets_and_private_keys(self):
        q = self.question()
        for values in (("uuid", "UUID"), ("uuid", "ｕｕｉｄ")):
            with self.assertRaises(ValueError):
                answer_for(self.start, q, values)
        for hostile in ("password=x", "access_token=abc", "ghp_abcdefghijklmnop", "sk-abcdefghijklmnopqrst", "Bearer opaque", "-----BEGIN PRIVATE KEY-----", "\ud800", "bad\x01", "line\nfeed"):
            with self.subTest(hostile=repr(hostile)), self.assertRaises(ValueError):
                answer_for(self.start, q, ("uuid",), raw="uuid " + hostile)

    def test_size_limits_and_executable_serialization(self):
        with self.assertRaises(ValueError):
            answer_for(self.start, self.question(), ("uuid",), raw="uuid " + "a" * 100_001)
        with self.assertRaises(ValueError):
            ModelFinalization.from_json(" " * 5_000_001, handoff=self.handoff)
        raw = self.start.canonical_dict()
        raw["history"] = [{}] * 257
        with self.assertRaises(ValueError):
            ModelFinalization.from_dict(raw, handoff=self.handoff)
        answer = answer_for(self.start, self.question(), ("uuid",)).canonical_dict()
        answer["user_answer"] = lambda: "uuid"
        with self.assertRaises(ValueError):
            self.resolve(self.start, answer)

    def test_code_sql_paths_and_commands_are_inert(self):
        raw = "TEST FIXTURE ONLY: uuid; DROP TABLE records; __import__('os').system('echo never'); $(echo never); C:/inert/path"
        answer = answer_for(self.start, self.question(), ("uuid",), raw=raw)
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), patch("builtins.eval", side_effect=AssertionError("eval")), patch("socket.create_connection", side_effect=AssertionError("network")), patch("builtins.open", side_effect=AssertionError("filesystem")):
            state = self.resolve(self.start, answer)
        self.assertEqual(state.decisions[0].user_answer, raw)
        self.assertEqual(state.original_model.project_stage, BuildStage.MODELS)
        for key in ("sql", "tables", "orm", "migrations", "apis", "backend", "generated_artifacts"):
            self.assertNotIn(key, state.canonical_dict())


if __name__ == "__main__":
    unittest.main()
