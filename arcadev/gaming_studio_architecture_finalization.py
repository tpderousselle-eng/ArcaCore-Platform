"""Initial unresolved production finalization and public-state review."""

from .architecture_clarification import ArchitectureFinalization
from .architecture_engine import generate_baseline_architecture
from .gaming_studio_architecture import (
    ARCHITECTURE_AREA, production_architecture_inputs, read_architecture_authority,
)
from .gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, local_authority_path


FINALIZATION_FILES = frozenset({"architecture_finalization.json", "clarification_review.json"})
REVIEW_SCHEMA = "arcadev.gaming_studio.architecture_clarification_review"
REVIEW_VERSION = 1


def production_architecture_initial_state(directory=AUTHORITY_DIRECTORY):
    """Independently derive architecture; never replay supplied architecture answers."""
    directory = local_authority_path(directory)
    handoff = production_architecture_inputs(directory)
    architecture = generate_baseline_architecture(handoff)
    raw = read_architecture_authority(directory / ARCHITECTURE_AREA / "architecture_specification.json")
    if raw != architecture.canonical_json().encode("utf-8"):
        raise ValueError("Production architecture differs from exact public baseline generation.")
    return handoff, ArchitectureFinalization.start(architecture, handoff=handoff)


def architecture_clarification_review(handoff, finalization):
    """Project an internally reconstructed initial public finalization."""
    architecture = finalization.original_architecture
    if any(q.blocking for q in finalization.unresolved_questions):
        status, action = "BLOCKED_PENDING_ARCHITECTURE_CLARIFICATION", "COLLECT_EXPLICIT_ARCHITECTURE_CLARIFICATIONS"
    elif finalization.effective_ready_for_approval:
        status, action = "ARCHITECTURE_READY_FOR_APPROVAL", "REQUEST_EXPLICIT_ARCHITECTURE_APPROVAL"
    else:
        status, action = "BLOCKED_PENDING_ARCHITECTURE_COMPLETION", "COMPLETE_REQUIRED_ARCHITECTURE_SECTIONS"
    return {
        "schema": REVIEW_SCHEMA, "schema_version": REVIEW_VERSION,
        "product_key": "gaming_studio", "architecture_id": architecture.architecture_id,
        "architecture_finalization_id": finalization.finalization_id,
        "project_id": architecture.project_id, "handoff_id": architecture.handoff_id,
        "unresolved_question_count": len(finalization.unresolved_questions),
        "conflict_count": len(finalization.conflicts),
        "effective_ready_for_approval": finalization.effective_ready_for_approval,
        "current_stage": handoff.resulting_project.current_build_stage.value,
        "project_status": handoff.resulting_project.project_status.value,
        "status": status, "next_authorized_action": action,
        "architecture_approved": False, "models_authorized": False,
    }


def production_architecture_review_package(directory=AUTHORITY_DIRECTORY):
    handoff, finalization = production_architecture_initial_state(directory)
    return {
        "architecture_finalization.json": finalization.canonical_json().encode("utf-8"),
        "clarification_review.json": canonical_bytes(architecture_clarification_review(handoff, finalization)),
    }


def validate_production_architecture_finalization(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    actual = {name: read_architecture_authority(directory / ARCHITECTURE_AREA / name)
              for name in sorted(FINALIZATION_FILES)}
    handoff, finalization = production_architecture_initial_state(directory)
    expected = {
        "architecture_finalization.json": finalization.canonical_json().encode("utf-8"),
        "clarification_review.json": canonical_bytes(architecture_clarification_review(handoff, finalization)),
    }
    if actual != expected:
        raise ValueError("Production architecture finalization or review differs from exact initial public state.")
    return finalization
