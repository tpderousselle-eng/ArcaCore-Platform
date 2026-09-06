"""Sprint 26.4 reviewed data-migration policy validation."""

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from tools.alembic_migration import (
    AssertionKind,
    BackfillPolicy,
    DataAssertion,
    DataTransform,
    MigrationPolicy,
    TransformKind,
    UnsafeMigrationError,
    generate_alembic_migration,
    write_alembic_migration,
)
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.postgresql_test_server import postgresql_test_server
from tools.schema_evolution import SafetyClassification, plan_schema_evolution


def module(fields):
    return ModuleDefinition("item", "Item", "item", "items", parse_fields("item", fields))


def required_plan(field="code:str"):
    return plan_schema_evolution(module(["name:str"]), module(["name:str", field]))


def policy(field, transform, *, assertions=()):
    return MigrationPolicy(
        backfills=(BackfillPolicy(field, transform),),
        assertions=tuple(assertions),
    )


def execute(migration, connection, direction="upgrade"):
    namespace = {"__name__": f"migration_{migration.revision}"}
    exec(compile(migration.content, migration.filename, "exec"), namespace)
    namespace["op"] = Operations(MigrationContext.configure(connection))
    namespace[direction]()


class DataMigrationPolicyTest(unittest.TestCase):
    def test_required_field_with_literal_backfill_is_phased(self):
        plan = required_plan()
        self.assertEqual(plan.changes[0].safety, SafetyClassification.REQUIRES_DATA_MIGRATION)
        migration = generate_alembic_migration(
            plan, policy=policy("code", DataTransform(TransformKind.LITERAL, value="unknown"))
        )
        operations = migration.content
        self.assertLess(operations.index("nullable=True"), operations.index("UPDATE \"items\""))
        self.assertLess(operations.index("UPDATE \"items\""), operations.index("NULL_COUNT".lower()))
        self.assertLess(operations.index("NULL_COUNT".lower()), operations.index("nullable=False"))

    def test_required_field_with_copy_backfill(self):
        migration = generate_alembic_migration(
            required_plan(), policy=policy("code", DataTransform(TransformKind.COPY_FIELD, source_field="name"))
        )
        self.assertIn('SET "code" = "name"', migration.content)

    def test_allowed_string_normalization_is_bounded(self):
        for kind, sql_name in ((TransformKind.LOWER, "lower"), (TransformKind.UPPER, "upper"), (TransformKind.TRIM, "btrim")):
            migration = generate_alembic_migration(
                required_plan(), policy=policy("code", DataTransform(kind, source_field="name"))
            )
            self.assertIn(f'{sql_name}("name")', migration.content)

    def test_policy_schema_compatibility_is_exact(self):
        with self.assertRaisesRegex(UnsafeMigrationError, "mismatch"):
            generate_alembic_migration(
                required_plan(), policy=policy("other", DataTransform(TransformKind.LITERAL, value="x"))
            )

    def test_policy_serialization_is_canonical_and_immutable(self):
        first = MigrationPolicy(
            verified_data_preconditions=("field:z", "field:a"),
            assertions=(DataAssertion(AssertionKind.NULL_COUNT, ("code",), 0),),
            backfills=(BackfillPolicy("code", DataTransform(TransformKind.LITERAL, value="x")),),
        )
        second = MigrationPolicy(
            verified_data_preconditions=("field:a", "field:z"),
            backfills=first.backfills,
            assertions=first.assertions,
        )
        self.assertEqual(
            json.dumps(first.canonical_dict(), sort_keys=True, separators=(",", ":")),
            json.dumps(second.canonical_dict(), sort_keys=True, separators=(",", ":")),
        )
        with self.assertRaises(FrozenInstanceError):
            first.backfills = ()

    def test_policy_changes_deterministic_migration_identity(self):
        plan = required_plan()
        first_policy = policy("code", DataTransform(TransformKind.LITERAL, value="a"))
        second_policy = policy("code", DataTransform(TransformKind.LITERAL, value="b"))
        self.assertEqual(generate_alembic_migration(plan, policy=first_policy), generate_alembic_migration(plan, policy=first_policy))
        self.assertNotEqual(generate_alembic_migration(plan, policy=first_policy).revision, generate_alembic_migration(plan, policy=second_policy).revision)

    def test_malformed_and_hostile_policy_values_are_rejected(self):
        bad_values = [
            lambda: DataTransform("sql", value="DROP TABLE items"),
            lambda: DataTransform(TransformKind.COPY_FIELD, source_field='name"; DROP TABLE items;--'),
            lambda: DataTransform(TransformKind.LITERAL, value=lambda: None),
            lambda: DataTransform(TransformKind.LITERAL, value="x\nDROP TABLE items"),
            lambda: BackfillPolicy("../code", DataTransform(TransformKind.LITERAL, value="x")),
            lambda: DataAssertion(AssertionKind.NULL_COUNT, ("bad;sql",), 0),
        ]
        for factory in bad_values:
            with self.subTest(factory=factory), self.assertRaises(ValueError):
                factory()

    def test_unsupported_transformation_and_arbitrary_python_are_rejected(self):
        with self.assertRaises(ValueError):
            DataTransform(TransformKind.LOWER, value="__import__('os')", source_field="name")
        with self.assertRaises(ValueError):
            MigrationPolicy(backfills=(object(),))

    def test_no_output_is_written_when_policy_validation_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(UnsafeMigrationError):
                write_alembic_migration(root, required_plan())
            self.assertEqual(list(root.iterdir()), [])

    def test_typed_assertions_render_only_internal_templates(self):
        assertions = (
            DataAssertion(AssertionKind.ROW_COUNT, ("id",), 2),
            DataAssertion(AssertionKind.NULL_COUNT, ("name",), 0),
            DataAssertion(AssertionKind.UNIQUE, ("name",), 0),
        )
        plan = plan_schema_evolution(module(["name:str"]), module(["name:str", "note:text:nullable"]))
        migration = generate_alembic_migration(plan, policy=MigrationPolicy(assertions=assertions))
        self.assertIn("SELECT count(*)", migration.content)
        self.assertIn("HAVING count(*) > 1", migration.content)


class DataMigrationPolicyPostgreSQLTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_context = postgresql_test_server()
        cls.server = cls.server_context.__enter__()
        cls.engine = create_engine(cls.server.url, poolclass=NullPool)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.server_context.__exit__(None, None, None)

    def setUp(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS items CASCADE"))
            connection.execute(text("CREATE TABLE items (id SERIAL PRIMARY KEY, name VARCHAR NOT NULL)"))
            connection.execute(text("INSERT INTO items (name) VALUES ('  ALPHA  '), ('Beta')"))

    def test_literal_backfill_enforces_not_null_and_preserves_rows(self):
        migration = generate_alembic_migration(
            required_plan(), policy=policy("code", DataTransform(TransformKind.LITERAL, value="ready"))
        )
        with self.engine.begin() as connection:
            execute(migration, connection)
            self.assertEqual(connection.execute(text("SELECT code FROM items ORDER BY id")).scalars().all(), ["ready", "ready"])
        self.assertFalse({v["name"]: v for v in inspect(self.engine).get_columns("items")}["code"]["nullable"])

    def test_copy_and_normalization_backfills_execute(self):
        migration = generate_alembic_migration(
            required_plan(), policy=policy("code", DataTransform(TransformKind.TRIM, source_field="name"))
        )
        with self.engine.begin() as connection:
            execute(migration, connection)
            self.assertEqual(connection.execute(text("SELECT code FROM items ORDER BY id")).scalars().all(), ["ALPHA", "Beta"])

    def test_failed_assertion_rolls_back_schema_and_data(self):
        plan = plan_schema_evolution(module(["name:str"]), module(["name:str", "note:text:nullable"]))
        migration = generate_alembic_migration(
            plan,
            policy=MigrationPolicy(assertions=(DataAssertion(AssertionKind.ROW_COUNT, ("id",), 99),)),
        )
        with self.assertRaises(DBAPIError):
            with self.engine.begin() as connection:
                execute(migration, connection)
        self.assertNotIn("note", {v["name"] for v in inspect(self.engine).get_columns("items")})


if __name__ == "__main__":
    unittest.main(verbosity=2)
