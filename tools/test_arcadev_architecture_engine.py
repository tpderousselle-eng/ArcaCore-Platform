"""ArcaDev 3.2 deterministic generation and adversarial candidate certification."""
from dataclasses import fields, replace
from types import MappingProxyType
import unittest
from unittest.mock import patch

from arcadev import (
    ArchitectureCandidateAdapter, ArchitectureSpecification, ArchitectureFact, ArchitectureArea,
    BuildStage, ProjectStatus, generate_baseline_architecture, validate_architecture_candidate,
    validate_architecture_adapter_candidate, plan_source_id,
)
from tools.test_arcadev_architecture_specification import approved_handoff
from tools import test_arcadev_idea_plan_handoff as idea_helpers
from tools import test_arcadev_plan_approval as plan_helpers


class ArcaDevArchitectureEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = approved_handoff()
        cls.spec = generate_baseline_architecture(cls.handoff)

    def altered(self, **changes):
        names = ("objective", "system_boundary", "style", "external_entities", "approved_constraints", "components", "interfaces", "data_flows", "aspects", "open_architecture_questions")
        args = {name: getattr(self.spec, name) for name in names}
        args.update(changes)
        return ArchitectureSpecification.create(handoff=self.handoff, **args)

    def validate(self, candidate):
        return validate_architecture_candidate(self.handoff, candidate)

    def test_deterministic_gaming_studio_generation(self):
        other = generate_baseline_architecture(self.handoff)
        self.assertEqual(other.architecture_id, self.spec.architecture_id)
        self.assertEqual(other.canonical_json(), self.spec.canonical_json())
        self.assertEqual(self.validate(other.canonical_json()), self.spec)

    def test_complete_capability_ownership(self):
        plan = self.handoff.frozen_approved_plan.package.plan_finalization.original_plan
        owned = [source for c in self.spec.components for source in c.owned_capabilities]
        self.assertCountEqual(owned, [plan_source_id(item) for item in plan.in_scope_capabilities])
        self.assertEqual(len(owned), len(set(owned)))

    def test_approved_intent_and_fixture_decisions_preserved(self):
        text = self.spec.canonical_json()
        for value in ("Desktop web", "Mobile web", "Email/password", "Google OAuth", "GitHub", "ArcaCentum managed cloud", "deletion controls", "isolated build", "user-controlled", "user-authorized"):
            self.assertIn(value, text)
        for area in (ArchitectureArea.AUTHENTICATION, ArchitectureArea.INTEGRATION, ArchitectureArea.DEPLOYMENT):
            self.assertTrue(any(a.area is area for a in self.spec.aspects))

    def test_workers_storage_publishing_and_flow_boundaries(self):
        worker = next(c for c in self.spec.components if c.category == "worker")
        self.assertEqual(worker.trust_classification, "isolated")
        self.assertTrue(any(e.destination == worker.component_id for e in self.spec.interfaces))
        self.assertTrue(any(c.category == "storage" for c in self.spec.components))
        self.assertTrue(any("publish" in c.name.casefold() for c in self.spec.components))
        self.assertTrue(self.spec.data_flows)
        self.assertTrue(all(e.protocol is None and e.interaction is None for e in self.spec.interfaces))

    def test_unresolved_implementation_questions_do_not_reopen_plan(self):
        self.assertEqual(len(self.spec.open_architecture_questions), 8)
        self.assertFalse(self.spec.readiness.ready_for_finalization)
        self.assertEqual(self.spec.readiness.blocking_reasons, ("blocking_architecture_questions",))
        text = " ".join(q.question for q in self.spec.open_architecture_questions)
        for token in ("frontend", "persistence", "asset storage", "worker isolation", "background job", "synchronization", "publishing", "deployment-unit"):
            self.assertIn(token, text)
        for q in self.handoff.frozen_approved_plan.package.plan_finalization.original_plan.open_planning_questions:
            self.assertNotIn(q.question, text)
        for token in ("React", "PostgreSQL", "Docker", "Kubernetes", "AWS", "Redis", "Kafka"):
            self.assertNotIn(token, self.spec.canonical_json())

    def test_explicit_test_fixture_technology_preferences_are_not_reasked(self):
        from arcadev import (IdeaIntake, IdeaFinalization, ProjectMetadata, create_idea_plan_handoff,
                             generate_baseline_plan, approve_plan, create_plan_architecture_handoff)
        original, _ = idea_helpers.finalized()
        intake = original.current_intake
        args = {f.name: getattr(intake, f.name) for f in fields(intake) if f.name not in {"readiness", "schema", "schema_version"}}
        args["original_user_request"] += "; React; PostgreSQL"
        args["technology_preferences"] = tuple(idea_helpers._intent(value, args["original_user_request"]) for value in ("React", "PostgreSQL"))
        idea = IdeaFinalization.start(IdeaIntake.create(**args))
        project = idea.to_project(metadata=ProjectMetadata.create(created_at="2026-09-10T08:00:00Z"))
        idea_handoff = create_idea_plan_handoff(project, idea)
        plan = generate_baseline_plan(idea_handoff)
        finalized = plan_helpers.ArcaDevPlanApprovalTest().resolve(idea_handoff, plan)
        approved = approve_plan(handoff=idea_handoff, finalization=finalized, approval_statement="Approve explicit test-fixture technologies.")
        handoff = create_plan_architecture_handoff(source_project=idea_handoff.resulting_project, approved_plan=approved)
        generated = generate_baseline_architecture(handoff)
        self.assertEqual({a.technology.value for a in generated.aspects if a.technology}, {"React", "PostgreSQL"})
        self.assertFalse(any(q.area is ArchitectureArea.FRONTEND or "primary persistence" in q.question for q in generated.open_architecture_questions))
        self.assertEqual(validate_architecture_candidate(handoff, generated), generated)

    def test_provider_neutral_adapter_and_inert_mapping(self):
        spec = self.spec
        class Adapter:
            def create_candidate(self, handoff):
                return spec.canonical_json()
        self.assertIsInstance(Adapter(), ArchitectureCandidateAdapter)
        self.assertEqual(validate_architecture_adapter_candidate(self.handoff, Adapter()), spec)
        self.assertEqual(self.validate(MappingProxyType(spec.canonical_dict())), spec)
        with self.assertRaises(ValueError):
            validate_architecture_adapter_candidate(self.handoff, object())
        class ExecutableMapping(dict):
            def __iter__(self):
                raise AssertionError("Untrusted objects must not execute")
        with self.assertRaises(ValueError):
            self.validate(ExecutableMapping(spec.canonical_dict()))

    def test_alternate_grounded_component_names(self):
        components = tuple(replace(c, name="Logical boundary " + str(i)) for i, c in enumerate(self.spec.components))
        alternate = self.altered(components=components)
        self.assertNotEqual(alternate.architecture_id, self.spec.architecture_id)
        self.assertEqual(self.validate(alternate), alternate)

    def test_valid_alternate_grouping_of_service_capabilities(self):
        services = [c for c in self.spec.components if c.category == "service"][:2]
        self.assertEqual(len(services), 2)
        target, removed = services
        owned = target.owned_capabilities + removed.owned_capabilities
        responsibility = ArchitectureFact.create(handoff=self.handoff, source_requirements=owned, derivation="responsibility")
        # Merge two service responsibilities; preserve graph edges and aspect owners.
        def endpoint(value):
            return target.component_id if value == removed.component_id else value
        interfaces = tuple(replace(e, source=endpoint(e.source), destination=endpoint(e.destination)) for e in self.spec.interfaces)
        flows = tuple(replace(e, source=endpoint(e.source), destination=endpoint(e.destination)) for e in self.spec.data_flows)
        components = []
        for c in self.spec.components:
            if c == removed:
                continue
            if c == target:
                c = replace(c, name="Combined approved services", owned_capabilities=owned, responsibility=responsibility)
            deps = {endpoint(e.destination) for e in interfaces if e.source == c.component_id and endpoint(e.destination) in {x.component_id for x in self.spec.components}}
            exposed = tuple(e.connection_id for e in interfaces if c.component_id in (e.source, e.destination))
            components.append(replace(c, dependencies=tuple(deps), exposed_interfaces=exposed))
        aspects = tuple(replace(a, component_ids=tuple(sorted({endpoint(v) for v in a.component_ids}))) for a in self.spec.aspects)
        alternate = self.altered(components=tuple(components), interfaces=interfaces, data_flows=flows, aspects=aspects)
        self.assertEqual(self.validate(alternate), alternate)

    def test_invented_and_removed_capabilities(self):
        for owned in (("billing",), ()):
            value = self.spec.canonical_dict()
            owner = next(c for c in value["components"] if c["owned_capabilities"])
            owner["owned_capabilities"] = list(owned)
            with self.assertRaises(ValueError):
                self.validate(value)

    def test_changed_approved_decisions_rejected(self):
        for expected in ("Desktop web", "Email/password", "GitHub", "ArcaCentum managed cloud"):
            value = self.spec.canonical_dict()
            fact = next(f for f in value["approved_constraints"] if f["value"] == expected)
            fact["value"] = "Changed approved decision"
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                self.validate(value)

    def test_required_questions_and_isolation_cannot_be_removed(self):
        without = self.altered(open_architecture_questions=())
        self.assertTrue(without.readiness.ready_for_finalization)
        with self.assertRaisesRegex(ValueError, "unresolved"):
            self.validate(without)
        weak = self.altered(components=tuple(replace(c, trust_classification="application") if c.category == "worker" else c for c in self.spec.components))
        with self.assertRaisesRegex(ValueError, "isolation"):
            self.validate(weak)
        with self.assertRaises(ValueError):
            self.validate(self.altered(aspects=tuple(a for a in self.spec.aspects if a.area is not ArchitectureArea.STORAGE)))
        with self.assertRaisesRegex(ValueError, "data flow"):
            self.validate(self.altered(data_flows=()))

    def test_wrong_handoff_forged_identity_and_readiness(self):
        for key, value in (("handoff_id", "forged"), ("architecture_id", "forged"), ("readiness", {"ready_for_finalization": True, "blocking_reasons": []})):
            candidate = self.spec.canonical_dict()
            candidate[key] = value
            with self.assertRaises(ValueError):
                self.validate(candidate)
        with self.assertRaises(ValueError):
            generate_baseline_architecture(replace(self.handoff, handoff_id="forged"))

    def test_broken_graph_references(self):
        for key, field, invalid in (("components", "dependencies", ["missing"]), ("interfaces", "source", "missing"), ("data_flows", "destination", "missing")):
            value = self.spec.canonical_dict()
            value[key][0][field] = invalid
            with self.assertRaises(ValueError):
                self.validate(value)

    def test_untrusted_security_matrix(self):
        for key, value in (("provider", "model"), ("schema", "wrong"), ("schema_version", 2), ("components", [object()])):
            candidate = self.spec.canonical_dict()
            candidate[key] = value
            with self.assertRaises(ValueError):
                self.validate(candidate)
        for text in ("api_key=abcdef", "-----BEGIN PRIVATE KEY-----", "\ud800", "bad\x01", "x" * 100_001):
            candidate = self.spec.canonical_dict()
            candidate["components"][0]["name"] = text
            with self.assertRaises(ValueError):
                self.validate(candidate)
        for candidate in ("{", '{"schema":1,"schema":2}', " " * 5_000_001, object()):
            with self.assertRaises(ValueError):
                self.validate(candidate)

    def test_hostile_commands_inert_and_upstream_stage_preserved(self):
        before = self.handoff.canonical_json()
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), patch("builtins.eval", side_effect=AssertionError("eval")), patch("socket.create_connection", side_effect=AssertionError("network")):
            value = self.altered(components=(replace(self.spec.components[0], name="$(echo hostile); __import__('os').system('echo no')"),) + self.spec.components[1:])
            self.assertEqual(self.validate(value), value)
        self.assertEqual(self.handoff.canonical_json(), before)
        self.assertEqual(self.spec.project_stage, BuildStage.ARCHITECTURE)
        self.assertEqual(self.handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        for name in ("models", "backend", "frontend", "approved"):
            self.assertFalse(hasattr(self.spec, name))


if __name__ == "__main__":
    unittest.main()
