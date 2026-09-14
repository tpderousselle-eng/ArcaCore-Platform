"""Production approval authority and independent public eligibility checks."""

from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes, parse_authority
from arcadev.gaming_studio_plan_approval import (
    APPROVAL_AREA, APPROVAL_FILES, APPROVAL_STATEMENT, APPROVAL_STATEMENT_DIGEST,
    FINALIZATION_ID, IDEA_HANDOFF_ID, PLAN_ID, PROJECT_ID,
    production_plan_approval_authorization, production_plan_approval_package,
    validate_plan_approval_authorization, validate_plan_approval_package,
)
from arcadev import (
    ApprovedPlan, BuildStage, PlanArchitectureHandoff, PlanClarificationAnswer,
    PlanFinalization, PlanScope, ProjectStatus, SoftwarePlan, approve_plan,
    evaluate_plan_consistency, planning_question_id,
)


class ProductionPlanApprovalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.approved = validate_plan_approval_package()
        cls.handoff = cls.approved.package.idea_handoff
        cls.finalization = cls.approved.package.plan_finalization
        cls.plan = cls.finalization.original_plan

    def copy_authority(self):
        temporary = tempfile.TemporaryDirectory(prefix="gaming-plan-approval-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / "authority"
        shutil.copytree(AUTHORITY_DIRECTORY, root)
        return root

    def test_exact_statement_digest_scope_and_identity(self):
        data = production_plan_approval_authorization()
        value = validate_plan_approval_authorization(data)
        self.assertEqual(value["approval_statement"],
            "I explicitly approve the complete Gaming Studio production SoftwarePlan and authorize the PLAN → ARCHITECTURE transition.")
        self.assertEqual(value["approval_statement_digest"], digest_bytes(APPROVAL_STATEMENT.encode("utf-8")))
        self.assertEqual(value["approval_statement_digest"], APPROVAL_STATEMENT_DIGEST)
        self.assertEqual(value["scope"], "complete_plan_approval_and_plan_to_architecture_authorization")
        self.assertEqual(value["provenance"], "explicit_user")
        for key in ("architecture_generation_authorized", "models_authorized", "backend_authorized", "frontend_authorized"):
            self.assertIs(value[key], False)
        for key, expected in (("project_id", PROJECT_ID), ("idea_handoff_id", IDEA_HANDOFF_ID),
                              ("software_plan_id", PLAN_ID), ("plan_finalization_id", FINALIZATION_ID)):
            self.assertEqual(value[key], expected)

    def test_altered_statement_rehashed_digest_and_bindings_rejected(self):
        for key, replacement in (("approval_statement", "I approve everything"),
                ("approval_statement_digest", "0" * 64), ("project_id", PROJECT_ID + "0"),
                ("software_plan_id", PLAN_ID + "0"), ("plan_finalization_id", FINALIZATION_ID + "0"),
                ("idea_handoff_id", IDEA_HANDOFF_ID + "0"), ("provenance", "fixture"),
                ("architecture_generation_authorized", True), ("schema_version", True)):
            value = parse_authority(production_plan_approval_authorization())
            value[key] = replacement
            if key == "approval_statement":
                value["approval_statement_digest"] = digest_bytes(value["approval_statement"].encode("utf-8"))
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan_approval_authorization(canonical_bytes(value))

    def test_public_approval_roundtrip_and_exact_production_package(self):
        approved = approve_plan(handoff=self.handoff, finalization=self.finalization,
                                approval_statement=APPROVAL_STATEMENT)
        self.assertEqual(approved, self.approved)
        self.assertEqual(ApprovedPlan.from_json(approved.canonical_json()), approved)
        expected = production_plan_approval_package()
        self.assertEqual(set(expected), APPROVAL_FILES)
        for name, data in expected.items():
            self.assertEqual(data, (AUTHORITY_DIRECTORY / APPROVAL_AREA / name).read_bytes())
        self.assertEqual(approved.source_project_id, PROJECT_ID)
        self.assertEqual(approved.software_plan_id, PLAN_ID)
        self.assertEqual(approved.plan_finalization_id, FINALIZATION_ID)

    def test_computed_eligibility_and_warnings_preserved(self):
        approved = self.approved
        self.assertIs(approved.approved, True)
        self.assertIs(approved.approval_eligible, True)
        self.assertIs(approved.effective_ready_for_architecture, True)
        self.assertEqual(approved.decision.value, "approved")
        evaluation = evaluate_plan_consistency(self.handoff, self.finalization)
        self.assertEqual(approved.package.consistency, evaluation)
        self.assertIs(evaluation.consistent, True)
        self.assertEqual(evaluation.blocking_findings, ())
        self.assertEqual([w.code for w in evaluation.warnings], ["decision_semantics_not_machine_classified"])
        self.assertEqual(self.finalization.unresolved_questions, ())
        self.assertEqual(self.finalization.conflicts, ())

    def test_unresolved_question_and_real_conflict_prevent_approval(self):
        initial = PlanFinalization.start(self.plan, handoff=self.handoff)
        answer = PlanClarificationAnswer.create(target_plan_id=self.plan.plan_id,
            target_finalization_id=initial.finalization_id,
            target_question_id=planning_question_id(initial.unresolved_questions[0]),
            user_answer="platform=iOS only", normalized_values=["platform=iOS only"], evidence=["platform=iOS only"])
        conflicted = initial.resolve(answer, handoff=self.handoff)
        self.assertTrue(conflicted.conflicts)
        for state in (initial, conflicted):
            with self.assertRaisesRegex(ValueError, "cannot be approved"):
                approve_plan(handoff=self.handoff, finalization=state, approval_statement=APPROVAL_STATEMENT)

    def test_real_blocking_consistency_prevents_approval(self):
        fields = ("product_objective", "user_problem_statement", "scope", "in_scope_capabilities",
            "user_roles", "user_journeys", "functional_requirements", "non_functional_requirements",
            "milestones", "dependencies", "integrations", "assumptions", "risks",
            "open_planning_questions", "acceptance_criteria", "planning_constraints")
        values = {field: getattr(self.plan, field) for field in fields}
        values["scope"] = PlanScope.create(self.plan.scope.in_scope[:-1], self.plan.scope.out_of_scope, handoff=self.handoff)
        plan = SoftwarePlan.create(handoff=self.handoff, **values)
        current = PlanFinalization.start(plan, handoff=self.handoff)
        for entry in self.finalization.history:
            answer = replace(entry.answer, target_plan_id=plan.plan_id, target_finalization_id=current.finalization_id)
            current = current.resolve(answer, handoff=self.handoff)
        self.assertTrue(current.effective_ready_for_architecture)
        evaluation = evaluate_plan_consistency(self.handoff, current)
        self.assertIn("scope_capability_mismatch", [f.code for f in evaluation.blocking_findings])
        with self.assertRaisesRegex(ValueError, "cannot be approved"):
            approve_plan(handoff=self.handoff, finalization=current, approval_statement=APPROVAL_STATEMENT)

    def test_wrong_project_stage_and_status_prevent_approval(self):
        for project in (replace(self.handoff.resulting_project, current_build_stage=BuildStage.ARCHITECTURE),
                        replace(self.handoff.resulting_project, project_status=ProjectStatus.BLOCKED)):
            with self.assertRaises(ValueError):
                approve_plan(handoff=replace(self.handoff, resulting_project=project),
                             finalization=self.finalization, approval_statement=APPROVAL_STATEMENT)

    def test_forged_approval_eligibility_and_frozen_consistency_rejected(self):
        for field, value in (("approval_eligible", False), ("approved", False),
                             ("plan_finalization_id", FINALIZATION_ID + "0")):
            candidate = self.approved.canonical_dict()
            candidate[field] = value
            with self.assertRaises(ValueError):
                ApprovedPlan.from_dict(candidate)
        candidate = self.approved.canonical_dict()
        candidate["package"]["consistency"]["warnings"] = []
        with self.assertRaises(ValueError):
            ApprovedPlan.from_dict(candidate)

    def test_stale_finalization_and_modified_approved_plan_rejected(self):
        root = self.copy_authority()
        path = root / "production_plan/plan_resolution/plan_finalization.json"
        original = path.read_bytes()
        path.write_bytes(PlanFinalization.start(self.plan, handoff=self.handoff).canonical_json().encode("utf-8"))
        with self.assertRaises(ValueError):
            validate_plan_approval_package(root)
        path.write_bytes(original)
        path = root / APPROVAL_AREA / "approved_plan.json"
        candidate = self.approved.canonical_dict()
        candidate["approval_statement"] = "Approve another scope."
        path.write_bytes(canonical_bytes(candidate))
        with self.assertRaises(ValueError):
            validate_plan_approval_package(root)

    def test_approval_alone_never_transitions_generates_executes_or_writes(self):
        from arcadev import architecture_engine, domain_model_engine, backend_generation
        from tools import generate
        with ExitStack() as stack:
            for owner, name in ((PlanArchitectureHandoff, "create"),
                    (architecture_engine, "generate_baseline_architecture"),
                    (domain_model_engine, "generate_baseline_domain_model"),
                    (backend_generation, "generate_backend"), (generate, "generate_module"),
                    (socket, "socket"), (subprocess, "Popen"), (Path, "write_bytes"), (Path, "write_text")):
                stack.enter_context(patch.object(owner, name, side_effect=AssertionError(name)))
            result = production_plan_approval_package()
        self.assertEqual(set(result), APPROVAL_FILES)
        self.assertEqual(self.handoff.resulting_project.current_build_stage, BuildStage.PLAN)
        self.assertFalse(hasattr(self.approved, "architecture_specification"))


if __name__ == "__main__":
    unittest.main()
