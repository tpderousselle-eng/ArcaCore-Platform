"""Complete approved production lineage and adversarial ARCHITECTURE checkpoint."""

from contextlib import ExitStack, redirect_stdout
from dataclasses import replace
import io
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcadev.gaming_studio_authority import main, validate_production_authority
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes, parse_authority
from arcadev.gaming_studio_plan_approval import APPROVAL_AREA, APPROVAL_STATEMENT, APPROVAL_STATEMENT_DIGEST
from arcadev.gaming_studio_plan_approval_checkpoint import (
    APPROVAL_PACKAGE_FILES, historical_authority_names,
    production_plan_approval_checkpoint_package, validate_plan_approval_checkpoint,
)


class ProductionPlanApprovalCheckpointTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gaming-architecture-checkpoint-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "authority"
        shutil.copytree(AUTHORITY_DIRECTORY, self.root)
        self.area = self.root / APPROVAL_AREA
        self.package = {n: (self.area / n).read_bytes() for n in APPROVAL_PACKAGE_FILES}

    def mutate_reject(self, relative, change, *, rehash=False):
        path = self.root / relative
        original = path.read_bytes()
        cp_path = self.area / "checkpoint.json"
        cp_before = cp_path.read_bytes()
        value = parse_authority(original)
        change(value)
        path.write_bytes(canonical_bytes(value))
        if rehash:
            cp = parse_authority(cp_path.read_bytes())
            cp["authority_digests"][relative] = digest_bytes(path.read_bytes())
            cp_path.write_bytes(canonical_bytes(cp))
        try:
            with self.assertRaises(ValueError):
                validate_plan_approval_checkpoint(self.root)
        finally:
            path.write_bytes(original)
            cp_path.write_bytes(cp_before)

    def test_complete_production_lineage_and_deterministic_package(self):
        self.assertEqual(self.package, production_plan_approval_checkpoint_package(self.root))
        result = validate_production_authority(self.root, require_plan_approval=True)
        cp = parse_authority(self.package["checkpoint.json"])
        self.assertTrue(result["valid"])
        self.assertEqual(result["checkpoint"], cp)
        self.assertEqual(result["checkpoint_digest"], digest_bytes(self.package["checkpoint.json"]))
        self.assertEqual(result["ready_for_approval_checkpoint"]["status"], "PLAN_READY_FOR_APPROVAL")
        self.assertEqual(result["unanswered_plan_checkpoint"]["status"], "BLOCKED_PENDING_PLAN_CLARIFICATION")
        self.assertEqual(result["idea_checkpoint"]["status"], "PLAN_READY_FOR_GENERATION")
        self.assertEqual(result["seed_checkpoint"], parse_authority((self.root / "checkpoint.json").read_bytes()))

    def test_checkpoint_bindings_warning_and_complete_digest_inventory(self):
        cp = parse_authority(self.package["checkpoint.json"])
        approved = parse_authority(self.package["approved_plan.json"])
        handoff = parse_authority(self.package["plan_architecture_handoff.json"])
        auth = parse_authority(self.package["approval_authorization.json"])
        self.assertEqual(cp["schema"], "arcadev.gaming_studio.plan_approval_checkpoint")
        self.assertEqual(cp["schema_version"], 1)
        self.assertEqual(cp["package_version"], 3)
        for key, expected in {
                "approved_plan_id": approved["approval_id"], "software_plan_id": approved["software_plan_id"],
                "plan_finalization_id": approved["plan_finalization_id"],
                "plan_architecture_handoff_id": handoff["handoff_id"],
                "project_id": handoff["resulting_project"]["project_id"],
                "approval_statement_digest": APPROVAL_STATEMENT_DIGEST,
                "approval_decision": "approved", "approval_eligible": True,
                "complete_plan_approved": True, "consistency_result": True,
                "transition_eligible": True, "transition_decision": "transitioned",
                "current_stage": "ARCHITECTURE", "project_status": "IN_PROGRESS",
                "architecture_specification_id": None, "architecture_generated": False,
                "architecture_generation_authorized": False, "unresolved_question_count": 0,
                "conflict_count": 0, "status": "ARCHITECTURE_READY_FOR_GENERATION",
                "next_authorized_action": "GENERATE_PRODUCTION_ARCHITECTURE_SPECIFICATION"}.items():
            self.assertEqual(cp[key], expected, key)
        self.assertEqual(approved["approval_statement"], APPROVAL_STATEMENT)
        self.assertEqual(auth["approval_statement"], APPROVAL_STATEMENT)
        self.assertEqual(cp["consistency"], approved["package"]["consistency"])
        self.assertEqual(cp["consistency_warnings"], cp["consistency"]["warnings"])
        self.assertEqual([w["code"] for w in cp["consistency_warnings"]], ["decision_semantics_not_machine_classified"])
        self.assertEqual(cp["consistency"]["blocking_findings"], [])
        names = historical_authority_names() | {f"{APPROVAL_AREA}/{n}" for n in APPROVAL_PACKAGE_FILES - {"checkpoint.json"}}
        self.assertEqual(len(names), 24)
        self.assertEqual(set(cp["authority_digests"]), names)
        for name, digest in cp["authority_digests"].items():
            self.assertEqual(digest, digest_bytes((self.root / name).read_bytes()))

    def test_every_historical_authority_record_is_bound(self):
        for name in sorted(historical_authority_names()):
            with self.subTest(name=name):
                self.mutate_reject(name, lambda v: v.update(unapproved=True))
        # Rehashing a modified decision/finalization must not replace replay.
        self.mutate_reject("production_plan/plan_resolution/plan_finalization.json",
            lambda v: v["decisions"][0]["accepted_values"].append("Unauthorized unlimited storage"), rehash=True)
        self.mutate_reject("idea_resolution/project.json",
            lambda v: v.update(current_build_stage="ARCHITECTURE"), rehash=True)

    def test_exact_approval_statement_digest_scope_and_identity_reject_tampering(self):
        relative = APPROVAL_AREA + "/approval_authorization.json"
        for key, replacement in (("approval_statement", "I approve all future stages."),
                ("approval_statement_digest", "0" * 64), ("software_plan_id", "another_plan"),
                ("plan_finalization_id", "stale_finalization"), ("project_id", "another_project"),
                ("architecture_generation_authorized", True), ("provenance", "fixture")):
            def change(v):
                v[key] = replacement
                if key == "approval_statement":
                    v["approval_statement_digest"] = digest_bytes(replacement.encode("utf-8"))
            with self.subTest(key=key):
                self.mutate_reject(relative, change, rehash=True)

    def test_rehashed_forged_approval_eligibility_and_handoff_rejected(self):
        for name, change in (
                ("approved_plan.json", lambda v: v.update(approval_eligible=False)),
                ("plan_architecture_handoff.json", lambda v: v.update(approved_plan_id="another_approval")),
                ("project.json", lambda v: v.update(current_build_stage="MODELS"))):
            with self.subTest(name=name):
                self.mutate_reject(APPROVAL_AREA + "/" + name, change, rehash=True)

    def test_valid_public_approval_of_another_plan_and_finalization_is_not_production_authority(self):
        from arcadev import ApprovedPlan, PlanFinalization, SoftwarePlan, approve_plan, PlanArchitectureHandoff
        approved = ApprovedPlan.from_json(self.package["approved_plan.json"].decode("utf-8"))
        idea = approved.package.idea_handoff
        old = approved.package.plan_finalization
        plan = old.original_plan
        fields = ("product_objective", "user_problem_statement", "scope", "in_scope_capabilities", "user_roles",
            "user_journeys", "functional_requirements", "non_functional_requirements", "milestones", "dependencies",
            "integrations", "assumptions", "risks", "open_planning_questions", "acceptance_criteria", "planning_constraints")
        values = {field: getattr(plan, field) for field in fields}
        self.assertGreater(len(plan.acceptance_criteria), 1)
        values["acceptance_criteria"] = plan.acceptance_criteria[:-1]
        other_plan = SoftwarePlan.create(handoff=idea, **values)
        current = PlanFinalization.start(other_plan, handoff=idea)
        for entry in old.history:
            answer = replace(entry.answer, target_plan_id=other_plan.plan_id, target_finalization_id=current.finalization_id)
            current = current.resolve(answer, handoff=idea)
        other = approve_plan(handoff=idea, finalization=current, approval_statement=APPROVAL_STATEMENT)
        self.assertTrue(other.approved)
        self.assertNotEqual(other.software_plan_id, approved.software_plan_id)
        self.assertNotEqual(other.plan_finalization_id, approved.plan_finalization_id)
        other_handoff = PlanArchitectureHandoff.create(source_project=idea.resulting_project, approved_plan=other)
        self.assertEqual(ApprovedPlan.from_json(other.canonical_json()), other)
        self.assertEqual(PlanArchitectureHandoff.from_json(other_handoff.canonical_json()), other_handoff)
        cp = parse_authority(self.package["checkpoint.json"])
        for name, data in {"approved_plan.json": other.canonical_json().encode("utf-8"),
                           "plan_architecture_handoff.json": other_handoff.canonical_json().encode("utf-8")}.items():
            (self.area / name).write_bytes(data)
            cp["authority_digests"][APPROVAL_AREA + "/" + name] = digest_bytes(data)
        cp.update(approved_plan_id=other.approval_id, software_plan_id=other.software_plan_id,
                  plan_finalization_id=other.plan_finalization_id, plan_architecture_handoff_id=other_handoff.handoff_id)
        (self.area / "checkpoint.json").write_bytes(canonical_bytes(cp))
        with self.assertRaises(ValueError):
            validate_plan_approval_checkpoint(self.root)

    def test_forged_checkpoint_flags_warnings_and_digest_paths_rejected(self):
        for change in (lambda v: v.update(architecture_generated=True),
                       lambda v: v.update(architecture_specification_id="fake_architecture"),
                       lambda v: v.update(current_stage="MODELS"),
                       lambda v: v.update(consistency_warnings=[]),
                       lambda v: v.update(schema_version=True),
                       lambda v: v.update(approved_architecture={}),
                       lambda v: v["authority_digests"].update({"//server/share/authority": "0" * 64})):
            self.mutate_reject(APPROVAL_AREA + "/checkpoint.json", change)

    def test_fake_architecture_later_stage_fixture_and_unknown_files_rejected(self):
        for name in ("architecture_specification.json", "approved_architecture.json", "architecture_models_handoff.json",
                     "architecture_candidates.json", "domain_model.json", "backend.json", "frontend.json",
                     "arcacore_generation_request.json", "fixture.json", "future_strategy.md"):
            path = self.area / name
            path.write_bytes(b"{}\n")
            try:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unknown or missing"):
                    validate_plan_approval_checkpoint(self.root)
            finally:
                path.unlink()
        for relative in ("unknown.json", "idea_resolution/unknown.json", "production_plan/unknown.json"):
            path = self.root / relative
            path.write_bytes(b"{}\n")
            try:
                with self.assertRaises(ValueError):
                    validate_production_authority(self.root, require_plan_approval=True)
            finally:
                path.unlink()

    def test_missing_nonregular_noncanonical_oversized_and_linked_records_rejected(self):
        path = self.area / "checkpoint.json"
        path.unlink()
        with self.assertRaises(ValueError):
            validate_plan_approval_checkpoint(self.root)
        path.mkdir()
        with self.assertRaises(ValueError):
            validate_plan_approval_checkpoint(self.root)
        path.rmdir()
        for data in (b'{"schema":1,"schema":1}\n', b" " * 100001, b"\xff", b'{"password":"secret-value"}\n'):
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                validate_plan_approval_checkpoint(self.root)
        path.write_bytes(self.package["checkpoint.json"])
        original = Path.is_symlink
        with patch.object(Path, "is_symlink", autospec=True, side_effect=lambda p: p == self.area or original(p)):
            with self.assertRaisesRegex(ValueError, "links"):
                validate_plan_approval_checkpoint(self.root)

    def test_public_consistency_is_reevaluated_and_blockers_cannot_be_overridden(self):
        from arcadev import plan_approval
        blocker = plan_approval.PlanConsistencyFinding.create("production_blocker", "A blocking finding must stop approval.",
            plan_approval.PlanFindingSeverity.BLOCKING, ["scope"])
        evaluation = plan_approval.PlanConsistencyEvaluation.create([blocker])
        with patch.object(plan_approval, "evaluate_plan_consistency", return_value=evaluation) as evaluate:
            with self.assertRaisesRegex(ValueError, "cannot be approved"):
                validate_plan_approval_checkpoint(self.root)
        self.assertTrue(evaluate.called)

    def test_historical_seed_cli_requirement_and_fixture_independence(self):
        seed = validate_production_authority(self.root, seed_only=True)
        self.assertEqual(seed["checkpoint"], parse_authority((self.root / "checkpoint.json").read_bytes()))
        with self.assertRaises(ValueError):
            validate_production_authority(self.root, seed_only=True, require_plan_approval=True)
        historical = self.root.parent / "historical"
        shutil.copytree(self.root, historical, ignore=shutil.ignore_patterns("plan_approval"))
        with self.assertRaisesRegex(ValueError, "PLAN approval authority is required"):
            validate_production_authority(historical, require_plan_approval=True)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(self.root), "--require-plan-approval"]), 0)
        self.assertEqual(parse_authority(output.getvalue().encode("utf-8"))["checkpoint"]["current_stage"], "ARCHITECTURE")
        from arcadev import gaming_studio_plan_approval_checkpoint
        target = Path(gaming_studio_plan_approval_checkpoint.__file__).resolve()
        original = Path.read_text
        def injected(p, *args, **kwargs):
            text = original(p, *args, **kwargs)
            return text + "\nfrom tools import fixture_fake_authority\n" if p.resolve() == target else text
        with patch.object(Path, "read_text", injected), self.assertRaisesRegex(ValueError, "fixture"):
            validate_plan_approval_checkpoint(self.root)

    def test_validation_has_no_generation_execution_network_writes_or_future_strategy(self):
        from arcadev import architecture_engine, domain_model_engine, backend_generation
        from tools import generate
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        original = Path.read_text
        def guarded(p, *args, **kwargs):
            if p.name == "GAMING_STUDIO_FUTURE_STRATEGY.md":
                raise AssertionError("Future strategy entered production authority")
            return original(p, *args, **kwargs)
        with ExitStack() as stack:
            for owner, name in ((architecture_engine, "generate_baseline_architecture"),
                    (domain_model_engine, "generate_baseline_domain_model"), (backend_generation, "generate_backend"),
                    (generate, "generate_module"), (socket, "socket"), (subprocess, "Popen"),
                    (Path, "write_bytes"), (Path, "write_text")):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            stack.enter_context(patch.object(Path, "read_text", guarded))
            self.assertTrue(validate_production_authority(self.root, require_plan_approval=True)["valid"])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
