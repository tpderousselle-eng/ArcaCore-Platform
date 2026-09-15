"""Read-only Gaming Studio authority through approved architecture and MODELS entry.

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
from .gaming_studio_transition import validate_transition_package


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


def validate_production_authority(directory: Path = AUTHORITY_DIRECTORY, *, seed_only=False,
                                  require_current=False, require_plan=False,
                                  require_plan_resolution=False, require_plan_approval=False,
                                  require_architecture=False, require_architecture_resolution=False,
                                  require_models_entry=False) -> dict:
    """Reconstruct and compare every canonical artifact against the pinned root."""
    directory = local_authority_path(directory)
    # Unqualified validation means the current production checkpoint.
    # Explicit historical gates still accept their intentionally older packages.
    historical_requirement = (seed_only or require_current or require_plan or require_plan_resolution
                              or require_plan_approval or require_architecture or require_architecture_resolution)
    require_models_entry = require_models_entry or not historical_requirement
    require_architecture_resolution = require_architecture_resolution or require_models_entry
    require_architecture = require_architecture or require_architecture_resolution
    require_plan_approval = require_plan_approval or require_architecture
    require_plan_resolution = require_plan_resolution or require_plan_approval
    require_plan = require_plan or require_plan_resolution
    if seed_only and (require_current or require_plan):
        raise ValueError("Seed-only validation cannot require current resolution or PLAN authority.")
    if not directory.is_dir():
        raise ValueError("Production authority directory does not exist.")
    names = set()
    for path in directory.iterdir():
        if path.name in {"idea_resolution", "production_plan", "production_architecture"} and not path.is_symlink() and not path.is_junction() and path.is_dir():
            continue
        if path.name not in PACKAGE_FILES or path.is_symlink() or path.is_junction() or not path.is_file():
            raise ValueError("Unknown authority file or non-regular package entry.")
        names.add(path.name)
    if names != PACKAGE_FILES:
        raise ValueError("Production authority package is incomplete.")

    architecture_area = directory / "production_architecture"
    if require_architecture and not architecture_area.exists():
        raise ValueError("Current production architecture authority is required.")
    if not seed_only and architecture_area.exists():
        from .gaming_studio_architecture_checkpoint import validate_architecture_package_inventory
        validate_architecture_package_inventory(directory)

    if require_models_entry:
        from .gaming_studio_models_entry_checkpoint import validate_models_entry_checkpoint
        current = validate_models_entry_checkpoint(directory)
        validate_fixture_independence()
        # The current validator has already reconstructed and compared the
        # complete lineage. Project its verified historical checkpoints without
        # rerunning each ancestor's entire replay a second time.
        history = {
            key: parse_authority(read_authority(directory / relative))
            for key, relative in (
                ("seed_checkpoint", "checkpoint.json"),
                ("idea_checkpoint", "idea_resolution/checkpoint.json"),
                ("unanswered_plan_checkpoint", "production_plan/checkpoint.json"),
                ("ready_for_approval_checkpoint", "production_plan/plan_resolution/checkpoint.json"),
                ("pre_architecture_checkpoint", "production_plan/plan_approval/checkpoint.json"),
                ("unresolved_architecture_checkpoint", "production_architecture/checkpoint.json"),
                ("ready_for_architecture_approval_checkpoint", "production_architecture/architecture_resolution/checkpoint.json"),
            )
        }
        return {**history, "checkpoint": current,
                "checkpoint_digest": digest_bytes(canonical_bytes(current)),
                "fixture_independent": True, "valid": True}

    resolved_checkpoint = None
    if require_architecture_resolution:
        from .gaming_studio_architecture_resolution_checkpoint import validate_architecture_resolution_checkpoint
        # Current validation requires the complete resolution package even if
        # the child directory was removed. Historical selection is explicit.
        resolved_checkpoint = validate_architecture_resolution_checkpoint(directory)

    validate_fixture_independence()
    source = ProductionIntent.from_bytes(read_authority(directory / "production_intent.json"))
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
    result = {
        "checkpoint": expected_checkpoint,
        "checkpoint_digest": digest_bytes(canonical_bytes(expected_checkpoint)),
        "fixture_independent": True,
        "valid": True,
    }
    resolution = directory / "idea_resolution"
    if (require_current or require_plan) and not resolution.exists():
        raise ValueError("Current production resolution authority is required.")
    if resolution.exists() and not seed_only:
        current = validate_transition_package(resolution, source)
        result.update(seed_checkpoint=expected_checkpoint, checkpoint=current,
                      checkpoint_digest=digest_bytes(canonical_bytes(current)))
    plan_area = directory / "production_plan"
    if require_plan and not plan_area.exists():
        raise ValueError("Current production PLAN authority is required.")
    if plan_area.exists() and not seed_only:
        from .gaming_studio_plan import validate_production_plan_package
        plan_checkpoint = validate_production_plan_package(directory)
        result.update(idea_checkpoint=result["checkpoint"], checkpoint=plan_checkpoint,
                      checkpoint_digest=digest_bytes(canonical_bytes(plan_checkpoint)))
    resolution_area = directory / "production_plan" / "plan_resolution"
    if require_plan_resolution and not resolution_area.exists():
        raise ValueError("Current production PLAN resolution authority is required.")
    if not seed_only and resolution_area.exists():
        from .gaming_studio_plan_checkpoint import validate_plan_resolution_package
        current_checkpoint = validate_plan_resolution_package(directory)
        result.update(unanswered_plan_checkpoint=result["checkpoint"], checkpoint=current_checkpoint,
                      checkpoint_digest=digest_bytes(canonical_bytes(current_checkpoint)))
    approval_area = directory / "production_plan" / "plan_approval"
    if require_plan_approval and not approval_area.exists():
        raise ValueError("Current production PLAN approval authority is required.")
    if not seed_only and approval_area.exists():
        from .gaming_studio_plan_approval_checkpoint import validate_plan_approval_checkpoint
        current_checkpoint = validate_plan_approval_checkpoint(directory)
        result.update(ready_for_approval_checkpoint=result["checkpoint"], checkpoint=current_checkpoint,
                      checkpoint_digest=digest_bytes(canonical_bytes(current_checkpoint)))
    if not seed_only and architecture_area.exists():
        from .gaming_studio_architecture_checkpoint import validate_production_architecture_checkpoint
        current_checkpoint = validate_production_architecture_checkpoint(directory)
        result.update(pre_architecture_checkpoint=result["checkpoint"], checkpoint=current_checkpoint,
                      checkpoint_digest=digest_bytes(canonical_bytes(current_checkpoint)))
    if resolved_checkpoint is not None:
        result.update(unresolved_architecture_checkpoint=result["checkpoint"], checkpoint=resolved_checkpoint,
                      checkpoint_digest=digest_bytes(canonical_bytes(resolved_checkpoint)))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=AUTHORITY_DIRECTORY)
    parser.add_argument("--seed-only", action="store_true", help="Verify the original historical seed package only.")
    parser.add_argument("--require-current", action="store_true", help="Reject a seed-only package or a missing resolution area.")
    parser.add_argument("--require-plan", action="store_true", help="Require the complete unapproved production PLAN package.")
    parser.add_argument("--require-plan-resolution", action="store_true", help="Require the resolved, still-unapproved production PLAN checkpoint.")
    parser.add_argument("--require-plan-approval", action="store_true", help="Require complete PLAN approval and its certified ARCHITECTURE handoff.")
    parser.add_argument("--require-architecture", action="store_true", help="Require the complete generated, unapproved production architecture checkpoint.")
    parser.add_argument("--require-architecture-resolution", action="store_true",
                        help="Require the complete resolved, unapproved production architecture checkpoint.")
    parser.add_argument("--require-models-entry", action="store_true",
                        help="Require complete architecture approval and MODELS entry, without model generation.")
    args = parser.parse_args(argv)
    try:
        result = validate_production_authority(args.directory, seed_only=args.seed_only,
                                               require_current=args.require_current, require_plan=args.require_plan,
                                               require_plan_resolution=args.require_plan_resolution,
                                               require_plan_approval=args.require_plan_approval,
                                               require_architecture=args.require_architecture,
                                               require_architecture_resolution=args.require_architecture_resolution,
                                               require_models_entry=args.require_models_entry)
    except (OSError, ValueError, SyntaxError) as error:
        parser.exit(1, f"Production authority validation failed: {error}\n")
    print(canonical_bytes(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
