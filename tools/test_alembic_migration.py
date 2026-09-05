import tempfile
from pathlib import Path
import unittest

from tools.alembic_migration import (
    MigrationPolicy, UnsafeMigrationError, generate_alembic_migration,
    write_alembic_migration,
)
from tools.core.constraint_parser import parse_constraints
from tools.core.field_parser import parse_fields
from tools.core.index_parser import parse_indexes
from tools.core.module_definition import ModuleDefinition
from tools.schema_evolution import plan_schema_evolution
from tools.schema_evolution import (
    ChangeKind, SafetyClassification, SchemaChange, SchemaEvolutionPlan,
)


def module(fields, *, indexes=(), constraints=()):
    parsed = parse_fields("item", list(fields))
    unique, checks = parse_constraints("items", list(constraints), parsed)
    composite = parse_indexes("items", list(indexes), parsed)
    return ModuleDefinition("item", "Item", "item", "items", parsed, indexes=composite, unique_constraints=unique, check_constraints=checks)


class AlembicMigrationTest(unittest.TestCase):
    def test_new_module_creates_table_indexes_constraints_and_managed_columns(self):
        proposed = module(
            ["name:str", "quantity:int"],
            indexes=["index(name,quantity)"],
            constraints=["check(quantity >= 0)", "unique_together(name,quantity)"],
        )
        proposed.soft_delete = True
        proposed.version_column = True
        migration = generate_alembic_migration(plan_schema_evolution(None, proposed))
        self.assertIn("op.create_table('items'", migration.content)
        self.assertIn("sa.Column('deleted_at'", migration.content)
        self.assertIn("sa.Column('version_id'", migration.content)
        self.assertIn("sa.UniqueConstraint('name', 'quantity'", migration.content)
        self.assertIn("sa.CheckConstraint", migration.content)
        self.assertIn("op.create_index('ix_items_name_quantity'", migration.content)
        self.assertIn("op.drop_table('items')", migration.content)

    def test_repeated_generation_has_identical_bytes_and_revision(self):
        plan = plan_schema_evolution(module(["name:str"]), module(["name:str", "note:text:nullable"]))
        first = generate_alembic_migration(plan)
        second = generate_alembic_migration(plan)
        self.assertEqual(first, second)
        self.assertEqual(first.content.encode(), second.content.encode())

    def test_revision_changes_with_plan_and_is_bounded(self):
        one = generate_alembic_migration(plan_schema_evolution(module(["name:str"]), module(["name:str", "a:int:nullable"])))
        two = generate_alembic_migration(plan_schema_evolution(module(["name:str"]), module(["name:str", "b:int:nullable"])))
        self.assertRegex(one.revision, r"^[0-9a-f]{12}$")
        self.assertNotEqual(one.revision, two.revision)

    def test_nullable_add_column_upgrade_and_downgrade(self):
        migration = generate_alembic_migration(plan_schema_evolution(module(["name:str"]), module(["name:str", "note:text:nullable"])))
        self.assertIn("op.add_column('items', sa.Column('note', sa.Text(), nullable=True))", migration.content)
        self.assertIn("op.drop_column('items', 'note')", migration.content)
        compile(migration.content, migration.filename, "exec")

    def test_safe_literal_default_is_explicit(self):
        migration = generate_alembic_migration(plan_schema_evolution(module(["name:str"]), module(["name:str", "count:int:default=0"])))
        self.assertIn("server_default=sa.text('0')", migration.content)

    def test_composite_index_addition_is_reversible(self):
        migration = generate_alembic_migration(plan_schema_evolution(module(["a:str", "b:str"]), module(["a:str", "b:str"], indexes=["index(a,b)"])))
        self.assertIn("op.create_index('ix_items_a_b'", migration.content)
        self.assertIn("op.drop_index('ix_items_a_b'", migration.content)

    def test_index_removal_requires_exact_authorization(self):
        plan = plan_schema_evolution(module(["a:str", "b:str"], indexes=["index(a,b)"]), module(["a:str", "b:str"]))
        with self.assertRaisesRegex(UnsafeMigrationError, "not authorized"):
            generate_alembic_migration(plan)
        migration = generate_alembic_migration(plan, policy=MigrationPolicy(authorized_index_removals=("ix_items_a_b",)))
        self.assertIn("op.drop_index('ix_items_a_b'", migration.content)

    def test_unique_and_check_constraints_require_preconditions(self):
        plan = plan_schema_evolution(module(["a:int", "b:int"]), module(["a:int", "b:int"], constraints=["unique_together(a,b)", "check(a >= 0)"]))
        with self.assertRaisesRegex(UnsafeMigrationError, "verified existing-data"):
            generate_alembic_migration(plan)
        policy = MigrationPolicy(verified_data_preconditions=tuple(change.target for change in plan.changes))
        migration = generate_alembic_migration(plan, policy=policy)
        self.assertIn("op.create_unique_constraint", migration.content)
        self.assertIn("op.create_check_constraint", migration.content)

    def test_foreign_key_addition_requires_precondition(self):
        plan = plan_schema_evolution(module(["owner_id:int"]), module(["owner_id:int:fk=users.id"]))
        with self.assertRaises(UnsafeMigrationError):
            generate_alembic_migration(plan)
        migration = generate_alembic_migration(plan, policy=MigrationPolicy(verified_data_preconditions=("field:owner_id",)))
        self.assertIn("op.create_foreign_key('fk_items_owner_id_users'", migration.content)

    def test_required_without_default_and_destructive_changes_fail_closed(self):
        required = plan_schema_evolution(module(["name:str"]), module(["name:str", "code:str"]))
        removed = plan_schema_evolution(module(["name:str", "note:text:nullable"]), module(["name:str"]))
        with self.assertRaisesRegex(UnsafeMigrationError, "backfill policy"):
            generate_alembic_migration(required)
        with self.assertRaisesRegex(UnsafeMigrationError, "field_removed"):
            generate_alembic_migration(removed)

    def test_type_narrowing_and_encryption_changes_do_not_generate(self):
        for plan in (
            plan_schema_evolution(module(["value:text"]), module(["value:str"])),
            plan_schema_evolution(module(["value:text:encrypted=KEY"]), module(["value:text"])),
        ):
            with self.assertRaises(UnsafeMigrationError):
                generate_alembic_migration(plan)

    def test_hostile_defaults_and_down_revisions_are_rejected(self):
        proposed = module(["name:str", "value:str:nullable"])
        proposed.fields[1].default = "__import__('os').system('id')"
        with self.assertRaises(ValueError):
            plan_schema_evolution(module(["name:str"]), proposed)
        safe = plan_schema_evolution(module(["name:str"]), module(["name:str", "value:str:nullable"]))
        with self.assertRaisesRegex(ValueError, "down_revision"):
            generate_alembic_migration(safe, down_revision="../../escape")

    def test_forged_plan_cannot_inject_constraint_sql_or_identifiers(self):
        forged = SchemaEvolutionPlan("item", (SchemaChange(
            ChangeKind.CONSTRAINT_ADDED,
            SafetyClassification.REQUIRES_DATA_MIGRATION,
            "constraint:ck_items_hostile",
            None,
            {"name": "ck_items_hostile", "expression": '"name" = 1); DROP TABLE users; --'},
            "forged",
        ),))
        with self.assertRaises(ValueError):
            generate_alembic_migration(
                forged,
                policy=MigrationPolicy(verified_data_preconditions=("constraint:ck_items_hostile",)),
            )

    def test_generation_failure_does_not_mutate_directory(self):
        plan = plan_schema_evolution(module(["name:str", "note:text:nullable"]), module(["name:str"]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sentinel = root / "sentinel.txt"
            sentinel.write_text("original", encoding="utf-8")
            with self.assertRaises(UnsafeMigrationError):
                generate_alembic_migration(plan)
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, {"sentinel.txt": b"original"})

    def test_write_uses_deterministic_filename_and_exact_bytes(self):
        plan = plan_schema_evolution(module(["name:str"]), module(["name:str", "note:text:nullable"]))
        migration = generate_alembic_migration(plan)
        with tempfile.TemporaryDirectory() as temporary:
            output = write_alembic_migration(Path(temporary), migration)
            self.assertEqual(output.name, migration.filename)
            self.assertEqual(output.read_text(encoding="utf-8"), migration.content)


if __name__ == "__main__":
    unittest.main()
