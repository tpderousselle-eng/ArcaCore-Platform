"""Exercise generated models, schemas, and databases without writing backend files."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import importlib
from io import StringIO
import json
import sys
import types
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base

from tools.core.engine import env
from tools.core.field_parser import parse_fields
from tools.registry.registry import Registry
from tools.renderers.sqlalchemy_renderer import SQLAlchemyRenderer
from tools.test_composite_indexes import GENERATORS, pipeline
from tools.test_validators import schemas


def generate_models(definitions):
    base_module = types.ModuleType("backend.app.db.base")
    base_module.Base = declarative_base()
    sources, registry, models = {}, {}, {}
    try:
        for name, fields in definitions.items():
            captured = {}

            def capture(template_name, output_path, **context):
                source = env.get_template(template_name).render(**context)
                compile(source, str(output_path), "exec")
                captured[template_name] = source

            def save(data):
                registry.clear()
                registry.update(data)

            with ExitStack() as stack:
                for kind in GENERATORS:
                    generator = importlib.import_module(f"tools.generate_{kind}")
                    stack.enter_context(patch.object(generator, "render_template", side_effect=capture))
                stack.enter_context(patch.object(Registry, "load", side_effect=lambda: deepcopy(registry)))
                stack.enter_context(patch.object(Registry, "save", side_effect=save))
                stack.enter_context(redirect_stdout(StringIO()))
                pipeline.generate_module(name, fields)
            sources[name] = captured
            namespace = {"__name__": f"generated_{name.lower()}"}
            with patch.dict(sys.modules, {"backend.app.db.base": base_module}):
                exec(compile(captured["model.j2"], f"<generated-{name}>", "exec"), namespace)
            models[name] = namespace[name.capitalize()]
        base_module.Base.registry.configure()
        return base_module.Base, models, sources, registry
    except Exception:
        base_module.Base.registry.dispose()
        raise


def database(base):
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
    base.metadata.create_all(engine)
    return engine


class OneToManySmokeTest(unittest.TestCase):
    def test_generated_scalar_and_reverse_collection(self):
        base, models, sources, _ = generate_models({
            "User": ["name:str"],
            "Post": ["user_id:int:fk=users.id:one_to_many", "title:str"],
        })
        try:
            user, post = models["User"], models["Post"]
            self.assertTrue(inspect(user).relationships.posts.uselist)
            self.assertFalse(inspect(post).relationships.user.uselist)
            self.assertEqual(inspect(post).relationships.user.back_populates, "posts")
            self.assertFalse(post.user_id.unique)
            self.assertFalse(post.user_id.nullable)
            self.assertEqual(inspect(post).relationships.user.local_columns, {post.__table__.c.user_id})
            self.assertNotIn("posts", user.__table__.c)
            self.assertIn("foreign_keys=[user_id]", sources["Post"]["model.j2"])
        finally:
            base.registry.dispose()

    def test_append_reassign_remove_and_reload(self):
        base, models, _, _ = generate_models({
            "User": [], "Post": ["user_id:int:nullable:fk=users.id:one_to_many"],
        })
        engine = database(base)
        try:
            user, post = models["User"], models["Post"]
            with Session(engine) as session:
                first, second = user(), user()
                a, b = post(), post()
                first.posts.extend([a, b])
                session.add_all([first, second])
                session.commit()
                session.expire_all()
                self.assertEqual(len(first.posts), 2)
                self.assertIs(a.user, first)
                second.posts.append(a)
                session.commit()
                self.assertEqual(first.posts, [b])
                self.assertEqual(second.posts, [a])
                self.assertEqual(a.user_id, second.id)
                second.posts.remove(a)
                session.commit()
                self.assertIsNone(a.user_id)
                self.assertIsNone(a.user)
                self.assertEqual(len(session.scalars(select(post)).all()), 2)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_required_and_invalid_foreign_keys(self):
        base, models, _, _ = generate_models({
            "User": [], "Post": ["user_id:int:fk=users.id:one_to_many"],
        })
        engine = database(base)
        try:
            user, post = models["User"], models["Post"]
            with Session(engine) as session:
                owner = user(posts=[post(), post()])
                session.add(owner)
                session.commit()
                self.assertEqual(len(owner.posts), 2)
                owner.posts.remove(owner.posts[0])
                with self.assertRaises(IntegrityError):
                    session.commit()
                session.rollback()
                session.add(post(user_id=999))
                with self.assertRaises(IntegrityError):
                    session.commit()
                session.rollback()
                self.assertEqual(len(owner.posts), 2)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_multiple_foreign_keys_to_same_parent(self):
        base, models, _, _ = generate_models({
            "Post": [
                "author_id:int:fk=users.id:one_to_many(User,authored_posts)",
                "reviewer_id:int:fk=users.id:one_to_many(User,reviewed_posts)",
            ],
            "User": [],
        })
        engine = database(base)
        try:
            user, post = models["User"], models["Post"]
            with Session(engine) as session:
                author, reviewer = user(), user()
                article = post(author=author, reviewer=reviewer)
                session.add(article)
                session.commit()
                session.expire_all()
                self.assertEqual(author.authored_posts, [article])
                self.assertEqual(reviewer.reviewed_posts, [article])
                self.assertEqual(author.reviewed_posts, [])
                self.assertEqual(article.author_id, author.id)
                self.assertEqual(article.reviewer_id, reviewer.id)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_uuid_and_string_custom_keys(self):
        for field_type, key in (("uuid", uuid4()), ("str", "owner-1")):
            with self.subTest(field_type=field_type):
                base, models, _, _ = generate_models({
                    "User": [f"identifier:{field_type}:pk"],
                    "Post": [f"owner_id:{field_type}:fk=users.identifier:one_to_many(User,posts)"],
                })
                engine = database(base)
                try:
                    user, post = models["User"], models["Post"]
                    with Session(engine) as session:
                        owner = user(identifier=key, posts=[post(), post()])
                        session.add(owner)
                        session.commit()
                        session.expire_all()
                        self.assertEqual(len(owner.posts), 2)
                        self.assertTrue(all(item.owner_id == key for item in owner.posts))
                        self.assertIs(owner.posts[0].owner, owner)
                finally:
                    engine.dispose()
                    base.registry.dispose()

    def test_cli_schemas_and_registry_metadata(self):
        ns, sources, registry = schemas([
            "owner_id:uuid:fk=users.identifier:one_to_many(User,records)",
            "count:int:min=1", "double:int:computed=count * 2",
            "index(owner_id,double)", "check(double >= 0)", "soft_delete",
        ], use_cli=True)
        metadata = json.loads(json.dumps(registry))["Record"]["fields"][0]
        self.assertEqual(metadata["relationship_type"], "many_to_one")
        self.assertEqual(metadata["relationship_class"], "User")
        self.assertEqual(metadata["relationship_key"], "identifier")
        self.assertEqual(metadata["backref"], "records")
        self.assertIsNone(metadata["back_populates"])
        key = uuid4()
        self.assertEqual(ns["RecordCreate"](owner_id=key, count=1).owner_id, key)
        self.assertNotIn("owner", ns["RecordCreate"].model_fields)
        self.assertEqual(ns["RecordUpdate"]().model_dump(exclude_unset=True), {})
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](count=1)
        self.assertIn("deleted_at", sources["model.j2"])
        self.assertIn("Computed", sources["model.j2"])

    def test_invalid_declarations_fail_before_writing(self):
        invalid = (
            "user_id:int:one_to_many", "user_id:int:fk=users:one_to_many",
            "user_id:int:fk=users.:one_to_many", "user_id:int:fk=.id:one_to_many",
            "user_id:int:fk=users.id:one_to_many()", "user_id:int:fk=users.id:one_to_many(User)",
            "user_id:int:fk=users.id:one_to_many(User,)", "user_id:int:fk=users.id:one_to_many(User,posts,x)",
            "user_id:int:fk=users.id:one_to_many(class,posts)",
            "user_id:int:fk=users.id:one_to_many(User,__dict__)",
            "user_id:int:fk=users.id:one_to_many(User,metadata)",
            "user_id:int:fk=users.id:one_to_many:one_to_many(User,posts)",
            "user_id:int:fk=users.id:one_to_many:one_to_one",
            "user_id:int:fk=users.id:one_to_one:one_to_many",
            "user_id:int:fk=users.id:one_to_many:unique",
            "user_id:int:fk=users.id:one_to_many:pk",
            "user_id:int:fk=users.id:one_to_many:computed=1",
            "user_id:array(int):fk=users.id:one_to_many",
            "user_id:json():fk=users.id:one_to_many",
            "roles:many_to_many(Role):one_to_many",
        )
        for definition in invalid:
            with self.subTest(definition=definition):
                self.assert_invalid([definition])

    def test_conflicts_and_self_relationships_are_rejected(self):
        invalid = (
            ["user:str", "user_id:int:fk=users.id:one_to_many"],
            ["user_id:int:fk=users.id:one_to_many", "other:int:fk=roles.id:one_to_many(Role,posts)", "roles:str"],
            ["author_id:int:fk=users.id:one_to_many(User,posts)", "reviewer_id:int:fk=users.id:one_to_many(User,posts)"],
            ["parent_id:int:fk=posts.id:one_to_many(Post,children)"],
            ["user_id:int:fk=posts.id:one_to_many"],
        )
        for definitions in invalid:
            with self.subTest(definitions=definitions):
                self.assert_invalid(definitions)

    def assert_invalid(self, definitions):
        with patch.object(pipeline, "generate_model") as model, patch.object(Registry, "register") as register:
            with self.assertRaises(ValueError):
                pipeline.generate_module("Post", definitions)
            model.assert_not_called()
            register.assert_not_called()

    def test_modifier_order_and_legacy_relationships(self):
        first = parse_fields("Post", ["user_id:int:fk=users.id:one_to_many:nullable"])[0]
        second = parse_fields("Post", ["user_id:int:nullable:one_to_many:fk=users.id"])[0]
        self.assertEqual(first, second)
        explicit = parse_fields("Post", ["user_id:int:fk=users.id:one_to_many(User,posts):nullable"])[0]
        self.assertEqual(first, explicit)
        legacy = parse_fields("Post", ["user_id:int:fk=users.id"])[0]
        self.assertEqual(SQLAlchemyRenderer.render_relationship(legacy), ['"User"', 'back_populates="posts"'])
        one = parse_fields("Profile", ["user_id:int:fk=users.id:one_to_one"])[0]
        self.assertTrue(one.unique)
        self.assertEqual(one.relationship_type, "one_to_one")
        many = parse_fields("User", ["roles:many_to_many(Role)"])[0]
        self.assertEqual(many.relationship_type, "many_to_many")


if __name__ == "__main__":
    unittest.main(verbosity=2)
