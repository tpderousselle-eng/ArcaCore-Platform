"""Smoke-test partial indexes with generated code in memory and SQLite databases."""

from contextlib import ExitStack
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, create_mock_engine, inspect, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex

from tools.core.field_parser import parse_fields
from tools.core.index_parser import parse_indexes
from tools.registry.registry import Registry
from tools.test_composite_indexes import GENERATORS, load_model, pipeline, run_generation
from tools.test_one_to_many import database, generate_models
from tools.test_soft_delete import load_generated
from tools.test_validators import schemas


class PartialIndexSmokeTest(unittest.TestCase):
    def prepare(self, definitions):
        sources, registry = run_generation(definitions)
        model = load_model(sources["model.j2"])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        return model, engine, sources, registry

    def test_single_column_ddl_reflection_and_query_plan(self):
        model, engine, sources, registry = self.prepare([
            "tenant_id:int", "status:str", "partial_index(tenant_id,where=status == 'Open')",
        ])
        item = registry["Record"]["indexes"][0]
        index = next(index for index in model.__table__.indexes if index.name == item["name"])
        self.assertFalse(index.unique)
        self.assertEqual(list(index.columns.keys()), ["tenant_id"])
        for dialect in (postgresql.dialect(), sqlite.dialect()):
            ddl = str(CreateIndex(index).compile(dialect=dialect))
            self.assertIn('WHERE ("status" = \'Open\')', ddl)
            self.assertNotIn("UNIQUE", ddl)
        self.assertIn("literal_column as _arca_index_predicate", sources["model.j2"])
        reflected = {item["name"]: item for item in inspect(engine).get_indexes("records")}
        self.assertEqual(str(reflected[index.name]["dialect_options"]["sqlite_where"]), item["where"])
        with engine.begin() as connection:
            connection.execute(model.__table__.insert(), [
                {"tenant_id": 7, "status": "Open"},
                {"tenant_id": 7, "status": "Open"},
                {"tenant_id": 7, "status": "Closed"},
            ])
            plan = connection.exec_driver_sql(
                "EXPLAIN QUERY PLAN SELECT id FROM records WHERE tenant_id=7 AND status='Open'"
            ).all()
            self.assertTrue(any(index.name in row[3] for row in plan), plan)
            self.assertEqual(len(connection.execute(select(model)).all()), 3)

    def test_unique_composite_only_constrains_matching_rows(self):
        model, engine, _, _ = self.prepare([
            "tenant_id:int", "email:str", "active:bool:nullable",
            "partial_index(tenant_id,email,where=active == True,unique=True)",
        ])
        with Session(engine) as session:
            session.add_all([
                model(tenant_id=1, email="a", active=True),
                model(tenant_id=2, email="a", active=True),
                model(tenant_id=1, email="a", active=False),
                model(tenant_id=1, email="a", active=False),
                model(tenant_id=1, email="a", active=None),
            ])
            session.commit()
            session.add(model(tenant_id=1, email="a", active=True))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            self.assertEqual(len(session.scalars(select(model)).all()), 5)

    def test_updates_enter_and_leave_unique_subset(self):
        model, engine, _, _ = self.prepare([
            "code:str", "active:bool", "partial_index(code,where=active == True,unique=True)",
        ])
        with Session(engine) as session:
            first, second = model(code="same", active=True), model(code="same", active=False)
            session.add_all([first, second])
            session.commit()
            second.active = True
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            self.assertFalse(second.active)
            first.active = False
            session.commit()
            second.active = True
            session.commit()
            self.assertFalse(first.active)
            self.assertTrue(second.active)

    def test_soft_delete_releases_key_and_restore_checks_uniqueness(self):
        model, crud_type, service_type, _ = load_generated([
            "email:str", "soft_delete",
            "partial_index(email,where=deleted_at is None,unique=True)",
        ])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(model(id=1, email="same"))
            session.commit()
            service = service_type(session)
            service.delete(1)
            session.add(model(id=2, email="same"))
            session.commit()
            with self.assertRaises(IntegrityError):
                service.restore(1)
            self.assertTrue(session.is_active)
            self.assertIsNotNone(crud_type(session).get(1, include_deleted=True).deleted_at)
            self.assertEqual([row.id for row in service.list()], [2])
            service.delete(2)
            service.restore(1)
            self.assertEqual([row.id for row in service.list()], [1])

    def test_boolean_grouping_nulls_and_column_comparisons(self):
        model, engine, _, _ = self.prepare([
            "code:str", "low:int", "high:int", "status:str:nullable",
            "partial_index(code,where=(low < high and not (status == 'Skip')) or status is None,unique=True)",
        ])
        with Session(engine) as session:
            session.add_all([
                model(code="a", low=1, high=2, status="Keep"),
                model(code="a", low=1, high=2, status="Skip"),
                model(code="a", low=3, high=2, status="Keep"),
            ])
            session.commit()
            session.add(model(code="a", low=3, high=2, status=None))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            self.assertEqual(len(session.scalars(select(model)).all()), 3)

    def test_literal_escaping_colons_and_exact_decimal_ddl(self):
        literal = "O'Reilly,:token); DROP TABLE records; --"
        model, engine, _, registry = self.prepare([
            "code:str", "status:str", "amount:decimal(30,20)",
            f"partial_index(code,where=status == {literal!r},unique=True)",
            "partial_index(amount,where=amount >= -0.12345678901234567890)",
        ])
        items = registry["Record"]["indexes"]
        self.assertIn("O''Reilly,:token", items[0]["where"])
        self.assertIn("-0.12345678901234567890", items[1]["where"])
        for index in model.__table__.indexes:
            if index.name == items[0]["name"]:
                ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
                self.assertIn("O''Reilly,:token", ddl)
                self.assertNotIn("NULL", ddl)
        with Session(engine) as session:
            session.add(model(code="a", status=literal))
            session.commit()
            session.add(model(code="a", status=literal))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            self.assertEqual(len(session.scalars(select(model)).all()), 1)

    def test_names_are_stable_distinct_and_bounded(self):
        name = "column_" + "a" * 80
        fields = parse_fields("Record", [f"{name}:int", "status:str"])
        definitions = [
            f"partial_index({name},where={name} > 0)",
            f"partial_index({name},where={name} > 1)",
            f"partial_index({name},where={name} > 0,unique=True)",
            f"index({name},status)",
        ]
        indexes = parse_indexes("records", definitions, fields)
        self.assertEqual(indexes, parse_indexes("records", definitions, fields))
        self.assertEqual(len({index.name for index in indexes}), 4)
        self.assertTrue(all(len(index.name.encode("utf-8")) <= 63 for index in indexes))
        reordered = parse_indexes("records", [f"partial_index({name},unique=False,where=({name}>0))"], fields)
        self.assertEqual(indexes[0], reordered[0])
        with self.assertRaises(ValueError):
            parse_indexes("records", [definitions[0], f"partial_index({name},where=({name}>0),unique=False)"], fields)

    def test_invalid_declarations_fail_before_any_generation(self):
        invalid = [
            "partial_index", "partial_index()", "partial_index(a)",
            "partial_index(where=a > 0)", "partial_index(a,a,where=a > 0)",
            "partial_index(missing,where=a > 0)", "partial_index(a,where=missing > 0)",
            "partial_index(a,where=deleted_at is None)",
            "partial_index(a,where=True)", "partial_index(a,where='a > 0')",
            "partial_index(a,where=a == None)", "partial_index(a,where=a is True)",
            "partial_index(a,where=1 < a < 3)", "partial_index(a,where=a in [1,2])",
            "partial_index(a,where=a + 1 > 0)", "partial_index(a,where=abs(a) > 0)",
            "partial_index(a,where=a.__class__ == 1)", "partial_index(a,where=a[0] == 1)",
            "partial_index(a,where=1 == 1)", "partial_index(a,where=a > 0,unique=1)",
            "partial_index(a,where=a > 0,unique='True')", "partial_index(a,where=a > 0,unique=a)",
            "partial_index(a,where=a > 0,extra=True)", "partial_index(a,where=a > 0,where=a > 1)",
            "partial_index(a,where=a > 0,unique=True,unique=False)",
            "partial_index(*a,where=a > 0)", "partial_index(a,**options)",
            "partial_index('a',where=a > 0)", "partial_index(a,where=a > 0",
            "partial_index(a,where=a > 0):unique", "partial_index(a,where=a > 1e999)",
            "partial_index(a,where=a > 0x10)", "partial_index(a,where=status == 'line\\nfeed')",
            "partial_index(a,where=status == 'back\\\\slash')",
        ]
        for definition in invalid:
            with self.subTest(definition=definition):
                self.assert_invalid(["a:int", "status:str", definition])
        for definitions in (
            ["identifier:uuid:pk", "partial_index(id,where=identifier is not None)"],
            ["roles:many_to_many(Role)", "partial_index(roles,where=id > 0)"],
            ["roles:many_to_many(Role)", "partial_index(id,where=roles is not None)"],
            ["owner_id:int:fk=users.id:one_to_many", "partial_index(owner,where=id > 0)"],
            ["a:int", "partial_index(a,where=a > 0)", "partial_index(a,where=(a>0))"],
        ):
            with self.subTest(definitions=definitions):
                self.assert_invalid(definitions)

    def assert_invalid(self, definitions):
        with ExitStack() as stack:
            generators = [stack.enter_context(patch.object(pipeline, f"generate_{kind}")) for kind in GENERATORS]
            register = stack.enter_context(patch.object(Registry, "register"))
            with self.assertRaises(ValueError):
                pipeline.generate_module("Record", definitions)
            for generate in generators:
                generate.assert_not_called()
            register.assert_not_called()

    def test_implicit_and_custom_keys_and_timestamp_columns(self):
        for key_definition, key in ((None, 1), ("identifier:uuid:pk", uuid4()), ("identifier:str:pk", "key")):
            key_name = "identifier" if key_definition else "id"
            definitions = [key_definition] if key_definition else []
            model, engine, _, registry = self.prepare([
                *definitions, "status:str",
                f"partial_index({key_name},where=created_at is not None and updated_at is not None)",
            ])
            self.assertEqual(registry["Record"]["indexes"][0]["columns"], [key_name])
            with Session(engine) as session:
                session.add(model(**{key_name: key, "status": "Open"}))
                session.commit()
                self.assertIsNotNone(session.get(model, key))

    def test_cli_schemas_computed_constraints_and_registry(self):
        definitions = [
            "count:int:min=1", "total:int:computed=count * 2", "status:choice(Open,Closed)",
            "partial_index(total,status,where=total >= 2 and status == 'Open')",
            "check(total >= 2)", "unique_together(count,status)", "index(count,status)",
        ]
        namespace, sources, registry = schemas(definitions, use_cli=True)
        self.assertEqual(namespace["RecordCreate"](count=1, status="Open").count, 1)
        self.assertNotIn("total", namespace["RecordCreate"].model_fields)
        self.assertIn("total", namespace["RecordResponse"].model_fields)
        item = json.loads(json.dumps(registry))["Record"]["indexes"][0]
        self.assertEqual(item["columns"], ["total", "status"])
        self.assertFalse(item["unique"])
        self.assertIn('"total" >= 2', item["where"])
        baseline, _ = run_generation([value for value in definitions if not value.startswith("partial_index(")])
        for kind in ("schema", "crud", "service", "router"):
            self.assertEqual(sources[f"{kind}.j2"], baseline[f"{kind}.j2"])
        model = load_model(sources["model.j2"])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        with Session(engine) as session:
            record = model(count=2, status="Open")
            session.add(record)
            session.commit()
            self.assertEqual(record.total, 4)

    def test_relationships_compose_with_partial_indexes(self):
        base, models, sources, registry = generate_models({
            "User": [],
            "Post": [
                "owner_id:int:fk=users.id:one_to_many(User,posts):cascade_delete:passive_deletes",
                "status:str", "partial_index(owner_id,where=status == 'Open')",
            ],
        })
        self.addCleanup(base.registry.dispose)
        engine = database(base)
        self.addCleanup(engine.dispose)
        with Session(engine) as session:
            owner = models["User"](posts=[models["Post"](status="Open"), models["Post"](status="Closed")])
            session.add(owner)
            session.commit()
            identifier = owner.id
        with Session(engine) as session:
            session.delete(session.get(models["User"], identifier))
            session.commit()
            self.assertEqual(session.scalars(select(models["Post"])).all(), [])
        self.assertTrue(registry["Post"]["fields"][0]["passive_deletes"])
        self.assertIn("postgresql_where", sources["Post"]["model.j2"])

    def test_existing_indexes_and_field_named_partial_index(self):
        model, engine, sources, registry = self.prepare([
            "partial_index:str:index", "number:int", "index(partial_index,number)",
        ])
        self.assertNotIn("_arca_index_predicate", sources["model.j2"])
        self.assertEqual(registry["Record"]["indexes"], [
            {"name": "ix_records_partial_index_number", "columns": ["partial_index", "number"]},
        ])
        self.assertTrue(model.__table__.c.partial_index.index)
        self.assertIn("ix_records_partial_index_number", {item["name"] for item in inspect(engine).get_indexes("records")})

    def test_unsupported_database_does_not_create_unfiltered_unique_index(self):
        sources, registry = run_generation([
            "code:str:length=100", "partial_index(code,where=code != '',unique=True)",
        ])
        model = load_model(sources["model.j2"])
        self.addCleanup(model.registry.dispose)
        statements = []
        engine = create_mock_engine("mysql://", lambda ddl, *args, **kwargs: statements.append(str(ddl.compile(dialect=engine.dialect))))
        model.metadata.create_all(engine)
        self.assertTrue(any("CREATE TABLE" in sql for sql in statements))
        self.assertFalse(any(registry["Record"]["indexes"][0]["name"] in sql for sql in statements))


if __name__ == "__main__":
    unittest.main(verbosity=2)
