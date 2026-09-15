"""Exact production architecture approval through the certified public contract.

Repository constants preserve bounded user authority. Supplied JSON cannot
change the approved statement, its sources, or the scope of authorization.
"""

from .architecture_approval import approve_architecture
from .architecture_clarification import ArchitectureFinalization
from .gaming_studio_architecture import read_architecture_authority
from .gaming_studio_architecture_resolution import ARCHITECTURE_ID, PROJECT_ID, RESOLUTION_AREA
from .gaming_studio_architecture_resolution_checkpoint import validate_architecture_resolution_checkpoint
from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes,
    local_authority_path, parse_authority,
)
from .gaming_studio_plan_approval import APPROVAL_AREA as PLAN_APPROVAL_AREA
from .plan_architecture_handoff import PlanArchitectureHandoff


APPROVAL_SCHEMA = "arcadev.gaming_studio.architecture_approval_authorization"
APPROVAL_VERSION = 1
APPROVAL_AREA = "production_architecture/architecture_approval"
APPROVAL_FILES = frozenset({"approval_authorization.json", "approved_architecture.json"})
FINALIZATION_ID = "arcadev_architecture_final_17fe8c2deb6ed3712f04cdd3df6e074e"
APPROVAL_STATEMENT = "I explicitly approve the complete resolved Gaming Studio ArchitectureSpecification and authorize the ARCHITECTURE → MODELS transition."
APPROVAL_STATEMENT_DIGEST = digest_bytes(APPROVAL_STATEMENT.encode("utf-8"))


def production_architecture_approval_authorization():
    return canonical_bytes({
        "schema": APPROVAL_SCHEMA, "schema_version": APPROVAL_VERSION,
        "package_version": 1, "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        "project_id": PROJECT_ID, "architecture_specification_id": ARCHITECTURE_ID,
        "architecture_finalization_id": FINALIZATION_ID,
        "approval_statement": APPROVAL_STATEMENT,
        "approval_statement_digest": APPROVAL_STATEMENT_DIGEST,
        "provenance": "explicit_user",
        "scope": "complete_architecture_approval_and_architecture_to_models_authorization",
        "domain_model_generation_authorized": False,
        "backend_authorized": False, "frontend_authorized": False,
    })


def validate_architecture_approval_authorization(data):
    value = parse_authority(data)
    if data != production_architecture_approval_authorization():
        raise ValueError("Architecture approval differs from exact bounded user authority.")
    return value


def production_approved_architecture(directory=AUTHORITY_DIRECTORY):
    """Reconstruct the complete certified lineage before independent approval."""
    directory = local_authority_path(directory)
    authority = validate_architecture_approval_authorization(read_architecture_authority(
        directory / APPROVAL_AREA / "approval_authorization.json"))
    checkpoint = validate_architecture_resolution_checkpoint(directory)
    handoff = PlanArchitectureHandoff.from_json(read_architecture_authority(
        directory / PLAN_APPROVAL_AREA / "plan_architecture_handoff.json").decode("utf-8"))
    source = handoff.resulting_project
    if read_architecture_authority(directory / PLAN_APPROVAL_AREA / "project.json") != source.canonical_json().encode("utf-8"):
        raise ValueError("Architecture source project differs from its certified PLAN handoff.")
    finalization = ArchitectureFinalization.from_json(read_architecture_authority(
        directory / RESOLUTION_AREA / "architecture_finalization.json").decode("utf-8"), handoff=handoff)
    architecture = finalization.original_architecture
    if (source.project_id != authority["project_id"]
            or architecture.architecture_id != authority["architecture_specification_id"]
            or finalization.finalization_id != authority["architecture_finalization_id"]
            or checkpoint["architecture_finalization_id"] != finalization.finalization_id):
        raise ValueError("Architecture approval has stale or mismatched source authority.")
    return approve_architecture(source_project=source, handoff=handoff,
        architecture=architecture, finalization=finalization,
        approval_statement=authority["approval_statement"])


def production_architecture_approval_package(directory=AUTHORITY_DIRECTORY):
    approved = production_approved_architecture(directory)
    return {
        "approval_authorization.json": production_architecture_approval_authorization(),
        "approved_architecture.json": approved.canonical_json().encode("utf-8"),
    }


def validate_architecture_approval_package(directory=AUTHORITY_DIRECTORY):
    """Compare persisted approval with public replay; return that certified result."""
    directory = local_authority_path(directory)
    area = local_authority_path(directory / APPROVAL_AREA)
    actual = {name: read_architecture_authority(area / name) for name in sorted(APPROVAL_FILES)}
    validate_architecture_approval_authorization(actual["approval_authorization.json"])
    approved = production_approved_architecture(directory)
    if actual["approved_architecture.json"] != approved.canonical_json().encode("utf-8"):
        raise ValueError("ApprovedArchitecture differs from exact production public replay.")
    return approved
