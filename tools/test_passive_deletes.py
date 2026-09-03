"""Verify database-delegated deletes and emitted SQL using generated models."""
from contextlib import contextmanager
import importlib
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import event, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.registry.registry import Registry
from tools.test_composite_indexes import pipeline
from tools.test_one_to_many import database, generate_models
from tools.test_soft_delete import load_generated
from tools.test_validators import schemas


@contextmanager
def capture_sql(engine):
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.upper().split()))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", capture)


class PassiveDeleteSmokeTest(unittest.TestCase):
    def build(self, definitions):
        base, models, sources, registry = generate_models(definitions)
        self.addCleanup(base.registry.dispose)
        engine = database(base)
        self.addCleanup(engine.dispose)
        return models, sources, registry, engine

    def test_unloaded_collection_uses_only_parent_delete(self):
        models, sources, _, engine = self.build({
            "User": [], "Post": ["user_id:int:fk=users.id:one_to_many:cascade_delete:passive_deletes"],
        })
        user, post = models["User"], models["Post"]
        relation = inspect(user).relationships.posts
        self.assertTrue(relation.passive_deletes)
        self.assertTrue(relation.cascade.delete)
        self.assertFalse(relation.cascade.delete_orphan)
        self.assertFalse(inspect(post).relationships.user.passive_deletes)
        self.assertFalse(inspect(post).relationships.user.cascade.delete)
        ddl = str(CreateTable(post.__table__).compile(dialect=postgresql.dialect()))
        self.assertIn("REFERENCES users (id) ON DELETE CASCADE", ddl)
        self.assertIn("passive_deletes=True", sources["Post"]["model.j2"])
        with Session(engine) as session:
            session.add_all([user(id=1, posts=[post(), post()]), user(id=2, posts=[post()])])
            session.commit()
        with Session(engine) as session:
            parent = session.get(user, 1)
            self.assertNotIn("posts", parent.__dict__)
            with capture_sql(engine) as statements:
                session.delete(parent)
                session.flush()
            self.assertEqual(len(statements), 1, statements)
            self.assertTrue(statements[0].startswith("DELETE FROM USERS "), statements)
            session.commit()
        with Session(engine) as session:
            self.assertIsNone(session.get(user, 1))
            self.assertEqual([item.user_id for item in session.scalars(select(post))], [2])

    def test_loaded_collection_deletes_children_and_updates_session(self):
        models, _, _, engine = self.build({
            "User": [], "Post": ["user_id:int:fk=users.id:one_to_many:cascade_delete:passive_deletes"],
        })
        user, post = models["User"], models["Post"]
        with Session(engine) as session:
            session.add(user(id=1, posts=[post(), post()]))
            session.commit()
        with Session(engine) as session:
            parent = session.get(user, 1)
            children = list(parent.posts)
            with capture_sql(engine) as statements:
                session.delete(parent)
                session.flush()
            self.assertTrue(all(inspect(child).deleted for child in children))
            self.assertFalse(any(sql.startswith(("SELECT ", "UPDATE ")) for sql in statements), statements)
            self.assertTrue(any(sql.startswith("DELETE FROM POSTS ") for sql in statements), statements)
            self.assertTrue(any(sql.startswith("DELETE FROM USERS ") for sql in statements), statements)
            session.commit()
        with Session(engine) as session:
            self.assertEqual(session.scalars(select(post)).all(), [])

    def test_one_to_one_unloaded_and_child_delete_direction(self):
        models, _, _, engine = self.build({
            "User": [], "Profile": ["user_id:int:fk=users.id:one_to_one:cascade_delete:passive_deletes"],
        })
        user, profile = models["User"], models["Profile"]
        self.assertFalse(inspect(user).relationships.profile.uselist)
        self.assertTrue(inspect(user).relationships.profile.passive_deletes)
        with Session(engine) as session:
            session.add_all([user(id=1, profile=profile(id=1)), user(id=2, profile=profile(id=2))])
            session.commit()
        with Session(engine) as session:
            parent = session.get(user, 1)
            self.assertNotIn("profile", parent.__dict__)
            with capture_sql(engine) as statements:
                session.delete(parent)
                session.flush()
            self.assertEqual(len(statements), 1, statements)
            self.assertTrue(statements[0].startswith("DELETE FROM USERS "), statements)
            session.commit()
            session.delete(session.get(profile, 2))
            session.commit()
            self.assertIsNotNone(session.get(user, 2))
            self.assertEqual(session.scalars(select(profile)).all(), [])

    def test_self_hierarchy_uses_database_for_unloaded_descendants(self):
        models, _, _, engine = self.build({"Node": [
            "parent_id:int:nullable:fk=nodes.id:self_relationship:cascade_delete:passive_deletes",
        ]})
        node = models["Node"]
        self.assertTrue(inspect(node).relationships.children.passive_deletes)
        self.assertFalse(inspect(node).relationships.parent.passive_deletes)
        with Session(engine) as session:
            session.add_all([node(id=1, children=[node(id=2, children=[node(id=3)])]), node(id=9)])
            session.commit()
        with Session(engine) as session:
            root = session.get(node, 1)
            with capture_sql(engine) as statements:
                session.delete(root)
                session.flush()
            self.assertEqual(len(statements), 1, statements)
            self.assertTrue(statements[0].startswith("DELETE FROM NODES "), statements)
            session.commit()
        with Session(engine) as session:
            self.assertEqual(session.scalars(select(node.id)).all(), [9])

    def test_uuid_and_string_custom_keys(self):
        for kind, key in (("uuid", uuid4()), ("str", "owner-key")):
            with self.subTest(kind=kind):
                models, _, _, engine = self.build({
                    "User": [f"identifier:{kind}:pk"],
                    "Post": [f"owner_id:{kind}:fk=users.identifier:one_to_many(User,posts):cascade_delete:passive_deletes"],
                })
                user, post = models["User"], models["Post"]
                with Session(engine) as session:
                    session.add(user(identifier=key, posts=[post(), post()]))
                    session.commit()
                with Session(engine) as session:
                    parent = session.get(user, key)
                    with capture_sql(engine) as statements:
                        session.delete(parent)
                        session.flush()
                    self.assertEqual(len(statements), 1, statements)
                    self.assertTrue(statements[0].startswith("DELETE FROM USERS "), statements)
                    session.commit()
                    self.assertEqual(session.scalars(select(post)).all(), [])

    def test_detachment_and_reparenting_keep_rows(self):
        models, _, _, engine = self.build({
            "User": [], "Post": ["user_id:int:nullable:fk=users.id:one_to_many:cascade_delete:passive_deletes"],
        })
        user, post = models["User"], models["Post"]
        with Session(engine) as session:
            child = post(id=1)
            first, second = user(id=1, posts=[child]), user(id=2)
            session.add_all([first, second])
            session.commit()
            first.posts.remove(child)
            session.commit()
            self.assertIsNone(child.user_id)
            self.assertIsNotNone(session.get(post, 1))
            second.posts.append(child)
            session.commit()
            session.delete(first)
            session.commit()
            self.assertEqual(session.get(post, 1).user_id, 2)

    def test_blocking_child_dependency_rolls_back(self):
        models, _, _, engine = self.build({
            "User": [], "Post": ["user_id:int:fk=users.id:one_to_many:cascade_delete:passive_deletes"],
            "Audit": ["post_id:int:fk=posts.id:one_to_many"],
        })
        user, post, audit = models["User"], models["Post"], models["Audit"]
        with Session(engine) as session:
            session.add(user(id=1, posts=[post(id=1, audits=[audit(id=1)])]))
            session.commit()
        with Session(engine) as session:
            parent = session.get(user, 1)
            self.assertNotIn("posts", parent.__dict__)
            with self.assertRaises(IntegrityError):
                session.delete(parent)
                session.commit()
            session.rollback()
            self.assertIsNotNone(session.get(user, 1))
            self.assertIsNotNone(session.get(post, 1))
            self.assertIsNotNone(session.get(audit, 1))

    def test_soft_delete_and_restore_do_not_delete_children(self):
        model, crud_type, _, _ = load_generated([
            "parent_id:int:nullable:fk=records.id:self_relationship:cascade_delete:passive_deletes", "soft_delete",
        ])
        self.addCleanup(model.registry.dispose)
        engine = database(model.__bases__[0])
        self.addCleanup(engine.dispose)
        with Session(engine) as session:
            session.add(model(id=1, children=[model(id=2)]))
            session.commit()
            crud = crud_type(session)
            crud.delete(1)
            self.assertIsNone(crud.get(1))
            self.assertIsNone(crud.get(2).deleted_at)
            self.assertEqual(crud.get(2).parent_id, 1)
            crud.restore(1)
            self.assertIsNone(crud.get(1).deleted_at)
            self.assertEqual(len(crud.list()), 2)

    def test_cli_metadata_schemas_and_order(self):
        definition = "parent_id:int:nullable:fk=records.id:self_relationship:cascade_delete:passive_deletes"
        ns, sources, registry = schemas([
            definition, "quantity:int:min=1", "double:int:computed=quantity * 2",
            "index(parent_id,double)", "check(double >= 0)", "soft_delete",
        ], use_cli=True)
        fields = json.loads(json.dumps(registry))["Record"]["fields"]
        self.assertTrue(fields[0]["passive_deletes"])
        self.assertTrue(fields[0]["cascade_delete"])
        self.assertFalse(fields[1]["passive_deletes"])
        self.assertIn("passive_deletes=True", sources["model.j2"])
        self.assertEqual(ns["RecordCreate"](quantity=2).parent_id, None)
        self.assertNotIn("passive_deletes", ns["RecordCreate"].model_fields)
        self.assertEqual(ns["RecordUpdate"](parent_id=None).model_dump(exclude_unset=True), {"parent_id": None})
        reordered = "parent_id:int:passive_deletes:nullable:cascade_delete:self_relationship:fk=records.id"
        self.assertEqual(parse_fields("Record", [definition]), parse_fields("Record", [reordered]))

    def test_invalid_flags_fail_before_writing(self):
        prefix = "user_id:int:fk=users.id:one_to_many:cascade_delete"
        invalid = (
            "value:int:passive_deletes", "user_id:int:fk=users.id:passive_deletes",
            "user_id:int:fk=users.id:one_to_many:passive_deletes",
            "user_id:int:fk=users.id:one_to_one:passive_deletes",
            "parent_id:int:fk=records.id:self_relationship:passive_deletes",
            "user_id:int:fk=users.id:cascade_delete:passive_deletes",
            prefix + ":passive_deletes:passive_deletes", prefix + ":passive_deletes=all",
            prefix + ":passive_deletes=True", prefix + ":passive_deletes=False",
            prefix + ":passive_deletes()", prefix + ":passive_deletes(all)",
            "roles:many_to_many(Role):passive_deletes", "value:array(int):cascade_delete:passive_deletes",
        )
        for definition in invalid:
            with self.subTest(definition=definition):
                with patch.object(pipeline, "generate_model") as model, patch.object(Registry, "register") as register:
                    with self.assertRaises(ValueError):
                        pipeline.generate_module("Record", [definition])
                    model.assert_not_called()
                    register.assert_not_called()
        generator = importlib.import_module("tools.generate_model")
        fields = parse_fields("Post", ["user_id:int:fk=users.id:one_to_many"])
        fields[0].passive_deletes = True
        module = ModuleDefinition(name="Post", class_name="Post", module_name="post", table_name="posts", fields=fields)
        with patch.object(generator, "render_template") as render:
            with self.assertRaisesRegex(ValueError, "requires cascade_delete"):
                generator.generate_model(module)
            render.assert_not_called()

    def test_absent_option_keeps_orm_loading_behavior(self):
        models, sources, registry, engine = self.build({
            "User": [], "Post": ["user_id:int:fk=users.id:one_to_many:cascade_delete"],
        })
        user, post = models["User"], models["Post"]
        self.assertFalse(inspect(user).relationships.posts.passive_deletes)
        self.assertFalse(registry["Post"]["fields"][0]["passive_deletes"])
        self.assertNotIn("passive_deletes=", sources["Post"]["model.j2"])
        with Session(engine) as session:
            session.add(user(id=1, posts=[post()]))
            session.commit()
        with Session(engine) as session:
            parent = session.get(user, 1)
            with capture_sql(engine) as statements:
                session.delete(parent)
                session.flush()
            self.assertTrue(any(sql.startswith("SELECT ") and "FROM POSTS" in sql for sql in statements), statements)
            self.assertTrue(any(sql.startswith("DELETE FROM POSTS ") for sql in statements), statements)
            session.commit()
            self.assertEqual(session.scalars(select(post)).all(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
