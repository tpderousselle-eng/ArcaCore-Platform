"""Certified production ARCHITECTURE to MODELS handoff, with no generation."""

from .architecture_models_handoff import ArchitectureModelsHandoff
from .gaming_studio_architecture import read_architecture_authority
from .gaming_studio_architecture_approval import APPROVAL_AREA, validate_architecture_approval_package
from .gaming_studio_intent import AUTHORITY_DIRECTORY, local_authority_path
from .gaming_studio_plan_approval import APPROVAL_AREA as PLAN_APPROVAL_AREA


TRANSITION_FILES = frozenset({"architecture_models_handoff.json", "project.json"})


def production_architecture_models_handoff(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    approved = validate_architecture_approval_package(directory)
    package = approved.package
    source = package.plan_handoff.resulting_project
    if read_architecture_authority(directory / PLAN_APPROVAL_AREA / "project.json") != source.canonical_json().encode("utf-8"):
        raise ValueError("Architecture source project differs from its exact certified history.")
    return ArchitectureModelsHandoff.create(source_project=source,
        approved_architecture=approved, handoff=package.plan_handoff,
        architecture=package.original_architecture, finalization=package.architecture_finalization)


def production_architecture_transition_state(directory=AUTHORITY_DIRECTORY):
    handoff = production_architecture_models_handoff(directory)
    return {
        "architecture_models_handoff.json": handoff.canonical_json().encode("utf-8"),
        "project.json": handoff.resulting_project.canonical_json().encode("utf-8"),
    }


def validate_architecture_transition_state(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    actual = {name: read_architecture_authority(directory / APPROVAL_AREA / name)
              for name in sorted(TRANSITION_FILES)}
    handoff = production_architecture_models_handoff(directory)
    expected = {
        "architecture_models_handoff.json": handoff.canonical_json().encode("utf-8"),
        "project.json": handoff.resulting_project.canonical_json().encode("utf-8"),
    }
    if actual != expected:
        raise ValueError("Architecture MODELS handoff or project differs from certified public replay.")
    return handoff
