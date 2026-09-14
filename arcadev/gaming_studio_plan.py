"""First production SoftwarePlan, reconstructed exclusively from certified IDEA."""

from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes,
    load_production_intent, local_authority_path,
    parse_authority, read_authority,
)
from .gaming_studio_transition import CURRENT_PACKAGE_FILES, validate_transition_package
from .idea_plan_handoff import IdeaPlanHandoff
from .planning_engine import generate_baseline_plan, validate_plan_candidate
from .plan_clarification import planning_question_id
from .software_plan import SoftwarePlan


PLAN_PACKAGE_FILES = frozenset({"software_plan.json", "planning_review.json", "checkpoint.json"})
PLANNING_REVIEW_SCHEMA = "arcadev.gaming_studio.planning_review"
PLANNING_REVIEW_SCHEMA_VERSION = 1
PLAN_CHECKPOINT_SCHEMA = "arcadev.gaming_studio.production_plan_checkpoint"
PLAN_CHECKPOINT_SCHEMA_VERSION = 1
PLAN_PACKAGE_VERSION = 3


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


def _baseline_software_plan(handoff):
    plan = generate_baseline_plan(handoff)
    plan = SoftwarePlan.from_json(plan.canonical_json(), handoff=handoff)
    return validate_plan_candidate(handoff, plan)


def production_software_plan(directory=AUTHORITY_DIRECTORY):
    return _baseline_software_plan(production_plan_inputs(directory))


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


def production_plan_package(directory=AUTHORITY_DIRECTORY):
    """Reconstruct all PLAN artifacts from the complete immutable upstream chain.

    Supplied plan/review/checkpoint bytes never supply decisions to reconstruction.
    This function returns inert canonical bytes and performs no writes.
    """
    from .gaming_studio_authority import PACKAGE_FILES

    directory = local_authority_path(directory)
    handoff = production_plan_inputs(directory)
    plan = _baseline_software_plan(handoff)
    review = production_planning_review(plan, handoff=handoff)
    package = {
        "software_plan.json": plan.canonical_json().encode("utf-8"),
        "planning_review.json": canonical_bytes(review),
    }
    upstream_names = sorted(PACKAGE_FILES | {
        f"idea_resolution/{name}" for name in CURRENT_PACKAGE_FILES
    })
    checkpoint = {
        "schema": PLAN_CHECKPOINT_SCHEMA, "schema_version": PLAN_CHECKPOINT_SCHEMA_VERSION,
        "package_version": PLAN_PACKAGE_VERSION, "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        **{key: review[key] for key in (
            "plan_id", "handoff_id", "project_id", "current_stage", "project_status",
            "ready_for_architecture", "blocking_reasons", "blocking_question_ids",
            "unresolved_question_count", "assumption_count", "status", "next_authorized_action",
        )},
        "software_plan_digest": digest_bytes(package["software_plan.json"]),
        "planning_review_digest": digest_bytes(package["planning_review.json"]),
        "authority_digests": {
            name: digest_bytes(read_authority(directory / name)) for name in upstream_names
        },
    }
    package["checkpoint.json"] = canonical_bytes(checkpoint)
    return package


def validate_production_plan_package(directory=AUTHORITY_DIRECTORY):
    """Reject any package differing from baseline reconstruction, even rehashed."""
    directory = local_authority_path(directory)
    area = local_authority_path(directory / "production_plan")
    if not area.is_dir():
        raise ValueError("Production PLAN package has unknown or missing authority files.")
    names = set()
    for path in area.iterdir():
        if path.name in {"plan_resolution", "plan_approval"}:
            if not local_authority_path(path).is_dir():
                raise ValueError("PLAN extension must be a local directory.")
            continue
        names.add(path.name)
    if names != PLAN_PACKAGE_FILES:
        raise ValueError("Production PLAN package has unknown or missing authority files.")
    actual = {name: read_authority(area / name) for name in sorted(PLAN_PACKAGE_FILES)}
    for data in actual.values():
        parse_authority(data)
    expected = production_plan_package(directory)
    if actual != expected:
        raise ValueError("Production PLAN package differs from exact baseline reconstruction.")
    return parse_authority(expected["checkpoint.json"])
