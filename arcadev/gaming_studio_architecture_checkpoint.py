"""Immutable complete production lineage through unresolved ARCHITECTURE."""

from .gaming_studio_architecture import ARCHITECTURE_AREA, SPECIFICATION_FILES, read_architecture_authority
from .gaming_studio_architecture_finalization import (
    FINALIZATION_FILES, architecture_clarification_review, production_architecture_initial_state,
)
from .gaming_studio_architecture_request import REQUEST_FILES, architecture_clarification_request
from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes,
    local_authority_path, parse_authority, read_authority,
)
from .gaming_studio_plan_approval import APPROVAL_AREA
from .gaming_studio_plan_approval_checkpoint import APPROVAL_PACKAGE_FILES, historical_authority_names


ARCHITECTURE_CHECKPOINT_SCHEMA = "arcadev.gaming_studio.production_architecture_checkpoint"
ARCHITECTURE_CHECKPOINT_VERSION = 1
ARCHITECTURE_PACKAGE_VERSION = 4
ARCHITECTURE_PACKAGE_FILES = SPECIFICATION_FILES | FINALIZATION_FILES | REQUEST_FILES | {"checkpoint.json"}


def architecture_historical_authority_names():
    return historical_authority_names() | {f"{APPROVAL_AREA}/{n}" for n in APPROVAL_PACKAGE_FILES}


def _authority_digests(directory, package):
    # Only trusted inventory names determine filesystem reads.
    return {
        **{name: digest_bytes(read_authority(directory / name))
           for name in sorted(architecture_historical_authority_names())},
        **{f"{ARCHITECTURE_AREA}/{name}": digest_bytes(package[name])
           for name in sorted(ARCHITECTURE_PACKAGE_FILES - {"checkpoint.json"})},
    }


def production_architecture_checkpoint_package(directory=AUTHORITY_DIRECTORY):
    """Reconstruct from certified history; supplied architecture decisions are inert."""
    directory = local_authority_path(directory)
    handoff, finalization = production_architecture_initial_state(directory)
    architecture = finalization.original_architecture
    review = architecture_clarification_review(handoff, finalization)
    package = {
        "architecture_specification.json": architecture.canonical_json().encode("utf-8"),
        "architecture_finalization.json": finalization.canonical_json().encode("utf-8"),
        "clarification_review.json": canonical_bytes(review),
        "clarification_request.json": canonical_bytes(architecture_clarification_request(finalization)),
    }
    checkpoint = {
        "schema": ARCHITECTURE_CHECKPOINT_SCHEMA, "schema_version": ARCHITECTURE_CHECKPOINT_VERSION,
        "package_version": ARCHITECTURE_PACKAGE_VERSION, "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        "software_plan_id": architecture.software_plan_id,
        "plan_finalization_id": architecture.plan_finalization_id,
        "approved_plan_id": architecture.approved_plan_id,
        "plan_architecture_handoff_id": architecture.handoff_id,
        "architecture_specification_id": architecture.architecture_id,
        **{key: review[key] for key in (
            "project_id", "architecture_finalization_id", "current_stage", "project_status",
            "unresolved_question_count", "conflict_count", "effective_ready_for_approval",
            "architecture_approved", "models_authorized", "status", "next_authorized_action",
        )},
        "component_count": len(architecture.components), "interface_count": len(architecture.interfaces),
        "data_flow_count": len(architecture.data_flows), "aspect_count": len(architecture.aspects),
        "original_question_count": len(architecture.open_architecture_questions),
        "blocking_question_count": sum(q.blocking for q in finalization.unresolved_questions),
        "authority_digests": _authority_digests(directory, package),
    }
    package["checkpoint.json"] = canonical_bytes(checkpoint)
    return package


def validate_architecture_package_inventory(directory=AUTHORITY_DIRECTORY):
    """Reject incomplete or unknown architecture entries before expensive replay."""
    directory = local_authority_path(directory)
    area = local_authority_path(directory / ARCHITECTURE_AREA)
    if not area.is_dir():
        raise ValueError("Production architecture package has unknown or missing authority files.")
    names = {p.name for p in area.iterdir()}
    # The versioned resolution is a separate child package, never a rewrite of
    # this historical checkpoint. Its own validator owns its contents.
    if "architecture_resolution" in names:
        child = local_authority_path(area / "architecture_resolution")
        if not child.is_dir():
            raise ValueError("Architecture resolution must be a regular local directory.")
        names.remove("architecture_resolution")
    if names != ARCHITECTURE_PACKAGE_FILES:
        raise ValueError("Production architecture package has unknown or missing authority files.")
    return area


def validate_production_architecture_checkpoint(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    area = validate_architecture_package_inventory(directory)
    actual = {name: read_architecture_authority(area / name) for name in sorted(ARCHITECTURE_PACKAGE_FILES)}
    checkpoint = parse_authority(actual["checkpoint.json"])
    if checkpoint.get("authority_digests") != _authority_digests(directory, actual):
        raise ValueError("Production architecture digests do not match the complete lineage.")
    expected = production_architecture_checkpoint_package(directory)
    if actual != expected:
        raise ValueError("Production architecture checkpoint differs from exact certified public replay.")
    return parse_authority(expected["checkpoint.json"])
