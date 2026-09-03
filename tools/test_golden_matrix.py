"""Generate the Stabilization 25.1 application matrix in temporary roots."""

from contextlib import ExitStack, redirect_stdout
from io import StringIO
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import generate as pipeline
from tools.golden_matrix import GOLDEN_APPLICATIONS, GoldenApplication
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
LAYERS = ("models", "schemas", "crud", "services", "api")
DECLARATION_PREFIXES = (
    "index(",
    "partial_index(",
    "expression_index(",
    "unique_together(",
    "check(",
)
MODULE_OPTIONS = {"soft_delete", "audit_fields", "version_column"}
REGISTRY_FIELD_KEYS = {
    "name",
    "python_type",
    "sqlalchemy_type",
    "nullable",
    "unique",
    "index",
    "default",
    "min",
    "max",
    "min_length",
    "max_length",
    "regex",
    "computed",
    "computed_sql",
    "foreign_key",
    "relationship_name",
    "relationship_class",
    "relationship_type",
    "back_populates",
    "backref",
    "association_table",
    "relationship_table",
    "relationship_key",
    "cascade_delete",
    "passive_deletes",
}


def declared_field_names(definitions):
    return [
        definition.split(":", 1)[0]
        for definition in definitions
        if definition not in MODULE_OPTIONS
        and not definition.startswith("audit_fields(")
        and not definition.startswith("version_column(")
        and not definition.startswith(DECLARATION_PREFIXES)
    ]


