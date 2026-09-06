"""Sprint 26.5 deterministic type compatibility and enum evolution tests."""

from decimal import Decimal
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from tools.alembic_migration import UnsafeMigrationError, generate_alembic_migration
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.postgresql_test_server import postgresql_test_server
from tools.schema_evolution import (
    ChangeKind, SafetyClassification, SchemaChange, SchemaEvolutionPlan,
    plan_schema_evolution,
)
from tools.type_evolution import (
    TypeCompatibility, added_enum_values, classify_type_transition,
)


def module(field):
    return ModuleDefinition("item", "Item", "item", "items", parse_fields("item", [field]))


def change(before, after):
    return plan_schema_evolution(module(before), module(after)).changes[0]


def execute(migration, connection, direction="upgrade"):
    namespace = {"__name__": f"migration_{migration.revision}"}
    exec(compile(migration.content, migration.filename, "exec"), namespace)
    namespace["op"] = Operations(MigrationContext.configure(connection))
    namespace[direction]()


class TypeCompatibilityTest(unittest.TestCase):
    def assert_classification(self, before, after, expected):
        self.assertEqual(classify_type_transition(change(before, after)).classification, expected)

    def test_string_widening_is_safe(self):
        self.assert_classification("value:str:length=10", "value:str:length=20", TypeCompatibility.SAFE_WIDENING)
        self.assert_classification("value:str:length=10", "value:str", TypeCompatibility.SAFE_WIDENING)
        self.assert_classification("value:str:length=10", "value:text", TypeCompatibility.SAFE_WIDENING)

    def test_string_narrowing_requires_validation_and_does_not_generate(self):
        self.assert_classification("value:str:length=20", "value:str:length=10", TypeCompatibility.POTENTIALLY_DESTRUCTIVE)
        with self.assertRaises(UnsafeMigrationError):
            generate_alembic_migration(plan_schema_evolution(module("value:str:length=20"), module("value:str:length=10")))

    def test_decimal_precision_widening_is_safe(self):
        self.assert_classification("value:decimal(10,2)", "value:decimal(12,2)", TypeCompatibility.SAFE_WIDENING)

    def test_decimal_narrowing_and_scale_change_fail_closed(self):
        self.assert_classification("value:decimal(12,2)", "value:decimal(10,2)", TypeCompatibility.POTENTIALLY_DESTRUCTIVE)
        self.assert_classification("value:decimal(12,4)", "value:decimal(12,2)", TypeCompatibility.POTENTIALLY_DESTRUCTIVE)
        self.assert_classification("value:decimal(12,2)", "value:decimal(14,4)", TypeCompatibility.REQUIRES_VALIDATION)

    def test_compatible_numeric_widening(self):
        self.assert_classification("value:int", "value:decimal(20,0)", TypeCompatibility.SAFE_WIDENING)
        self.assert_classification("value:int", "value:decimal(10,0)", TypeCompatibility.REQUIRES_VALIDATION)

    def test_unsupported_scalar_conversions(self):
        self.assert_classification("value:float", "value:int", TypeCompatibility.POTENTIALLY_DESTRUCTIVE)
        self.assert_classification("value:uuid", "value:str", TypeCompatibility.REQUIRES_TRANSFORMATION_POLICY)
        self.assert_classification("value:json", "value:str", TypeCompatibility.UNSUPPORTED)
        self.assert_classification("value:array(str)", "value:array(int)", TypeCompatibility.UNSUPPORTED)

    def test_enum_addition_and_removal_classification(self):
        addition = change("value:enum(draft,live)", "value:enum(draft,live,archived)")
        self.assertEqual(added_enum_values(addition), ("archived",))
        removal = change("value:enum(draft,live)", "value:enum(draft)")
        with self.assertRaisesRegex(ValueError, "append-only"):
            added_enum_values(removal)
        with self.assertRaises(ValueError):
            generate_alembic_migration(plan_schema_evolution(module("value:enum(draft,live)"), module("value:enum(draft)")))

    def test_operation_order_and_revision_are_deterministic(self):
        plan = plan_schema_evolution(
            ModuleDefinition("item", "Item", "item", "items", parse_fields("item", ["a:str:length=10", "b:decimal(10,2)"])),
            ModuleDefinition("item", "Item", "item", "items", parse_fields("item", ["a:str:length=20", "b:decimal(12,2)"])),
        )
        first = generate_alembic_migration(plan)
        second = generate_alembic_migration(plan)
        self.assertEqual(first, second)
        self.assertLess(first.content.index("'a'"), first.content.index("'b'"))

    def test_forged_compatibility_metadata_is_rejected(self):
        forged = SchemaChange(
            ChangeKind.FIELD_TYPE_CHANGED, SafetyClassification.POTENTIALLY_DESTRUCTIVE,
            "field:value", {"python_type": "str", "max_length": "huge"},
            {"python_type": "str", "max_length": 20}, "forged",
        )
        with self.assertRaises(ValueError):
            classify_type_transition(forged)

    def test_forged_enum_type_name_cannot_inject_generated_sql(self):
        forged = SchemaEvolutionPlan("item", (SchemaChange(
            ChangeKind.ENUM_CHANGED, SafetyClassification.SAFE_ADDITIVE,
            "field:state",
            {"name": 'ItemState"; DROP TABLE users;--', "values": ["draft"]},
            {"name": 'ItemState"; DROP TABLE users;--', "values": ["draft", "live"]},
            "forged",
        ),))
        with self.assertRaisesRegex(ValueError, "canonical"):
            generate_alembic_migration(forged)

    def test_hostile_type_metadata_is_rejected_before_planning(self):
        hostile = module("value:str:length=10")
        hostile.fields[0].python_type = "str); DROP TABLE items;--"
        with self.assertRaises(ValueError):
            plan_schema_evolution(module("value:str:length=10"), hostile)

    def test_downgrade_is_explicitly_blocked_without_fit_validation(self):
        migration = generate_alembic_migration(
            plan_schema_evolution(module("value:str:length=10"), module("value:str:length=20"))
        )
        self.assertIn("Downgrade requires validated data-fit precondition", migration.content)
        namespace = {"__name__": "migration_test"}
        exec(compile(migration.content, migration.filename, "exec"), namespace)
        with self.assertRaises(RuntimeError):
            namespace["downgrade"]()


