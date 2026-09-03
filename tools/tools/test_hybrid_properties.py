"""Hybrid-property smoke tests; generated files and databases stay in memory."""

from contextlib import ExitStack
from decimal import Decimal
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from tools.core.field_parser import Field, parse_fields
from tools.core.hybrid_property_parser import validate_hybrid_properties
from tools.core.module_definition import ModuleDefinition
from tools.generate_model import generate_model
from tools.generate_schema import generate_schema
from tools.registry.registry import Registry
from tools.test_composite_indexes import GENERATORS, load_model, pipeline, run_generation
from tools.test_custom_validators import rules
from tools.test_one_to_many import database, generate_models
from tools.test_soft_delete import load_generated
from tools.test_validators import schemas
from tools.validators.field_validator import FieldValidator


def generated_model(source):
    model = load_model(source)
    model.__module__ = "generated_hybrid_model"
    return model


class HybridPropertySmokeTest(unittest.TestCase):
    def test_numeric_instance_sql_query_and_recalculation(self):
        namespace, sources, _ = schemas([
            "quantity:int",
            "price:decimal(10,2)",
            "total:decimal(12,2):hybrid=quantity * price",
        ])
        model = generated_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        self.addCleanup(model.registry.dispose)
        model.metadata.create_all(engine)

        self.assertNotIn("total", model.__table__.c)
        with Session(engine) as session:
            row = model(quantity=3, price=Decimal("2.50"))
            session.add(row)
            session.commit()
            self.assertEqual(row.total, Decimal("7.50"))
            self.assertEqual(session.scalar(select(model.total)), Decimal("7.50"))
            self.assertEqual(session.scalar(select(model).where(model.total > 7)), row)
            row.quantity = 4
            session.commit()
            self.assertEqual(row.total, Decimal("10.00"))
            response = namespace["RecordResponse"].model_validate(row)
            self.assertEqual(response.total, Decimal("10.00"))

    def test_text_concatenation_forward_references_and_sql(self):
        _, sources, _ = schemas([
            "display_name:str:hybrid=first_name + ': ' + last_name",
            "first_name:str",
            "last_name:text",
        ])
        model = generated_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        self.addCleanup(model.registry.dispose)
        model.metadata.create_all(engine)

        with Session(engine) as session:
            row = model(first_name="Tyler", last_name="Derousselle")
            session.add(row)
            session.commit()
            self.assertEqual(row.display_name, "Tyler: Derousselle")
            self.assertEqual(
                session.scalar(
                    select(model.display_name).where(
                        model.display_name == "Tyler: Derousselle"
                    )
                ),
                "Tyler: Derousselle",
            )
        sql = str(select(model.display_name).compile(dialect=postgresql.dialect()))
        self.assertIn("records.first_name ||", sql)
        self.assertIn("records.last_name", sql)

    def test_decimal_literals_float_arithmetic_and_exact_values(self):
        _, decimal_sources, registry = schemas([
            "price:decimal(24,18)",
            "adjusted:decimal(24,18):hybrid=price + 0.100000000000000001",
        ])
        self.assertIn(
            "_decimal.Decimal('0.100000000000000001')",
            decimal_sources["model.j2"],
        )
        metadata = registry["Record"]["fields"][-1]
        self.assertIn("0.100000000000000001", metadata["hybrid_python"])
        decimal_model = generated_model(decimal_sources["model.j2"])
        float_sources, _ = run_generation([
            "score:float",
            "weighted:float:hybrid=score * 1.5 + 2",
        ])
        float_model = generated_model(float_sources["model.j2"])
        try:
            self.assertEqual(
                decimal_model(price=Decimal("1")).adjusted,
                Decimal("1.100000000000000001"),
            )
            self.assertEqual(float_model(score=2.0).weighted, 5.0)
        finally:
            decimal_model.registry.dispose()
            float_model.registry.dispose()

    def test_nullable_sources_return_none_and_query_with_database_semantics(self):
        namespace, sources, _ = schemas([
            "amount:int:nullable",
            "doubled:int:nullable:hybrid=amount * 2",
        ])
        model = generated_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        self.addCleanup(model.registry.dispose)
        model.metadata.create_all(engine)

        self.assertIn(
            "return None if self.amount is None else (self.amount * 2)",
            sources["model.j2"],
        )
        with Session(engine) as session:
            empty = model(amount=None)
            full = model(amount=3)
            session.add_all([empty, full])
            session.commit()
            self.assertIsNone(empty.doubled)
            self.assertEqual(full.doubled, 6)
            self.assertEqual(
                session.scalars(select(model).where(model.doubled.is_(None))).all(),
                [empty],
            )
            self.assertIsNone(
                namespace["RecordResponse"].model_validate(empty).doubled
            )

    def test_read_only_schema_behavior_and_property_has_no_setter(self):
        namespace, sources, _ = schemas([
            "quantity:int",
            "doubled:int:min=0:hybrid=quantity * 2",
        ])
        for name in ("RecordCreate", "RecordUpdate"):
            schema = namespace[name]
            self.assertNotIn("doubled", schema.model_fields)
            with self.assertRaises(ValidationError):
                schema(quantity=2, doubled=4)
        self.assertTrue(
            namespace["RecordResponse"]
            .model_json_schema()["properties"]["doubled"]["readOnly"]
        )
        with self.assertRaises(ValidationError):
            namespace["RecordResponse"](id=1, quantity=2)
        model = generated_model(sources["model.j2"])
        try:
            row = model(quantity=2)
            with self.assertRaises(AttributeError):
                row.doubled = 8
        finally:
            model.registry.dispose()

    def test_response_constraints_formats_and_custom_validators(self):
        calls = []

        def maximum(value):
            calls.append(value)
            if value > 10:
                raise ValueError("Hybrid value is too large.")
            return value

        with rules(maximum=maximum):
            namespace, _, _ = schemas([
                "quantity:int",
                "doubled:int:max=10:hybrid=quantity * 2:validator=application_rules.maximum",
            ])
        self.assertEqual(
            namespace["RecordResponse"].model_validate(
                SimpleNamespace(id=1, quantity=4, doubled=8)
            ).doubled,
            8,
        )
        with self.assertRaises(ValidationError):
            namespace["RecordResponse"].model_validate(
                SimpleNamespace(id=1, quantity=6, doubled=12)
            )
        self.assertEqual(calls, [8])

        namespace, _, _ = schemas([
            "name:str",
            "slug:str:format=slug:hybrid=name + '-account'",
        ])
        value = SimpleNamespace(id=1, name="tyler", slug="tyler-account")
        self.assertEqual(
            namespace["RecordResponse"].model_validate(value).slug,
            "tyler-account",
        )

    def test_cli_registry_and_json_schema_metadata(self):
        namespace, sources, registry = schemas([
            "quantity:int",
            "price:decimal(10,2)",
            "total:decimal(12,2):hybrid=quantity * price",
        ], use_cli=True)
        metadata = json.loads(json.dumps(registry))["Record"]["fields"][-1]
        self.assertEqual(metadata["hybrid"], "quantity * price")
        self.assertEqual(metadata["hybrid_python"], "(self.quantity * self.price)")
        self.assertEqual(metadata["hybrid_class"], "(cls.quantity * cls.price)")
        self.assertEqual(metadata["hybrid_references"], ["quantity", "price"])
        self.assertNotIn("total = Column", sources["model.j2"])
        response = namespace["RecordResponse"].model_json_schema()["properties"]
        self.assertTrue(response["total"]["readOnly"])
        self.assertNotIn(
            "total", namespace["RecordCreate"].model_json_schema()["properties"]
        )

    def test_computed_soft_delete_relationships_and_custom_keys_compose(self):
        definitions = {
            "User": ["identifier:uuid:pk", "first:str", "last:str",
                     "display:str:hybrid=first + ' ' + last", "soft_delete"],
            "Post": [
                "owner_id:uuid:fk=users.identifier:one_to_many(User,posts):cascade_delete:passive_deletes",
                "quantity:int",
                "price:int",
                "stored_total:int:computed=quantity * price",
                "live_total:int:hybrid=quantity * price",
            ],
        }
        base, models, _, registry = generate_models(definitions)
        engine = database(base)
        self.addCleanup(engine.dispose)
        self.addCleanup(base.registry.dispose)

        with Session(engine) as session:
            key = uuid4()
            user = models["User"](
                identifier=key,
                first="Tyler",
                last="Derousselle",
                posts=[models["Post"](quantity=2, price=5)],
            )
            session.add(user)
            session.commit()
            self.assertEqual(user.display, "Tyler Derousselle")
            self.assertEqual(user.posts[0].stored_total, 10)
            self.assertEqual(user.posts[0].live_total, 10)
            self.assertEqual(
                session.scalar(select(models["Post"].live_total)), 10
            )
        self.assertTrue(registry["User"]["soft_delete"])
        self.assertEqual(
            registry["Post"]["fields"][-1]["hybrid_references"],
            ["quantity", "price"],
        )

    def test_invalid_expressions_fail_before_all_generation(self):
        expressions = (
            "",
            "missing + 1",
            "total + 1",
            "quantity / 2",
            "quantity // 2",
            "quantity % 2",
            "quantity ** 2",
            "abs(quantity)",
            "quantity.real",
            "quantity[0]",
            "quantity if quantity else 0",
            "quantity > 0",
            "quantity + True",
            "quantity + None",
            "1 + 2",
            "__import__('os').system('false')",
            "(quantity + 1",
            "quantity + " + "+".join(["1"] * 100),
        )
        for expression in expressions:
            with self.subTest(expression=expression):
                self.assert_invalid([
                    "quantity:int",
                    f"total:int:hybrid={expression}",
                ])

    def test_invalid_types_results_references_and_modifiers(self):
        cases = (
            ["value:bool", "result:bool:hybrid=value"],
            ["value:json()", "result:str:hybrid=value"],
            ["value:array(int)", "result:int:hybrid=value"],
            ["value:float", "result:int:hybrid=value"],
            ["value:decimal(8,2)", "result:float:hybrid=value"],
            ["value:float", "result:decimal(8,2):hybrid=value"],
            ["value:str", "result:int:hybrid=value"],
            ["value:int", "result:str:hybrid=value"],
            ["value:int:nullable", "result:int:hybrid=value"],
            ["value:int", "result:int:hybrid=result + value"],
            ["value:int", "result:int:hybrid=value:computed=value"],
            ["value:int", "result:int:hybrid=value:default=1"],
            ["value:int", "result:int:pk:hybrid=value"],
            ["value:int", "result:int:unique:hybrid=value"],
            ["value:int", "result:int:index:hybrid=value"],
            ["value:int", "result:int:fk=records.value:hybrid=value"],
            ["value:int", "id:int:hybrid=value"],
            ["value:int", "created_at:int:hybrid=value"],
            ["value:int", "result:decimal():hybrid=value"],
            ["value:int", "result:decimal(1,2):hybrid=value"],
            ["value:int", "first:int:hybrid=value", "second:int:hybrid=first + 1"],
            ["value:int", "stored:int:computed=value", "result:int:hybrid=stored"],
            ["value:int", "virtual:int:hybrid=value", "stored:int:computed=virtual"],
            ["roles:many_to_many(Role)", "result:int:hybrid=roles"],
        )
        for definitions in cases:
            with self.subTest(definitions=definitions):
                self.assert_invalid(definitions)

    def test_hybrid_fields_are_rejected_as_indexes_and_constraints(self):
        declarations = (
            "index(quantity,total)",
            "partial_index(total,where=total > 0)",
            "expression_index(abs(total))",
            "unique_together(quantity,total)",
            "check(total > 0)",
        )
        for declaration in declarations:
            with self.subTest(declaration=declaration):
                self.assert_invalid([
                    "quantity:int",
                    "total:int:hybrid=quantity * 2",
                    declaration,
                ])

    def test_programmatic_metadata_and_direct_generators_validate(self):
        invalid = Field(
            "total",
            "int",
            "Integer",
            hybrid_expression="missing + 1",
        )
        module = ModuleDefinition(
            "Record", "Record", "record", "records", [invalid]
        )
        with self.assertRaises(ValueError):
            validate_hybrid_properties([invalid])
        with self.assertRaises(ValueError):
            FieldValidator.validate([invalid])
        for generator, patch_target in (
            (generate_model, "tools.generate_model.render_template"),
            (generate_schema, "tools.generate_schema.render_template"),
        ):
            with self.subTest(generator=generator.__name__), patch(patch_target) as render:
                with self.assertRaises(ValueError):
                    generator(module)
                render.assert_not_called()

        fields = [
            Field("quantity", "int", "Integer"),
            Field(
                "total",
                "int",
                "Integer",
                hybrid_expression="quantity * 2",
            ),
        ]
        validate_hybrid_properties(fields)
        self.assertEqual(fields[-1].hybrid_python, "(self.quantity * 2)")
        self.assertEqual(fields[-1].hybrid_class, "(cls.quantity * 2)")

    def test_models_without_hybrids_keep_existing_outputs(self):
        definitions = [
            "name:str",
            "quantity:int",
            "total:int:computed=quantity * 2",
            "soft_delete",
        ]
        sources, registry = run_generation(definitions)
        self.assertNotIn("hybrid_property", sources["model.j2"])
        self.assertNotIn("_expression(cls)", sources["model.j2"])
        self.assertNotIn("hybrid", registry["Record"]["fields"][0])

        with_hybrid, _ = run_generation([
            *definitions,
            "live_total:int:hybrid=quantity * 2",
        ])
        for kind in ("crud", "service", "router"):
            self.assertEqual(sources[f"{kind}.j2"], with_hybrid[f"{kind}.j2"])

    def test_modifier_order_cli_preflight_and_security_limits(self):
        first = parse_fields("Record", [
            "quantity:int",
            "total:int:min=0:hybrid=quantity * 2:validator=rules.check",
        ])
        second = parse_fields("Record", [
            "quantity:int",
            "total:int:validator=rules.check:hybrid=quantity * 2:min=0",
        ])
        self.assertEqual(first, second)
        self.assert_invalid([
            "quantity:int",
            "total:int:hybrid=quantity:hybrid=quantity + 1",
        ])
        self.assert_invalid([
            "quantity:int",
            "total:int:hybrid=quantity + 1e999",
        ])
        self.assert_invalid([
            "text:str",
            "joined:str:hybrid=text + 'line\\nfeed'",
        ])

    def assert_invalid(self, definitions):
        with ExitStack() as stack:
            generators = [
                stack.enter_context(
                    patch.object(pipeline, f"generate_{kind}")
                )
                for kind in GENERATORS
            ]
            register = stack.enter_context(patch.object(Registry, "register"))
            with self.assertRaises(ValueError):
                pipeline.generate_module("Record", definitions)
            for generator in generators:
                generator.assert_not_called()
            register.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
