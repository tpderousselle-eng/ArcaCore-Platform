"""Computed-column smoke tests; generated files and databases stay in memory."""
from decimal import Decimal
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from tools.core.field_parser import parse_fields
from tools.registry.registry import Registry
from tools.test_composite_indexes import load_model as load_test_model, pipeline
from tools.test_soft_delete import load_generated
from tools.test_validators import schemas


def load_model(source):
    model = load_test_model(source)
    # The older exec fixture assigns 'builtins'. Use a normal module identity so
    # Pydantic treats the fixture like a model imported from a generated file.
    model.__module__ = "generated_computed_model"
    return model


class ComputedSmokeTest(unittest.TestCase):
    def test_database_recalculates_insert_and_update(self):
        ns, sources, _ = schemas([
            "quantity:int:min=1", "price:decimal(12,2):min=0",
            "total:decimal(14,2):computed=quantity * price",
        ])
        model = load_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with Session(engine) as session:
                payload = ns["RecordCreate"](quantity=3, price="12.50")
                row = model(**payload.model_dump(exclude_unset=True))
                session.add(row)
                session.commit()
                session.refresh(row)
                self.assertEqual(row.total, Decimal("37.50"))
                self.assertEqual(ns["RecordResponse"].model_validate(row).total, Decimal("37.50"))
                changes = ns["RecordUpdate"](quantity=4).model_dump(exclude_unset=True)
                for name, value in changes.items():
                    setattr(row, name, value)
                session.commit()
                session.refresh(row)
                self.assertEqual(row.total, Decimal("50.00"))
                self.assertEqual(session.scalar(select(model.total)), Decimal("50.00"))
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_computed_is_read_only_in_schemas_and_database(self):
        ns, sources, _ = schemas(["amount:int", "total:int:computed=amount * 2"])
        for class_name in ("RecordCreate", "RecordUpdate"):
            schema = ns[class_name]
            self.assertNotIn("total", schema.model_fields)
            self.assertNotIn("total", schema.model_json_schema()["properties"])
            for value in (9, None):
                with self.subTest(class_name=class_name, value=value), self.assertRaises(ValidationError):
                    schema(amount=2, total=value)
        self.assertEqual(ns["RecordUpdate"]().model_dump(exclude_unset=True), {})
        self.assertTrue(ns["RecordResponse"].model_json_schema()["properties"]["total"]["readOnly"])
        with self.assertRaises(ValidationError):
            ns["RecordResponse"](id=1, amount=2)
        model = load_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(model.__table__.insert().values(amount=2))
                with self.assertRaises(DBAPIError):
                    connection.execute(update(model).values(total=99))
                with self.assertRaises(DBAPIError):
                    connection.execute(model.__table__.insert().values(amount=2, total=99))
                self.assertEqual(connection.scalar(select(model.total)), 4)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_precedence_unary_operators_float_and_forward_references(self):
        ns, sources, _ = schemas([
            "total:int:computed=-(a + 2) * +b - 1", "a:int", "b:int",
            "ratio:float", "adjusted:float:computed=ratio * 1.5 + a",
        ])
        model = load_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with Session(engine) as session:
                row = model(a=3, b=4, ratio=0.5)
                session.add(row)
                session.commit()
                self.assertEqual(row.total, -21)
                self.assertEqual(row.adjusted, 3.75)
                self.assertEqual(ns["RecordResponse"].model_validate(row).total, -21)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_nullable_computed_result(self):
        ns, sources, _ = schemas(["amount:int:nullable", "total:int:nullable:computed=amount * 2"])
        model = load_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with Session(engine) as session:
                row = model(amount=None)
                session.add(row)
                session.commit()
                self.assertIsNone(ns["RecordResponse"].model_validate(row).total)
                row.amount = 3
                session.commit()
                self.assertEqual(row.total, 6)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_invalid_expressions_fail_before_generation(self):
        expressions = (
            "", "missing + 1", "total + 1", "amount / 2", "amount // 2", "amount % 2",
            "amount ** 2", "abs(amount)", "amount.real", "amount[0]", "amount if amount else 0",
            "amount > 0", "amount + True", "amount + None", "amount + 'x'", "1 + 2",
            "amount + 0x10", "amount + 1e999", "amount + 0.5", "amount + 1e2",
            "amount; DROP TABLE records", "__import__('os').system('false')", "(amount + 1",
            "amount + " + "+".join(["1"] * 100),
        )
        for expression in expressions:
            with self.subTest(expression=expression):
                self.assert_invalid(["amount:int", f"total:int:computed={expression}"])
        self.assert_invalid(["amount:int", "total:int:computed=amount:computed=amount+1"])

    def test_invalid_types_references_and_modifiers(self):
        cases = (
            ["amount:int", "total:str:computed=amount"],
            ["amount:str", "total:int:computed=amount"],
            ["amount:float", "total:int:computed=amount"],
            ["amount:int:nullable", "total:int:computed=amount"],
            ["roles:many_to_many(Role)", "total:int:computed=roles"],
            ["amount:int", "total:int:computed=amount:default=1"],
            ["amount:int", "total:int:pk:computed=amount"],
            ["amount:int", "total:int:fk=users.id:computed=amount"],
            ["amount:int", "total:int:computed=amount", "other:int:computed=total+1"],
            ["first:int:computed=second", "second:int:computed=first"],
            ["amount:int", "id:int:computed=amount"],
            ["amount:int", "created_at:int:computed=amount"],
            ["amount:int", "total:decimal():computed=amount"],
            ["amount:int", "total:decimal(1,2):computed=amount"],
        )
        for definitions in cases:
            with self.subTest(definitions=definitions):
                self.assert_invalid(definitions)

    def assert_invalid(self, definitions):
        with patch.object(pipeline, "generate_model") as model, patch.object(Registry, "register") as register:
            with self.assertRaises(ValueError):
                pipeline.generate_module("Record", definitions)
            model.assert_not_called()
            register.assert_not_called()

    def test_cli_registry_indexes_constraints_and_soft_delete(self):
        definitions = [
            "identifier:uuid:pk", "tenant:int", "quantity:int:min=1", "price:decimal(8,2)",
            "total:decimal(10,2):index:computed=quantity * price", "index(tenant,total)",
            "unique_together(tenant,total)", "check(total >= 0)", "soft_delete",
        ]
        ns, sources, registry = schemas(definitions, use_cli=True)
        metadata = json.loads(json.dumps(registry))["Record"]["fields"][-1]
        self.assertEqual(metadata["computed"], "quantity * price")
        self.assertEqual(metadata["computed_sql"], '("quantity" * "price")')
        self.assertNotIn("id", ns["RecordResponse"].model_fields)
        model, crud, service, _ = load_generated(definitions)
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            indexes = {item["name"] for item in inspect(engine).get_indexes("records")}
            self.assertIn("ix_records_tenant_total", indexes)
            self.assertIn("ix_records_total", indexes)
            with Session(engine) as session:
                key = uuid4()
                session.add(model(identifier=key, tenant=1, quantity=2, price=Decimal("5")))
                session.commit()
                row = service(session).delete(key)
                self.assertEqual(row.total, Decimal("10.00"))
                self.assertIsNone(service(session).get(key))
                self.assertEqual(service(session).restore(key).total, Decimal("10.00"))
                session.add(model(identifier=uuid4(), tenant=1, quantity=1, price=Decimal("10")))
                with self.assertRaises(IntegrityError):
                    session.commit()
                session.rollback()
                session.add(model(identifier=uuid4(), tenant=2, quantity=1, price=Decimal("-1")))
                with self.assertRaises(IntegrityError):
                    session.commit()
                session.rollback()
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_postgresql_ddl_and_exact_literal_rendering(self):
        _, sources, _ = schemas([
            "order:decimal(24,18)", "total:decimal(24,18):computed=order + 0.100000000000000001",
        ])
        model = load_model(sources["model.j2"])
        try:
            column = model.__table__.c.total
            self.assertTrue(column.computed.persisted)
            sql = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
            self.assertIn("GENERATED ALWAYS AS", sql)
            self.assertIn("STORED", sql)
            self.assertIn('"order" + 0.100000000000000001', sql)
            self.assertIn("NOT NULL", sql)
            fields = parse_fields("Record", ["a:int", "total:int:computed= a + 2 "])
            self.assertEqual(fields[-1].computed_sql, '("a" + 2)')
        finally:
            model.registry.dispose()

    def test_models_without_computed_fields(self):
        ns, sources, registry = schemas(["name:str:length=40", "amount:int:min=1"])
        self.assertNotIn("Computed", sources["model.j2"])
        self.assertNotIn("_reject_computed_input", sources["schema.j2"])
        self.assertEqual(ns["RecordCreate"](name="Tyler", amount=1).amount, 1)
        self.assertEqual(ns["RecordUpdate"]().model_dump(exclude_unset=True), {})
        self.assertIsNone(registry["Record"]["fields"][0]["computed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
