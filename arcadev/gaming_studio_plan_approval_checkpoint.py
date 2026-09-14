"""Complete production approval lineage; stop before architecture generation."""

from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes,
    local_authority_path, parse_authority, read_authority,
)
from .gaming_studio_plan import PLAN_PACKAGE_FILES
from .gaming_studio_plan_checkpoint import RESOLUTION_PACKAGE_FILES
from .gaming_studio_plan_approval import (
    APPROVAL_AREA, APPROVAL_FILES, APPROVAL_STATEMENT_DIGEST,
    production_plan_approval_authorization, validate_plan_approval_authorization,
)
from .gaming_studio_plan_transition import PLAN_TRANSITION_FILES, production_plan_architecture_handoff
from .gaming_studio_transition import CURRENT_PACKAGE_FILES


APPROVAL_CHECKPOINT_SCHEMA = "arcadev.gaming_studio.plan_approval_checkpoint"
APPROVAL_CHECKPOINT_VERSION = 1
APPROVAL_PACKAGE_VERSION = 3
APPROVAL_PACKAGE_FILES = APPROVAL_FILES | PLAN_TRANSITION_FILES | frozenset({"checkpoint.json"})


def historical_authority_names():
    from .gaming_studio_authority import PACKAGE_FILES

    return (PACKAGE_FILES | {f"idea_resolution/{n}" for n in CURRENT_PACKAGE_FILES}
            | {f"production_plan/{n}" for n in PLAN_PACKAGE_FILES}
            | {f"production_plan/plan_resolution/{n}" for n in RESOLUTION_PACKAGE_FILES})


def _authority_digests(directory, package):
    # Only trusted names determine reads; checkpoint-supplied paths are inert.
    return {
        **{name: digest_bytes(read_authority(directory / name)) for name in sorted(historical_authority_names())},
        **{f"{APPROVAL_AREA}/{name}": digest_bytes(package[name])
           for name in sorted(APPROVAL_PACKAGE_FILES - {"checkpoint.json"})},
    }


def production_plan_approval_checkpoint_package(directory=AUTHORITY_DIRECTORY):
    """Reconstruct every approval child through the certified public contracts.

    Historical validation and PLAN replay happen before approval and handoff.
    No supplied approval, eligibility, warning, transition or checkpoint flag
    can replace the independently reconstructed public result.
    """
    directory = local_authority_path(directory)
    handoff = production_plan_architecture_handoff(directory)
    approved = handoff.frozen_approved_plan
    finalization = approved.package.plan_finalization
    consistency = approved.package.consistency.canonical_dict()
    project = handoff.resulting_project
    package = {
        "approval_authorization.json": production_plan_approval_authorization(),
        "approved_plan.json": approved.canonical_json().encode("utf-8"),
        "plan_architecture_handoff.json": handoff.canonical_json().encode("utf-8"),
        "project.json": project.canonical_json().encode("utf-8"),
    }
    checkpoint = {
        "schema": APPROVAL_CHECKPOINT_SCHEMA, "schema_version": APPROVAL_CHECKPOINT_VERSION,
        "package_version": APPROVAL_PACKAGE_VERSION, "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        "project_id": project.project_id, "idea_handoff_id": approved.idea_handoff_id,
        "software_plan_id": approved.software_plan_id,
        "plan_finalization_id": approved.plan_finalization_id,
        "approved_plan_id": approved.approval_id,
        "plan_architecture_handoff_id": handoff.handoff_id,
        "approval_statement_digest": APPROVAL_STATEMENT_DIGEST,
        "approval_decision": approved.decision.value,
        "approval_eligible": approved.approval_eligible,
        "complete_plan_approved": approved.approved,
        "effective_ready_for_architecture": approved.effective_ready_for_architecture,
        "consistency": consistency, "consistency_result": consistency["consistent"],
        "consistency_warnings": consistency["warnings"],
        "unresolved_question_count": len(finalization.unresolved_questions),
        "conflict_count": len(finalization.conflicts),
        "transition_eligible": handoff.transition_eligible,
        "transition_decision": handoff.decision.value,
        "current_stage": project.current_build_stage.value,
        "project_status": project.project_status.value,
        "architecture_specification_id": None, "architecture_generated": False,
        "architecture_generation_authorized": False,
        "status": "ARCHITECTURE_READY_FOR_GENERATION",
        "next_authorized_action": "GENERATE_PRODUCTION_ARCHITECTURE_SPECIFICATION",
        "authority_digests": _authority_digests(directory, package),
    }
    package["checkpoint.json"] = canonical_bytes(checkpoint)
    return package


def validate_plan_approval_checkpoint(directory=AUTHORITY_DIRECTORY):
    """Require the exact full package and compare it with independent replay."""
    directory = local_authority_path(directory)
    area = local_authority_path(directory / APPROVAL_AREA)
    if not area.is_dir() or {p.name for p in area.iterdir()} != APPROVAL_PACKAGE_FILES:
        raise ValueError("PLAN approval package has unknown or missing authority files.")
    actual = {name: read_authority(area / name) for name in sorted(APPROVAL_PACKAGE_FILES)}
    for data in actual.values():
        parse_authority(data)
    validate_plan_approval_authorization(actual["approval_authorization.json"])
    checkpoint = parse_authority(actual["checkpoint.json"])
    if checkpoint.get("authority_digests") != _authority_digests(directory, actual):
        raise ValueError("PLAN approval authority digests do not match the complete lineage.")
    expected = production_plan_approval_checkpoint_package(directory)
    if actual != expected:
        raise ValueError("PLAN approval checkpoint differs from exact certified production replay.")
    return parse_authority(expected["checkpoint.json"])
