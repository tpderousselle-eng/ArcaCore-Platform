"""3.1 certification: explicit Gaming Studio representation, not generation."""
import copy
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from arcadev import create_plan_architecture_handoff, BuildStage, ProjectStatus
from arcadev.architecture_specification import (
    ArchitectureSpecification, ArchitectureFact, ArchitectureProvenance,
    ArchitectureComponent, ArchitectureConnection, ArchitectureAspect,
    ArchitectureQuestion, ArchitectureArea, architecture_question_id,
    approved_architecture_sources, plan_source_id, validate_architecture_specification,
)
from tools import test_arcadev_plan_architecture_handoff as upstream


def approved_handoff():
    source, approved = upstream.ArcaDevPlanArchitectureHandoffTest().approved()
    return create_plan_architecture_handoff(source_project=source, approved_plan=approved)


def fixture(handoff):
    """Test-only construction of a logical architecture through public records."""
    plan = handoff.frozen_approved_plan.package.plan_finalization.original_plan
    catalog = approved_architecture_sources(handoff)
    def fact(sources, rule=None):
        return ArchitectureFact.create(handoff=handoff, source_requirements=sources, derivation=rule)
    capabilities = tuple(plan_source_id(item) for item in plan.in_scope_capabilities)
    objective = fact([plan_source_id(plan.product_objective)])
    constraints = {plan_source_id(item) for item in (*plan.planning_constraints, *plan.integrations)}
    constraints.update(d.decision_id for d in handoff.frozen_approved_plan.package.plan_finalization.decisions)
    component = ArchitectureComponent("application", "Gaming Studio application", "application", fact(capabilities, "responsibility"), capabilities, ("storage",), ("persistence",), "application")
    storage = ArchitectureComponent("storage", "Logical persistent storage", "storage", fact(capabilities, "storage"), (), (), ("persistence",), "application")
    connection = ArchitectureConnection("persistence", "application", "storage", fact(capabilities, "interaction"))
    aspects = [ArchitectureAspect(area, ArchitectureArea(area), fact(capabilities, rule), ("application",)) for area, rule in (
        ("security", "security"), ("risk", "risk"), ("observability", "observability"), ("resilience", "resilience"), ("storage", "storage"))]
    intake = handoff.frozen_approved_plan.package.idea_handoff.snapshot.intake
    for values, area in ((intake.authentication_requirements, "authentication"), (intake.integration_requirements, "integration"), (intake.deployment_requirements, "deployment")):
        for n, item in enumerate(values):
            source = next(key for key, (value, _) in catalog.items() if value == item.value)
            aspects.append(ArchitectureAspect(area + str(n), ArchitectureArea(area), fact([source], "boundary"), ("application",)))
    questions = [ArchitectureQuestion.create("Which persistence implementation supports the approved capabilities?", True, capabilities, "storage", handoff=handoff)]
    return ArchitectureSpecification.create(handoff=handoff, objective=objective, system_boundary=fact(capabilities, "boundary"),
        style=fact(capabilities, "style"), external_entities=tuple(fact([plan_source_id(item)]) for item in (*plan.user_roles, *plan.integrations)),
        approved_constraints=tuple(fact([source]) for source in constraints), components=(component, storage), interfaces=(connection,),
        data_flows=(replace(connection, connection_id="persistent_data"),), aspects=tuple(aspects), open_architecture_questions=questions)


class ArcaDevArchitectureSpecificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = approved_handoff()
        cls.spec = fixture(cls.handoff)

    def load(self, value):
        return ArchitectureSpecification.from_dict(value, handoff=self.handoff)

    def altered(self, **changes):
        names = ("objective", "system_boundary", "style", "external_entities", "approved_constraints", "components", "interfaces", "data_flows", "aspects", "open_architecture_questions")
        args = {name: getattr(self.spec, name) for name in names}
        args.update(changes)
        return ArchitectureSpecification.create(handoff=self.handoff, **args)

    def test_gaming_studio_representation_and_bindings(self):
        self.assertEqual(self.spec.handoff_id, self.handoff.handoff_id)
        for field in ("idea_handoff_id", "software_plan_id", "plan_finalization_id", "approved_plan_id"):
            self.assertEqual(getattr(self.spec, field), getattr(self.handoff, field))
        text = self.spec.canonical_json()
        for value in ("Desktop web", "Mobile web", "Email/password", "Google OAuth", "GitHub", "ArcaCentum managed cloud", "deletion controls", "isolated build", "user-controlled", "user-authorized"):
            self.assertIn(value, text)
        for value in ("React", "PostgreSQL", "Kubernetes", "AWS"):
            self.assertNotIn(value, text)

    def test_identity_ordering_roundtrip_immutability(self):
        self.assertEqual(self.spec, fixture(self.handoff))
        self.assertEqual(self.spec, ArchitectureSpecification.from_json(self.spec.canonical_json(), handoff=self.handoff))
        self.assertEqual(self.spec, self.altered(components=tuple(reversed(self.spec.components)), aspects=tuple(reversed(self.spec.aspects))))
        raw = self.spec.canonical_dict()
        raw["components"].reverse()
        self.assertEqual(self.load(raw), self.spec)
        with self.assertRaises(AttributeError):
            self.spec.project_id = "forged"

    def test_capability_ownership_and_duplicates(self):
        for change in ((), ("nonexistent",)):
            components = tuple(replace(c, owned_capabilities=change) if c.component_id == "application" else c for c in self.spec.components)
            with self.assertRaises(ValueError):
                self.altered(components=components)
        with self.assertRaises(ValueError):
            self.altered(components=self.spec.components + (self.spec.components[0],))
        components = tuple(replace(c, owned_capabilities=self.spec.components[0].owned_capabilities) if c.component_id == "storage" else c for c in self.spec.components)
        with self.assertRaises(ValueError):
            self.altered(components=components)

    def test_component_dependency_and_interface_references(self):
        for field, value in (("dependencies", ("missing",)), ("dependencies", ("application",)), ("exposed_interfaces", ("missing",))):
            components = tuple(replace(c, **{field: value}) if c.component_id == "application" else c for c in self.spec.components)
            with self.assertRaises(ValueError):
                self.altered(components=components)

    def test_interface_and_flow_validation(self):
        for name in ("interfaces", "data_flows"):
            original = getattr(self.spec, name)
            for field, value in (("source", "missing"), ("destination", "missing"), ("destination", original[0].source), ("direction", "reverse"), ("trust_boundary_crossing", 1)):
                with self.assertRaises(ValueError):
                    self.altered(**{name: (replace(original[0], **{field: value}),)})
            with self.assertRaises(ValueError):
                self.altered(**{name: original + original})

    def test_approved_constraints_and_boundaries_preserved(self):
        for fact in self.spec.approved_constraints:
            with self.subTest(value=fact.value), self.assertRaises(ValueError):
                self.altered(approved_constraints=tuple(v for v in self.spec.approved_constraints if v != fact))
        for area in ("authentication", "integration", "deployment"):
            with self.subTest(area=area), self.assertRaises(ValueError):
                self.altered(aspects=tuple(v for v in self.spec.aspects if v.area.value != area))

    def test_provenance_grounding_and_technology(self):
        raw = self.spec.canonical_dict()
        for field, value in (("value", "Invented billing"), ("provenance", "model"), ("source_requirements", ["missing"]), ("derivation", "invented")):
            candidate = copy.deepcopy(raw)
            candidate["objective"][field] = value
            with self.assertRaises(ValueError):
                self.load(candidate)
        with self.assertRaises(ValueError):
            self.altered(aspects=(replace(self.spec.aspects[0], technology=self.spec.objective),) + self.spec.aspects[1:])

    def test_readiness_recomputed_and_structural_blockers(self):
        self.assertFalse(self.spec.readiness.ready_for_finalization)
        self.assertTrue(self.altered(open_architecture_questions=()).readiness.ready_for_finalization)
        missing_security = self.altered(open_architecture_questions=(), aspects=tuple(v for v in self.spec.aspects if v.area is not ArchitectureArea.SECURITY))
        self.assertFalse(missing_security.readiness.ready_for_finalization)
        self.assertIn("security", missing_security.readiness.blocking_reasons)

    def test_forged_identity_binding_stage_readiness(self):
        for key in ("architecture_id", "handoff_id", "project_id", "idea_handoff_id", "software_plan_id", "plan_finalization_id", "approved_plan_id", "project_stage"):
            value = self.spec.canonical_dict()
            value[key] = "forged"
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load(value)
        for readiness in ({"ready_for_finalization": True, "blocking_reasons": []}, None, {"ready_for_finalization": 0, "blocking_reasons": ["blocking_architecture_questions"]}):
            value = self.spec.canonical_dict()
            value["readiness"] = readiness
            with self.assertRaises(ValueError):
                self.load(value)

    def test_untrusted_shape_schema_unicode_secret_and_size(self):
        for key, item in (("provider", "model"), ("schema", "wrong"), ("schema_version", True), ("schema_version", 2), ("components", {})):
            value = self.spec.canonical_dict()
            value[key] = item
            with self.assertRaises(ValueError):
                self.load(value)
        for text in ("password=abcd1234", "-----BEGIN PRIVATE KEY-----", "bad\x00value", "bad\tvalue", "bad\ud800value", "x" * 100_001):
            value = self.spec.canonical_dict()
            value["components"][0]["name"] = text
            with self.assertRaises(ValueError):
                self.load(value)
        for text in ('{"schema":1,"schema":2}', "{", " " * 5_000_001, "[" * 1000):
            with self.assertRaises(ValueError):
                ArchitectureSpecification.from_json(text, handoff=self.handoff)
        value = self.spec.canonical_dict()
        value["components"][0]["name"] = object()
        with self.assertRaises(ValueError):
            self.load(value)

    def test_question_identity_and_sources(self):
        q = self.spec.open_architecture_questions[0]
        self.assertEqual(architecture_question_id(q), architecture_question_id(ArchitectureQuestion.create(q.question, q.blocking, tuple(reversed(q.source_requirements)), q.area, handoff=self.handoff)))
        for changed in (replace(q, area=ArchitectureArea.FRONTEND), replace(q, blocking=False)):
            self.assertNotEqual(architecture_question_id(q), architecture_question_id(changed))
        with self.assertRaises(ValueError):
            self.altered(open_architecture_questions=(replace(q, source_requirements=("missing",)),))

    def test_malformed_nested_records_fail_closed(self):
        for section, field, invalid in (("components", "name", None), ("interfaces", "source", []),
                ("aspects", "constraints", {}), ("components", "dependencies", "storage")):
            value = self.spec.canonical_dict()
            value[section][0][field] = invalid
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.load(value)
        for field, invalid in (("value", None), ("provenance", None), ("derivation", [])):
            value = self.spec.canonical_dict()
            value["objective"][field] = invalid
            with self.assertRaises(ValueError):
                self.load(value)

    def test_hostile_text_inert_no_generation_or_stage_transition(self):
        before = self.handoff.canonical_json()
        with patch("subprocess.Popen", side_effect=AssertionError("execution forbidden")), patch("builtins.eval", side_effect=AssertionError("eval forbidden")), patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            components = (replace(self.spec.components[0], name="__import__('os').system('echo hostile'); $(cmd /c whoami)"),) + self.spec.components[1:]
            spec = self.altered(components=components)
            self.assertEqual(spec, validate_architecture_specification(spec.canonical_json(), handoff=self.handoff))
        self.assertEqual(before, self.handoff.canonical_json())
        self.assertEqual(spec.project_stage, BuildStage.ARCHITECTURE)
        self.assertEqual(self.handoff.resulting_project.project_status, ProjectStatus.IN_PROGRESS)
        for name in ("models", "backend", "frontend", "approved"):
            self.assertFalse(hasattr(spec, name))


if __name__ == "__main__":
    unittest.main()
