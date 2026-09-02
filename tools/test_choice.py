"""Run python -m tools.test_choice; generated models stay in memory."""

import unittest

from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from tools.core.field_parser import parse_fields
from tools.test_array import render_model


class ChoiceSmokeTest(unittest.TestCase):
    def test_choice_generation(self):
        source, model, ddl = render_model(["status:choice(Draft,Published)"])
        self.assertIn("Enum as SQLEnum", source)
        self.assertNotIn("from enum import Enum", source)
        self.assertEqual(model.status.type.enums, ["Draft", "Published"])
        self.assertFalse(model.status.type.native_enum)
        self.assertTrue(model.status.type.validate_strings)
        self.assertIn("CHECK (status IN ('Draft', 'Published'))", ddl)

    def test_values_round_trip_and_enforcement(self):
        _, model, _ = render_model(["status:choice(Draft,Published)"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(model.__table__.insert(), [
                    {"status": "Draft"}, {"status": "Published"},
                ])
                self.assertEqual(
                    connection.execute(select(model.status).order_by(model.id)).scalars().all(),
                    ["Draft", "Published"],
                )
                with self.assertRaises(StatementError):
                    connection.execute(model.__table__.insert().values(status="Other"))
                # Bypass SQLAlchemy's validation to verify the database constraint.
                with self.assertRaises(IntegrityError):
                    connection.execute(text("INSERT INTO samples (status) VALUES ('Other')"))
        finally:
            engine.dispose()

    def test_modifiers_and_escaping(self):
        _, model, _ = render_model([
            "status:choice(Draft, Published):nullable:index:unique:default='Draft'",
        ])
        self.assertTrue(model.status.nullable)
        self.assertTrue(model.status.index)
        self.assertTrue(model.status.unique)
        self.assertEqual(model.status.default.arg, "Draft")
        _, escaped, _ = render_model(["status:choice(Owner's draft,Ready to publish)"])
        self.assertEqual(escaped.status.type.enums, ["Owner's draft", "Ready to publish"])

    def test_invalid_choices(self):
        for definition in (
            "status:choice", "status:choice()", "status:choice( )",
            "status:choice(Draft,)", "status:choice(,Draft)",
            "status:choice(Draft,Draft)", "status:choice(Draft",
            "status:choice(Draft))", "status:choice(array(str))",
            "status:array(choice)",
        ):
            with self.subTest(definition=definition):
                with self.assertRaises(ValueError):
                    parse_fields("Sample", [definition])

    def test_choice_and_enum_coexist(self):
        _, model, ddl = render_model([
            "status:choice(Draft,Published)", "priority:enum(low,high)",
            "tags:array(str)", "price:decimal(10,2)", "metadata_value:json",
            "identifier:uuid:pk",
        ])
        self.assertEqual(model.status.type.enums, ["Draft", "Published"])
        self.assertEqual(model.priority.type.enums, ["LOW", "HIGH"])
        self.assertIn("tags VARCHAR[]", ddl)


if __name__ == "__main__":
    unittest.main(verbosity=2)
