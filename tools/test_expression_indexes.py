"""Exercise expression indexes without writing backend files or registry data."""

from contextlib import ExitStack
from decimal import Decimal
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, create_mock_engine, func, select
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


class ExpressionIndexSmokeTest(unittest.TestCase):
    def prepare(self, definitions):
        sources, registry = run_generation(definitions)
        model = load_model(sources["model.j2"])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        return model, engine, sources, registry

    def test_lower_index_ddl_query_plan_and_original_values(self):
        model, engine, sources, registry = self.prepare([
            "email:str", "expression_index(lower(email))",
        ])
        item = registry["Record"]["indexes"][0]
        self.assertEqual(item["expressions"], ['lower("email")'])
        self.assertEqual(item["columns"], ["email"])
        self.assertIsNone(item["where"])
        self.assertFalse(item["unique"])
        index = next(index for index in model.__table__.indexes if index.name == item["name"])
        self.assertIs(index.table, model.__table__)
        for dialect in (postgresql.dialect(), sqlite.dialect()):
            ddl = str(CreateIndex(index).compile(dialect=dialect))
            self.assertIn('ON records (lower("email"))', ddl)
            self.assertNotIn("UNIQUE", ddl)
        self.assertIn("literal_column as _arca_index_predicate", sources["model.j2"])
        with Session(engine) as session:
            session.add_all([model(email="Alice@Example.com"), model(email="ALICE@EXAMPLE.COM")])
            session.commit()
            self.assertEqual(len(session.scalars(select(model).where(func.lower(model.email) == "alice@example.com")).all()), 2)
            self.assertEqual(session.get(model, 1).email, "Alice@Example.com")
        with engine.connect() as connection:
            plan = connection.exec_driver_sql(
                "EXPLAIN QUERY PLAN SELECT id FROM records WHERE lower(email)='alice@example.com'"
            ).all()
            self.assertTrue(any(item["name"] in row[3] for row in plan), plan)
            ddl = connection.exec_driver_sql("SELECT sql FROM sqlite_master WHERE name=?", (item["name"],)).scalar_one()
            self.assertIn('lower("email")', ddl)

    def test_unique_lower_rejects_insert_and_update_conflicts(self):
        model, engine, _, _ = self.prepare(["email:str", "expression_index(lower(email),unique=True)"])
        with Session(engine) as session:
            session.add_all([model(id=1, email="Alice"), model(id=2, email="Bob")])
            session.commit()
            session.add(model(email="ALICE"))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            session.get(model, 2).email = "alice"
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            self.assertEqual(session.get(model, 2).email, "Bob")
            session.get(model, 1).email = "Carol"
            session.commit()
            session.get(model, 2).email = "ALICE"
            session.commit()
            self.assertEqual([row.email for row in session.scalars(select(model).order_by(model.id))], ["Carol", "ALICE"])

    def test_mixed_keys_preserve_order_and_scope_uniqueness(self):
        model, engine, _, registry = self.prepare([
            "tenant_id:int", "email:str", "expression_index(tenant_id,lower(email),unique=True)",
        ])
        item = registry["Record"]["indexes"][0]
        self.assertEqual(item["expressions"], ['"tenant_id"', 'lower("email")'])
        index = next(index for index in model.__table__.indexes if index.name == item["name"])
        self.assertEqual([str(value) for value in index.expressions], item["expressions"])
        with Session(engine) as session:
            session.add_all([model(tenant_id=1, email="Name"), model(tenant_id=2, email="NAME")])
            session.commit()
            session.add(model(tenant_id=1, email="name"))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            self.assertEqual(len(session.scalars(select(model)).all()), 2)

    def test_arithmetic_precedence_unary_and_exact_literals(self):
        model, engine, _, registry = self.prepare([
            "price:decimal(20,4)", "quantity:int", "offset:int", "rate:float",
            "expression_index(price * (quantity + 1) - -offset)",
            "expression_index(rate * +0.12345678901234567890)",
        ])
        item = registry["Record"]["indexes"][0]
        self.assertEqual(item["expressions"], ['(("price" * ("quantity" + 1)) - (-"offset"))'])
        self.assertIn("0.12345678901234567890", registry["Record"]["indexes"][1]["expressions"][0])
        for index in model.__table__.indexes:
            str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        with Session(engine) as session:
            record = model(price=Decimal("2.5"), quantity=3, offset=1, rate=2.0)
            session.add(record)
            session.commit()
            self.assertEqual(session.scalar(select(model.id).where(model.price * (model.quantity + 1) - -model.offset == 11)), record.id)
        with engine.connect() as connection:
            plan = connection.exec_driver_sql(
                'EXPLAIN QUERY PLAN SELECT id FROM records WHERE ((price * (quantity + 1)) - (-offset))=11'
            ).all()
            self.assertTrue(any(item["name"] in row[3] for row in plan), plan)

    def test_nested_functions_and_shared_column_references(self):
        model, engine, _, registry = self.prepare([
            "title:text", "status:choice(Open,Closed)", "amount:int",
            "expression_index(upper(lower(title)),length(title),abs(amount - length(status)))",
        ])
        item = registry["Record"]["indexes"][0]
        self.assertEqual(item["columns"], ["title", "amount", "status"])
        self.assertEqual(item["expressions"], [
            'upper(lower("title"))', 'length("title")', 'abs(("amount" - length("status")))',
        ])
        with Session(engine) as session:
            session.add(model(title="Mixed", status="Open", amount=-4))
            session.commit()
            self.assertEqual(session.execute(select(func.upper(func.lower(model.title)), func.length(model.title), func.abs(model.amount - func.length(model.status)))).one(), ("MIXED", 5, 8))

    def test_null_expression_results_keep_database_null_semantics(self):
        model, engine, _, _ = self.prepare([
            "email:str:nullable", "expression_index(lower(email),unique=True)",
        ])
        with Session(engine) as session:
            session.add_all([model(email=None), model(email=None), model(email="A")])
            session.commit()
            self.assertEqual(len(session.scalars(select(model)).all()), 3)
            session.add(model(email="a"))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()

    def test_partial_expression_soft_delete_and_restore(self):
        model, crud_type, service_type, registry = load_generated([
            "email:str", "soft_delete",
            "expression_index(lower(email),where=deleted_at is None,unique=True)",
        ])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        self.assertEqual(registry["Record"]["indexes"][0]["where"], '("deleted_at" IS NULL)')
        with Session(engine) as session:
            session.add(model(id=1, email="Alice"))
            session.commit()
            service = service_type(session)
            service.delete(1)
            session.add(model(id=2, email="ALICE"))
            session.commit()
            with self.assertRaises(IntegrityError):
                service.restore(1)
            self.assertTrue(session.is_active)
            self.assertIsNotNone(crud_type(session).get(1, include_deleted=True).deleted_at)
            service.delete(2)
            service.restore(1)
            self.assertEqual([row.id for row in service.list()], [1])
        for index in model.__table__.indexes:
            if index.name == registry["Record"]["indexes"][0]["name"]:
                ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
                self.assertIn('lower("email")', ddl)
                self.assertIn('WHERE ("deleted_at" IS NULL)', ddl)

    def test_literals_are_escaped_without_bind_parameters_or_execution(self):
        literal = "O'Reilly,:value); DROP TABLE records; --"
        model, engine, _, registry = self.prepare([
            "amount:int", "status:str",
            f"expression_index(amount + length({literal!r}),where=status == {literal!r},unique=True)",
        ])
        item = registry["Record"]["indexes"][0]
        self.assertIn("O''Reilly,:value", item["expressions"][0])
        for index in model.__table__.indexes:
            if index.name == item["name"]:
                ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
                self.assertEqual(ddl.count("O''Reilly,:value"), 2)
                self.assertNotIn("NULL", ddl)
        with Session(engine) as session:
            session.add(model(amount=1, status=literal))
            session.commit()
            session.add(model(amount=1, status=literal))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            self.assertEqual(len(session.scalars(select(model)).all()), 1)

    def test_names_deduplicate_normalized_keys_and_preserve_differences(self):
        name = "title_" + "a" * 80
        fields = parse_fields("Record", [f"{name}:str", "tenant:int"])
        definitions = [
            f"expression_index(lower({name}),tenant)",
            f"expression_index(tenant,lower({name}))",
            f"expression_index(upper({name}),tenant)",
            f"expression_index(lower({name}),tenant,unique=True)",
            f"expression_index(lower({name}),tenant,where=tenant > 0)",
            f"partial_index({name},tenant,where=tenant > 0)",
            f"index({name},tenant)",
        ]
        indexes = parse_indexes("records", definitions, fields)
        self.assertEqual(indexes, parse_indexes("records", definitions, fields))
        self.assertEqual(len({index.name for index in indexes}), 7)
        self.assertTrue(all(len(index.name.encode("utf-8")) <= 63 for index in indexes))
        normalized = f"expression_index((lower( {name} )), tenant, unique=False)"
        self.assertEqual(indexes[0], parse_indexes("records", [normalized], fields)[0])
        with self.assertRaises(ValueError):
            parse_indexes("records", [definitions[0], normalized], fields)

    def test_invalid_expressions_and_options_fail_before_any_generation(self):
        declarations = [
            "expression_index", "expression_index()", "expression_index(email)",
            "expression_index(email,amount)", "expression_index(1)", "expression_index(lower('fixed'))",
            "expression_index(lower(email),1)", "expression_index(lower(email),lower((email)))",
            "expression_index(lower(missing))", "expression_index(lower(email)",
            "expression_index(lower(email)):unique", "expression_index(abs(amount),extra=True)",
            "expression_index(abs(amount),unique=1)", "expression_index(abs(amount),unique='True')",
            "expression_index(abs(amount),unique=True,unique=False)",
            "expression_index(abs(amount),where=amount > 0,where=amount > 1)",
            "expression_index(abs(amount),where=True)", "expression_index(abs(amount),where=missing > 0)",
            "expression_index(abs(amount),where=deleted_at is None)",
            "expression_index(abs(amount),where=amount > 1e999)",
            "expression_index(abs(amount),where=abs(amount) > 0)",
            "expression_index(lower(email),**options)", "expression_index(*email)",
            "expression_index(lower())", "expression_index(lower(email, email))",
            "expression_index(lower(value=email))", "expression_index(unknown(email))",
            "expression_index(random())", "expression_index(now())", "expression_index(lower(__import__('os')))",
            "expression_index(email.lower())", "expression_index(email[0])",
            "expression_index((lambda: email)())", "expression_index([value for value in email])",
            "expression_index(email if amount > 0 else email)", "expression_index((x := amount))",
            "expression_index(amount / 2)", "expression_index(amount // 2)", "expression_index(amount ** 2)",
            "expression_index(amount % 2)", "expression_index(amount > 0)", "expression_index(amount + True)",
            "expression_index(amount + None)", "expression_index(amount + 0x10)", "expression_index(amount * 1e999)",
            "expression_index(amount + length('line\\nfeed'))", "expression_index(amount + length('back\\\\slash'))",
            "expression_index(lower(email) + 1)", "expression_index(-email)",
            "expression_index(abs(email))", "expression_index(lower(amount))", "expression_index(length(amount))",
            "expression_index(abs(active))", "expression_index(lower(identifier))", "expression_index(lower(state))",
            "expression_index(lower(data))", "expression_index(abs(tags))", "expression_index(abs(amount),data)",
            "expression_index(abs(amount),roles)", "expression_index(lower(owner))",
            "expression_index(" + "+".join(["amount"] * 60) + ")",
            "expression_index(abs(amount))" + " " * 4000,
        ]
        fields = [
            "email:str", "amount:int", "active:bool", "identifier:uuid", "state:enum(Open,Closed)",
            "data:json()", "tags:array(int)", "roles:many_to_many(Role)",
            "owner_id:int:fk=users.id:one_to_many",
        ]
        for declaration in declarations:
            with self.subTest(declaration=declaration):
                with ExitStack() as stack:
                    generators = [stack.enter_context(patch.object(pipeline, f"generate_{kind}")) for kind in GENERATORS]
                    register = stack.enter_context(patch.object(Registry, "register"))
                    with self.assertRaises(ValueError):
                        pipeline.generate_module("Record", [*fields, declaration])
                    for generate in generators:
                        generate.assert_not_called()
                    register.assert_not_called()

    def test_cli_registry_schemas_and_computed_columns(self):
        definitions = [
            "title:str:min_length=1", "amount:int:min=1", "total:int:computed=amount * 2",
            "expression_index(length(title),total + 1,where=amount > 0)",
            "index(title,amount)", "partial_index(amount,where=amount > 0)",
            "unique_together(title,amount)", "check(amount > 0)",
        ]
        namespace, sources, registry = schemas(definitions, use_cli=True)
        self.assertEqual(namespace["RecordCreate"](title="Title", amount=1).title, "Title")
        self.assertNotIn("total", namespace["RecordCreate"].model_fields)
        metadata = json.loads(json.dumps(registry))["Record"]["indexes"][0]
        self.assertEqual(metadata["columns"], ["title", "total"])
        self.assertEqual(metadata["expressions"], ['length("title")', '("total" + 1)'])
        baseline, old_registry = run_generation([value for value in definitions if not value.startswith("expression_index(")])
        for kind in ("schema", "crud", "service", "router"):
            self.assertEqual(sources[f"{kind}.j2"], baseline[f"{kind}.j2"])
        self.assertEqual(registry["Record"]["indexes"][1:], old_registry["Record"]["indexes"])
        model = load_model(sources["model.j2"])
        self.addCleanup(model.registry.dispose)
        engine = create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        model.metadata.create_all(engine)
        with Session(engine) as session:
            item = model(title="Title", amount=3)
            session.add(item)
            session.commit()
            self.assertEqual(item.total, 6)

    def test_implicit_custom_keys_and_function_named_fields(self):
        for key_definition, key in ((None, 1), ("identifier:uuid:pk", uuid4()), ("identifier:str:pk", "key")):
            key_name = "identifier" if key_definition else "id"
            definitions = [key_definition] if key_definition else []
            model, engine, _, registry = self.prepare([
                *definitions, "lower:str", "expression_index:str", f"expression_index({key_name},lower(lower))",
            ])
            self.assertEqual(registry["Record"]["indexes"][0]["columns"], [key_name, "lower"])
            with Session(engine) as session:
                session.add(model(**{key_name: key, "lower": "Mixed", "expression_index": "regular field"}))
                session.commit()
                self.assertEqual(session.get(model, key).lower, "Mixed")
        fields = parse_fields("Record", ["identifier:uuid:pk", "email:str"])
        with self.assertRaises(ValueError):
            parse_indexes("records", ["expression_index(id,lower(email))"], fields)

    def test_relationship_keys_and_delete_options_compose(self):
        base, models, _, registry = generate_models({
            "User": [],
            "Post": [
                "owner_id:int:fk=users.id:one_to_many(User,posts):cascade_delete:passive_deletes",
                "title:str", "expression_index(owner_id,lower(title),unique=True)",
            ],
        })
        self.addCleanup(base.registry.dispose)
        engine = database(base)
        self.addCleanup(engine.dispose)
        with Session(engine) as session:
            owner = models["User"](posts=[models["Post"](title="Title")])
            session.add(owner)
            session.commit()
            identifier = owner.id
            session.add(models["Post"](owner_id=identifier, title="TITLE"))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
        with Session(engine) as session:
            session.delete(session.get(models["User"], identifier))
            session.commit()
            self.assertEqual(session.scalars(select(models["Post"])).all(), [])
        self.assertTrue(registry["Post"]["fields"][0]["passive_deletes"])

    def test_absent_expression_and_unsupported_dialect_behavior(self):
        sources, registry = run_generation(["email:str", "count:int", "index(email,count)"])
        self.assertNotIn("_arca_index_predicate", sources["model.j2"])
        self.assertEqual(registry["Record"]["indexes"], [{"name": "ix_records_email_count", "columns": ["email", "count"]}])
        sources, registry = run_generation(["email:str:length=100", "expression_index(lower(email),unique=True)"])
        model = load_model(sources["model.j2"])
        self.addCleanup(model.registry.dispose)
        statements = []
        engine = create_mock_engine("mysql://", lambda ddl, *args, **kwargs: statements.append(str(ddl.compile(dialect=engine.dialect))))
        model.metadata.create_all(engine)
        self.assertTrue(any("CREATE TABLE" in sql for sql in statements))
        self.assertFalse(any(registry["Record"]["indexes"][0]["name"] in sql for sql in statements))


if __name__ == "__main__":
    unittest.main(verbosity=2)
