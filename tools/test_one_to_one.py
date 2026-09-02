"""Run python -m tools.test_one_to_one; no backend files are written."""

import importlib
import sys
import types
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base

from tools.core.engine import env
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.renderers.sqlalchemy_renderer import SQLAlchemyRenderer
from tools.validators.field_validator import FieldValidator

model_generator = importlib.import_module("tools.generate_model")


def generate_pair(key_type="int", nullable=False):
    base_module = types.ModuleType("backend.app.db.base")
    base_module.Base = declarative_base()
    namespace = {}
    sources = {}
    modifier = ":nullable" if nullable else ""
    definitions = {
        "User": [f"id:{key_type}:pk"],
        "Profile": [f"user_id:{key_type}:fk=users.id:one_to_one{modifier}"],
    }
    for name, field_strings in definitions.items():
        fields = parse_fields(name, field_strings)
        FieldValidator.validate(fields)
        module = ModuleDefinition(name, name, name.lower(), f"{name.lower()}s", fields)
        with patch.object(model_generator, "render_template") as render:
            model_generator.generate_model(module)
        context = dict(render.call_args.kwargs)
        template_name = context.pop("template_name")
        context.pop("output_path")
        source = env.get_template(template_name).render(**context)
        sources[name] = source
        with patch.dict(sys.modules, {"backend.app.db.base": base_module}):
            exec(compile(source, f"<generated-{name}>", "exec"), namespace)
    base_module.Base.registry.configure()
    return base_module.Base, namespace["User"], namespace["Profile"], sources


class OneToOneSmokeTest(unittest.TestCase):
    def test_generated_relationships(self):
        base, user, profile, sources = generate_pair()
        try:
            self.assertFalse(inspect(profile).relationships.user.uselist)
            self.assertFalse(inspect(user).relationships.profile.uselist)
            self.assertTrue(profile.user_id.unique)
            self.assertEqual(next(iter(profile.user_id.foreign_keys)).target_fullname, "users.id")
            self.assertIn("from sqlalchemy.orm import backref", sources["Profile"])
            self.assertNotIn("from sqlalchemy.orm import backref", sources["User"])
        finally:
            base.registry.dispose()

    def test_round_trip_and_unique_constraint(self):
        base, user, profile, _ = generate_pair()
        engine = create_engine("sqlite://")
        try:
            base.metadata.create_all(engine)
            with Session(engine) as session:
                owner = user(id=1)
                detail = profile(user=owner)
                session.add(detail)
                session.commit()
                session.expire_all()
                loaded_user = session.get(user, 1)
                self.assertIs(loaded_user.profile.user, loaded_user)
                self.assertEqual(loaded_user.profile.user_id, 1)
            with engine.begin() as connection:
                with self.assertRaises(IntegrityError):
                    connection.execute(profile.__table__.insert().values(user_id=1))
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_uuid_and_nullable(self):
        base, user, profile, _ = generate_pair("uuid", nullable=True)
        engine = create_engine("sqlite://")
        try:
            base.metadata.create_all(engine)
            self.assertTrue(profile.user_id.nullable)
            with Session(engine) as session:
                owner = user()
                detail = profile(user=owner)
                unlinked = profile()
                session.add_all([detail, unlinked])
                session.commit()
                self.assertEqual(detail.user_id, owner.id)
                self.assertIs(owner.profile, detail)
                self.assertIsNone(unlinked.user)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_modifier_order_and_existing_foreign_keys(self):
        first = parse_fields("Profile", ["user_id:int:fk=users.id:one_to_one"])[0]
        second = parse_fields("Profile", ["user_id:int:one_to_one:fk=users.id"])[0]
        self.assertEqual(first, second)
        self.assertEqual(first.backref, "profile")
        self.assertIsNone(first.back_populates)
        ordinary = parse_fields("Profile", ["user_id:int:fk=users.id"])[0]
        self.assertFalse(ordinary.unique)
        self.assertEqual(ordinary.relationship_type, "many_to_one")
        self.assertEqual(
            SQLAlchemyRenderer.render_relationship(ordinary),
            ['"User"', 'back_populates="profiles"'],
        )

    def test_invalid_one_to_one(self):
        for definition in (
            "user_id:int:one_to_one", "user_id:int:one_to_one:fk=",
            "user_id:int:one_to_one:fk=users", "user_id:int:one_to_one:fk=users.",
            "user_id:int:one_to_one:fk=.id", "user_id:array(int):fk=users.id:one_to_one",
            "user_id:json:fk=users.id:one_to_one",
        ):
            with self.subTest(definition=definition):
                with self.assertRaises(ValueError):
                    parse_fields("Profile", [definition])


if __name__ == "__main__":
    unittest.main(verbosity=2)
