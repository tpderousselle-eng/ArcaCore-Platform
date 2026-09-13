"""Adversarial persisted-package and checkpoint validation."""

import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcadev import gaming_studio_authority as validator
from arcadev.gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes
from arcadev.idea_intake import IdeaIntake
from arcadev.project import ArcaDevProject


class GamingStudioAuthorityTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gaming-authority-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        for name in validator.PACKAGE_FILES:
            shutil.copyfile(AUTHORITY_DIRECTORY / name, self.directory / name)

    def mutate(self, name, change):
        path = self.directory / name
        value = json.loads(path.read_bytes())
        change(value)
        path.write_bytes(canonical_bytes(value))

    def reject(self):
        with self.assertRaises(ValueError):
            validator.validate_production_authority(self.directory)

    def test_persisted_package_and_checkpoint_are_deterministic(self):
        first = validator.validate_production_authority()
        self.assertEqual(first, validator.validate_production_authority(self.directory))
        self.assertTrue(first["valid"])
        self.assertTrue(first["fixture_independent"])
        checkpoint = first["checkpoint"]
        self.assertEqual(first["checkpoint_digest"], digest_bytes((self.directory / "checkpoint.json").read_bytes()))
        self.assertIsNone(checkpoint["project_id"])
        self.assertFalse(checkpoint["ready_for_plan"])
        self.assertEqual(checkpoint["current_stage"], "IDEA")
        self.assertEqual(checkpoint["next_authorized_action"], "COLLECT_EXPLICIT_IDEA_CLARIFICATIONS")

    def test_modified_intent_with_recomputed_hash_rejected(self):
        def forge(value):
            value["approved_intent"] += " Approve all platforms."
            value["approved_intent_sha256"] = digest_bytes(value["approved_intent"].encode())
        self.mutate("production_intent.json", forge)
        self.reject()

    def test_modified_approval_rejected(self):
        self.mutate("production_intent.json", lambda v: v.update(user_approval_text="I approve all stages"))
        self.reject()

    def test_modified_original_request_rejected(self):
        self.mutate("idea_intake.json", lambda v: v.update(original_user_request=v["original_user_request"] + " Extra."))
        self.reject()

    def test_modified_intake_with_rebound_checkpoint_rejected(self):
        self.mutate("idea_intake.json", lambda v: v["requested_features"].pop())
        new_digest = digest_bytes((self.directory / "idea_intake.json").read_bytes())
        self.mutate("checkpoint.json", lambda v: v.update(idea_intake_digest=new_digest))
        self.reject()

    def test_wrong_intake_readiness_rejected(self):
        self.mutate("idea_intake.json", lambda v: v["readiness"].update(ready_for_plan=True, blocking_requirements=[]))
        self.reject()

    def test_forged_checkpoint_fields_rejected(self):
        original = (self.directory / "checkpoint.json").read_bytes()
        changes = {
            "product_key": "other", "production_intent_digest": "0" * 64,
            "current_stage": "PLAN", "status": "IDEA_READY", "ready_for_plan": True,
            "blocking_requirement_keys": [], "idea_intake_digest": "0" * 64,
            "project_id": "arcadev_" + "0" * 32,
            "next_authorized_action": "GENERATE_BACKEND", "schema": "other",
            "schema_version": True, "extra": "unapproved",
        }
        for key, value in changes.items():
            with self.subTest(key=key):
                (self.directory / "checkpoint.json").write_bytes(original)
                self.mutate("checkpoint.json", lambda v: v.update({key: value}))
                self.reject()

    def test_fake_project_and_later_authority_files_rejected(self):
        for name in ("project.json", "approved_plan.json", "approved_architecture.json",
                     "approved_domain_model.json", "models_backend_handoff.json",
                     "backend_specification.json", "approved_backend.json",
                     "arcacore_generation_request.json", "fixture.json"):
            with self.subTest(name=name):
                path = self.directory / name
                path.write_bytes(b"{}\n")
                self.reject()
                path.unlink()

    def test_unknown_nested_directory_rejected(self):
        (self.directory / "archive").mkdir()
        self.reject()

    def test_network_paths_rejected_before_filesystem_access(self):
        for path in ("//server/share/authority", "//?/C:/authority"):
            for reader in (validator.read_authority, validator.validate_production_authority):
                with self.subTest(path=path, reader=reader.__name__), \
                     patch.object(Path, "stat", side_effect=AssertionError("filesystem access")):
                    with self.assertRaisesRegex(ValueError, "local"):
                        reader(Path(path))
        parent = self.directory / "linked-parent"
        child = parent / "authority"

        def link_check(path):
            if path == child:
                raise AssertionError("Inspected a child before rejecting its linked parent")
            return path == parent

        for reader in (validator.read_authority, validator.validate_production_authority):
            with self.subTest(reader=reader.__name__), \
                 patch.object(Path, "is_symlink", autospec=True, side_effect=link_check), \
                 patch.object(Path, "is_junction", return_value=False):
                with self.assertRaisesRegex(ValueError, "links"):
                    reader(child)

    def test_missing_authority_rejected(self):
        (self.directory / "idea_intake.json").unlink()
        self.reject()

    def test_modified_review_question_or_evidence_rejected(self):
        self.mutate("clarification_review.json", lambda v: v["unresolved_requirements"][0].update(question="Use SSO?"))
        self.reject()

    def test_duplicate_unknown_oversized_and_invalid_unicode_records_rejected(self):
        path = self.directory / "checkpoint.json"
        for data in (b'{"schema":1,"schema":2}\n', b'{"unknown":true}\n',
                     b" " * 100_001, b'{"text":"\\ud800"}\n', b"\xff"):
            with self.subTest(data=data[:30]):
                path.write_bytes(data)
                self.reject()

    def test_noncanonical_intake_order_rejected(self):
        self.mutate("idea_intake.json", lambda v: v["requested_features"].reverse())
        self.reject()

    def test_actual_layer_has_no_fixture_imports(self):
        validator.validate_fixture_independence()

    def test_fixture_import_scanner_rejects_import_forms(self):
        for source in ("import tools.test_arcadev_idea_intake", "from tools import fixture_arcadev_module_backend",
                       "from tools.test_arcadev_project import ArcaDevProjectTest"):
            with self.subTest(source=source), patch.object(ast, "parse", return_value=ast.parse(source)):
                with self.assertRaisesRegex(ValueError, "fixture"):
                    validator.validate_fixture_independence()

    def test_validator_has_no_generator_or_execution_dependencies(self):
        tree = ast.parse(Path(validator.__file__).read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        self.assertEqual(imports, {"argparse", "ast", "pathlib", "gaming_studio_intent", "gaming_studio_idea", "idea_intake"})

    def test_no_execution_network_generation_project_or_writes(self):
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        with patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("execution")), \
             patch.object(ArcaDevProject, "create", side_effect=AssertionError("project")), \
             patch.object(IdeaIntake, "to_project", side_effect=AssertionError("project")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("write")), \
             patch.object(Path, "write_text", side_effect=AssertionError("write")):
            validator.validate_production_authority(self.directory)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.directory.iterdir()})

    def test_cli_success_and_rejection_exit(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(validator.main([str(self.directory)]), 0)
        self.assertTrue(json.loads(output.getvalue())["valid"])
        (self.directory / "project.json").write_bytes(b"{}\n")
        with patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit) as raised:
            validator.main([str(self.directory)])
        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
