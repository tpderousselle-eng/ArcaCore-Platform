"""Bounded production PLAN approvals and sequential public contract bindings."""

from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes
from arcadev.gaming_studio_plan import production_plan_inputs, production_software_plan
from arcadev.gaming_studio_plan_resolution import (
    ORDER, QUESTIONS, RESPONSES, PROPOSALS, VALUES, PLAN_ID,
    plan_authorization_package, validate_plan_authorization,
)
from arcadev.plan_clarification import PlanClarificationAnswer, PlanFinalization


class ProductionPlanAuthorizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = plan_authorization_package()
        cls.data = canonical_bytes(cls.package)
        cls.handoff = production_plan_inputs()
        cls.plan = production_software_plan()

    def reject(self, change):
        value = deepcopy(self.package)
        change(value)
        with self.assertRaises(ValueError):
            validate_plan_authorization(canonical_bytes(value))

    def test_persisted_three_exact_production_answers(self):
        path = AUTHORITY_DIRECTORY / "production_plan/plan_resolution/clarification_authorization.json"
        self.assertEqual(path.read_bytes(), self.data)
        self.assertEqual(validate_plan_authorization(self.data), self.package)
        self.assertEqual(len(self.package["approvals"]), 3)
        self.assertEqual(ORDER, (
            "arcadev_question_64610a51eaf261a7116813cf9cb32d91",
            "arcadev_question_06fa970b49a43c4d5442756aa4361ccc",
            "arcadev_question_3386cafaf9fe1e6672db5b0a9bed716f",
        ))
        self.assertEqual(RESPONSES, (
            "I approve the recommended Gaming Studio asset storage and retention policy.",
            "I approve isolated disposable build environments with strict resource, network, secret, and filesystem boundaries for Gaming Studio.",
            "I approve PC, Web, Android, and iOS publishing/export with validation gates, user-controlled releases, and direct store publishing only through explicitly supported integrations.",
        ))
        for i, approval in enumerate(self.package["approvals"]):
            answer = PlanClarificationAnswer.from_dict(approval["answer"])
            self.assertEqual(approval["ordinal"], i + 1)
            self.assertEqual(approval["question_id"], ORDER[i])
            self.assertEqual(approval["question"], QUESTIONS[i])
            self.assertEqual(approval["approved_proposal"], PROPOSALS[i])
            self.assertEqual(approval["proposal_digest"], digest_bytes(PROPOSALS[i].encode()))
            self.assertEqual(approval["provenance"], "explicit_user")
            self.assertEqual(answer.provenance, "explicit_user")
            self.assertEqual(answer.user_answer, RESPONSES[i])
            self.assertEqual(answer.evidence, (RESPONSES[i],))
            self.assertEqual(set(answer.normalized_values), set(VALUES[i]))
            self.assertEqual(answer.target_plan_id, PLAN_ID)

    def test_current_finalization_lineage_and_stale_rejection(self):
        current = PlanFinalization.start(self.plan, handoff=self.handoff)
        ids = [current.finalization_id]
        self.assertEqual(ids[0], self.package["initial_finalization_id"])
        for approval in self.package["approvals"]:
            answer = PlanClarificationAnswer.from_dict(approval["answer"])
            self.assertEqual(answer.target_finalization_id, current.finalization_id)
            current = current.resolve(answer, handoff=self.handoff)
            self.assertEqual(current.finalization_id, approval["resulting_finalization_id"])
            ids.append(current.finalization_id)
            with self.assertRaisesRegex(ValueError, "stale"):
                current.resolve(answer, handoff=self.handoff)
        self.assertEqual(len(set(ids)), 4)

    def test_duplicate_rebinding_does_not_authorize_repeat(self):
        initial = PlanFinalization.start(self.plan, handoff=self.handoff)
        raw = deepcopy(self.package["approvals"][0]["answer"])
        current = initial.resolve(PlanClarificationAnswer.from_dict(raw), handoff=self.handoff)
        raw["target_finalization_id"] = current.finalization_id
        with self.assertRaisesRegex(ValueError, "already resolved"):
            current.resolve(PlanClarificationAnswer.from_dict(raw), handoff=self.handoff)

    def test_all_envelope_and_answer_bindings_reject_tampering(self):
        for i in range(3):
            for key, value in {
                "ordinal": 4, "question_id": ORDER[(i + 1) % 3], "question": "Rewritten question?",
                "approved_proposal": PROPOSALS[i] + " Unlimited storage.",
                "proposal_digest": "0" * 64, "relationship": "blanket_plan_approval",
                "provenance": "fixture", "resulting_finalization_id": self.package["initial_finalization_id"],
                "unknown": True,
            }.items():
                with self.subTest(i=i, envelope=key):
                    self.reject(lambda v: v["approvals"][i].update({key: value}))
            for key, value in {
                "target_plan_id": "arcadev_plan_" + "0" * 32,
                "target_question_id": ORDER[(i + 1) % 3],
                "target_finalization_id": "arcadev_plan_final_" + "0" * 32,
                "user_answer": RESPONSES[(i + 1) % 3], "normalized_values": ["Unlimited storage"],
                "evidence": [], "provenance": "test", "action": "replace_decision", "unknown": True,
            }.items():
                with self.subTest(i=i, answer=key):
                    self.reject(lambda v: v["approvals"][i]["answer"].update({key: value}))

    def test_rehashed_referent_and_reused_short_approval_rejected(self):
        def rehash(v):
            approval = v["approvals"][0]
            approval["approved_proposal"] = "Approve marketplace storage."
            approval["proposal_digest"] = digest_bytes(approval["approved_proposal"].encode())
        self.reject(rehash)
        self.reject(lambda v: v["approvals"][1].update(answer=deepcopy(v["approvals"][0]["answer"])))
        self.reject(lambda v: v["approvals"].append(deepcopy(v["approvals"][0])))
        self.reject(lambda v: v["approvals"].reverse())
        self.reject(lambda v: v["approvals"].pop())

    def test_unknown_duplicate_secret_oversized_noncanonical_and_fixture_rejected(self):
        for data in (
            b'{"schema":1,"schema":1}\n', b" " * 100001, b"\xff",
            self.data.replace(b"\n", b"\r\n"), b'{"password":"secret-value"}\n',
        ):
            with self.subTest(data=data[:30]), self.assertRaises(ValueError):
                validate_plan_authorization(data)
        self.reject(lambda v: v.update(fixture="tools.test_fake_authority"))
        self.reject(lambda v: v.update(schema_version=True))
        self.reject(lambda v: v.update(approved_plan={}))

    def test_normalization_preserves_boundaries(self):
        self.assertEqual(len(VALUES[0]), 8)
        for rule in ("50 GB", "30 days", "7 days", "kept/pinned", "entitlement"):
            self.assertIn(rule, " ".join(VALUES[0]))
        self.assertEqual([v for v in VALUES[0] if "Marketplace" in v],
                         ["Marketplace asset retention is outside current initial scope"])
        for invented in ("unlimited", "pooling", "Kubernetes", "Docker", "AWS", "GiB", "Steam", "Epic", "SDK"):
            self.assertNotIn(invented, " ".join(v for group in VALUES for v in group))
        self.assertIn("PC, Web, Android and iOS", VALUES[2][0])
        self.assertIn("Consoles are outside initial scope", VALUES[2])

    def test_no_approval_architecture_generation_execution_or_writes(self):
        from arcadev import ApprovedPlan, PlanArchitectureHandoff, architecture_engine, backend_generation, domain_model_engine
        from tools import generate
        with ExitStack() as stack:
            for owner, name in (
                (ApprovedPlan, "create"), (PlanArchitectureHandoff, "create"),
                (architecture_engine, "generate_baseline_architecture"),
                (domain_model_engine, "generate_baseline_domain_model"),
                (backend_generation, "generate_backend"), (generate, "generate_module"),
                (socket, "socket"), (subprocess, "Popen"),
                (Path, "write_bytes"), (Path, "write_text"),
            ):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            self.assertEqual(validate_plan_authorization(self.data), self.package)
        self.assertEqual(self.plan.project_stage.value, "PLAN")
        self.assertFalse(self.plan.readiness.ready_for_architecture)


if __name__ == "__main__":
    unittest.main()
