"""Sprint 26.6 advanced index migration and review-first CLI tests."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from tools.alembic_migration import MigrationPolicy, UnsafeMigrationError, generate_alembic_migration
from tools.core.field_parser import parse_fields
from tools.core.index_parser import parse_indexes
from tools.core.module_definition import ModuleDefinition
from tools.migration_cli import main
from tools.postgresql_test_server import postgresql_test_server
from tools.schema_evolution import plan_schema_evolution


def module(fields, indexes=(), *, soft_delete=False):
    parsed = parse_fields("item", list(fields))
    return ModuleDefinition(
        "item", "Item", "item", "items", parsed,
        indexes=parse_indexes("items", list(indexes), parsed, soft_delete=soft_delete),
        soft_delete=soft_delete,
    )


def execute(migration, connection, direction="upgrade"):
    namespace = {"__name__": f"migration_{migration.revision}"}
    exec(compile(migration.content, migration.filename, "exec"), namespace)
    namespace["op"] = Operations(MigrationContext.configure(connection))
    namespace[direction]()


class AdvancedIndexMigrationTest(unittest.TestCase):
    def test_partial_index_add_and_authorized_remove(self):
        old = module(["code:str"], soft_delete=True)
        new = module(["code:str"], ["partial_index(code,where=deleted_at is None)"], soft_delete=True)
        addition = plan_schema_evolution(old, new)
        migration = generate_alembic_migration(addition)
        self.assertIn("postgresql_where=sa.text('(\"deleted_at\" IS NULL)')", migration.content)
        removal = plan_schema_evolution(new, old)
        with self.assertRaisesRegex(UnsafeMigrationError, "not authorized"):
            generate_alembic_migration(removal)
        name = removal.changes[0].before["name"]
        removed = generate_alembic_migration(removal, policy=MigrationPolicy(authorized_index_removals=(name,)))
        self.assertIn(f"op.drop_index('{name}'", removed.content)
        self.assertIn("postgresql_where=sa.text", removed.content)

    def test_expression_index_add_and_authorized_remove(self):
        old = module(["email:str"])
        new = module(["email:str"], ["expression_index(lower(email))"])
        addition = generate_alembic_migration(plan_schema_evolution(old, new))
        self.assertIn("sa.text('lower(\"email\")')", addition.content)
        removal = plan_schema_evolution(new, old)
        name = removal.changes[0].before["name"]
        generated = generate_alembic_migration(removal, policy=MigrationPolicy(authorized_index_removals=(name,)))
        self.assertIn(f"op.drop_index('{name}'", generated.content)

    def test_hostile_predicate_and_expression_are_rejected_by_existing_parsers(self):
        bad = (
            "partial_index(code,where=code == 'x'); __import__('os')",
            "expression_index(__import__('os').system(email))",
        )
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module(["code:str", "email:str"], [value])

    def test_index_generation_is_deterministic(self):
        plan = plan_schema_evolution(
            module(["email:str", "code:str"], soft_delete=True),
            module(["email:str", "code:str"], [
                "expression_index(lower(email))",
                "partial_index(code,where=deleted_at is None)",
            ], soft_delete=True),
        )
        self.assertEqual(generate_alembic_migration(plan), generate_alembic_migration(plan))


class MigrationCliTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="arcacore-cli-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def run_cli(self, *arguments):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(list(arguments))
        return code, output.getvalue(), error.getvalue()

    def schemas(self, old_fields, new_fields, **new_options):
        old = self.write_json("old.json", {"module": "Item", "fields": old_fields})
        new = self.write_json("new.json", {"module": "Item", "fields": new_fields, **new_options})
        return old, new

    def test_inspect_identical_and_additive_schemas(self):
        old, new = self.schemas(["name:str"], ["name:str"])
        code, output, _ = self.run_cli("inspect", "--old", str(old), "--new", str(new))
        self.assertEqual(code, 0)
        self.assertIn("No schema changes", output)
        new.write_text(json.dumps({"module": "Item", "fields": ["name:str", "note:text:nullable"]}), encoding="utf-8")
        code, output, _ = self.run_cli("inspect", "--old", str(old), "--new", str(new))
        self.assertEqual(code, 0)
        self.assertIn("SAFE_ADDITIVE", output)
        self.assertIn("Executable migration: yes", output)

    def test_inspect_requires_policy_destructive_and_unsupported(self):
        cases = (
            (["name:str"], ["name:str", "code:str"], "REQUIRES_DATA_MIGRATION"),
            (["name:str", "legacy:text:nullable"], ["name:str"], "POTENTIALLY_DESTRUCTIVE"),
            (["value:json"], ["value:str"], "POTENTIALLY_DESTRUCTIVE"),
        )
        for index, (before, after, label) in enumerate(cases):
            old = self.write_json(f"old{index}.json", {"module": "Item", "fields": before})
            new = self.write_json(f"new{index}.json", {"module": "Item", "fields": after})
            code, output, _ = self.run_cli("inspect", "--old", str(old), "--new", str(new))
            self.assertEqual(code, 0)
            self.assertIn(label, output)
            self.assertIn("Executable migration: no", output)

    def test_valid_and_invalid_policy_loading(self):
        old, new = self.schemas(["name:str"], ["name:str", "code:str"])
        valid = self.write_json("policy.json", {"backfills": [{"target_field": "code", "transform": {"kind": "copy_field", "source_field": "name"}}]})
        code, output, _ = self.run_cli("validate", "--old", str(old), "--new", str(new), "--policy", str(valid))
        self.assertEqual(code, 0)
        self.assertIn("Migration valid", output)
        invalid = self.write_json("invalid-policy.json", {"backfills": [{"target_field": "code", "transform": {"kind": "sql", "value": "DROP TABLE items"}}]})
        code, _, error = self.run_cli("validate", "--old", str(old), "--new", str(new), "--policy", str(invalid))
        self.assertEqual(code, 2)
        self.assertIn("failed", error)
        malformed_container = self.write_json("bad-container.json", {"authorized_index_removals": "ix_items_name"})
        code, _, error = self.run_cli("validate", "--old", str(old), "--new", str(new), "--policy", str(malformed_container))
        self.assertEqual(code, 2)
        self.assertIn("JSON list", error)

    def test_unsafe_validate_returns_nonzero(self):
        old, new = self.schemas(["name:str", "legacy:text:nullable"], ["name:str"])
        code, _, error = self.run_cli("validate", "--old", str(old), "--new", str(new))
        self.assertEqual(code, 2)
        self.assertIn("Unsupported or destructive", error)

    def test_plan_and_render_outputs_are_deterministic(self):
        old, new = self.schemas(["name:str"], ["name:str", "note:text:nullable"])
        first = self.run_cli("plan", "--old", str(old), "--new", str(new))
        second = self.run_cli("plan", "--old", str(old), "--new", str(new))
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first[1])["module"], "Item")
        rendered = self.run_cli("render", "--old", str(old), "--new", str(new))
        self.assertEqual(rendered, self.run_cli("render", "--old", str(old), "--new", str(new)))
        self.assertIn("def upgrade", rendered[1])

    def test_safe_output_write_and_overwrite_protection(self):
        old, new = self.schemas(["name:str"], ["name:str", "note:text:nullable"])
        output_dir = self.root / "migrations"
        arguments = ("render", "--old", str(old), "--new", str(new), "--output-root", str(self.root), "--output-dir", str(output_dir))
        code, output, _ = self.run_cli(*arguments)
        self.assertEqual(code, 0)
        written = Path(output.strip())
        self.assertTrue(written.is_file())
        code, _, error = self.run_cli(*arguments)
        self.assertEqual(code, 2)
        self.assertIn("overwrite", error)

    def test_path_traversal_is_rejected(self):
        old, new = self.schemas(["name:str"], ["name:str", "note:text:nullable"])
        outside = self.root.parent / "outside"
        code, _, error = self.run_cli(
            "render", "--old", str(old), "--new", str(new),
            "--output-root", str(self.root), "--output-dir", str(outside),
        )
        self.assertEqual(code, 2)
        self.assertIn("escapes", error)
        self.assertFalse(outside.exists())

    def test_malformed_and_malicious_schema_rejection(self):
        old, _ = self.schemas(["name:str"], ["name:str"])
        malformed = self.root / "bad.json"
        malformed.write_text("{", encoding="utf-8")
        malicious = self.write_json("malicious.json", {"module": "../../Owned", "fields": ["name:str"]})
        for candidate in (malformed, malicious):
            code, _, _ = self.run_cli("plan", "--old", str(old), "--new", str(candidate))
            self.assertEqual(code, 2)

    def test_failed_render_does_not_mutate_output(self):
        old, new = self.schemas(["name:str", "legacy:text:nullable"], ["name:str"])
        output_dir = self.root / "migrations"
        output_dir.mkdir()
        sentinel = output_dir / "sentinel"
        sentinel.write_bytes(b"unchanged")
        code, _, _ = self.run_cli(
            "render", "--old", str(old), "--new", str(new),
            "--output-root", str(self.root), "--output-dir", str(output_dir),
        )
        self.assertEqual(code, 2)
        self.assertEqual({p.name: p.read_bytes() for p in output_dir.iterdir()}, {"sentinel": b"unchanged"})


class AdvancedIndexPostgreSQLTest(unittest.TestCase):
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
            connection.execute(text("CREATE TABLE items (id SERIAL PRIMARY KEY, email VARCHAR NOT NULL, code VARCHAR NOT NULL, deleted_at TIMESTAMP NULL)"))

    def test_partial_and_expression_indexes_upgrade_and_downgrade(self):
        old = module(["email:str", "code:str"], soft_delete=True)
        new = module(["email:str", "code:str"], [
            "partial_index(code,where=deleted_at is None)",
            "expression_index(lower(email))",
        ], soft_delete=True)
        migration = generate_alembic_migration(plan_schema_evolution(old, new))
        with self.engine.begin() as connection:
            execute(migration, connection)
        names = {value["name"] for value in inspect(self.engine).get_indexes("items")}
        self.assertEqual(names, {value.name for value in new.indexes})
        with self.engine.begin() as connection:
            execute(migration, connection, "downgrade")
        self.assertEqual(inspect(self.engine).get_indexes("items"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
