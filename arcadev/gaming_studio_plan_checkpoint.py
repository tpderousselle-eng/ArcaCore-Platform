"""Read-only reconstruction of resolved, explicitly UNAPPROVED production PLAN."""

from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes,
    local_authority_path, parse_authority, read_authority,
)
from .gaming_studio_plan import PLAN_PACKAGE_FILES
from .gaming_studio_plan_finalization import STATE_FILES, production_plan_resolution_state
from .gaming_studio_plan_resolution import APPROVED_AUTHORIZATION_DIGEST
from .gaming_studio_transition import CURRENT_PACKAGE_FILES


RESOLUTION_PACKAGE_FILES = STATE_FILES | frozenset({"clarification_authorization.json", "checkpoint.json"})
RESOLUTION_CHECKPOINT_SCHEMA = "arcadev.gaming_studio.plan_resolution_checkpoint"
RESOLUTION_CHECKPOINT_VERSION = 1
RESOLUTION_PACKAGE_VERSION = 3


def _authority_digests(directory, package):
    from .gaming_studio_authority import PACKAGE_FILES

    upstream = PACKAGE_FILES | {
        f"idea_resolution/{name}" for name in CURRENT_PACKAGE_FILES
    } | {f"production_plan/{name}" for name in PLAN_PACKAGE_FILES}
    return {
        **{name: digest_bytes(read_authority(directory / name)) for name in sorted(upstream)},
        **{f"production_plan/plan_resolution/{name}": digest_bytes(package[name])
           for name in sorted(RESOLUTION_PACKAGE_FILES - {"checkpoint.json"})},
    }


def production_plan_resolution_package(directory=AUTHORITY_DIRECTORY):
    """Validate upstream authority and return all canonical bytes without writes."""
    directory = local_authority_path(directory)
    # This validates the exact approved envelope, immutable historical artifacts,
    # and original PLAN before replay. Supplied finalization/review/checkpoint
    # fields cannot supply a decision or grant approval to reconstruction.
    package = production_plan_resolution_state(directory)
    package["clarification_authorization.json"] = read_authority(
        directory / "production_plan/plan_resolution/clarification_authorization.json")
    if digest_bytes(package["clarification_authorization.json"]) != APPROVED_AUTHORIZATION_DIGEST:
        raise ValueError("PLAN clarification authorization digest is not approved.")
    review = parse_authority(package["resolution_review.json"])
    checkpoint = {
        "schema": RESOLUTION_CHECKPOINT_SCHEMA,
        "schema_version": RESOLUTION_CHECKPOINT_VERSION,
        "package_version": RESOLUTION_PACKAGE_VERSION,
        "product_key": "gaming_studio", "production_intent_digest": APPROVED_INTENT_DIGEST,
        **{key: review[key] for key in (
            "handoff_id", "project_id", "plan_id", "plan_finalization_id",
            "accepted_decision_ids", "unresolved_question_count", "conflict_count",
            "effective_ready_for_architecture", "current_stage", "project_status",
            "status", "next_authorized_action", "complete_plan_approved", "architecture_authorized",
        )},
        "authority_digests": _authority_digests(directory, package),
    }
    package["checkpoint.json"] = canonical_bytes(checkpoint)
    return package


def validate_plan_resolution_package(directory=AUTHORITY_DIRECTORY):
    """Reject missing/unknown files and any divergence from exact public replay."""
    directory = local_authority_path(directory)
    area = local_authority_path(directory / "production_plan/plan_resolution")
    if not area.is_dir() or {p.name for p in area.iterdir()} != RESOLUTION_PACKAGE_FILES:
        raise ValueError("PLAN resolution package has unknown or missing authority files.")
    actual = {name: read_authority(area / name) for name in sorted(RESOLUTION_PACKAGE_FILES)}
    for data in actual.values():
        parse_authority(data)
    if digest_bytes(actual["clarification_authorization.json"]) != APPROVED_AUTHORIZATION_DIGEST:
        raise ValueError("PLAN clarification authorization digest is not approved.")
    # A fast integrity check is only a rejection filter. Even fully rehashed
    # candidates must subsequently equal trusted public-contract reconstruction.
    checkpoint = parse_authority(actual["checkpoint.json"])
    if checkpoint.get("authority_digests") != _authority_digests(directory, actual):
        raise ValueError("PLAN resolution authority digests do not match the complete lineage.")
    expected = production_plan_resolution_package(directory)
    if actual != expected:
        raise ValueError("PLAN resolution differs from the exact production clarification lineage.")
    return parse_authority(expected["checkpoint.json"])
