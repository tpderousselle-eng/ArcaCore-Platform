"""Read-only validator for the first Gaming Studio production authority package.

Run: python -m arcadev.gaming_studio_authority [authority-directory]
No supplied file can introduce new decisions or downstream lifecycle authority.
"""

import argparse
import ast
from pathlib import Path

from .gaming_studio_intent import (
    AUTHORITY_DIRECTORY, ProductionIntent, canonical_bytes, digest_bytes,
    local_authority_path, parse_authority, read_authority,
)
from .gaming_studio_idea import (
    checkpoint_manifest, clarification_review, validate_production_idea,
)
from .idea_intake import IdeaIntake
from .gaming_studio_resolution import validate_authorization


PACKAGE_FILES = frozenset({
    "production_intent.json", "idea_intake.json", "checkpoint.json",
    "clarification_review.json",
})


def validate_fixture_independence() -> None:
    """Check static imports across the ArcaDev layer, including package init.

    Repository code is trusted. This check does not pretend to sandbox arbitrary
    modified Python code or authenticate the repository itself.
    """
    for path in sorted(Path(__file__).parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or "", *(alias.name for alias in node.names)]
            for module in modules:
                if any(part.lower().startswith(("test_", "fixture")) or part.lower() == "tests"
                       for part in module.split(".")):
                    raise ValueError("Production ArcaDev layer imports test/fixture authority.")


def validate_production_authority(directory: Path = AUTHORITY_DIRECTORY) -> dict:
    """Reconstruct and compare every canonical artifact against the pinned root."""
    directory = local_authority_path(directory)
    if not directory.is_dir():
        raise ValueError("Production authority directory does not exist.")
    names = set()
    for path in directory.iterdir():
        if path.name == "idea_resolution" and not path.is_symlink() and not path.is_junction() and path.is_dir():
            continue
        if path.name not in PACKAGE_FILES or path.is_symlink() or path.is_junction() or not path.is_file():
            raise ValueError("Unknown authority file or non-regular package entry.")
        names.add(path.name)
    if names != PACKAGE_FILES:
        raise ValueError("Production authority package is incomplete.")

    validate_fixture_independence()
    source = ProductionIntent.from_bytes(read_authority(directory / "production_intent.json"))
    resolution = directory / "idea_resolution"
    if resolution.exists():
        entries = list(resolution.iterdir())
        if {p.name for p in entries} != {"clarification_authorization.json"}:
            raise ValueError("Resolution authority package has unknown or missing files.")
        validate_authorization(read_authority(resolution / "clarification_authorization.json"), source)
    raw_intake = read_authority(directory / "idea_intake.json")
    intake = IdeaIntake.from_dict(parse_authority(raw_intake))
    if intake.canonical_json().encode("utf-8") != raw_intake:
        raise ValueError("Production IDEA does not roundtrip canonically.")
    intake = validate_production_idea(source, intake)

    # A recomputed digest of a forged intake, review or checkpoint is insufficient:
    # compare complete reconstruction, including readiness, questions and null ID.
    expected_checkpoint = checkpoint_manifest(source, intake)
    expected_review = clarification_review(source, intake)
    for filename, expected in (("checkpoint.json", expected_checkpoint),
                               ("clarification_review.json", expected_review)):
        data = read_authority(directory / filename)
        parse_authority(data)
        if data != canonical_bytes(expected):
            raise ValueError(f"Production {filename} differs from canonical reconstruction.")
    return {
        "checkpoint": expected_checkpoint,
        "checkpoint_digest": digest_bytes(canonical_bytes(expected_checkpoint)),
        "fixture_independent": True,
        "valid": True,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=AUTHORITY_DIRECTORY)
    args = parser.parse_args(argv)
    try:
        result = validate_production_authority(args.directory)
    except (OSError, ValueError, SyntaxError) as error:
        parser.exit(1, f"Production authority validation failed: {error}\n")
    print(canonical_bytes(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
