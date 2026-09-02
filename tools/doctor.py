from pathlib import Path
import importlib.util
import platform

from tools.version import (
    __title__,
    __version__,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check_python():

    print(f"✓ Python      : {platform.python_version()}")


def check_package(name: str):

    if importlib.util.find_spec(name):
        print(f"✓ {name}")
    else:
        print(f"✗ {name}")


def check_directory(name: str):

    path = PROJECT_ROOT / name

    if path.exists():
        print(f"✓ {name}/")
    else:
        print(f"✗ {name}/")


def run():

    print()
    print(f"{__title__} Doctor")
    print("=" * 40)
    print(f"Version     : {__version__}")
    print()

    check_python()

    check_package("jinja2")
    check_package("sqlalchemy")
    check_package("black")

    print()

    check_directory("docs")
    check_directory("backend")
    check_directory("tools")

    print()