class TypeEvolutionPostgreSQLTest(unittest.TestCase):
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
            connection.execute(text("DROP TYPE IF EXISTS itemvalue CASCADE"))

    def test_string_and_decimal_widening_execute_without_data_loss(self):
        before = ModuleDefinition("item", "Item", "item", "items", parse_fields("item", ["name:str:length=10", "amount:decimal(10,2)"]))
        after = ModuleDefinition("item", "Item", "item", "items", parse_fields("item", ["name:str:length=20", "amount:decimal(12,2)"]))
        migration = generate_alembic_migration(plan_schema_evolution(before, after))
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE items (id SERIAL PRIMARY KEY, name VARCHAR(10) NOT NULL, amount NUMERIC(10,2) NOT NULL)"))
            connection.execute(text("INSERT INTO items (name, amount) VALUES ('existing', 123.45)"))
            execute(migration, connection)
            self.assertEqual(tuple(connection.execute(text("SELECT name, amount FROM items")).one()), ("existing", Decimal("123.45")))
            connection.execute(text("INSERT INTO items (name, amount) VALUES ('fifteen-letters!', 123456789.12)"))
        columns = {value["name"]: value for value in inspect(self.engine).get_columns("items")}
        self.assertEqual(columns["name"]["type"].length, 20)
        self.assertEqual((columns["amount"]["type"].precision, columns["amount"]["type"].scale), (12, 2))

    def test_enum_addition_executes_and_downgrade_refuses_false_safety(self):
        migration = generate_alembic_migration(
            plan_schema_evolution(module("value:enum(draft,live)"), module("value:enum(draft,live,archived)"))
        )
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TYPE itemvalue AS ENUM ('draft', 'live')"))
            connection.execute(text("CREATE TABLE items (id SERIAL PRIMARY KEY, value itemvalue NOT NULL)"))
            connection.execute(text("INSERT INTO items (value) VALUES ('draft')"))
            execute(migration, connection)
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO items (value) VALUES ('archived')"))
            self.assertEqual(connection.scalar(text("SELECT count(*) FROM items")), 2)
            with self.assertRaises(RuntimeError):
                execute(migration, connection, "downgrade")


if __name__ == "__main__":
    unittest.main(verbosity=2)
