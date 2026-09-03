"""Exercise deterministic Dockerfile generation without changing backend files."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

from tools import __main__ as cli
from tools.core.dockerfile_parser import (
    DockerfileDefinition,
    parse_dockerfile_options,
)
from tools.generate_dockerfile import generate_dockerfile
import tools.generate_dockerfile as generator


class DockerfileSmokeTest(unittest.TestCase):
    def test_default_definition_and_render_context(self):
        with patch.object(generator, "render_template") as render:
            output = generate_dockerfile()
        self.assertEqual(output.name, "Dockerfile")
        self.assertEqual(
            render.call_args.kwargs,
            {
                "template_name": "Dockerfile.j2",
                "output_path": output,
                "python_version": "3.13",
                "port": 8000,
                "app": "backend.main:app",
                "requirements": "backend/requirements.txt",
                "source": "backend",
            },
        )

    def test_custom_options_and_order(self):
        arguments = [
            "--port",
            "9000",
            "--python-version",
            "3.12.8",
            "--source",
            "src/api",
            "--app",
            "src.api.main:application",
            "--requirements",
            "config/runtime.txt",
        ]
        definition = parse_dockerfile_options(arguments)
        reordered = parse_dockerfile_options(
            [
                "--requirements",
                "config/runtime.txt",
                "--app",
                "src.api.main:application",
                "--source",
                "src/api",
                "--python-version",
                "3.12.8",
                "--port",
                "9000",
            ]
        )
        self.assertEqual(definition, reordered)
        self.assertEqual(definition.port, 9000)
        self.assertEqual(definition.requirements, "config/runtime.txt")

    def test_windows_paths_normalize_for_docker(self):
        definition = DockerfileDefinition(
            requirements=r"backend\requirements.txt",
            source=r"src\backend",
        )
        self.assertEqual(definition.requirements, "backend/requirements.txt")
        self.assertEqual(definition.source, "src/backend")

    def test_invalid_metadata_fails_before_rendering(self):
        invalid = (
            {"python_version": "latest"},
            {"python_version": "2.7"},
            {"port": 0},
            {"port": 65536},
            {"port": True},
            {"app": "backend.main"},
            {"app": "backend.main:app;echo"},
            {"requirements": "/tmp/requirements.txt"},
            {"requirements": "../requirements.txt"},
            {"requirements": "backend/requirements.in"},
            {"source": "."},
            {"source": "backend app"},
        )
        for values in invalid:
            with self.subTest(values=values), patch.object(
                generator, "render_template"
            ) as render:
                with self.assertRaises(ValueError):
                    DockerfileDefinition(**values)
                render.assert_not_called()

    def test_invalid_cli_options_fail_before_generation(self):
        invalid = (
            ["--unknown", "value"],
            ["--port"],
            ["--port", "abc"],
            ["--port", "8000", "--port", "9000"],
            ["--source", "--port", "8000"],
        )
        for arguments in invalid:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                parse_dockerfile_options(arguments)

    def test_direct_generator_revalidates_metadata(self):
        invalid = SimpleNamespace(
            python_version="3.13",
            port=8000,
            app="backend.main:app",
            requirements="backend/requirements.txt",
            source="backend",
        )
        with patch.object(generator, "render_template") as render:
            with self.assertRaises(ValueError):
                generate_dockerfile(invalid)
            render.assert_not_called()

    def test_real_generation_writes_only_root_dockerfile(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            backend = root / "backend"
            backend.mkdir()
            marker = backend / "main.py"
            marker.write_text("unchanged\n", encoding="utf-8")
            with patch.object(generator, "PROJECT_ROOT", root), redirect_stdout(
                StringIO()
            ):
                output = generate_dockerfile()
            self.assertEqual(output, root / "Dockerfile")
            self.assertTrue(output.is_file())
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged\n")
            self.assertEqual(
                sorted(path.relative_to(root).as_posix() for path in root.rglob("*")),
                ["Dockerfile", "backend", "backend/main.py"],
            )

    def test_regeneration_is_a_complete_deterministic_replacement(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "Dockerfile"
            output.write_text("obsolete content\n", encoding="utf-8")
            definition = DockerfileDefinition(port=9100)
            with patch.object(generator, "PROJECT_ROOT", root), redirect_stdout(
                StringIO()
            ):
                first = generate_dockerfile(definition)
                first_source = first.read_text(encoding="utf-8")
                second = generate_dockerfile(definition)
            self.assertNotIn("obsolete content", first_source)
            self.assertEqual(first_source, second.read_text(encoding="utf-8"))

    def test_generated_contract_is_non_root_and_cache_friendly(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(generator, "PROJECT_ROOT", root), redirect_stdout(
                StringIO()
            ):
                source = generate_dockerfile().read_text(encoding="utf-8")
        self.assertIn("FROM python:3.13-slim", source)
        self.assertLess(
            source.index("COPY backend/requirements.txt"),
            source.index("COPY --chown=arcacore:arcacore backend ./backend"),
        )
        self.assertIn("USER arcacore", source)
        self.assertIn("EXPOSE 8000", source)
        self.assertIn('"backend.main:app"', source)
        self.assertIn("HEALTHCHECK --interval=30s", source)
        self.assertIn("http://127.0.0.1:8000/health", source)
        self.assertIn("urllib.request.urlopen", source)
        self.assertNotIn("PASSWORD", source)

    def test_cli_generates_with_custom_configuration(self):
        definition = DockerfileDefinition(port=8080)
        with patch.object(
            sys, "argv", ["tools", "dockerfile", "--port", "8080"]
        ), patch.object(
            cli, "generate_dockerfile", return_value=Path("Dockerfile")
        ) as generate, redirect_stdout(
            StringIO()
        ) as output:
            cli.main()
        generate.assert_called_once_with(definition)
        self.assertIn("Dockerfile generated successfully", output.getvalue())

    def test_cli_help_does_not_generate(self):
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag), patch.object(
                sys, "argv", ["tools", "dockerfile", flag]
            ), patch.object(cli, "generate_dockerfile") as generate, redirect_stdout(
                StringIO()
            ) as output:
                cli.main()
            generate.assert_not_called()
            self.assertIn("--python-version", output.getvalue())

    def test_main_help_advertises_dockerfile_command(self):
        with patch.object(sys, "argv", ["tools"]), redirect_stdout(
            StringIO()
        ) as output:
            cli.main()
        self.assertIn("dockerfile", output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
