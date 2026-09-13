"""5.6 isolated public generation, hostile evidence and immutable run contracts."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import arcadev.backend_generation as generation
import arcadev._generation_process as transport
from arcadev.backend_generation import (
    BackendGenerationRun, BackendArtifactManifest, GenerationDisposition as D,
    GenerationDiagnostic as G, generate_backend, validate_backend_generation_run,
    validate_backend_artifact_manifest,
)
from arcadev import BuildStage, ProjectStatus
from arcadev import ArcaCoreGenerationRequest, ArcaCoreCapabilityStatus
from arcadev.backend_specification import backend_architecture
from tools.fixture_arcadev_module_backend import minimal_approved_backend
from tools.test_arcadev_arcacore_generation_request import eligible_request, gaming_request
from tools.test_arcadev_backend_approval import source_snapshot


class BackendGenerationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eligible, cls.gaming = eligible_request(), gaming_request()
        cls.paths, cls.commands, cls.contents = [], [], {}
        cls.bundle = generation._trusted_bundle()
        original_popen, original_validate = subprocess.Popen, generation._validate_artifacts

        def tracked_directory(*args, **kwargs):
            directory = TemporaryDirectory(*args, **kwargs)
            cls.paths.append(directory.name)
            return directory

        def tracked_popen(command, **kwargs):
            cls.commands.append((command, kwargs))
            return original_popen(command, **kwargs)

        def tracked_validate(workspace, request, bundle):
            for relative in generation._expected(request, workspace):
                cls.contents[relative] = (workspace / relative).read_bytes()
            return original_validate(workspace, request, bundle)

        cls.before = source_snapshot()
        with patch.object(generation, "TemporaryDirectory", side_effect=tracked_directory), \
                patch.object(transport.subprocess, "Popen", side_effect=tracked_popen), \
                patch.object(generation, "_validate_artifacts", side_effect=tracked_validate):
            cls.one = generate_backend(cls.eligible)
            cls.two = generate_backend(cls.eligible)
        cls.after = source_snapshot()

    def artifact_workspace(self):
        directory = TemporaryDirectory(prefix="arcadev-evidence-test-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        generation._prepare(root, self.bundle)
        for relative, content in self.contents.items():
            target = root / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
        return root

    def test_eligible_fixture_generates_complete_validated_evidence(self):
        self.assertEqual(self.one.disposition, D.GENERATED, self.one.diagnostics)
        self.assertEqual(self.one.invocation_count, len(self.eligible.module_requests))
        self.assertEqual(len(self.one.artifact_manifest.artifacts), 6)
        self.assertFalse(self.one.diagnostics)

    def test_actual_public_entrypoint_and_containment(self):
        self.assertEqual(len(self.commands), 2)
        for argv, options in self.commands:
            self.assertEqual(argv, [sys.executable, "-B", "-m", "tools.generate", "record_state",
                "external_principal_id:str", "id:str:pk", "title:str"])
            self.assertIs(options["shell"], False)
            self.assertFalse(Path(options["cwd"]).resolve().is_relative_to(generation._SOURCE_ROOT))
            self.assertEqual(options["env"]["PYTHONPATH"], str(options["cwd"]))
            self.assertNotIn("PATH", options["env"])
            if os.name == "nt":
                self.assertTrue(options["creationflags"] & 4)  # Suspended before Job assignment.
                self.assertTrue(options["creationflags"] & subprocess.CREATE_NO_WINDOW)
            else:
                self.assertTrue(options["start_new_session"])

    def test_environment_does_not_inherit_credentials_or_python_hooks(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "do-not-forward", "PYTHONSTARTUP": "untrusted.py", "PATH": "untrusted"}):
            result = transport.safe_environment(Path("workspace"), Path("runtime"))
        for key in ("GITHUB_TOKEN", "PYTHONSTARTUP", "PATH"):
            self.assertNotIn(key, result)
        self.assertEqual(result["PYTHONDONTWRITEBYTECODE"], "1")

    def test_two_fresh_runs_have_identical_canonical_artifacts_and_run_identity(self):
        self.assertEqual(len(set(self.paths)), 2)
        self.assertIsNotNone(self.one.artifact_manifest, self.one.diagnostics)
        self.assertEqual(self.one.artifact_manifest.canonical_json(), self.two.artifact_manifest.canonical_json())
        self.assertEqual(self.one.canonical_json(), self.two.canonical_json())
        for path in self.paths:
            self.assertNotIn(path.replace("\\", "\\\\"), self.one.canonical_json())

    def test_source_repository_unchanged_and_workspaces_cleaned(self):
        self.assertEqual(self.before, self.after)
        self.assertTrue(self.one.source_tree_unchanged)
        self.assertTrue(self.two.source_tree_unchanged)
        self.assertTrue(self.one.workspace_cleaned)
        self.assertTrue(all(not Path(p).exists() for p in self.paths))

    def test_only_trusted_implementation_and_resources_are_copied(self):
        self.assertIn("tools/generate.py", self.bundle)
        self.assertNotIn("tools/registry/models.json", self.bundle)
        self.assertTrue(all(p.startswith("tools/") and Path(p).suffix in {".py", ".j2"} for p in self.bundle))
        self.assertFalse(any(p.startswith(("backend/", "frontend/", "shared/", ".git/", ".codex/")) or ".env" in p for p in self.bundle))

    def test_expected_surfaces_compile_and_registry_matches(self):
        self.assertEqual(set(self.contents), set(generation._expected(self.eligible, generation._SOURCE_ROOT)))
        for relative, content in self.contents.items():
            if relative.endswith(".py"): compile(content, relative, "exec")
        registry = json.loads(self.contents["tools/registry/models.json"])
        self.assertEqual(set(registry), {"Record_state"})
        self.assertEqual(registry["Record_state"]["table"], "record_states")
        self.assertEqual([f["name"] for f in registry["Record_state"]["fields"]], ["external_principal_id", "id", "title"])

    def test_public_generation_manifest_uses_observed_digests(self):
        manifest = self.one.artifact_manifest
        self.assertIsNotNone(manifest, self.one.diagnostics)
        for artifact, owned in zip(manifest.artifacts, manifest.generation_manifest.files):
            self.assertEqual(artifact.content_digest, sha256(self.contents[artifact.path]).hexdigest())
            self.assertEqual(artifact.byte_size, len(self.contents[artifact.path]))
            self.assertEqual(owned.content_digest, artifact.content_digest)
            self.assertEqual(owned.generator, "tools.generate.generate_module")
        self.assertEqual(manifest.pending_authority, ("accepted_schema_revision", "application_manifest", "runtime_validation"))

    def test_gaming_blocked_before_workspace_or_subprocess(self):
        before = self.gaming.approved_backend.canonical_json()
        with patch.object(generation, "TemporaryDirectory") as workspace, patch.object(generation, "invoke_module") as invoke, \
                patch.object(transport.subprocess, "Popen") as popen:
            result = generate_backend(self.gaming)
            again = generate_backend(self.gaming)
        for mock in (workspace, invoke, popen): mock.assert_not_called()
        self.assertEqual(result.disposition, D.BLOCKED_INCOMPATIBLE)
        self.assertEqual(result.invocation_count, 0)
        self.assertIsNone(result.artifact_manifest)
        self.assertEqual(result.blocking_findings, self.gaming.blocking_findings)
        self.assertEqual(result.canonical_json(), again.canonical_json())
        self.assertEqual(before, result.request.approved_backend.canonical_json())
        project = result.request.approved_backend.package.models_backend_handoff.resulting_project
        self.assertEqual((project.project_status, project.current_build_stage), (ProjectStatus.IN_PROGRESS, BuildStage.BACKEND))

    def test_forged_eligibility_never_executes(self):
        with patch.object(generation, "TemporaryDirectory") as directory:
            with self.assertRaises(ValueError): generate_backend(replace(self.gaming, eligible_for_generation=True))
        directory.assert_not_called()

    def test_approved_plan_decision_is_not_silently_dropped_at_execution_boundary(self):
        approved = minimal_approved_backend(planning_decision=True)
        request = ArcaCoreGenerationRequest.create(approved)
        decisions = backend_architecture(approved.package.models_backend_handoff).plan_handoff.frozen_approved_plan.package.plan_finalization.decisions
        self.assertEqual(len(decisions), 1)
        mapping = next(m for m in request.capability_mappings if m.responsibility_id == decisions[0].decision_id)
        self.assertEqual(mapping.status, ArcaCoreCapabilityStatus.REQUIRES_CERTIFICATION)
        self.assertTrue(approved.approved)
        self.assertFalse(request.eligible_for_generation)
        with patch.object(generation, "TemporaryDirectory") as directory, patch.object(generation, "invoke_module") as invoke:
            result = generate_backend(request)
        directory.assert_not_called(); invoke.assert_not_called()
        self.assertEqual(result.disposition, D.BLOCKED_INCOMPATIBLE)
        self.assertEqual(result.blocking_findings, request.blocking_findings)

    def test_run_and_manifest_canonical_roundtrips_and_immutability(self):
        self.assertEqual(self.one, BackendGenerationRun.from_json(self.one.canonical_json()))
        self.assertEqual(self.one, validate_backend_generation_run(self.one.canonical_dict()))
        manifest = self.one.artifact_manifest
        self.assertIsNotNone(manifest, self.one.diagnostics)
        self.assertEqual(manifest, BackendArtifactManifest.from_json(manifest.canonical_json()))
        self.assertEqual(manifest, validate_backend_artifact_manifest(manifest.canonical_dict(), request=self.eligible))
        with self.assertRaises(FrozenInstanceError): self.one.invocation_count = 0
        with self.assertRaises(FrozenInstanceError): manifest.artifacts = ()

    def test_run_rejects_stale_authority_and_forged_completion(self):
        with self.assertRaises(ValueError): validate_backend_generation_run(self.one, request=self.gaming)
        for mutation in ({"invocation_count": 0}, {"workspace_cleaned": False}, {"source_after_digest": "0" * 64}, {"artifact_manifest": None}):
            value = self.one.canonical_dict(); value.update(mutation)
            with self.assertRaises(ValueError): BackendGenerationRun.from_dict(value)

    def test_strict_loaders_reject_unknown_keys_versions_duplicates_and_size(self):
        self.assertIsNotNone(self.one.artifact_manifest, self.one.diagnostics)
        for record, loader in ((self.one, BackendGenerationRun), (self.one.artifact_manifest, BackendArtifactManifest)):
            for mutation in ({"unknown": True}, {"schema_version": 2}, {"schema_version": True}):
                value = record.canonical_dict(); value.update(mutation)
                with self.assertRaises(ValueError): loader.from_dict(value)
            with self.assertRaises(ValueError): loader.from_json('{"schema":1,"schema":2}')
            with self.assertRaises(ValueError): loader.from_json(" " * 5_000_001)

    def test_manifest_rejects_tampered_paths_digests_provenance_and_duplicates(self):
        manifest = self.one.artifact_manifest
        self.assertIsNotNone(manifest, self.one.diagnostics)
        for path in ("../escape.py", "/absolute.py", "C:/escape.py", "backend\\app\\models\\record_state.py", "backend/app/../escape.py", ".env", "frontend/app.py", "tools/run.exe"):
            value = manifest.canonical_dict(); value["artifacts"][0]["path"] = path
            with self.assertRaises(ValueError): BackendArtifactManifest.from_dict(value)
        value = manifest.canonical_dict(); value["artifacts"].append(value["artifacts"][0])
        with self.assertRaises(ValueError): BackendArtifactManifest.from_dict(value)
        value = manifest.canonical_dict(); value["artifacts"][0]["content_digest"] = "z" * 64
        with self.assertRaises(ValueError): BackendArtifactManifest.from_dict(value)
        with self.assertRaises(ValueError): validate_backend_artifact_manifest(manifest, request=self.gaming)

    def test_artifact_validation_rejects_extra_surfaces_env_and_executables(self):
        for relative in (".env", "credentials.json", "tools/run.exe", "frontend/app.py", "backend/app/jobs/custom.py"):
            root = self.artifact_workspace()
            path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("x=1")
            with self.assertRaises(ValueError): generation._validate_artifacts(root, self.eligible, self.bundle)
            path.unlink()

    def test_artifact_validation_rejects_secret_values(self):
        root = self.artifact_workspace()
        target = root / "backend/app/models/record_state.py"
        original = target.read_bytes()
        for secret in ("password='unapproved-value'", "token='ghp_12345678901234567890'", "key='-----BEGIN PRIVATE KEY-----'"):
            target.write_bytes(original + ("\n" + secret + "\n").encode())
            with self.assertRaises(ValueError): generation._validate_artifacts(root, self.eligible, self.bundle)

    def test_symlink_and_reparse_escape_rejected_without_following(self):
        root = self.artifact_workspace()
        original = Path.is_symlink
        with patch.object(Path, "is_symlink", lambda p: p == root / "backend" or original(p)):
            with self.assertRaisesRegex(ValueError, "Symbolic"):
                generation._validate_artifacts(root, self.eligible, self.bundle)
        original_stat = Path.lstat
        def reparse(path):
            result = original_stat(path)
            if path == root / "backend":
                class Reparse:
                    st_file_attributes = 0x400
                    st_mode = result.st_mode
                return Reparse()
            return result
        with patch.object(Path, "lstat", reparse):
            with self.assertRaisesRegex(ValueError, "Reparse"):
                generation._checked_path(root, "backend/app/models/record_state.py")

    def test_missing_broken_python_registry_and_modified_generator_rejected(self):
        root = self.artifact_workspace()
        for relative, replacement in (("backend/app/models/record_state.py", b"invalid syntax !"),
                ("tools/registry/models.json", b"{}"), ("tools/generate.py", b"# changed")):
            target = root / relative; old = target.read_bytes(); target.write_bytes(replacement)
            with self.assertRaises((ValueError, SyntaxError)):
                generation._validate_artifacts(root, self.eligible, self.bundle)
            target.write_bytes(old)
        (root / "backend/app/api/record_state.py").unlink()
        with self.assertRaises(ValueError): generation._validate_artifacts(root, self.eligible, self.bundle)

    def test_deleted_trusted_input_and_incomplete_manifest_cannot_pass(self):
        root = self.artifact_workspace()
        (root / "tools/generate.py").unlink()
        with self.assertRaises(ValueError): generation._validate_artifacts(root, self.eligible, self.bundle)
        manifest = self.one.artifact_manifest
        partial = BackendArtifactManifest._build(manifest.request_id, manifest.request_digest, manifest.provenance, manifest.artifacts[:-1])
        with self.assertRaises(ValueError): validate_backend_artifact_manifest(partial, request=self.eligible)

    def test_malformed_collection_and_provenance_types_rejected(self):
        value = self.one.canonical_dict(); value["diagnostics"] = None
        with self.assertRaises(ValueError): BackendGenerationRun.from_dict(value)
        for replacement in (None, True, "not-an-array"):
            value = self.one.artifact_manifest.canonical_dict(); value["artifacts"] = replacement
            with self.assertRaises(ValueError): BackendArtifactManifest.from_dict(value)
        value = self.one.artifact_manifest.canonical_dict(); value["provenance"]["interpreter_version"] = None
        with self.assertRaises(ValueError): BackendArtifactManifest.from_dict(value)

    def test_generator_failures_are_structured_and_cleanup(self):
        paths = []
        def directory(*args, **kwargs):
            result = TemporaryDirectory(*args, **kwargs); paths.append(result.name); return result
        for diagnostic in ("nonzero_exit", "timeout", "output_limit", "process_setup"):
            with patch.object(generation, "invoke_module", return_value=transport.ProcessOutcome(True, diagnostic)), \
                    patch.object(generation, "TemporaryDirectory", side_effect=directory):
                result = generate_backend(self.eligible)
            self.assertEqual(result.disposition, D.FAILED_GENERATION)
            self.assertEqual(result.diagnostics, (G(diagnostic),))
            self.assertIsNone(result.artifact_manifest)
            self.assertTrue(result.workspace_cleaned)
        self.assertTrue(all(not Path(p).exists() for p in paths))

    def test_validation_failure_and_source_change_cannot_report_success(self):
        with patch.object(generation, "invoke_module", return_value=transport.ProcessOutcome(True)), \
                patch.object(generation, "_validate_artifacts", side_effect=ValueError("untrusted diagnostic")):
            result = generate_backend(self.eligible)
        self.assertEqual(result.disposition, D.FAILED_VALIDATION)
        self.assertEqual(result.diagnostics, (G.ARTIFACT_VALIDATION,))
        self.assertNotIn("untrusted diagnostic", result.canonical_json())
        with patch.object(generation, "_source_snapshot", side_effect=["a" * 64, "b" * 64]), \
                patch.object(generation, "invoke_module", return_value=transport.ProcessOutcome(False, "process_setup")):
            result = generate_backend(self.eligible)
        self.assertEqual(result.disposition, D.FAILED_VALIDATION)
        self.assertEqual(result.diagnostics, (G.SOURCE_CHANGED,))

    def test_repository_temporary_base_rejected_before_workspace_creation(self):
        with patch.object(generation, "gettempdir", return_value=str(generation._SOURCE_ROOT)), \
                patch.object(generation, "TemporaryDirectory") as directory:
            result = generate_backend(self.eligible)
        directory.assert_not_called()
        self.assertEqual(result.disposition, D.FAILED_GENERATION)
        self.assertEqual(result.invocation_count, 0)

    def test_real_timeout_and_bounded_stdout_stderr(self):
        with TemporaryDirectory(prefix="arcadev-process-test-") as directory:
            root = Path(directory)
            with patch.object(transport, "PROCESS_TIMEOUT", 0.1):
                result = transport._run_process([sys.executable, "-B", "-c", "import time; time.sleep(30)"], root, root)
            self.assertEqual(result.diagnostic, "timeout")
            for stream in ("stdout", "stderr"):
                result = transport._run_process([sys.executable, "-B", "-c",
                    "import sys; sys." + stream + ".write('s'*300000)"], root, root)
                self.assertEqual(result.diagnostic, "output_limit")
                self.assertLess(len(repr(result)), 100)

    def test_failed_process_setup_is_bounded(self):
        with patch.object(transport.subprocess, "Popen", side_effect=OSError("password=do-not-record")):
            result = transport._run_process([], Path("workspace"), Path("runtime"))
        self.assertEqual(result, transport.ProcessOutcome(False, "process_setup"))
        self.assertNotIn("do-not-record", repr(result))

    def test_actual_nonzero_exit_is_generation_failure_transport(self):
        with TemporaryDirectory(prefix="arcadev-exit-test-") as directory:
            root = Path(directory)
            result = transport._run_process([sys.executable, "-B", "-c", "raise SystemExit(7)"], root, root)
        self.assertEqual(result, transport.ProcessOutcome(True, "nonzero_exit"))

    def test_process_descendants_are_terminated_after_parent_exit(self):
        with TemporaryDirectory(prefix="arcadev-descendant-test-") as directory:
            root = Path(directory)
            code = ("import pathlib, subprocess, sys; "
                "child = subprocess.Popen([sys.executable, '-B', '-c', 'import time; time.sleep(30)']); "
                "pathlib.Path('descendant.pid').write_text(str(child.pid))")
            result = transport._run_process([sys.executable, "-B", "-c", code], root, root)
            self.assertEqual(result, transport.ProcessOutcome(True))
            pid = int((root / "descendant.pid").read_text())
            if os.name == "nt":
                import ctypes as c
                from ctypes import wintypes as w
                kernel = c.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
                kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]; kernel.WaitForSingleObject.restype = w.DWORD
                kernel.CloseHandle.argtypes = [w.HANDLE]
                handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                if handle:
                    try: self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0)
                    finally: kernel.CloseHandle(handle)
            else:
                deadline = time.monotonic() + 5
                while True:
                    try: os.kill(pid, 0)
                    except ProcessLookupError: break
                    status = Path('/proc') / str(pid) / 'stat'
                    if status.exists() and status.read_text().split()[2] == 'Z': break
                    if time.monotonic() >= deadline: self.fail('Generator descendant survived process-group cleanup.')
                    time.sleep(0.025)


if __name__ == "__main__":
    unittest.main()
