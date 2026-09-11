"""ArcaDev 3.3 certification. All implementation choices here are TEST ONLY."""
import copy
from dataclasses import replace
import unittest
from unittest.mock import patch

from arcadev import (
    ArchitectureArea, ArchitectureQuestion, ArchitectureSpecification,
    ArchitectureClarificationAnswer, ArchitectureFinalization,
    ArchitectureResolutionAction, ArchitectureResolutionOutcome,
    BuildStage, ProjectStatus, architecture_question_id,
    generate_baseline_architecture, resolve_architecture_clarification,
)
from tools.test_arcadev_architecture_specification import approved_handoff


def fixture_choice(question):
    choices = {
        "frontend implementation": "React web frontend",
        "primary persistence": "PostgreSQL primary relational persistence",
        "asset storage": "Managed object storage with explicit deletion-policy enforcement",
        "worker isolation": "One isolated OCI container per build with bounded permissions",
        "background job": "Persisted job records and leased worker execution with idempotent job identifiers",
        "synchronization implementation": "Explicit user-triggered repository synchronization through an authorized API adapter",
        "publishing implementation": "A release adapter invoked only by explicit user release actions",
        "deployment-unit topology": "Separate web, application, storage, and isolated worker units within ArcaCentum managed cloud",
    }
    return next(value for fragment, value in choices.items() if fragment in question.question)


def answer_for(state, question, value, *, action=ArchitectureResolutionAction.ANSWER, prior=(), raw=None):
    return ArchitectureClarificationAnswer.create(target_architecture_id=state.original_architecture.architecture_id,
        target_finalization_id=state.finalization_id, target_question_id=architecture_question_id(question),
        user_answer=raw if raw is not None else "TEST FIXTURE ONLY: " + value,
        normalized_values=(value,), evidence=(value,), action=action, expected_prior_values=prior)


class ArcaDevArchitectureClarificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = approved_handoff()
        cls.frozen_before = cls.handoff.canonical_json()
        cls.spec = generate_baseline_architecture(cls.handoff)
        cls.architecture_before = cls.spec.canonical_json()
        cls.initial = ArchitectureFinalization.start(cls.spec, handoff=cls.handoff)
        cls.states, cls.answers = [cls.initial], []
        for question in cls.initial.unresolved_questions:
            answer = answer_for(cls.states[-1], question, fixture_choice(question))
            cls.answers.append(answer)
            cls.states.append(cls.states[-1].resolve(answer, handoff=cls.handoff))
        cls.complete = cls.states[-1]

    def load(self, value):
        return ArchitectureFinalization.from_dict(value, handoff=self.handoff)

    def test_complete_gaming_studio_fixture(self):
        self.assertFalse(self.initial.effective_ready_for_approval)
        self.assertEqual(len(self.complete.decisions), 8)
        self.assertEqual(self.complete.unresolved_questions, ())
        self.assertEqual(self.complete.conflicts, ())
        self.assertTrue(self.complete.effective_ready_for_approval)
        self.assertFalse(self.complete.original_architecture.readiness.ready_for_finalization)
        self.assertEqual(len(self.complete.history), 8)

    def test_each_answer_resolves_exactly_one_question(self):
        for before, after, answer in zip(self.states, self.states[1:], self.answers):
            before_ids = {architecture_question_id(q): q for q in before.unresolved_questions}
            after_ids = {architecture_question_id(q): q for q in after.unresolved_questions}
            self.assertEqual(set(before_ids) - set(after_ids), {answer.target_question_id})
            self.assertEqual(after_ids, {key: value for key, value in before_ids.items() if key != answer.target_question_id})
            self.assertEqual(after.history[:-1], before.history)

    def test_upstream_and_original_architecture_immutable(self):
        for state in self.states:
            self.assertEqual(state.original_architecture.canonical_json(), self.architecture_before)
        self.assertEqual(self.frozen_before, self.handoff.canonical_json())
        with self.assertRaises(AttributeError):
            self.complete.effective_ready_for_approval = False

    def test_question_and_decision_identity_deterministic(self):
        q = self.initial.unresolved_questions[0]
        equivalent = ArchitectureQuestion.create(q.question, q.blocking, tuple(reversed(q.source_requirements)), q.area, handoff=self.handoff)
        self.assertEqual(architecture_question_id(q), architecture_question_id(equivalent))
        repeated = self.initial.resolve(self.answers[0], handoff=self.handoff)
        self.assertEqual(repeated.canonical_json(), self.states[1].canonical_json())
        self.assertEqual(repeated.decisions[0].decision_id, self.states[1].decisions[0].decision_id)

    def test_explicit_decision_traceability_and_unchanged_answer(self):
        for decision in self.complete.decisions:
            answer = next(a for a in self.answers if a.target_question_id == decision.question_id)
            self.assertEqual(decision.user_answer, answer.user_answer)
            self.assertEqual(decision.provenance, "explicit_user")
            self.assertEqual(decision.area, decision.source_question.area)
            self.assertEqual(decision.plan_source_requirements, decision.source_question.source_requirements)
            self.assertEqual(decision.evidence, answer.evidence)
            self.assertEqual(decision.accepted_values, answer.normalized_values)
        q = self.initial.unresolved_questions[0]
        text = "  TEST ONLY: " + fixture_choice(q) + "  "
        answer = answer_for(self.initial, q, fixture_choice(q), raw=text)
        self.assertEqual(answer.user_answer, text)

    def test_canonical_round_trip_and_resolution_boundary(self):
        self.assertEqual(ArchitectureFinalization.from_json(self.complete.canonical_json(), handoff=self.handoff), self.complete)
        answer = self.answers[0]
        self.assertEqual(ArchitectureClarificationAnswer.from_json(answer.canonical_json()), answer)
        for candidate in (answer, answer.canonical_dict(), answer.canonical_json()):
            self.assertEqual(resolve_architecture_clarification(self.initial, candidate, handoff=self.handoff), self.states[1])
        with self.assertRaises(ValueError):
            resolve_architecture_clarification(self.initial, object(), handoff=self.handoff)

    def test_stale_and_replayed_answers_rejected(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            self.states[1].resolve(self.answers[0], handoff=self.handoff)
        repeated = replace(self.answers[0], target_finalization_id=self.states[1].finalization_id)
        with self.assertRaisesRegex(ValueError, "Duplicate|replayed"):
            self.states[1].resolve(repeated, handoff=self.handoff)

    def test_already_resolved_requires_deliberate_replacement(self):
        q = self.initial.unresolved_questions[0]
        answer = answer_for(self.states[1], q, "A different explicit implementation")
        with self.assertRaisesRegex(ValueError, "already resolved"):
            self.states[1].resolve(answer, handoff=self.handoff)

    def test_nonexistent_and_forged_targets_rejected(self):
        for key, prefix in (("target_architecture_id", "architecture"), ("target_finalization_id", "architecture_final"), ("target_question_id", "architecture_question")):
            answer = replace(self.answers[0], **{key: "arcadev_" + prefix + "_" + "0" * 32})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.initial.resolve(answer, handoff=self.handoff)

    def test_deliberate_replacement_records_exact_prior_values(self):
        q = self.initial.unresolved_questions[0]
        previous = self.states[1].decisions[0]
        answer = answer_for(self.states[1], q, "Alternative explicit test implementation", action="replace_decision", prior=previous.accepted_values)
        updated = self.states[1].resolve(answer, handoff=self.handoff)
        decision = updated.decisions[0]
        self.assertEqual(decision.replaces_decision_id, previous.decision_id)
        self.assertEqual(decision.previous_values, previous.accepted_values)
        self.assertEqual(updated.history[-1].previous_values, previous.accepted_values)
        self.assertEqual(updated.unresolved_questions, self.states[1].unresolved_questions)
        self.assertEqual(self.load(updated.canonical_dict()), updated)

    def test_invalid_replacement_is_explicit_blocking_conflict(self):
        q = self.initial.unresolved_questions[0]
        answer = answer_for(self.states[1], q, "Alternative implementation", action="replace_decision", prior=("Wrong prior value",))
        result = self.states[1].resolve(answer, handoff=self.handoff)
        self.assertEqual(result.decisions, self.states[1].decisions)
        self.assertEqual(result.history[-1].outcome, ArchitectureResolutionOutcome.CONFLICT)
        self.assertEqual(result.history[-1].rejected_values, answer.normalized_values)
        self.assertFalse(result.effective_ready_for_approval)
        with self.assertRaises(ValueError):
            self.initial.resolve(answer_for(self.initial, q, "Replace absent", action="replace_decision", prior=("Absent",)), handoff=self.handoff)
        previous = self.states[1].decisions[0].accepted_values
        with self.assertRaises(ValueError):
            self.states[1].resolve(answer_for(self.states[1], q, previous[0], action="replace_decision", prior=previous), handoff=self.handoff)

    def test_plan_authority_contradictions_are_blocking_conflicts(self):
        q = self.initial.unresolved_questions[0]
        for value in ("Remove GitHub", "No GitHub", "Replace GitHub with GitLab", "Use GitLab instead of GitHub",
                      "Mobile web only", "Only Email/password", "iOS native only", "Only passkeys", "Self-hosted only",
                      "platform=Desktop web", "authentication=Email/password", "integration=GitLab",
                      "deployment=Self-hosted", "capability=Billing", "Remove deletion controls",
                      "Use unisolated build workers", "Use automatic publishing", "Synchronize without user authorization"):
            with self.subTest(value=value):
                result = self.initial.resolve(answer_for(self.initial, q, value), handoff=self.handoff)
                self.assertEqual(result.conflicts[0].code, "frozen_plan_conflict")
                self.assertEqual(result.decisions, ())
                self.assertEqual(result.unresolved_questions, self.initial.unresolved_questions)
                self.assertFalse(result.effective_ready_for_approval)

    def test_conflict_resolution_preserves_other_questions(self):
        q = self.initial.unresolved_questions[0]
        conflicted = self.initial.resolve(answer_for(self.initial, q, "Remove GitHub"), handoff=self.handoff)
        corrected = conflicted.resolve(answer_for(conflicted, q, fixture_choice(q)), handoff=self.handoff)
        self.assertEqual(corrected.conflicts, ())
        self.assertEqual(len(corrected.unresolved_questions), 7)
        self.assertEqual(corrected.history[-1].conflicts_before, conflicted.conflicts)
        self.assertEqual(self.load(corrected.canonical_dict()), corrected)

    def test_duplicate_conflicting_answer_cannot_be_replayed(self):
        q = self.initial.unresolved_questions[0]
        answer = answer_for(self.initial, q, "Remove GitHub")
        state = self.initial.resolve(answer, handoff=self.handoff)
        repeated = replace(answer, target_finalization_id=state.finalization_id)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            state.resolve(repeated, handoff=self.handoff)

    def test_correcting_one_conflict_preserves_unrelated_conflict(self):
        first, second = self.initial.unresolved_questions[:2]
        state = self.initial.resolve(answer_for(self.initial, first, "Remove GitHub"), handoff=self.handoff)
        state = state.resolve(answer_for(state, second, "iOS native only"), handoff=self.handoff)
        other_conflict = next(c for c in state.conflicts if c.question_id == architecture_question_id(second))
        corrected = state.resolve(answer_for(state, first, fixture_choice(first)), handoff=self.handoff)
        self.assertEqual(corrected.conflicts, (other_conflict,))
        self.assertIn(second, corrected.unresolved_questions)
        self.assertFalse(corrected.effective_ready_for_approval)

    def test_nonblocking_question_does_not_prevent_effective_readiness(self):
        optional = ArchitectureQuestion.create("Which optional documentation format should describe these boundaries?", False,
            self.spec.objective.source_requirements, ArchitectureArea.CONTEXT, handoff=self.handoff)
        names = ("objective", "system_boundary", "style", "external_entities", "approved_constraints", "components", "interfaces", "data_flows", "aspects", "open_architecture_questions")
        args = {name: getattr(self.spec, name) for name in names}
        args["open_architecture_questions"] += (optional,)
        architecture = ArchitectureSpecification.create(handoff=self.handoff, **args)
        state = ArchitectureFinalization.start(architecture, handoff=self.handoff)
        for q in architecture.open_architecture_questions:
            if q.blocking:
                state = state.resolve(answer_for(state, q, fixture_choice(q)), handoff=self.handoff)
        self.assertTrue(state.effective_ready_for_approval)
        self.assertEqual(state.unresolved_questions, (optional,))

    def test_conflicting_accepted_architecture_decision(self):
        q = next(q for q in self.spec.open_architecture_questions if q.area is ArchitectureArea.FRONTEND)
        other = ArchitectureQuestion.create("Which frontend implementation variant is explicitly accepted?", True, q.source_requirements, q.area, handoff=self.handoff)
        names = ("objective", "system_boundary", "style", "external_entities", "approved_constraints", "components", "interfaces", "data_flows", "aspects", "open_architecture_questions")
        args = {name: getattr(self.spec, name) for name in names}
        args["open_architecture_questions"] += (other,)
        architecture = ArchitectureSpecification.create(handoff=self.handoff, **args)
        state = ArchitectureFinalization.start(architecture, handoff=self.handoff)
        state = state.resolve(answer_for(state, q, "frontend=React"), handoff=self.handoff)
        conflicted = state.resolve(answer_for(state, other, "frontend=Vue"), handoff=self.handoff)
        self.assertEqual(conflicted.conflicts[0].code, "accepted_decision_conflict")
        self.assertEqual(conflicted.decisions, state.decisions)
        self.assertIn(other, conflicted.unresolved_questions)
        self.assertEqual(self.load(conflicted.canonical_dict()), conflicted)

    def test_answer_cannot_resolve_a_different_area(self):
        q = next(q for q in self.initial.unresolved_questions if q.area is ArchitectureArea.STORAGE)
        result = self.initial.resolve(answer_for(self.initial, q, "frontend=React"), handoff=self.handoff)
        self.assertEqual(result.conflicts[0].code, "question_area_conflict")
        self.assertIn(q, result.unresolved_questions)

    def test_history_is_deterministic_and_complete(self):
        restored = self.load(self.complete.canonical_dict())
        self.assertEqual(restored.history, self.complete.history)
        for before, after in zip(self.states, self.states[1:]):
            event = after.history[-1]
            self.assertEqual(event.readiness_before, before.effective_ready_for_approval)
            self.assertEqual(event.readiness_after, after.effective_ready_for_approval)
            self.assertEqual(event.unresolved_before, tuple(sorted(architecture_question_id(q) for q in before.unresolved_questions)))
            self.assertEqual(event.unresolved_after, tuple(sorted(architecture_question_id(q) for q in after.unresolved_questions)))
            self.assertEqual(event.outcome, ArchitectureResolutionOutcome.ACCEPTED)

    def test_forged_state_and_readiness_rejected(self):
        for key, value in (("effective_ready_for_approval", True), ("effective_ready_for_approval", 0), ("finalization_id", "forged"), ("unresolved_questions", [])):
            raw = self.initial.canonical_dict()
            raw[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load(raw)
        forged = replace(self.initial, effective_ready_for_approval=True)
        with self.assertRaises(ValueError):
            forged.resolve(self.answers[0], handoff=self.handoff)
        raw = self.states[1].canonical_dict()
        raw["decisions"][0]["accepted_values"] = ["Forged technology"]
        with self.assertRaises(ValueError):
            self.load(raw)
        raw = self.initial.canonical_dict()
        raw["original_architecture"]["architecture_id"] = "forged"
        with self.assertRaises(ValueError):
            self.load(raw)
        with self.assertRaises(ValueError):
            ArchitectureFinalization.from_dict(self.initial.canonical_dict(), handoff=replace(self.handoff, handoff_id="forged"))

    def test_forged_history_fields_and_boolean_coercion_rejected(self):
        for field, value in (("accepted_values", ["forged"]), ("resulting_decision_id", "forged"), ("readiness_after", 0),
                             ("unresolved_after", []), ("previous_values", ["forged"]), ("conflicts_after", ["forged"])):
            raw = self.states[1].canonical_dict()
            raw["history"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.load(raw)
        raw = self.states[2].canonical_dict()
        raw["history"].reverse()
        with self.assertRaises(ValueError):
            self.load(raw)

    def test_answer_schema_shape_actions_evidence_and_duplicates(self):
        for key, value in (("provider", "model"), ("schema", "wrong"), ("schema_version", True), ("schema_version", 2),
                           ("provenance", "model"), ("action", "approve"), ("normalized_values", ["duplicate", "DUPLICATE"]),
                           ("evidence", ["Absent evidence"]), ("normalized_values", ["Unstated choice"]), ("expected_prior_values", ["Unexpected"]),
                           ("target_question_id", "arcadev_architecture_question_" + "z" * 32)):
            raw = self.answers[0].canonical_dict()
            raw[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                ArchitectureClarificationAnswer.from_dict(raw)
        with self.assertRaises(ValueError):
            answer_for(self.initial, self.initial.unresolved_questions[0], "Choice", action="replace_decision")

    def test_finalization_schema_shape_and_oversize(self):
        for key, value in (("provider", "model"), ("schema", "wrong"), ("schema_version", True), ("schema_version", 2), ("history", {}), ("decisions", object())):
            raw = self.initial.canonical_dict()
            raw[key] = value
            with self.assertRaises(ValueError):
                self.load(raw)
        raw = self.states[1].canonical_dict()
        raw["history"] *= 257
        with self.assertRaises(ValueError):
            self.load(raw)
        with self.assertRaises(ValueError):
            ArchitectureFinalization.from_json(" " * 5_000_001, handoff=self.handoff)

    def test_secrets_controls_unicode_malformed_json_and_objects(self):
        for value in ("secret=abcdef", "-----BEGIN OPENSSH PRIVATE KEY-----", "bad\x00", "bad\n", "bad\ud800", "x" * 100_001):
            raw = self.answers[0].canonical_dict()
            raw["user_answer"] = value
            with self.assertRaises(ValueError):
                ArchitectureClarificationAnswer.from_dict(raw)
        for text in ("{", '{"schema":1,"schema":2}', "[" * 1000, " " * 5_000_001):
            with self.assertRaises(ValueError):
                ArchitectureClarificationAnswer.from_json(text)
            with self.assertRaises(ValueError):
                ArchitectureFinalization.from_json(text, handoff=self.handoff)

    def test_hostile_commands_remain_inert(self):
        q = next(q for q in self.initial.unresolved_questions if q.area is ArchitectureArea.FRONTEND)
        value = "frontend=React"
        answer = answer_for(self.initial, q, value, raw="TEST ONLY: " + value + "; inert: __import__('os').system('echo hostile'); $(cmd /c whoami)")
        before = self.handoff.canonical_json()
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), patch("builtins.eval", side_effect=AssertionError("eval")), patch("socket.create_connection", side_effect=AssertionError("network")):
            state = self.initial.resolve(answer, handoff=self.handoff)
            self.assertEqual(state.decisions[0].user_answer, answer.user_answer)
        self.assertEqual(self.handoff.canonical_json(), before)

    def test_no_approval_models_or_generation_and_stage_unchanged(self):
        self.assertEqual(self.complete.original_architecture.project_stage, BuildStage.ARCHITECTURE)
        self.assertEqual(self.handoff.resulting_project.current_build_stage, BuildStage.ARCHITECTURE)
        self.assertEqual(self.handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        for value in (self.initial, self.complete):
            for field in ("approved", "models", "backend", "frontend", "generated_artifacts"):
                self.assertFalse(hasattr(value, field))


if __name__ == "__main__":
    unittest.main()
