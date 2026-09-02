import json
from pathlib import Path

from tools.version import __title__


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_FILE = PROJECT_ROOT / "tools" / "registry" / "models.json"


def run():

    print()
    print(f"{__title__} Registry")
    print("=" * 40)
    print()

    if not REGISTRY_FILE.exists():
        print("Registry file not found.")
        print()
        return

    try:
        data = json.loads(
            REGISTRY_FILE.read_text(
                encoding="utf-8",
            )
        )

    except Exception:
        print("Registry is invalid.")
        print()
        return

    if not data:
        print("No models registered.")
        print()
        return

    print("Registered Models")
    print()

    for name in sorted(data.keys()):
        print(f"✓ {name}")

    print()
    print(f"Total: {len(data)}")
    print()