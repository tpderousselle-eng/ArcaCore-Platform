"""Execute deterministic ArcaCore migrations against real isolated PostgreSQL."""

from contextlib import ExitStack, redirect_stdout
from io import StringIO
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from tools import generate as pipeline
from tools.alembic_migration import MigrationPolicy, UnsafeMigrationError, generate_alembic_migration
from tools.core.constraint_parser import parse_constraints
from tools.core.field_parser import parse_fields
from tools.core.index_parser import parse_indexes
from tools.core.module_definition import ModuleDefinition
import tools.generate_crud as crud_generator
import tools.generate_model as model_generator
import tools.generate_router as router_generator
import tools.generate_schema as schema_generator
import tools.generate_service as service_generator
from tools.postgresql_test_server import postgresql_test_server
import tools.registry.registry as registry_module
from tools.schema_evolution import plan_schema_evolution


GENERATORS = (model_generator, schema_generator, crud_generator, service_generator, router_generator)
VERSION_A = ["code:str", "quantity:int", "owner_id:int:nullable"]
VERSION_B = [
    "code:str", "quantity:int", "owner_id:int:nullable:fk=owners.id:one_to_many(Owner,items)",
    "note:text:nullable", "state:str:default='new'",
]


def definition(fields, *, indexes=(), constraints=()):
    parsed = parse_fields("item", list(fields))
    unique, checks = parse_constraints("items", list(constraints), parsed)
    composite = parse_indexes("items", list(indexes), parsed)
    return ModuleDefinition("item", "Item", "item", "items", parsed, indexes=composite, unique_constraints=unique, check_constraints=checks)


def version_b_definition():
    return definition(
        VERSION_B,
        indexes=["index(code,quantity)"],
        constraints=["unique_together(code,state)", "check(quantity >= 0)"],
    )


def execute(migration, connection, direction):
    namespace = {"__name__": f"migration_{migration.revision}"}
    exec(compile(migration.content, migration.filename, "exec"), namespace)
    namespace["op"] = Operations(MigrationContext.configure(connection))
    namespace[direction]()


def generate_application(root, item_fields):
    registry_path = root / "tools" / "registry" / "models.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for generator in GENERATORS:
            stack.enter_context(patch.object(generator, "PROJECT_ROOT", root))
        stack.enter_context(patch.object(registry_module, "REGISTRY_PATH", registry_path))
        stack.enter_context(redirect_stdout(StringIO()))
        pipeline.generate_module("Owner", ["name:str"])
        pipeline.generate_module("Item", list(item_fields))
    packages = ("backend", "backend/app", "backend/app/models", "backend/app/schemas", "backend/app/crud", "backend/app/services", "backend/app/api", "backend/app/db")
    for package in packages:
        target = root / package
        target.mkdir(parents=True, exist_ok=True)
        (target / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "app" / "db" / "base.py").write_text(
        "from sqlalchemy.orm import declarative_base\n\nBase = declarative_base()\n",
        encoding="utf-8",
    )
    return registry_path


