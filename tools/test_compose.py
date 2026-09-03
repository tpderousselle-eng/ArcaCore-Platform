"""Exercise deterministic Compose generation without changing backend files."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from tools import __main__ as cli
from tools.core.compose_parser import ComposeDefinition, parse_compose_options
from tools.generate_compose import generate_compose
import tools.generate_compose as generator


class ComposeSmokeTest(unittest.TestCase):
    def root_with_dockerfile(self, directory: str) -> Path:
        root = Path(directory)
        (root / "Dockerfile").write_text("FROM python:3.13-slim\n", encoding="utf-8")
        return root

    def test_default_definition_and_render_context(self):
        with TemporaryDirectory() as directory:
            root = self.root_with_dockerfile(directory)
            with patch.object(generator, "PROJECT_ROOT", root), patch.object(
                generator, "render_template"
            ) as render:
                output = generate_compose()
        self.assertEqual(output.name, "docker-compose.yml")
        self.assertEqual(
            render.call_args.kwargs,
            {
                "template_name": "compose.j2",
                "output_path": output,
                "project_name": "arcacore",
                "api_port": 8000,
                "container_port": 8000,
                "database_port": 5432,
                "database_image": "postgres:16",
                "env_file": ".env",
                "dockerfile": "Dockerfile",
            },
        )

    def test_custom_options_and_order(self):
        arguments = [
            "--database-image",
            "postgres:17-alpine",
            "--api-port",
            "9000",
            "--project-name",
            "arca_core",
            "--database-port",
            "5544",
            "--container-port",
            "8080",
            "--env-file",
            "config/runtime.env",
            "--dockerfile",
            "deploy/Dockerfile.prod",
        ]
        definition = parse_compose_options(arguments)
        reordered = parse_compose_options(
            [
                "--dockerfile",
                "deploy/Dockerfile.prod",
                "--env-file",
                "config/runtime.env",
                "--container-port",
                "8080",
                "--database-port",
                "5544",
                "--project-name",
                "arca_core",
                "--api-port",
                "9000",
                "--database-image",
                "postgres:17-alpine",
            ]
        )
        self.assertEqual(definition, reordered)
        self.assertEqual((definition.api_port, definition.container_port), (9000, 8080))

    def test_windows_paths_normalize_for_compose(self):
        definition = ComposeDefinition(
            env_file=r"config\runtime.env",
            dockerfile=r"deploy\Dockerfile.prod",
        )
        self.assertEqual(definition.env_file, "config/runtime.env")
        self.assertEqual(definition.dockerfile, "deploy/Dockerfile.prod")

    def test_invalid_metadata_fails_before_rendering(self):
        invalid = (
            {"project_name": "ArcaCore"},
            {"project_name": "-arcacore"},
            {"api_port": 0},
            {"container_port": 65536},
            {"database_port": True},
            {"database_image": "postgres:16;echo"},
            {"database_image": ""},
            {"env_file": "../.env"},
            {"env_file": "/tmp/.env"},
            {"dockerfile": "."},
            {"dockerfile": "deploy file"},
        )
        for values in invalid:
            with self.subTest(values=values), patch.object(
                generator, "render_template"
            ) as render:
                with self.assertRaises(ValueError):
                    ComposeDefinition(**values)
                render.assert_not_called()

    def test_invalid_cli_options_fail_before_generation(self):
        invalid = (
            ["--unknown", "value"],
            ["--api-port"],
            ["--api-port", "abc"],
            ["--api-port", "8000", "--api-port", "9000"],
            ["--env-file", "--database-port", "5432"],
        )
        for arguments in invalid:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                parse_compose_options(arguments)

    def test_direct_generator_revalidates_metadata(self):
        invalid = SimpleNamespace(
            project_name="arcacore",
            api_port=8000,
            container_port=8000,
            database_port=5432,
            database_image="postgres:16",
            env_file=".env",
            dockerfile="Dockerfile",
        )
        with patch.object(generator, "render_template") as render:
            with self.assertRaises(ValueError):
                generate_compose(invalid)
            render.assert_not_called()

    def test_missing_dockerfile_fails_before_writing(self):
        with TemporaryDirectory() as directory, patch.object(
            generator, "PROJECT_ROOT", Path(directory)
        ), patch.object(generator, "render_template") as render:
            with self.assertRaisesRegex(FileNotFoundError, "tools dockerfile"):
                generate_compose()
            render.assert_not_called()

    def test_real_generation_writes_only_root_compose_file(self):
        with TemporaryDirectory() as directory:
            root = self.root_with_dockerfile(directory)
            backend = root / "backend"
            backend.mkdir()
            marker = backend / "main.py"
            marker.write_text("unchanged\n", encoding="utf-8")
            with patch.object(generator, "PROJECT_ROOT", root), redirect_stdout(
                StringIO()
            ):
                output = generate_compose()
            self.assertEqual(output, root / "docker-compose.yml")
            self.assertTrue(output.is_file())
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged\n")
            self.assertEqual(
                sorted(path.relative_to(root).as_posix() for path in root.rglob("*")),
                ["Dockerfile", "backend", "backend/main.py", "docker-compose.yml"],
            )

    def test_regeneration_is_a_complete_deterministic_replacement(self):
        with TemporaryDirectory() as directory:
            root = self.root_with_dockerfile(directory)
            output = root / "docker-compose.yml"
            output.write_text("obsolete: true\n", encoding="utf-8")
            definition = ComposeDefinition(api_port=9100)
            with patch.object(generator, "PROJECT_ROOT", root), redirect_stdout(
                StringIO()
            ):
                first = generate_compose(definition)
                first_source = first.read_text(encoding="utf-8")
                second = generate_compose(definition)
            self.assertNotIn("obsolete", first_source)
            self.assertEqual(first_source, second.read_text(encoding="utf-8"))

    def test_generated_contract_uses_api_postgres_env_and_volume(self):
        with TemporaryDirectory() as directory:
            root = self.root_with_dockerfile(directory)
            with patch.object(generator, "PROJECT_ROOT", root), redirect_stdout(
                StringIO()
            ):
                source = generate_compose().read_text(encoding="utf-8")
        self.assertIn("name: arcacore", source)
        self.assertIn("  api:", source)
        self.assertIn("  postgres:", source)
        self.assertIn("dockerfile: Dockerfile", source)
        self.assertIn('DATABASE_URL: "postgresql+psycopg2://', source)
        self.assertIn(
            "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in the env file}", source
        )
        self.assertIn('"8000:8000"', source)
        self.assertIn('"5432:5432"', source)
        self.assertIn("postgres_data:/var/lib/postgresql/data", source)
        self.assertNotIn("HEALTHCHECK", source)
        self.assertNotIn("redis:", source)
        self.assertNotIn("secret_key", source.lower())

    def test_cli_generates_with_custom_configuration(self):
        definition = ComposeDefinition(api_port=8080)
        with patch.object(
            sys, "argv", ["tools", "compose", "--api-port", "8080"]
        ), patch.object(
            cli, "generate_compose", return_value=Path("docker-compose.yml")
        ) as generate, redirect_stdout(
            StringIO()
        ) as output:
            cli.main()
        generate.assert_called_once_with(definition)
        self.assertIn("Docker Compose generated successfully", output.getvalue())

    def test_cli_help_does_not_generate(self):
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag), patch.object(
                sys, "argv", ["tools", "compose", flag]
            ), patch.object(cli, "generate_compose") as generate, redirect_stdout(
                StringIO()
            ) as output:
                cli.main()
            generate.assert_not_called()
            self.assertIn("--database-image", output.getvalue())
            self.assertNotIn("--python-version", output.getvalue())

    def test_main_help_advertises_compose_command(self):
        with patch.object(sys, "argv", ["tools"]), redirect_stdout(
            StringIO()
        ) as output:
            cli.main()
        self.assertIn("compose", output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
