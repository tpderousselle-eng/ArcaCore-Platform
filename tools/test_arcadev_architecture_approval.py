"""ArcaDev 3.4 certification; Gaming Studio choices remain test fixtures only."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from arcadev import (
    ApprovalDecision, ApprovedArchitecture, ArchitectureFinalization, ArchitectureSpecification,
    ArchitectureConsistencyEvaluation, ArchitectureConsistencyFinding, ArchitectureFindingSeverity,
    BuildStage, ProjectStatus, approve_architecture, reject_architecture,
    evaluate_architecture_consistency, validate_approved_architecture,
    generate_baseline_architecture,
)
from tools.test_arcadev_architecture_specification import approved_handoff
from tools.test_arcadev_architecture_clarification import answer_for, fixture_choice


def resolved_architecture():
    handoff = approved_handoff()
    architecture = generate_baseline_architecture(handoff)
    initial = ArchitectureFinalization.start(architecture, handoff=handoff)
    state = initial
    for question in initial.unresolved_questions:
        state = state.resolve(answer_for(state, question, fixture_choice(question)), handoff=handoff)
    return handoff, architecture, initial, state


class ArcaDevArchitectureApprovalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff, cls.spec, cls.initial, cls.complete = resolved_architecture()
        cls.approved = approve_architecture(handoff=cls.handoff, architecture=cls.spec,
            finalization=cls.complete, approval_statement="I explicitly approve this Gaming Studio architecture.")

    def approve(self, **changes):
        args = dict(handoff=self.handoff, architecture=self.spec, finalization=self.complete, approval_statement="Approved.")
        args.update(changes)
        return approve_architecture(**args)

    def test_gaming_studio_explicit_approval_and_frozen_package(self):
        result = self.approved
        self.assertTrue(result.approved)
        self.assertTrue(result.approval_eligible)
        self.assertTrue(result.effective_ready_for_approval)
        self.assertTrue(result.package.consistency.consistent)
        self.assertEqual(result.decision, ApprovalDecision.APPROVED)
        self.assertEqual(result.package.original_architecture.canonical_json(), self.spec.canonical_json())
        self.assertEqual(result.package.plan_handoff.canonical_json(), self.handoff.canonical_json())
        self.assertEqual(result.package.architecture_finalization, self.complete)
        self.assertEqual(len(self.complete.decisions), 8)
        self.assertEqual(self.complete.unresolved_questions, ())
        self.assertEqual(self.complete.conflicts, ())

    def test_explicit_decision_and_statement_required(self):
        with self.assertRaises(TypeError):
            ApprovedArchitecture.create(handoff=self.handoff, architecture=self.spec, finalization=self.complete, approval_statement="Approved.")
        for statement in ("", " ", None, 1):
            with self.subTest(statement=statement), self.assertRaises(ValueError):
                self.approve(approval_statement=statement)
        with self.assertRaises(ValueError):
            ApprovedArchitecture.create(handoff=self.handoff, architecture=self.spec, finalization=self.complete, decision="ready", approval_statement="Ready.")

    def test_rejection_preserves_ready_and_unready_architecture(self):
        for state in (self.initial, self.complete):
            result = reject_architecture(handoff=self.handoff, architecture=self.spec, finalization=state, approval_statement="I reject this package.")
            self.assertFalse(result.approved)
            self.assertEqual(result.decision, ApprovalDecision.REJECTED)
            self.assertEqual(result.package.architecture_finalization, state)
            self.assertEqual(ApprovedArchitecture.from_json(result.canonical_json()), result)

    def test_deterministic_identity_roundtrip_and_statement_identity(self):
        first = self.approve()
        self.assertEqual(first, self.approve())
        self.assertEqual(first, ApprovedArchitecture.from_json(first.canonical_json()))
        self.assertEqual(first, ApprovedArchitecture.from_dict(dict(reversed(list(first.canonical_dict().items())))))
        self.assertNotEqual(first.approval_id, self.approve(approval_statement="Another explicit approval.").approval_id)

    def test_snapshot_is_deeply_immutable(self):
        with self.assertRaises(AttributeError):
            self.approved.approved = False
        with self.assertRaises(AttributeError):
            self.approved.package.architecture_finalization.decisions[0].accepted_values = ()
        value = self.approved.canonical_dict()
        value["package"]["original_architecture"]["components"].clear()
        self.assertEqual(self.approved.package.original_architecture, self.spec)

    def test_readiness_and_unresolved_blockers(self):
        evaluation = evaluate_architecture_consistency(self.handoff, self.spec, self.initial)
        self.assertFalse(evaluation.consistent)
        self.assertIn("unresolved_architecture_blockers", {f.code for f in evaluation.blocking_findings})
        with self.assertRaisesRegex(ValueError, "cannot be approved"):
            self.approve(finalization=self.initial)
        with self.assertRaises(ValueError):
            self.approve(finalization=replace(self.initial, effective_ready_for_approval=True))

    def test_active_conflict_and_plan_authority_contradictions(self):
        q = self.initial.unresolved_questions[0]
        for value in ("platform=iOS only", "authentication=passkeys only", "integration=GitLab", "deployment=Self hosted", "capability=Billing", "Remove GitHub", "Disable build isolation"):
            with self.subTest(value=value):
                state = self.initial.resolve(answer_for(self.initial, q, value), handoff=self.handoff)
                self.assertTrue(state.conflicts)
                evaluation = evaluate_architecture_consistency(self.handoff, self.spec, state)
                self.assertIn("active_architecture_conflicts", {f.code for f in evaluation.blocking_findings})
                with self.assertRaises(ValueError):
                    self.approve(finalization=state)

    def test_unknown_implementation_compatibility_is_warning(self):
        evaluation = evaluate_architecture_consistency(self.handoff, self.spec, self.complete)
        self.assertTrue(evaluation.consistent)
        self.assertFalse(evaluation.blocking_findings)
        self.assertEqual(evaluation.warnings[0].severity, ArchitectureFindingSeverity.WARNING)
        self.assertEqual(ArchitectureConsistencyEvaluation.from_dict(evaluation.canonical_dict()), evaluation)

    def test_consistency_finding_validation(self):
        finding = ArchitectureConsistencyFinding.create("known_contradiction", "A deterministic contradiction.", "blocking", ("decisions",))
        self.assertFalse(ArchitectureConsistencyEvaluation.create((finding,)).consistent)
        with self.assertRaises(ValueError):
            ArchitectureConsistencyEvaluation.create((finding, finding))
        with self.assertRaises(ValueError):
            ArchitectureConsistencyEvaluation.create((object(),))
        value = ArchitectureConsistencyEvaluation.create((finding,)).canonical_dict()
        value["consistent"] = True
        with self.assertRaises(ValueError):
            ArchitectureConsistencyEvaluation.from_dict(value)

    def test_exact_source_identity_bindings(self):
        for field in ("source_project_id", "plan_handoff_id", "architecture_id", "architecture_finalization_id", "approval_id"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                value = self.approved.canonical_dict()
                value[field] = "forged"
                ApprovedArchitecture.from_dict(value)
        for field in ("project_id", "handoff_id", "architecture_id"):
            with self.subTest(source_field=field), self.assertRaises(ValueError):
                self.approve(architecture=replace(self.spec, **{field: "forged"}))
        with self.assertRaises(ValueError):
            self.approve(finalization=replace(self.complete, finalization_id="forged"))
        with self.assertRaises(ValueError):
            self.approve(handoff=replace(self.handoff, handoff_id="forged"))

    def test_stale_architecture_and_finalization(self):
        values = self.spec.canonical_dict()
        args = {k: values[k] for k in ("objective", "system_boundary", "style", "external_entities", "approved_constraints", "components", "interfaces", "data_flows", "aspects", "open_architecture_questions")}
        from arcadev import ArchitectureFact
        for key in ("objective", "system_boundary", "style"):
            args[key] = ArchitectureFact.from_dict(args[key], handoff=self.handoff)
        args["components"][0]["name"] = "Alternate logical name"
        alternate = ArchitectureSpecification.create(handoff=self.handoff, **args)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.approve(architecture=alternate)
        for current in (dict(architecture=alternate), dict(finalization=self.initial), dict(handoff=replace(self.handoff, handoff_id="forged"))):
            with self.assertRaises(ValueError):
                validate_approved_architecture(self.approved, **current)

    def test_current_source_project_exact_state(self):
        source = self.handoff.resulting_project
        self.assertEqual(self.approve(source_project=source), self.approve())
        for project in (replace(source, current_build_stage=BuildStage.MODELS), replace(source, project_status=ProjectStatus.BLOCKED), replace(source, project_id="forged"), replace(source, metadata=replace(source.metadata, updated_at="2026-09-11T00:00:00Z"))):
            with self.assertRaises(ValueError):
                self.approve(source_project=project)

    def test_capability_ownership_and_unsupported_scope(self):
        for owned in ([], ["billing"]):
            value = self.approved.canonical_dict()
            owner = next(c for c in value["package"]["original_architecture"]["components"] if c["owned_capabilities"])
            owner["owned_capabilities"] = owned
            with self.assertRaises(ValueError):
                ApprovedArchitecture.from_dict(value)

    def test_integration_authentication_deployment_and_platform_consistency(self):
        for approved in ("GitHub", "Email/password", "Google OAuth", "ArcaCentum managed cloud", "Desktop web", "Mobile web"):
            value = self.approved.canonical_dict()
            facts = value["package"]["original_architecture"]["approved_constraints"]
            facts[:] = [f for f in facts if f["value"] != approved]
            with self.subTest(approved=approved), self.assertRaises(ValueError):
                ApprovedArchitecture.from_dict(value)
        for area in ("integration", "authentication", "deployment"):
            value = self.approved.canonical_dict()
            aspects = value["package"]["original_architecture"]["aspects"]
            aspects[:] = [a for a in aspects if a["area"] != area]
            with self.subTest(area=area), self.assertRaises(ValueError):
                ApprovedArchitecture.from_dict(value)

    def test_component_interface_and_data_flow_integrity(self):
        for collection, field, invalid in (("components", "dependencies", ["missing"]), ("components", "exposed_interfaces", ["missing"]), ("interfaces", "source", "missing"), ("data_flows", "destination", "missing")):
            value = self.approved.canonical_dict()
            value["package"]["original_architecture"][collection][0][field] = invalid
            with self.subTest(collection=collection, field=field), self.assertRaises(ValueError):
                ApprovedArchitecture.from_dict(value)

    def test_forged_consistency_eligibility_and_approval(self):
        for field, invalid in (("approval_eligible", False), ("approved", False), ("decision", "rejected"), ("effective_ready_for_approval", False), ("approved", 1)):
            value = self.approved.canonical_dict()
            value[field] = invalid
            with self.subTest(field=field), self.assertRaises(ValueError):
                ApprovedArchitecture.from_dict(value)
        value = self.approved.canonical_dict()
        value["package"]["consistency"]["warnings"] = []
        with self.assertRaises(ValueError):
            ApprovedArchitecture.from_dict(value)

    def test_tampered_history_decisions_and_frozen_plan(self):
        for field in ("history", "decisions"):
            value = self.approved.canonical_dict()
            value["package"]["architecture_finalization"][field] = []
            with self.assertRaises(ValueError):
                ApprovedArchitecture.from_dict(value)
        value = self.approved.canonical_dict()
        value["package"]["plan_handoff"]["frozen_approved_plan"]["approval_statement"] = "Tampered upstream approval."
        with self.assertRaises(ValueError):
            ApprovedArchitecture.from_dict(value)

    def test_json_and_schema_safety(self):
        for candidate in ("{", '{"schema":1,"schema":2}', " " * 5_000_001, "[" * 1000, object()):
            with self.assertRaises(ValueError):
                ApprovedArchitecture.from_json(candidate)
        for field, value in (("provider", "model"), ("schema", "wrong"), ("schema_version", 2), ("schema_version", True), ("package", object())):
            candidate = self.approved.canonical_dict()
            candidate[field] = value
            with self.assertRaises(ValueError):
                ApprovedArchitecture.from_dict(candidate)
        class ExecutableDict(dict):
            def items(self):
                raise AssertionError("Must not execute")
        with self.assertRaises(ValueError):
            ApprovedArchitecture.from_dict(ExecutableDict(self.approved.canonical_dict()))

    def test_statement_safety(self):
        for value in ("api_key=abcdef", "-----BEGIN RSA PRIVATE KEY-----", "\ud800", "bad\x01", "line\nbreak", "x" * 20_001, object()):
            with self.subTest(value=repr(value)[:60]), self.assertRaises(ValueError):
                self.approve(approval_statement=value)

    def test_inert_content_no_generation_and_architecture_stage(self):
        before = self.handoff.canonical_json(), self.spec.canonical_json(), self.complete.canonical_json()
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), patch("builtins.eval", side_effect=AssertionError("eval")), patch("socket.create_connection", side_effect=AssertionError("network")), patch("builtins.open", side_effect=AssertionError("filesystem")):
            approved = self.approve(approval_statement="Approved; $(echo hostile); __import__('os').system('echo no'); C:/inert/path")
            self.assertEqual(ApprovedArchitecture.from_json(approved.canonical_json()), approved)
        self.assertEqual(before, (self.handoff.canonical_json(), self.spec.canonical_json(), self.complete.canonical_json()))
        self.assertEqual(self.handoff.resulting_project.current_build_stage, BuildStage.ARCHITECTURE)
        self.assertEqual(self.handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        for name in ("models", "entities", "schemas", "migrations", "backend", "frontend", "resulting_project"):
            self.assertFalse(hasattr(approved, name))


if __name__ == "__main__":
    unittest.main()
