"""31.3: isolated multi-module evidence and actual Gaming Studio state delta."""
import ast
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arcadev import ArcaCoreGenerationRequest, BuildStage, ProjectStatus
from arcadev.architecture_specification import _json
import arcadev.backend_generation as generation
from arcadev.backend_generation import GenerationDisposition as D, GenerationDiagnostic as G
from arcadev._generation_process import ProcessOutcome
from arcadev.arcacore_generation_request import module_definition
from arcadev.state_certification import state_certification_report
from tools.fixture_arcadev_module_backend import minimal_approved_backend
from tools.test_arcadev_arcacore_generation_request import gaming_request
from tools.test_arcadev_state_relations import relation_modules

BASELINE = {"blockers": 57, "unsupported": 6, "requires_certification": 51}


def protected_snapshot():
    root = Path(__file__).resolve().parents[1]
    result = {}
    for name in ("tools.zip", ".codex"):
        path = root / name
        if not path.exists():
            result[name] = "ABSENT"
        else:
            for item in ([path] if path.is_file() else path.rglob("*")):
                if item.is_file():
                    result[item.relative_to(root).as_posix()] = sha256(item.read_bytes()).hexdigest()
    return result


class StateGenerationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = ArcaCoreGenerationRequest.create(minimal_approved_backend(constraints=True, module_count=2, domains=True))
        cls.paths, cls.contents, cls.invocations = [], [], []
        original_validate, original_invoke = generation._validate_artifacts, generation.invoke_module
        def directory(*args, **kwargs):
            value = TemporaryDirectory(*args, **kwargs)
            cls.paths.append(value.name)
            return value
        def validate(workspace, request, bundle):
            cls.contents.append({p: (workspace / p).read_bytes() for p in generation._expected(request, workspace)})
            return original_validate(workspace, request, bundle)
        def invoke(module, workspace, runtime):
            cls.invocations.append((module.module_request_id, str(workspace)))
            return original_invoke(module, workspace, runtime)
        cls.protected_before = protected_snapshot()
        with patch.object(generation, "TemporaryDirectory", side_effect=directory), \
                patch.object(generation, "_validate_artifacts", side_effect=validate), \
                patch.object(generation, "invoke_module", side_effect=invoke):
            cls.one = generation.generate_backend(cls.request)
            cls.two = generation.generate_backend(cls.request)
        cls.protected_after = protected_snapshot()

    def test_two_fresh_runs_generate_complete_scope(self):
        self.assertEqual(len(set(self.paths)), 2)
        for run in (self.one, self.two):
            self.assertEqual(run.disposition, D.GENERATED, run.diagnostics)
            self.assertEqual(run.invocation_count, 2)
            self.assertEqual(len(run.artifact_manifest.artifacts), 11)

    def test_execution_uses_exact_derived_order(self):
        expected = self.request.dependency_plan.ordered_module_request_ids
        self.assertEqual(tuple(i for i, _ in self.invocations), expected + expected)
        self.assertEqual(self.invocations[0][1], self.invocations[1][1])
        self.assertNotEqual(self.invocations[0][1], self.invocations[2][1])

    def test_artifact_bytes_inventory_hashes_and_run_are_deterministic(self):
        self.assertEqual(len(self.contents), 2)
        self.assertEqual(self.contents[0], self.contents[1])
        self.assertEqual(self.one.canonical_json(), self.two.canonical_json())
        for artifact in self.one.artifact_manifest.artifacts:
            content = self.contents[0][artifact.path]
            self.assertEqual((artifact.content_digest, artifact.byte_size), (sha256(content).hexdigest(), len(content)))
            if artifact.path.endswith(".py"):
                compile(content, artifact.path, "exec")
        for path in self.paths:
            self.assertNotIn(path.replace("\\", "\\\\"), self.one.canonical_json())

    def test_registry_contains_exact_approved_modules_and_constraints(self):
        registry = json.loads(self.contents[0]["tools/registry/models.json"])
        self.assertEqual(set(registry), {module_definition(m).class_name for m in self.request.module_requests})
        for module in self.request.module_requests:
            definition = module_definition(module)
            self.assertEqual(registry[definition.class_name]["check_constraints"],
                [{"name": c.name, "expression": c.expression} for c in definition.check_constraints])
            self.assertEqual(registry[definition.class_name]["indexes"], [])

    def test_generated_models_preserve_domains_defaults_and_integer_checks(self):
        checks = []
        for module in self.request.module_requests:
            definition = module_definition(module)
            tree = ast.parse(self.contents[0]["backend/app/models/" + definition.module_name + ".py"])
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
            domains = [n for n in calls if n.func.id == "SQLEnum"]
            self.assertEqual(len(domains), 1)
            self.assertEqual(tuple(ast.literal_eval(a) for a in domains[0].args), ("draft", "published"))
            options = {k.arg: ast.literal_eval(k.value) for k in domains[0].keywords}
            self.assertEqual(options["name"], "state_choice")
            self.assertFalse(options["native_enum"])
            self.assertTrue(options["create_constraint"])
            state = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "state" for t in n.targets))
            defaults = {k.arg: k.value for k in state.value.keywords}
            self.assertEqual(ast.literal_eval(defaults["default"]), "draft")
            checks.extend(ast.literal_eval(n.args[0]) for n in calls if n.func.id == "CheckConstraint")
            schema = ast.parse(self.contents[0]["backend/app/schemas/" + definition.module_name + ".py"])
            literals = [n for n in ast.walk(schema) if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Attribute) and n.value.attr == "Literal"]
            self.assertTrue(literals)
            self.assertTrue(all(ast.literal_eval(n.slice) == ("draft", "published") for n in literals))
        self.assertEqual(sorted(checks), ['("quantity" <= 100)', '("quantity" >= 0)'])

    def test_sources_and_protected_paths_unchanged_and_workspaces_removed(self):
        for run in (self.one, self.two):
            self.assertTrue(run.source_tree_unchanged)
            self.assertTrue(run.workspace_cleaned)
        self.assertTrue(all(not Path(p).exists() for p in self.paths))
        self.assertEqual(self.protected_before, self.protected_after)

    def test_second_module_failure_cannot_report_partial_completion(self):
        invoked, paths = [], []
        original = generation.invoke_module
        def invoke(module, workspace, runtime):
            invoked.append(module.module_request_id)
            if len(invoked) == 1:
                return original(module, workspace, runtime)
            self.assertTrue(list((workspace / "backend/app/models").glob("*.py")))
            paths.append(workspace)
            return ProcessOutcome(True, "nonzero_exit")
        with patch.object(generation, "invoke_module", side_effect=invoke):
            run = generation.generate_backend(self.request)
        self.assertEqual(run.disposition, D.FAILED_GENERATION)
        self.assertEqual(run.diagnostics, (G.NONZERO_EXIT,))
        self.assertEqual(run.invocation_count, 2)
        self.assertIsNone(run.artifact_manifest)
        self.assertTrue(run.workspace_cleaned and run.source_tree_unchanged)
        self.assertTrue(all(not p.exists() for p in paths))
        forged = run.canonical_dict(); forged["disposition"] = "GENERATED"
        with self.assertRaises(ValueError): generation.BackendGenerationRun.from_dict(forged)

    def test_dependent_public_modules_use_same_transport_and_preserve_relationship(self):
        # Physical public-contract evidence, not fabricated logical approval.
        child, parent = relation_modules("one_to_many(Parent,children):cascade_delete:passive_deletes")
        calls, original = [], generation.invoke_module
        def invoke(module, workspace, runtime):
            calls.append(module.module_request_id)
            return original(module, workspace, runtime)
        with TemporaryDirectory(prefix="arcadev-dependent-public-") as directory:
            root = Path(directory); workspace, runtime = root / "workspace", root / "runtime"
            workspace.mkdir(); runtime.mkdir()
            generation._prepare(workspace, generation._trusted_bundle())
            with patch.object(generation, "invoke_module", side_effect=invoke):
                count, diagnostic = generation._invoke_dependency_plan((child, parent), workspace, runtime)
            self.assertEqual((count, diagnostic), (2, None))
            self.assertEqual(calls, [parent.module_request_id, child.module_request_id])
            source = (workspace / "backend/app/models/child.py").read_text()
            self.assertIn('ForeignKey("parents.id", ondelete="CASCADE")', source)
            self.assertIn('passive_deletes=True', source)
            backref = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "backref")
            self.assertEqual(ast.literal_eval(backref.args[0]), "children")
            self.assertEqual({k.arg: ast.literal_eval(k.value) for k in backref.keywords},
                {"cascade": "save-update, merge, delete", "passive_deletes": True})
            self.assertEqual(set(json.loads((workspace / "tools/registry/models.json").read_text())), {"Parent", "Child"})
            for path in (workspace / "backend").rglob("*.py"):
                compile(path.read_bytes(), str(path), "exec")
        self.assertFalse(root.exists())


class GamingStateCertificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = gaming_request()
        cls.report = state_certification_report(cls.request, previous_counts=BASELINE)

    def test_actual_frozen_entities_have_exact_blocking_reasons(self):
        model = self.request.approved_backend.package.original_backend.resolved_model
        self.assertEqual(len(model.entities), 5)
        backend = self.request.approved_backend.package.original_backend
        self.assertEqual(backend.model_id, "arcadev_domain_model_fa14437a45ef581d1da735a1f2c22d5a")
        self.assertEqual(backend.model_finalization_id, "arcadev_model_final_69a80476151dcf829cee5d282af6de9a")
        self.assertEqual([(e["entity_id"], e["name"]) for e in self.report["entities"]],
            [(e.entity_id, e.name) for e in sorted(model.entities, key=lambda e: e.entity_id)])
        self.assertTrue(all(e["disposition"] == "BLOCKED" and "approved fields" in e["reason"] for e in self.report["entities"]))
        self.assertTrue(all(not e.approved_fields and not e.identity_field_ids for e in model.entities))
        self.assertEqual((model.value_domains, model.relationships, model.constraints, model.access_requirements), ((), (), (), ()))

    def test_delta_uses_actual_counts_and_contains_every_capability(self):
        self.assertEqual(self.report["before"], BASELINE)
        self.assertEqual(self.report["after"], BASELINE)
        self.assertTrue(all(v == 0 for v in self.report["delta"].values()))
        groups = self.report["remaining_by_capability"]
        self.assertEqual(set(groups), {"LOGICAL_STATE", "STANDARD_MODULE", "AUTHORIZATION", "APPLICATION_OPERATION",
            "EXTERNAL_INTEGRATION", "PUBLISHING", "ISOLATED_WORKER", "APPLICATION_JOB", "STORAGE", "IMPLEMENTATION_CHOICE"})
        self.assertEqual(sum(g["count"] for g in groups.values()), 57)
        for key, group in groups.items():
            expected = [f.canonical_dict() for f in self.request.blocking_findings if f.capability.name == key]
            self.assertEqual(group["findings"], expected)

    def test_report_is_deterministic_read_only_and_canonical(self):
        before = self.request.approved_backend.canonical_json()
        with patch.object(generation, "TemporaryDirectory") as directory, patch.object(generation, "invoke_module") as invoke:
            again = state_certification_report(self.request.canonical_json(), previous_counts=BASELINE)
        self.assertEqual(_json(again), _json(self.report))
        self.assertEqual(before, self.request.approved_backend.canonical_json())
        directory.assert_not_called(); invoke.assert_not_called()

    def test_historical_context_cannot_change_current_counts_or_support(self):
        report = state_certification_report(self.request, previous_counts={"blockers": 1, "unsupported": 1, "requires_certification": 0})
        self.assertEqual(report["after"], BASELINE)
        self.assertFalse(report["all_state_generatable"] or report["eligible_for_backend_generation"])
        with self.assertRaises(ValueError): state_certification_report(self.request, previous_counts={**BASELINE, "blockers": True})
        with self.assertRaises(ValueError): state_certification_report(replace(self.request, eligible_for_generation=True), previous_counts=BASELINE)

    def test_unsupported_application_behaviors_remain_blocked_without_execution(self):
        groups = self.report["remaining_by_capability"]
        for key in ("EXTERNAL_INTEGRATION", "PUBLISHING", "ISOLATED_WORKER"):
            self.assertGreater(groups[key]["unsupported"], 0)
        for key in ("APPLICATION_JOB", "STORAGE", "APPLICATION_OPERATION", "IMPLEMENTATION_CHOICE"):
            self.assertGreater(groups[key]["count"], 0)
        with patch.object(generation, "TemporaryDirectory") as directory, patch.object(generation, "invoke_module") as invoke:
            run = generation.generate_backend(self.request)
        directory.assert_not_called(); invoke.assert_not_called()
        self.assertEqual(run.disposition, D.BLOCKED_INCOMPATIBLE)
        self.assertEqual(run.invocation_count, 0)
        self.assertIsNone(run.artifact_manifest)
        project = self.request.approved_backend.package.models_backend_handoff.resulting_project
        self.assertEqual((project.project_status, project.current_build_stage), (ProjectStatus.IN_PROGRESS, BuildStage.BACKEND))

    def test_generatable_state_does_not_bypass_backend_authority(self):
        request = ArcaCoreGenerationRequest.create(minimal_approved_backend("No authentication"))
        report = state_certification_report(request, previous_counts=BASELINE)
        self.assertTrue(report["all_state_generatable"])
        self.assertFalse(report["eligible_for_backend_generation"])
        self.assertEqual(report["module_request_count"], 1)
        self.assertNotEqual(report["after"], BASELINE)
        with patch.object(generation, "invoke_module") as invoke:
            run = generation.generate_backend(request)
        invoke.assert_not_called()
        self.assertEqual(run.disposition, D.BLOCKED_INCOMPATIBLE)


if __name__ == "__main__":
    unittest.main()
