"""Exact bounded production approval, replayed through the public PLAN contract.

This package extends immutable history. It neither transitions the project nor
generates architecture. Repository constants are the trusted user authority;
supplied JSON, including recomputed digests, cannot grant different approval.
"""

from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes,
    local_authority_path, parse_authority, read_authority,
)
from .gaming_studio_plan import production_plan_inputs
from .gaming_studio_plan_checkpoint import validate_plan_resolution_package
from .gaming_studio_plan_resolution import PLAN_ID
from .plan_approval import ApprovedPlan, approve_plan
from .plan_clarification import PlanFinalization


APPROVAL_SCHEMA = "arcadev.gaming_studio.plan_approval_authorization"
APPROVAL_VERSION = 1
PROJECT_ID = "arcadev_969321c8959864fe18393b9d2b551063"
IDEA_HANDOFF_ID = "arcadev_handoff_2d8411540b13ce1eecd8c480e0f5a692"
FINALIZATION_ID = "arcadev_plan_final_d9698e456e67fae47ef46dbd11880dd2"
APPROVAL_STATEMENT = "I explicitly approve the complete Gaming Studio production SoftwarePlan and authorize the PLAN → ARCHITECTURE transition."
APPROVAL_STATEMENT_DIGEST = digest_bytes(APPROVAL_STATEMENT.encode("utf-8"))
APPROVAL_FILES = frozenset({"approval_authorization.json", "approved_plan.json"})
APPROVAL_AREA = "production_plan/plan_approval"


def production_plan_approval_authorization():
    """Return the exact versioned authority, without interpreting arbitrary text."""
    return canonical_bytes({
        "schema": APPROVAL_SCHEMA, "schema_version": APPROVAL_VERSION,
        "package_version": 1, "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        "project_id": PROJECT_ID, "idea_handoff_id": IDEA_HANDOFF_ID,
        "software_plan_id": PLAN_ID, "plan_finalization_id": FINALIZATION_ID,
        "approval_statement": APPROVAL_STATEMENT,
        "approval_statement_digest": APPROVAL_STATEMENT_DIGEST,
        "provenance": "explicit_user",
        "scope": "complete_plan_approval_and_plan_to_architecture_authorization",
        "architecture_generation_authorized": False, "models_authorized": False,
        "backend_authorized": False, "frontend_authorized": False,
    })


def validate_plan_approval_authorization(data):
    value = parse_authority(data)
    if data != production_plan_approval_authorization():
        raise ValueError("Production PLAN approval differs from exact bounded user authority.")
    return value


def production_approved_plan(directory=AUTHORITY_DIRECTORY):
    """Validate complete current resolution before independent public approval."""
    directory = local_authority_path(directory)
    authority = validate_plan_approval_authorization(read_authority(
        directory / APPROVAL_AREA / "approval_authorization.json"))
    checkpoint = validate_plan_resolution_package(directory)
    handoff = production_plan_inputs(directory)
    finalization = PlanFinalization.from_json(read_authority(
        directory / "production_plan/plan_resolution/plan_finalization.json").decode("utf-8"),
        handoff=handoff)
    if (handoff.source_project_id != authority["project_id"]
            or handoff.handoff_id != authority["idea_handoff_id"]
            or finalization.original_plan.plan_id != authority["software_plan_id"]
            or finalization.finalization_id != authority["plan_finalization_id"]
            or checkpoint["plan_finalization_id"] != finalization.finalization_id):
        raise ValueError("Production PLAN approval has stale or different source authority.")
    return approve_plan(handoff=handoff, finalization=finalization,
                        approval_statement=authority["approval_statement"])


def production_plan_approval_package(directory=AUTHORITY_DIRECTORY):
    approved = production_approved_plan(directory)
    return {
        "approval_authorization.json": production_plan_approval_authorization(),
        "approved_plan.json": approved.canonical_json().encode("utf-8"),
    }


def validate_plan_approval_package(directory=AUTHORITY_DIRECTORY):
    """Validate Approval 1 files; subsequent packages validate their own files."""
    directory = local_authority_path(directory)
    area = local_authority_path(directory / APPROVAL_AREA)
    actual = {name: read_authority(area / name) for name in sorted(APPROVAL_FILES)}
    validate_plan_approval_authorization(actual["approval_authorization.json"])
    expected = production_plan_approval_package(directory)
    if actual != expected:
        raise ValueError("Production ApprovedPlan differs from exact public approval replay.")
    return ApprovedPlan.from_json(actual["approved_plan.json"].decode("utf-8"))
