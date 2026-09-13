"""Actual production approvals: bounded referents, exact text and replay lineage."""

from copy import deepcopy
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

from arcadev.clarification import ClarificationAnswer, IdeaFinalization
from arcadev.gaming_studio_intent import (
    AUTHORITY_DIRECTORY, canonical_bytes, load_production_intent,
)
from arcadev.gaming_studio_resolution import (
    EVIDENCE, ORDER, PROPOSALS, RESPONSES, VALUES,
    authorization_package, replay_authorization, validate_authorization,
)
from arcadev.project import ArcaDevProject


class ProductionClarificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.intent = load_production_intent()
        cls.package = authorization_package(cls.intent)
        cls.data = canonical_bytes(cls.package)

    def reject(self, change):
        value = deepcopy(self.package)
        change(value)
        with self.assertRaises(ValueError):
            validate_authorization(canonical_bytes(value), self.intent)

    def test_persisted_five_exact_answers_and_referents(self):
        data = (AUTHORITY_DIRECTORY / "idea_resolution" / "clarification_authorization.json").read_bytes()
        self.assertEqual(data, self.data)
        self.assertEqual(len(self.package["approvals"]), 5)
        for i, approval in enumerate(self.package["approvals"]):
            with self.subTest(requirement=ORDER[i]):
                answer = ClarificationAnswer.from_dict(approval["answer"])
                self.assertEqual(answer.user_answer, RESPONSES[i])
                self.assertEqual(approval["approved_proposal"], PROPOSALS[i])
                self.assertEqual(answer.requirement, ORDER[i])
                self.assertEqual(set(answer.normalized_values), set(VALUES[i]))
                self.assertEqual(approval["provenance"], "explicit_user")
                self.assertEqual(answer.answer_provenance.value, "explicitly_stated")
                self.assertEqual(answer.evidence, (EVIDENCE[i],))
                self.assertIn(EVIDENCE[i], answer.user_answer)

    def test_sequential_identities_and_deterministic_history(self):
        result = replay_authorization(self.data, self.intent)
        self.assertEqual(result.canonical_json(), replay_authorization(self.data, self.intent).canonical_json())
        self.assertEqual(result, IdeaFinalization.from_json(result.canonical_json()))
        current = result.initial_intake_id
        seen = {current}
        for entry in result.history:
            self.assertEqual(entry.answer.target_intake_id, current)
            self.assertNotIn(entry.resulting_intake_id, seen)
            current = entry.resulting_intake_id
            seen.add(current)
        self.assertEqual(len(seen), 6)
        self.assertEqual([entry.outcome.value for entry in result.history], ["accepted"] * 5)
        self.assertFalse(result.conflicts)

    def test_refinement_requires_exact_previous_values_and_current_question(self):
        result = replay_authorization(self.data, self.intent)
        before = IdeaFinalization.start(result.initial_intake).resolve(result.history[0].answer)
        original = result.history[1].answer.canonical_dict()
        for changes in ({"expected_previous_values": []},
                        {"expected_previous_values": ["enterprise users"]},
                        {"requirement": "requested_features"},
                        {"normalized_values": original["expected_previous_values"]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                before.resolve(ClarificationAnswer.from_dict({**original, **changes}))
        duplicate = {**original, "target_intake_id": result.current_intake_id}
        with self.assertRaisesRegex(ValueError, "unresolved question"):
            result.resolve(ClarificationAnswer.from_dict(duplicate))

    def test_ordinary_answers_still_conflict_and_refinement_cannot_override_conflict(self):
        result = replay_authorization(self.data, self.intent)
        before = IdeaFinalization.start(result.initial_intake).resolve(result.history[0].answer)
        refinement = result.history[1].answer.canonical_dict()
        ordinary = {**refinement, "action": "answer", "expected_previous_values": []}
        conflict = before.resolve(ClarificationAnswer.from_dict(ordinary))
        self.assertEqual(conflict.history[-1].outcome.value, "conflict")
        with self.assertRaisesRegex(ValueError, "without conflicts"):
            conflict.resolve(ClarificationAnswer.from_dict({**refinement, "target_intake_id": conflict.current_intake_id}))

    def test_refinement_does_not_bypass_assumptions_or_missing_explicit_values(self):
        from arcadev.idea_intake import IdeaIntake, IntentValue
        result = replay_authorization(self.data, self.intent)
        before = IdeaFinalization.start(result.initial_intake).resolve(result.history[0].answer)
        refinement = result.history[1].answer.canonical_dict()
        for mode in ("assumption", "empty", "derived"):
            raw = before.current_intake.canonical_dict()
            if mode == "assumption":
                raw["assumptions"] = [IntentValue.create(
                    value="Unapproved audience assumption", provenance="inferred_assumption",
                    confidence="low", evidence=(), original_user_request=raw["original_user_request"],
                ).canonical_dict()]
            elif mode == "empty":
                raw["target_users"] = []
            else:
                raw["target_users"][0]["provenance"] = "deterministically_derived"
            # create recomputes readiness independently; no forged readiness.
            raw.pop("readiness")
            raw.pop("schema")
            raw.pop("schema_version")
            from arcadev.idea_intake import ClarificationRequirement
            for key, value in raw.items():
                if isinstance(value, dict):
                    raw[key] = IntentValue.create(**value, original_user_request=raw["original_user_request"])
                elif isinstance(value, list):
                    if key == "unresolved_requirements":
                        raw[key] = [ClarificationRequirement.create(
                            requirement=item["requirement"], question=item["question"],
                            blocking=item["blocking"], evidence=item["evidence"],
                            original_user_request=raw["original_user_request"],
                        ) for item in value]
                    else:
                        raw[key] = [IntentValue.create(**item, original_user_request=raw["original_user_request"]) for item in value]
            altered = IdeaFinalization.start(IdeaIntake.create(**raw))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                altered.resolve(ClarificationAnswer.from_dict({**refinement, "target_intake_id": altered.current_intake_id}))

    def test_changed_response_referent_values_evidence_and_scope_rejected(self):
        mutations = [
            lambda v: v["approvals"][1]["answer"].update(user_answer="I approve everything"),
            lambda v: v["approvals"][1].update(approved_proposal="AAA enterprise studios"),
            lambda v: v["approvals"][1]["answer"].update(normalized_values=["AAA studios"]),
            lambda v: v["approvals"][1]["answer"].update(evidence=[]),
            lambda v: v["approvals"][1]["answer"].update(evidence=[PROPOSALS[1]]),
            lambda v: v["approvals"][1]["answer"].update(requirement="deployment_requirements"),
            lambda v: v["approvals"][1]["answer"].update(answer_provenance="derived"),
            lambda v: v["approvals"][1]["answer"].update(user_answer="password=supersecret"),
            lambda v: v["approvals"][1].update(proposal_digest="0" * 64),
            lambda v: v["approvals"][1].update(relationship="blanket_approval"),
        ]
        for change in mutations:
            with self.subTest(change=mutations.index(change)):
                self.reject(change)

    def test_stale_duplicate_sixth_and_reordered_answers_rejected(self):
        self.reject(lambda v: v["approvals"][1]["answer"].update(target_intake_id=v["seed_intake_id"]))
        self.reject(lambda v: v["approvals"].append(deepcopy(v["approvals"][0])))
        self.reject(lambda v: v["approvals"].__setitem__(1, deepcopy(v["approvals"][0])))
        self.reject(lambda v: v["approvals"].reverse())
        result = replay_authorization(self.data, self.intent)
        with self.assertRaisesRegex(ValueError, "stale"):
            result.resolve(result.history[0].answer)
        duplicate = result.history[0].answer.canonical_dict()
        duplicate["target_intake_id"] = result.current_intake_id
        with self.assertRaisesRegex(ValueError, "already resolved"):
            result.resolve(ClarificationAnswer.from_dict(duplicate))

    def test_strict_schema_unknown_fields_and_bounded_json(self):
        for key, value in (("schema", "other"), ("schema_version", 2),
                           ("schema_version", True), ("unknown", "value")):
            with self.subTest(key=key, value=value):
                self.reject(lambda v: v.update({key: value}))
        for data in (b'{"schema":1,"schema":2}\n', b" " * 100001, b"\xff"):
            with self.assertRaises(ValueError):
                validate_authorization(data, self.intent)

    def test_platform_distinction_and_deferred_context_do_not_expand_scope(self):
        result = replay_authorization(self.data, self.intent)
        self.assertEqual({v.value for v in result.current_intake.platform_targets}, set(VALUES[2]))
        self.assertEqual(result.initial_intake.requested_features, result.current_intake.requested_features)
        self.assertEqual(result.initial_intake.explicit_constraints, result.current_intake.explicit_constraints)
        self.assertEqual(result.initial_intake.non_functional_requirements, result.current_intake.non_functional_requirements)
        self.assertFalse(result.current_intake.assumptions)
        for value in VALUES[3]:
            self.assertNotIn("upgrade", value.lower())
            self.assertNotIn("paid", value.lower())
        for note in self.package["deferred_context"].values():
            self.assertIn(note["quote"], RESPONSES[note["source_ordinal"] - 1])
        self.reject(lambda v: v["deferred_context"]["upgraded_access"].update(disposition="implement_billing"))

    def test_no_project_transition_execution_generation_or_writes(self):
        from arcadev.idea_plan_handoff import IdeaPlanHandoff
        from arcadev import planning_engine, backend_generation
        with patch.object(ArcaDevProject, "create", side_effect=AssertionError("project")), \
             patch.object(IdeaPlanHandoff, "create", side_effect=AssertionError("transition")), \
             patch.object(planning_engine, "generate_baseline_plan", side_effect=AssertionError("plan")), \
             patch.object(backend_generation, "generate_backend", side_effect=AssertionError("generation")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("execution")), \
             patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("write")):
            replay_authorization(self.data, self.intent)


if __name__ == "__main__":
    unittest.main()
