"""Certified production PLAN handoff only; no architecture content generation."""

from .gaming_studio_intent import (
    AUTHORITY_DIRECTORY, local_authority_path, read_authority,
)
from .gaming_studio_plan import production_plan_inputs
from .gaming_studio_plan_approval import APPROVAL_AREA, validate_plan_approval_package
from .plan_architecture_handoff import PlanArchitectureHandoff


PLAN_TRANSITION_FILES = frozenset({"plan_architecture_handoff.json", "project.json"})


def production_plan_architecture_handoff(directory=AUTHORITY_DIRECTORY):
    """Load certified approval and the still-current immutable PLAN source.

    The public handoff independently validates the frozen approval and exact
    source project. This wrapper implements no transition algorithm.
    """
    directory = local_authority_path(directory)
    approved = validate_plan_approval_package(directory)
    # The general project loader accepts only IDEA. Obtain PLAN through the
    # certified IDEA handoff and compare the actual persisted source exactly.
    source = production_plan_inputs(directory).resulting_project
    if read_authority(directory / "idea_resolution/project.json") != source.canonical_json().encode("utf-8"):
        raise ValueError("Production PLAN source project differs from its certified IDEA handoff.")
    return PlanArchitectureHandoff.create(source_project=source, approved_plan=approved)


def production_plan_transition_state(directory=AUTHORITY_DIRECTORY):
    """Return inert canonical handoff/project bytes and stop at ARCHITECTURE."""
    handoff = production_plan_architecture_handoff(directory)
    return {
        "plan_architecture_handoff.json": handoff.canonical_json().encode("utf-8"),
        "project.json": handoff.resulting_project.canonical_json().encode("utf-8"),
    }


def validate_plan_transition_state(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    area = local_authority_path(directory / APPROVAL_AREA)
    actual = {name: read_authority(area / name) for name in sorted(PLAN_TRANSITION_FILES)}
    expected = production_plan_transition_state(directory)
    if actual != expected:
        raise ValueError("Production PLAN handoff or resulting project differs from certified replay.")
    return PlanArchitectureHandoff.from_json(actual["plan_architecture_handoff.json"].decode("utf-8"))