class GoldenMatrixSmokeTest(unittest.TestCase):
    def generate(self, root: Path, application: GoldenApplication, modules=None):
        registry_path = root / "tools" / "registry" / "models.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        selected = application.modules if modules is None else modules
        with ExitStack() as stack:
            for generator in GENERATORS:
                stack.enter_context(patch.object(generator, "PROJECT_ROOT", root))
            stack.enter_context(
                patch.object(registry_module, "REGISTRY_PATH", registry_path)
            )
            stack.enter_context(redirect_stdout(StringIO()))
            for module in selected:
                pipeline.generate_module(module.name, list(module.fields))
        return json.loads(registry_path.read_text(encoding="utf-8"))

    def generated_files(self, root: Path):
        return {
            path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
            for path in root.rglob("*")
            if path.is_file()
        }

    def python_files(self, root: Path):
        return sorted((root / "backend" / "app").glob("*/*.py"))

    def make_importable(self, root: Path):
        for package in (
            "backend",
            "backend/app",
            "backend/app/models",
            "backend/app/schemas",
            "backend/app/crud",
            "backend/app/services",
            "backend/app/api",
            "backend/app/db",
        ):
            target = root / package
            target.mkdir(parents=True, exist_ok=True)
            (target / "__init__.py").write_text("", encoding="utf-8")
        (root / "backend" / "app" / "db" / "base.py").write_text(
            "from sqlalchemy.orm import declarative_base\n\nBase = declarative_base()\n",
            encoding="utf-8",
        )
        (root / "fastapi.py").write_text(
            "class APIRouter:\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        pass\n\n"
            "    def get(self, *args, **kwargs):\n"
            "        return lambda function: function\n",
            encoding="utf-8",
        )

    def assert_imports_resolve(self, root: Path, application: GoldenApplication):
        self.make_importable(root)
        names = [module.name.lower() for module in application.modules]
        script = "\n".join(
            ["import importlib", "from backend.app.db.base import Base"]
            + [
                f'importlib.import_module("backend.app.models.{name}")'
                for name in names
            ]
            + ["Base.registry.configure()", "list(Base.metadata.sorted_tables)"]
            + [
                f'importlib.import_module("backend.app.{layer}.{name}")'
                for layer in ("schemas", "crud", "services", "api")
                for name in names
            ]
        )
        repo_root = Path(__file__).resolve().parent.parent
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            value
            for value in (
                str(root),
                str(repo_root),
                environment.get("PYTHONPATH", ""),
            )
            if value
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_matrix_has_five_named_representative_applications(self):
        self.assertEqual(
            [application.name for application in GOLDEN_APPLICATIONS],
            [
                "simple_crud_saas",
                "ecommerce_product_order",
                "crm_customer_contact",
                "multitenant_workspace_user",
                "advanced_combination",
            ],
        )
        self.assertTrue(
            all(application.description for application in GOLDEN_APPLICATIONS)
        )

    def test_every_application_generates_all_layers_and_only_expected_files(self):
        for application in GOLDEN_APPLICATIONS:
            with self.subTest(
                application=application.name
            ), TemporaryDirectory() as directory:
                root = Path(directory)
                registry = self.generate(root, application)
                expected = {"tools/registry/models.json"}
                for module in application.modules:
                    expected.update(
                        f"backend/app/{layer}/{module.name.lower()}.py"
                        for layer in LAYERS
                    )
                self.assertEqual(set(self.generated_files(root)), expected)
                self.assertEqual(
                    set(registry),
                    {module.name.capitalize() for module in application.modules},
                )

    def test_generated_python_compiles_and_imports_resolve(self):
        for application in GOLDEN_APPLICATIONS:
            with self.subTest(
                application=application.name
            ), TemporaryDirectory() as directory:
                root = Path(directory)
                self.generate(root, application)
                for path in self.python_files(root):
                    compile(path.read_text(encoding="utf-8"), str(path), "exec")
                self.assert_imports_resolve(root, application)

    def test_names_registry_schema_model_and_layers_agree(self):
        for application in GOLDEN_APPLICATIONS:
            with self.subTest(
                application=application.name
            ), TemporaryDirectory() as directory:
                root = Path(directory)
                registry = self.generate(root, application)
                paths = []
                for module in application.modules:
                    class_name = module.name.capitalize()
                    module_name = module.name.lower()
                    metadata = registry[class_name]
                    self.assertEqual(metadata["table"], f"{module_name}s")
                    self.assertEqual(
                        [field["name"] for field in metadata["fields"]],
                        declared_field_names(module.fields),
                    )
                    for field in metadata["fields"]:
                        self.assertTrue(REGISTRY_FIELD_KEYS <= set(field))

                    sources = {
                        layer: (
                            root / "backend" / "app" / layer / f"{module_name}.py"
                        ).read_text(encoding="utf-8")
                        for layer in LAYERS
                    }
                    self.assertIn(f"class {class_name}(Base):", sources["models"])
                    self.assertIn(
                        f"class {class_name}Base(_pydantic.BaseModel):",
                        sources["schemas"],
                    )
                    self.assertIn(f"class {class_name}CRUD:", sources["crud"])
                    self.assertIn(
                        f"from backend.app.models.{module_name} import {class_name}",
                        sources["crud"],
                    )
                    self.assertIn(f"class {class_name}Service:", sources["services"])
                    self.assertIn(
                        f"from backend.app.crud.{module_name} import {class_name}CRUD",
                        sources["services"],
                    )
                    self.assertIn(f'prefix="/{module_name}s"', sources["api"])
                    paths.extend(
                        root / "backend" / "app" / layer / f"{module_name}.py"
                        for layer in LAYERS
                    )
                self.assertEqual(len(paths), len(set(paths)))

    def test_regeneration_is_a_complete_deterministic_replacement(self):
        for application in GOLDEN_APPLICATIONS:
            with self.subTest(
                application=application.name
            ), TemporaryDirectory() as directory:
                root = Path(directory)
                self.generate(root, application)
                first = self.generated_files(root)
                victim = next(iter(self.python_files(root)))
                victim.write_text("obsolete\n", encoding="utf-8")
                self.generate(root, application)
                self.assertEqual(self.generated_files(root), first)

    def test_generation_is_independent_of_module_order(self):
        for application in GOLDEN_APPLICATIONS:
            with self.subTest(
                application=application.name
            ), TemporaryDirectory() as first_dir, TemporaryDirectory() as second_dir:
                first_root, second_root = Path(first_dir), Path(second_dir)
                first_registry = self.generate(first_root, application)
                second_registry = self.generate(
                    second_root, application, tuple(reversed(application.modules))
                )
                first_files = self.generated_files(first_root)
                second_files = self.generated_files(second_root)
                first_files.pop("tools/registry/models.json")
                second_files.pop("tools/registry/models.json")
                self.assertEqual(first_files, second_files)
                self.assertEqual(first_registry, second_registry)

    def test_invalid_combinations_fail_before_any_output_is_written(self):
        invalid = (
            ("Secret", ("value:str:encrypted:unique",)),
            ("Versioned", ("version_id:int", "version_column")),
            ("Linked", ("roles:many_to_many(Role)", "index(roles)")),
        )
        for name, fields in invalid:
            with self.subTest(name=name), TemporaryDirectory() as directory:
                root = Path(directory)
                registry_path = root / "tools" / "registry" / "models.json"
                with ExitStack() as stack:
                    for generator in GENERATORS:
                        stack.enter_context(
                            patch.object(generator, "PROJECT_ROOT", root)
                        )
                    stack.enter_context(
                        patch.object(registry_module, "REGISTRY_PATH", registry_path)
                    )
                    stack.enter_context(redirect_stdout(StringIO()))
                    with self.assertRaises(ValueError):
                        pipeline.generate_module(name, list(fields))
                self.assertEqual(self.generated_files(root), {})

    def test_scenarios_do_not_leak_registry_or_files_across_roots(self):
        with TemporaryDirectory() as first_dir, TemporaryDirectory() as second_dir:
            first, second = GOLDEN_APPLICATIONS[:2]
            first_root, second_root = Path(first_dir), Path(second_dir)
            first_registry = self.generate(first_root, first)
            second_registry = self.generate(second_root, second)
            self.assertEqual(set(first_registry), {"Task"})
            self.assertEqual(set(second_registry), {"Product", "Order", "Item"})
            self.assertFalse(
                (first_root / "backend" / "app" / "models" / "product.py").exists()
            )
            self.assertFalse(
                (second_root / "backend" / "app" / "models" / "task.py").exists()
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
