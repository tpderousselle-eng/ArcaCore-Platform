"""Complete certified production lineage through resolved, unapproved architecture."""

from .gaming_studio_architecture import ARCHITECTURE_AREA, read_architecture_authority
from .gaming_studio_architecture_checkpoint import (
    ARCHITECTURE_PACKAGE_FILES, architecture_historical_authority_names,
)
from .gaming_studio_architecture_resolution import RESOLUTION_AREA, INITIAL_FINALIZATION_ID
from .gaming_studio_architecture_resolution_finalization import (
    STATE_FILES, production_architecture_resolution_state,
)
from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes,
    local_authority_path, parse_authority,
)


RESOLUTION_CHECKPOINT_SCHEMA = "arcadev.gaming_studio.architecture_resolution_checkpoint"
RESOLUTION_CHECKPOINT_VERSION = 1
RESOLUTION_PACKAGE_VERSION = 3
# Rejection filter only; a matching checkpoint still requires full public replay.
APPROVED_CHECKPOINT_DIGEST = '16ca974c5311811ae6a558523bc4981f9cb1870a8465007e7333800bf99887ba'
RESOLUTION_PACKAGE_FILES = STATE_FILES | {"clarification_authorization.json", "checkpoint.json"}


def resolution_historical_authority_names():
    return architecture_historical_authority_names() | {
        f"{ARCHITECTURE_AREA}/{name}" for name in ARCHITECTURE_PACKAGE_FILES}


def _authority_digests(directory, package):
    # Never follow a filename supplied by a checkpoint or authorization document.
    return {
        **{name: digest_bytes(read_architecture_authority(directory / name))
           for name in sorted(resolution_historical_authority_names())},
        **{f"{RESOLUTION_AREA}/{name}": digest_bytes(package[name])
           for name in sorted(RESOLUTION_PACKAGE_FILES - {"checkpoint.json"})},
    }


def production_architecture_resolution_package(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    package = production_architecture_resolution_state(directory)
    package["clarification_authorization.json"] = read_architecture_authority(
        directory / RESOLUTION_AREA / "clarification_authorization.json")
    review = parse_authority(package["resolution_review.json"])
    # The original checkpoint has already been fully reconstructed by public
    # replay above. It supplies historical IDs only after that validation.
    historical = parse_authority(read_architecture_authority(directory / ARCHITECTURE_AREA / "checkpoint.json"))
    checkpoint = {
        "schema": RESOLUTION_CHECKPOINT_SCHEMA, "schema_version": RESOLUTION_CHECKPOINT_VERSION,
        "package_version": RESOLUTION_PACKAGE_VERSION, "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        **{key: historical[key] for key in (
            "software_plan_id", "plan_finalization_id", "approved_plan_id",
            "plan_architecture_handoff_id", "architecture_specification_id",
        )},
        "initial_architecture_finalization_id": INITIAL_FINALIZATION_ID,
        **{key: review[key] for key in (
            "project_id", "architecture_finalization_id", "accepted_decision_ids",
            "accepted_decision_count", "history_count", "unresolved_question_count", "conflict_count",
            "effective_ready_for_approval", "current_stage", "project_status", "architecture_approved",
            "models_authorized", "backend_authorized", "frontend_authorized", "status", "next_authorized_action",
        )},
        "authority_digests": _authority_digests(directory, package),
    }
    package["checkpoint.json"] = canonical_bytes(checkpoint)
    return package


def validate_architecture_resolution_inventory(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    area = local_authority_path(directory / RESOLUTION_AREA)
    if not area.is_dir() or {p.name for p in area.iterdir()} != RESOLUTION_PACKAGE_FILES:
        raise ValueError("Architecture resolution package has unknown or missing authority files.")
    for name in sorted(RESOLUTION_PACKAGE_FILES):
        if not local_authority_path(area / name).is_file():
            raise ValueError("Architecture resolution requires regular local authority files.")
    return area


def validate_architecture_resolution_checkpoint(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    area = validate_architecture_resolution_inventory(directory)
    actual = {name: read_architecture_authority(area / name) for name in sorted(RESOLUTION_PACKAGE_FILES)}
    checkpoint = parse_authority(actual["checkpoint.json"])
    if digest_bytes(actual["checkpoint.json"]) != APPROVED_CHECKPOINT_DIGEST:
        raise ValueError("Architecture resolution checkpoint differs from exact approved bytes.")
    if checkpoint.get("authority_digests") != _authority_digests(directory, actual):
        raise ValueError("Architecture resolution digests do not match the complete lineage.")
    expected = production_architecture_resolution_package(directory)
    if actual != expected:
        raise ValueError("Architecture resolution checkpoint differs from exact authorized public replay.")
    return parse_authority(expected["checkpoint.json"])
