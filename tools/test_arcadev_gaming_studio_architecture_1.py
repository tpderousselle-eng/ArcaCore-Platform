"""Production generation preserves exact certified PLAN authority and questions."""

from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from arcadev import gaming_studio_architecture as production
from arcadev.architecture_engine import generate_baseline_architecture
from arcadev.architecture_specification import (
    ArchitectureSpecification, approved_architecture_sources, architecture_question_id,
)
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, parse_authority


class ProductionArchitectureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handoff = production.production_architecture_inputs()
        cls.architecture = generate_baseline_architecture(cls.handoff)

    def test_public_generation_exact_persisted_canonical_roundtrip(self):
        with patch.object(production, "generate_baseline_architecture", wraps=generate_baseline_architecture) as generate:
            actual = production.validate_production_architecture_specification()
        generate.assert_called_once()
        self.assertEqual(actual, self.architecture)
        self.assertEqual(ArchitectureSpecification.from_json(actual.canonical_json(), handoff=self.handoff), actual)

    def test_exact_five_production_bindings_and_current_project(self):
        a = self.architecture
        expected = {
            "project_id": "arcadev_969321c8959864fe18393b9d2b551063",
            "handoff_id": production.CERTIFIED_HANDOFF_ID,
            "approved_plan_id": "arcadev_approved_plan_f32c4002a7e6c5aea8e3b328d242ffd5",
            "software_plan_id": "arcadev_plan_9aed1a01dad6e95cb75b6db67730dd5b",
            "plan_finalization_id": "arcadev_plan_final_d9698e456e67fae47ef46dbd11880dd2",
        }
        for key, value in expected.items():
            self.assertEqual(getattr(a, key), value)
        self.assertEqual(self.handoff.resulting_project.current_build_stage.value, "ARCHITECTURE")
        self.assertEqual(self.handoff.resulting_project.project_status.value, "IN_PROGRESS")

    def test_every_material_fact_and_question_is_source_grounded(self):
        catalog = approved_architecture_sources(self.handoff)
        seen = []
        def visit(value):
            if isinstance(value, dict):
                if "source_requirements" in value:
                    self.assertTrue(value["source_requirements"])
                    self.assertLessEqual(set(value["source_requirements"]), set(catalog))
                    seen.append(value)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(self.architecture.canonical_dict())
        self.assertGreater(len(seen), 20)

    def test_policy_boundaries_and_isolated_worker_preserved(self):
        a = self.architecture
        self.assertLessEqual({"storage", "authentication", "integration", "background", "deployment",
                             "security", "resilience", "observability", "risk"}, {x.area.value for x in a.aspects})
        self.assertTrue(any(c.category == "worker" and c.trust_classification == "isolated" for c in a.components))
        constraints = a.canonical_json()
        for phrase in ("user-controlled", "Network denied by default", "recoverable for 30 days"):
            self.assertIn(phrase.casefold(), constraints.casefold())
        for decision in self.handoff.frozen_approved_plan.package.plan_finalization.decisions:
            self.assertTrue(any(f.source_requirements == (decision.decision_id,)
                                and all(v in f.value for v in decision.accepted_values)
                                for f in a.approved_constraints))
        self.assertTrue(a.interfaces)
        self.assertEqual(len(a.interfaces), len(a.data_flows))

    def test_question_identity_and_readiness_deterministic_without_choices(self):
        again = generate_baseline_architecture(self.handoff)
        self.assertEqual(again.canonical_json(), self.architecture.canonical_json())
        questions = again.open_architecture_questions
        self.assertTrue(questions)
        self.assertEqual(len(questions), len({architecture_question_id(q) for q in questions}))
        self.assertTrue(all(q.blocking for q in questions))
        self.assertFalse(again.readiness.ready_for_finalization)
        self.assertEqual(again.readiness.blocking_reasons, ("blocking_architecture_questions",))
        self.assertTrue(all(x.technology is None for x in again.aspects))

    def test_forged_and_invented_plan_sources_rejected_publicly(self):
        for key in ("handoff_id", "project_id", "approved_plan_id", "software_plan_id", "plan_finalization_id"):
            value = self.architecture.canonical_dict()
            value[key] = "invented"
            with self.subTest(key=key), self.assertRaises(ValueError):
                ArchitectureSpecification.from_dict(value, handoff=self.handoff)
        value = self.architecture.canonical_dict()
        value["objective"]["source_requirements"] = ["invented_plan_source"]
        with self.assertRaises(ValueError):
            ArchitectureSpecification.from_dict(value, handoff=self.handoff)

    def test_exact_handoff_guard_rejects_other_identity_and_stage(self):
        project = self.handoff.resulting_project
        from arcadev.project import BuildStage
        for handoff in (replace(self.handoff, handoff_id="another_handoff"),
                        replace(self.handoff, resulting_project=replace(project, current_build_stage=BuildStage.MODELS))):
            with patch.object(production, "validate_plan_approval_checkpoint"), \
                 patch.object(production.PlanArchitectureHandoff, "from_json", return_value=handoff), \
                 self.assertRaisesRegex(ValueError, "exact certified"):
                production.production_architecture_inputs()

    def test_changed_persisted_specification_and_upstream_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "authority"
            shutil.copytree(AUTHORITY_DIRECTORY, root)
            for relative in ("production_architecture/architecture_specification.json",
                             "production_plan/plan_approval/plan_architecture_handoff.json"):
                path = root / relative
                before = path.read_bytes()
                value = json.loads(before)
                value["forged"] = True
                path.write_bytes(canonical_bytes(value))
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    production.validate_production_architecture_specification(root)
                path.write_bytes(before)

    def test_no_later_authority(self):
        area = AUTHORITY_DIRECTORY / production.ARCHITECTURE_AREA
        paths = tuple(area.rglob("*"))
        # The frozen historical package never gains approval. Explicit later
        # approval/handoff authority belongs only to its versioned child area.
        names = {p.name for p in paths if "architecture_approval" not in p.relative_to(area).parts}
        self.assertFalse(names & {"approved_architecture.json", "architecture_models_handoff.json", "domain_model.json"})
        for path in paths:
            if path.name in {"approved_architecture.json", "architecture_models_handoff.json"}:
                self.assertEqual(path.parent, area / "architecture_approval")
        self.assertFalse({p.name for p in paths} & {
            "domain_model.json", "domain_model_specification.json", "approved_domain_model.json",
            "models_backend_handoff.json", "backend.json", "frontend.json",
        })
        self.assertEqual(self.architecture.project_stage.value, "ARCHITECTURE")


if __name__ == "__main__":
    unittest.main()
