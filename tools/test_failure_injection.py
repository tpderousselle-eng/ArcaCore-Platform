"""Stabilization 25.6 failure injection and generation rollback tests."""

from contextlib import ExitStack, redirect_stdout
from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import generate as pipeline
from tools.core.compose_parser import ComposeDefinition
from tools.core.dockerfile_parser import DockerfileDefinition
from tools.core.kubernetes_parser import KubernetesDefinition
from tools.core import engine
import tools.generate_crud as crud_generator
import tools.generate_model as model_generator
import tools.generate_router as router_generator
import tools.generate_schema as schema_generator
import tools.generate_service as service_generator
import tools.registry.registry as registry_module


GENERATORS = (
    model_generator,
    schema_generator,
    crud_generator,
    service_generator,
    router_generator,
)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class FailureInjectionAndRegressionHardeningTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory(prefix="arcacore-failure-")
        self.root = Path(self.temporary_directory.name)
        self.registry_path = self.root / "tools" / "registry" / "models.json"
        self.registry_path.parent.mkdir(parents=True)
        self.registry_path.write_text("{}", encoding="utf-8")
        self.stack = ExitStack()
        for generator in GENERATORS:
            self.stack.enter_context(patch.object(generator, "PROJECT_ROOT", self.root))
        self.stack.enter_context(
            patch.object(registry_module, "REGISTRY_PATH", self.registry_path)
        )
        self.stack.enter_context(redirect_stdout(StringIO()))

    def tearDown(self):
        self.stack.close()
        self.temporary_directory.cleanup()

    def assert_invalid_unchanged(self, definitions):
        before = snapshot(self.root)
        with self.assertRaises((ValueError, TypeError)):
            pipeline.generate_module("Record", definitions)
        self.assertEqual(snapshot(self.root), before)

    def test_malformed_dsl_fails_before_writing(self):
        cases = (
            ["missing_type"],
            ["tags:array()"],
            ["state:choice(open,,closed)"],
            ["amount:decimal(8)"],
            ["title:str:default='unterminated"],
            ["title:str:unsupported=value"],
        )
        for definitions in cases:
            with self.subTest(definitions=definitions):
                self.assert_invalid_unchanged(definitions)

    def test_conflicting_fields_and_primary_keys_fail_before_writing(self):
        cases = (
            ["value:unknown"],
            ["id:int:pk:pk"],
            ["id:int:pk:nullable"],
            ["value:int:length=4"],
            ["value:str:default='a':default='b'"],
            ["value:str:nullable:nullable"],
        )
        for definitions in cases:
            with self.subTest(definitions=definitions):
                self.assert_invalid_unchanged(definitions)

    def test_invalid_relationships_fail_before_writing(self):
        cases = (
            ["owner_id:int:fk="],
            ["owner_id:int:one_to_one"],
            ["parent_id:int:fk=records.id:self_relationship:one_to_many"],
            ["peers:many_to_many(Record)"],
            ["owner_id:int:fk=users.id:one_to_many:one_to_many"],
        )
        for definitions in cases:
            with self.subTest(definitions=definitions):
                self.assert_invalid_unchanged(definitions)

    def test_invalid_indexes_and_constraints_fail_before_writing(self):
        cases = (
            ["a:int", "index(a,missing)"],
            ["a:int", "partial_index(a,where=missing > 0)"],
            ["email:str", "expression_index(lower(missing))"],
            ["a:int", "check(a >=)"],
            ["a:int", "b:int", "unique_together(a,b)", "unique_together(b,a)"],
        )
        for definitions in cases:
            with self.subTest(definitions=definitions):
                self.assert_invalid_unchanged(definitions)

    def test_invalid_validators_computed_hybrid_and_managed_fields_fail_safely(self):
        cases = (
            ["name:str:validator=missing"],
            ["name:str:validator=_private.rule"],
            ["amount:int", "total:int:computed=missing + 1"],
            ["amount:int", "total:int:hybrid=missing + 1"],
            ["secret:int:encrypted"],
            ["name:str", "audit_fields", "audit_fields"],
            ["name:str", "version_column", "version_column"],
            ["version_id:int", "version_column"],
        )
        for definitions in cases:
            with self.subTest(definitions=definitions):
                self.assert_invalid_unchanged(definitions)

    def test_invalid_deployment_metadata_is_rejected_without_output(self):
        before = snapshot(self.root)
        constructors = (
            lambda: DockerfileDefinition(port=0),
            lambda: DockerfileDefinition(source="../backend"),
            lambda: ComposeDefinition(project_name="Unsafe Name"),
            lambda: ComposeDefinition(env_file="../.env"),
            lambda: KubernetesDefinition(name="Unsafe_Name"),
            lambda: KubernetesDefinition(api_port=0),
            lambda: KubernetesDefinition(storage_size="0Gi"),
        )
        for constructor in constructors:
            with self.subTest(constructor=constructor), self.assertRaises(ValueError):
                constructor()
        self.assertEqual(snapshot(self.root), before)

    def test_new_module_rolls_back_interrupted_multi_file_generation(self):
        before = snapshot(self.root)
        with patch.object(pipeline, "generate_service", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                pipeline.generate_module("Record", ["name:str"])
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse((self.root / "backend").exists())

    def test_failed_regeneration_restores_every_prior_file_and_registry(self):
        pipeline.generate_module("Record", ["name:str:length=20"])
        before = snapshot(self.root)
        with patch.object(pipeline, "generate_router", side_effect=RuntimeError("injected")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                pipeline.generate_module("Record", ["name:str:length=80"])
        self.assertEqual(snapshot(self.root), before)

    def test_registry_failure_rolls_back_generated_outputs(self):
        before = snapshot(self.root)
        with patch.object(registry_module.Registry, "save", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                pipeline.generate_module("Record", ["name:str"])
        self.assertEqual(snapshot(self.root), before)

    def test_atomic_file_replace_preserves_existing_file_and_cleans_temp(self):
        output = self.root / "existing.py"
        output.write_bytes(b"prior valid output\n")
        before = snapshot(self.root)
        with patch.object(os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(OSError, "replace failed"):
                engine.render_template("router.j2", output, class_name="Record", module="record", fields=[], soft_delete=False, audit_fields=False, actor_type=None, primary_key_type="int")
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(list(self.root.glob(".existing.py.*")), [])

    def test_repeated_invalid_operation_and_failure_after_success_are_stable(self):
        pipeline.generate_module("Record", ["name:str"])
        before = snapshot(self.root)
        for _ in range(3):
            self.assert_invalid_unchanged(["name:str", "check(missing > 0)"])
        self.assertEqual(snapshot(self.root), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
