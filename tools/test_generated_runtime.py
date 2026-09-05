"""Execute an unmodified generated FastAPI application in a temporary root."""

from contextlib import ExitStack, redirect_stdout
from io import StringIO
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from tools import generate as pipeline
import tools.generate_crud as crud_generator
import tools.generate_model as model_generator
import tools.generate_router as router_generator
import tools.generate_schema as schema_generator
import tools.generate_service as service_generator
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
        "User",
        ("name:str:min_length=2:length=80",),
    ),
    (
        "Record",
        (
            "owner_id:int:fk=users.id:one_to_many(User,records)",
            "title:str:min_length=2:length=120",
            "quantity:int:min=1",
            "total:int:computed=quantity * 2",
            "audit_fields(users.id,int)",
            "version_column",
            "soft_delete",
        ),
    ),
)


class GeneratedRuntimeSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = TemporaryDirectory()
        cls.root = Path(cls.temporary_directory.name)
        cls.registry_path = cls.root / "tools" / "registry" / "models.json"
        cls.registry_path.parent.mkdir(parents=True, exist_ok=True)

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

        cls.main_module = importlib.import_module("backend.main")
        cls.base_module = importlib.import_module("backend.app.db.base")
        cls.session_module = importlib.import_module("backend.app.db.session")
        cls.user_module = importlib.import_module("backend.app.models.user")
        cls.record_module = importlib.import_module("backend.app.models.record")
        cls.record_schema_module = importlib.import_module("backend.app.schemas.record")

    @classmethod
    def tearDownClass(cls):
        cls.session_module.engine.dispose()
        if str(cls.root) in sys.path:
            sys.path.remove(str(cls.root))
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)
        sys.modules.update(cls.previous_backend_modules)
        cls.temporary_directory.cleanup()

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
            "from sqlalchemy.orm import declarative_base\n\n"
            "Base = declarative_base()\n",
            encoding="utf-8",
        )
        (cls.root / "backend" / "app" / "db" / "session.py").write_text(
            "from sqlalchemy import create_engine\n"
            "from sqlalchemy.orm import sessionmaker\n"
            "from sqlalchemy.pool import StaticPool\n\n"
            "engine = create_engine(\n"
            "    'sqlite://',\n"
            "    connect_args={'check_same_thread': False},\n"
            "    poolclass=StaticPool,\n"
            ")\n"
            "SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\n\n"
            "def get_db():\n"
            "    db = SessionLocal()\n"
            "    try:\n"
            "        yield db\n"
            "    finally:\n"
            "        db.close()\n",
            encoding="utf-8",
        )
        (cls.root / "backend" / "main.py").write_text(
            "from fastapi import FastAPI\n\n"
            "from backend.app.api.record import router as record_router\n"
            "from backend.app.api.user import router as user_router\n"
            "from backend.app.db.base import Base\n"
            "from backend.app.db.session import engine\n"
            "from backend.app.models.record import Record\n"
            "from backend.app.models.user import User\n\n"
            "Base.metadata.create_all(bind=engine)\n\n"
            "app = FastAPI(title='ArcaCore Generated Runtime')\n"
            "@app.middleware('http')\n"
            "async def authenticate(request, call_next):\n"
            "    if request.headers.get('Authorization') == 'Bearer test-token':\n"
            "        request.state.arcacore_principal_id = 1\n"
            "        request.state.arcacore_scopes = {'user:*', 'record:*'}\n"
            "    elif request.headers.get('Authorization') == 'Bearer read-token':\n"
            "        request.state.arcacore_principal_id = 2\n"
            "        request.state.arcacore_scopes = {'record:read'}\n"
            "    return await call_next(request)\n\n"
            "app.include_router(user_router)\n"
            "app.include_router(record_router)\n\n"
            "@app.get('/health')\n"
            "def health():\n"
            "    return {'status': 'ok'}\n",
            encoding="utf-8",
        )

    def setUp(self):
        self.base_module.Base.metadata.drop_all(bind=self.session_module.engine)
        self.base_module.Base.metadata.create_all(bind=self.session_module.engine)
        self.client = TestClient(
            self.main_module.app, headers={"Authorization": "Bearer test-token"}
        )

    def tearDown(self):
        self.client.close()

    def create_user(self, name="Runtime Owner"):
        response = self.client.post("/users", json={"name": name})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def create_record(self, user_id, **overrides):
        payload = {
            "owner_id": user_id,
            "title": "Generated record",
            "quantity": 2,
            **overrides,
        }
        response = self.client.post(
            "/records",
            json=payload,
            headers={"X-Actor-ID": "999999"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_generated_modules_import_and_metadata_initialize(self):
        self.assertEqual(
            set(self.base_module.Base.metadata.tables),
            {"users", "records"},
        )
        self.assertTrue(hasattr(self.record_schema_module, "RecordCreate"))
        self.assertTrue(hasattr(self.record_schema_module, "RecordUpdate"))
        self.assertTrue(hasattr(self.record_schema_module, "RecordResponse"))
        self.assertEqual(
            self.record_module.Record.owner.property.mapper.class_,
            self.user_module.User,
        )

    def test_fastapi_starts_and_generated_routers_register(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        paths = self.main_module.app.openapi()["paths"]
        self.assertEqual(
            set(paths["/records"]),
            {"get", "post"},
        )
        self.assertEqual(
            set(paths["/records/{item_id}"]),
            {"get", "patch", "delete"},
        )
        self.assertIn("post", paths["/records/{item_id}/restore"])

    def test_generated_routes_fail_closed_and_enforce_scopes(self):
        unauthenticated = self.client.get(
            "/records", headers={"Authorization": ""}
        )
        self.assertEqual(unauthenticated.status_code, 401)
        read_only_write = self.client.post(
            "/records",
            json={"owner_id": 1, "title": "Denied", "quantity": 2},
            headers={"Authorization": "Bearer read-token"},
        )
        self.assertEqual(read_only_write.status_code, 403)

    def test_create_read_and_list_execute_through_http(self):
        user = self.create_user()
        created = self.create_record(user["id"])
        self.assertEqual(created["created_by"], user["id"])
        self.assertEqual(created["total"], 4)
        fetched = self.client.get(f"/records/{created['id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), created)
        listed = self.client.get("/records")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json(), [created])

    def test_update_recalculates_computed_field_and_increments_version(self):
        user = self.create_user()
        created = self.create_record(user["id"])
        updated = self.client.patch(
            f"/records/{created['id']}",
            json={"title": "Updated record", "quantity": 3},
            headers={"X-Actor-ID": str(user["id"])},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        body = updated.json()
        self.assertEqual(
            (body["title"], body["quantity"], body["total"]), ("Updated record", 3, 6)
        )
        self.assertEqual(body["version_id"], 2)
        self.assertEqual(body["updated_by"], user["id"])

    def test_soft_delete_filters_reads_and_restore_recovers_row(self):
        user = self.create_user()
        created = self.create_record(user["id"])
        deleted = self.client.delete(
            f"/records/{created['id']}",
            headers={"X-Actor-ID": str(user["id"])},
        )
        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertEqual(self.client.get(f"/records/{created['id']}").status_code, 404)
        with self.session_module.SessionLocal() as session:
            stored = session.get(self.record_module.Record, created["id"])
            self.assertIsNotNone(stored.deleted_at)
            self.assertEqual(stored.version_id, 2)
        restored = self.client.post(
            f"/records/{created['id']}/restore",
            headers={"X-Actor-ID": str(user["id"])},
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["version_id"], 3)
        self.assertEqual(self.client.get(f"/records/{created['id']}").status_code, 200)

    def test_non_soft_delete_removes_row(self):
        user = self.create_user()
        response = self.client.delete(f"/users/{user['id']}")
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.client.get(f"/users/{user['id']}").status_code, 404)
        with self.session_module.SessionLocal() as session:
            self.assertIsNone(session.get(self.user_module.User, user["id"]))

    def test_validation_and_managed_fields_return_422(self):
        user = self.create_user()
        invalid_quantity = self.client.post(
            "/records",
            json={"owner_id": user["id"], "title": "Valid", "quantity": 0},
            headers={"X-Actor-ID": str(user["id"])},
        )
        self.assertEqual(invalid_quantity.status_code, 422)
        computed_input = self.client.post(
            "/records",
            json={
                "owner_id": user["id"],
                "title": "Valid",
                "quantity": 2,
                "total": 999,
            },
            headers={"X-Actor-ID": str(user["id"])},
        )
        self.assertEqual(computed_input.status_code, 422)
        missing_actor = self.client.post(
            "/records",
            json={"owner_id": user["id"], "title": "Valid", "quantity": 2},
            headers={"Authorization": ""},
        )
        self.assertEqual(missing_actor.status_code, 401)

    def test_relationship_foreign_key_serializes_and_navigation_resolves(self):
        user = self.create_user("Relationship Owner")
        record = self.create_record(user["id"])
        self.assertEqual(record["owner_id"], user["id"])
        with self.session_module.SessionLocal() as session:
            stored = session.get(self.record_module.Record, record["id"])
            self.assertEqual(stored.owner.name, "Relationship Owner")
            self.assertEqual([item.id for item in stored.owner.records], [record["id"]])

    def test_audit_and_version_fields_execute_without_payload_access(self):
        user = self.create_user()
        created = self.create_record(user["id"])
        self.assertEqual(created["created_by"], user["id"])
        self.assertIsNone(created["updated_by"])
        self.assertEqual(created["version_id"], 1)
        self.assertIn("created_at", created)
        self.assertIn("updated_at", created)
        rejected = self.client.patch(
            f"/records/{created['id']}",
            json={"version_id": 99, "updated_by": user["id"]},
            headers={"X-Actor-ID": str(user["id"])},
        )
        self.assertEqual(rejected.status_code, 422)

    def test_runtime_never_rewrites_generated_source(self):
        current = {
            path.relative_to(self.root).as_posix(): path.read_text(encoding="utf-8")
            for path in self.root.rglob("*.py")
            if path.relative_to(self.root).as_posix() in self.generated_sources
        }
        self.assertEqual(current, self.generated_sources)
        registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        self.assertEqual(set(registry), {"User", "Record"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
