"""Run with python -m tools.test_array; no backend files are written."""

import importlib
import sys
import types
import unittest
from unittest.mock import patch

from sqlalchemy import ARRAY, JSON, Numeric, String, UUID
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import declarative_base
from sqlalchemy.schema import CreateTable

from tools.core.engine import env
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.renderers.sqlalchemy_renderer import SQLAlchemyRenderer
from tools.validators.field_validator import FieldValidator

model_generator = importlib.import_module("tools.generate_model")


def render_model(definitions):
    fields = parse_fields("Sample", definitions)
    FieldValidator.validate(fields)
    module = ModuleDefinition("Sample", "Sample", "sample", "samples", fields)
    with patch.object(model_generator, "render_template") as render:
        model_generator.generate_model(module)
    context = dict(render.call_args.kwargs)
    template_name = context.pop("template_name")
    context.pop("output_path")
    source = env.get_template(template_name).render(**context)
    base_module = types.ModuleType("backend.app.db.base")
    base_module.Base = declarative_base()
    namespace = {}
    with patch.dict(sys.modules, {"backend.app.db.base": base_module}):
        exec(compile(source, "<generated-model>", "exec"), namespace)
    model = namespace["Sample"]
    ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
    return source, model, ddl


class ArraySmokeTest(unittest.TestCase):
    def test_string_array(self):
        field = parse_fields("Sample", ["tags:array(str)"])[0]
        self.assertEqual(field.type_arguments, ["str"])
        self.assertEqual(SQLAlchemyRenderer.render(field), ["ARRAY(String)"])
        source, model, ddl = render_model(["tags:array(str)"])
        self.assertIn("    ARRAY,", source)
        self.assertIn("    String,", source)
        self.assertIsInstance(model.tags.type, ARRAY)
        self.assertIsInstance(model.tags.type.item_type, String)
        self.assertIn("tags VARCHAR[]", ddl)

    def test_supported_elements_and_modifiers(self):
        expected_types = {
            "str": "String", "int": "Integer", "float": "Float",
            "bool": "Boolean", "datetime": "DateTime", "date": "Date",
            "text": "Text", "uuid": "UUID", "json": "JSON",
        }
        for element, expected in expected_types.items():
            with self.subTest(element=element):
                _, model, _ = render_model([f"items:array({element}):nullable:index"])
                self.assertEqual(type(model.items.type.item_type).__name__, expected)
                self.assertTrue(model.items.nullable)
                self.assertTrue(model.items.index)
        field = parse_fields("Sample", ["tags:array( str ):default=list"])[0]
        self.assertEqual(SQLAlchemyRenderer.render(field), ["ARRAY(String)", "default=list"])

    def test_invalid_arrays(self):
        for raw_type in (
            "array", "array()", "array( )", "array(str,int)",
            "array(str,)", "array(,str)", "array(unknown)",
            "array(array(str))", "array(enum)", "array(decimal)",
            "array(str", "array(str))",
        ):
            with self.subTest(raw_type=raw_type):
                with self.assertRaises(ValueError):
                    parse_fields("Sample", [f"tags:{raw_type}"])

    def test_existing_types(self):
        source, model, ddl = render_model([
            "identifier:uuid:pk", "status:enum(draft,active)",
            "amount:decimal(10,2)", "payload:json", "title:str:length=200",
        ])
        self.assertNotIn("    ARRAY,", source)
        self.assertIsInstance(model.identifier.type, UUID)
        self.assertIsNotNone(model.identifier.default)
        self.assertEqual(model.status.type.enums, ["DRAFT", "ACTIVE"])
        self.assertIsInstance(model.amount.type, Numeric)
        self.assertEqual((model.amount.type.precision, model.amount.type.scale), (10, 2))
        self.assertIsInstance(model.payload.type, JSON)
        self.assertEqual(model.title.type.length, 200)
        self.assertIn("PRIMARY KEY (identifier)", ddl)


if __name__ == "__main__":
    unittest.main(verbosity=2)
