"""Run python -m tools.test_constraints; generated models and databases stay in memory."""

from decimal import Decimal
import unittest
from unittest.mock import patch

from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from tools.core.constraint_parser import parse_check
from tools.registry.registry import Registry
from tools.test_composite_indexes import load_model, pipeline, run_generation


class ConstraintSmokeTest(unittest.TestCase):
    def test_unique_together_database_enforcement(self):
        sources, registry = run_generation([
            "tenant_id:int", "email:str:length=200", "unique_together(tenant_id,email)",
        ])
        model = load_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(model.__table__.insert(), [
                    {"tenant_id": 1, "email": "owner@example.com"},
                    {"tenant_id": 2, "email": "owner@example.com"},
                    {"tenant_id": 1, "email": "other@example.com"},
                ])
                with self.assertRaises(IntegrityError):
                    connection.execute(model.__table__.insert().values(tenant_id=1, email="owner@example.com"))
            self.assertEqual(registry["Record"]["unique_constraints"], [
                {"name": "uq_records_tenant_id_email", "columns": ["tenant_id", "email"]},
            ])
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_check_comparisons_enforced(self):
        sources, _ = run_generation([
            "price:decimal(10,2)", "minimum:int", "maximum:int",
            "check(price >= 0)", "check(maximum >= minimum)",
        ])
        model = load_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(model.__table__.insert().values(price=Decimal("12.50"), minimum=1, maximum=3))
                for values in (
                    {"price": Decimal("-1.00"), "minimum": 1, "maximum": 3},
                    {"price": Decimal("1.00"), "minimum": 3, "maximum": 1},
                ):
                    with self.assertRaises(IntegrityError):
                        connection.execute(model.__table__.insert().values(**values))
            ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
            self.assertIn('CHECK (("price" >= 0))', ddl)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_boolean_expressions_and_nulls(self):
        sources, _ = run_generation([
            "amount:int:nullable", "check(amount is not None and (amount >= 0 and amount <= 10))",
        ])
        model = load_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(model.__table__.insert().values(amount=5))
                for value in (None, -1, 11):
                    with self.assertRaises(IntegrityError):
                        connection.execute(model.__table__.insert().values(amount=value))
            expression = parse_check("not (amount < -2) or amount is None", {"amount"})
            self.assertIn("NOT", expression)
            self.assertIn("IS NULL", expression)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_literal_escaping_and_decimal_precision(self):
        sources, _ = run_generation(["title:str", 'check(title != "Owner\'s draft")'])
        model = load_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(model.__table__.insert().values(title="Published"))
                with self.assertRaises(IntegrityError):
                    connection.execute(model.__table__.insert().values(title="Owner's draft"))
            expression = parse_check("price >= 0.1234567890123456789012345", {"price"})
            self.assertIn("0.1234567890123456789012345", expression)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_composition_with_indexes_soft_delete_and_cli(self):
        sources, registry = run_generation([
            "tenant_id:int", "email:str", "price:decimal(10,2)", "soft_delete",
            "index(tenant_id,deleted_at)", "unique_together(tenant_id,email)", "check(price >= 0)",
        ], use_cli=True)
        model = load_model(sources["model.j2"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            self.assertEqual(sources["model.j2"].count("__table_args__"), 1)
            self.assertIn("ix_records_tenant_id_deleted_at", {item.name for item in model.__table__.indexes})
            self.assertTrue(any(isinstance(item, UniqueConstraint) for item in model.__table__.constraints))
            self.assertTrue(any(isinstance(item, CheckConstraint) for item in model.__table__.constraints))
            self.assertTrue(registry["Record"]["soft_delete"])
            self.assertEqual(len(registry["Record"]["check_constraints"]), 1)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_invalid_constraints_fail_before_writing(self):
        invalid = (
            "unique_together", "unique_together()", "unique_together(a)",
            "unique_together(a,)", "unique_together(a,a)", "unique_together(a,missing)",
            "check", "check()", "check(a >=)", "check(missing > 0)",
            "check(1 > 0)", "check(a == None)", "check(a is True)",
            "check(a > len('x'))", "check(a in [1,2])", "check(0 < a < 10)",
            "check(a.b > 0)", "check(a > 0); DROP TABLE records;", "check(a > float('inf'))",
        )
        definitions = [["a:int", "b:int", item] for item in invalid]
        definitions.extend([
            ["a:int", "b:int", "unique_together(a,b)", "unique_together(b,a)"],
            ["a:int", "check(a > 0)", "check(a>0)"],
            ["a:int", "roles:many_to_many(Role)", "unique_together(a,roles)"],
            ["roles:many_to_many(Role)", "check(roles > 0)"],
        ])
        for fields in definitions:
            with self.subTest(fields=fields):
                with patch.object(pipeline, "generate_model") as generate:
                    with patch.object(Registry, "register") as register:
                        with self.assertRaises(ValueError):
                            pipeline.generate_module("Record", fields)
                        generate.assert_not_called()
                        register.assert_not_called()

    def test_long_names_and_stable_check_names(self):
        first, second = "column_" + "a" * 40, "column_" + "b" * 40
        sources, registry = run_generation([
            f"{first}:int", f"{second}:int", f"unique_together({first},{second})", f"check({first} >= 0)",
        ])
        model = load_model(sources["model.j2"])
        try:
            for item in model.__table__.constraints:
                if item.name:
                    self.assertLessEqual(len(item.name.encode("utf-8")), 63)
            str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
            _, repeated = run_generation([f"{first}:int", f"check({first}>=0)"])
            self.assertEqual(registry["Record"]["check_constraints"], repeated["Record"]["check_constraints"])
        finally:
            model.registry.dispose()

    def test_no_constraints_preserves_existing_output(self):
        sources, registry = run_generation(["check:str", "unique_together:str"])
        self.assertNotIn("    CheckConstraint,", sources["model.j2"])
        self.assertNotIn("    UniqueConstraint,", sources["model.j2"])
        self.assertNotIn("__table_args__", sources["model.j2"])
        self.assertEqual(registry["Record"]["unique_constraints"], [])
        self.assertEqual(registry["Record"]["check_constraints"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
