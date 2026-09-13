"""First production SoftwarePlan, reconstructed exclusively from certified IDEA."""

from .gaming_studio_intent import (
    AUTHORITY_DIRECTORY, load_production_intent, local_authority_path,
    parse_authority, read_authority,
)
from .gaming_studio_transition import validate_transition_package
from .idea_plan_handoff import IdeaPlanHandoff
from .planning_engine import generate_baseline_plan, validate_plan_candidate
from .software_plan import SoftwarePlan


PLAN_PACKAGE_FILES = frozenset({"software_plan.json"})


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
    return plan
