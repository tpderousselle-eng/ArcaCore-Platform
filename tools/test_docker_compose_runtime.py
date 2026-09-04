"""Validate generated Docker and Compose files, including an opt-in real runtime."""

from contextlib import ExitStack, redirect_stdout
import hashlib
from io import StringIO
import os
from pathlib import Path
import secrets
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

from tools import generate as pipeline
from tools.core.compose_parser import ComposeDefinition
from tools.core.dockerfile_parser import DockerfileDefinition
from tools.docker_compose_test_runtime import (
    DOCKER_RUNTIME_ENV,
    DockerComposeTestRuntime,
    docker_capability,
    docker_runtime_requested,
)
import tools.generate_compose as compose_generator
import tools.generate_crud as crud_generator
import tools.generate_dockerfile as dockerfile_generator
import tools.generate_model as model_generator
import tools.generate_router as router_generator
import tools.generate_schema as schema_generator
import tools.generate_service as service_generator
import tools.registry.registry as registry_module


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GENERATORS = (
    model_generator,
    schema_generator,
    crud_generator,
    service_generator,
    router_generator,
)
MODULES = (
    ("User", ("name:str:min_length=2:length=80",)),
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
GENERATED_LAYERS = ("models", "schemas", "crud", "services", "api")


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _snapshot(root: Path, pattern: str = "*") -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob(pattern)
        if path.is_file()
    }


class DockerComposeGeneratedRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository_backend_before = _snapshot(REPOSITORY_ROOT / "backend")
        cls.temporary_directory = TemporaryDirectory(prefix="arcacore-compose-")
        cls.root = Path(cls.temporary_directory.name)
        cls.registry_path = cls.root / "tools" / "registry" / "models.json"
        cls.registry_path.parent.mkdir(parents=True, exist_ok=True)
        cls.project_name = f"arcacore25_4_{uuid4().hex[:10]}"
        cls.api_port = _free_port()
        cls.database_port = _free_port()
        while cls.database_port == cls.api_port:
            cls.database_port = _free_port()
        cls.password = secrets.token_urlsafe(32)

        with ExitStack() as stack:
            for generator in GENERATORS:
                stack.enter_context(patch.object(generator, "PROJECT_ROOT", cls.root))
            stack.enter_context(
                patch.object(registry_module, "REGISTRY_PATH", cls.registry_path)
            )
            stack.enter_context(redirect_stdout(StringIO()))
            for name, fields in MODULES:
                pipeline.generate_module(name, list(fields))

        cls._write_application_scaffold()
        cls.dockerfile_definition = DockerfileDefinition()
        cls.compose_definition = ComposeDefinition(
            project_name=cls.project_name,
            api_port=cls.api_port,
            database_port=cls.database_port,
            database_image="postgres:16-alpine",
        )
        with patch.object(
            dockerfile_generator, "PROJECT_ROOT", cls.root
        ), patch.object(
            compose_generator, "PROJECT_ROOT", cls.root
        ), redirect_stdout(StringIO()):
            dockerfile_generator.generate_dockerfile(cls.dockerfile_definition)
            compose_generator.generate_compose(cls.compose_definition)

        (cls.root / ".env").write_text(
            "POSTGRES_USER=arcacore\n"
            f"POSTGRES_PASSWORD={cls.password}\n"
            "POSTGRES_DB=arcacore\n",
            encoding="utf-8",
        )
        cls.generated_before = _snapshot(cls.root)
        cls.runtime = DockerComposeTestRuntime(
            root=cls.root,
            project_name=cls.project_name,
            api_port=cls.api_port,
            secrets=(cls.password,),
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    @classmethod
    def _write_application_scaffold(cls):
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
            "import os\n\n"
            "from sqlalchemy import create_engine\n"
            "from sqlalchemy.orm import sessionmaker\n\n"
            "DATABASE_URL = os.environ['DATABASE_URL']\n"
            "engine = create_engine(DATABASE_URL, pool_pre_ping=True)\n"
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
            "from fastapi import FastAPI\n"
            "from sqlalchemy import text\n\n"
            "from backend.app.api.record import router as record_router\n"
            "from backend.app.api.user import router as user_router\n"
            "from backend.app.db.base import Base\n"
            "from backend.app.db.session import engine\n"
            "from backend.app.models.record import Record\n"
            "from backend.app.models.user import User\n\n"
            "Base.metadata.create_all(bind=engine)\n\n"
            "app = FastAPI(title='ArcaCore Container Runtime')\n"
            "app.include_router(user_router)\n"
            "app.include_router(record_router)\n\n"
            "@app.get('/health')\n"
            "def health():\n"
            "    with engine.connect() as connection:\n"
            "        connection.execute(text('SELECT 1'))\n"
            "    return {'status': 'ok', 'database': 'connected'}\n",
            encoding="utf-8",
        )
        (cls.root / "backend" / "requirements.txt").write_text(
            "fastapi==0.115.12\n"
            "uvicorn==0.34.2\n"
            "SQLAlchemy==2.0.41\n"
            "pydantic==2.11.5\n"
            "psycopg2-binary==2.9.12\n",
            encoding="utf-8",
        )

    def test_all_generated_layers_and_build_inputs_are_real_files(self):
        expected = {
            f"backend/app/{layer}/{module.lower()}.py"
            for layer in GENERATED_LAYERS
            for module, _fields in MODULES
        }
        actual = {
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*.py")
        }
        self.assertTrue(expected.issubset(actual))
        self.assertTrue((self.root / "Dockerfile").is_file())
        self.assertTrue((self.root / "docker-compose.yml").is_file())
        self.assertTrue((self.root / "backend" / "requirements.txt").is_file())
        for path in self.root.rglob("*.py"):
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_deployment_regeneration_is_byte_identical(self):
        dockerfile = (self.root / "Dockerfile").read_bytes()
        compose = (self.root / "docker-compose.yml").read_bytes()
        with patch.object(
            dockerfile_generator, "PROJECT_ROOT", self.root
        ), patch.object(
            compose_generator, "PROJECT_ROOT", self.root
        ), redirect_stdout(StringIO()):
            dockerfile_generator.generate_dockerfile(self.dockerfile_definition)
            compose_generator.generate_compose(self.compose_definition)
        self.assertEqual((self.root / "Dockerfile").read_bytes(), dockerfile)
        self.assertEqual((self.root / "docker-compose.yml").read_bytes(), compose)

    def test_generated_compose_connects_api_postgresql_health_and_storage(self):
        dockerfile = (self.root / "Dockerfile").read_text(encoding="utf-8")
        compose = (self.root / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("COPY backend/requirements.txt", dockerfile)
        self.assertIn("COPY --chown=arcacore:arcacore backend ./backend", dockerfile)
        self.assertIn("USER arcacore", dockerfile)
        self.assertIn("backend.main:app", dockerfile)
        self.assertIn("DATABASE_URL", compose)
        self.assertIn("@postgres:5432/", compose)
        self.assertIn("condition: service_healthy", compose)
        self.assertIn("postgres_data:/var/lib/postgresql/data", compose)
        self.assertIn(f'"{self.api_port}:8000"', compose)
        self.assertIn(f'"{self.database_port}:5432"', compose)

    def test_health_endpoint_is_a_database_probe(self):
        main = (self.root / "backend" / "main.py").read_text(encoding="utf-8")
        session = (
            self.root / "backend" / "app" / "db" / "session.py"
        ).read_text(encoding="utf-8")
        self.assertIn("connection.execute(text('SELECT 1'))", main)
        self.assertIn("'database': 'connected'", main)
        self.assertIn("os.environ['DATABASE_URL']", session)
        self.assertIn("app.include_router(user_router)", main)
        self.assertIn("app.include_router(record_router)", main)

    def test_runtime_secret_is_external_to_generated_artifacts(self):
        inspected = [
            self.root / "Dockerfile",
            self.root / "docker-compose.yml",
            *self.root.rglob("*.py"),
        ]
        for path in inspected:
            self.assertNotIn(self.password, path.read_text(encoding="utf-8"))
        compose = (self.root / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("${POSTGRES_PASSWORD:?", compose)
        self.assertNotIn("POSTGRES_PASSWORD: arcacore", compose)

    def test_repository_backend_is_never_modified(self):
        self.assertEqual(_snapshot(REPOSITORY_ROOT / "backend"), self.repository_backend_before)

    def test_real_generated_application_in_docker_compose(self):
        if not docker_runtime_requested():
            self.skipTest(
                f"Set {DOCKER_RUNTIME_ENV}=1 to run the real Docker Compose contract."
            )
        capable, reason = docker_capability()
        if not capable:
            self.fail(f"{DOCKER_RUNTIME_ENV} requested, but {reason}.")

        cleanup_error = None
        try:
            self.runtime.validate_configuration()
            self.runtime.build()
            self.runtime.start()
            image_id = self.runtime.api_image_id()
            self.assertTrue(image_id, "Compose did not report a built API image.")
            self.assertNotIn(self.password, self.runtime.image_history(image_id))

            self.assertEqual(self.runtime.wait_until_healthy()["database"], "connected")
            self.assertEqual(self.runtime.database_probe(), "1")
            self.assertEqual(self.runtime.running_services(), {"api", "postgres"})

            user = self.runtime.request_json(
                "POST", "/users", {"name": "Container Owner"}
            )
            record = self.runtime.request_json(
                "POST",
                "/records",
                {"owner_id": user["id"], "title": "Persistent record", "quantity": 2},
                headers={"X-Actor-ID": str(user["id"])},
            )
            self.assertEqual(record["total"], 4)
            self.assertEqual(
                self.runtime.request_json("GET", f"/records/{record['id']}")["id"],
                record["id"],
            )

            self.runtime.restart_api()
            self.runtime.wait_until_healthy()
            self.assertEqual(
                self.runtime.request_json("GET", f"/records/{record['id']}")["id"],
                record["id"],
            )

            self.runtime.stop_preserving_storage()
            self.runtime.start()
            self.runtime.wait_until_healthy()
            self.assertEqual(
                self.runtime.request_json("GET", f"/records/{record['id']}")["id"],
                record["id"],
            )
        finally:
            try:
                self.runtime.clean()
            except Exception as error:
                cleanup_error = error
        if cleanup_error is not None:
            self.fail(f"Docker Compose cleanup failed: {cleanup_error}")
        self.assertEqual(_snapshot(self.root), self.generated_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
