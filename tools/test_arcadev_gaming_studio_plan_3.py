"""Complete PLAN-package reconstruction, tamper rejection and lifecycle boundary."""

import ast
from contextlib import ExitStack, redirect_stdout
from dataclasses import fields
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
from arcadev.gaming_studio_plan import (
    PLAN_PACKAGE_FILES, production_plan_inputs, production_plan_package,
    production_planning_review, production_software_plan, validate_production_plan_package,
)
from arcadev.gaming_studio_transition import CURRENT_PACKAGE_FILES
from arcadev.software_plan import PlanItem, PlanProvenance, PlanScope, SoftwarePlan


class ProductionPlanPackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = production_plan_inputs()
        cls.plan = production_software_plan()
        cls.package = production_plan_package()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="gaming-plan-package-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "authority"
        # This suite certifies the immutable unanswered PLAN package. Current
        # resolution authority has its own complete-package adversarial suite.
        shutil.copytree(AUTHORITY_DIRECTORY, self.root,
                        ignore=shutil.ignore_patterns("plan_resolution", "plan_approval", "production_architecture"))
        self.area = self.root / "production_plan"

    def assert_mutation_rejected(self, relative, change):
        path = self.root / relative
        original = path.read_bytes()
        value = parse_authority(original)
        change(value)
        path.write_bytes(canonical_bytes(value))
        try:
            with self.assertRaises(ValueError):
                validate_production_authority(self.root, require_plan=True)
        finally:
            path.write_bytes(original)

    def test_complete_package_identity_digests_and_computed_checkpoint(self):
        actual = {name: (self.area / name).read_bytes() for name in PLAN_PACKAGE_FILES}
        self.assertEqual(actual, self.package)
        self.assertEqual(actual, production_plan_package(self.root))
        result = validate_production_authority(self.root, require_plan=True)
        checkpoint = parse_authority(actual["checkpoint.json"])
        self.assertEqual(result["checkpoint"], checkpoint)
        self.assertEqual(result["checkpoint_digest"], digest_bytes(actual["checkpoint.json"]))
        self.assertEqual(checkpoint["schema"], "arcadev.gaming_studio.production_plan_checkpoint")
        self.assertEqual(checkpoint["schema_version"], 1)
        self.assertEqual(checkpoint["package_version"], 3)
        self.assertEqual(checkpoint["handoff_id"], self.handoff.handoff_id)
        self.assertEqual(checkpoint["plan_id"], self.plan.plan_id)
        self.assertEqual(checkpoint["project_id"], self.plan.project_id)
        self.assertEqual(checkpoint["current_stage"], "PLAN")
        self.assertEqual(checkpoint["project_status"], "IN_PROGRESS")
        self.assertFalse(checkpoint["ready_for_architecture"])
        self.assertEqual(checkpoint["blocking_reasons"], ["blocking_planning_questions"])
        self.assertEqual(checkpoint["unresolved_question_count"], 3)
        self.assertEqual(checkpoint["assumption_count"], 0)
        self.assertEqual(checkpoint["status"], "BLOCKED_PENDING_PLAN_CLARIFICATION")
        self.assertEqual(checkpoint["next_authorized_action"], "COLLECT_EXPLICIT_PLAN_CLARIFICATIONS")
        for name, key in (("software_plan.json", "software_plan_digest"), ("planning_review.json", "planning_review_digest")):
            self.assertEqual(checkpoint[key], digest_bytes(actual[name]))
        upstream = PACKAGE_FILES | {f"idea_resolution/{name}" for name in CURRENT_PACKAGE_FILES}
        self.assertEqual(set(checkpoint["authority_digests"]), upstream)
        self.assertEqual(len(upstream), 13)
        for name, digest in checkpoint["authority_digests"].items():
            self.assertEqual(digest, digest_bytes((self.root / name).read_bytes()))

    def test_seed_and_idea_resolution_remain_valid_and_plan_requirement_prevents_downgrade(self):
        seed = validate_production_authority(self.root, seed_only=True)
        self.assertEqual(seed["checkpoint"]["status"], "BLOCKED_PENDING_IDEA_CLARIFICATION")
        historical = self.root.parent / "historical"
        historical.mkdir()
        for name in PACKAGE_FILES:
            shutil.copyfile(self.root / name, historical / name)
        shutil.copytree(self.root / "idea_resolution", historical / "idea_resolution")
        result = validate_production_authority(historical, require_current=True)
        self.assertEqual(result["checkpoint"]["status"], "PLAN_READY_FOR_GENERATION")
        with self.assertRaisesRegex(ValueError, "PLAN authority is required"):
            validate_production_authority(historical, require_plan=True)
        with self.assertRaises(ValueError):
            validate_production_authority(self.root, seed_only=True, require_plan=True)

    def test_modified_upstream_authority_is_rejected(self):
        def altered_intent(value):
            value["approved_intent"] += " Add unapproved marketplace scope."
            value["approved_intent_sha256"] = digest_bytes(value["approved_intent"].encode())
        changes = (
            ("production_intent.json", altered_intent),
            ("idea_intake.json", lambda v: v["requested_features"].pop()),
            ("idea_resolution/current_intake.json", lambda v: v["requested_features"].pop()),
            ("idea_resolution/idea_finalization.json", lambda v: v["history"][0].update(readiness_after=not v["history"][0]["readiness_after"])),
            ("idea_resolution/metadata_authority.json", lambda v: v["metadata"].update(created_at="2026-09-14T00:00:00Z")),
            ("idea_resolution/source_project.json", lambda v: v.update(current_build_stage="PLAN")),
            ("idea_resolution/idea_plan_handoff.json", lambda v: v.update(eligible=False)),
            ("idea_resolution/project.json", lambda v: v.update(current_build_stage="ARCHITECTURE")),
        )
        for name, change in changes:
            with self.subTest(name=name):
                self.assert_mutation_rejected(name, change)

    def test_modified_plan_readiness_question_and_review_rejected(self):
        for change in (
            lambda v: v["readiness"].update(ready_for_architecture=True, blocking_reasons=[]),
            lambda v: v["open_planning_questions"][0].update(question="Rewritten planning question?"),
            lambda v: v["open_planning_questions"].pop(),
        ):
            self.assert_mutation_rejected("production_plan/software_plan.json", change)
        self.assert_mutation_rejected("production_plan/planning_review.json",
                                     lambda v: v["questions"][0].update(question_id="fake", current_accepted_planning_decision="fabricated"))

    def test_recomputed_plan_identity_review_and_checkpoint_digests_cannot_authorize_changes(self):
        ignored = {"plan_id", "handoff_id", "project_id", "project_stage", "schema", "schema_version", "readiness"}
        kwargs = {field.name: getattr(self.plan, field.name) for field in fields(self.plan) if field.name not in ignored}
        invented = PlanItem.create("ArcaCreator Marketplace", PlanProvenance.DERIVED,
                                  self.plan.in_scope_capabilities[0].source_requirements, handoff=self.handoff)
        candidates = (
            SoftwarePlan.create(handoff=self.handoff, **{**kwargs, "open_planning_questions": ()}),
            SoftwarePlan.create(handoff=self.handoff, **{
                **kwargs,
                "scope": PlanScope.create((*self.plan.scope.in_scope, invented), self.plan.scope.out_of_scope, handoff=self.handoff),
                "in_scope_capabilities": (*self.plan.in_scope_capabilities, invented),
            }),
        )
        for candidate in candidates:
            with self.subTest(plan_id=candidate.plan_id):
                candidate = SoftwarePlan.from_json(candidate.canonical_json(), handoff=self.handoff)
                review = production_planning_review(candidate, handoff=self.handoff)
                raw_plan = candidate.canonical_json().encode()
                raw_review = canonical_bytes(review)
                checkpoint = parse_authority(self.package["checkpoint.json"])
                checkpoint.update({key: review[key] for key in checkpoint.keys() & review.keys() if key not in {"schema", "schema_version"}})
                checkpoint.update(software_plan_digest=digest_bytes(raw_plan), planning_review_digest=digest_bytes(raw_review))
                for name, data in (("software_plan.json", raw_plan), ("planning_review.json", raw_review), ("checkpoint.json", canonical_bytes(checkpoint))):
                    (self.area / name).write_bytes(data)
                with self.assertRaisesRegex(ValueError, "exact baseline reconstruction"):
                    validate_production_plan_package(self.root)

    def test_forged_checkpoint_flags_and_upstream_digests_rejected(self):
        for change in (
            lambda v: v.update(ready_for_architecture=True, current_stage="ARCHITECTURE", status="APPROVED"),
            lambda v: v["authority_digests"].update({"idea_resolution/project.json": "0" * 64}),
            lambda v: v.update(blocking_question_ids=[], unresolved_question_count=0, next_authorized_action="GENERATE_BACKEND"),
        ):
            self.assert_mutation_rejected("production_plan/checkpoint.json", change)

    def test_unknown_answers_decisions_approval_and_architecture_files_rejected(self):
        for name in ("plan_clarification_answer.json", "planning_decision.json", "plan_finalization.json",
                     "approved_plan.json", "plan_architecture_handoff.json", "architecture_specification.json",
                     "domain_model.json", "backend.json", "arcacore_generation_request.json", "fixture.json", "future_strategy.md"):
            path = self.area / name
            path.write_bytes(b"{}\n")
            try:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unknown or missing"):
                    validate_production_plan_package(self.root)
            finally:
                path.unlink()

    def test_missing_nonregular_and_noncanonical_authority_rejected(self):
        path = self.area / "checkpoint.json"
        path.unlink()
        with self.assertRaises(ValueError):
            validate_production_plan_package(self.root)
        path.mkdir()
        with self.assertRaises(ValueError):
            validate_production_plan_package(self.root)
        path.rmdir()
        for data in (b'{"schema":1,"schema":2}\n', b" " * 100001, b"\xff", self.package["checkpoint.json"].replace(b"\n", b"\r\n")):
            path.write_bytes(data)
            with self.assertRaises(ValueError):
                validate_production_plan_package(self.root)

    def test_fixture_authority_dependency_is_rejected(self):
        from arcadev import gaming_studio_plan
        target = Path(gaming_studio_plan.__file__).resolve()
        original_read = Path.read_text
        def injected_read(path, *args, **kwargs):
            text = original_read(path, *args, **kwargs)
            return text + "\nimport tools.test_fake_authority\n" if path.resolve() == target else text
        with patch.object(Path, "read_text", injected_read), self.assertRaisesRegex(ValueError, "fixture"):
            validate_production_authority(self.root, require_plan=True)

    def test_no_answers_approval_architecture_generation_execution_network_or_writes(self):
        from arcadev import (
            PlanClarificationAnswer, PlanningDecision, PlanFinalization, ApprovedPlan, PlanArchitectureHandoff,
            architecture_engine, domain_model_engine, backend_generation, gaming_studio_plan,
        )
        from tools import generate
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        with ExitStack() as stack:
            for owner, name in (
                (PlanClarificationAnswer, "create"), (PlanningDecision, "create"), (PlanFinalization, "start"),
                (ApprovedPlan, "create"), (PlanArchitectureHandoff, "create"),
                (architecture_engine, "generate_baseline_architecture"),
                (domain_model_engine, "generate_baseline_domain_model"),
                (backend_generation, "generate_backend"), (generate, "generate_module"),
                (socket, "socket"), (subprocess, "Popen"), (Path, "write_bytes"), (Path, "write_text"),
            ):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            self.assertTrue(validate_production_authority(self.root, require_plan=True)["valid"])
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        tree = ast.parse(Path(gaming_studio_plan.__file__).read_text(encoding="utf-8"))
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertEqual(imports, {"gaming_studio_intent", "gaming_studio_transition", "idea_plan_handoff",
                                   "planning_engine", "plan_clarification", "software_plan", "gaming_studio_authority"})

    def test_cli_requires_current_plan_and_reports_unapproved_checkpoint(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(self.root), "--require-plan"]), 0)
        result = parse_authority(output.getvalue().encode())
        self.assertTrue(result["valid"])
        self.assertEqual(result["checkpoint"]["status"], "BLOCKED_PENDING_PLAN_CLARIFICATION")
        self.assertEqual(result["idea_checkpoint"]["status"], "PLAN_READY_FOR_GENERATION")


if __name__ == "__main__":
    unittest.main()
