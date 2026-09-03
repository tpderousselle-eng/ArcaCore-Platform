"""Exercise deterministic Kubernetes generation without changing backend files."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from tools import __main__ as cli
from tools.core.kubernetes_parser import (
    KubernetesDefinition,
    parse_kubernetes_options,
)
from tools.generate_kubernetes import generate_kubernetes
import tools.generate_kubernetes as generator


class KubernetesSmokeTest(unittest.TestCase):
    def test_default_definition_and_render_context(self):
        with TemporaryDirectory() as directory, patch.object(
            generator, "PROJECT_ROOT", Path(directory)
        ), patch.object(generator, "render_template") as render:
            output = generate_kubernetes()
        self.assertEqual(
            output.as_posix().split("/")[-2:], ["kubernetes", "arcacore.yaml"]
        )
        self.assertEqual(
            render.call_args.kwargs,
            {
                "template_name": "kubernetes.j2",
                "output_path": output,
                "name": "arcacore",
                "namespace": "arcacore",
                "api_image": "arcacore-api:latest",
                "api_port": 8000,
                "service_port": 80,
                "replicas": 2,
                "database_image": "postgres:16",
                "database_port": 5432,
                "storage_size": "10Gi",
                "secret_name": "arcacore-secrets",
            },
        )

    def test_custom_options_and_order(self):
        arguments = [
            "--database-image",
            "postgres:17-alpine",
            "--storage-size",
            "20Gi",
            "--replicas",
            "3",
            "--service-port",
            "8080",
            "--api-port",
            "9000",
            "--database-port",
            "5544",
            "--secret-name",
            "arca-secrets",
            "--api-image",
            "ghcr.io/example/api:1.2.3",
            "--namespace",
            "production",
            "--name",
            "arca-api",
        ]
        definition = parse_kubernetes_options(arguments)
        reordered = parse_kubernetes_options(
            list(sum(zip(arguments[::2][::-1], arguments[1::2][::-1]), ()))
        )
        self.assertEqual(definition, reordered)
        self.assertEqual((definition.api_port, definition.replicas), (9000, 3))

    def test_invalid_metadata_fails_before_rendering(self):
        invalid = (
            {"name": "ArcaCore"},
            {"name": "-arcacore"},
            {"name": "a" * 48},
            {"namespace": "arcacore_qa"},
            {"secret_name": "secret."},
            {"api_image": "api:latest;echo"},
            {"database_image": ""},
            {"api_port": 0},
            {"service_port": 65536},
            {"database_port": True},
            {"replicas": 0},
            {"replicas": 101},
            {"storage_size": "10GB"},
            {"storage_size": "0Gi"},
        )
        for values in invalid:
            with self.subTest(values=values), patch.object(
                generator, "render_template"
            ) as render:
                with self.assertRaises(ValueError):
                    KubernetesDefinition(**values)
                render.assert_not_called()

    def test_invalid_cli_options_fail_before_generation(self):
        invalid = (
            ["--unknown", "value"],
            ["--replicas"],
            ["--replicas", "many"],
            ["--replicas", "2", "--replicas", "3"],
            ["--api-image", "--api-port", "8000"],
        )
        for arguments in invalid:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                parse_kubernetes_options(arguments)

    def test_direct_generator_revalidates_metadata(self):
        invalid = SimpleNamespace(name="arcacore")
        with patch.object(generator, "render_template") as render:
            with self.assertRaises(ValueError):
                generate_kubernetes(invalid)
            render.assert_not_called()

    def test_real_generation_writes_only_manifest(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            backend = root / "backend"
            backend.mkdir()
            marker = backend / "main.py"
            marker.write_text("unchanged\n", encoding="utf-8")
            with patch.object(generator, "PROJECT_ROOT", root), redirect_stdout(
                StringIO()
            ):
                output = generate_kubernetes()
            self.assertEqual(output, root / "kubernetes" / "arcacore.yaml")
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged\n")
            self.assertEqual(
                sorted(path.relative_to(root).as_posix() for path in root.rglob("*")),
                [
                    "backend",
                    "backend/main.py",
                    "kubernetes",
                    "kubernetes/arcacore.yaml",
                ],
            )

    def test_regeneration_is_a_complete_deterministic_replacement(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "kubernetes" / "arcacore.yaml"
            output.parent.mkdir()
            output.write_text("obsolete: true\n", encoding="utf-8")
            definition = KubernetesDefinition(replicas=3)
            with patch.object(generator, "PROJECT_ROOT", root), redirect_stdout(
                StringIO()
            ):
                first = generate_kubernetes(definition)
                first_source = first.read_text(encoding="utf-8")
                second = generate_kubernetes(definition)
            self.assertNotIn("obsolete", first_source)
            self.assertEqual(first_source, second.read_text(encoding="utf-8"))

    def test_manifest_contains_expected_resource_kinds(self):
        source = self.render_source()
        self.assertEqual(source.count("apiVersion:"), 7)
        for kind in (
            "Namespace",
            "ConfigMap",
            "Deployment",
            "StatefulSet",
            "PersistentVolumeClaim",
        ):
            self.assertIn(f"kind: {kind}", source)
        self.assertEqual(source.count("kind: Service"), 2)

    def test_api_and_postgres_contract(self):
        source = self.render_source()
        self.assertIn("name: arcacore-api", source)
        self.assertIn("image: arcacore-api:latest", source)
        self.assertIn("replicas: 2", source)
        self.assertIn("name: arcacore-postgres", source)
        self.assertIn("image: postgres:16", source)
        self.assertIn("claimName: arcacore-postgres-data", source)
        self.assertIn("storage: 10Gi", source)

    def test_manifest_references_secrets_without_writing_them(self):
        source = self.render_source()
        self.assertEqual(source.count("name: arcacore-secrets"), 2)
        self.assertIn("key: database-url", source)
        self.assertIn("key: postgres-password", source)
        self.assertNotIn("kind: Secret", source)
        self.assertNotIn("REPLACE_ME", source)
        self.assertNotIn("password:", source.lower())

    def test_health_and_later_scope_are_not_generated(self):
        source = self.render_source()
        for excluded in (
            "livenessProbe",
            "readinessProbe",
            "startupProbe",
            "kind: Ingress",
            "kind: HorizontalPodAutoscaler",
        ):
            self.assertNotIn(excluded, source)

    def test_cli_generates_with_custom_configuration(self):
        definition = KubernetesDefinition(replicas=3)
        with patch.object(
            sys, "argv", ["tools", "kubernetes", "--replicas", "3"]
        ), patch.object(
            cli, "generate_kubernetes", return_value=Path("kubernetes/arcacore.yaml")
        ) as generate, redirect_stdout(
            StringIO()
        ) as output:
            cli.main()
        generate.assert_called_once_with(definition)
        self.assertIn("Kubernetes resources generated successfully", output.getvalue())

    def test_cli_help_does_not_generate(self):
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag), patch.object(
                sys, "argv", ["tools", "kubernetes", flag]
            ), patch.object(cli, "generate_kubernetes") as generate, redirect_stdout(
                StringIO()
            ) as output:
                cli.main()
            generate.assert_not_called()
            self.assertIn("--storage-size", output.getvalue())
            self.assertNotIn("--env-file", output.getvalue())

    def test_main_help_advertises_kubernetes_command(self):
        with patch.object(sys, "argv", ["tools"]), redirect_stdout(
            StringIO()
        ) as output:
            cli.main()
        self.assertIn("kubernetes", output.getvalue())

    def render_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(generator, "PROJECT_ROOT", root), redirect_stdout(
                StringIO()
            ):
                return generate_kubernetes().read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
