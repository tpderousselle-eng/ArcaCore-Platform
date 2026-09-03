"""Exercise health checks across generated deployment outputs."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.core.compose_parser import ComposeDefinition
from tools.core.dockerfile_parser import DockerfileDefinition
from tools.core.kubernetes_parser import KubernetesDefinition
from tools.generate_compose import generate_compose
from tools.generate_dockerfile import generate_dockerfile
from tools.generate_kubernetes import generate_kubernetes
import tools.generate_compose as compose_generator
import tools.generate_dockerfile as dockerfile_generator
import tools.generate_kubernetes as kubernetes_generator


class HealthCheckSmokeTest(unittest.TestCase):
    def render_sources(
        self,
        dockerfile_definition=None,
        compose_definition=None,
        kubernetes_definition=None,
    ):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(dockerfile_generator, "PROJECT_ROOT", root), patch.object(
                compose_generator, "PROJECT_ROOT", root
            ), patch.object(
                kubernetes_generator, "PROJECT_ROOT", root
            ), redirect_stdout(
                StringIO()
            ):
                dockerfile = generate_dockerfile(dockerfile_definition).read_text(
                    encoding="utf-8"
                )
                compose = generate_compose(compose_definition).read_text(
                    encoding="utf-8"
                )
                kubernetes = generate_kubernetes(kubernetes_definition).read_text(
                    encoding="utf-8"
                )
        return dockerfile, compose, kubernetes

    def test_dockerfile_checks_existing_health_endpoint(self):
        dockerfile, _, _ = self.render_sources()
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("http://127.0.0.1:8000/health", dockerfile)
        self.assertIn("urllib.request.urlopen", dockerfile)

    def test_dockerfile_healthcheck_uses_configured_port(self):
        dockerfile, _, _ = self.render_sources(
            dockerfile_definition=DockerfileDefinition(port=9000)
        )
        self.assertIn("http://127.0.0.1:9000/health", dockerfile)
        self.assertNotIn("http://127.0.0.1:8000/health", dockerfile)

    def test_dockerfile_healthcheck_needs_no_extra_binary(self):
        dockerfile, _, _ = self.render_sources()
        self.assertNotIn("curl", dockerfile.lower())
        self.assertNotIn("wget", dockerfile.lower())
        self.assertIn("--start-period=10s", dockerfile)

    def test_compose_checks_api_endpoint(self):
        _, compose, _ = self.render_sources()
        self.assertIn("http://127.0.0.1:8000/health", compose)
        self.assertIn('test: ["CMD", "python", "-c"', compose)

    def test_compose_api_check_uses_container_port(self):
        _, compose, _ = self.render_sources(
            compose_definition=ComposeDefinition(container_port=9000)
        )
        self.assertIn("http://127.0.0.1:9000/health", compose)

    def test_compose_checks_postgres_with_runtime_environment(self):
        _, compose, _ = self.render_sources()
        self.assertIn("pg_isready", compose)
        self.assertIn("$${POSTGRES_USER}", compose)
        self.assertIn("$${POSTGRES_DB}", compose)

    def test_compose_waits_for_healthy_postgres(self):
        _, compose, _ = self.render_sources()
        self.assertIn("condition: service_healthy", compose)
        self.assertLess(compose.index("healthcheck:"), compose.index("depends_on:"))

    def test_kubernetes_api_has_startup_readiness_and_liveness_probes(self):
        _, _, kubernetes = self.render_sources()
        self.assertEqual(kubernetes.count("startupProbe:"), 1)
        self.assertEqual(kubernetes.count("readinessProbe:"), 2)
        self.assertEqual(kubernetes.count("livenessProbe:"), 2)

    def test_kubernetes_api_probes_use_named_port_and_health_path(self):
        _, _, kubernetes = self.render_sources()
        self.assertEqual(kubernetes.count("path: /health"), 3)
        self.assertEqual(kubernetes.count("port: http"), 3)

    def test_kubernetes_postgres_probes_use_pg_isready(self):
        _, _, kubernetes = self.render_sources()
        self.assertEqual(kubernetes.count("- pg_isready"), 2)
        self.assertEqual(kubernetes.count("- -U"), 2)
        self.assertEqual(kubernetes.count("- -d"), 2)
        self.assertEqual(kubernetes.count("- -p"), 3)

    def test_kubernetes_postgres_check_uses_configured_port(self):
        _, _, kubernetes = self.render_sources(
            kubernetes_definition=KubernetesDefinition(database_port=5544)
        )
        self.assertEqual(kubernetes.count("5544"), 5)
        self.assertNotIn("containerPort: 5432", kubernetes)

    def test_health_checks_do_not_embed_credentials(self):
        dockerfile, compose, kubernetes = self.render_sources()
        combined = "\n".join((dockerfile, compose, kubernetes))
        self.assertNotIn("REPLACE_ME", combined)
        self.assertNotIn("secret_key", combined.lower())
        self.assertNotIn("kind: Secret", kubernetes)

    def test_all_generators_preserve_backend_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            backend = root / "backend"
            backend.mkdir()
            marker = backend / "main.py"
            marker.write_text("unchanged\n", encoding="utf-8")
            with patch.object(dockerfile_generator, "PROJECT_ROOT", root), patch.object(
                compose_generator, "PROJECT_ROOT", root
            ), patch.object(
                kubernetes_generator, "PROJECT_ROOT", root
            ), redirect_stdout(
                StringIO()
            ):
                generate_dockerfile()
                generate_compose()
                generate_kubernetes()
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
