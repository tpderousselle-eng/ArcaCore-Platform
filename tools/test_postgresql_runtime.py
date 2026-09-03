"""Execute generated ArcaCore models against isolated PostgreSQL."""

import base64
from contextlib import ExitStack, redirect_stdout
from decimal import Decimal
from io import StringIO
import importlib
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, inspect, text
from sqlalchemy.dialects.postgresql import ARRAY, JSON, NUMERIC, UUID as PG_UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from tools import generate as pipeline
import tools.generate_crud as crud_generator
import tools.generate_model as model_generator
import tools.generate_router as router_generator
import tools.generate_schema as schema_generator
import tools.generate_service as service_generator
from tools.postgresql_test_server import postgresql_test_server
import tools.registry.registry as registry_module


GENERATORS = (
    model_generator,
    schema_generator,
    crud_generator,
    service_generator,
    router_generator,
)
MODULES = (
    (
        "Account",
        (
            "identifier:uuid:pk",
            "email:str:length=120:unique",
            "roles:many_to_many(Role,roles.identifier)",
        ),
    ),
    (
        "Role",
        (
            "identifier:uuid:pk",
            "name:enum(Admin,Editor,Viewer):unique",
        ),
    ),
    (
        "Record",
        (
            "owner_id:uuid:fk=accounts.identifier:one_to_many(Account,records):cascade_delete:passive_deletes",
            "reference:str:length=80",
            "code:str:length=80",
            "state:enum(Open,Closed):default='Open'",
            "price:decimal(12,2):min=0",
            "quantity:int:min=1",
            "tags:array(str):nullable",
            "payload:json:nullable",
            "total:decimal(14,2):computed=price * quantity",
            "secret:text:encrypted=ARCACORE_POSTGRES_TEST_KEY",
            "audit_fields(accounts.identifier,uuid)",
            "version_column",
            "soft_delete",
            "index(owner_id,state)",
            "partial_index(code,where=deleted_at is None,unique=True)",
            "expression_index(lower(code),where=deleted_at is None,unique=True)",
            "unique_together(owner_id,reference)",
            "check(quantity >= 1)",
        ),
    ),
)


class PostgreSQLGeneratedRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_context = postgresql_test_server()
        cls.server = cls.server_context.__enter__()
        cls.temporary_directory = TemporaryDirectory()
        cls.root = Path(cls.temporary_directory.name)
        cls.registry_path = cls.root / "tools" / "registry" / "models.json"
        cls.registry_path.parent.mkdir(parents=True, exist_ok=True)

        cls.encryption_patch = patch.dict(
            os.environ,
            {
                "ARCACORE_POSTGRES_TEST_KEY": base64.urlsafe_b64encode(
                    AESGCM.generate_key(bit_length=256)
                ).decode("ascii")
            },
            clear=False,
        )
        cls.encryption_patch.start()

        with ExitStack() as stack:
            for generator in GENERATORS:
                stack.enter_context(patch.object(generator, "PROJECT_ROOT", cls.root))
            stack.enter_context(
                patch.object(registry_module, "REGISTRY_PATH", cls.registry_path)
            )
            stack.enter_context(redirect_stdout(StringIO()))
            for name, fields in MODULES:
                pipeline.generate_module(name, list(fields))

        cls.generated_sources = {
            path.relative_to(cls.root).as_posix(): path.read_text(encoding="utf-8")
            for path in cls.root.rglob("*.py")
        }
        cls._write_runtime_scaffold()
        cls.previous_backend_modules = {
            name: module
            for name, module in sys.modules.items()
            if name == "backend" or name.startswith("backend.")
        }
        for name in cls.previous_backend_modules:
            sys.modules.pop(name, None)
        sys.path.insert(0, str(cls.root))

        cls.base_module = importlib.import_module("backend.app.db.base")
        cls.session_module = importlib.import_module("backend.app.db.session")
        cls.account_module = importlib.import_module("backend.app.models.account")
        cls.role_module = importlib.import_module("backend.app.models.role")
        cls.record_module = importlib.import_module("backend.app.models.record")
        cls.record_crud_module = importlib.import_module("backend.app.crud.record")
        cls.base_module.Base.registry.configure()
        cls.engine = cls.session_module.engine
        cls.SessionLocal = cls.session_module.SessionLocal

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "base_module") and hasattr(cls, "engine"):
            cls.base_module.Base.metadata.drop_all(bind=cls.engine)
            cls.engine.dispose()
        if hasattr(cls, "root") and str(cls.root) in sys.path:
            sys.path.remove(str(cls.root))
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)
        if hasattr(cls, "previous_backend_modules"):
            sys.modules.update(cls.previous_backend_modules)
        if hasattr(cls, "temporary_directory"):
            cls.temporary_directory.cleanup()
        if hasattr(cls, "encryption_patch"):
            cls.encryption_patch.stop()
        if hasattr(cls, "server_context"):
            cls.server_context.__exit__(None, None, None)

    @classmethod
    def _write_runtime_scaffold(cls):
        packages = (
            "backend",
            "backend/app",
            "backend/app/models",
            "backend/app/schemas",
            "backend/app/crud",
            "backend/app/services",
            "backend/app/api",
            "backend/app/db",
        )
        for package in packages:
            target = cls.root / package
            target.mkdir(parents=True, exist_ok=True)
            (target / "__init__.py").write_text("", encoding="utf-8")
        (cls.root / "backend" / "app" / "db" / "base.py").write_text(
            "from sqlalchemy.orm import declarative_base\n\nBase = declarative_base()\n",
            encoding="utf-8",
        )
        (cls.root / "backend" / "app" / "db" / "session.py").write_text(
            "from sqlalchemy import create_engine\n"
            "from sqlalchemy.orm import sessionmaker\n"
            "from sqlalchemy.pool import NullPool\n\n"
            f"engine = create_engine({cls.server.url!r}, poolclass=NullPool)\n"
            "SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\n\n"
            "def get_db():\n"
            "    db = SessionLocal()\n"
            "    try:\n"
            "        yield db\n"
            "    finally:\n"
            "        db.close()\n",
            encoding="utf-8",
        )

    def setUp(self):
        self.base_module.Base.metadata.drop_all(bind=self.engine)
        self.base_module.Base.metadata.create_all(bind=self.engine)

    def account(self, session, email=None, roles=None):
        account = self.account_module.Account(
            email=email or f"account-{uuid4()}@example.com",
            roles=list(roles or ()),
        )
        session.add(account)
        session.commit()
        return account

    def record(self, session, owner, **overrides):
        values = {
            "owner_id": owner.identifier,
            "reference": f"ref-{uuid4()}",
            "code": f"code-{uuid4()}",
            "price": Decimal("12.50"),
            "quantity": 2,
            "tags": ["postgresql", "generated"],
            "payload": {"source": "25.3", "valid": True},
            "secret": "classified",
            **overrides,
        }
        crud = self.record_crud_module.RecordCRUD(session)
        return crud.create(values, actor_id=owner.identifier)

    def test_real_postgresql_server_and_generated_table_creation(self):
        with self.engine.connect() as connection:
            version = connection.scalar(text("select version()"))
            database = connection.scalar(text("select current_database()"))
        self.assertEqual(self.engine.dialect.name, "postgresql")
        self.assertIn("PostgreSQL", version)
        self.assertEqual(database, "postgres")
        self.assertIn("PostgreSQL", self.server.implementation)
        self.assertEqual(
            set(inspect(self.engine).get_table_names()),
            {"accounts", "roles", "account_roles", "records"},
        )

    def test_uuid_numeric_json_array_and_enum_round_trip(self):
        with self.SessionLocal() as session:
            role = self.role_module.Role(name="Admin")
            owner = self.account(session, roles=[role])
            stored = self.record(session, owner)
            identifier = owner.identifier
            record_id = stored.id
        with self.SessionLocal() as session:
            owner = session.get(self.account_module.Account, identifier)
            stored = session.get(self.record_module.Record, record_id)
            self.assertIsInstance(owner.identifier, UUID)
            self.assertEqual(stored.price, Decimal("12.50"))
            self.assertEqual(stored.total, Decimal("25.00"))
            self.assertEqual(stored.tags, ["postgresql", "generated"])
            self.assertEqual(stored.payload, {"source": "25.3", "valid": True})
            self.assertEqual(stored.state.value, "Open")
            self.assertEqual(owner.roles[0].name.value, "Admin")
        reflected = inspect(self.engine).get_columns("records")
        types = {column["name"]: column["type"] for column in reflected}
        self.assertIsInstance(types["owner_id"], PG_UUID)
        self.assertIsInstance(types["price"], NUMERIC)
        self.assertIsInstance(types["payload"], JSON)
        self.assertIsInstance(types["tags"], ARRAY)

    def test_foreign_keys_unique_and_check_constraints_are_enforced(self):
        with self.SessionLocal() as session:
            owner = self.account(session, email="unique@example.com")
            self.record(
                session,
                owner,
                reference="same-reference",
                code="first-code",
            )
            with self.assertRaises(IntegrityError):
                self.record(
                    session,
                    owner,
                    reference="same-reference",
                    code="second-code",
                )
            session.rollback()
            session.add(self.account_module.Account(email="unique@example.com"))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            invalid = self.record_module.Record(
                owner_id=uuid4(),
                reference="invalid-owner",
                code="invalid-owner",
                price=Decimal("1.00"),
                quantity=1,
                secret="value",
                created_by=owner.identifier,
            )
            session.add(invalid)
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()
            invalid = self.record_module.Record(
                owner_id=owner.identifier,
                reference="invalid-quantity",
                code="invalid-quantity",
                price=Decimal("1.00"),
                quantity=0,
                secret="value",
                created_by=owner.identifier,
            )
            session.add(invalid)
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_composite_partial_and_expression_indexes_execute(self):
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    "select indexname, indexdef from pg_indexes "
                    "where schemaname = current_schema() and tablename = 'records'"
                )
            ).all()
        definitions = {name: definition for name, definition in rows}
        self.assertIn("ix_records_owner_id_state", definitions)
        self.assertTrue(
            any("WHERE (deleted_at IS NULL)" in value for value in definitions.values())
        )
        self.assertTrue(any("lower(" in value for value in definitions.values()))

        with self.SessionLocal() as session:
            owner = self.account(session)
            first = self.record(
                session,
                owner,
                reference="first",
                code="CaseSensitive",
            )
            self.record_crud_module.RecordCRUD(session).delete(
                first.id,
                actor_id=owner.identifier,
            )
            active = self.record(
                session,
                owner,
                reference="second",
                code="CaseSensitive",
            )
            self.assertIsNotNone(active.id)
            with self.assertRaises(IntegrityError):
                self.record(
                    session,
                    owner,
                    reference="third",
                    code="casesensitive",
                )

    def test_database_computed_column_recalculates(self):
        with self.SessionLocal() as session:
            owner = self.account(session)
            stored = self.record(
                session,
                owner,
                price=Decimal("7.25"),
                quantity=4,
            )
            self.assertEqual(stored.total, Decimal("29.00"))
            stored.quantity = 5
            session.commit()
            session.refresh(stored)
            self.assertEqual(stored.total, Decimal("36.25"))
        with self.engine.connect() as connection:
            generated = connection.scalar(
                text(
                    "select is_generated from information_schema.columns "
                    "where table_name = 'records' and column_name = 'total'"
                )
            )
        self.assertEqual(generated, "ALWAYS")

    def test_encrypted_values_are_ciphertext_in_postgresql(self):
        with self.SessionLocal() as session:
            owner = self.account(session)
            first = self.record(session, owner, secret="same plaintext")
            second = self.record(session, owner, secret="same plaintext")
            identifiers = (first.id, second.id)
        with self.engine.connect() as connection:
            values = connection.execute(
                text("select secret from records order by id")
            ).scalars().all()
        self.assertTrue(all(value.startswith("v1.") for value in values))
        self.assertTrue(all("same plaintext" not in value for value in values))
        self.assertNotEqual(values[0], values[1])
        with self.SessionLocal() as session:
            self.assertEqual(
                [session.get(self.record_module.Record, key).secret for key in identifiers],
                ["same plaintext", "same plaintext"],
            )

    def test_relationship_persistence_is_bidirectional(self):
        with self.SessionLocal() as session:
            admin = self.role_module.Role(name="Admin")
            editor = self.role_module.Role(name="Editor")
            owner = self.account(session, roles=[admin, editor])
            stored = self.record(session, owner)
            owner_id, record_id = owner.identifier, stored.id
        with self.SessionLocal() as session:
            owner = session.get(self.account_module.Account, owner_id)
            stored = session.get(self.record_module.Record, record_id)
            self.assertEqual(
                {role.name.value for role in owner.roles},
                {"Admin", "Editor"},
            )
            self.assertEqual({account.identifier for account in owner.roles[0].accounts}, {owner_id})
            self.assertEqual(stored.owner.identifier, owner_id)
            self.assertEqual([record.id for record in owner.records], [record_id])

    def test_passive_database_cascade_deletes_unloaded_children(self):
        with self.SessionLocal() as session:
            owner = self.account(session)
            stored = self.record(session, owner)
            owner_id, record_id = owner.identifier, stored.id
        self.assertTrue(self.record_module.Record.owner.property.backref[1]["passive_deletes"])
        with self.SessionLocal() as session:
            session.execute(
                delete(self.account_module.Account).where(
                    self.account_module.Account.identifier == owner_id
                )
            )
            session.commit()
        with self.SessionLocal() as session:
            self.assertIsNone(session.get(self.account_module.Account, owner_id))
            self.assertIsNone(session.get(self.record_module.Record, record_id))

    def test_soft_delete_restore_and_version_column_execute(self):
        with self.SessionLocal() as session:
            owner = self.account(session)
            stored = self.record(session, owner)
            crud = self.record_crud_module.RecordCRUD(session)
            self.assertEqual(stored.version_id, 1)
            deleted = crud.delete(stored.id, actor_id=owner.identifier)
            self.assertEqual(deleted.version_id, 2)
            self.assertIsNone(crud.get(stored.id))
            self.assertEqual(crud.list(), [])
            restored = crud.restore(stored.id, actor_id=owner.identifier)
            self.assertEqual(restored.version_id, 3)
            self.assertEqual(restored.updated_by, owner.identifier)
            self.assertEqual(crud.get(stored.id).id, stored.id)

    def test_concurrent_postgresql_update_rejects_stale_version(self):
        with self.SessionLocal() as session:
            owner = self.account(session)
            stored = self.record(session, owner)
            record_id = stored.id
        with self.SessionLocal() as stale_reader:
            stale = stale_reader.get(self.record_module.Record, record_id)
            stale_reader.expunge(stale)
            stale_reader.rollback()
        with self.SessionLocal() as first:
            winner = first.get(self.record_module.Record, record_id)
            winner.quantity = 3
            first.commit()
        stale.quantity = 4
        with self.SessionLocal() as second:
            with self.assertRaises(StaleDataError):
                second.merge(stale)
                second.commit()
            second.rollback()
            self.assertEqual(second.get(self.record_module.Record, record_id).version_id, 2)

    def test_generated_sources_and_registry_remain_unmodified(self):
        current = {
            path.relative_to(self.root).as_posix(): path.read_text(encoding="utf-8")
            for path in self.root.rglob("*.py")
            if path.relative_to(self.root).as_posix() in self.generated_sources
        }
        self.assertEqual(current, self.generated_sources)
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(set(registry), {"Account", "Role", "Record"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
