"""Smoke-test generated self relationships in memory with real ORM persistence."""
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased
from sqlalchemy.schema import CreateTable

from tools.core.field_parser import parse_fields
from tools.registry.registry import Registry
from tools.test_composite_indexes import pipeline
from tools.test_one_to_many import database, generate_models
from tools.test_validators import schemas


class SelfRelationshipSmokeTest(unittest.TestCase):
    def test_scalar_collection_and_postgresql_ddl(self):
        base, models, sources, _ = generate_models({
            "Node": ["parent_id:int:nullable:fk=nodes.id:self_relationship(children)"],
        })
        try:
            node = models["Node"]
            parent = inspect(node).relationships.parent
            self.assertFalse(parent.uselist)
            self.assertTrue(inspect(node).relationships.children.uselist)
            self.assertEqual(parent.remote_side, {node.__table__.c.id})
            self.assertEqual(parent.local_columns, {node.__table__.c.parent_id})
            self.assertEqual(parent.back_populates, "children")
            self.assertTrue(node.parent_id.nullable)
            self.assertNotIn("children", node.__table__.c)
            self.assertIn("remote_side=[id]", sources["Node"]["model.j2"])
            ddl = str(CreateTable(node.__table__).compile(dialect=postgresql.dialect()))
            self.assertIn("FOREIGN KEY(parent_id) REFERENCES nodes (id)", ddl)
        finally:
            base.registry.dispose()

    def test_hierarchy_reparent_detach_and_self_join(self):
        base, models, _, _ = generate_models({
            "Node": ["name:str", "parent_id:int:nullable:fk=nodes.id:self_relationship"],
        })
        engine = database(base)
        try:
            node = models["Node"]
            with Session(engine) as session:
                root = node(name="root")
                left, right, leaf = node(name="left"), node(name="right"), node(name="leaf")
                root.children.extend([left, right])
                left.children.append(leaf)
                session.add(root)
                session.commit()
                session.expire_all()
                self.assertIs(leaf.parent, left)
                self.assertIs(left.parent, root)
                self.assertEqual({child.name for child in root.children}, {"left", "right"})
                parent_alias = aliased(node)
                found = session.scalars(select(node).join(node.parent.of_type(parent_alias)).where(
                    parent_alias.name == "left"
                )).all()
                self.assertEqual(found, [leaf])
                right.children.append(leaf)
                session.commit()
                self.assertEqual(left.children, [])
                self.assertEqual(leaf.parent_id, right.id)
                right.children.remove(leaf)
                session.commit()
                session.expire_all()
                self.assertIsNone(leaf.parent)
                self.assertIsNone(leaf.parent_id)
                self.assertEqual(len(session.scalars(select(node)).all()), 4)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_custom_keys_and_forward_declarations(self):
        for field_type, first_key, second_key in (
            ("int", 101, 102), ("uuid", uuid4(), uuid4()), ("str", "root-key", "child-key"),
        ):
            with self.subTest(field_type=field_type):
                base, models, _, _ = generate_models({"Node": [
                    f"parent_id:{field_type}:nullable:self_relationship:fk=nodes.identifier",
                    f"identifier:{field_type}:pk",
                ]})
                engine = database(base)
                try:
                    node = models["Node"]
                    with Session(engine) as session:
                        root = node(identifier=first_key, children=[node(identifier=second_key)])
                        session.add(root)
                        session.commit()
                        session.expire_all()
                        child = session.get(node, second_key)
                        self.assertEqual(child.parent_id, first_key)
                        self.assertIs(child.parent, root)
                        self.assertEqual(root.children, [child])
                        self.assertEqual(inspect(node).relationships.parent.remote_side,
                                         {node.__table__.c.identifier})
                finally:
                    engine.dispose()
                    base.registry.dispose()

    def test_multiple_self_links_and_external_relationship(self):
        base, models, _, _ = generate_models({
            "Team": [],
            "Employee": [
                "manager_id:int:nullable:fk=employees.id:self_relationship(reports)",
                "mentor_id:int:nullable:fk=employees.id:self_relationship(mentees)",
                "team_id:int:fk=teams.id:one_to_many(Team,members)",
            ],
        })
        engine = database(base)
        try:
            employee, team = models["Employee"], models["Team"]
            with Session(engine) as session:
                group = team()
                boss, mentor = employee(team=group), employee(team=group)
                worker = employee(team=group, manager=boss, mentor=mentor)
                session.add(worker)
                session.commit()
                session.expire_all()
                self.assertEqual(boss.reports, [worker])
                self.assertEqual(mentor.mentees, [worker])
                self.assertEqual(boss.mentees, [])
                self.assertEqual(worker.manager_id, boss.id)
                self.assertEqual(worker.mentor_id, mentor.id)
                self.assertEqual(len(group.members), 3)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_required_and_missing_foreign_keys(self):
        base, models, _, _ = generate_models({
            "Node": ["parent_id:int:fk=nodes.id:self_relationship"],
        })
        engine = database(base)
        try:
            node = models["Node"]
            self.assertFalse(node.parent_id.nullable)
            with Session(engine) as session:
                for item in (node(), node(parent_id=999)):
                    session.add(item)
                    with self.assertRaises(IntegrityError):
                        session.commit()
                    session.rollback()
                # A required self link can be inserted by key without a nullable root.
                session.add(node(id=1, parent_id=1))
                session.commit()
                self.assertIs(session.get(node, 1).parent, session.get(node, 1))
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_cli_registry_schemas_and_existing_model_options(self):
        definitions = [
            "parent_id:int:nullable:fk=records.id:self_relationship(children)",
            "amount:int:min=1", "double:int:computed=amount * 2",
            "index(parent_id,double)", "check(double >= 0)", "soft_delete",
        ]
        ns, _, registry = schemas(definitions, use_cli=True)
        metadata = json.loads(json.dumps(registry))["Record"]["fields"][0]
        self.assertEqual(metadata["relationship_type"], "self_many_to_one")
        self.assertEqual(metadata["relationship_class"], "Record")
        self.assertEqual(metadata["relationship_table"], "records")
        self.assertEqual(metadata["relationship_key"], "id")
        self.assertEqual(metadata["backref"], "children")
        self.assertIsNone(metadata["back_populates"])
        self.assertEqual(ns["RecordCreate"](amount=2).parent_id, None)
        self.assertEqual(ns["RecordUpdate"](parent_id=None).model_dump(exclude_unset=True), {"parent_id": None})
        self.assertNotIn("parent", ns["RecordResponse"].model_fields)
        self.assertNotIn("children", ns["RecordCreate"].model_fields)
        with self.assertRaises(ValidationError):
            ns["RecordCreate"](amount=2, parent_id="invalid")
        base, models, _, _ = generate_models({"Record": definitions})
        engine = database(base)
        try:
            record = models["Record"]
            with Session(engine) as session:
                root = record(amount=2, children=[record(amount=3)])
                session.add(root)
                session.commit()
                self.assertEqual(root.children[0].double, 6)
                response = ns["RecordResponse"].model_validate(root.children[0])
                self.assertEqual(response.parent_id, root.id)
                self.assertEqual(response.double, 6)
                self.assertTrue(record.deleted_at.nullable)
        finally:
            engine.dispose()
            base.registry.dispose()

    def test_invalid_declarations_fail_before_writing(self):
        suffix = ":fk=nodes.id:self_relationship"
        invalid = [
            ["parent_id:int:self_relationship"], ["parent_id:int:fk=others.id:self_relationship"],
            ["parent_id:int:fk=nodes:self_relationship"], ["parent_id:int:fk=nodes.:self_relationship"],
            ["parent_id:int" + suffix + "()"], ["parent_id:int" + suffix + "(children,x)"],
            ["parent_id:int" + suffix + "(class)"], ["parent_id:int" + suffix + "(__dict__)"],
            ["parent_id:int" + suffix + "(metadata)"], ["parent_id:int" + suffix + "(parent)"],
            ["parent_id:int" + suffix + ":self_relationship(children)"],
            ["parent_id:int" + suffix + ":one_to_many"],
            ["parent_id:int:one_to_many" + suffix],
            ["parent_id:int" + suffix + ":one_to_one"],
            ["parent_id:int:one_to_one" + suffix],
            ["parent_id:int" + suffix + ":unique"], ["parent_id:int" + suffix + ":pk"],
            ["parent_id:int" + suffix + ":computed=1"],
            ["parent_id:array(int)" + suffix], ["parent_id:json()" + suffix],
            ["parent_id:float" + suffix], ["parent_id:bool" + suffix],
            ["links:many_to_many(Node):self_relationship"],
        ]
        for definitions in invalid:
            with self.subTest(definitions=definitions):
                self.assert_invalid(definitions)

    def test_invalid_keys_and_conflicting_names(self):
        link = "parent_id:int:nullable:fk=nodes.id:self_relationship"
        invalid = [
            ["parent_id:int:fk=nodes.missing:self_relationship"],
            ["identifier:int:pk", link], ["id:uuid:pk", link],
            ["id:int:pk", "other:int:pk", link], ["id:str", link],
            ["code:int:unique", "parent_id:int:fk=nodes.code:self_relationship"],
            ["parent:str", link], ["children:str", link],
            [link, "owner_id:int:fk=nodes.id:self_relationship"],
            [link, "children_id:int:fk=nodes.id:self_relationship(descendants)"],
            [link, "owner_id:int:fk=nodes.id:self_relationship(parent)"],
            [link, "children:many_to_many(Role)"],
            ["metadata_id:int:fk=nodes.id:self_relationship"],
            ["relationship_id:int:fk=nodes.id:self_relationship"],
            ["parent_id:int:fk=nodes.id:self_relationship(deleted_at)", "soft_delete"],
        ]
        for definitions in invalid:
            with self.subTest(definitions=definitions):
                self.assert_invalid(definitions)

    def assert_invalid(self, definitions):
        with patch.object(pipeline, "generate_model") as model, patch.object(Registry, "register") as register:
            with self.assertRaises(ValueError):
                pipeline.generate_module("Node", definitions)
            model.assert_not_called()
            register.assert_not_called()

    def test_modifier_order_and_models_without_self_relationships(self):
        first = parse_fields("Node", ["parent_id:int:nullable:fk=nodes.id:self_relationship:index"])[0]
        second = parse_fields("Node", ["parent_id:int:index:self_relationship(children):fk=nodes.id:nullable"])[0]
        self.assertEqual(first, second)
        base, _, sources, _ = generate_models({"Node": ["name:str"]})
        try:
            self.assertNotIn("remote_side", sources["Node"]["model.j2"])
            self.assertNotIn("from sqlalchemy.orm import relationship", sources["Node"]["model.j2"])
        finally:
            base.registry.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
