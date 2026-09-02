"""Run python -m tools.test_composite_indexes; generated files stay in memory."""

from contextlib import ExitStack, redirect_stdout
import importlib
from io import StringIO
import sys
import types
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import declarative_base
from sqlalchemy.schema import CreateIndex

from tools.core.engine import env
from tools.core.field_parser import parse_fields
from tools.core.index_parser import parse_indexes
from tools.registry.registry import Registry

pipeline = importlib.import_module("tools.generate")
cli = importlib.import_module("tools.__main__")
GENERATORS = ("model", "schema", "crud", "service", "router")


def run_generation(definitions, use_cli=False):
    sources = {}

    def capture(template_name, output_path, **context):
        source = env.get_template(template_name).render(**context)
        compile(source, str(output_path), "exec")
        sources[template_name] = source

    with ExitStack() as stack:
        for kind in GENERATORS:
            generator = importlib.import_module(f"tools.generate_{kind}")
            stack.enter_context(patch.object(generator, "render_template", side_effect=capture))
        stack.enter_context(patch.object(Registry, "load", return_value={}))
        save = stack.enter_context(patch.object(Registry, "save"))
        stack.enter_context(redirect_stdout(StringIO()))
        if use_cli:
            stack.enter_context(patch.object(sys, "argv", ["tools", "generate", "Record", *definitions]))
            cli.main()
        else:
            pipeline.generate_module("Record", definitions)
    return sources, save.call_args.args[0]


def load_model(source):
    base_module = types.ModuleType("backend.app.db.base")
    base_module.Base = declarative_base()
    namespace = {}
    with patch.dict(sys.modules, {"backend.app.db.base": base_module}):
        exec(compile(source, "<generated-model>", "exec"), namespace)
    return namespace["Record"]


class CompositeIndexSmokeTest(unittest.TestCase):
    def test_database_index_and_registry(self):
        sources, registry = run_generation([
            "tenant_id:int:index", "status:str:length=40", "index(tenant_id,status)",
        ])
        self.assertEqual(set(sources), {f"{kind}.j2" for kind in GENERATORS})
        model = load_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            indexes = {item["name"]: item for item in inspect(engine).get_indexes("records")}
            self.assertEqual(indexes["ix_records_tenant_id_status"]["column_names"], ["tenant_id", "status"])
            self.assertFalse(indexes["ix_records_tenant_id_status"]["unique"])
            self.assertEqual(indexes["ix_records_tenant_id"]["column_names"], ["tenant_id"])
            self.assertEqual(registry["Record"]["indexes"], [
                {"name": "ix_records_tenant_id_status", "columns": ["tenant_id", "status"]},
            ])
            self.assertEqual(len(registry["Record"]["fields"]), 2)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_multiple_indexes_preserve_order(self):
        sources, _ = run_generation([
            "a:int", "b:int", "c:int",
            "index( a, b, c )", "index(b,a)",
        ])
        model = load_model(sources["model.j2"])
        try:
            indexes = {item.name: item for item in model.__table__.indexes}
            self.assertEqual(list(indexes["ix_records_a_b_c"].columns.keys()), ["a", "b", "c"])
            self.assertEqual(list(indexes["ix_records_b_a"].columns.keys()), ["b", "a"])
            sql = str(CreateIndex(indexes["ix_records_b_a"]).compile(dialect=postgresql.dialect()))
            self.assertIn("(b, a)", sql)
        finally:
            model.registry.dispose()

    def test_implicit_and_custom_keys(self):
        sources, _ = run_generation(["title:str", "index(id,created_at)"])
        model = load_model(sources["model.j2"])
        try:
            self.assertIn("ix_records_id_created_at", {index.name for index in model.__table__.indexes})
        finally:
            model.registry.dispose()
        sources, _ = run_generation([
            "identifier:uuid:pk", "status:choice(Draft,Published)", "index(identifier,status)",
        ])
        model = load_model(sources["model.j2"])
        try:
            self.assertNotIn("id", model.__table__.c)
            index = next(iter(model.__table__.indexes))
            self.assertEqual(list(index.columns.keys()), ["identifier", "status"])
        finally:
            model.registry.dispose()

    def test_invalid_declarations_fail_before_generation(self):
        invalid = (
            ["a:int", "b:int", "index"],
            ["a:int", "b:int", "index()"],
            ["a:int", "b:int", "index(a)"],
            ["a:int", "b:int", "index(a,)"],
            ["a:int", "b:int", "index(a,a)"],
            ["a:int", "b:int", "index(a,missing)"],
            ["a:int", "b:int", "index(a,b"],
            ["a:int", "b:int", "index(a,b):unique"],
            ["a:int", "b:int", "index(a,b)", "index(a,b)"],
            ["identifier:uuid:pk", "title:str", "index(id,title)"],
            ["roles:many_to_many(Role)", "title:str", "index(roles,title)"],
        )
        for definitions in invalid:
            with self.subTest(definitions=definitions):
                with patch.object(pipeline, "generate_model") as generate:
                    with patch.object(Registry, "register") as register:
                        with self.assertRaises(ValueError):
                            pipeline.generate_module("Record", definitions)
                        generate.assert_not_called()
                        register.assert_not_called()

    def test_long_names_are_stable(self):
        column_a, column_b = "first_" + "a" * 40, "second_" + "b" * 40
        sources, registry = run_generation([
            f"{column_a}:int", f"{column_b}:int", f"index({column_a},{column_b})",
        ])
        name = registry["Record"]["indexes"][0]["name"]
        self.assertLessEqual(len(name.encode("utf-8")), 63)
        fields = parse_fields("Record", [f"{column_a}:int", f"{column_b}:int"])
        self.assertEqual(parse_indexes("records", [f"index({column_a},{column_b})"], fields)[0].name, name)
        model = load_model(sources["model.j2"])
        try:
            for index in model.__table__.indexes:
                str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        finally:
            model.registry.dispose()

    def test_cli_entry_point(self):
        sources, registry = run_generation([
            "index(tenant_id,status)", "tenant_id:int", "status:str",
        ], use_cli=True)
        self.assertIn("__table_args__", sources["model.j2"])
        self.assertEqual(registry["Record"]["indexes"][0]["columns"], ["tenant_id", "status"])

    def test_existing_field_named_index(self):
        sources, registry = run_generation(["index:str:index", "title:str"])
        self.assertNotIn("    Index,", sources["model.j2"])
        self.assertNotIn("__table_args__", sources["model.j2"])
        self.assertEqual(registry["Record"]["indexes"], [])
        model = load_model(sources["model.j2"])
        try:
            self.assertTrue(model.__table__.c.index.index)
        finally:
            model.registry.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
