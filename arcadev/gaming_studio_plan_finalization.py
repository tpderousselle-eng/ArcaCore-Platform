"""Replay the three production PLAN answers; readiness never grants approval."""

from .gaming_studio_intent import (
    AUTHORITY_DIRECTORY, canonical_bytes, local_authority_path, read_authority,
)
from .gaming_studio_plan import production_plan_inputs
from .gaming_studio_plan_resolution import PLAN_ID, validate_plan_authorization
from .plan_clarification import PlanClarificationAnswer, PlanFinalization
from .software_plan import SoftwarePlan


RESOLUTION_REVIEW_SCHEMA = "arcadev.gaming_studio.plan_resolution_review"
RESOLUTION_REVIEW_VERSION = 1
STATE_FILES = frozenset({"plan_finalization.json", "resolution_review.json"})


def _replay_plan_authorization(data, directory):
    """Read the original canonical SoftwarePlan and use only public resolution APIs."""
    directory = local_authority_path(directory)
    value = validate_plan_authorization(data, directory)
    handoff = production_plan_inputs(directory)
    plan = SoftwarePlan.from_json(read_authority(
        directory / "production_plan/software_plan.json").decode("utf-8"), handoff=handoff)
    current = PlanFinalization.start(plan, handoff=handoff)
    if current.finalization_id != value["initial_finalization_id"]:
        raise ValueError("Production PLAN authorization has stale initial lineage.")
    for approval in value["approvals"]:
        answer = PlanClarificationAnswer.from_dict(approval["answer"])
        current = current.resolve(answer, handoff=handoff)
        if current.conflicts:
            # Return the public contract's actual blocked state, never advance.
            break
        if current.finalization_id != approval["resulting_finalization_id"]:
            raise ValueError("Production PLAN authorization has stale resulting lineage.")
    return PlanFinalization.from_json(current.canonical_json(), handoff=handoff), handoff


def replay_plan_authorization(data, directory=AUTHORITY_DIRECTORY):
    """Return the public replay result without granting complete PLAN approval."""
    finalization, _ = _replay_plan_authorization(data, directory)
    return finalization


def plan_resolution_review(finalization, *, handoff):
    """Validate readiness by public replay and project a PLAN-only review."""
    finalization = PlanFinalization.from_dict(finalization.canonical_dict(), handoff=handoff)
    plan = finalization.original_plan
    if plan.plan_id != PLAN_ID:
        raise ValueError("Resolution review targets a different production SoftwarePlan.")
    ready = finalization.effective_ready_for_architecture
    if finalization.conflicts:
        status, action = "BLOCKED_PENDING_PLAN_CONFLICT_RESOLUTION", "RESOLVE_PLAN_CLARIFICATION_CONFLICTS"
    elif any(q.blocking for q in finalization.unresolved_questions):
        status, action = "BLOCKED_PENDING_PLAN_CLARIFICATION", "COLLECT_EXPLICIT_PLAN_CLARIFICATIONS"
    elif ready:
        status, action = "PLAN_READY_FOR_APPROVAL", "REQUEST_EXPLICIT_PLAN_APPROVAL"
    else:
        status, action = "BLOCKED_PENDING_PLAN_COMPLETION", "COMPLETE_REQUIRED_PLAN_SECTIONS"
    return {
        "schema": RESOLUTION_REVIEW_SCHEMA, "schema_version": RESOLUTION_REVIEW_VERSION,
        "plan_id": plan.plan_id, "plan_finalization_id": finalization.finalization_id,
        "project_id": plan.project_id, "handoff_id": plan.handoff_id,
        "accepted_decision_ids": [entry.resulting_decision_id for entry in finalization.history
                                  if entry.outcome.value == "accepted"],
        "decisions": [decision.canonical_dict() for decision in finalization.decisions],
        "history_outcomes": [entry.outcome.value for entry in finalization.history],
        "unresolved_question_count": len(finalization.unresolved_questions),
        "conflict_count": len(finalization.conflicts),
        "effective_ready_for_architecture": ready,
        "current_stage": plan.project_stage.value,
        "project_status": handoff.resulting_project.project_status.value,
        "status": status, "next_authorized_action": action,
        "complete_plan_approved": False, "architecture_authorized": False,
    }


def production_plan_resolution_state(directory=AUTHORITY_DIRECTORY):
    """Return inert canonical finalization/review bytes; never write or approve."""
    directory = local_authority_path(directory)
    data = read_authority(directory / "production_plan/plan_resolution/clarification_authorization.json")
    finalization, handoff = _replay_plan_authorization(data, directory)
    return {
        "plan_finalization.json": finalization.canonical_json().encode("utf-8"),
        "resolution_review.json": canonical_bytes(plan_resolution_review(finalization, handoff=handoff)),
    }
