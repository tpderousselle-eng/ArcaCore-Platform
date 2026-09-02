import platform
import sys

from tools.doctor import run as run_doctor
from tools.generate import generate_module
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

    print(
        "python -m tools generate "
        "Invoice title:str:length=200 amount:float"
    )

    print(
        "python -m tools doctor"
    )

    print(
        "python -m tools registry"
    )

    print(
        "python -m tools version"
    )

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