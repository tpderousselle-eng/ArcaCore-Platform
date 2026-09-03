"""Exercise generated audit fields without writing backend files."""

from datetime import datetime
import importlib
from inspect import signature
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import Column, Integer, String, Table, create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

from tools.core.audit_field_parser import AuditFieldDefinition, parse_audit_fields
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.registry.registry import Registry
from tools.test_composite_indexes import GENERATORS, load_model, pipeline, run_generation
from tools.test_soft_delete import load_generated
from tools.test_validators import schemas


def add_actor_table(model, key_name="id", key_type=None):
    Table(
        "users",
        model.metadata,
        Column(key_name, key_type or Integer, primary_key=True),
    )


class AuditFieldSmokeTest(unittest.TestCase):
    def prepare(self, definitions, key_name="id", key_type=None):
        sources, registry = run_generation(definitions)
        model = load_model(sources["model.j2"])
        self.addCleanup(model.registry.dispose)
        add_actor_table(model, key_name, key_type)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
        model.metadata.create_all(engine)
        return model, engine, sources, registry

    def test_default_and_custom_declarations(self):
        self.assertEqual(
            parse_audit_fields("audit_fields"),
            AuditFieldDefinition("users.id", "int", "Integer"),
        )
        self.assertEqual(
            parse_audit_fields("audit_fields(accounts.identifier,uuid)"),
            AuditFieldDefinition("accounts.identifier", "uuid", "UUID"),
        )
        self.assertEqual(
            parse_audit_fields("audit_fields(people.username,str)"),
            AuditFieldDefinition("people.username", "str", "String"),
        )

    def test_model_columns_postgresql_ddl_and_registry(self):
        model, _, sources, registry = self.prepare(["name:str", "audit_fields"])
        created, updated = model.created_by.property.columns[0], model.updated_by.property.columns[0]
        self.assertFalse(created.nullable)
        self.assertTrue(updated.nullable)
        self.assertTrue(created.index)
        self.assertTrue(updated.index)
        self.assertEqual(next(iter(created.foreign_keys)).target_fullname, "users.id")
        ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
        self.assertIn("created_by INTEGER NOT NULL", ddl)
        self.assertIn("updated_by INTEGER", ddl)
        self.assertEqual(registry["Record"]["audit_fields"], {
            "target": "users.id", "python_type": "int", "sqlalchemy_type": "Integer",
        })
        self.assertNotIn("created_by", [field["name"] for field in registry["Record"]["fields"]])
        self.assertIn('ForeignKey("users.id")', sources["model.j2"])

    def test_database_round_trip_timestamps_and_actors(self):
        model, engine, _, _ = self.prepare(["name:str", "audit_fields"])
        users = model.metadata.tables["users"]
        with engine.begin() as connection:
            connection.execute(users.insert(), [{"id": 7}, {"id": 9}])
        with Session(engine) as session:
            item = model(name="First", created_by=7)
            session.add(item)
            session.commit()
            self.assertEqual(item.created_by, 7)
            self.assertIsNone(item.updated_by)
            self.assertIsInstance(item.created_at, datetime)
            self.assertIsInstance(item.updated_at, datetime)
            item.name = "Second"
            item.updated_by = 9
            session.commit()
            session.expire_all()
            stored = session.scalar(select(model))
            self.assertEqual((stored.name, stored.created_by, stored.updated_by), ("Second", 7, 9))

    def test_uuid_and_string_actor_keys(self):
        from sqlalchemy import UUID

        cases = (
            ("uuid", "accounts.identifier", UUID(as_uuid=True), uuid4()),
            ("str", "accounts.username", String, "operator"),
        )
        for kind, target, key_type, actor in cases:
            with self.subTest(kind=kind):
                definitions = ["name:str", f"audit_fields({target},{kind})"]
                sources, registry = run_generation(definitions)
                model = load_model(sources["model.j2"])
                try:
                    Table("accounts", model.metadata, Column(target.split(".")[1], key_type, primary_key=True))
                    engine = create_engine("sqlite://")
                    try:
                        with engine.connect() as connection:
                            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                            connection.commit()
                        model.metadata.create_all(engine)
                        with engine.begin() as connection:
                            connection.execute(model.metadata.tables["accounts"].insert(), [{target.split(".")[1]: actor}])
                        with Session(engine) as session:
                            session.add(model(name="value", created_by=actor))
                            session.commit()
                            self.assertEqual(session.scalar(select(model.created_by)), actor)
                        self.assertEqual(registry["Record"]["audit_fields"]["python_type"], kind)
                    finally:
                        engine.dispose()
                finally:
                    model.registry.dispose()

    def test_schemas_are_read_only_and_expose_metadata(self):
        ns, _, _ = schemas(["name:str", "audit_fields(accounts.identifier,uuid)"])
        create, update, response = ns["RecordCreate"], ns["RecordUpdate"], ns["RecordResponse"]
        for schema in (create, update):
            self.assertFalse({"created_by", "updated_by", "created_at", "updated_at"} & schema.model_fields.keys())
            for name in ("created_by", "updated_by", "created_at", "updated_at"):
                with self.subTest(schema=schema.__name__, name=name), self.assertRaises(ValidationError):
                    schema(name="valid", **{name: uuid4()})
        actor = uuid4()
        value = response.model_validate(SimpleNamespace(
            id=1, name="valid", created_by=actor, updated_by=None,
            created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 2),
        ))
        self.assertEqual(value.created_by, actor)
        properties = response.model_json_schema()["properties"]
        self.assertTrue(properties["created_by"]["readOnly"])
        self.assertEqual(properties["updated_at"]["x-arca-audit-role"], "updated-at")

    def test_soft_delete_and_restore_record_actor(self):
        model, _, service_type, _ = load_generated(["name:str", "audit_fields", "soft_delete"])
        self.addCleanup(model.registry.dispose)
        add_actor_table(model)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(model(id=1, name="value", created_by=1))
            session.commit()
            service = service_type(session)
            deleted = service.delete(1, actor_id=2)
            self.assertEqual(deleted.updated_by, 2)
            timestamp = deleted.deleted_at
            self.assertEqual(service.delete(1, actor_id=3).updated_by, 2)
            self.assertEqual(service.delete(1, actor_id=3).deleted_at, timestamp)
            restored = service.restore(1, actor_id=4)
            self.assertIsNone(restored.deleted_at)
            self.assertEqual(restored.updated_by, 4)
            self.assertEqual(service.restore(1, actor_id=5).updated_by, 4)

    def test_failed_delete_and_restore_roll_back_actor(self):
        model, crud_type, _, _ = load_generated(["name:str", "audit_fields", "soft_delete"])
        self.addCleanup(model.registry.dispose)
        add_actor_table(model)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(model(id=1, name="value", created_by=1))
            session.commit()
            crud = crud_type(session)
            with patch.object(session, "commit", side_effect=RuntimeError("failed")):
                with self.assertRaises(RuntimeError):
                    crud.delete(1, 2)
            item = crud.get(1, include_deleted=True)
            self.assertIsNone(item.deleted_at)
            self.assertIsNone(item.updated_by)
            crud.delete(1, 2)
            with patch.object(session, "commit", side_effect=RuntimeError("failed")):
                with self.assertRaises(RuntimeError):
                    crud.restore(1, 3)
            item = crud.get(1, include_deleted=True)
            self.assertIsNotNone(item.deleted_at)
            self.assertEqual(item.updated_by, 2)

    def test_indexes_constraints_and_cli_metadata(self):
        definitions = [
            "name:str", "audit_fields", "index(created_by,updated_by)",
            "partial_index(name,where=updated_by is None,unique=True)",
            "unique_together(created_by,name)", "check(created_by > 0)",
        ]
        sources, registry = run_generation(definitions, use_cli=True)
        model = load_model(sources["model.j2"])
        try:
            add_actor_table(model)
            names = {index.name for index in model.__table__.indexes}
            self.assertIn("ix_records_created_by_updated_by", names)
            self.assertEqual(registry["Record"]["indexes"][0]["columns"], ["created_by", "updated_by"])
            self.assertEqual(registry["Record"]["unique_constraints"][0]["columns"], ["created_by", "name"])
            self.assertIn('"created_by" > 0', registry["Record"]["check_constraints"][0]["expression"])
            for index in model.__table__.indexes:
                str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        finally:
            model.registry.dispose()

    def test_invalid_declarations_fail_before_generation(self):
        invalid = (
            ["audit_fields()"], ["audit_fields(users)"], ["audit_fields(.id)"],
            ["audit_fields(users.id,float)"], ["audit_fields(users.id,int,extra)"],
            ["audit_fields", "audit_fields"], ["audit_fields(users.id)junk"],
        )
        for definitions in invalid:
            with self.subTest(definitions=definitions):
                with patch.object(pipeline, "generate_model") as generate, patch.object(Registry, "register") as register:
                    with self.assertRaises(ValueError):
                        pipeline.generate_module("Record", definitions)
                    generate.assert_not_called()
                    register.assert_not_called()

    def test_reserved_field_and_relationship_names_are_rejected(self):
        invalid = (
            ["created_by:int", "audit_fields"], ["updated_at:datetime", "audit_fields"],
            ["created_by_id:int:fk=users.id:one_to_many(User,created_by)", "audit_fields"],
        )
        for definitions in invalid:
            with self.subTest(definitions=definitions), self.assertRaises(ValueError):
                run_generation(definitions)

    def test_direct_generators_revalidate_mutated_metadata(self):
        module = ModuleDefinition(
            name="Record", class_name="Record", module_name="record", table_name="records",
            fields=parse_fields("Record", ["name:str"]),
        )
        module.audit_fields = AuditFieldDefinition("users.id", "int", "String")
        for name in ("model", "schema", "crud", "service"):
            generator = importlib.import_module(f"tools.generate_{name}")
            with self.subTest(generator=name), patch.object(generator, "render_template") as render:
                with self.assertRaises(ValueError):
                    getattr(generator, f"generate_{name}")(module)
                render.assert_not_called()
        with patch.object(Registry, "load") as load:
            with self.assertRaises(ValueError):
                Registry.register(module)
            load.assert_not_called()

    def test_composes_with_advanced_fields_and_relationships(self):
        ns, sources, registry = schemas([
            "owner_id:int:fk=users.id:one_to_many", "quantity:int:min=1",
            "total:int:computed=quantity * 2", "name:str",
            "label:str:hybrid=name + '-audit'",
            "secret:str:encrypted", "audit_fields", "soft_delete",
        ])
        self.assertEqual(ns["RecordCreate"](owner_id=1, quantity=2, name="n", secret="x").quantity, 2)
        self.assertNotIn("total", ns["RecordCreate"].model_fields)
        self.assertIn("created_by = Column", sources["model.j2"])
        self.assertTrue(registry["Record"]["soft_delete"])
        self.assertEqual(registry["Record"]["audit_fields"]["target"], "users.id")

    def test_expression_index_boundary_and_audit_predicate(self):
        sources, registry = run_generation([
            "name:str", "audit_fields",
            "expression_index(lower(name),where=updated_by is None)",
        ])
        self.assertEqual(registry["Record"]["indexes"][0]["where"], '("updated_by" IS NULL)')
        self.assertIn('lower("name")', sources["model.j2"])
        with self.assertRaises(ValueError):
            run_generation(["name:str", "audit_fields", "expression_index(abs(created_by))"])
        sources, _ = run_generation([
            "status:str", "audit_fields",
            "expression_index(lower(status),where=status == 'created_by')",
        ])
        self.assertIn("created_by", sources["model.j2"])

    def test_modules_without_option_keep_existing_shapes(self):
        plain_sources, plain_registry = run_generation(["name:str", "soft_delete"])
        self.assertNotIn("created_by", plain_sources["model.j2"])
        self.assertNotIn("actor_id", plain_sources["crud.j2"])
        self.assertNotIn("audit_fields", plain_registry["Record"])
        model, crud_type, service_type, _ = load_generated(["name:str", "soft_delete"])
        try:
            self.assertNotIn("created_by", model.__table__.c)
            self.assertEqual(signature(crud_type.delete).parameters.keys(), {"self", "item_id"})
            self.assertEqual(signature(service_type.restore).parameters.keys(), {"self", "item_id"})
        finally:
            model.registry.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
