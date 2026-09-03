"""Exercise generated optimistic version columns without writing backend files."""

from datetime import datetime, timezone
import importlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.schema import CreateIndex, CreateTable

from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.core.version_column_parser import parse_version_column
from tools.registry.registry import Registry
from tools.test_composite_indexes import load_model, pipeline, run_generation
from tools.test_soft_delete import load_generated
from tools.test_validators import schemas


class VersionColumnSmokeTest(unittest.TestCase):
    def prepare(self, definitions):
        sources, registry = run_generation(definitions)
        model = load_model(sources["model.j2"])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        return model, engine, sources, registry

    def test_declaration_and_modifier_order(self):
        self.assertTrue(parse_version_column("version_column"))
        first, first_registry = run_generation(["name:str", "version_column", "soft_delete"])
        second, second_registry = run_generation(["soft_delete", "version_column", "name:str"])
        self.assertEqual(first, second)
        self.assertEqual(first_registry, second_registry)

    def test_model_mapper_postgresql_ddl_and_registry(self):
        model, _, sources, registry = self.prepare(["name:str", "version_column"])
        column = model.__table__.c.version_id
        self.assertFalse(column.nullable)
        self.assertEqual(column.default.arg, 1)
        self.assertIs(model.__mapper__.version_id_col, column)
        ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
        self.assertIn("version_id INTEGER NOT NULL", ddl)
        self.assertIn('"version_id_col": version_id', sources["model.j2"])
        self.assertEqual(registry["Record"]["version_column"], {
            "name": "version_id", "python_type": "int",
            "sqlalchemy_type": "Integer", "initial": 1,
        })
        self.assertNotIn("version_id", [field["name"] for field in registry["Record"]["fields"]])

    def test_insert_and_each_update_increment_version(self):
        model, engine, _, _ = self.prepare(["name:str", "version_column"])
        with Session(engine) as session:
            item = model(name="one")
            session.add(item)
            session.commit()
            self.assertEqual(item.version_id, 1)
            item.name = "two"
            session.commit()
            self.assertEqual(item.version_id, 2)
            item.name = "three"
            session.commit()
            self.assertEqual(item.version_id, 3)
            session.expire_all()
            self.assertEqual(session.scalar(select(model.version_id)), 3)

    def test_concurrent_update_rejects_stale_write(self):
        model, engine, _, _ = self.prepare(["name:str", "version_column"])
        with Session(engine) as setup:
            setup.add(model(id=1, name="original"))
            setup.commit()
        first, second = Session(engine), Session(engine)
        try:
            left, right = first.get(model, 1), second.get(model, 1)
            left.name = "first"
            first.commit()
            self.assertEqual(left.version_id, 2)
            right.name = "stale"
            with self.assertRaises(StaleDataError):
                second.commit()
            second.rollback()
            second.expire_all()
            stored = second.get(model, 1)
            self.assertEqual((stored.name, stored.version_id), ("first", 2))
        finally:
            first.close()
            second.close()

    def test_custom_primary_key_uses_same_optimistic_check(self):
        key = uuid4()
        model, engine, _, _ = self.prepare(["identifier:uuid:pk", "name:str", "version_column"])
        with Session(engine) as setup:
            setup.add(model(identifier=key, name="original"))
            setup.commit()
        first, second = Session(engine), Session(engine)
        try:
            left, right = first.get(model, key), second.get(model, key)
            left.name = "winner"
            first.commit()
            right.name = "loser"
            with self.assertRaises(StaleDataError):
                second.commit()
            second.rollback()
            self.assertEqual(second.get(model, key).name, "winner")
        finally:
            first.close()
            second.close()

    def test_soft_delete_restore_and_noops_version_correctly(self):
        model, _, service_type, _ = load_generated(["name:str", "version_column", "soft_delete"])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(model(id=1, name="value"))
            session.commit()
            service = service_type(session)
            self.assertEqual(service.delete(1).version_id, 2)
            self.assertEqual(service.delete(1).version_id, 2)
            self.assertEqual(service.restore(1).version_id, 3)
            self.assertEqual(service.restore(1).version_id, 3)

    def test_concurrent_soft_delete_rejects_stale_state(self):
        model, crud_type, _, _ = load_generated(["name:str", "version_column", "soft_delete"])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        with Session(engine) as setup:
            setup.add(model(id=1, name="value"))
            setup.commit()
        first, second = Session(engine), Session(engine)
        try:
            first.get(model, 1)
            stale = second.get(model, 1)
            self.assertEqual(crud_type(first).delete(1).version_id, 2)
            stale.deleted_at = datetime.now(timezone.utc)
            with self.assertRaises(StaleDataError):
                second.commit()
            second.rollback()
            stored = crud_type(second).get(1, include_deleted=True)
            self.assertIsNotNone(stored.deleted_at)
            self.assertEqual(stored.version_id, 2)
        finally:
            first.close()
            second.close()

    def test_audit_fields_and_version_increment_together(self):
        model, _, service_type, registry = load_generated([
            "name:str", "audit_fields", "version_column", "soft_delete",
        ])
        self.addCleanup(model.registry.dispose)
        from tools.test_audit_fields import add_actor_table

        add_actor_table(model)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(model(id=1, name="value", created_by=10))
            session.commit()
            deleted = service_type(session).delete(1, actor_id=20)
            self.assertEqual((deleted.updated_by, deleted.version_id), (20, 2))
            restored = service_type(session).restore(1, actor_id=30)
            self.assertEqual((restored.updated_by, restored.version_id), (30, 3))
        self.assertIn("audit_fields", registry["Record"])
        self.assertIn("version_column", registry["Record"])

    def test_schemas_reject_input_and_expose_read_only_version(self):
        ns, _, _ = schemas(["name:str", "version_column"])
        for schema in (ns["RecordCreate"], ns["RecordUpdate"]):
            self.assertNotIn("version_id", schema.model_fields)
            with self.subTest(schema=schema.__name__), self.assertRaises(ValidationError):
                schema(name="valid", version_id=1)
        response = ns["RecordResponse"].model_validate(SimpleNamespace(id=1, name="valid", version_id=4))
        self.assertEqual(response.version_id, 4)
        metadata = ns["RecordResponse"].model_json_schema()["properties"]["version_id"]
        self.assertTrue(metadata["readOnly"])
        self.assertTrue(metadata["x-arca-version-column"])

    def test_indexes_constraints_cli_and_expression_boundary(self):
        definitions = [
            "name:str", "version_column", "index(name,version_id)",
            "partial_index(name,where=version_id > 1)",
            "unique_together(name,version_id)", "check(version_id >= 1)",
            "expression_index(lower(name),where=version_id > 0)",
        ]
        sources, registry = run_generation(definitions, use_cli=True)
        model = load_model(sources["model.j2"])
        try:
            self.assertEqual(registry["Record"]["indexes"][0]["columns"], ["name", "version_id"])
            self.assertEqual(registry["Record"]["unique_constraints"][0]["columns"], ["name", "version_id"])
            self.assertIn('"version_id" >= 1', registry["Record"]["check_constraints"][0]["expression"])
            self.assertEqual(registry["Record"]["indexes"][2]["where"], '("version_id" > 0)')
            for index in model.__table__.indexes:
                str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        finally:
            model.registry.dispose()
        with self.assertRaises(ValueError):
            run_generation(["name:str", "version_column", "expression_index(abs(version_id))"])

    def test_invalid_declarations_fail_before_generation(self):
        invalid = (
            ["version_column()"], ["version_column(1)"],
            ["version_column", "version_column"], ["version_column(extra=True)"],
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
            ["version_id:int", "version_column"],
            ["version_id_id:int:fk=users.id:one_to_many", "version_column"],
        )
        for definitions in invalid:
            with self.subTest(definitions=definitions), self.assertRaises(ValueError):
                run_generation(definitions)

    def test_direct_generators_revalidate_mutated_metadata(self):
        module = ModuleDefinition(
            name="Record", class_name="Record", module_name="record", table_name="records",
            fields=parse_fields("Record", ["name:str"]),
        )
        module.version_column = 1
        for name in ("model", "schema"):
            generator = importlib.import_module(f"tools.generate_{name}")
            with self.subTest(generator=name), patch.object(generator, "render_template") as render:
                with self.assertRaises(ValueError):
                    getattr(generator, f"generate_{name}")(module)
                render.assert_not_called()
        with patch.object(Registry, "load") as load:
            with self.assertRaises(ValueError):
                Registry.register(module)
            load.assert_not_called()

    def test_advanced_fields_compose_and_plain_modules_stay_unchanged(self):
        ns, sources, registry = schemas([
            "owner_id:int:fk=users.id:one_to_many", "quantity:int:min=1", "name:str",
            "total:int:computed=quantity * 2", "label:str:hybrid=name + '-versioned'",
            "secret:text:encrypted", "version_column", "soft_delete",
        ])
        self.assertEqual(ns["RecordCreate"](owner_id=1, quantity=2, name="n", secret="x").quantity, 2)
        self.assertIn("__mapper_args__", sources["model.j2"])
        self.assertTrue(registry["Record"]["soft_delete"])
        plain_sources, plain_registry = run_generation(["name:str", "soft_delete"])
        self.assertNotIn("version_id", plain_sources["model.j2"])
        self.assertNotIn("version_id", plain_sources["schema.j2"])
        self.assertNotIn("version_column", plain_registry["Record"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
