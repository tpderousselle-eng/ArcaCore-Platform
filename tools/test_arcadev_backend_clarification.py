"""5.3 certification. All Gaming Studio answers are explicit TEST FIXTURE ONLY."""
from dataclasses import replace, FrozenInstanceError
from functools import lru_cache
import unittest
from unittest.mock import patch

from arcadev import (
    BackendArea, BackendQuestion, BackendClarificationAnswer, BackendFinalization,
    BackendResolutionAction, BackendResolutionOutcome, backend_question_id,
    resolve_backend_clarification, BuildStage, ProjectStatus,
)
from tools.test_arcadev_backend_engine import backend_baseline, grouped_candidate
from tools.test_arcadev_backend_specification import backend_fixture_handoff, rebuild


def fixture_choice(question):
    return ({
        BackendArea.PERSISTENCE_MAPPING: "snake_case_unfixed_names",
        BackendArea.API_BOUNDARY: "http_json",
        BackendArea.TRANSACTION: "operation_atomic",
        BackendArea.ASYNC_EXECUTION: "authenticated_completion_callback",
        BackendArea.EXTERNAL_INTEGRATION: "no_automatic_retry",
        BackendArea.FAILURE_SEMANTICS: "return_failure_without_state_promotion",
        BackendArea.IDEMPOTENCY: "caller_request_key",
        BackendArea.STORAGE: "entity_identity_reference",
        BackendArea.IMPLEMENTATION_TECHNOLOGY: "require_generator_capability_certification",
    }[question.area],)


def answer_for(state, question, values=None, *, raw=None, action="answer", prior=()):
    values = fixture_choice(question) if values is None else values
    return BackendClarificationAnswer.create(target_backend_id=state.original_backend.backend_id,
        target_finalization_id=state.finalization_id, target_question_id=question.question_id,
        user_answer=raw if raw is not None else "TEST FIXTURE ONLY: " + "; ".join(values),
        normalized_values=values, evidence=values, action=action, expected_prior_values=prior)


@lru_cache(maxsize=1)
def resolved_backend():
    h, spec = backend_fixture_handoff(), backend_baseline()
    state = BackendFinalization.start(spec, handoff=h)
    for q in spec.open_backend_questions:
        before = state
        state = resolve_backend_clarification(state, answer_for(state, q), handoff=h)
        assert state.history[-1].outcome is BackendResolutionOutcome.ACCEPTED
        assert set(state.unresolved_questions) == set(before.unresolved_questions) - {q}
        assert state.original_backend == spec
    return state


class BackendClarificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff, cls.spec = backend_fixture_handoff(), backend_baseline()
        cls.start = BackendFinalization.start(cls.spec, handoff=cls.handoff)

    def question(self, area=BackendArea.API_BOUNDARY):
        return next(q for q in self.spec.open_backend_questions if q.area is area)

    def resolve(self, state, answer):
        return resolve_backend_clarification(state, answer, handoff=self.handoff)

    def test_single_answer_provenance_and_unrelated_questions(self):
        q = self.question()
        answer = answer_for(self.start, q, raw="  TEST FIXTURE ONLY: choose http_json.  ")
        state = self.resolve(self.start, answer)
        decision = state.decisions[0]
        self.assertEqual(state, self.resolve(self.start, answer.canonical_json()))
        self.assertEqual(decision.user_answer, answer.user_answer)
        self.assertEqual(decision.source_question, q)
        self.assertEqual(decision.provenance, "explicit_user")
        self.assertEqual(decision.evidence, answer.evidence)
        for field in ("architecture_source_ids", "model_source_ids", "component_ids", "operation_ids", "area"):
            self.assertEqual(getattr(decision, field), getattr(q, field))
        self.assertEqual(decision.claims[0].values, ("http_json", "preserve_authorization"))
        self.assertEqual(set(state.unresolved_questions), set(self.start.unresolved_questions) - {q})
        self.assertFalse(state.effective_ready_for_approval)
        with self.assertRaises(FrozenInstanceError): decision.user_answer = "changed"

    def test_complete_gaming_fixture_preserves_all_frozen_authority(self):
        upstream, original = self.handoff.canonical_json(), self.spec.canonical_json()
        state = resolved_backend()
        self.assertEqual((len(state.decisions), len(state.history)), (10, 10))
        self.assertFalse(state.unresolved_questions)
        self.assertFalse(state.conflicts)
        self.assertTrue(state.effective_ready_for_approval)
        self.assertFalse(self.start.effective_ready_for_approval)
        self.assertFalse(state.original_backend.readiness.ready_for_approval)
        self.assertEqual(state.original_backend.canonical_json(), original)
        self.assertEqual(self.handoff.canonical_json(), upstream)
        self.assertEqual(state.original_backend.resolved_model, self.handoff.frozen_approved_domain_model.package.resolved_model)
        self.assertEqual(state.original_backend.project_stage, BuildStage.BACKEND)
        self.assertEqual(self.handoff.resulting_project.current_build_stage, BuildStage.BACKEND)
        self.assertEqual(self.handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        self.assertTrue(all(not h.readiness_after for h in state.history[:-1]))
        self.assertTrue(state.history[-1].readiness_after)

    def test_question_identity_complete_content_and_canonical_order(self):
        q = self.question()
        payload = q.canonical_dict(); payload.pop("question_id")
        for key in ("architecture_source_ids", "model_source_ids", "component_ids", "operation_ids"):
            payload[key].reverse()
        equivalent = BackendQuestion.create(handoff=self.handoff, **payload)
        self.assertEqual(backend_question_id(q), backend_question_id(equivalent))
        for changes in ({"question": q.question + " Explicitly?"}, {"blocking": False},
            {"area": BackendArea.TRANSACTION}, {"component_ids": q.component_ids[:1]},
            {"operation_ids": q.operation_ids[:1]}, {"model_source_ids": ()}, {"architecture_source_ids": ()}):
            self.assertNotEqual(q.question_id, backend_question_id(replace(q, **changes)))

    def test_canonical_round_trip_replays_every_decision(self):
        for state in (self.start, resolved_backend()):
            self.assertEqual(state, BackendFinalization.from_json(state.canonical_json(), handoff=self.handoff))

    def test_multiple_answers_deterministic_history_and_decision_ids(self):
        states = []
        for _ in range(2):
            state = self.start
            for q in self.spec.open_backend_questions[:3]:
                state = self.resolve(state, answer_for(state, q))
            states.append(state)
        self.assertEqual(states[0].canonical_json(), states[1].canonical_json())
        self.assertEqual(len(states[0].decisions), 3)
        for event in states[0].history:
            self.assertEqual(event.accepted_values, event.answer.normalized_values)
            self.assertEqual(set(event.unresolved_after), set(event.unresolved_before) - {event.answer.target_question_id})

    def test_stale_replay_and_already_resolved_rejected(self):
        q = self.question()
        answer = answer_for(self.start, q)
        state = self.resolve(self.start, answer)
        for invalid in (answer, replace(answer, target_finalization_id=state.finalization_id),
                        answer_for(state, q, raw="Different explicit http_json evidence")):
            with self.assertRaises(ValueError): self.resolve(state, invalid)

    def test_forged_targets_and_nonexistent_question(self):
        answer = answer_for(self.start, self.question())
        for field, prefix in (("target_backend_id", "backend_specification"),
            ("target_finalization_id", "backend_final"), ("target_question_id", "backend_question")):
            for identity in ("malformed", "arcadev_" + prefix + "_" + "f" * 32):
                with self.assertRaises(ValueError): self.resolve(self.start, replace(answer, **{field: identity}))

    def test_wrong_handoff_and_forged_original_rejected(self):
        with self.assertRaises(ValueError):
            BackendFinalization.start(self.spec, handoff=replace(self.handoff, source_project_id="wrong"))
        raw = self.start.canonical_dict(); raw["original_backend"]["backend_id"] = "forged"
        with self.assertRaises(ValueError): BackendFinalization.from_dict(raw, handoff=self.handoff)

    def test_finalization_cannot_bypass_material_candidate_questions(self):
        missing = rebuild(self.spec, open_backend_questions=())
        self.assertTrue(missing.readiness.ready_for_approval)
        with self.assertRaises(ValueError): BackendFinalization.start(missing, handoff=self.handoff)

    def test_replacement_requires_explicit_action_exact_prior_and_preserves_history(self):
        q = self.question(BackendArea.EXTERNAL_INTEGRATION)
        old = self.resolve(self.start, answer_for(self.start, q))
        answer = answer_for(old, q, ("transient_retry_twice_no_delay",),
            action=BackendResolutionAction.REPLACE_DECISION, prior=("no_automatic_retry",))
        state = self.resolve(old, answer)
        decision = state.decisions[0]
        self.assertNotEqual(old.decisions[0].decision_id, decision.decision_id)
        self.assertEqual(decision.replaces_decision_id, old.decisions[0].decision_id)
        self.assertEqual(decision.previous_values, ("no_automatic_retry",))
        self.assertEqual(state.history[0], old.history[0])
        self.assertEqual(state.history[1].previous_values, ("no_automatic_retry",))
        self.assertIn("maximum_attempts_2", decision.claims[0].values)
        self.assertEqual(state, BackendFinalization.from_json(state.canonical_json(), handoff=self.handoff))

    def test_invalid_replacements_and_unchanged_replay(self):
        q = self.question(BackendArea.EXTERNAL_INTEGRATION)
        with self.assertRaises(ValueError): answer_for(self.start, q, action="replace_decision")
        with self.assertRaises(ValueError): answer_for(self.start, q, prior=("old",))
        with self.assertRaises(ValueError):
            self.resolve(self.start, answer_for(self.start, q, action="replace_decision", prior=("old",)))
        old = self.resolve(self.start, answer_for(self.start, q))
        with self.assertRaises(ValueError):
            self.resolve(old, answer_for(old, q, action="replace_decision", prior=("no_automatic_retry",)))
        conflict = self.resolve(old, answer_for(old, q, ("transient_retry_twice_no_delay",),
            action="replace_decision", prior=("wrong_prior",)))
        self.assertEqual(conflict.decisions, old.decisions)
        self.assertEqual(conflict.conflicts[0].code, "accepted_decision_conflict")
        self.assertEqual(conflict.history[-1].rejected_values, ("transient_retry_twice_no_delay",))

    def test_frozen_architecture_contradictions(self):
        q = self.question()
        for text in ("Do not implement GitHub integration", "Run builds directly inside the main request process",
                     "Replace PostgreSQL", "Disable authentication", "Remove managed object storage"):
            state = self.resolve(self.start, answer_for(self.start, q, raw=text + "; http_json"))
            self.assertEqual(state.conflicts[0].code, "frozen_architecture_conflict", text)
            self.assertFalse(state.decisions)
            self.assertEqual(state.unresolved_questions, self.start.unresolved_questions)

    def test_approved_model_relationship_and_identity_contradictions(self):
        model = self.spec.resolved_model
        choice = next(c.claim for e in model.entities for c in e.choices if c.claim.related_entity_id is not None)
        names = {e.entity_id: e.name for e in model.entities}
        text = names[choice.entity_id] + " persistence does not retain any " + names[choice.related_entity_id] + " relationship"
        for raw in (text, "Remove all logical relationships", "Change approved identities", "Drop approved fields"):
            state = self.resolve(self.start, answer_for(self.start, self.question(), raw=raw + "; http_json"))
            self.assertEqual(state.conflicts[0].code, "approved_domain_model_conflict")
            self.assertEqual(state.original_backend.resolved_model, model)

    def test_previous_backend_decision_conflict(self):
        q = self.question(BackendArea.EXTERNAL_INTEGRATION)
        advisory = self.advisory(q)
        spec = rebuild(self.spec, open_backend_questions=(*self.spec.open_backend_questions, advisory))
        state = BackendFinalization.start(spec, handoff=self.handoff)
        state = self.resolve(state, answer_for(state, q))
        conflict = self.resolve(state, answer_for(state, advisory, ("transient_retry_twice_no_delay",)))
        self.assertEqual(conflict.conflicts[0].code, "accepted_decision_conflict")
        self.assertEqual(conflict.decisions, state.decisions)
        self.assertIn(advisory, conflict.unresolved_questions)

    def advisory(self, q, **changes):
        payload = q.canonical_dict(); payload.pop("question_id")
        payload.update(question="Advisory review: " + q.question, blocking=False, **changes)
        return BackendQuestion.create(handoff=self.handoff, **payload)

    def test_conflict_recovery_keeps_rejected_history(self):
        q = self.question()
        bad = answer_for(self.start, q, raw="Do not implement GitHub integration; http_json")
        conflict = self.resolve(self.start, bad)
        with self.assertRaises(ValueError):
            self.resolve(conflict, replace(bad, target_finalization_id=conflict.finalization_id))
        state = self.resolve(conflict, answer_for(conflict, q))
        self.assertFalse(state.conflicts)
        self.assertEqual(state.history[0].outcome, BackendResolutionOutcome.CONFLICT)
        self.assertEqual(state.history[1].conflicts_before, conflict.conflicts)
        self.assertEqual(state.history[1].outcome, BackendResolutionOutcome.ACCEPTED)

    def test_backend_area_mismatch_and_unsupported_scope(self):
        for values, code in ((("operation_atomic",), "question_area_conflict"),
            (("transaction: operation_atomic",), "question_area_conflict"),
            (("invented_transport",), "unsupported_backend_choice"), (("add_payments",), "unsupported_product_scope")):
            state = self.resolve(self.start, answer_for(self.start, self.question(), values))
            self.assertEqual(state.conflicts[0].code, code)
        state = self.resolve(self.start, answer_for(self.start, self.question(), raw="Add payment processing; http_json"))
        self.assertEqual(state.conflicts[0].code, "unsupported_product_scope")

    def test_uncertified_generator_representation_is_a_conflict(self):
        q = self.question(BackendArea.IMPLEMENTATION_TECHNOLOGY)
        state = self.resolve(self.start, answer_for(self.start, q, ("all_handlers_already_supported",)))
        self.assertEqual(state.conflicts[0].code, "uncertified_generator_representation")
        self.assertFalse(state.effective_ready_for_approval)

    def test_compatibility_decision_is_only_a_future_precondition(self):
        decision = next(d for d in resolved_backend().decisions if d.area is BackendArea.IMPLEMENTATION_TECHNOLOGY)
        self.assertEqual(decision.claims[0].values, ("certify_all_approved_responsibilities_before_generation", "fail_closed_on_unrepresented_capability"))
        self.assertEqual(set(decision.component_ids), {c.component_id for c in self.spec.components})

    def test_advisory_without_operation_scope_cannot_grant_claims(self):
        advisory = self.advisory(self.question(), operation_ids=[])
        spec = rebuild(self.spec, open_backend_questions=(*self.spec.open_backend_questions, advisory))
        state = BackendFinalization.start(spec, handoff=self.handoff)
        state = self.resolve(state, answer_for(state, advisory))
        self.assertEqual(state.conflicts[0].code, "question_scope_conflict")

    def test_nonblocking_advisory_can_remain_open_but_conflict_blocks_readiness(self):
        advisory = self.advisory(self.question(BackendArea.EXTERNAL_INTEGRATION))
        spec = rebuild(self.spec, open_backend_questions=(*self.spec.open_backend_questions, advisory))
        state = BackendFinalization.start(spec, handoff=self.handoff)
        for q in self.spec.open_backend_questions: state = self.resolve(state, answer_for(state, q))
        self.assertTrue(state.effective_ready_for_approval)
        self.assertEqual(state.unresolved_questions, (advisory,))
        state = self.resolve(state, answer_for(state, advisory, ("transient_retry_twice_no_delay",)))
        self.assertFalse(state.effective_ready_for_approval)
        state = self.resolve(state, answer_for(state, advisory))
        self.assertTrue(state.effective_ready_for_approval)

    def test_grouped_owner_questions_resolve_without_broadening_scope(self):
        spec = grouped_candidate(self.spec)
        state = BackendFinalization.start(spec, handoff=self.handoff)
        for q in spec.open_backend_questions: state = self.resolve(state, answer_for(state, q))
        self.assertTrue(state.effective_ready_for_approval)
        self.assertEqual(state.original_backend, spec)
        idempotency = [d for d in state.decisions if d.area is BackendArea.IDEMPOTENCY]
        self.assertEqual(len(idempotency), 2)
        self.assertFalse(set(idempotency[0].operation_ids) & set(idempotency[1].operation_ids))
        self.assertTrue(all(d.claims[0].operation_ids == d.operation_ids for d in state.decisions))

    def test_forged_readiness_history_and_decision_payload_rejected(self):
        state = resolved_backend()
        mutations = (
            lambda r: r.update(finalization_id="forged"), lambda r: r.update(effective_ready_for_approval=False),
            lambda r: r["history"][0].update(readiness_after=True), lambda r: r["history"].reverse(),
            lambda r: r["history"][0].update(rejected_values=["forged"]),
            lambda r: r["decisions"][0].update(user_answer="rewritten"),
            lambda r: r["decisions"][0]["claims"][0].update(operation_ids=["invented"]),
            lambda r: r["decisions"][0]["claims"][0].update(values=["__import__('os').system('echo unsafe')"]),
        )
        for mutate in mutations:
            raw = state.canonical_dict(); mutate(raw)
            with self.assertRaises(ValueError): BackendFinalization.from_dict(raw, handoff=self.handoff)
        with self.assertRaises(ValueError):
            self.resolve(replace(self.start, effective_ready_for_approval=True), answer_for(self.start, self.question()))

    def test_unknown_fields_invalid_schemas_and_collection_types(self):
        answer = answer_for(self.start, self.question()).canonical_dict()
        for changes in ({"extra": "untrusted"}, {"schema": "other"}, {"schema_version": True},
            {"schema_version": 2}, {"provenance": "ai"}, {"normalized_values": "http_json"},
            {"evidence": {}}, {"expected_prior_values": ()}, {"action": "approve"}):
            raw = dict(answer); raw.update(changes)
            with self.assertRaises(ValueError): BackendClarificationAnswer.from_dict(raw)
        for changes in ({"extra": 1}, {"schema_version": True}, {"schema_version": 2},
            {"schema": "other"}, {"history": {}}, {"effective_ready_for_approval": 1}):
            raw = self.start.canonical_dict(); raw.update(changes)
            with self.assertRaises(ValueError): BackendFinalization.from_dict(raw, handoff=self.handoff)

    def test_malformed_json_duplicate_keys_and_executable_objects(self):
        for raw in ("{", '{"schema":1,"schema":2}', '[]', 'null'):
            with self.assertRaises(ValueError): BackendClarificationAnswer.from_json(raw)
            with self.assertRaises(ValueError): BackendFinalization.from_json(raw, handoff=self.handoff)
        for raw in (object(), lambda: None):
            with self.assertRaises(ValueError): self.resolve(self.start, raw)
        answer = answer_for(self.start, self.question()).canonical_dict(); answer["evidence"] = [object()]
        with self.assertRaises(ValueError): BackendClarificationAnswer.from_dict(answer)

    def test_duplicate_normalized_values_and_exact_evidence_required(self):
        for values in (("http_json", "http_json"), ("http_json", "HTTP_JSON"), ("http_json", "ｈｔｔｐ_json")):
            with self.assertRaises(ValueError): answer_for(self.start, self.question(), values)
        answer = answer_for(self.start, self.question()).canonical_dict()
        for changes in ({"normalized_values": ["invented"]}, {"evidence": ["missing"]},
                        {"evidence": ["TEST FIXTURE"]}, {"evidence": []}):
            raw = dict(answer); raw.update(changes)
            with self.assertRaises(ValueError): BackendClarificationAnswer.from_dict(raw)

    def test_credentials_tokens_unicode_and_controls_rejected(self):
        for raw in ("password=x", "access_token=x", "ghp_abcdefghijklmnop", "Bearer opaque",
                    "-----BEGIN PRIVATE KEY-----", "\ud800", "\x00"):
            with self.assertRaises(ValueError): answer_for(self.start, self.question(), raw=raw + "; http_json")

    def test_oversized_answer_document_and_history_rejected(self):
        with self.assertRaises(ValueError): answer_for(self.start, self.question(), raw="http_json" + "x" * 100_001)
        with self.assertRaises(ValueError): BackendFinalization.from_json(" " * 5_000_001, handoff=self.handoff)
        raw = self.start.canonical_dict(); raw["history"] = [{}] * 257
        with self.assertRaises(ValueError): BackendFinalization.from_dict(raw, handoff=self.handoff)

    def test_hostile_code_sql_shell_stays_inert_and_never_becomes_claims(self):
        raw = "TEST FIXTURE: http_json; DROP TABLE x; __import__('os'); $(echo inert)"
        answer = answer_for(self.start, self.question(), raw=raw)
        with patch("tools.generate.generate_module", side_effect=AssertionError("generator")), \
             patch("subprocess.Popen", side_effect=AssertionError("execution")), \
             patch("socket.create_connection", side_effect=AssertionError("network")), \
             patch("builtins.open", side_effect=AssertionError("file")), \
             patch("os.system", side_effect=AssertionError("shell")), \
             patch("builtins.eval", side_effect=AssertionError("eval")):
            state = self.resolve(self.start, answer)
        self.assertEqual(state.decisions[0].user_answer, raw)
        self.assertEqual(state.decisions[0].claims[0].values, ("http_json", "preserve_authorization"))
        self.assertEqual(state.original_backend.project_stage, BuildStage.BACKEND)
        for text in ("DROP TABLE x", "__import__('os')", "$(echo inert)"):
            conflict = self.resolve(self.start, answer_for(self.start, self.question(), (text,)))
            self.assertEqual(conflict.conflicts[0].code, "unsupported_backend_choice")


if __name__ == "__main__":
    unittest.main()
