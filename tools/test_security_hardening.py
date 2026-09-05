"""Stabilization 25.7 hostile-input security regression tests."""

from contextlib import ExitStack, redirect_stdout
from io import StringIO
import base64
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tools import generate as pipeline
from tools.core.compose_parser import ComposeDefinition
from tools.core.dockerfile_parser import DockerfileDefinition
from tools.core.field_parser import Field
from tools.core.kubernetes_parser import KubernetesDefinition
from tools.core.module_definition import CheckRule, CompositeIndex, ModuleDefinition, UniqueTogether
from tools.kubernetes_manifest_validation import load_validated_manifest
from tools.test_composite_indexes import load_model, run_generation
import tools.generate_compose as compose_generator
import tools.generate_crud as crud_generator
import tools.generate_dockerfile as dockerfile_generator
import tools.generate_kubernetes as kubernetes_generator
import tools.generate_model as model_generator
import tools.generate_router as router_generator
import tools.generate_schema as schema_generator
import tools.generate_service as service_generator
import tools.registry.registry as registry_module


MODULE_GENERATORS = (
    (model_generator, model_generator.generate_model),
    (schema_generator, schema_generator.generate_schema),
    (crud_generator, crud_generator.generate_crud),
    (service_generator, service_generator.generate_service),
    (router_generator, router_generator.generate_router),
)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class SecurityHardeningTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory(prefix="arcacore-security-")
        self.root = Path(self.temporary_directory.name)
        self.registry_path = self.root / "tools" / "registry" / "models.json"
        self.registry_path.parent.mkdir(parents=True)
        self.registry_path.write_text('{"Existing": {"safe": true}}', encoding="utf-8")
        self.stack = ExitStack()
        for generator, _generate in MODULE_GENERATORS:
            self.stack.enter_context(patch.object(generator, "PROJECT_ROOT", self.root))
        self.stack.enter_context(patch.object(registry_module, "REGISTRY_PATH", self.registry_path))
        self.stack.enter_context(redirect_stdout(StringIO()))

    def tearDown(self):
        self.stack.close()
        self.temporary_directory.cleanup()

    def assert_rejected_unchanged(self, name, definitions):
        before = snapshot(self.root)
        with self.assertRaises(ValueError):
            pipeline.generate_module(name, definitions)
        self.assertEqual(snapshot(self.root), before)

    def test_module_path_traversal_and_hostile_identifiers_are_rejected(self):
        names = (
            "../escape", "..\\escape", "/tmp/escape", "C:\\escape", "\\\\host\\share",
            "nested/../../escape", "class", "_private", "__dunder__", "Bad;import os",
            "Bad\nInjected", "{{config}}", "{% include 'x' %}", "café",
        )
        outside = self.root.parent / "arcacore-security-escape.py"
        outside_before = outside.read_bytes() if outside.exists() else None
        for name in names:
            with self.subTest(name=name):
                self.assert_rejected_unchanged(name, ["value:str"])
        self.assertEqual(outside.read_bytes() if outside.exists() else None, outside_before)

    def test_programmatic_module_metadata_cannot_escape_any_layer_or_registry(self):
        field = Field("value", "str", "String")
        attacks = (
            ModuleDefinition("Record", "Record", "../../escape", "records", [field]),
            ModuleDefinition("Record", "Injected;pass", "record", "records", [field]),
            ModuleDefinition("Record", "Record", "record", "other_table", [field]),
        )
        before = snapshot(self.root)
        for module in attacks:
            for generator, generate in MODULE_GENERATORS:
                with self.subTest(module=module, generator=generator.__name__), self.assertRaises(ValueError):
                    generate(module)
            with self.assertRaises(ValueError):
                registry_module.Registry.register(module)
        self.assertEqual(snapshot(self.root), before)

    def test_programmatic_field_injection_is_rejected_by_every_direct_boundary(self):
        attacks = (
            Field("value", "str", "String", default="__import__('os').system('whoami')"),
            Field("bad;pass", "str", "String"),
            Field("value", "str", "String", foreign_key='users.id\"); exec("pass")'),
            Field("state", "enum", "Enum", type_arguments=["Safe", "Bad-Value"],
                  enum_name="RecordState", enum_values=["Safe", "Bad-Value"]),
            Field("amount", "decimal", "Numeric",
                  type_arguments=["10); __import__('os').system('whoami') #", "2"]),
        )
        for field in attacks:
            module = ModuleDefinition("Record", "Record", "record", "records", [field])
            before = snapshot(self.root)
            for generator, generate in MODULE_GENERATORS:
                with self.subTest(field=field, generator=generator.__name__), self.assertRaises(ValueError):
                    generate(module)
            with self.assertRaises(ValueError):
                registry_module.Registry.register(module)
            self.assertEqual(snapshot(self.root), before)

    def test_safe_programmatic_module_remains_supported(self):
        module = ModuleDefinition(
            "Record", "Record", "record", "records",
            [Field("tags", "array", "ARRAY", type_arguments=["str"], default="list")],
        )
        for _generator, generate in MODULE_GENERATORS:
            generate(module)
        registry_module.Registry.register(module)
        self.assertEqual(len(tuple((self.root / "backend").rglob("record.py"))), 5)

    def test_programmatic_indexes_and_constraints_cannot_bypass_validation(self):
        metadata_attacks = (
            {"indexes": [CompositeIndex(
                "ix_records_value_partial_deadbeef00", ["value"],
                where='"value" > 0); DROP TABLE accounts; --',
            )]},
            {"indexes": [CompositeIndex(
                "ix_records_value_expr_deadbeef00", ["value"],
                expressions=['lower("value") || load_extension(\'evil\')'],
            )]},
            {"unique_constraints": [UniqueTogether("uq_records_value_other;DROP", ["value", "other"])]},
            {"check_constraints": [CheckRule(
                "ck_records_deadbeef00", '"value" > 0); DROP TABLE accounts; --',
            )]},
        )
        fields = [Field("value", "int", "Integer"), Field("other", "int", "Integer")]
        for metadata in metadata_attacks:
            module = ModuleDefinition(
                "Record", "Record", "record", "records", fields, **metadata
            )
            before = snapshot(self.root)
            for generator, generate in MODULE_GENERATORS:
                with self.subTest(metadata=metadata, generator=generator.__name__), self.assertRaises(ValueError):
                    generate(module)
            with self.assertRaises(ValueError):
                registry_module.Registry.register(module)
            self.assertEqual(snapshot(self.root), before)

    def test_python_code_injection_through_fields_defaults_foreign_keys_and_enums_fails(self):
        cases = (
            ["x;import_os:str"],
            ["__class__:str"],
            ["value:str:default=__import__('os').system('whoami')"],
            ["value:str:default=(lambda: 1)()"],
            ["value:str:default=data[0]"],
            ['owner_id:int:fk=users.id\");__import__("os")'],
            ["state:enum(Safe,Bad-Value)"],
            ["state:enum(Safe,__import__)"],
        )
        for definitions in cases:
            with self.subTest(definitions=definitions):
                self.assert_rejected_unchanged("Record", definitions)

    def test_literal_template_syntax_remains_inert_data(self):
        payload = "{{ cycler.__init__.__globals__ }} {% include 'x' %} {# secret #}"
        pipeline.generate_module("Record", [f"value:str:default={payload!r}"])
        generated = tuple((self.root / "backend").rglob("record.py"))
        self.assertEqual(len(generated), 5)
        for path in generated:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
            self.assertNotIn("__globals__ =", source)
        model_path = self.root / "backend" / "app" / "models" / "record.py"
        self.assertIn(payload, model_path.read_text(encoding="utf-8"))

    def test_validator_references_reject_syntax_and_execution_primitives(self):
        references = (
            "os.system", "subprocess.run", "builtins.eval", "importlib.import_module",
            "urllib.request.urlopen", "requests.get", "http.client.HTTPConnection",
            "socket.create_connection",
            "rules.check()", "rules.items[0]", ".rules.check", "rules.__dict__.get",
            "rules.check;exec", "rules.check\nimport os", "pathlib.Path.unlink",
        )
        for reference in references:
            with self.subTest(reference=reference):
                self.assert_rejected_unchanged("Record", [f"value:str:validator={reference}"])

    def test_callable_defaults_use_a_positive_allowlist(self):
        for reference in (
            "exit", "quit", "eval", "exec", "compile", "open", "input", "breakpoint",
            "__import__", "random.choice", "urllib.request.urlopen",
        ):
            with self.subTest(reference=reference):
                self.assert_rejected_unchanged("Record", [f"value:str:default={reference}"])
        pipeline.generate_module("SafeDefaults", ["items:array(str):default=list", "active:bool:default=True"])

    def test_computed_hybrid_index_and_constraint_grammars_reject_injection(self):
        attacks = (
            ["amount:int", "total:int:computed=amount; __import__('os')"],
            ["amount:int", "total:int:computed=__import__('os').system('x')"],
            ["amount:int", "total:int:hybrid=amount.__class__"],
            ["email:str", "expression_index(__import__('os'))"],
            ["amount:int", "partial_index(amount,where=amount > 0); DROP TABLE records"],
            ["amount:int", "check(amount > 0 -- injected)"],
            ["amount:int", "check({{ amount }})"],
        )
        for definitions in attacks:
            with self.subTest(definitions=definitions):
                self.assert_rejected_unchanged("Record", definitions)

    def test_docker_and_compose_reject_paths_directives_and_command_payloads(self):
        attacks = (
            lambda: DockerfileDefinition(requirements="../secret"),
            lambda: DockerfileDefinition(source="C:\\Windows"),
            lambda: DockerfileDefinition(app="backend.main:app\nRUN whoami"),
            lambda: DockerfileDefinition(app="backend.main:app;whoami"),
            lambda: ComposeDefinition(env_file="..\\.env"),
            lambda: ComposeDefinition(dockerfile="/tmp/Dockerfile"),
            lambda: ComposeDefinition(database_image="postgres:16\nvolumes: [/etc:/host]"),
            lambda: ComposeDefinition(project_name="safe; whoami"),
        )
        before = snapshot(self.root)
        for attack in attacks:
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                attack()
        self.assertEqual(snapshot(self.root), before)

    def test_kubernetes_rejects_yaml_injection_and_preserves_strict_schema(self):
        attacks = (
            lambda: KubernetesDefinition(name="safe\n---\nkind: Secret"),
            lambda: KubernetesDefinition(namespace="{{ namespace }}"),
            lambda: KubernetesDefinition(api_image="api:latest\ncommand: [sh]"),
            lambda: KubernetesDefinition(secret_name="../../secret"),
            lambda: KubernetesDefinition(storage_size="1Gi\n---"),
        )
        for attack in attacks:
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                attack()
        with patch.object(kubernetes_generator, "PROJECT_ROOT", self.root):
            path = kubernetes_generator.generate_kubernetes(KubernetesDefinition())
        validated = load_validated_manifest(path)
        self.assertEqual(len(validated.documents), 7)
        self.assertNotIn("Secret", {item["kind"] for item in validated.documents})

    def test_secret_values_do_not_enter_generated_artifacts_registry_or_output(self):
        sentinel = "ARCACORE_SENTINEL_SECRET_7f29d1"
        with patch.dict(os.environ, {"DATABASE_URL": sentinel, "VAULT_KEYS": sentinel}), patch.object(
            dockerfile_generator, "PROJECT_ROOT", self.root
        ), patch.object(
            compose_generator, "PROJECT_ROOT", self.root
        ), patch.object(kubernetes_generator, "PROJECT_ROOT", self.root):
            (self.root / "backend").mkdir()
            (self.root / "backend" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
            dockerfile_generator.generate_dockerfile()
            compose_generator.generate_compose()
            kubernetes_generator.generate_kubernetes()
        pipeline.generate_module("Vault", ["payload:str:encrypted=VAULT_KEYS"])
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(sentinel, path.read_text(encoding="utf-8"))

    def test_encrypted_plaintext_is_absent_from_storage_metadata_source_and_repr(self):
        plaintext = "ARCACORE_PLAINTEXT_SENTINEL_2ac98e"
        key = base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii")
        with patch.dict(os.environ, {"ARCACORE_ENCRYPTION_KEYS": key}, clear=False):
            sources, registry = run_generation(["secret:str:encrypted"])
            model = load_model(sources["model.j2"])
            self.addCleanup(model.registry.dispose)
            engine = create_engine("sqlite://")
            self.addCleanup(engine.dispose)
            model.metadata.create_all(engine)
            with Session(engine) as session:
                row = model(secret=plaintext)
                session.add(row)
                session.commit()
                identifier = row.id
                self.assertNotIn(plaintext, repr(row))
            with engine.connect() as connection:
                stored = connection.exec_driver_sql(
                    "SELECT secret FROM records WHERE id = ?", (identifier,)
                ).scalar_one()
            with Session(engine) as session:
                self.assertEqual(session.get(model, identifier).secret, plaintext)
        self.assertTrue(stored.startswith("v1."))
        self.assertNotIn(plaintext, stored)
        self.assertNotIn(plaintext, repr(registry))
        self.assertNotIn(plaintext, "".join(sources.values()))

    def test_subprocess_boundaries_use_argument_lists_without_shell_execution(self):
        tool_files = (
            "core/engine.py", "docker_compose_test_runtime.py",
            "kubernetes_manifest_validation.py", "postgresql_test_server.py",
            "test_golden_matrix.py",
        )
        for relative in tool_files:
            source = (Path(__file__).parent / relative).read_text(encoding="utf-8")
            with self.subTest(path=relative):
                self.assertNotIn("shell=True", source)
                self.assertNotIn("os.system(", source)
        runtime = (Path(__file__).parent / "docker_compose_test_runtime.py").read_text(encoding="utf-8")
        self.assertIn("command = [*self.compose_prefix, *arguments]", runtime)

    def test_generated_routers_require_server_authenticated_scoped_identity(self):
        pipeline.generate_module("Record", ["name:str", "audit_fields"])
        source = (
            self.root / "backend" / "app" / "api" / "record.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("X-Actor-ID", source)
        self.assertNotIn("Header(", source)
        self.assertIn('request.state, "arcacore_principal_id"', source)
        self.assertIn('request.state, "arcacore_scopes"', source)
        self.assertIn('"record:read"', source)
        self.assertIn('"record:write"', source)
        self.assertIn("Depends(_require_read_access)", source)
        self.assertIn("Depends(_require_write_access)", source)
        compile(source, "<generated-secure-router>", "exec")


if __name__ == "__main__":
    unittest.main(verbosity=2)
