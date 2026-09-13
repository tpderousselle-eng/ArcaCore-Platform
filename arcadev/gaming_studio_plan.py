"""First production SoftwarePlan, reconstructed exclusively from certified IDEA."""

from .gaming_studio_intent import (
    AUTHORITY_DIRECTORY, canonical_bytes, load_production_intent, local_authority_path,
    parse_authority, read_authority,
)
from .gaming_studio_transition import validate_transition_package
from .idea_plan_handoff import IdeaPlanHandoff
from .planning_engine import generate_baseline_plan, validate_plan_candidate
from .plan_clarification import planning_question_id
from .software_plan import SoftwarePlan


PLAN_PACKAGE_FILES = frozenset({"software_plan.json", "planning_review.json"})
PLANNING_REVIEW_SCHEMA = "arcadev.gaming_studio.planning_review"
PLANNING_REVIEW_SCHEMA_VERSION = 1


def production_plan_inputs(directory=AUTHORITY_DIRECTORY):
    """Validate the entire historical chain before exposing a planning handoff."""
    from .gaming_studio_authority import validate_production_authority

    directory = local_authority_path(directory)
    validate_production_authority(directory, seed_only=True)
    intent = load_production_intent(directory / "production_intent.json")
    validate_transition_package(directory / "idea_resolution", intent)
    handoff = IdeaPlanHandoff.from_dict(parse_authority(read_authority(
        directory / "idea_resolution" / "idea_plan_handoff.json")))
    return handoff


def production_software_plan(directory=AUTHORITY_DIRECTORY):
    handoff = production_plan_inputs(directory)
    plan = generate_baseline_plan(handoff)
    plan = SoftwarePlan.from_json(plan.canonical_json(), handoff=handoff)
    return validate_plan_candidate(handoff, plan)


def production_planning_review(plan, *, handoff):
    """Project the public plan contract; never create planning answers or decisions."""
    plan = SoftwarePlan.from_dict(plan.canonical_dict(), handoff=handoff)
    questions = [{
        "question_id": planning_question_id(question),
        **question.canonical_dict(),
        "why_unresolved": "The baseline SoftwarePlan retains this question; no explicit user planning answer has been accepted.",
        "current_accepted_planning_decision": None,
    } for question in plan.open_planning_questions]
    ready = plan.readiness.ready_for_architecture
    blocking = [q["question_id"] for q in questions if q["blocking"]]
    if blocking:
        status, action = "BLOCKED_PENDING_PLAN_CLARIFICATION", "COLLECT_EXPLICIT_PLAN_CLARIFICATIONS"
    elif ready:
        status, action = "PLAN_READY_FOR_APPROVAL", "REQUEST_EXPLICIT_PLAN_APPROVAL"
    else:
        status, action = "BLOCKED_PENDING_PLAN_COMPLETION", "COMPLETE_REQUIRED_PLAN_SECTIONS"
    return {
        "schema": PLANNING_REVIEW_SCHEMA, "schema_version": PLANNING_REVIEW_SCHEMA_VERSION,
        "plan_id": plan.plan_id, "handoff_id": plan.handoff_id, "project_id": plan.project_id,
        "ready_for_architecture": ready, "blocking_reasons": list(plan.readiness.blocking_reasons),
        "blocking_question_ids": blocking,
        "non_blocking_question_ids": [q["question_id"] for q in questions if not q["blocking"]],
        "unresolved_question_count": len(questions), "assumption_count": len(plan.assumptions),
        "current_stage": plan.project_stage.value,
        "project_status": handoff.resulting_project.project_status.value,
        "status": status, "next_authorized_action": action, "questions": questions,
    }


def validate_production_plan_package(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    area = local_authority_path(directory / "production_plan")
    if not area.is_dir() or {p.name for p in area.iterdir()} != PLAN_PACKAGE_FILES:
        raise ValueError("Production PLAN package has unknown or missing authority files.")
    plan = production_software_plan(directory)
    actual = read_authority(area / "software_plan.json")
    parse_authority(actual)
    if actual != plan.canonical_json().encode("utf-8"):
        raise ValueError("Production SoftwarePlan differs from exact baseline reconstruction.")
    review = production_planning_review(plan, handoff=production_plan_inputs(directory))
    actual_review = read_authority(area / "planning_review.json")
    parse_authority(actual_review)
    if actual_review != canonical_bytes(review):
        raise ValueError("Production planning review differs from exact SoftwarePlan reconstruction.")
    return plan
