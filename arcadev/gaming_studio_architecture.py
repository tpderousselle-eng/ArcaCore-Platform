"""First production architecture, derived only through certified public contracts."""

from .architecture_engine import generate_baseline_architecture
from .architecture_specification import ArchitectureSpecification, MAX_ARCHITECTURE_BYTES
from .gaming_studio_intent import AUTHORITY_DIRECTORY, local_authority_path, read_authority
from .gaming_studio_plan_approval import APPROVAL_AREA
from .gaming_studio_plan_approval_checkpoint import validate_plan_approval_checkpoint
from .plan_architecture_handoff import PlanArchitectureHandoff


ARCHITECTURE_AREA = "production_architecture"
SPECIFICATION_FILES = frozenset({"architecture_specification.json"})
CERTIFIED_HANDOFF_ID = "arcadev_arch_handoff_6a1e0fa782722a73b813dd1937066928"


def read_architecture_authority(path):
    """Use the public architecture size bound without widening historical readers."""
    path = local_authority_path(path)
    if not path.is_file():
        raise ValueError("Architecture authority must be a regular local file.")
    with path.open("rb") as stream:
        data = stream.read(MAX_ARCHITECTURE_BYTES + 1)
    if len(data) > MAX_ARCHITECTURE_BYTES:
        raise ValueError("Architecture authority exceeds its byte limit.")
    return data


def production_architecture_inputs(directory=AUTHORITY_DIRECTORY):
    """Replay the complete approved PLAN before accepting the persisted handoff."""
    directory = local_authority_path(directory)
    validate_plan_approval_checkpoint(directory)
    handoff = PlanArchitectureHandoff.from_json(read_authority(
        directory / APPROVAL_AREA / "plan_architecture_handoff.json").decode("utf-8"))
    project = handoff.resulting_project
    if (handoff.handoff_id != CERTIFIED_HANDOFF_ID
            or project.project_status.value != "IN_PROGRESS"
            or project.current_build_stage.value != "ARCHITECTURE"):
        raise ValueError("Production architecture requires the exact certified ARCHITECTURE handoff.")
    return handoff


def production_architecture_specification(directory=AUTHORITY_DIRECTORY):
    handoff = production_architecture_inputs(directory)
    architecture = generate_baseline_architecture(handoff)
    return ArchitectureSpecification.from_json(architecture.canonical_json(), handoff=handoff)


def production_architecture_specification_package(directory=AUTHORITY_DIRECTORY):
    return {"architecture_specification.json":
            production_architecture_specification(directory).canonical_json().encode("utf-8")}


def validate_production_architecture_specification(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    raw = read_architecture_authority(directory / ARCHITECTURE_AREA / "architecture_specification.json")
    expected = production_architecture_specification(directory)
    if raw != expected.canonical_json().encode("utf-8"):
        raise ValueError("Production architecture differs from exact public baseline generation.")
    return expected
