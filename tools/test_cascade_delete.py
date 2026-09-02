"""Verify generated hard-delete cascades without writing backend files."""
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from tools.core.field_parser import parse_fields
from tools.registry.registry import Registry
from tools.renderers.sqlalchemy_renderer import SQLAlchemyRenderer
from tools.test_composite_indexes import pipeline
from tools.test_one_to_many import database, generate_models
from tools.test_soft_delete import load_generated
from tools.test_validators import schemas


class CascadeDeleteSmokeTest(unittest.TestCase):
    def build(self, definitions):
        base, models, sources, registry = generate_models(definitions)
        self.addCleanup(base.registry.dispose)
        engine = database(base)
        self.addCleanup(engine.dispose)
        return base, models, sources, registry, engine

    def test_mapping_direction_and_postgresql_ddl(self):
        _, models, sources, _, _ = self.build({
            "User": [], "Post": ["user_id:int:fk=users.id:one_to_many:cascade_delete"],
        })
        user, post = models["User"], models["Post"]
        self.assertTrue(inspect(user).relationships.posts.cascade.delete)
        self.assertFalse(inspect(post).relationships.user.cascade.delete)
        self.assertFalse(inspect(user).relationships.posts.cascade.delete_orphan)
        self.assertFalse(inspect(user).relationships.posts.passive_deletes)
        self.assertFalse(inspect(post).relationships.user.uselist)
        self.assertTrue(inspect(user).relationships.posts.uselist)
        foreign_key = next(iter(post.__table__.c.user_id.foreign_keys))
        self.assertEqual(foreign_key.ondelete, "CASCADE")
        ddl = str(CreateTable(post.__table__).compile(dialect=postgresql.dialect()))
        self.assertIn("REFERENCES users (id) ON DELETE CASCADE", ddl)
        self.assertIn("from sqlalchemy.orm import backref", sources["Post"]["model.j2"])

    def test_orm_loaded_and_unloaded_children_and_direction(self):
        for loaded in (False, True):
            with self.subTest(loaded=loaded):
                _, models, _, _, engine = self.build({
                    "User": [], "Post": ["user_id:int:fk=users.id:one_to_many:cascade_delete"],
                })
                user, post = models["User"], models["Post"]
                with Session(engine) as session:
                    parent = user(posts=[post(), post()])
                    survivor = user(posts=[post()])
                    session.add_all([parent, survivor])
                    session.commit()
                    parent_id, survivor_id = parent.id, survivor.id
                    session.delete(parent.posts[0])
                    session.commit()
                    self.assertIsNotNone(session.get(user, parent_id))
                with Session(engine) as session:
                    parent = session.get(user, parent_id)
                    self.assertNotIn("posts", parent.__dict__)
                    if loaded:
                        self.assertEqual(len(parent.posts), 1)
                    session.delete(parent)
                    session.commit()
                with Session(engine) as session:
                    self.assertIsNone(session.get(user, parent_id))
                    self.assertEqual([item.id for item in session.scalars(select(user))], [survivor_id])
                    self.assertEqual([item.user_id for item in session.scalars(select(post))], [survivor_id])

    def test_database_delete_without_orm(self):
        _, models, _, _, engine = self.build({
            "User": [], "Post": ["user_id:int:fk=users.id:one_to_many:cascade_delete"],
        })
        user, post = models["User"], models["Post"]
        with Session(engine) as session:
            session.add_all([user(id=1, posts=[post(), post()]), user(id=2, posts=[post()])])
            session.commit()
        with engine.begin() as connection:
            connection.execute(delete(user.__table__).where(user.__table__.c.id == 1))
        with Session(engine) as session:
            self.assertIsNone(session.get(user, 1))
            self.assertEqual([item.user_id for item in session.scalars(select(post))], [2])

    def test_one_to_one_parent_delete_and_child_delete(self):
        _, models, _, _, engine = self.build({
            "User": [], "Profile": ["user_id:int:fk=users.id:one_to_one:cascade_delete"],
        })
        user, profile = models["User"], models["Profile"]
        self.assertFalse(inspect(user).relationships.profile.uselist)
        self.assertTrue(inspect(user).relationships.profile.cascade.delete)
        self.assertFalse(inspect(profile).relationships.user.cascade.delete)
        with Session(engine) as session:
            first, second = user(id=1, profile=profile()), user(id=2, profile=profile())
            session.add_all([first, second])
            session.commit()
            session.delete(first.profile)
            session.commit()
            self.assertIsNotNone(session.get(user, 1))
            session.delete(second)
            session.commit()
            self.assertEqual(session.scalars(select(profile)).all(), [])
            self.assertIsNotNone(session.get(user, 1))

    def test_self_subtree_deletion_orm_and_database(self):
        for mode in ("orm", "database"):
            with self.subTest(mode=mode):
                _, models, _, _, engine = self.build({"Node": [
                    "parent_id:int:nullable:fk=nodes.id:self_relationship:cascade_delete",
                ]})
                node = models["Node"]
                with Session(engine) as session:
                    root = node(id=1, children=[node(id=2, children=[node(id=3)]), node(id=4)])
                    session.add(root)
                    session.commit()
                if mode == "orm":
                    with Session(engine) as session:
                        session.delete(session.get(node, 2))
                        session.commit()
                else:
                    with engine.begin() as connection:
                        connection.execute(delete(node.__table__).where(node.__table__.c.id == 2))
                with Session(engine) as session:
                    self.assertEqual(session.scalars(select(node.id).order_by(node.id)).all(), [1, 4])
                    self.assertEqual(session.get(node, 1).children[0].id, 4)

    def test_uuid_and_string_custom_keys(self):
        for field_type, key in (("uuid", uuid4()), ("str", "owner-key")):
            with self.subTest(field_type=field_type):
                _, models, _, _, engine = self.build({
                    "User": [f"identifier:{field_type}:pk"],
                    "Post": [f"owner_id:{field_type}:fk=users.identifier:one_to_many(User,posts):cascade_delete"],
                })
                user, post = models["User"], models["Post"]
                with Session(engine) as session:
                    session.add(user(identifier=key, posts=[post(), post()]))
                    session.commit()
                with Session(engine) as session:
                    session.delete(session.get(user, key))
                    session.commit()
                    self.assertEqual(session.scalars(select(post)).all(), [])

    def test_detachment_and_reparenting_do_not_delete_orphans(self):
        _, models, _, _, engine = self.build({
            "User": [], "Post": ["user_id:int:nullable:fk=users.id:one_to_many:cascade_delete"],
        })
        user, post = models["User"], models["Post"]
        with Session(engine) as session:
            child = post(id=1)
            first, second = user(posts=[child]), user()
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
            self.assertEqual(child.user_id, second.id)
            session.delete(second)
            session.commit()
            self.assertIsNone(session.get(post, 1))

    def test_only_selected_foreign_key_cascades(self):
        _, models, _, _, engine = self.build({
            "User": [], "Post": [
                "author_id:int:fk=users.id:one_to_many(User,authored):cascade_delete",
                "reviewer_id:int:nullable:fk=users.id:one_to_many(User,reviewed)",
            ],
        })
        user, post = models["User"], models["Post"]
        self.assertFalse(inspect(user).relationships.reviewed.cascade.delete)
        self.assertIsNone(next(iter(post.__table__.c.reviewer_id.foreign_keys)).ondelete)
        with Session(engine) as session:
            author, reviewer = user(id=1), user(id=2)
            article = post(id=1, author=author, reviewer=reviewer)
            session.add(article)
            session.commit()
            session.delete(reviewer)
            session.commit()
            self.assertIsNotNone(session.get(post, 1))
            self.assertIsNone(article.reviewer_id)
            session.delete(author)
            session.commit()
            self.assertIsNone(session.get(post, 1))

    def test_blocking_foreign_key_rolls_back_cascaded_deletes(self):
        _, models, _, _, engine = self.build({
            "User": [], "Post": ["user_id:int:fk=users.id:one_to_many:cascade_delete"],
            "Audit": ["user_id:int:fk=users.id:one_to_many"],
        })
        user, post, audit = models["User"], models["Post"], models["Audit"]
        with Session(engine) as session:
            session.add(user(id=1, posts=[post(id=1)], audits=[audit(id=1)]))
            session.commit()
        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(delete(user.__table__).where(user.__table__.c.id == 1))
        with Session(engine) as session:
            self.assertIsNotNone(session.get(user, 1))
            self.assertIsNotNone(session.get(post, 1))
            session.delete(session.get(user, 1))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            self.assertIsNotNone(session.get(user, 1))
            self.assertIsNotNone(session.get(post, 1))
            self.assertIsNotNone(session.get(audit, 1))

    def test_soft_delete_keeps_hierarchy_and_restore(self):
        model, crud_type, _, _ = load_generated([
            "parent_id:int:nullable:fk=records.id:self_relationship:cascade_delete", "soft_delete",
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
            self.assertEqual(len(crud.list(include_deleted=True)), 2)
            crud.restore(1)
            self.assertEqual(crud.get(1).children[0].id, 2)
            session.delete(crud.get(1))
            session.commit()
            self.assertEqual(crud.list(include_deleted=True), [])

    def test_orm_removes_association_links_and_preserves_shared_targets(self):
        base, models, _, _, engine = self.build({
            "User": [], "Role": [], "Post": [
                "user_id:int:fk=users.id:one_to_many:cascade_delete", "roles:many_to_many(Role)",
            ],
        })
        user, role, post = models["User"], models["Role"], models["Post"]
        with Session(engine) as session:
            shared = role(id=1)
            session.add_all([user(id=1, posts=[post(roles=[shared])]), user(id=2, posts=[post(roles=[shared])])])
            session.commit()
            session.delete(session.get(user, 1))
            session.commit()
            self.assertIsNotNone(session.get(role, 1))
            self.assertEqual(len(session.scalars(select(post)).all()), 1)
            links = base.metadata.tables["post_roles"]
            self.assertEqual(session.scalar(select(func.count()).select_from(links)), 1)

    def test_cli_registry_schemas_and_modifier_order(self):
        definitions = [
            "parent_id:int:nullable:fk=records.id:self_relationship:cascade_delete",
            "quantity:int:min=1", "double:int:computed=quantity * 2",
            "index(parent_id,double)", "check(double >= 0)", "soft_delete",
        ]
        ns, sources, registry = schemas(definitions, use_cli=True)
        fields = json.loads(json.dumps(registry))["Record"]["fields"]
        self.assertTrue(fields[0]["cascade_delete"])
        self.assertFalse(fields[1]["cascade_delete"])
        self.assertEqual(fields[0]["backref"], "children")
        self.assertIn('ondelete="CASCADE"', sources["model.j2"])
        self.assertNotIn("cascade_delete", ns["RecordCreate"].model_fields)
        self.assertEqual(ns["RecordCreate"](quantity=2).parent_id, None)
        reordered = "parent_id:int:cascade_delete:self_relationship:fk=records.id:nullable"
        self.assertEqual(parse_fields("Record", [definitions[0]]), parse_fields("Record", [reordered]))

    def test_invalid_cascades_fail_before_generation(self):
        invalid = (
            ["value:int:cascade_delete"], ["user_id:int:fk=users.id:cascade_delete"],
            ["user_id:int:fk=users.id:one_to_many:cascade_delete:cascade_delete"],
            ["user_id:int:fk=users.id:one_to_many:cascade_delete=true"],
            ["user_id:int:fk=users.id:one_to_many:cascade_delete()"],
            ["user_id:int:fk=users.id:one_to_many:cascade=delete"],
            ["user_id:int:fk=users.id:one_to_many:passive_deletes"],
            ["user_id:int:fk=users:one_to_one:cascade_delete"],
            ["user_id:float:fk=users.id:one_to_one:cascade_delete"],
            ["user_id:json():fk=users.id:one_to_one:cascade_delete"],
            ["parent_id:int:fk=posts.id:one_to_one:cascade_delete"],
            ["roles:many_to_many(Role):cascade_delete"],
            ["backref:str", "user_id:int:fk=users.id:one_to_many:cascade_delete"],
            ["user:str", "user_id:int:fk=users.id:one_to_one:cascade_delete"],
            ["user_id:int:fk=users.id:one_to_one:cascade_delete", "other_id:int:fk=users.id:one_to_many(User,post)"],
        )
        for definitions in invalid:
            with self.subTest(definitions=definitions):
                with patch.object(pipeline, "generate_model") as model, patch.object(Registry, "register") as register:
                    with self.assertRaises(ValueError):
                        pipeline.generate_module("Post", definitions)
                    model.assert_not_called()
                    register.assert_not_called()

    def test_relationships_without_option_retain_existing_behavior(self):
        _, models, sources, _, engine = self.build({
            "User": [], "Post": ["user_id:int:nullable:fk=users.id:one_to_many"],
        })
        user, post = models["User"], models["Post"]
        self.assertFalse(inspect(user).relationships.posts.cascade.delete)
        self.assertIsNone(next(iter(post.__table__.c.user_id.foreign_keys)).ondelete)
        self.assertNotIn("from sqlalchemy.orm import backref", sources["Post"]["model.j2"])
        field = parse_fields("Post", ["user_id:int:fk=users.id"])[0]
        self.assertEqual(SQLAlchemyRenderer.render_relationship(field), ['"User"', 'back_populates="posts"'])
        with Session(engine) as session:
            session.add(user(id=1, posts=[post(id=1)]))
            session.commit()
            session.delete(session.get(user, 1))
            session.commit()
            self.assertIsNone(session.get(post, 1).user_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
