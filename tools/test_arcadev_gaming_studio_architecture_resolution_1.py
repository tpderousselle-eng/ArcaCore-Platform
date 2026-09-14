"""Verbatim eight-question authority and rejection of new or redirected authority."""

from contextlib import ExitStack
import copy
import json
import unittest
from unittest.mock import patch

from arcadev import gaming_studio_architecture_resolution as production
from arcadev.architecture_clarification import ArchitectureClarificationAnswer, ArchitectureFinalization
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes


class ArchitectureClarificationAuthorizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (AUTHORITY_DIRECTORY / production.RESOLUTION_AREA / "clarification_authorization.json").read_bytes()
        cls.value = json.loads(cls.raw)

    def reject(self, change):
        value = copy.deepcopy(self.value)
        change(value)
        with self.assertRaises(ValueError):
            production.validate_architecture_authorization(canonical_bytes(value))

    def test_exact_full_response_and_deterministic_digest(self):
        self.assertEqual(self.value["full_user_response"], production.FULL_RESPONSE)
        self.assertEqual(self.value["full_user_response_digest"],
                         "1b6eb81b0d0152373c674d86eda2150857458ee8e9f8554804ba5057b3cd9755")
        self.assertEqual(digest_bytes(production.FULL_RESPONSE.encode("utf-8")),
                         self.value["full_user_response_digest"])
        paragraphs = production.FULL_RESPONSE.split("\r\n\r\n")
        self.assertEqual(paragraphs[1:9], [f"{i}. {s}" for i, s in enumerate(production.RESPONSES, 1)])
        self.assertEqual(len(paragraphs), 10)
        self.assertEqual(canonical_bytes(self.value), self.raw)

    def test_exact_manifest_question_identity_text_area_and_order(self):
        request = json.loads((AUTHORITY_DIRECTORY / "production_architecture/clarification_request.json").read_bytes())
        self.assertEqual(self.value["answer_order"], list(production.ORDER))
        self.assertEqual(len(self.value["approvals"]), 8)
        for approval, question in zip(self.value["approvals"], request["questions"], strict=True):
            for target, source in (("ordinal", "ordinal"), ("question_id", "architecture_question_id"),
                                   ("question", "question"), ("area", "area")):
                self.assertEqual(approval[target], question[source])
            self.assertEqual(approval["answer"]["target_question_id"], approval["question_id"])

    def test_one_paragraph_per_answer_all_constraints_and_literal_evidence(self):
        self.assertEqual([len(values) for values in production.VALUES], [3, 4, 2, 4, 2, 4, 4, 3])
        for index, approval in enumerate(self.value["approvals"]):
            answer = ArchitectureClarificationAnswer.from_dict(approval["answer"])
            paragraph = production.RESPONSES[index]
            self.assertEqual(answer.user_answer, paragraph)
            self.assertEqual(answer.evidence, (paragraph,))
            self.assertEqual(set(answer.normalized_values), set(production.VALUES[index]))
            self.assertEqual(" ".join(production.VALUES[index]), paragraph)
            for value in answer.normalized_values:
                self.assertIn(value, paragraph)
                self.assertTrue(any(value in evidence for evidence in answer.evidence))
            self.assertEqual(answer.provenance, "explicit_user")

    def test_full_public_reconstruction_never_approves_or_transitions(self):
        from arcadev import architecture_approval, domain_model_engine, backend_generation
        from arcadev.architecture_models_handoff import ArchitectureModelsHandoff
        calls = []
        original = ArchitectureFinalization.resolve
        def resolve(state, answer, *, handoff):
            result = original(state, answer, handoff=handoff)
            calls.append((state.finalization_id, answer, result))
            return result
        with ExitStack() as stack:
            for owner, name in ((architecture_approval, "approve_architecture"),
                                (architecture_approval.ApprovedArchitecture, "create"),
                                (ArchitectureModelsHandoff, "create"),
                                (domain_model_engine, "generate_baseline_domain_model"),
                                (backend_generation, "generate_backend")):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            stack.enter_context(patch.object(ArchitectureFinalization, "resolve", resolve))
            actual = production.validate_architecture_authorization(self.raw)
        self.assertEqual(actual, self.value)
        self.assertEqual(len(calls), 8)
        parent = production.INITIAL_FINALIZATION_ID
        for call, approval in zip(calls, self.value["approvals"], strict=True):
            previous, answer, state = call
            self.assertEqual(previous, parent)
            self.assertEqual(answer.target_finalization_id, parent)
            self.assertEqual(state.finalization_id, approval["resulting_finalization_id"])
            self.assertEqual(state.history[-1].outcome.value, "accepted")
            self.assertFalse(state.conflicts)
            parent = state.finalization_id

    def test_wrong_question_answer_mapping_rejected(self):
        def swap(v):
            a, b = v["approvals"][:2]
            a["answer"]["user_answer"], b["answer"]["user_answer"] = b["answer"]["user_answer"], a["answer"]["user_answer"]
        self.reject(swap)

    def test_changed_question_text_and_area_rejected(self):
        for key, value in (("question", "Which other storage?"), ("area", "integration")):
            with self.subTest(key=key):
                self.reject(lambda v: v["approvals"][0].update({key: value}))

    def test_changed_response_even_with_recomputed_digest_rejected(self):
        def change(v):
            v["full_user_response"] = v["full_user_response"].replace("AWS S3", "Azure Blob")
            v["full_user_response_digest"] = digest_bytes(v["full_user_response"].encode())
        self.reject(change)

    def test_changed_implementation_values_or_evidence_rejected(self):
        for key, value in (("user_answer", "Use Azure Blob"), ("normalized_values", ["S3-compatible object storage"]),
                           ("evidence", ["AWS S3"]), ("provenance", "derived")):
            with self.subTest(key=key):
                self.reject(lambda v: v["approvals"][0]["answer"].update({key: value}))

    def test_ninth_answer_and_reordering_rejected(self):
        self.reject(lambda v: v["approvals"].append(copy.deepcopy(v["approvals"][0])))
        self.reject(lambda v: v["answer_order"].reverse())
        self.reject(lambda v: v["approvals"].reverse())

    def test_stale_architecture_initial_and_sequential_finalization_rejected(self):
        for key in ("architecture_id", "initial_finalization_id"):
            with self.subTest(key=key):
                self.reject(lambda v: v.update({key: "forged"}))
        self.reject(lambda v: v["approvals"][1]["answer"].update(target_finalization_id=production.INITIAL_FINALIZATION_ID))
        self.reject(lambda v: v["approvals"][0].update(resulting_finalization_id=production.INITIAL_FINALIZATION_ID))

    def test_authority_scope_and_all_approval_boundaries(self):
        self.assertEqual(self.value["authority_scope"], "only_eight_architecture_clarifications")
        self.assertEqual(self.value["provenance"], "explicit_user")
        for key in ("complete_architecture_approved", "models_authorized", "backend_authorized", "frontend_authorized"):
            self.assertIs(self.value[key], False)
            self.reject(lambda v: v.update({key: True}))
        for key in ("approved_architecture", "architecture_models_handoff", "domain_model"):
            self.assertNotIn(key, self.value)
            self.reject(lambda v: v.update({key: {}}))

    def test_malformed_and_noncanonical_authorization_rejected(self):
        for raw in (b"{", b'{"a":1,"a":2}\n', b"[]\n", self.raw + b" "):
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                production.validate_architecture_authorization(raw)


if __name__ == "__main__":
    unittest.main()
