"""Complete current production lineage, ending at MODELS without generation."""

from .gaming_studio_architecture import read_architecture_authority
from .gaming_studio_architecture_approval import (
    APPROVAL_AREA, APPROVAL_FILES, APPROVAL_STATEMENT_DIGEST,
    production_architecture_approval_authorization,
)
from .gaming_studio_architecture_resolution import RESOLUTION_AREA
from .gaming_studio_architecture_resolution_checkpoint import (
    RESOLUTION_PACKAGE_FILES, resolution_historical_authority_names,
)
from .gaming_studio_architecture_transition import TRANSITION_FILES, production_architecture_models_handoff
from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes,
    local_authority_path, parse_authority,
)


MODELS_ENTRY_SCHEMA = "arcadev.gaming_studio.models_entry_checkpoint"
MODELS_ENTRY_VERSION = 1
MODELS_ENTRY_PACKAGE_VERSION = 3
MODELS_ENTRY_FILES = APPROVAL_FILES | TRANSITION_FILES | {"checkpoint.json"}
# Rejection filter only; acceptance always requires complete certified replay.
APPROVED_CHECKPOINT_DIGEST = "006bf4418a17d1ef3aebdf0f8e044a558d58ac73186e90618e8cd971f6891114"
# No existing domain-model checkpoint/action enum exists. Follow the established
# REQUEST_EXPLICIT_* authority convention; this action requests, never generates.
MODELS_ENTRY_STATUS = "MODELS_PENDING_GENERATION_AUTHORIZATION"
NEXT_AUTHORIZED_ACTION = "REQUEST_EXPLICIT_DOMAIN_MODEL_GENERATION_AUTHORIZATION"


def models_entry_historical_authority_names():
    return resolution_historical_authority_names() | {
        f"{RESOLUTION_AREA}/{name}" for name in RESOLUTION_PACKAGE_FILES}


def _authority_digests(directory, package):
    return {
        **{name: digest_bytes(read_architecture_authority(directory / name))
           for name in sorted(models_entry_historical_authority_names())},
        **{f"{APPROVAL_AREA}/{name}": digest_bytes(package[name])
           for name in sorted(MODELS_ENTRY_FILES - {"checkpoint.json"})},
    }


def validate_models_entry_inventory(directory=AUTHORITY_DIRECTORY):
    """Allow exactly the complete local lineage, with no downstream authority.

    Inspect each directory before traversing it. Unknown entries and links are
    rejected before reads or replay, including inside historical child areas.
    """
    directory = local_authority_path(directory)
    files = models_entry_historical_authority_names() | {
        f"{APPROVAL_AREA}/{name}" for name in MODELS_ENTRY_FILES}
    directories = {name.rsplit("/", 1)[0] for name in files if "/" in name}
    pending = [(directory, "")]
    seen = set()
    while pending:
        parent, prefix = pending.pop()
        if not parent.is_dir():
            raise ValueError("MODELS entry package has unknown or missing authority files.")
        for child in parent.iterdir():
            name = prefix + child.name
            child = local_authority_path(child)
            if name in directories and child.is_dir():
                pending.append((child, name + "/"))
            elif name in files and child.is_file():
                seen.add(name)
            else:
                raise ValueError("MODELS entry package has unknown or missing authority files.")
    if seen != files:
        raise ValueError("MODELS entry package has unknown or missing authority files.")
    return directory / APPROVAL_AREA


def production_models_entry_package(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    handoff = production_architecture_models_handoff(directory)
    approved = handoff.frozen_approved_architecture
    architecture = approved.package.original_architecture
    finalization = approved.package.architecture_finalization
    consistency = approved.package.consistency.canonical_dict()
    project = handoff.resulting_project
    package = {
        "approval_authorization.json": production_architecture_approval_authorization(),
        "approved_architecture.json": approved.canonical_json().encode("utf-8"),
        "architecture_models_handoff.json": handoff.canonical_json().encode("utf-8"),
        "project.json": project.canonical_json().encode("utf-8"),
    }
    checkpoint = {
        "schema": MODELS_ENTRY_SCHEMA, "schema_version": MODELS_ENTRY_VERSION,
        "package_version": MODELS_ENTRY_PACKAGE_VERSION, "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        "project_id": project.project_id, "software_plan_id": architecture.software_plan_id,
        "plan_finalization_id": architecture.plan_finalization_id,
        "approved_plan_id": architecture.approved_plan_id,
        "plan_architecture_handoff_id": approved.plan_handoff_id,
        "architecture_specification_id": architecture.architecture_id,
        "architecture_finalization_id": finalization.finalization_id,
        "approved_architecture_id": approved.approval_id,
        "architecture_models_handoff_id": handoff.handoff_id,
        "architecture_approval_statement_digest": APPROVAL_STATEMENT_DIGEST,
        "architecture_approval_decision": approved.decision.value,
        "approval_eligible": approved.approval_eligible,
        "architecture_approved": approved.approved,
        "effective_ready_for_approval": approved.effective_ready_for_approval,
        "consistency": consistency, "consistency_result": consistency["consistent"],
        "consistency_warnings": consistency["warnings"],
        "accepted_decision_ids": [d.decision_id for d in finalization.decisions],
        "accepted_decision_count": len(finalization.decisions),
        "unresolved_question_count": len(finalization.unresolved_questions),
        "conflict_count": len(finalization.conflicts),
        "transition_eligible": handoff.transition_eligible,
        "transition_decision": handoff.decision.value,
        "source_stage": approved.package.plan_handoff.resulting_project.current_build_stage.value,
        "current_stage": project.current_build_stage.value,
        "project_status": project.project_status.value,
        "domain_model_id": None, "domain_model_generated": False,
        "domain_model_generation_authorized": False, "models_approved": False,
        "backend_authorized": False, "frontend_authorized": False,
        "status": MODELS_ENTRY_STATUS, "next_authorized_action": NEXT_AUTHORIZED_ACTION,
        "authority_digests": _authority_digests(directory, package),
    }
    package["checkpoint.json"] = canonical_bytes(checkpoint)
    return package


def validate_models_entry_checkpoint(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    area = validate_models_entry_inventory(directory)
    actual = {name: read_architecture_authority(area / name) for name in sorted(MODELS_ENTRY_FILES)}
    checkpoint = parse_authority(actual["checkpoint.json"])
    if digest_bytes(actual["checkpoint.json"]) != APPROVED_CHECKPOINT_DIGEST:
        raise ValueError("MODELS entry checkpoint differs from exact approved bytes.")
    if checkpoint.get("authority_digests") != _authority_digests(directory, actual):
        raise ValueError("MODELS entry digests differ from the complete certified lineage.")
    expected = production_models_entry_package(directory)
    if actual != expected:
        raise ValueError("MODELS entry differs from exact certified public replay.")
    return parse_authority(expected["checkpoint.json"])
