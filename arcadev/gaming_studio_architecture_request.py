"""Inert architecture questions for future explicit user responses."""

from .architecture_specification import architecture_question_id
from .gaming_studio_architecture import ARCHITECTURE_AREA, read_architecture_authority
from .gaming_studio_architecture_finalization import validate_production_architecture_finalization
from .gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, local_authority_path


REQUEST_SCHEMA = "arcadev.gaming_studio.architecture_clarification_request"
REQUEST_VERSION = 1
REQUEST_FILES = frozenset({"clarification_request.json"})


def architecture_clarification_request(finalization):
    """Project a validated finalization without adding answers or recommendations."""
    architecture = finalization.original_architecture
    questions = [{
        "ordinal": ordinal, "architecture_question_id": architecture_question_id(question),
        "question": question.question, "blocking": question.blocking,
        "area": question.area.value, "source_requirements": list(question.source_requirements),
        "architecture_id": architecture.architecture_id,
        "architecture_finalization_id": finalization.finalization_id,
    } for ordinal, question in enumerate(sorted(finalization.unresolved_questions,
                                                key=architecture_question_id), 1)]
    return {
        "schema": REQUEST_SCHEMA, "schema_version": REQUEST_VERSION,
        "product_key": "gaming_studio", "project_id": architecture.project_id,
        "question_count": len(questions), "questions": questions,
        "authority": False, "answers_present": False, "requires_explicit_user": True,
    }


def production_architecture_request_package(directory=AUTHORITY_DIRECTORY):
    finalization = validate_production_architecture_finalization(directory)
    return {"clarification_request.json": canonical_bytes(architecture_clarification_request(finalization))}


def validate_production_architecture_request(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    raw = read_architecture_authority(directory / ARCHITECTURE_AREA / "clarification_request.json")
    finalization = validate_production_architecture_finalization(directory)
    request = architecture_clarification_request(finalization)
    if raw != canonical_bytes(request):
        raise ValueError("Architecture request differs from the exact inert unresolved question manifest.")
    return request
