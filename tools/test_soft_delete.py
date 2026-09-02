"""Run python -m tools.test_soft_delete; no backend files are written."""

import sys
import types
import unittest
from unittest.mock import patch

from sqlalchemy import Column, Integer, create_engine, func, select
from sqlalchemy.orm import Session

from tools.registry.registry import Registry
from tools.test_composite_indexes import load_model, pipeline, run_generation


def load_generated(definitions):
    sources, registry = run_generation(definitions)
    model = load_model(sources["model.j2"])
    model_module = types.ModuleType("backend.app.models.record")
    model_module.Record = model
    crud_module = types.ModuleType("backend.app.crud.record")
    service_module = types.ModuleType("backend.app.services.record")
    with patch.dict(sys.modules, {
        "backend.app.models.record": model_module,
        "backend.app.crud.record": crud_module,
    }):
        exec(compile(sources["crud.j2"], "<generated-crud>", "exec"), crud_module.__dict__)
        exec(compile(sources["service.j2"], "<generated-service>", "exec"), service_module.__dict__)
    return model, crud_module.RecordCRUD, service_module.RecordService, registry


class SoftDeleteSmokeTest(unittest.TestCase):
    def test_delete_persists_row_and_filters_reads(self):
        model, crud_type, service_type, _ = load_generated(["title:str", "soft_delete"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with Session(engine) as session:
                session.add_all([model(id=1, title="Keep data"), model(id=2, title="Active")])
                session.commit()
                deleted = service_type(session).delete(1)
                self.assertIsNotNone(deleted.deleted_at)
                self.assertEqual(deleted.title, "Keep data")
            with Session(engine) as session:
                crud = crud_type(session)
                self.assertIsNone(crud.get(1))
                self.assertEqual([item.id for item in crud.list()], [2])
                self.assertEqual(len(crud.list(include_deleted=True)), 2)
                self.assertEqual(crud.get(1, include_deleted=True).title, "Keep data")
                self.assertEqual(session.scalar(select(func.count()).select_from(model)), 2)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_restore_and_repeated_operations(self):
        model, _, service_type, _ = load_generated(["title:str", "soft_delete"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with Session(engine) as session:
                session.add(model(id=1, title="Original"))
                session.commit()
                service = service_type(session)
                timestamp = service.delete(1).deleted_at
                self.assertEqual(service.delete(1).deleted_at, timestamp)
                self.assertIsNone(service.get(1))
                self.assertEqual(len(service.list(include_deleted=True)), 1)
                self.assertIsNone(service.restore(1).deleted_at)
                self.assertEqual(service.get(1).title, "Original")
                self.assertIsNone(service.restore(1).deleted_at)
                self.assertIsNone(service.delete(999))
                self.assertIsNone(service.restore(999))
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_uuid_custom_primary_key(self):
        model, crud_type, _, _ = load_generated(["identifier:uuid:pk", "soft_delete"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with Session(engine) as session:
                item = model()
                session.add(item)
                session.commit()
                identifier = item.identifier
                crud = crud_type(session)
                self.assertIs(crud.get(identifier), item)
                crud.delete(identifier)
                self.assertIsNone(crud.get(identifier))
                crud.restore(identifier)
                self.assertEqual(crud.get(identifier).identifier, identifier)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_model_registry_indexes_and_cli(self):
        sources, registry = run_generation([
            "soft_delete", "tenant_id:int", "index(tenant_id,deleted_at)",
        ], use_cli=True)
        self.assertTrue(registry["Record"]["soft_delete"])
        model = load_model(sources["model.j2"])
        try:
            column = model.__table__.c.deleted_at
            self.assertTrue(column.nullable)
            self.assertTrue(column.type.timezone)
            self.assertTrue(column.index)
            self.assertIn("ix_records_tenant_id_deleted_at", {index.name for index in model.__table__.indexes})
        finally:
            model.registry.dispose()

    def test_invalid_options_fail_before_generation(self):
        for definitions in (
            ["soft_delete", "soft_delete"],
            ["deleted_at:datetime", "soft_delete"],
            ["first:int:pk", "second:int:pk", "soft_delete"],
            ["soft_delete()"],
            ["title:str", "index(title,deleted_at)"],
        ):
            with self.subTest(definitions=definitions):
                with patch.object(pipeline, "generate_model") as generate:
                    with patch.object(Registry, "register") as register:
                        with self.assertRaises(ValueError):
                            pipeline.generate_module("Record", definitions)
                        generate.assert_not_called()
                        register.assert_not_called()

    def test_models_without_option_remain_unchanged(self):
        model, crud_type, service_type, registry = load_generated(["title:str"])
        engine = create_engine("sqlite://")
        try:
            self.assertNotIn("deleted_at", model.__table__.c)
            self.assertFalse(registry["Record"]["soft_delete"])
            self.assertFalse(hasattr(crud_type, "delete"))
            self.assertFalse(hasattr(service_type, "restore"))
            model.metadata.create_all(engine)
            with Session(engine) as session:
                session.add(model(id=1, title="Active"))
                session.commit()
                service = service_type(session)
                self.assertEqual(service.get(1).title, "Active")
                self.assertEqual(len(service.list()), 1)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_failed_commit_rolls_back(self):
        model, crud_type, _, _ = load_generated(["title:str", "soft_delete"])
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with Session(engine) as session:
                session.add(model(id=1, title="Preserved"))
                session.commit()
                crud = crud_type(session)
                with patch.object(session, "commit", side_effect=RuntimeError("commit failed")):
                    with self.assertRaises(RuntimeError):
                        crud.delete(1)
                self.assertIsNone(crud.get(1).deleted_at)
                crud.delete(1)
                with patch.object(session, "commit", side_effect=RuntimeError("commit failed")):
                    with self.assertRaises(RuntimeError):
                        crud.restore(1)
                self.assertIsNotNone(crud.get(1, include_deleted=True).deleted_at)
        finally:
            engine.dispose()
            model.registry.dispose()

    def test_many_to_many_links_survive_delete(self):
        model, crud_type, _, _ = load_generated(["roles:many_to_many(Role)", "soft_delete"])
        base = model.__bases__[0]
        role = type("Role", (base,), {"__tablename__": "roles", "id": Column(Integer, primary_key=True)})
        engine = create_engine("sqlite://")
        try:
            model.metadata.create_all(engine)
            with Session(engine) as session:
                item = model(id=1, roles=[role(id=1)])
                session.add(item)
                session.commit()
                crud = crud_type(session)
                crud.delete(1)
                association = model.metadata.tables["record_roles"]
                self.assertEqual(session.scalar(select(func.count()).select_from(association)), 1)
                crud.restore(1)
                self.assertEqual([linked.id for linked in crud.get(1).roles], [1])
        finally:
            engine.dispose()
            model.registry.dispose()


if __name__ == "__main__":
    unittest.main(verbosity=2)
