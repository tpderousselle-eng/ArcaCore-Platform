"""Run python -m tools.test_many_to_many; model and database tests stay in memory."""

import importlib
import sys
import types
import unittest
from unittest.mock import patch

from sqlalchemy import UUID, create_engine, func, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.schema import CreateTable

from tools.core.engine import env
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.registry.registry import Registry
from tools.validators.field_validator import FieldValidator

model_generator = importlib.import_module("tools.generate_model")


def make_module(name, definitions):
    fields = parse_fields(name, definitions)
    FieldValidator.validate(fields)
    return ModuleDefinition(name, name.capitalize(), name.lower(), f"{name.lower()}s", fields)


def generate_pair(uuid_keys=False):
    base_module = types.ModuleType("backend.app.db.base")
    base_module.Base = declarative_base()
    namespace = {}
    sources = {}
    if uuid_keys:
        definitions = {
            "User": ["identifier:uuid:pk", "roles:many_to_many(Role,roles.identifier)"],
            "Role": ["identifier:uuid:pk"],
        }
    else:
        definitions = {"User": ["roles:many_to_many(Role)"], "Role": ["name:str"]}
    for name, fields in definitions.items():
        module = make_module(name, fields)
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
    return base_module.Base, namespace["User"], namespace["Role"], sources


class ManyToManySmokeTest(unittest.TestCase):
    def test_association_and_collections(self):
        base, user, role, sources = generate_pair()
        try:
            association = base.metadata.tables["user_roles"]
            self.assertEqual(list(association.primary_key.columns.keys()), ["source_id", "target_id"])
            self.assertEqual(
                {fk.target_fullname for fk in association.foreign_keys}, {"users.id", "roles.id"}
            )
            self.assertNotIn("roles", user.__table__.c)
            self.assertTrue(inspect(user).relationships.roles.uselist)
            self.assertTrue(inspect(role).relationships.users.uselist)
            self.assertNotIn("    Table,", sources["Role"])
            ddl = str(CreateTable(association).compile(dialect=postgresql.dialect()))
            self.assertIn("PRIMARY KEY (source_id, target_id)", ddl)
        finally:
            base.registry.dispose()

    def test_round_trip_remove_and_delete(self):
        base, user, role, _ = generate_pair()
        engine = create_engine("sqlite://")
        try:
            base.metadata.create_all(engine)
            with Session(engine) as session:
                admin, reader = role(name="admin"), role(name="reader")
                first, second = user(roles=[admin, reader]), user(roles=[reader])
                session.add_all([first, second])
                session.commit()
                session.expire_all()
                self.assertEqual({item.name for item in first.roles}, {"admin", "reader"})
                self.assertEqual(len(reader.users), 2)
                first.roles.remove(reader)
                session.commit()
                self.assertEqual(reader.users, [second])
                session.delete(second)
                session.commit()
                self.assertEqual(reader.users, [])
                self.assertEqual(session.scalar(select(func.count()).select_from(role)), 2)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_duplicate_and_invalid_links_rejected(self):
        base, user, role, _ = generate_pair()
        engine = create_engine("sqlite://")
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()
            base.metadata.create_all(engine)
            association = base.metadata.tables["user_roles"]
            with engine.begin() as connection:
                connection.execute(user.__table__.insert().values(id=1))
                connection.execute(role.__table__.insert().values(id=1, name="reader"))
                connection.execute(association.insert().values(source_id=1, target_id=1))
                with self.assertRaises(IntegrityError):
                    connection.execute(association.insert().values(source_id=1, target_id=1))
                with self.assertRaises(IntegrityError):
                    connection.execute(association.insert().values(source_id=1, target_id=999))
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_uuid_custom_keys(self):
        base, user, role, _ = generate_pair(uuid_keys=True)
        engine = create_engine("sqlite://")
        try:
            association = base.metadata.tables["user_roles"]
            self.assertIsInstance(association.c.source_id.type, UUID)
            self.assertIsInstance(association.c.target_id.type, UUID)
            base.metadata.create_all(engine)
            with Session(engine) as session:
                owner = user(roles=[role()])
                session.add(owner)
                session.commit()
                session.expire_all()
                self.assertEqual(owner.roles[0].users, [owner])
                self.assertIsNotNone(owner.identifier)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_invalid_dsl(self):
        for definition in (
            "roles:many_to_many", "roles:many_to_many()", "roles:many_to_many(Role,)",
            "roles:many_to_many(Role,roles.id,extra)", "roles:many_to_many(Role,roles)",
            "roles:many_to_many(Role,roles.)", "roles:many_to_many(Role):pk",
            "roles:many_to_many(Role):fk=roles.id", "roles:many_to_many(Role):one_to_one",
            "roles:many_to_many(User)", "roles:many_to_many(class)",
            "roles:many_to_many(Role())", "roles:array(many_to_many)",
        ):
            with self.subTest(definition=definition):
                with self.assertRaises(ValueError):
                    parse_fields("User", [definition])

    def test_unsupported_configurations_fail_before_writing(self):
        for fields in (
            ["first:int:pk", "second:int:pk", "roles:many_to_many(Role)"],
            ["roles:many_to_many(Role)", "other_roles:many_to_many(Role)"],
        ):
            with self.subTest(fields=fields):
                with patch.object(model_generator, "render_template") as render:
                    with self.assertRaises(ValueError):
                        model_generator.generate_model(make_module("User", fields))
                    render.assert_not_called()

    def test_registry_preserves_relationship_metadata(self):
        module = make_module("User", ["roles:many_to_many(Role,roles.identifier)"])
        existing = {"Role": {"table": "roles", "fields": []}}
        with patch.object(Registry, "load", return_value=existing):
            with patch.object(Registry, "save") as save:
                Registry.register(module)
        registered = save.call_args.args[0]
        field = registered["User"]["fields"][0]
        self.assertEqual(field["association_table"], "user_roles")
        self.assertEqual(field["relationship_table"], "roles")
        self.assertEqual(field["relationship_key"], "identifier")
        self.assertEqual(field["backref"], "users")
        self.assertIn("Role", registered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
