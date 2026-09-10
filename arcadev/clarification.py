"""Deterministic clarification resolution and IDEA finalization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping
import unicodedata

from .idea_intake import (
    ClarificationRequirement,
    Confidence,
    IdeaIntake,
    IntentProvenance,
    IntentValue,
)
from .project import ArcaDevProject, ProjectMetadata


ARCADEV_CLARIFICATION_ANSWER_SCHEMA = "arcadev.clarification_answer"
ARCADEV_CLARIFICATION_ANSWER_SCHEMA_VERSION = 1
ARCADEV_IDEA_FINALIZATION_SCHEMA = "arcadev.idea_finalization"
ARCADEV_IDEA_FINALIZATION_SCHEMA_VERSION = 1
MAX_CLARIFICATION_ANSWER_LENGTH = 20_000
MAX_CLARIFICATION_DOCUMENT_BYTES = 5_000_000
MAX_RESOLUTION_VALUES = 256
MAX_RESOLUTION_HISTORY = 256

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_INTAKE_ID = re.compile(r"arcadev_idea_[0-9a-f]{32}\Z")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:password|passwd|secret|api[_ -]?key|access[_ -]?token|private[_ -]?key)"
    r"\s*(?:=|:)\s*[^\s,;]{4,}"
)
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")

_SCALAR_REQUIREMENTS = {
    "proposed_project_name",
    "project_type",
    "product_description",
    "primary_goal",
}
_COLLECTION_REQUIREMENTS = {
    "target_users",
    "requested_features",
    "platform_targets",
    "authentication_requirements",
    "integration_requirements",
    "deployment_requirements",
    "explicit_constraints",
    "non_functional_requirements",
    "technology_preferences",
}
_SUPPORTED_REQUIREMENTS = _SCALAR_REQUIREMENTS | _COLLECTION_REQUIREMENTS
_FIELD_MAXIMUMS = {
    "proposed_project_name": 120,
    "project_type": 64,
    "product_description": 8_000,
    "primary_goal": 4_000,
}


class ResolutionAction(str, Enum):
    ANSWER = "answer"
    CONFIRM_ASSUMPTION = "confirm_assumption"
    REJECT_ASSUMPTION = "reject_assumption"
    REPLACE_ASSUMPTION = "replace_assumption"
    REPLACE_EXPLICIT = "replace_explicit"


class ResolutionOutcome(str, Enum):
    ACCEPTED = "accepted"
    CONFLICT = "conflict"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Clarification document contains duplicate key: {key}")
        result[key] = value
    return result


def _require_exact_dict(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has an invalid shape or unsupported fields.")
    return value


def _validate_text(value: Any, label: str, *, maximum: int, preserve: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    normalized = value if preserve else " ".join(value.split())
    if not normalized or not normalized.strip() or len(normalized) > maximum:
        raise ValueError(f"{label} is empty or exceeds its size limit.")
    try:
        normalized.encode("utf-8")
    except UnicodeError as error:
        raise ValueError(f"{label} is not valid Unicode text.") from error
    if any(
        unicodedata.category(character) == "Cc" and character not in "\n\r\t"
        for character in normalized
    ):
        raise ValueError(f"{label} contains control characters.")
    if _SECRET_ASSIGNMENT.search(normalized) or _PRIVATE_KEY.search(normalized):
        raise ValueError(f"{label} appears to contain a credential or secret value.")
    return normalized


def _validate_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a canonical lowercase identifier.")
    return value


def _canonical_texts(
    values: Iterable[str],
    label: str,
    *,
    maximum: int = 8_000,
    required: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{label} must be a collection of text values.")
    try:
        normalized = tuple(_validate_text(item, label, maximum=maximum) for item in values)
    except TypeError as error:
        raise ValueError(f"{label} must be a collection of text values.") from error
    if required and not normalized:
        raise ValueError(f"{label} must not be empty.")
    if len(normalized) > MAX_RESOLUTION_VALUES:
        raise ValueError(f"{label} exceeds its item limit.")
    ordered = tuple(sorted(normalized, key=lambda item: (item.casefold(), item)))
    if len({item.casefold() for item in ordered}) != len(ordered):
        raise ValueError(f"{label} contains duplicate values.")
    return ordered


def _parse_json(text: str, label: str) -> Any:
    if not isinstance(text, str):
        raise ValueError(f"{label} must be JSON text.")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError as error:
        raise ValueError(f"{label} is not valid Unicode text.") from error
    if size > MAX_CLARIFICATION_DOCUMENT_BYTES:
        raise ValueError(f"{label} exceeds the safety limit.")
    try:
        return json.loads(text, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is not valid JSON.") from error


def idea_intake_id(intake: IdeaIntake) -> str:
    if not isinstance(intake, IdeaIntake):
        raise ValueError("Idea intake identity requires a validated IdeaIntake.")
    validated = IdeaIntake.from_dict(intake.canonical_dict())
    digest = hashlib.sha256(
        ("arcadev-idea-intake-identity/v1\0" + validated.canonical_json()).encode("utf-8")
    ).hexdigest()
    return f"arcadev_idea_{digest[:32]}"


@dataclass(frozen=True)
class ClarificationAnswer:
    target_intake_id: str
    requirement: str
    user_answer: str
    action: ResolutionAction
    normalized_values: tuple[str, ...]
    evidence: tuple[str, ...]
    expected_previous_values: tuple[str, ...]
    target_assumption: str | None
    answer_provenance: IntentProvenance = IntentProvenance.EXPLICIT
    schema: str = ARCADEV_CLARIFICATION_ANSWER_SCHEMA
    schema_version: int = ARCADEV_CLARIFICATION_ANSWER_SCHEMA_VERSION

    @classmethod
    def create(
        cls,
        *,
        target_intake_id: str,
        requirement: str,
        user_answer: str,
        action: ResolutionAction | str = ResolutionAction.ANSWER,
        normalized_values: Iterable[str] = (),
        evidence: Iterable[str],
        expected_previous_values: Iterable[str] = (),
        target_assumption: str | None = None,
    ) -> ClarificationAnswer:
        if not isinstance(target_intake_id, str) or not _INTAKE_ID.fullmatch(target_intake_id):
            raise ValueError("Clarification answer target intake identity is invalid.")
        key = _validate_identifier(requirement, "clarification requirement")
        answer = _validate_text(
            user_answer,
            "clarification user answer",
            maximum=MAX_CLARIFICATION_ANSWER_LENGTH,
            preserve=True,
        )
        try:
            resolution_action = ResolutionAction(action)
        except (TypeError, ValueError) as error:
            raise ValueError("Clarification resolution action is unsupported.") from error
        values = _canonical_texts(normalized_values, "normalized clarification values")
        citations = _canonical_texts(evidence, "clarification answer evidence", required=True)
        previous = _canonical_texts(expected_previous_values, "expected previous values")
        compact_answer = " ".join(answer.split())
        for citation in citations:
            if citation not in answer and " ".join(citation.split()) not in compact_answer:
                raise ValueError("Clarification evidence must quote the unchanged user answer.")
        assumption = None
        if target_assumption is not None:
            assumption = _validate_text(target_assumption, "target assumption", maximum=8_000)

        assumption_actions = {
            ResolutionAction.CONFIRM_ASSUMPTION,
            ResolutionAction.REJECT_ASSUMPTION,
            ResolutionAction.REPLACE_ASSUMPTION,
        }
        if resolution_action in assumption_actions and assumption is None:
            raise ValueError("Assumption resolution requires an exact target assumption.")
        if resolution_action not in assumption_actions and assumption is not None:
            raise ValueError("Only assumption actions may target an assumption.")
        if resolution_action is ResolutionAction.REJECT_ASSUMPTION:
            if values:
                raise ValueError("Rejecting an assumption cannot accept normalized values.")
        elif not values:
            raise ValueError("This clarification action requires normalized values.")
        if resolution_action is ResolutionAction.REPLACE_EXPLICIT:
            if not previous:
                raise ValueError("Explicit replacement requires expected previous values.")
        elif previous:
            raise ValueError("Expected previous values are only valid for explicit replacement.")
        return cls(
            target_intake_id=target_intake_id,
            requirement=key,
            user_answer=answer,
            action=resolution_action,
            normalized_values=values,
            evidence=citations,
            expected_previous_values=previous,
            target_assumption=assumption,
        )

    @classmethod
    def from_dict(cls, value: Any) -> ClarificationAnswer:
        keys = {
            "schema",
            "schema_version",
            "target_intake_id",
            "requirement",
            "user_answer",
            "action",
            "normalized_values",
            "evidence",
            "expected_previous_values",
            "target_assumption",
            "answer_provenance",
        }
        value = _require_exact_dict(value, keys, "Clarification answer")
        if value["schema"] != ARCADEV_CLARIFICATION_ANSWER_SCHEMA:
            raise ValueError("Clarification answer schema is unsupported.")
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != ARCADEV_CLARIFICATION_ANSWER_SCHEMA_VERSION
        ):
            raise ValueError("Clarification answer schema version is unsupported.")
        if value["answer_provenance"] != IntentProvenance.EXPLICIT.value:
            raise ValueError("Clarification answers must have explicit user provenance.")
        for field in ("normalized_values", "evidence", "expected_previous_values"):
            if not isinstance(value[field], list):
                raise ValueError(f"{field} must be a JSON array.")
        return cls.create(
            target_intake_id=value["target_intake_id"],
            requirement=value["requirement"],
            user_answer=value["user_answer"],
            action=value["action"],
            normalized_values=value["normalized_values"],
            evidence=value["evidence"],
            expected_previous_values=value["expected_previous_values"],
            target_assumption=value["target_assumption"],
        )

    @classmethod
    def from_json(cls, text: str) -> ClarificationAnswer:
        return cls.from_dict(_parse_json(text, "Clarification answer"))

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "answer_provenance": self.answer_provenance.value,
            "evidence": list(self.evidence),
            "expected_previous_values": list(self.expected_previous_values),
            "normalized_values": list(self.normalized_values),
            "requirement": self.requirement,
            "schema": self.schema,
            "schema_version": self.schema_version,
            "target_assumption": self.target_assumption,
            "target_intake_id": self.target_intake_id,
            "user_answer": self.user_answer,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_dict())


@dataclass(frozen=True)
class IntentConflict:
    requirement: str
    target_intake_id: str
    existing_values: tuple[str, ...]
    proposed_values: tuple[str, ...]
    user_answer: str

    @classmethod
    def create(
        cls,
        *,
        requirement: str,
        target_intake_id: str,
        existing_values: Iterable[str],
        proposed_values: Iterable[str],
        user_answer: str,
    ) -> IntentConflict:
        key = _validate_identifier(requirement, "conflict requirement")
        if not isinstance(target_intake_id, str) or not _INTAKE_ID.fullmatch(target_intake_id):
            raise ValueError("Conflict target intake identity is invalid.")
        existing = _canonical_texts(existing_values, "conflict existing values", required=True)
        proposed = _canonical_texts(proposed_values, "conflict proposed values", required=True)
        answer = _validate_text(
            user_answer,
            "conflicting user answer",
            maximum=MAX_CLARIFICATION_ANSWER_LENGTH,
            preserve=True,
        )
        return cls(key, target_intake_id, existing, proposed, answer)

    @classmethod
    def from_dict(cls, value: Any) -> IntentConflict:
        value = _require_exact_dict(
            value,
            {"requirement", "target_intake_id", "existing_values", "proposed_values", "user_answer"},
            "Intent conflict",
        )
        for field in ("existing_values", "proposed_values"):
            if not isinstance(value[field], list):
                raise ValueError(f"{field} must be a JSON array.")
        return cls.create(**value)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "existing_values": list(self.existing_values),
            "proposed_values": list(self.proposed_values),
            "requirement": self.requirement,
            "target_intake_id": self.target_intake_id,
            "user_answer": self.user_answer,
        }


@dataclass(frozen=True)
class ClarificationHistoryEntry:
    answer: ClarificationAnswer
    outcome: ResolutionOutcome
    resulting_intake_id: str
    previous_values: tuple[str, ...]
    accepted_values: tuple[str, ...]
    rejected_values: tuple[str, ...]
    readiness_before: bool
    readiness_after: bool
    unresolved_before: tuple[str, ...]
    unresolved_after: tuple[str, ...]
    assumptions_before: tuple[str, ...]
    assumptions_after: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        answer: ClarificationAnswer,
        outcome: ResolutionOutcome | str,
        resulting_intake_id: str,
        previous_values: Iterable[str],
        accepted_values: Iterable[str],
        rejected_values: Iterable[str],
        readiness_before: bool,
        readiness_after: bool,
        unresolved_before: Iterable[str],
        unresolved_after: Iterable[str],
        assumptions_before: Iterable[str],
        assumptions_after: Iterable[str],
    ) -> ClarificationHistoryEntry:
        if not isinstance(answer, ClarificationAnswer):
            raise ValueError("History answer must be a validated clarification answer.")
        try:
            result = ResolutionOutcome(outcome)
        except (TypeError, ValueError) as error:
            raise ValueError("Clarification history outcome is unsupported.") from error
        if not isinstance(resulting_intake_id, str) or not _INTAKE_ID.fullmatch(resulting_intake_id):
            raise ValueError("History resulting intake identity is invalid.")
        if type(readiness_before) is not bool or type(readiness_after) is not bool:
            raise ValueError("History readiness values must be booleans.")
        before_keys = _canonical_texts(unresolved_before, "unresolved requirements before")
        after_keys = _canonical_texts(unresolved_after, "unresolved requirements after")
        for key in (*before_keys, *after_keys):
            _validate_identifier(key, "history unresolved requirement")
        return cls(
            answer=answer,
            outcome=result,
            resulting_intake_id=resulting_intake_id,
            previous_values=_canonical_texts(previous_values, "history previous values"),
            accepted_values=_canonical_texts(accepted_values, "history accepted values"),
            rejected_values=_canonical_texts(rejected_values, "history rejected values"),
            readiness_before=readiness_before,
            readiness_after=readiness_after,
            unresolved_before=before_keys,
            unresolved_after=after_keys,
            assumptions_before=_canonical_texts(assumptions_before, "assumptions before"),
            assumptions_after=_canonical_texts(assumptions_after, "assumptions after"),
        )

    @classmethod
    def from_dict(cls, value: Any) -> ClarificationHistoryEntry:
        keys = {
            "answer",
            "outcome",
            "resulting_intake_id",
            "previous_values",
            "accepted_values",
            "rejected_values",
            "readiness_before",
            "readiness_after",
            "unresolved_before",
            "unresolved_after",
            "assumptions_before",
            "assumptions_after",
        }
        value = _require_exact_dict(value, keys, "Clarification history entry")
        for field in keys - {
            "answer",
            "outcome",
            "resulting_intake_id",
            "readiness_before",
            "readiness_after",
        }:
            if not isinstance(value[field], list):
                raise ValueError(f"{field} must be a JSON array.")
        return cls.create(
            answer=ClarificationAnswer.from_dict(value["answer"]),
            outcome=value["outcome"],
            resulting_intake_id=value["resulting_intake_id"],
            previous_values=value["previous_values"],
            accepted_values=value["accepted_values"],
            rejected_values=value["rejected_values"],
            readiness_before=value["readiness_before"],
            readiness_after=value["readiness_after"],
            unresolved_before=value["unresolved_before"],
            unresolved_after=value["unresolved_after"],
            assumptions_before=value["assumptions_before"],
            assumptions_after=value["assumptions_after"],
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "accepted_values": list(self.accepted_values),
            "answer": self.answer.canonical_dict(),
            "assumptions_after": list(self.assumptions_after),
            "assumptions_before": list(self.assumptions_before),
            "outcome": self.outcome.value,
            "previous_values": list(self.previous_values),
            "readiness_after": self.readiness_after,
            "readiness_before": self.readiness_before,
            "rejected_values": list(self.rejected_values),
            "resulting_intake_id": self.resulting_intake_id,
            "unresolved_after": list(self.unresolved_after),
            "unresolved_before": list(self.unresolved_before),
        }


def _unresolved_keys(intake: IdeaIntake) -> tuple[str, ...]:
    return tuple(sorted(item.requirement for item in intake.unresolved_requirements))


def _assumption_values(intake: IdeaIntake) -> tuple[str, ...]:
    return tuple(item.value for item in intake.assumptions)


def _requirement_items(intake: IdeaIntake, requirement: str) -> tuple[IntentValue, ...]:
    value = getattr(intake, requirement)
    if requirement in _SCALAR_REQUIREMENTS:
        return () if value is None else (value,)
    return tuple(value)


def _intake_arguments(intake: IdeaIntake) -> dict[str, Any]:
    return {
        "original_user_request": intake.original_user_request,
        "proposed_project_name": intake.proposed_project_name,
        "project_type": intake.project_type,
        "product_description": intake.product_description,
        "target_users": intake.target_users,
        "primary_goal": intake.primary_goal,
        "requested_features": intake.requested_features,
        "platform_targets": intake.platform_targets,
        "authentication_requirements": intake.authentication_requirements,
        "integration_requirements": intake.integration_requirements,
        "deployment_requirements": intake.deployment_requirements,
        "explicit_constraints": intake.explicit_constraints,
        "non_functional_requirements": intake.non_functional_requirements,
        "technology_preferences": intake.technology_preferences,
        "unresolved_requirements": intake.unresolved_requirements,
        "assumptions": intake.assumptions,
    }


def _append_answer(intake: IdeaIntake, answer: ClarificationAnswer) -> str:
    return f"{intake.original_user_request}\n{answer.user_answer}"


def _explicit_intent_values(
    answer: ClarificationAnswer, *, source_transcript: str
) -> tuple[IntentValue, ...]:
    maximum = _FIELD_MAXIMUMS.get(answer.requirement, 512)
    if answer.requirement == "project_type":
        for value in answer.normalized_values:
            _validate_identifier(value, "project_type")
    values = []
    for value in answer.normalized_values:
        values.append(
            IntentValue.create(
                value=value,
                provenance=IntentProvenance.EXPLICIT,
                confidence=Confidence.HIGH,
                evidence=answer.evidence,
                original_user_request=source_transcript,
                maximum=maximum,
            )
        )
    return tuple(values)


def _set_requirement(
    arguments: dict[str, Any], requirement: str, values: tuple[IntentValue, ...]
) -> None:
    if requirement in _SCALAR_REQUIREMENTS:
        if len(values) != 1:
            raise ValueError(f"{requirement} requires exactly one normalized value.")
        arguments[requirement] = values[0]
    else:
        if not values:
            raise ValueError(f"{requirement} requires at least one normalized value.")
        arguments[requirement] = values


def _clear_derived_requirement(arguments: dict[str, Any], intake: IdeaIntake, requirement: str) -> None:
    existing = _requirement_items(intake, requirement)
    if existing and all(item.provenance is not IntentProvenance.EXPLICIT for item in existing):
        arguments[requirement] = None if requirement in _SCALAR_REQUIREMENTS else ()


def _without_requirement(
    clarifications: Iterable[ClarificationRequirement], requirement: str
) -> tuple[ClarificationRequirement, ...]:
    return tuple(item for item in clarifications if item.requirement != requirement)


def _history_entry(
    *,
    before: IdeaIntake,
    after: IdeaIntake,
    answer: ClarificationAnswer,
    outcome: ResolutionOutcome,
    previous_values: Iterable[str],
    accepted_values: Iterable[str],
    rejected_values: Iterable[str],
) -> ClarificationHistoryEntry:
    return ClarificationHistoryEntry.create(
        answer=answer,
        outcome=outcome,
        resulting_intake_id=idea_intake_id(after),
        previous_values=previous_values,
        accepted_values=accepted_values,
        rejected_values=rejected_values,
        readiness_before=before.readiness.ready_for_plan,
        readiness_after=after.readiness.ready_for_plan,
        unresolved_before=_unresolved_keys(before),
        unresolved_after=_unresolved_keys(after),
        assumptions_before=_assumption_values(before),
        assumptions_after=_assumption_values(after),
    )


@dataclass(frozen=True)
class IdeaFinalization:
    initial_intake: IdeaIntake
    current_intake: IdeaIntake
    conflicts: tuple[IntentConflict, ...]
    history: tuple[ClarificationHistoryEntry, ...]
    schema: str = ARCADEV_IDEA_FINALIZATION_SCHEMA
    schema_version: int = ARCADEV_IDEA_FINALIZATION_SCHEMA_VERSION

    @classmethod
    def start(cls, intake: IdeaIntake) -> IdeaFinalization:
        if not isinstance(intake, IdeaIntake):
            raise ValueError("Idea finalization requires a validated IdeaIntake.")
        validated = IdeaIntake.from_dict(intake.canonical_dict())
        return cls(validated, validated, (), ())

    @property
    def initial_intake_id(self) -> str:
        return idea_intake_id(self.initial_intake)

    @property
    def current_intake_id(self) -> str:
        return idea_intake_id(self.current_intake)

    def resolve(self, answer: ClarificationAnswer) -> IdeaFinalization:
        if len(self.history) >= MAX_RESOLUTION_HISTORY:
            raise ValueError("Idea finalization exceeds its clarification history limit.")
        if not isinstance(answer, ClarificationAnswer):
            raise ValueError("Resolution requires a validated clarification answer.")
        answer = ClarificationAnswer.from_dict(answer.canonical_dict())
        before = IdeaIntake.from_dict(self.current_intake.canonical_dict())
        if answer.target_intake_id != idea_intake_id(before):
            raise ValueError("Clarification answer targets a different or stale idea intake.")
        requirement = answer.requirement
        if requirement not in _SUPPORTED_REQUIREMENTS:
            raise ValueError("Clarification answer targets a nonexistent requirement.")
        active_clarification = any(
            item.requirement == requirement for item in before.unresolved_requirements
        )
        active_conflicts = tuple(
            item for item in self.conflicts if item.requirement == requirement
        )
        existing_items = _requirement_items(before, requirement)
        existing_values = tuple(item.value for item in existing_items)
        transcript = _append_answer(before, answer)
        arguments = _intake_arguments(before)
        arguments["original_user_request"] = transcript
        conflicts = list(self.conflicts)

        assumption_actions = {
            ResolutionAction.CONFIRM_ASSUMPTION,
            ResolutionAction.REJECT_ASSUMPTION,
            ResolutionAction.REPLACE_ASSUMPTION,
        }
        if answer.action in assumption_actions:
            if not active_clarification:
                raise ValueError("Assumption resolution must target a currently unresolved requirement.")
            matching_assumptions = tuple(
                item for item in before.assumptions if item.value == answer.target_assumption
            )
            if len(matching_assumptions) != 1:
                raise ValueError("Target assumption does not exist uniquely on this idea intake.")
            arguments["assumptions"] = tuple(
                item for item in before.assumptions if item.value != answer.target_assumption
            )
            if answer.action is ResolutionAction.REJECT_ASSUMPTION:
                _clear_derived_requirement(arguments, before, requirement)
                after = IdeaIntake.create(**arguments)
                accepted_values: tuple[str, ...] = ()
            else:
                normalized = _explicit_intent_values(answer, source_transcript=transcript)
                if (
                    answer.action is ResolutionAction.CONFIRM_ASSUMPTION
                    and tuple(sorted(answer.normalized_values, key=str.casefold))
                    != tuple(sorted(existing_values, key=str.casefold))
                ):
                    raise ValueError("Assumption confirmation must preserve the existing normalized value.")
                _set_requirement(arguments, requirement, normalized)
                arguments["unresolved_requirements"] = _without_requirement(
                    before.unresolved_requirements, requirement
                )
                after = IdeaIntake.create(**arguments)
                accepted_values = answer.normalized_values
            record = _history_entry(
                before=before,
                after=after,
                answer=answer,
                outcome=ResolutionOutcome.ACCEPTED,
                previous_values=existing_values,
                accepted_values=accepted_values,
                rejected_values=(),
            )
            return IdeaFinalization(
                self.initial_intake, after, tuple(conflicts), self.history + (record,)
            )

        if answer.action is ResolutionAction.REPLACE_EXPLICIT:
            if not active_clarification or len(active_conflicts) != 1:
                raise ValueError("Explicit replacement requires one active intent conflict.")
            if answer.expected_previous_values != tuple(
                sorted(existing_values, key=lambda item: (item.casefold(), item))
            ):
                raise ValueError("Explicit replacement does not match the existing values.")
            normalized = _explicit_intent_values(answer, source_transcript=transcript)
            _set_requirement(arguments, requirement, normalized)
            arguments["unresolved_requirements"] = _without_requirement(
                before.unresolved_requirements, requirement
            )
            conflicts = [item for item in conflicts if item.requirement != requirement]
            after = IdeaIntake.create(**arguments)
            record = _history_entry(
                before=before,
                after=after,
                answer=answer,
                outcome=ResolutionOutcome.ACCEPTED,
                previous_values=existing_values,
                accepted_values=answer.normalized_values,
                rejected_values=(),
            )
            return IdeaFinalization(
                self.initial_intake, after, tuple(conflicts), self.history + (record,)
            )

        if answer.action is not ResolutionAction.ANSWER:
            raise ValueError("Clarification resolution action is not valid for this requirement.")
        if active_conflicts:
            raise ValueError("An active conflict requires deliberate explicit replacement.")
        if existing_items and before.assumptions and active_clarification:
            raise ValueError("Use an explicit assumption action to resolve this tentative value.")
        if existing_items:
            canonical_existing = tuple(
                sorted(existing_values, key=lambda item: (item.casefold(), item))
            )
            if answer.normalized_values == canonical_existing and not active_clarification:
                raise ValueError("This requirement is already resolved.")
            if answer.normalized_values != canonical_existing:
                conflict = IntentConflict.create(
                    requirement=requirement,
                    target_intake_id=answer.target_intake_id,
                    existing_values=existing_values,
                    proposed_values=answer.normalized_values,
                    user_answer=answer.user_answer,
                )
                evidence = tuple(
                    dict.fromkeys(
                        citation for item in existing_items for citation in item.evidence
                    )
                )
                conflict_clarification = ClarificationRequirement.create(
                    requirement=requirement,
                    question=(
                        f"Resolve the conflict between the existing {requirement} value and the proposed replacement."
                    ),
                    blocking=True,
                    evidence=evidence,
                    original_user_request=transcript,
                )
                arguments["unresolved_requirements"] = _without_requirement(
                    before.unresolved_requirements, requirement
                ) + (conflict_clarification,)
                after = IdeaIntake.create(**arguments)
                conflicts.append(conflict)
                conflicts = sorted(
                    conflicts, key=lambda item: (item.requirement, item.target_intake_id)
                )
                record = _history_entry(
                    before=before,
                    after=after,
                    answer=answer,
                    outcome=ResolutionOutcome.CONFLICT,
                    previous_values=existing_values,
                    accepted_values=(),
                    rejected_values=answer.normalized_values,
                )
                return IdeaFinalization(
                    self.initial_intake, after, tuple(conflicts), self.history + (record,)
                )
        if not active_clarification:
            raise ValueError("Clarification answer does not target a currently unresolved requirement.")
        normalized = _explicit_intent_values(answer, source_transcript=transcript)
        _set_requirement(arguments, requirement, normalized)
        arguments["unresolved_requirements"] = _without_requirement(
            before.unresolved_requirements, requirement
        )
        after = IdeaIntake.create(**arguments)
        record = _history_entry(
            before=before,
            after=after,
            answer=answer,
            outcome=ResolutionOutcome.ACCEPTED,
            previous_values=existing_values,
            accepted_values=answer.normalized_values,
            rejected_values=(),
        )
        return IdeaFinalization(
            self.initial_intake, after, tuple(conflicts), self.history + (record,)
        )

    @classmethod
    def from_dict(cls, value: Any) -> IdeaFinalization:
        keys = {
            "schema",
            "schema_version",
            "initial_intake_id",
            "current_intake_id",
            "initial_intake",
            "current_intake",
            "conflicts",
            "history",
        }
        value = _require_exact_dict(value, keys, "Idea finalization")
        if value["schema"] != ARCADEV_IDEA_FINALIZATION_SCHEMA:
            raise ValueError("Idea finalization schema is unsupported.")
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != ARCADEV_IDEA_FINALIZATION_SCHEMA_VERSION
        ):
            raise ValueError("Idea finalization schema version is unsupported.")
        if not isinstance(value["conflicts"], list) or not isinstance(value["history"], list):
            raise ValueError("Idea finalization history and conflicts must be JSON arrays.")
        if len(value["history"]) > MAX_RESOLUTION_HISTORY:
            raise ValueError("Idea finalization exceeds its clarification history limit.")
        if len(value["conflicts"]) > len(_SUPPORTED_REQUIREMENTS):
            raise ValueError("Idea finalization contains excessive conflicts.")
        initial = IdeaIntake.from_dict(value["initial_intake"])
        expected_current = IdeaIntake.from_dict(value["current_intake"])
        if value["initial_intake_id"] != idea_intake_id(initial):
            raise ValueError("Idea finalization initial intake identity is forged.")
        if value["current_intake_id"] != idea_intake_id(expected_current):
            raise ValueError("Idea finalization current intake identity is forged.")
        expected_history = tuple(
            ClarificationHistoryEntry.from_dict(item) for item in value["history"]
        )
        expected_conflicts = tuple(IntentConflict.from_dict(item) for item in value["conflicts"])
        replayed = cls.start(initial)
        for expected_record in expected_history:
            replayed = replayed.resolve(expected_record.answer)
            if replayed.history[-1] != expected_record:
                raise ValueError("Idea finalization history does not match deterministic replay.")
        if replayed.current_intake != expected_current or replayed.conflicts != expected_conflicts:
            raise ValueError("Idea finalization result does not match deterministic history.")
        return replayed

    @classmethod
    def from_json(cls, text: str) -> IdeaFinalization:
        return cls.from_dict(_parse_json(text, "Idea finalization"))

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "conflicts": [item.canonical_dict() for item in self.conflicts],
            "current_intake": self.current_intake.canonical_dict(),
            "current_intake_id": self.current_intake_id,
            "history": [item.canonical_dict() for item in self.history],
            "initial_intake": self.initial_intake.canonical_dict(),
            "initial_intake_id": self.initial_intake_id,
            "schema": self.schema,
            "schema_version": self.schema_version,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_dict())

    def to_project(self, *, metadata: ProjectMetadata) -> ArcaDevProject:
        validated = IdeaFinalization.from_dict(self.canonical_dict())
        if validated.conflicts:
            raise ValueError("An IDEA with unresolved conflicts cannot become a project.")
        return validated.current_intake.to_project(metadata=metadata)


def validate_resolution_candidate(
    intake: IdeaIntake, candidate: Mapping[str, Any] | str
) -> ClarificationAnswer:
    target = idea_intake_id(intake)
    if isinstance(candidate, str):
        answer = ClarificationAnswer.from_json(candidate)
    elif isinstance(candidate, Mapping):
        answer = ClarificationAnswer.from_dict(dict(candidate))
    else:
        raise ValueError("Clarification candidate must be a JSON object or JSON text.")
    if answer.target_intake_id != target:
        raise ValueError("Clarification candidate targets a different or stale idea intake.")
    return answer


def resolve_clarification(
    finalization: IdeaFinalization, candidate: ClarificationAnswer | Mapping[str, Any] | str
) -> IdeaFinalization:
    if not isinstance(finalization, IdeaFinalization):
        raise ValueError("Resolution requires a validated IdeaFinalization.")
    if isinstance(candidate, ClarificationAnswer):
        answer = validate_resolution_candidate(
            finalization.current_intake, candidate.canonical_dict()
        )
    else:
        answer = validate_resolution_candidate(finalization.current_intake, candidate)
    return finalization.resolve(answer)
