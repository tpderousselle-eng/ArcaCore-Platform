"""Resolved production architecture through the eight exact public answers."""

from .gaming_studio_architecture import read_architecture_authority
from .gaming_studio_architecture_finalization import architecture_clarification_review
from .gaming_studio_architecture_resolution import (
    RESOLUTION_AREA, _validated_authorization,
)
from .gaming_studio_intent import AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes, local_authority_path


RESOLUTION_REVIEW_SCHEMA = "arcadev.gaming_studio.architecture_resolution_review"
RESOLUTION_REVIEW_VERSION = 1
STATE_FILES = frozenset({"architecture_finalization.json", "resolution_review.json"})
# Early rejection only; accepted bytes must still equal full public reconstruction.
APPROVED_STATE_DIGESTS = {'architecture_finalization.json': '77da4ad6c5c4a677f331d56d62ec06d54298d0a27ed56e64e855f9e170036e35', 'resolution_review.json': '48033465cb831e2b5b16746a6c00d67b4e621955cb365fb9c63779080f812689'}


def replay_architecture_authorization(data, directory=AUTHORITY_DIRECTORY):
    """Validate the fixed envelope and return its sequential public replay result."""
    _, finalization, _ = _validated_authorization(data, directory)
    return finalization


def _resolution_review(handoff, finalization):
    # Only called with the result of trusted, validated public replay below.
    if (len(finalization.decisions) != 8 or len(finalization.history) != 8
            or any(e.outcome.value != "accepted" for e in finalization.history)
            or finalization.unresolved_questions or finalization.conflicts
            or not finalization.effective_ready_for_approval):
        raise ValueError("The complete eight-question architecture resolution is not ready.")
    return {
        **architecture_clarification_review(handoff, finalization),
        "schema": RESOLUTION_REVIEW_SCHEMA, "schema_version": RESOLUTION_REVIEW_VERSION,
        "accepted_decision_ids": [e.resulting_decision_id for e in finalization.history],
        "accepted_decision_count": len(finalization.decisions),
        "history_count": len(finalization.history),
        "history_outcomes": [e.outcome.value for e in finalization.history],
        "decisions": [d.canonical_dict() for d in finalization.decisions],
        "backend_authorized": False, "frontend_authorized": False,
    }


def production_architecture_resolution_state(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    data = read_architecture_authority(directory / RESOLUTION_AREA / "clarification_authorization.json")
    _, finalization, handoff = _validated_authorization(data, directory)
    return {
        "architecture_finalization.json": finalization.canonical_json().encode("utf-8"),
        "resolution_review.json": canonical_bytes(_resolution_review(handoff, finalization)),
    }


def validate_architecture_resolution_state(directory=AUTHORITY_DIRECTORY):
    directory = local_authority_path(directory)
    actual = {name: read_architecture_authority(directory / RESOLUTION_AREA / name) for name in sorted(STATE_FILES)}
    if {name: digest_bytes(raw) for name, raw in actual.items()} != APPROVED_STATE_DIGESTS:
        raise ValueError("Architecture resolution state differs from the exact approved replay.")
    expected = production_architecture_resolution_state(directory)
    if actual != expected:
        raise ValueError("Architecture resolution state differs from exact authorized public replay.")
    return expected
