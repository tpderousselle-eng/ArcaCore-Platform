"""ArcaDev 3.5 certification; no application model design or generation."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from arcadev import (
    ArchitectureArea, ArchitectureFinalization, ArchitectureModelsHandoff,
    ArchitectureQuestion, ArchitectureSpecification, BuildStage, ModelsTransitionDecision,
    ProjectStatus, approve_architecture, reject_architecture,
    create_architecture_models_handoff, validate_architecture_models_handoff,
)
from tools.test_arcadev_architecture_approval import resolved_architecture
from tools.test_arcadev_architecture_clarification import answer_for, fixture_choice


class ArcaDevArchitectureModelsHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan_handoff, cls.spec, cls.initial, cls.complete = resolved_architecture()
        cls.source = cls.plan_handoff.resulting_project
        cls.approved = approve_architecture(handoff=cls.plan_handoff, architecture=cls.spec,
            finalization=cls.complete, approval_statement="I explicitly approve this Gaming Studio architecture.")
        cls.handoff = create_architecture_models_handoff(source_project=cls.source, approved_architecture=cls.approved)

    def transition(self, **changes):
        args = dict(source_project=self.source, approved_architecture=self.approved)
        args.update(changes)
        return create_architecture_models_handoff(**args)

    def test_gaming_studio_transition_and_complete_authority(self):
        result = self.handoff
        self.assertTrue(result.transition_eligible)
        self.assertEqual(result.decision, ModelsTransitionDecision.TRANSITIONED)
        self.assertEqual(result.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        self.assertEqual(result.resulting_project.current_build_stage, BuildStage.MODELS)
        self.assertEqual(result.frozen_approved_architecture.canonical_json(), self.approved.canonical_json())
        self.assertEqual(result.frozen_approved_architecture.package.plan_handoff, self.plan_handoff)
        self.assertEqual(result.frozen_approved_architecture.package.original_architecture, self.spec)
        self.assertEqual(result.frozen_approved_architecture.package.architecture_finalization, self.complete)
        self.assertTrue(result.frozen_approved_architecture.package.consistency.consistent)

    def test_deterministic_identity_and_canonical_roundtrip(self):
        self.assertEqual(self.handoff, self.transition())
        self.assertEqual(self.handoff, ArchitectureModelsHandoff.from_json(self.handoff.canonical_json()))
        reordered = dict(reversed(list(self.handoff.canonical_dict().items())))
        self.assertEqual(self.handoff, ArchitectureModelsHandoff.from_dict(reordered))
        self.assertEqual(self.handoff, validate_architecture_models_handoff(self.handoff.canonical_json(),
            source_project=self.source, approved_architecture=self.approved, handoff=self.plan_handoff,
            architecture=self.spec, finalization=self.complete))

    def test_original_project_and_all_snapshots_immutable(self):
        self.assertEqual(self.source.current_build_stage, BuildStage.ARCHITECTURE)
        self.assertEqual(self.source.project_status, ProjectStatus.IN_PROGRESS)
        self.assertIsNot(self.source, self.handoff.resulting_project)
        self.assertEqual(replace(self.handoff.resulting_project, current_build_stage=BuildStage.ARCHITECTURE), self.source)
        with self.assertRaises(AttributeError):
            self.handoff.resulting_project.current_build_stage = BuildStage.BACKEND
        with self.assertRaises(AttributeError):
            self.handoff.frozen_approved_architecture.approved = False
        copied = self.handoff.canonical_dict()
        copied["frozen_approved_architecture"]["package"]["architecture_finalization"]["decisions"].clear()
        self.assertEqual(len(self.handoff.frozen_approved_architecture.package.architecture_finalization.decisions), 8)

    def test_explicit_approval_required_and_rejected_state_refused(self):
        for state in (self.initial, self.complete):
            rejected = reject_architecture(handoff=self.plan_handoff, architecture=self.spec, finalization=state, approval_statement="Rejected for review.")
            with self.assertRaisesRegex(ValueError, "explicit architecture approval"):
                self.transition(approved_architecture=rejected)
        for candidate in (self.spec, self.complete, None, object()):
            with self.assertRaises(ValueError):
                self.transition(approved_architecture=candidate)

    def test_readiness_consistency_and_eligibility_cannot_be_forged(self):
        for field in ("approved", "approval_eligible", "effective_ready_for_approval"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.transition(approved_architecture=replace(self.approved, **{field: False}))
        forged = replace(self.approved, package=replace(self.approved.package,
            consistency=replace(self.approved.package.consistency, consistent=False)))
        with self.assertRaises(ValueError):
            self.transition(approved_architecture=forged)
        forged = replace(self.approved, package=replace(self.approved.package, architecture_finalization=self.initial))
        with self.assertRaises(ValueError):
            self.transition(approved_architecture=forged)

    def test_unresolved_blockers_and_active_conflicts_refused(self):
        conflicted = self.initial.resolve(answer_for(self.initial, self.initial.unresolved_questions[0], "Remove GitHub"), handoff=self.plan_handoff)
        self.assertTrue(conflicted.conflicts)
        for state in (self.initial, conflicted):
            forged = replace(self.approved, package=replace(self.approved.package, architecture_finalization=state))
            with self.assertRaises(ValueError):
                self.transition(approved_architecture=forged)

    def test_even_advisory_questions_must_be_resolved_before_models(self):
        # 3.4 permits advisory questions; 3.5 deliberately closes all questions.
        question = ArchitectureQuestion.create("Which review order should implementation use?", False,
            self.spec.objective.source_requirements, ArchitectureArea.CONTEXT, handoff=self.plan_handoff)
        args = {key: getattr(self.spec, key) for key in ("objective", "system_boundary", "style", "external_entities",
            "approved_constraints", "components", "interfaces", "data_flows", "aspects", "open_architecture_questions")}
        args["open_architecture_questions"] += (question,)
        spec = ArchitectureSpecification.create(handoff=self.plan_handoff, **args)
        state = ArchitectureFinalization.start(spec, handoff=self.plan_handoff)
        for q in tuple(state.unresolved_questions):
            if q.blocking:
                state = state.resolve(answer_for(state, q, fixture_choice(q)), handoff=self.plan_handoff)
        self.assertTrue(state.effective_ready_for_approval)
        approved = approve_architecture(handoff=self.plan_handoff, architecture=spec, finalization=state, approval_statement="Approved with advisory review question.")
        self.assertTrue(approved.approved)
        with self.assertRaisesRegex(ValueError, "no unresolved"):
            self.transition(approved_architecture=approved)

    def test_exact_binding_across_every_source_identity(self):
        for field in ("handoff_id", "source_project_id", "plan_handoff_id", "approved_architecture_id", "architecture_id", "architecture_finalization_id"):
            value = self.handoff.canonical_dict()
            value[field] = "forged"
            with self.subTest(field=field), self.assertRaises(ValueError):
                ArchitectureModelsHandoff.from_dict(value)
        for field in ("approval_id", "architecture_id", "architecture_finalization_id", "plan_handoff_id"):
            with self.subTest(approval_field=field), self.assertRaises(ValueError):
                self.transition(approved_architecture=replace(self.approved, **{field: "forged"}))

    def test_wrong_project_stage_status_and_already_transitioned_source(self):
        for project in (replace(self.source, project_id="forged"), replace(self.source, project_status=ProjectStatus.BLOCKED),
            replace(self.source, current_build_stage=BuildStage.PLAN), self.handoff.resulting_project,
            replace(self.source, metadata=replace(self.source.metadata, updated_at="2026-09-11T00:00:00Z"))):
            with self.assertRaises(ValueError):
                self.transition(source_project=project)
            with self.assertRaises(ValueError):
                validate_architecture_models_handoff(self.handoff, source_project=project)

    def test_stale_architecture_finalization_and_plan_handoff(self):
        for current in (dict(architecture=replace(self.spec, architecture_id="forged")), dict(finalization=self.initial),
                        dict(handoff=replace(self.plan_handoff, handoff_id="forged"))):
            with self.assertRaises(ValueError):
                self.transition(**current)
            with self.assertRaises(ValueError):
                validate_architecture_models_handoff(self.handoff, **current)
        # A changed object with the same claimed identity cannot bypass matching.
        with self.assertRaises(ValueError):
            self.transition(architecture=replace(self.spec, components=()))

    def test_different_valid_approval_changes_identity_and_replay_expectation(self):
        other = approve_architecture(handoff=self.plan_handoff, architecture=self.spec, finalization=self.complete,
            approval_statement="A separate explicit approval statement.")
        self.assertNotEqual(self.transition(approved_architecture=other).handoff_id, self.handoff.handoff_id)
        with self.assertRaises(ValueError):
            validate_architecture_models_handoff(self.handoff, approved_architecture=other)

    def test_forged_eligibility_transition_and_result(self):
        for field, replacement in (("transition_eligible", False), ("transition_eligible", 1), ("decision", "blocked"), ("decision", "approved")):
            value = self.handoff.canonical_dict()
            value[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                ArchitectureModelsHandoff.from_dict(value)
        for field, replacement in (("current_build_stage", "ARCHITECTURE"), ("current_build_stage", "BACKEND"),
                                   ("project_status", "COMPLETED"), ("project_id", "forged"), ("models", [])):
            value = self.handoff.canonical_dict()
            value["resulting_project"][field] = replacement
            with self.subTest(project_field=field), self.assertRaises(ValueError):
                ArchitectureModelsHandoff.from_dict(value)

    def test_tampered_frozen_architecture_plan_history_and_consistency(self):
        for field in ("history", "decisions"):
            value = self.handoff.canonical_dict()
            value["frozen_approved_architecture"]["package"]["architecture_finalization"][field] = []
            with self.assertRaises(ValueError):
                ArchitectureModelsHandoff.from_dict(value)
        value = self.handoff.canonical_dict()
        value["frozen_approved_architecture"]["package"]["original_architecture"]["components"] = []
        with self.assertRaises(ValueError):
            ArchitectureModelsHandoff.from_dict(value)
        value = self.handoff.canonical_dict()
        value["frozen_approved_architecture"]["package"]["plan_handoff"]["frozen_approved_plan"]["approval_statement"] = "Tampered."
        with self.assertRaises(ValueError):
            ArchitectureModelsHandoff.from_dict(value)
        value = self.handoff.canonical_dict()
        value["frozen_approved_architecture"]["package"]["consistency"]["warnings"] = []
        with self.assertRaises(ValueError):
            ArchitectureModelsHandoff.from_dict(value)

    def test_malformed_duplicate_unknown_schema_and_oversized_json(self):
        for text in ("{", '{"schema":1,"schema":2}', " " * 5_000_001, "[" * 1000, object()):
            with self.assertRaises(ValueError):
                ArchitectureModelsHandoff.from_json(text)
        for field, replacement in (("provider", "model"), ("schema", "wrong"), ("schema_version", 2), ("schema_version", True),
                                   ("frozen_approved_architecture", object()), ("models", [])):
            value = self.handoff.canonical_dict()
            value[field] = replacement
            with self.assertRaises(ValueError):
                ArchitectureModelsHandoff.from_dict(value)

    def test_secrets_and_executable_serialized_objects_rejected(self):
        for text in ("api_key=abcdef", "-----BEGIN PRIVATE KEY-----", "\ud800", "bad\x01"):
            value = self.handoff.canonical_dict()
            value["frozen_approved_architecture"]["approval_statement"] = text
            with self.assertRaises(ValueError):
                ArchitectureModelsHandoff.from_dict(value)
        class ExecutableDict(dict):
            def items(self):
                raise AssertionError("Must not execute")
        with self.assertRaises(ValueError):
            ArchitectureModelsHandoff.from_dict(ExecutableDict(self.handoff.canonical_dict()))

    def test_commands_inert_and_no_model_or_code_generation(self):
        before = self.source.canonical_json(), self.approved.canonical_json()
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), patch("builtins.eval", side_effect=AssertionError("eval")), patch("socket.create_connection", side_effect=AssertionError("network")), patch("builtins.open", side_effect=AssertionError("filesystem")):
            approved = approve_architecture(handoff=self.plan_handoff, architecture=self.spec, finalization=self.complete,
                approval_statement="Approved; $(echo inert); __import__('os').system('echo no'); C:/inert/path")
            result = self.transition(approved_architecture=approved)
            self.assertEqual(result, ArchitectureModelsHandoff.from_json(result.canonical_json()))
        self.assertEqual(before, (self.source.canonical_json(), self.approved.canonical_json()))
        for name in ("entities", "models", "tables", "schemas", "migrations", "relationships", "indexes", "api_contracts", "backend", "frontend", "generated_artifacts"):
            self.assertNotIn(name, result.canonical_dict())
            self.assertFalse(hasattr(result, name))


if __name__ == "__main__":
    unittest.main()
