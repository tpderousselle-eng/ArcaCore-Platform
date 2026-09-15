"""Production approval authority and independent public eligibility gates."""

from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from arcadev import gaming_studio_architecture_approval as production
from arcadev.architecture_approval import (
    ApprovedArchitecture, ArchitectureConsistencyEvaluation,
    ArchitectureConsistencyFinding, approve_architecture, validate_approved_architecture,
)
from arcadev.architecture_clarification import ArchitectureClarificationAnswer, ArchitectureFinalization
from arcadev.architecture_specification import ArchitectureSpecification, _parse, _safe, architecture_question_id
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes
from arcadev.project import BuildStage


class ProductionArchitectureApprovalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Public loader validates the canonical production value, not a fixture.
        cls.approved = ApprovedArchitecture.from_json((AUTHORITY_DIRECTORY /
            production.APPROVAL_AREA / "approved_architecture.json").read_text(encoding="utf-8"))
        cls.handoff = cls.approved.package.plan_handoff
        cls.spec = cls.approved.package.original_architecture
        cls.final = cls.approved.package.architecture_finalization
        cls.source = cls.handoff.resulting_project

    def approve(self, **changes):
        args = dict(source_project=self.source, handoff=self.handoff,
            architecture=self.spec, finalization=self.final,
            approval_statement=production.APPROVAL_STATEMENT)
        args.update(changes)
        return approve_architecture(**args)

    def test_exact_authorization_digest_and_scope(self):
        raw = production.production_architecture_approval_authorization()
        value = production.validate_architecture_approval_authorization(raw)
        self.assertEqual(value["approval_statement"], "I explicitly approve the complete resolved Gaming Studio ArchitectureSpecification and authorize the ARCHITECTURE → MODELS transition.")
        self.assertEqual(value["approval_statement_digest"], hashlib.sha256(value["approval_statement"].encode()).hexdigest())
        for name in ("domain_model_generation_authorized", "backend_authorized", "frontend_authorized"):
            self.assertIs(value[name], False)
        for field, replacement in (("approval_statement", "I approve something else."),
                ("project_id", "stale"), ("architecture_specification_id", "stale"),
                ("architecture_finalization_id", "stale"), ("scope", "all_stages"),
                ("domain_model_generation_authorized", True)):
            changed = {**value, field: replacement}
            changed["approval_statement_digest"] = hashlib.sha256(changed["approval_statement"].encode()).hexdigest()
            with self.subTest(field=field), self.assertRaises(ValueError):
                production.validate_architecture_approval_authorization(canonical_bytes(changed))

    def test_full_production_replay_no_transition_generation_or_side_effects(self):
        before = {p.relative_to(AUTHORITY_DIRECTORY): p.read_bytes() for p in AUTHORITY_DIRECTORY.rglob("*") if p.is_file()}
        with ExitStack() as stack:
            for target in ("arcadev.architecture_models_handoff.ArchitectureModelsHandoff.create",
                    "arcadev.domain_model_engine.generate_baseline_domain_model",
                    "arcadev.domain_model_specification.DomainModelSpecification.create",
                    "subprocess.Popen", "socket.socket", "builtins.eval", "os.system",
                    "pathlib.Path.write_bytes", "pathlib.Path.write_text"):
                stack.enter_context(patch(target, side_effect=AssertionError(target)))
            self.assertEqual(production.validate_architecture_approval_package(), self.approved)
        self.assertEqual(before, {p.relative_to(AUTHORITY_DIRECTORY): p.read_bytes() for p in AUTHORITY_DIRECTORY.rglob("*") if p.is_file()})
        self.assertEqual(self.source.current_build_stage, BuildStage.ARCHITECTURE)

    def test_exact_binding_frozen_decisions_warning_and_canonical_roundtrip(self):
        a = self.approved
        self.assertEqual(a.source_project_id, production.PROJECT_ID)
        self.assertEqual(a.architecture_id, production.ARCHITECTURE_ID)
        self.assertEqual(a.architecture_finalization_id, production.FINALIZATION_ID)
        self.assertEqual(a.approval_statement, production.APPROVAL_STATEMENT)
        self.assertTrue(a.approved and a.approval_eligible and a.effective_ready_for_approval)
        self.assertEqual(a.decision.value, "approved")
        self.assertTrue(a.package.consistency.consistent)
        self.assertEqual(a.package.consistency.blocking_findings, ())
        self.assertEqual([w.code for w in a.package.consistency.warnings], ["implementation_compatibility_not_proven"])
        resolved = json.loads((AUTHORITY_DIRECTORY / production.RESOLUTION_AREA / "architecture_finalization.json").read_bytes())
        self.assertEqual([d.canonical_dict() for d in self.final.decisions], resolved["decisions"])
        self.assertEqual(len(self.final.decisions), 8)
        for decision in self.final.decisions:
            with self.assertRaises(AttributeError):
                decision.accepted_values = ()
        self.assertEqual(self.approve(), a)
        self.assertEqual(ApprovedArchitecture.from_json(a.canonical_json()), a)

    def test_stale_binding_wrong_stage_and_forged_eligibility_rejected(self):
        for changes in (dict(finalization=replace(self.final, finalization_id="stale")),
                dict(architecture=replace(self.spec, architecture_id="stale")),
                dict(source_project=replace(self.source, current_build_stage=BuildStage.MODELS))):
            with self.subTest(changes=tuple(changes)), self.assertRaises(ValueError):
                self.approve(**changes)
        for field, value in (("approval_eligible", False), ("approved", False), ("effective_ready_for_approval", False)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_approved_architecture(replace(self.approved, **{field: value}))

    def test_unresolved_conflict_and_blocking_consistency_prevent_approval(self):
        initial = ArchitectureFinalization.start(self.spec, handoff=self.handoff)
        question = initial.unresolved_questions[0]
        answer = ArchitectureClarificationAnswer.create(target_architecture_id=self.spec.architecture_id,
            target_finalization_id=initial.finalization_id, target_question_id=architecture_question_id(question),
            user_answer="integration=GitLab", normalized_values=("integration=GitLab",), evidence=("integration=GitLab",))
        conflicted = initial.resolve(answer, handoff=self.handoff)
        self.assertTrue(conflicted.conflicts)
        for state in (initial, conflicted):
            with self.assertRaises(ValueError):
                self.approve(finalization=state)
        blocking = ArchitectureConsistencyEvaluation.create((ArchitectureConsistencyFinding.create(
            "test_blocker", "Independent consistency failure.", "blocking", ("decisions",)),))
        with patch("arcadev.architecture_approval._evaluate", return_value=blocking), self.assertRaises(ValueError):
            self.approve()

    def test_changed_persisted_statement_rejected_before_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "authority"
            shutil.copytree(AUTHORITY_DIRECTORY, root)
            path = root / production.APPROVAL_AREA / "approval_authorization.json"
            value = json.loads(path.read_bytes())
            value["approval_statement"] = "Changed approval."
            path.write_bytes(canonical_bytes(value))
            with patch.object(production, "validate_architecture_resolution_checkpoint", side_effect=AssertionError("must reject first")):
                with self.assertRaises(ValueError):
                    production.validate_architecture_approval_package(root)

    def test_inherited_multiline_request_preserved_and_architecture_text_stays_strict(self):
        self.assertIn("\r\n", self.source.original_user_request)
        original = json.loads((AUTHORITY_DIRECTORY / "production_plan/plan_approval/plan_architecture_handoff.json").read_bytes())
        self.assertEqual(self.handoff.canonical_dict(), original)
        self.assertEqual(ApprovedArchitecture.from_json(self.approved.canonical_json()).package.plan_handoff.canonical_dict(), original)
        value = self.spec.canonical_dict()
        value["components"][0]["name"] += "\nInjected label"
        with self.assertRaisesRegex(ValueError, "control characters"):
            ArchitectureSpecification.from_dict(value, handoff=self.handoff)
        with self.assertRaisesRegex(ValueError, "control characters"):
            self.approve(approval_statement="Approved\narchitecture")


class InheritedRequestEnvelopeTest(unittest.TestCase):
    def test_exception_is_opt_in_field_scoped_and_preserves_exact_json(self):
        value = {"package": {"original_user_request": "First paragraph.\r\n\tSecond paragraph."}}
        raw = canonical_bytes(value).decode("utf-8")
        with self.assertRaisesRegex(ValueError, "control characters"):
            _parse(raw)
        self.assertEqual(_parse(raw, allow_original_request=True), value)
        self.assertEqual(canonical_bytes(value).decode("utf-8"), raw)
        for name in ("name", "approval_statement", "user_answer", "message", "original_user_request\n"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "control characters"):
                _safe({name: "Text\nwith newline"}, allow_original_request=True)

    def test_other_controls_secret_unicode_size_and_unknown_fields_still_rejected(self):
        for text in ("a\x00b", "a\x01b", "a\x7fb", "password=secretvalue", "\ud800", "x" * 100_001):
            with self.subTest(text=text[:20]), self.assertRaises(ValueError):
                _safe({"original_user_request": text}, allow_original_request=True)
        # An allowed envelope string does not establish a certified parent.
        with self.assertRaises(ValueError):
            ApprovedArchitecture.from_json('{"original_user_request":"first\\nsecond"}')


if __name__ == "__main__":
    unittest.main()
