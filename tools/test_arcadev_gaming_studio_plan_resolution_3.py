"""Complete unapproved production PLAN lineage and adversarial checkpoint gate."""

from contextlib import ExitStack, redirect_stdout
import io
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcadev.gaming_studio_authority import PACKAGE_FILES, main, validate_production_authority
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes, parse_authority
from arcadev.gaming_studio_plan import PLAN_PACKAGE_FILES
from arcadev.gaming_studio_plan_checkpoint import (
    RESOLUTION_PACKAGE_FILES, production_plan_resolution_package, validate_plan_resolution_package,
)
from arcadev.gaming_studio_transition import CURRENT_PACKAGE_FILES


class ProductionPlanResolutionCheckpointTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gaming-plan-resolution-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "authority"
        # Preserve this suite's strict historical, unapproved checkpoint scope.
        # The later approval/transition has its own complete lineage suite.
        shutil.copytree(AUTHORITY_DIRECTORY, self.root, ignore=shutil.ignore_patterns("plan_approval"))
        self.area = self.root / "production_plan/plan_resolution"
        self.package = {name: (self.area / name).read_bytes() for name in RESOLUTION_PACKAGE_FILES}

    def mutate_reject(self, relative, change, *, rehash=False):
        path = self.root / relative
        original = path.read_bytes()
        checkpoint = self.area / "checkpoint.json"
        checkpoint_before = checkpoint.read_bytes()
        value = parse_authority(original)
        change(value)
        path.write_bytes(canonical_bytes(value))
        if rehash:
            current = parse_authority(checkpoint.read_bytes())
            current["authority_digests"][relative] = digest_bytes(path.read_bytes())
            checkpoint.write_bytes(canonical_bytes(current))
        try:
            with self.assertRaises(ValueError):
                validate_plan_resolution_package(self.root)
        finally:
            path.write_bytes(original)
            checkpoint.write_bytes(checkpoint_before)

    def test_complete_public_reconstruction_and_digest_inventory(self):
        self.assertEqual(self.package, production_plan_resolution_package(self.root))
        result = validate_production_authority(self.root, require_plan_resolution=True)
        checkpoint = parse_authority(self.package["checkpoint.json"])
        self.assertEqual(result["checkpoint"], checkpoint)
        self.assertEqual(result["checkpoint_digest"], digest_bytes(self.package["checkpoint.json"]))
        self.assertEqual(checkpoint["schema"], "arcadev.gaming_studio.plan_resolution_checkpoint")
        self.assertEqual(checkpoint["schema_version"], 1)
        self.assertEqual(checkpoint["package_version"], 3)
        names = PACKAGE_FILES | {f"idea_resolution/{n}" for n in CURRENT_PACKAGE_FILES} | {
            f"production_plan/{n}" for n in PLAN_PACKAGE_FILES
        } | {f"production_plan/plan_resolution/{n}" for n in RESOLUTION_PACKAGE_FILES - {"checkpoint.json"}}
        self.assertEqual(len(names), 19)
        self.assertEqual(set(checkpoint["authority_digests"]), names)
        for name, digest in checkpoint["authority_digests"].items():
            self.assertEqual(digest, digest_bytes((self.root / name).read_bytes()))
        self.assertEqual(result["unanswered_plan_checkpoint"]["status"], "BLOCKED_PENDING_PLAN_CLARIFICATION")
        self.assertEqual(result["idea_checkpoint"]["status"], "PLAN_READY_FOR_GENERATION")

    def test_decisions_finalization_readiness_and_stage_bindings(self):
        cp = parse_authority(self.package["checkpoint.json"])
        finalization = parse_authority(self.package["plan_finalization.json"])
        review = parse_authority(self.package["resolution_review.json"])
        auth = parse_authority(self.package["clarification_authorization.json"])
        self.assertEqual(cp["plan_id"], finalization["original_plan"]["plan_id"])
        self.assertEqual(cp["plan_finalization_id"], finalization["finalization_id"])
        self.assertEqual(cp["accepted_decision_ids"], [e["resulting_decision_id"] for e in finalization["history"]])
        self.assertEqual(set(cp["accepted_decision_ids"]), {d["decision_id"] for d in finalization["decisions"]})
        current = auth["initial_finalization_id"]
        for approval, history in zip(auth["approvals"], finalization["history"], strict=True):
            self.assertEqual(approval["answer"], history["answer"])
            self.assertEqual(approval["answer"]["target_finalization_id"], current)
            current = approval["resulting_finalization_id"]
        self.assertEqual(current, cp["plan_finalization_id"])
        for field, expected in {
            "unresolved_question_count": 0, "conflict_count": 0,
            "effective_ready_for_architecture": True, "current_stage": "PLAN",
            "project_status": "IN_PROGRESS", "status": "PLAN_READY_FOR_APPROVAL",
            "next_authorized_action": "REQUEST_EXPLICIT_PLAN_APPROVAL",
            "complete_plan_approved": False, "architecture_authorized": False,
        }.items():
            self.assertEqual(cp[field], expected)
            self.assertEqual(cp[field], review[field])

    def test_all_historical_authority_files_remain_bound(self):
        cp = parse_authority(self.package["checkpoint.json"])
        for relative in cp["authority_digests"]:
            if relative.startswith("production_plan/plan_resolution/"):
                continue
            with self.subTest(relative=relative):
                self.mutate_reject(relative, lambda v: v.update(unapproved=True))

    def test_rehashed_historical_plan_review_and_checkpoint_still_rejected(self):
        for name in PLAN_PACKAGE_FILES:
            with self.subTest(name=name):
                self.mutate_reject(f"production_plan/{name}", lambda v: v.update(unapproved=True), rehash=True)

    def test_authorization_response_values_proposal_and_lineage_tampering_rejected(self):
        relative = "production_plan/plan_resolution/clarification_authorization.json"
        for index in range(3):
            for change in (
                lambda v: v["approvals"][index]["answer"].update(user_answer="I approve everything"),
                lambda v: v["approvals"][index]["answer"]["normalized_values"].append("Unlimited storage"),
                lambda v: v["approvals"][index]["answer"].update(target_finalization_id=v["initial_finalization_id"] + "0"),
                lambda v: v["approvals"][index].update(approved_proposal="Altered referent"),
            ):
                self.mutate_reject(relative, change)
        def rehashed_proposal(v):
            approval = v["approvals"][0]
            approval["approved_proposal"] += " Marketplace storage approved."
            approval["proposal_digest"] = digest_bytes(approval["approved_proposal"].encode())
        self.mutate_reject(relative, rehashed_proposal, rehash=True)

    def test_decision_history_finalization_and_review_forgery_rejected(self):
        relative = "production_plan/plan_resolution/plan_finalization.json"
        for change in (
            lambda v: v["decisions"][0]["accepted_values"].append("4 CPUs on Kubernetes"),
            lambda v: v["history"][1]["answer"].update(target_finalization_id=v["history"][0]["answer"]["target_finalization_id"]),
            lambda v: v.update(effective_ready_for_architecture=False),
            lambda v: v.update(approved_plan={}),
        ):
            self.mutate_reject(relative, change)
        self.mutate_reject(relative, lambda v: v.update(effective_ready_for_architecture=False), rehash=True)
        self.mutate_reject("production_plan/plan_resolution/resolution_review.json",
                           lambda v: v.update(complete_plan_approved=True), rehash=True)
        # Even a self-consistent, ready public finalization with new IDs and a
        # repaired checkpoint digest cannot replace the fixed production answers.
        from arcadev.idea_plan_handoff import IdeaPlanHandoff
        from arcadev.software_plan import SoftwarePlan
        from arcadev.plan_clarification import PlanFinalization, PlanClarificationAnswer
        handoff = IdeaPlanHandoff.from_json((self.root / "idea_resolution/idea_plan_handoff.json").read_text(encoding="utf-8"))
        plan = SoftwarePlan.from_json((self.root / "production_plan/software_plan.json").read_text(encoding="utf-8"), handoff=handoff)
        candidate = PlanFinalization.start(plan, handoff=handoff)
        for index, approval in enumerate(parse_authority(self.package["clarification_authorization.json"])["approvals"]):
            answer = approval["answer"]
            answer["target_finalization_id"] = candidate.finalization_id
            if index == 0:
                answer["normalized_values"].append("Unlimited storage")
            candidate = candidate.resolve(PlanClarificationAnswer.from_dict(answer), handoff=handoff)
        self.assertTrue(candidate.effective_ready_for_architecture)
        self.assertEqual(candidate, PlanFinalization.from_dict(candidate.canonical_dict(), handoff=handoff))
        self.mutate_reject(relative, lambda v: (v.clear(), v.update(candidate.canonical_dict())), rehash=True)

    def test_forged_checkpoint_flags_unknown_fields_and_digest_names_rejected(self):
        relative = "production_plan/plan_resolution/checkpoint.json"
        for change in (
            lambda v: v.update(current_stage="ARCHITECTURE"),
            lambda v: v.update(complete_plan_approved=True, architecture_authorized=True),
            lambda v: v.update(status="APPROVED", next_authorized_action="GENERATE_BACKEND"),
            lambda v: v.update(unresolved_question_count=1, conflict_count=1, effective_ready_for_architecture=True),
            lambda v: v.update(plan_finalization_id="arcadev_plan_final_" + "0" * 32),
            lambda v: v.update(accepted_decision_ids=[]),
            lambda v: v.update(schema_version=True),
            lambda v: v.update(approved_plan={}),
            lambda v: v["authority_digests"].update({"//server/share/secret": "0" * 64}),
        ):
            self.mutate_reject(relative, change)

    def test_fake_approval_handoff_architecture_and_unknown_authority_files_rejected(self):
        for name in ("approved_plan.json", "plan_architecture_handoff.json", "architecture_specification.json",
                     "domain_model.json", "backend.json", "arcacore_generation_request.json",
                     "fourth_answer.json", "fixture.json", "future_strategy.md"):
            path = self.area / name
            path.write_bytes(b"{}\n")
            try:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unknown or missing"):
                    validate_plan_resolution_package(self.root)
            finally:
                path.unlink()
        path = self.root / "approved_plan.json"
        path.write_bytes(b"{}\n")
        with self.assertRaises(ValueError):
            validate_production_authority(self.root, require_plan_resolution=True)

    def test_missing_nonregular_duplicate_unknown_secret_and_oversized_records_rejected(self):
        path = self.area / "checkpoint.json"
        path.unlink()
        with self.assertRaises(ValueError):
            validate_plan_resolution_package(self.root)
        path.mkdir()
        with self.assertRaises(ValueError):
            validate_plan_resolution_package(self.root)
        path.rmdir()
        for data in (b'{"schema":1,"schema":1}\n', b" " * 100001, b"\xff", b'{"password":"secret-value"}\n'):
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                validate_plan_resolution_package(self.root)

    def test_fixture_dependency_and_linked_authority_rejected(self):
        from arcadev import gaming_studio_plan_checkpoint
        target = Path(gaming_studio_plan_checkpoint.__file__).resolve()
        original_read = Path.read_text
        def injected_read(path, *args, **kwargs):
            content = original_read(path, *args, **kwargs)
            return content + "\nfrom tools import fixture_fake_authority\n" if path.resolve() == target else content
        with patch.object(Path, "read_text", injected_read), self.assertRaisesRegex(ValueError, "fixture"):
            validate_plan_resolution_package(self.root)
        original_link = Path.is_symlink
        with patch.object(Path, "is_symlink", autospec=True,
                          side_effect=lambda path: path == self.area or original_link(path)):
            with self.assertRaisesRegex(ValueError, "links"):
                validate_plan_resolution_package(self.root)

    def test_validation_has_no_approval_architecture_execution_generation_writes_or_strategy(self):
        from arcadev import ApprovedPlan, PlanArchitectureHandoff, architecture_engine, domain_model_engine, backend_generation
        from tools import generate
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        original_read = Path.read_text
        def guarded_read(path, *args, **kwargs):
            if path.name == "GAMING_STUDIO_FUTURE_STRATEGY.md":
                raise AssertionError("Future strategy entered authority")
            return original_read(path, *args, **kwargs)
        with ExitStack() as stack:
            for owner, name in (
                (ApprovedPlan, "create"), (PlanArchitectureHandoff, "create"),
                (architecture_engine, "generate_baseline_architecture"),
                (domain_model_engine, "generate_baseline_domain_model"),
                (backend_generation, "generate_backend"), (generate, "generate_module"),
                (socket, "socket"), (subprocess, "Popen"), (Path, "write_bytes"), (Path, "write_text"),
            ):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            stack.enter_context(patch.object(Path, "read_text", guarded_read))
            self.assertTrue(validate_production_authority(self.root, require_plan_resolution=True)["valid"])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_cli_current_checkpoint_and_required_resolution_prevent_downgrade(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(self.root), "--require-plan-resolution"]), 0)
        result = parse_authority(output.getvalue().encode())
        self.assertEqual(result["checkpoint"]["status"], "PLAN_READY_FOR_APPROVAL")
        historical = self.root.parent / "historical"
        shutil.copytree(self.root, historical, ignore=shutil.ignore_patterns("plan_resolution"))
        with self.assertRaisesRegex(ValueError, "PLAN resolution authority is required"):
            validate_production_authority(historical, require_plan_resolution=True)
        with self.assertRaises(ValueError):
            validate_production_authority(self.root, seed_only=True, require_plan_resolution=True)


if __name__ == "__main__":
    unittest.main()
