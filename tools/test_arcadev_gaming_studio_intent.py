"""Tests consume production authority; no fixture can supply its approval."""

import ast
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcadev import gaming_studio_intent as authority


class GamingStudioIntentTest(unittest.TestCase):
    def setUp(self):
        self.path = authority.AUTHORITY_DIRECTORY / "production_intent.json"
        self.data = self.path.read_bytes()
        self.value = json.loads(self.data)

    def reject(self, **changes):
        self.value.update(changes)
        with self.assertRaises(ValueError):
            authority.ProductionIntent.from_bytes(authority.canonical_bytes(self.value))

    def test_exact_source_roundtrip_and_utf8_digest(self):
        root = authority.load_production_intent()
        self.assertEqual(root.canonical_bytes(), self.data)
        raw = root.approved_intent.encode("utf-8")
        self.assertEqual(len(raw), 2291)
        self.assertEqual(authority.digest_bytes(raw), authority.APPROVED_INTENT_DIGEST)
        self.assertIn(b"\r\n\r\n", raw)
        self.assertFalse(raw.endswith(b"\n"))

    def test_exact_approval_binding(self):
        self.assertEqual(self.value["user_approval_text"], "I approve")
        for answer in ("I approve ", "Approved", "TEST FIXTURE ONLY", "", None):
            with self.subTest(answer=answer):
                self.reject(user_approval_text=answer)

    def test_modified_intent_and_recomputed_digest_rejected(self):
        modified = self.value["approved_intent"] + " Extra capability."
        self.reject(approved_intent=modified,
                    approved_intent_sha256=authority.digest_bytes(modified.encode()))

    def test_newline_normalization_rejected(self):
        self.reject(approved_intent=self.value["approved_intent"].replace("\r\n", "\n"))

    def test_wrong_hash_rejected(self):
        self.reject(approved_intent_sha256="0" * 64)

    def test_schema_and_product_binding(self):
        for field, value in (("schema", "other"), ("schema_version", 2),
                             ("schema_version", True), ("product_key", "fixture"),
                             ("product_display_name", "Other")):
            with self.subTest(field=field, value=value):
                self.value = json.loads(self.data)
                self.reject(**{field: value})

    def test_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            authority.ProductionIntent.from_bytes(b'{"schema":1,"schema":2}\n')

    def test_unknown_fields_and_secret_material_rejected(self):
        self.reject(token="opaque-value")
        for secret in ("password=hunter2", "ghp_opaque", "-----BEGIN PRIVATE KEY-----"):
            self.value = json.loads(self.data)
            self.reject(approved_intent=self.value["approved_intent"] + secret)

    def test_invalid_unicode_oversize_and_noncanonical_rejected(self):
        for data in (b"\xff", b'{"text":"\\ud800"}\n', b" " * 100_001,
                     self.data + b"\n", b'{"x":NaN}\n', b'[]\n'):
            with self.subTest(data=data[:30]), self.assertRaises(ValueError):
                authority.ProductionIntent.from_bytes(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_bytes(b" " * 100_001)
            with self.assertRaises(ValueError):
                authority.load_production_intent(path)

    def test_forged_direct_object_rejected(self):
        with self.assertRaises(ValueError):
            authority.ProductionIntent("forged").canonical_bytes()

    def test_no_fixture_dependency_or_execution_imports(self):
        tree = ast.parse(Path(authority.__file__).read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
        self.assertEqual(imports, {"dataclasses", "hashlib", "json", "pathlib"})

    def test_validation_has_no_execution_network_or_writes(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("execution")), \
             patch.object(Path, "write_bytes", side_effect=AssertionError("write")), \
             patch.object(Path, "write_text", side_effect=AssertionError("write")):
            self.assertEqual(authority.load_production_intent().canonical_bytes(), self.data)


if __name__ == "__main__":
    unittest.main()
