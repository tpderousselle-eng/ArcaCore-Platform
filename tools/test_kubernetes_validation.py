"""Validate generated Kubernetes resources as deployable infrastructure."""

from contextlib import redirect_stdout
from io import StringIO
import importlib.util
import re
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from tools.core.dockerfile_parser import DockerfileDefinition
from tools.core.kubernetes_parser import KubernetesDefinition
import tools.generate_dockerfile as dockerfile_generator
import tools.generate_kubernetes as kubernetes_generator
from tools.kubernetes_manifest_validation import (
    KUBERNETES_SCHEMA_VERSION,
    kubectl_client_dry_run,
    load_validated_manifest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class KubernetesHealthValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository_backend_before = _snapshot(REPOSITORY_ROOT / "backend")
        cls.temporary_directory = TemporaryDirectory(prefix="arcacore-kubernetes-")
        cls.root = Path(cls.temporary_directory.name)
        cls.definition = KubernetesDefinition(
            name="arcacore-prod",
            namespace="arcacore-prod",
            api_image="ghcr.io/arcacentum/arcacore-api:25.5",
            api_port=8080,
            service_port=80,
            replicas=4,
            database_image="postgres:16-alpine",
            database_port=5433,
            storage_size="20Gi",
            secret_name="arcacore-prod-secrets",
        )
        cls._write_application_contract()
        with patch.object(
            dockerfile_generator, "PROJECT_ROOT", cls.root
        ), patch.object(
            kubernetes_generator, "PROJECT_ROOT", cls.root
        ), redirect_stdout(StringIO()):
            cls.dockerfile_path = dockerfile_generator.generate_dockerfile(
                DockerfileDefinition(port=cls.definition.api_port)
            )
            cls.manifest_path = kubernetes_generator.generate_kubernetes(cls.definition)
        cls.generated_before = _snapshot(cls.root)
        cls.validated = load_validated_manifest(cls.manifest_path)

    @classmethod
    def tearDownClass(cls):
        cls.temporary_directory.cleanup()

    @classmethod
    def _write_application_contract(cls):
        backend = cls.root / "backend"
        backend.mkdir(parents=True)
        (backend / "__init__.py").write_text("", encoding="utf-8")
        (backend / "main.py").write_text(
            "from fastapi import FastAPI\n\n"
            "app = FastAPI(title='ArcaCore Kubernetes Validation')\n\n"
            "@app.get('/health')\n"
            "def health():\n"
            "    return {'status': 'ok'}\n",
            encoding="utf-8",
        )
        (backend / "requirements.txt").write_text(
            "fastapi==0.141.1\n"
            "uvicorn==0.52.4\n",
            encoding="utf-8",
        )

    def resource(self, kind: str, suffix: str) -> dict:
        return self.validated.resource(kind, f"{self.definition.name}{suffix}")

    def test_yaml_and_every_resource_pass_strict_kubernetes_schema(self):
        self.assertEqual(len(self.validated.documents), 7)
        self.assertEqual(
            self.validated.schema_versions,
            ("1.36",) * len(self.validated.documents),
        )
        self.assertEqual(KUBERNETES_SCHEMA_VERSION, "1.36.0")
        self.assertEqual(
            [document["kind"] for document in self.validated.documents],
            [
                "Namespace",
                "ConfigMap",
                "Deployment",
                "Service",
                "StatefulSet",
                "Service",
                "PersistentVolumeClaim",
            ],
        )

    def test_api_deployment_selectors_image_replicas_and_port_align(self):
        deployment = self.resource("Deployment", "-api")
        spec = deployment["spec"]
        pod_spec = spec["template"]["spec"]
        container = pod_spec["containers"][0]
        self.assertEqual(spec["replicas"], 4)
        self.assertEqual(spec["selector"]["matchLabels"], spec["template"]["metadata"]["labels"])
        self.assertEqual(container["name"], "api")
        self.assertEqual(container["image"], self.definition.api_image)
        self.assertEqual(
            container["ports"],
            [{"name": "http", "containerPort": 8080, "protocol": "TCP"}],
        )
        self.assertIn("requests", container["resources"])
        self.assertIn("limits", container["resources"])

    def test_api_service_selects_deployment_and_targets_named_port(self):
        deployment = self.resource("Deployment", "-api")
        service = self.resource("Service", "-api")
        self.assertEqual(service["spec"]["type"], "ClusterIP")
        self.assertEqual(
            service["spec"]["selector"],
            deployment["spec"]["template"]["metadata"]["labels"],
        )
        self.assertEqual(
            service["spec"]["ports"],
            [{"name": "http", "port": 80, "targetPort": "http", "protocol": "TCP"}],
        )

    def test_postgresql_statefulset_service_and_storage_are_consistent(self):
        stateful_set = self.resource("StatefulSet", "-postgres")
        service = self.resource("Service", "-postgres")
        claim = self.resource("PersistentVolumeClaim", "-postgres-data")
        spec = stateful_set["spec"]
        container = spec["template"]["spec"]["containers"][0]
        volume = spec["template"]["spec"]["volumes"][0]
        self.assertEqual(spec["serviceName"], service["metadata"]["name"])
        self.assertEqual(service["spec"]["clusterIP"], "None")
        self.assertEqual(service["spec"]["selector"], spec["template"]["metadata"]["labels"])
        self.assertEqual(container["ports"][0]["containerPort"], 5433)
        self.assertEqual(service["spec"]["ports"][0]["port"], 5433)
        self.assertEqual(volume["persistentVolumeClaim"]["claimName"], claim["metadata"]["name"])
        self.assertEqual(claim["spec"]["resources"]["requests"]["storage"], "20Gi")

    def test_environment_uses_configmap_and_secret_references_only(self):
        deployment = self.resource("Deployment", "-api")
        stateful_set = self.resource("StatefulSet", "-postgres")
        api = deployment["spec"]["template"]["spec"]["containers"][0]
        postgres = stateful_set["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(
            api["env"],
            [
                {
                    "name": "DATABASE_URL",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": self.definition.secret_name,
                            "key": "database-url",
                        }
                    },
                }
            ],
        )
        self.assertEqual(
            postgres["envFrom"],
            [{"configMapRef": {"name": f"{self.definition.name}-database-config"}}],
        )
        self.assertEqual(
            postgres["env"][0]["valueFrom"]["secretKeyRef"],
            {"name": self.definition.secret_name, "key": "postgres-password"},
        )
        self.assertNotIn("Secret", {item["kind"] for item in self.validated.documents})
        self.assertNotIn("value", api["env"][0])
        self.assertNotIn("value", postgres["env"][0])

    def test_dockerfile_and_kubernetes_container_ports_match(self):
        dockerfile = self.dockerfile_path.read_text(encoding="utf-8")
        deployment = self.resource("Deployment", "-api")
        container_port = deployment["spec"]["template"]["spec"]["containers"][0][
            "ports"
        ][0]["containerPort"]
        self.assertEqual(container_port, self.definition.api_port)
        self.assertIn(f"EXPOSE {container_port}", dockerfile)
        self.assertIn(f'"--port", "{container_port}"', dockerfile)
        self.assertIn(f"http://127.0.0.1:{container_port}/health", dockerfile)

    def test_readiness_liveness_and_startup_probes_match_live_health_route(self):
        deployment = self.resource("Deployment", "-api")
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        probe_paths = {
            container[name]["httpGet"]["path"]
            for name in ("startupProbe", "readinessProbe", "livenessProbe")
        }
        probe_ports = {
            container[name]["httpGet"]["port"]
            for name in ("startupProbe", "readinessProbe", "livenessProbe")
        }
        module_path = self.root / "backend" / "main.py"
        spec = importlib.util.spec_from_file_location(
            "arcacore_kubernetes_health_fixture", module_path
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(module)
        with TestClient(module.app) as client:
            response = client.get("/health")
        self.assertEqual(probe_paths, {"/health"})
        self.assertEqual(probe_ports, {"http"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_all_object_names_and_namespaces_are_dns_safe(self):
        for document in self.validated.documents:
            with self.subTest(kind=document["kind"], name=document["metadata"]["name"]):
                name = document["metadata"]["name"]
                self.assertLessEqual(len(name), 63)
                self.assertIsNotNone(DNS_LABEL.fullmatch(name))
                namespace = document["metadata"].get("namespace")
                if namespace is not None:
                    self.assertIsNotNone(DNS_LABEL.fullmatch(namespace))

    def test_configurable_replicas_and_regeneration_are_deterministic(self):
        with TemporaryDirectory(prefix="arcacore-replicas-") as directory:
            root = Path(directory)
            definition = KubernetesDefinition(name="replica-check", replicas=7)
            with patch.object(
                kubernetes_generator, "PROJECT_ROOT", root
            ), redirect_stdout(StringIO()):
                first = kubernetes_generator.generate_kubernetes(definition)
                first_bytes = first.read_bytes()
                second = kubernetes_generator.generate_kubernetes(definition)
            validated = load_validated_manifest(second)
            deployment = validated.resource("Deployment", "replica-check-api")
            stateful_set = validated.resource("StatefulSet", "replica-check-postgres")
            self.assertEqual(first_bytes, second.read_bytes())
            self.assertEqual(deployment["spec"]["replicas"], 7)
            self.assertEqual(stateful_set["spec"]["replicas"], 1)

    def test_kubectl_client_dry_run_when_available(self):
        result = kubectl_client_dry_run(self.manifest_path)
        if result is not None:
            self.assertEqual(len(result), 7)
            self.assertIn(f"deployment.apps/{self.definition.name}-api", result)
            self.assertIn(f"statefulset.apps/{self.definition.name}-postgres", result)

    def test_validation_never_rewrites_generated_files_or_repository_backend(self):
        self.assertEqual(_snapshot(self.root), self.generated_before)
        self.assertEqual(_snapshot(REPOSITORY_ROOT / "backend"), self.repository_backend_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
