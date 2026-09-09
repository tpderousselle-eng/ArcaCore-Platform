"""Adversarial specification certification for the ArcaCore v1 boundary."""

from contextlib import ExitStack, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import generate as pipeline
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition, validate_module_definition
import tools.generate_crud as crud_generator
import tools.generate_model as model_generator
import tools.generate_router as router_generator
import tools.generate_schema as schema_generator
import tools.generate_service as service_generator
import tools.registry.registry as registry_module


GENERATORS = (model_generator, schema_generator, crud_generator, service_generator, router_generator)


class V1HostileSpecificationCertificationTest(unittest.TestCase):
    def reject_without_output(self, name, declarations):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "tools/registry/models.json"
            with ExitStack() as stack:
                for generator in GENERATORS:
                    stack.enter_context(patch.object(generator, "PROJECT_ROOT", root))
                stack.enter_context(patch.object(registry_module, "REGISTRY_PATH", registry))
                stack.enter_context(redirect_stdout(StringIO()))
                with self.assertRaises((TypeError, ValueError)):
                    pipeline.generate_module(name, list(declarations))
            self.assertEqual([path for path in root.rglob("*") if path.is_file()], [])

    def test_path_and_identifier_attacks_fail_before_generation(self):
        for name in ("../escape", "a/b", "a\\b", ".hidden", "class", "A;import os"):
            with self.subTest(name=name):
                self.reject_without_output(name, ("value:str",))

    def test_sql_python_template_and_command_payloads_fail_closed(self):
        attacks = (
            ("value:str:default=__import__('os').system('whoami')",),
            ("value:str:default={{ cycler.__init__.__globals__.os }}",),
            ("value:int", "check(value > 0); DROP TABLE users"),
            ("value:str:validator=os.system",),
            ("value:str:computed=__import__('os')",),
            ("value:str:hybrid=value + subprocess.run",),
        )
        for declarations in attacks:
            with self.subTest(declarations=declarations):
                self.reject_without_output("Record", declarations)

    def test_contradictory_privileged_and_migration_hostile_specs_fail_closed(self):
        attacks = (
            ("tenant_id:str", "tenant_scope(tenant_id,str)"),
            ("secret:text:encrypted=KEY:unique",),
            ("version_id:int", "version_column"),
            ("owner_id:int:fk=owners.id:tenant_target",),
            ("roles:many_to_many(Role)", "index(roles)"),
        )
        for declarations in attacks:
            with self.subTest(declarations=declarations):
                self.reject_without_output("Record", declarations)

    def test_resource_abuse_is_bounded_and_produces_no_artifacts(self):
        self.reject_without_output("A" * 10_000, ("value:str",))
        self.reject_without_output("Record", (f"value:str:default='{('x' * 100_000)}'",))

    def test_programmatic_metadata_mutation_is_revalidated(self):
        module = ModuleDefinition(
            "Record", "Record", "record", "records", parse_fields("Record", ["value:str"])
        )
        module.table_name = "records; DROP TABLE users"
        with self.assertRaises(ValueError):
            validate_module_definition(module)

    def test_registry_json_is_never_trusted_by_existence(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "models.json"
            path.write_text('{"Record":', encoding="utf-8")
            with patch.object(registry_module, "REGISTRY_PATH", path):
                with self.assertRaises(ValueError):
                    registry_module.Registry().load()


if __name__ == "__main__":
    unittest.main(verbosity=2)
