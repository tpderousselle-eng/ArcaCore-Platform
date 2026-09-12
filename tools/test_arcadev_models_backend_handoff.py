"""ArcaDev 4.5 certification; Gaming Studio decisions are TEST FIXTURE ONLY."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from arcadev import (
    ApprovalDecision, BackendTransitionDecision, BuildStage, ModelsBackendHandoff,
    ModelFinalization, ProjectStatus, approve_domain_model, reject_domain_model,
    create_models_backend_handoff, validate_models_backend_handoff,
)
from arcadev.model_approval import _certified_sources
from tools.test_arcadev_model_approval import approved_model, advisory_model_approval
from tools.test_arcadev_model_clarification import answer_for
from tools.test_arcadev_domain_model_engine import rename_entity


class ModelsBackendHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.approved = approved_model()
        cls.architecture_handoff = cls.approved.package.architecture_handoff
        cls.source = cls.architecture_handoff.resulting_project
        cls.model = cls.approved.package.original_model
        cls.complete = cls.approved.package.model_finalization
        cls.initial = ModelFinalization.start(cls.model, handoff=cls.architecture_handoff)
        cls.handoff = create_models_backend_handoff(source_project=cls.source, approved_domain_model=cls.approved)

    def transition(self, **changes):
        args = dict(source_project=self.source, approved_domain_model=self.approved)
        args.update(changes)
        return create_models_backend_handoff(**args)

    def test_gaming_studio_backend_transition(self):
        result = self.handoff
        self.assertTrue(result.transition_eligible)
        self.assertEqual(result.decision, BackendTransitionDecision.TRANSITIONED)
        self.assertEqual(result.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        self.assertEqual(result.resulting_project.current_build_stage, BuildStage.BACKEND)
        self.assertEqual(result.frozen_approved_domain_model, self.approved)
        self.assertTrue(result.frozen_approved_domain_model.package.consistency.consistent)
        self.assertTrue(result.frozen_approved_domain_model.package.resolved_model.entities)

    def test_every_upstream_binding_is_exact(self):
        for field in ("source_project_id", "plan_handoff_id", "approved_architecture_id", "architecture_id",
            "architecture_finalization_id", "architecture_handoff_id", "model_id", "model_finalization_id"):
            self.assertEqual(getattr(self.handoff, field), getattr(self.approved, field))
        self.assertEqual(self.handoff.approved_domain_model_id, self.approved.approval_id)
        self.assertEqual(self.handoff.architecture_handoff_id, self.architecture_handoff.handoff_id)
        self.assertEqual(self.handoff.model_id, self.model.model_id)
        self.assertEqual(self.handoff.model_finalization_id, self.complete.finalization_id)

    def test_all_frozen_authority_preserved(self):
        before = tuple(v.canonical_json() for v in (self.source, self.approved, self.architecture_handoff,
            self.architecture_handoff.frozen_approved_architecture, self.model, self.complete))
        result = self.transition()
        package = result.frozen_approved_domain_model.package
        self.assertEqual(package.architecture_handoff, self.architecture_handoff)
        self.assertEqual(package.original_model, self.model)
        self.assertEqual(package.model_finalization, self.complete)
        self.assertEqual(package.resolved_model, self.approved.package.resolved_model)
        self.assertEqual(before, tuple(v.canonical_json() for v in (self.source, self.approved, self.architecture_handoff,
            self.architecture_handoff.frozen_approved_architecture, self.model, self.complete)))

    def test_source_remains_models_and_result_is_new_value(self):
        self.assertIsNot(self.source, self.handoff.resulting_project)
        self.assertEqual(self.source.project_status, ProjectStatus.IN_PROGRESS)
        self.assertEqual(self.source.current_build_stage, BuildStage.MODELS)
        self.assertEqual(replace(self.handoff.resulting_project, current_build_stage=BuildStage.MODELS), self.source)
        self.assertEqual(self.source.metadata, self.handoff.resulting_project.metadata)

    def test_deep_immutability_and_defensive_serialization(self):
        for obj, field, value in ((self.handoff, "transition_eligible", False),
            (self.handoff.resulting_project, "current_build_stage", BuildStage.MODELS),
            (self.handoff.frozen_approved_domain_model, "approved", False),
            (self.complete.decisions[0].claims[0], "values", ())):
            with self.assertRaises(AttributeError):
                setattr(obj, field, value)
        raw = self.handoff.canonical_dict()
        raw["frozen_approved_domain_model"]["package"]["resolved_model"]["entities"].clear()
        self.assertEqual(self.handoff.frozen_approved_domain_model, self.approved)

    def test_deterministic_identity(self):
        self.assertEqual(self.handoff.canonical_json(), self.transition().canonical_json())

    def test_canonical_roundtrip(self):
        self.assertEqual(self.handoff, ModelsBackendHandoff.from_json(self.handoff.canonical_json()))
        self.assertEqual(self.handoff, ModelsBackendHandoff.from_dict(dict(reversed(list(self.handoff.canonical_dict().items())))))

    def test_explicit_approval_required(self):
        for candidate in (self.model, self.complete, None, object(), self.approved.canonical_dict()):
            with self.assertRaises(ValueError):
                self.transition(approved_domain_model=candidate)
        for field, value in (("approved", False), ("decision", ApprovalDecision.REJECTED), ("approval_id", "forged")):
            with self.assertRaises(ValueError):
                self.transition(approved_domain_model=replace(self.approved, **{field: value}))

    def test_ready_and_unready_rejected_models_refused(self):
        for state in (self.initial, self.complete):
            rejected = reject_domain_model(handoff=self.architecture_handoff, model=self.model, finalization=state,
                approval_statement="TEST FIXTURE ONLY: rejected for review.")
            with self.assertRaisesRegex(ValueError, "explicit domain model approval"):
                self.transition(approved_domain_model=rejected)

    def test_forged_readiness_eligibility_and_consistency_refused(self):
        for field in ("approval_eligible", "effective_ready_for_approval"):
            with self.assertRaises(ValueError):
                self.transition(approved_domain_model=replace(self.approved, **{field: False}))
        for changes in (dict(consistent=False), dict(warnings=()), dict(blocking_findings=self.approved.package.consistency.warnings)):
            forged = replace(self.approved, package=replace(self.approved.package,
                consistency=replace(self.approved.package.consistency, **changes)))
            with self.assertRaises(ValueError):
                self.transition(approved_domain_model=forged)

    def test_unresolved_blocking_questions_refused(self):
        forged = replace(self.approved, package=replace(self.approved.package, model_finalization=self.initial))
        with self.assertRaises(ValueError):
            self.transition(approved_domain_model=forged)

    def test_active_conflicts_refused(self):
        state = self.initial.resolve(answer_for(self.initial, self.initial.unresolved_questions[0], ("unsupported",)),
            handoff=self.architecture_handoff)
        self.assertTrue(state.conflicts)
        forged = replace(self.approved, package=replace(self.approved.package, model_finalization=state))
        with self.assertRaises(ValueError):
            self.transition(approved_domain_model=forged)

    def test_advisory_question_blocks_transition_of_valid_approval(self):
        approved = advisory_model_approval()
        self.assertTrue(approved.approved)
        self.assertTrue(approved.package.consistency.consistent)
        self.assertFalse(any(q.blocking for q in approved.package.model_finalization.unresolved_questions))
        with self.assertRaisesRegex(ValueError, "no unresolved model questions"):
            self.transition(approved_domain_model=approved)

    def test_every_non_models_stage_and_wrong_status_refused(self):
        for stage in BuildStage:
            if stage is not BuildStage.MODELS:
                source = replace(self.source, current_build_stage=stage)
                with self.subTest(stage=stage), self.assertRaises(ValueError):
                    self.transition(source_project=source)
        for status in ProjectStatus:
            if status is not ProjectStatus.IN_PROGRESS:
                with self.subTest(status=status), self.assertRaises(ValueError):
                    self.transition(source_project=replace(self.source, project_status=status))

    def test_already_transitioned_source_refused(self):
        with self.assertRaises(ValueError):
            self.transition(source_project=self.handoff.resulting_project)
        with self.assertRaises(ValueError):
            validate_models_backend_handoff(self.handoff, source_project=self.handoff.resulting_project)

    def test_current_source_compares_complete_content(self):
        for source in (replace(self.source, project_id="forged"), replace(self.source, project_name="Stale same ID"),
            replace(self.source, metadata=replace(self.source.metadata, schema_version=True)),
            replace(self.source, metadata=replace(self.source.metadata, updated_at="2026-09-11T00:00:00Z"))):
            with self.assertRaises(ValueError):
                self.transition(source_project=source)
            with self.assertRaises(ValueError):
                validate_models_backend_handoff(self.handoff, source_project=source)

    def test_current_upstream_references_and_same_id_mutations(self):
        refs = dict(source_project=self.source, approved_domain_model=self.approved, handoff=self.architecture_handoff,
            model=self.model, finalization=self.complete)
        self.assertEqual(validate_models_backend_handoff(self.handoff.canonical_json(), **refs), self.handoff)
        for current in (dict(handoff=replace(self.architecture_handoff, resulting_project=replace(self.source, project_name="Stale"))),
            dict(model=replace(self.model, entities=())), dict(finalization=replace(self.complete, history=()))):
            with self.assertRaises(ValueError):
                self.transition(**current)
            with self.assertRaises(ValueError):
                validate_models_backend_handoff(self.handoff, **current)
        with self.assertRaises(ValueError):
            validate_models_backend_handoff(self.handoff, approved_domain_model=replace(self.approved, approval_statement="Stale same ID"))

    def test_different_valid_approval_changes_handoff_identity(self):
        other = approve_domain_model(handoff=self.architecture_handoff, model=self.model, finalization=self.complete,
            approval_statement="TEST FIXTURE ONLY: another explicit approval.")
        self.assertNotEqual(self.transition(approved_domain_model=other).handoff_id, self.handoff.handoff_id)
        with self.assertRaises(ValueError):
            validate_models_backend_handoff(self.handoff, approved_domain_model=other)
        # Standalone validation proves historical integrity without claiming freshness.
        self.assertEqual(validate_models_backend_handoff(self.handoff), self.handoff)

    def test_different_valid_model_and_finalization_are_stale(self):
        alternate = rename_entity(self.model, self.architecture_handoff, self.model.entities[0], "Alternate state")
        for current in (dict(model=alternate), dict(finalization=self.initial)):
            with self.assertRaises(ValueError):
                self.transition(**current)
            with self.assertRaises(ValueError):
                validate_models_backend_handoff(self.handoff, **current)

    def test_every_handoff_identity_refuses_forgery(self):
        for field in ("handoff_id", "source_project_id", "plan_handoff_id", "approved_architecture_id", "architecture_id",
            "architecture_finalization_id", "architecture_handoff_id", "model_id", "model_finalization_id", "approved_domain_model_id"):
            raw = self.handoff.canonical_dict()
            raw[field] = "forged"
            with self.subTest(field=field), self.assertRaises(ValueError):
                ModelsBackendHandoff.from_dict(raw)

    def test_forged_transition_flags_and_resulting_project(self):
        for field, value in (("transition_eligible", False), ("transition_eligible", 1), ("decision", "approved"), ("decision", "blocked")):
            raw = self.handoff.canonical_dict()
            raw[field] = value
            with self.assertRaises(ValueError):
                ModelsBackendHandoff.from_dict(raw)
        for field, value in (("current_build_stage", "MODELS"), ("current_build_stage", "FRONTEND"),
            ("project_status", "COMPLETED"), ("project_id", "forged"), ("project_name", "Changed"), ("backend", [])):
            raw = self.handoff.canonical_dict()
            raw["resulting_project"][field] = value
            with self.assertRaises(ValueError):
                ModelsBackendHandoff.from_dict(raw)

    def test_standalone_load_reconstructs_entire_frozen_package(self):
        for mutate in (
            lambda a: a.update(approval_id="forged"),
            lambda a: a.update(approved=False),
            lambda a: a.update(approval_eligible=False),
            lambda a: a.update(effective_ready_for_approval=False),
            lambda a: a["package"]["consistency"].update(warnings=[]),
            lambda a: a["package"]["model_finalization"]["history"].pop(),
            lambda a: a["package"]["model_finalization"]["decisions"][0]["claims"][0].update(values=["forged"]),
            lambda a: a["package"]["original_model"].update(entities=[]),
            lambda a: a["package"]["resolved_model"].update(entities=[]),
            lambda a: a["package"]["architecture_handoff"]["frozen_approved_architecture"].update(approval_statement="Changed."),
        ):
            raw = self.handoff.canonical_dict()
            mutate(raw["frozen_approved_domain_model"])
            with self.assertRaises(ValueError):
                ModelsBackendHandoff.from_dict(raw)

    def test_malformed_duplicate_unknown_schema_and_oversized_json(self):
        for raw in ("{", '{"schema":1,"schema":2}', " " * 5_000_001, "[" * 1000, "null", "[]", object()):
            with self.assertRaises(ValueError):
                ModelsBackendHandoff.from_json(raw)
        for field, value in (("provider", "vendor"), ("schema", "wrong"), ("schema_version", 2), ("schema_version", True),
            ("frozen_approved_domain_model", object()), ("backend_files", [])):
            raw = self.handoff.canonical_dict()
            raw[field] = value
            with self.assertRaises(ValueError):
                ModelsBackendHandoff.from_dict(raw)

    def test_secrets_private_keys_tokens_and_executable_objects_rejected(self):
        for value in ("password=x", "access_token=abc", "ghp_abcdefghijklmnop", "sk-abcdefghijklmnopqrst", "Bearer opaque",
            "-----BEGIN PRIVATE KEY-----", "\ud800", "bad\x01", lambda: "execute"):
            raw = self.handoff.canonical_dict()
            raw["frozen_approved_domain_model"]["approval_statement"] = value
            with self.assertRaises(ValueError):
                ModelsBackendHandoff.from_dict(raw)
        class ExecutableDict(dict):
            def items(self):
                raise AssertionError("Must not execute")
        with self.assertRaises(ValueError):
            ModelsBackendHandoff.from_dict(ExecutableDict(self.handoff.canonical_dict()))

    def test_hostile_text_inert_and_absolute_generation_boundary(self):
        approved = approve_domain_model(handoff=self.architecture_handoff, model=self.model, finalization=self.complete,
            approval_statement="Approved; DROP TABLE records; $(echo inert); __import__('os').system('echo no'); C:/inert/path")
        before = self.source.canonical_json(), approved.canonical_json()
        _certified_sources.cache_clear()
        with patch("tools.generate.generate_module", side_effect=AssertionError("ArcaCore invocation")), \
             patch("subprocess.Popen", side_effect=AssertionError("execution")), patch("builtins.eval", side_effect=AssertionError("eval")), \
             patch("socket.create_connection", side_effect=AssertionError("network")), patch("builtins.open", side_effect=AssertionError("filesystem")):
            result = self.transition(approved_domain_model=approved)
            self.assertEqual(result, ModelsBackendHandoff.from_json(result.canonical_json()))
        self.assertEqual(before, (self.source.canonical_json(), approved.canonical_json()))
        for name in ("backend", "frontend", "sql", "tables", "orm", "migrations", "repositories", "services", "routers",
            "api_contracts", "indexes", "physical_constraints", "docker", "kubernetes", "generated_artifacts"):
            self.assertNotIn(name, result.canonical_dict())
            self.assertFalse(hasattr(result, name))


if __name__ == "__main__":
    unittest.main()
