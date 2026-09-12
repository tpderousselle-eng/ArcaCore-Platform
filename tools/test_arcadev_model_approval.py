"""ArcaDev 4.4 certification; all Gaming Studio choices are TEST FIXTURE ONLY."""
from dataclasses import replace
from functools import lru_cache
import unittest
from unittest.mock import patch

from arcadev import (
    ApprovalDecision, ApprovedDomainModel, ModelFinalization, ModelArea, ModelQuestion,
    ModelConsistencyEvaluation, ModelConsistencyFinding, ModelFindingSeverity,
    BuildStage, ProjectStatus, approve_domain_model, reject_domain_model,
    evaluate_model_consistency, validate_approved_domain_model,
    ModelField, ModelFact, LogicalType, DataClassification, model_element_id,
    ModelValueDomain, ModelRelationship, ModelAccessRequirement,
    ModelClaim, ResolvedModelChoice,
)
from arcadev.model_approval import _certified_sources, _evaluate
from tools.test_arcadev_model_clarification import resolved_model, answer_for, fixture_choice
from tools.test_arcadev_domain_model_specification import models_handoff
from tools.test_arcadev_domain_model_engine import altered, rename_entity


@lru_cache(maxsize=1)
def approved_model():
    state = resolved_model()
    return approve_domain_model(handoff=models_handoff(), model=state.original_model,
        finalization=state, approval_statement="TEST FIXTURE ONLY: I explicitly approve this Gaming Studio logical model.")


@lru_cache(maxsize=1)
def advisory_model_approval():
    handoff, state = models_handoff(), resolved_model()
    model = state.original_model
    q = ModelQuestion.create(handoff=handoff, question="TEST FIXTURE ONLY: advisory identity review?",
        blocking=False, area=ModelArea.IDENTITY, source_requirements=model.entities[0].responsibility.source_requirements,
        entity_ids=(model.entities[0].entity_id,))
    model = altered(model, handoff, open_model_questions=model.open_model_questions + (q,))
    state = ModelFinalization.start(model, handoff=handoff)
    for question in model.open_model_questions:
        if question.blocking:
            state = state.resolve(answer_for(state, question, fixture_choice(question, model)), handoff=handoff)
    return approve_domain_model(handoff=handoff, model=model, finalization=state,
        approval_statement="TEST FIXTURE ONLY: approve with an advisory question.")


class ModelApprovalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = models_handoff()
        cls.complete = resolved_model()
        cls.model = cls.complete.original_model
        cls.initial = ModelFinalization.start(cls.model, handoff=cls.handoff)
        cls.approved = approved_model()

    def approve(self, **changes):
        args = dict(handoff=self.handoff, model=self.model, finalization=self.complete, approval_statement="Approved.")
        args.update(changes)
        return approve_domain_model(**args)

    def test_gaming_studio_readiness_and_explicit_approval(self):
        self.assertFalse(self.model.readiness.ready_for_finalization)
        self.assertFalse(self.initial.effective_ready_for_approval)
        self.assertTrue(self.complete.effective_ready_for_approval)
        result = self.approved
        self.assertTrue(result.approved)
        self.assertTrue(result.approval_eligible)
        self.assertTrue(result.effective_ready_for_approval)
        self.assertEqual(result.decision, ApprovalDecision.APPROVED)
        self.assertTrue(result.package.consistency.consistent)
        self.assertFalse(result.package.consistency.blocking_findings)
        self.assertEqual(result.package.model_finalization, self.complete)
        self.assertEqual(result.package.original_model, self.model)
        self.assertEqual(result.package.architecture_handoff, self.handoff)
        self.assertEqual(result.package.architecture_handoff.frozen_approved_architecture, self.handoff.frozen_approved_architecture)

    def test_resolved_authority_has_every_structured_claim_and_owner(self):
        view = self.approved.package.resolved_model
        self.assertEqual(view.model_id, self.model.model_id)
        self.assertEqual(view.model_finalization_id, self.complete.finalization_id)
        actual = {(c.decision_id, c.question_id, c.claim) for e in view.entities for c in e.choices}
        expected = {(d.decision_id, d.question_id, c) for d in self.complete.decisions for c in d.claims}
        self.assertEqual(actual, expected)
        self.assertEqual({c.claim.slot for e in view.entities for c in e.choices}, {a.value for a in ModelArea})
        for entity in view.entities:
            original = next(e for e in self.model.entities if e.entity_id == entity.entity_id)
            self.assertEqual(entity.owned_capabilities, original.owned_capabilities)
            self.assertEqual(entity.architecture_source_requirements, original.responsibility.source_requirements)
            self.assertTrue(any(c.claim.slot == "identity" and c.claim.values == ("uuid",) for c in entity.choices))

    def test_proposed_field_type_is_not_silently_approved(self):
        entity = self.model.entities[0]
        q = next(q for q in self.model.open_model_questions if q.area is ModelArea.IDENTITY and entity.entity_id in q.entity_ids)
        fact = ModelFact.create(handoff=self.handoff, source_requirements=q.source_requirements,
            question_id=q.question_id, value="TEST FIXTURE ONLY: candidate proposes string identity")
        fid = model_element_id("field", name="id", source_requirements=fact.source_requirements, scope=(entity.entity_id,))
        field = ModelField(fid, "id", LogicalType.STRING, True, False, False, True, DataClassification.INTERNAL, fact)
        entity = replace(entity, fields=(field,), identity_field_ids=(fid,), identity_question_id=None)
        model = altered(self.model, self.handoff, entities=tuple(entity if e.entity_id == entity.entity_id else e for e in self.model.entities))
        state = ModelFinalization.start(model, handoff=self.handoff)
        for question in model.open_model_questions:
            state = state.resolve(answer_for(state, question, fixture_choice(question, model)), handoff=self.handoff)
        approved = self.approve(model=model, finalization=state)
        resolved = next(e for e in approved.package.resolved_model.entities if e.entity_id == entity.entity_id)
        self.assertFalse(resolved.approved_fields)
        self.assertFalse(resolved.identity_field_ids)
        self.assertTrue(any(c.claim.slot == "identity" and c.claim.values == ("uuid",) for c in resolved.choices))
        self.assertEqual(approved.package.original_model, model)

    def test_explicit_decision_and_nonempty_statement_required(self):
        with self.assertRaises(TypeError):
            ApprovedDomainModel.create(handoff=self.handoff, model=self.model, finalization=self.complete, approval_statement="Ready.")
        for statement in ("", " ", None, 1):
            with self.subTest(statement=statement), self.assertRaises(ValueError):
                self.approve(approval_statement=statement)
        with self.assertRaises(ValueError):
            ApprovedDomainModel.create(handoff=self.handoff, model=self.model, finalization=self.complete, decision="ready", approval_statement="Ready.")

    def test_rejection_preserves_ready_unready_and_conflicted_states(self):
        q = self.initial.unresolved_questions[0]
        conflict = self.initial.resolve(answer_for(self.initial, q, ("unsupported",)), handoff=self.handoff)
        for state in (self.initial, self.complete, conflict):
            result = reject_domain_model(handoff=self.handoff, model=self.model, finalization=state, approval_statement="I reject this package.")
            self.assertFalse(result.approved)
            self.assertEqual(result.decision, ApprovalDecision.REJECTED)
            self.assertEqual(result.package.model_finalization, state)
            self.assertEqual(ApprovedDomainModel.from_json(result.canonical_json()), result)

    def test_deterministic_identity_and_roundtrip(self):
        first = self.approve()
        self.assertEqual(first.canonical_json(), self.approve().canonical_json())
        self.assertEqual(first, ApprovedDomainModel.from_json(first.canonical_json()))
        self.assertEqual(first, ApprovedDomainModel.from_dict(dict(reversed(list(first.canonical_dict().items())))))
        self.assertNotEqual(first.approval_id, self.approve(approval_statement="Another explicit approval.").approval_id)

    def test_deep_immutability(self):
        for obj, key, value in ((self.approved, "approved", False), (self.complete.decisions[0], "accepted_values", ()),
            (self.approved.package.resolved_model.entities[0], "choices", ())):
            with self.assertRaises(AttributeError):
                setattr(obj, key, value)
        raw = self.approved.canonical_dict()
        raw["package"]["original_model"]["entities"].clear()
        self.assertEqual(self.approved.package.original_model, self.model)

    def test_blocking_readiness_and_identity_findings(self):
        evaluation = evaluate_model_consistency(self.handoff, self.model, self.initial)
        codes = {f.code for f in evaluation.blocking_findings}
        self.assertIn("unresolved_model_blockers", codes)
        self.assertIn("model_not_effectively_ready", codes)
        self.assertIn("missing_resolved_identity", codes)
        with self.assertRaisesRegex(ValueError, "cannot be approved"):
            self.approve(finalization=self.initial)

    def test_active_conflict_and_unsupported_scope_block_approval(self):
        q = self.initial.unresolved_questions[0]
        for value in ("unsupported", "Remove GitHub", "billing", "no build state"):
            state = self.initial.resolve(answer_for(self.initial, q, (value,)), handoff=self.handoff)
            self.assertTrue(state.conflicts)
            self.assertIn("active_model_conflicts", {f.code for f in evaluate_model_consistency(self.handoff, self.model, state).blocking_findings})
            with self.assertRaises(ValueError):
                self.approve(finalization=state)

    def test_advisory_question_can_be_approved(self):
        result = advisory_model_approval()
        self.assertTrue(result.approved)
        self.assertEqual(len(result.package.model_finalization.unresolved_questions), 1)
        self.assertIn("unresolved_advisory_questions", {f.code for f in result.package.consistency.warnings})

    def test_implementation_compatibility_is_warning(self):
        evaluation = self.approved.package.consistency
        self.assertTrue(evaluation.consistent)
        self.assertEqual(evaluation.warnings[0].code, "implementation_compatibility_not_proven")
        self.assertEqual(evaluation.warnings[0].severity, ModelFindingSeverity.WARNING)
        self.assertEqual(ModelConsistencyEvaluation.from_dict(evaluation.canonical_dict()), evaluation)

    def test_consistency_finding_validation(self):
        finding = ModelConsistencyFinding.create("contradiction", "Known contradiction.", "blocking", ("decisions",))
        self.assertFalse(ModelConsistencyEvaluation.create((finding,)).consistent)
        for findings in ((finding, finding), (object(),)):
            with self.assertRaises(ValueError):
                ModelConsistencyEvaluation.create(findings)
        raw = ModelConsistencyEvaluation.create((finding,)).canonical_dict()
        raw["consistent"] = True
        with self.assertRaises(ValueError):
            ModelConsistencyEvaluation.from_dict(raw)

    def test_combined_view_detects_frozen_lifecycle_and_uniqueness_conflicts(self):
        # Unit-test the final combination check after the independently tested
        # source replay boundary. These are structured values, not parsed prose.
        view = self.approved.package.resolved_model
        entity = view.entities[0]
        fact = self.model.entities[0].responsibility
        field = ModelField("fixed_field", "fixed", LogicalType.STRING, True, False, False, True, DataClassification.INTERNAL, fact)
        domain = ModelValueDomain("fixed_domain", "fixed", ("open", "closed"), fact)
        choices = (
            ResolvedModelChoice("uniqueness_decision", "uniqueness_question", ModelClaim("uniqueness", entity.entity_id, None, ("identity_only",))),
            ResolvedModelChoice("lifecycle_decision", "lifecycle_question", ModelClaim("lifecycle", entity.entity_id, None, ("pending", "done"))),
        )
        entity = replace(entity, approved_fields=(field,), lifecycle_domain_ids=(domain.domain_id,), choices=choices)
        with patch("arcadev.model_approval._resolved_model", return_value=replace(view, entities=(entity,), value_domains=(domain,))):
            codes = {f.code for f in _evaluate(self.complete).blocking_findings}
        self.assertIn("frozen_uniqueness_conflict", codes)
        self.assertIn("frozen_lifecycle_conflict", codes)

    def test_combined_view_detects_frozen_relationship_contradiction(self):
        view = self.approved.package.resolved_model
        source, target = view.entities[:2]
        relationship = ModelRelationship("fixed_relationship", "fixed", source.entity_id, target.entity_id,
            "one", "many", False, self.model.entities[0].responsibility, "source_owns_target", "retain")
        choice = ResolvedModelChoice("relationship_decision", "relationship_question",
            ModelClaim("relationship", source.entity_id, None, ("independent",)))
        source = replace(source, choices=source.choices + (choice,))
        with patch("arcadev.model_approval._resolved_model", return_value=replace(view, entities=(source, target), relationships=(relationship,))):
            self.assertIn("frozen_relationship_conflict", {f.code for f in _evaluate(self.complete).blocking_findings})
        # Reversing an edge preserves semantics only if cardinalities and owner
        # direction reverse together. Contradictions cannot hide in orientation.
        for values, conflict in ((("many", "one", "target_owns_source", "retain"), False),
                                  (("one", "one", "source_owns_target", "detach"), True)):
            reverse = ResolvedModelChoice("reverse_decision", "reverse_question",
                ModelClaim("relationship", target.entity_id, source.entity_id, values))
            target = replace(target, choices=(reverse,))
            with patch("arcadev.model_approval._resolved_model", return_value=replace(view, entities=(target,), relationships=(relationship,))):
                codes = {f.code for f in _evaluate(self.complete).blocking_findings}
            self.assertEqual("frozen_relationship_conflict" in codes, conflict)
        forward = ResolvedModelChoice("forward_decision", "forward_question",
            ModelClaim("relationship", source.entity_id, target.entity_id, ("one", "many", "source_owns_target", "retain")))
        source = replace(source, choices=(forward,))
        with patch("arcadev.model_approval._resolved_model", return_value=replace(view, entities=(source, target), relationships=())):
            self.assertIn("accepted_relationship_conflict", {f.code for f in _evaluate(self.complete).blocking_findings})

    def test_combined_view_requires_closed_frozen_references(self):
        view = self.approved.package.resolved_model
        entity = view.entities[0]
        fact = self.model.entities[0].responsibility
        field = ModelField("fixed_field", "fixed", LogicalType.ENUM, True, False, False, False,
            DataClassification.INTERNAL, fact, value_domain_id="proposed_domain")
        access = ModelAccessRequirement("fixed_access", "fixed", entity.entity_id, ("proposed_field",), False, fact)
        entity = replace(entity, approved_fields=(field,))
        with patch("arcadev.model_approval._resolved_model", return_value=replace(view, entities=(entity,), access_requirements=(access,))):
            codes = {f.code for f in _evaluate(self.complete).blocking_findings}
        self.assertIn("unresolved_frozen_value_domain", codes)
        self.assertIn("unresolved_frozen_field_reference", codes)

    def test_every_upstream_identity_is_bound(self):
        for field in ("source_project_id", "architecture_handoff_id", "plan_handoff_id", "approved_architecture_id",
            "architecture_id", "architecture_finalization_id", "model_id", "model_finalization_id", "approval_id"):
            raw = self.approved.canonical_dict()
            raw[field] = "forged"
            with self.subTest(field=field), self.assertRaises(ValueError):
                ApprovedDomainModel.from_dict(raw)

    def test_current_references_compare_complete_content(self):
        source = self.handoff.resulting_project
        self.assertEqual(validate_approved_domain_model(self.approved, source_project=source, handoff=self.handoff,
            model=self.model, finalization=self.complete), self.approved)
        for current in (dict(model=replace(self.model, entities=())), dict(finalization=replace(self.complete, history=())),
            dict(handoff=replace(self.handoff, resulting_project=replace(source, project_name=source.project_name + " stale")))):
            with self.assertRaises(ValueError):
                validate_approved_domain_model(self.approved, **current)

    def test_valid_alternative_model_is_stale(self):
        alternate = rename_entity(self.model, self.handoff, self.model.entities[0], "Alternate state")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.approve(model=alternate)
        with self.assertRaises(ValueError):
            validate_approved_domain_model(self.approved, model=alternate)

    def test_wrong_project_status_and_stage(self):
        source = self.handoff.resulting_project
        for project in (replace(source, current_build_stage=BuildStage.BACKEND), replace(source, project_status=ProjectStatus.BLOCKED),
            replace(source, project_id="forged"), replace(source, metadata=replace(source.metadata, schema_version=True)),
            replace(source, metadata=replace(source.metadata, updated_at="2026-09-11T00:00:00Z"))):
            with self.assertRaises(ValueError):
                self.approve(source_project=project)

    def test_forged_eligibility_boolean_readiness_decision_and_consistency(self):
        for field, invalid in (("approval_eligible", False), ("approved", False), ("decision", "rejected"),
            ("effective_ready_for_approval", False), ("approved", 1)):
            raw = self.approved.canonical_dict()
            raw[field] = invalid
            with self.subTest(field=field), self.assertRaises(ValueError):
                ApprovedDomainModel.from_dict(raw)
        for key, value in (("warnings", []), ("consistent", False), ("blocking_findings", [{}])):
            raw = self.approved.canonical_dict()
            raw["package"]["consistency"][key] = value
            with self.assertRaises(ValueError):
                ApprovedDomainModel.from_dict(raw)

    def test_forged_finalization_decisions_history_and_resolved_view(self):
        for mutate in (
            lambda p: p["model_finalization"].update(effective_ready_for_approval=False),
            lambda p: p["model_finalization"].update(finalization_id="forged"),
            lambda p: p["model_finalization"]["history"].reverse(),
            lambda p: p["model_finalization"]["history"].pop(),
            lambda p: p["model_finalization"]["decisions"][0].update(provenance="inferred"),
            lambda p: p["model_finalization"]["decisions"][0]["claims"][0].update(values=["forged"]),
            lambda p: p["resolved_model"]["entities"][0].update(choices=[]),
            lambda p: p["resolved_model"].update(extra="unknown"),
            lambda p: p["architecture_handoff"]["frozen_approved_architecture"].update(approval_statement="Changed."),
        ):
            raw = self.approved.canonical_dict()
            mutate(raw["package"])
            with self.assertRaises(ValueError):
                ApprovedDomainModel.from_dict(raw)

    def test_capability_and_logical_type_forgery(self):
        for mutate in (
            lambda m: m["entities"][0].update(owned_capabilities=[]),
            lambda m: m["entities"][0].update(owned_capabilities=["billing"]),
            lambda m: m["entities"][0].update(identity_question_id=None),
            lambda m: m.update(project_stage="backend"),
        ):
            raw = self.approved.canonical_dict()
            mutate(raw["package"]["original_model"])
            with self.assertRaises(ValueError):
                ApprovedDomainModel.from_dict(raw)

    def test_json_schema_size_and_executable_safety(self):
        for raw in ("{", '{"schema":1,"schema":2}', " " * 5_000_001, "[" * 1000, "null", "[]", object()):
            with self.assertRaises(ValueError):
                ApprovedDomainModel.from_json(raw)
        for field, value in (("provider", "vendor"), ("schema", "wrong"), ("schema_version", 2), ("schema_version", True),
            ("package", object()), ("approval_statement", lambda: "execute")):
            raw = self.approved.canonical_dict()
            raw[field] = value
            with self.assertRaises(ValueError):
                ApprovedDomainModel.from_dict(raw)
        class ExecutableDict(dict):
            def items(self):
                raise AssertionError("Must not execute")
        with self.assertRaises(ValueError):
            ApprovedDomainModel.from_dict(ExecutableDict(self.approved.canonical_dict()))

    def test_statement_credentials_tokens_keys_and_bounds(self):
        for value in ("password=x", "access_token=abc", "ghp_abcdefghijklmnop", "sk-abcdefghijklmnopqrst", "Bearer opaque",
            "-----BEGIN RSA PRIVATE KEY-----", "\ud800", "bad\x01", "line\nbreak", "x" * 20_001, object()):
            with self.subTest(value=repr(value)[:60]), self.assertRaises(ValueError):
                self.approve(approval_statement=value)

    def test_hostile_text_inert_and_no_generation_or_transition(self):
        before = self.handoff.canonical_json(), self.model.canonical_json(), self.complete.canonical_json()
        _certified_sources.cache_clear()
        # Import the existing generator solely to install its invocation guard
        # before guarding eval/open used by normal third-party module imports.
        with patch("tools.generate.generate_module", side_effect=AssertionError("ArcaCore invocation")), \
             patch("subprocess.Popen", side_effect=AssertionError("execution")), patch("builtins.eval", side_effect=AssertionError("eval")), \
             patch("socket.create_connection", side_effect=AssertionError("network")), patch("builtins.open", side_effect=AssertionError("filesystem")):
            approved = self.approve(approval_statement="Approved; DROP TABLE records; $(echo hostile); __import__('os').system('echo no'); C:/inert/path")
            self.assertEqual(ApprovedDomainModel.from_json(approved.canonical_json()), approved)
        self.assertEqual(before, (self.handoff.canonical_json(), self.model.canonical_json(), self.complete.canonical_json()))
        self.assertEqual(self.handoff.resulting_project.current_build_stage, BuildStage.MODELS)
        self.assertEqual(self.handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        for name in ("sql", "orm", "migrations", "apis", "backend", "frontend", "resulting_project"):
            self.assertFalse(hasattr(approved, name))


if __name__ == "__main__":
    unittest.main()
