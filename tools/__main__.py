import platform
import sys

from tools.core.dockerfile_parser import parse_dockerfile_options
from tools.doctor import run as run_doctor
from tools.generate import generate_module
from tools.generate_dockerfile import generate_dockerfile
from tools.registry_cli import run as run_registry
from tools.version import (
    __release__,
    __title__,
    __version__,
)


def print_help():

    print()
    print(f"{__title__} v{__version__}")
    print("=" * 50)
    print()

    print("Developer Commands")
    print()

    print("  generate")
    print("      Generate a CRUD module")
    print()

    print("  doctor")
    print("      Verify your ArcaCore installation")
    print()

    print("  dockerfile")
    print("      Generate the application Dockerfile")
    print()

    print("  registry")
    print("      Show registered models")
    print()

    print("  version")
    print("      Display framework version")
    print()

    print("-" * 50)
    print("Examples")
    print("-" * 50)
    print()

    print("python -m tools generate " "Invoice title:str:length=200 amount:float")

    print("python -m tools doctor")

    print("python -m tools dockerfile")

    print("python -m tools registry")

    print("python -m tools version")

    print()


def print_dockerfile_help():

    print()
    print("Generate Dockerfile")
    print("=" * 50)
    print()
    print("python -m tools dockerfile [options]")
    print()
    print("Options")
    print("  --python-version VERSION   Base Python 3 version (default: 3.13)")
    print("  --port PORT                Container port (default: 8000)")
    print("  --app MODULE:ATTRIBUTE     ASGI application (default: backend.main:app)")
    print(
        "  --requirements PATH        Requirements file (default: backend/requirements.txt)"
    )
    print("  --source PATH              Source directory (default: backend)")
    print()


def print_version():

    print()
    print(__title__)
    print("=" * 50)
    print(f"Version : {__version__}")
    print(f"Release : {__release__}")
    print(f"Python  : {platform.python_version()}")
    print()


def main():

    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1].lower()

    if command == "generate":

        if len(sys.argv) < 3:
            print("Missing module name.")
            return

        generate_module(
            sys.argv[2],
            sys.argv[3:],
        )

        return

    if command == "doctor":
        run_doctor()
        return

    if command == "dockerfile":
        if any(value in {"-h", "--help"} for value in sys.argv[2:]):
            print_dockerfile_help()
            return
        definition = parse_dockerfile_options(sys.argv[2:])
        output_path = generate_dockerfile(definition)
        print()
        print(f"Dockerfile generated successfully: {output_path}")
        return

    if command == "registry":
        run_registry()
        return

    if command == "version":
        print_version()
        return

    print(f"Unknown command: {command}")
    print()
    print_help()


if __name__ == "__main__":
    main()