class PostgreSQLMigrationValidationTest(unittest.TestCase):
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
            connection.execute(text("DROP TABLE IF EXISTS owners CASCADE"))

    def _migration(self):
        plan = plan_schema_evolution(definition(VERSION_A), version_b_definition())
        policy = MigrationPolicy(verified_data_preconditions=tuple(sorted({
            change.target for change in plan.changes
            if change.target.startswith("constraint:") or change.target == "field:owner_id"
        })))
        return plan, generate_alembic_migration(plan, policy=policy)

    def test_real_upgrade_preserves_rows_defaults_indexes_constraints_and_foreign_keys(self):
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE owners (id SERIAL PRIMARY KEY, name VARCHAR NOT NULL)"))
            connection.execute(text("CREATE TABLE items (id SERIAL PRIMARY KEY, code VARCHAR NOT NULL, quantity INTEGER NOT NULL, owner_id INTEGER NULL)"))
            owner_id = connection.scalar(text("INSERT INTO owners (name) VALUES ('owner-a') RETURNING id"))
            connection.execute(text("INSERT INTO items (code, quantity, owner_id) VALUES ('existing', 2, :owner)"), {"owner": owner_id})
        plan, migration = self._migration()
        with self.engine.begin() as connection:
            execute(migration, connection, "upgrade")
        inspector = inspect(self.engine)
        columns = {value["name"]: value for value in inspector.get_columns("items")}
        self.assertIn("note", columns)
        self.assertIn("state", columns)
        self.assertTrue(columns["note"]["nullable"])
        self.assertIn("ix_items_code_quantity", {value["name"] for value in inspector.get_indexes("items")})
        self.assertIn("uq_items_code_state", {value["name"] for value in inspector.get_unique_constraints("items")})
        self.assertTrue(inspector.get_check_constraints("items"))
        self.assertTrue(inspector.get_foreign_keys("items"))
        with self.engine.begin() as connection:
            row = connection.execute(text("SELECT code, quantity, note, state FROM items WHERE code='existing'" )).one()
            self.assertEqual(tuple(row), ("existing", 2, None, "new"))
            connection.execute(text("INSERT INTO items (code, quantity, owner_id, note) VALUES ('new', 3, :owner, 'v2')"), {"owner": owner_id})
            with self.assertRaises(IntegrityError):
                connection.execute(text("INSERT INTO items (code, quantity, owner_id) VALUES ('bad-fk', 1, 999999)"))
        self.assertEqual(migration.plan_sha256, __import__("hashlib").sha256(plan.canonical_json().encode()).hexdigest())

    def test_generated_version_b_reads_version_a_data_and_writes_new_rows(self):
        with TemporaryDirectory(prefix="arcacore-migration-a-") as first, TemporaryDirectory(prefix="arcacore-migration-b-") as second:
            root_a, root_b = Path(first), Path(second)
            generate_application(root_a, VERSION_A)
            generate_application(root_b, VERSION_B)
            with self.engine.begin() as connection:
                connection.execute(text("CREATE TABLE owners (id SERIAL PRIMARY KEY, name VARCHAR NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
                connection.execute(text("CREATE TABLE items (id SERIAL PRIMARY KEY, code VARCHAR NOT NULL, quantity INTEGER NOT NULL, owner_id INTEGER NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"))
                owner_id = connection.scalar(text("INSERT INTO owners (name) VALUES ('owner-a') RETURNING id"))
                connection.execute(text("INSERT INTO items (code, quantity, owner_id) VALUES ('existing', 2, :owner)"), {"owner": owner_id})
                execute(self._migration()[1], connection, "upgrade")
            prior = {name: value for name, value in sys.modules.items() if name == "backend" or name.startswith("backend.")}
            for name in prior:
                sys.modules.pop(name, None)
            sys.path.insert(0, str(root_b))
            try:
                base = importlib.import_module("backend.app.db.base")
                owner_module = importlib.import_module("backend.app.models.owner")
                item_module = importlib.import_module("backend.app.models.item")
                base.Base.registry.configure()
                from sqlalchemy.orm import Session
                with Session(self.engine) as session:
                    existing = session.query(item_module.Item).filter_by(code="existing").one()
                    self.assertEqual((existing.quantity, existing.note, existing.state), (2, None, "new"))
                    session.add(item_module.Item(code="created-v2", quantity=4, owner_id=owner_id, note="new field"))
                    session.commit()
                    self.assertEqual(session.query(item_module.Item).filter_by(code="created-v2").one().note, "new field")
            finally:
                sys.path.remove(str(root_b))
                for name in list(sys.modules):
                    if name == "backend" or name.startswith("backend."):
                        sys.modules.pop(name, None)
                sys.modules.update(prior)

    def test_honest_downgrade_then_reupgrade(self):
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE owners (id SERIAL PRIMARY KEY, name VARCHAR NOT NULL)"))
            connection.execute(text("CREATE TABLE items (id SERIAL PRIMARY KEY, code VARCHAR NOT NULL, quantity INTEGER NOT NULL, owner_id INTEGER NULL)"))
            migration = self._migration()[1]
            execute(migration, connection, "upgrade")
            execute(migration, connection, "downgrade")
        self.assertEqual({value["name"] for value in inspect(self.engine).get_columns("items")}, {"id", "code", "quantity", "owner_id"})
        with self.engine.begin() as connection:
            execute(migration, connection, "upgrade")
        self.assertIn("state", {value["name"] for value in inspect(self.engine).get_columns("items")})

    def test_invalid_existing_data_blocks_constraint_atomically(self):
        with TemporaryDirectory(prefix="arcacore-migration-failure-") as temporary:
            registry = Path(temporary) / "models.json"
            registry.write_text(json.dumps({"sentinel": "unchanged"}), encoding="utf-8")
            plan = plan_schema_evolution(
                definition(["quantity:int"]),
                definition(["quantity:int"], constraints=["check(quantity >= 0)"]),
            )
            policy = MigrationPolicy(verified_data_preconditions=tuple(change.target for change in plan.changes))
            migration = generate_alembic_migration(plan, policy=policy)
            with self.engine.begin() as connection:
                connection.execute(text("CREATE TABLE items (id SERIAL PRIMARY KEY, quantity INTEGER NOT NULL)"))
                connection.execute(text("INSERT INTO items (quantity) VALUES (-1)"))
            with self.assertRaises(IntegrityError):
                with self.engine.begin() as connection:
                    execute(migration, connection, "upgrade")
            self.assertEqual(inspect(self.engine).get_check_constraints("items"), [])
            self.assertEqual(registry.read_text(encoding="utf-8"), '{"sentinel": "unchanged"}')

    def test_unsupported_destructive_plan_fails_before_database_or_files_change(self):
        plan = plan_schema_evolution(definition(["name:str", "legacy:text:nullable"]), definition(["name:str"]))
        with TemporaryDirectory(prefix="arcacore-migration-reject-") as temporary:
            sentinel = Path(temporary) / "sentinel"
            sentinel.write_bytes(b"stable")
            with self.assertRaises(UnsafeMigrationError):
                generate_alembic_migration(plan)
            self.assertEqual(sentinel.read_bytes(), b"stable")
            self.assertEqual(list(Path(temporary).iterdir()), [sentinel])


if __name__ == "__main__":
    unittest.main(verbosity=2)
