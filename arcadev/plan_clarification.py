"""PLAN-stage clarification decisions and deterministic finalization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Iterable, Mapping
import unicodedata

from .idea_plan_handoff import IdeaPlanHandoff, validate_idea_plan_handoff
from .software_plan import PlanningQuestion, SoftwarePlan, validate_software_plan_candidate


ARCADEV_PLAN_CLARIFICATION_ANSWER_SCHEMA = "arcadev.plan_clarification_answer"
ARCADEV_PLAN_CLARIFICATION_ANSWER_SCHEMA_VERSION = 1
ARCADEV_PLAN_FINALIZATION_SCHEMA = "arcadev.plan_finalization"
ARCADEV_PLAN_FINALIZATION_SCHEMA_VERSION = 1
MAX_PLAN_CLARIFICATION_BYTES = 5_000_000
MAX_PLAN_ANSWER_LENGTH = 100_000
MAX_PLAN_HISTORY = 256
MAX_PLAN_VALUES = 256
_SECRET = re.compile(r"(?i)(?:password|passwd|secret|api[_ -]?key|access[_ -]?token|private[_ -]?key)\s*(?:=|:)\s*[^\s,;]{4,}")
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_AUTHORITY_VALUE = re.compile(r"(?i)^(platform|authentication|integration|deployment)\s*[:=]\s*(.+)$")


class PlanResolutionAction(str, Enum):
    ANSWER = "answer"
    REPLACE_DECISION = "replace_decision"


class PlanResolutionOutcome(str, Enum):
    ACCEPTED = "accepted"
    CONFLICT = "conflict"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Plan clarification document contains duplicate key: {key}")
        result[key] = value
    return result


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has an invalid shape or unsupported fields.")
    return value


def _text(value: Any, label: str, maximum: int, *, preserve: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    result = value if preserve else " ".join(value.split())
    if not result or not result.strip() or len(result) > maximum:
        raise ValueError(f"{label} is empty or exceeds its size limit.")
    try:
        result.encode("utf-8")
    except UnicodeError as error:
        raise ValueError(f"{label} is invalid Unicode.") from error
    if any(unicodedata.category(character) == "Cc" and character not in "\n\r\t" for character in result):
        raise ValueError(f"{label} contains control characters.")
    if _SECRET.search(result) or _PRIVATE_KEY.search(result):
        raise ValueError(f"{label} appears to contain a credential or secret value.")
    return result


def _texts(values: Iterable[str], label: str, *, required: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{label} must be a collection.")
    try:
        result = tuple(sorted((_text(item, label, 8_000) for item in values), key=lambda item: (item.casefold(), item)))
    except TypeError as error:
        raise ValueError(f"{label} must be a collection.") from error
    if (required and not result) or len(result) > MAX_PLAN_VALUES:
        raise ValueError(f"{label} is empty or excessive.")
    if len({item.casefold() for item in result}) != len(result):
        raise ValueError(f"{label} contains duplicate normalized values.")
    return result


def _parse(text: str, label: str) -> Any:
    if not isinstance(text, str):
        raise ValueError(f"{label} must be JSON text.")
    try:
        if len(text.encode("utf-8")) > MAX_PLAN_CLARIFICATION_BYTES:
            raise ValueError(f"{label} exceeds the safety limit.")
        return json.loads(text, object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON.") from error


def planning_question_id(question: PlanningQuestion) -> str:
    if not isinstance(question, PlanningQuestion):
        raise ValueError("Planning question identity requires a validated question.")
    digest = hashlib.sha256(("arcadev-planning-question-identity/v1\0" + _json(question.canonical_dict())).encode("utf-8")).hexdigest()
    return f"arcadev_question_{digest[:32]}"


@dataclass(frozen=True)
class PlanClarificationAnswer:
    target_plan_id: str
    target_finalization_id: str
    target_question_id: str
    user_answer: str
    normalized_values: tuple[str, ...]
    evidence: tuple[str, ...]
    provenance: str
    action: PlanResolutionAction
    expected_prior_values: tuple[str, ...]
    schema: str = ARCADEV_PLAN_CLARIFICATION_ANSWER_SCHEMA
    schema_version: int = ARCADEV_PLAN_CLARIFICATION_ANSWER_SCHEMA_VERSION

    @classmethod
    def create(cls, *, target_plan_id: str, target_finalization_id: str, target_question_id: str,
               user_answer: str, normalized_values: Iterable[str], evidence: Iterable[str],
               action: PlanResolutionAction | str = PlanResolutionAction.ANSWER, expected_prior_values: Iterable[str] = ()) -> "PlanClarificationAnswer":
        answer = _text(user_answer, "planning user answer", MAX_PLAN_ANSWER_LENGTH, preserve=True)
        values = _texts(normalized_values, "normalized planning values", required=True)
        citations = _texts(evidence, "planning answer evidence", required=True)
        if any(item not in answer for item in citations):
            raise ValueError("Planning answer evidence must quote the unchanged user answer.")
        try:
            action = PlanResolutionAction(action)
        except (TypeError, ValueError) as error:
            raise ValueError("Planning resolution action is unsupported.") from error
        prior = _texts(expected_prior_values, "expected prior values")
        if action is PlanResolutionAction.ANSWER and prior:
            raise ValueError("A new planning answer cannot claim prior decision values.")
        if action is PlanResolutionAction.REPLACE_DECISION and not prior:
            raise ValueError("Planning decision replacement requires exact prior values.")
        for identity, label, prefix in (
            (target_plan_id, "target plan identity", "arcadev_plan_"),
            (target_finalization_id, "target finalization identity", "arcadev_plan_final_"),
            (target_question_id, "target question identity", "arcadev_question_"),
        ):
            if not isinstance(identity, str) or not identity.startswith(prefix) or len(identity) != len(prefix) + 32:
                raise ValueError(f"{label} is invalid.")
        return cls(target_plan_id, target_finalization_id, target_question_id, answer, values, citations, "explicit_user", action, prior)

    @classmethod
    def from_dict(cls, value: Any) -> "PlanClarificationAnswer":
        fields = {"target_plan_id", "target_finalization_id", "target_question_id", "user_answer", "normalized_values", "evidence", "provenance", "action", "expected_prior_values", "schema", "schema_version"}
        value = _exact(value, fields, "Plan clarification answer")
        if value["schema"] != ARCADEV_PLAN_CLARIFICATION_ANSWER_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != ARCADEV_PLAN_CLARIFICATION_ANSWER_SCHEMA_VERSION:
            raise ValueError("Plan clarification answer schema or version is unsupported.")
        if value["provenance"] != "explicit_user":
            raise ValueError("Planning answers require explicit user provenance.")
        if not all(isinstance(value[field], list) for field in ("normalized_values", "evidence", "expected_prior_values")):
            raise ValueError("Plan clarification answer collections must be arrays.")
        return cls.create(**{key: value[key] for key in fields - {"schema", "schema_version", "provenance"}})

    @classmethod
    def from_json(cls, text: str) -> "PlanClarificationAnswer":
        return cls.from_dict(_parse(text, "Plan clarification answer"))

    def canonical_dict(self) -> dict[str, Any]:
        return {"action": self.action.value, "evidence": list(self.evidence), "expected_prior_values": list(self.expected_prior_values),
            "normalized_values": list(self.normalized_values), "provenance": self.provenance, "schema": self.schema,
            "schema_version": self.schema_version, "target_finalization_id": self.target_finalization_id,
            "target_plan_id": self.target_plan_id, "target_question_id": self.target_question_id, "user_answer": self.user_answer}

    def canonical_json(self) -> str:
        return _json(self.canonical_dict())


@dataclass(frozen=True)
class PlanningDecision:
    decision_id: str
    question_id: str
    source_question: PlanningQuestion
    accepted_values: tuple[str, ...]
    idea_source_requirements: tuple[str, ...]
    provenance: str
    evidence: tuple[str, ...]

    @classmethod
    def create(cls, question: PlanningQuestion, accepted_values: Iterable[str], evidence: Iterable[str]) -> "PlanningDecision":
        values = _texts(accepted_values, "accepted planning values", required=True)
        citations = _texts(evidence, "planning decision evidence", required=True)
        qid = planning_question_id(question)
        body = {"accepted_values": list(values), "evidence": list(citations), "idea_source_requirements": list(question.source_requirements),
            "provenance": "explicit_user", "question_id": qid, "source_question": question.canonical_dict()}
        digest = hashlib.sha256(("arcadev-planning-decision-identity/v1\0" + _json(body)).encode("utf-8")).hexdigest()
        return cls(f"arcadev_decision_{digest[:32]}", qid, question, values, question.source_requirements, "explicit_user", citations)

    @classmethod
    def from_dict(cls, value: Any) -> "PlanningDecision":
        value = _exact(value, {"decision_id", "question_id", "source_question", "accepted_values", "idea_source_requirements", "provenance", "evidence"}, "Planning decision")
        raw_question = _exact(value["source_question"], {"question", "blocking", "source_requirements"}, "Source planning question")
        if type(raw_question["blocking"]) is not bool or not isinstance(raw_question["source_requirements"], list):
            raise ValueError("Source planning question is malformed.")
        question = object.__new__(PlanningQuestion)
        object.__setattr__(question, "question", _text(raw_question["question"], "planning question", 2_000))
        object.__setattr__(question, "blocking", raw_question["blocking"])
        object.__setattr__(question, "source_requirements", _texts(raw_question["source_requirements"], "question sources", required=True))
        result = cls.create(question, value["accepted_values"], value["evidence"])
        if value != result.canonical_dict():
            raise ValueError("Planning decision identity or provenance is forged.")
        return result

    def canonical_dict(self) -> dict[str, Any]:
        return {"accepted_values": list(self.accepted_values), "decision_id": self.decision_id, "evidence": list(self.evidence),
            "idea_source_requirements": list(self.idea_source_requirements), "provenance": self.provenance,
            "question_id": self.question_id, "source_question": self.source_question.canonical_dict()}


@dataclass(frozen=True)
class PlanningConflict:
    question_id: str
    code: str
    existing_values: tuple[str, ...]
    proposed_values: tuple[str, ...]
    message: str

    @classmethod
    def create(cls, question_id: str, code: str, existing_values=(), proposed_values=(), message="") -> "PlanningConflict":
        return cls(question_id, _text(code, "conflict code", 100), _texts(existing_values, "conflict existing values"),
            _texts(proposed_values, "conflict proposed values", required=True), _text(message, "conflict message", 2_000))

    @classmethod
    def from_dict(cls, value: Any) -> "PlanningConflict":
        value = _exact(value, {"question_id", "code", "existing_values", "proposed_values", "message"}, "Planning conflict")
        return cls.create(**value)

    def canonical_dict(self) -> dict[str, Any]:
        return {"code": self.code, "existing_values": list(self.existing_values), "message": self.message,
            "proposed_values": list(self.proposed_values), "question_id": self.question_id}


@dataclass(frozen=True)
class PlanClarificationHistoryEntry:
    answer: PlanClarificationAnswer
    outcome: PlanResolutionOutcome
    previous_values: tuple[str, ...]
    accepted_values: tuple[str, ...]
    rejected_values: tuple[str, ...]
    resulting_decision_id: str | None
    readiness_before: bool
    readiness_after: bool
    unresolved_before: tuple[str, ...]
    unresolved_after: tuple[str, ...]
    conflicts_before: tuple[str, ...]
    conflicts_after: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "PlanClarificationHistoryEntry":
        fields = {"answer", "outcome", "previous_values", "accepted_values", "rejected_values", "resulting_decision_id",
            "readiness_before", "readiness_after", "unresolved_before", "unresolved_after", "conflicts_before", "conflicts_after"}
        value = _exact(value, fields, "Plan clarification history")
        if type(value["readiness_before"]) is not bool or type(value["readiness_after"]) is not bool:
            raise ValueError("Plan history readiness must be boolean.")
        if any(not isinstance(value[field], list) for field in ("previous_values", "accepted_values", "rejected_values", "unresolved_before", "unresolved_after", "conflicts_before", "conflicts_after")):
            raise ValueError("Plan history collections must be arrays.")
        return cls(PlanClarificationAnswer.from_dict(value["answer"]), PlanResolutionOutcome(value["outcome"]),
            _texts(value["previous_values"], "history previous values"), _texts(value["accepted_values"], "history accepted values"),
            _texts(value["rejected_values"], "history rejected values"), value["resulting_decision_id"],
            value["readiness_before"], value["readiness_after"], tuple(value["unresolved_before"]), tuple(value["unresolved_after"]),
            tuple(value["conflicts_before"]), tuple(value["conflicts_after"]))

    def canonical_dict(self) -> dict[str, Any]:
        return {"accepted_values": list(self.accepted_values), "answer": self.answer.canonical_dict(), "conflicts_after": list(self.conflicts_after),
            "conflicts_before": list(self.conflicts_before), "outcome": self.outcome.value, "previous_values": list(self.previous_values),
            "readiness_after": self.readiness_after, "readiness_before": self.readiness_before, "rejected_values": list(self.rejected_values),
            "resulting_decision_id": self.resulting_decision_id, "unresolved_after": list(self.unresolved_after), "unresolved_before": list(self.unresolved_before)}


def _question_map(questions: Iterable[PlanningQuestion]) -> dict[str, PlanningQuestion]:
    return {planning_question_id(item): item for item in questions}


def _idea_authority_conflict(answer: PlanClarificationAnswer, handoff: IdeaPlanHandoff) -> PlanningConflict | None:
    intake = handoff.snapshot.intake
    authority = {
        "platform": tuple(item.value for item in intake.platform_targets),
        "authentication": tuple(item.value for item in intake.authentication_requirements),
        "integration": tuple(item.value for item in intake.integration_requirements),
        "deployment": tuple(item.value for item in intake.deployment_requirements),
    }
    for value in answer.normalized_values:
        match = _AUTHORITY_VALUE.fullmatch(value)
        if not match:
            continue
        category, proposed = match.group(1).casefold(), " ".join(match.group(2).split())
        approved = authority[category]
        proposed_base = proposed.casefold().removesuffix(" only")
        if proposed_base not in {item.casefold() for item in approved}:
            return PlanningConflict.create(answer.target_question_id, "frozen_idea_conflict", approved, answer.normalized_values,
                f"The proposed {category} decision contradicts the frozen IDEA.")
    return None


@dataclass(frozen=True)
class PlanFinalization:
    finalization_id: str
    original_plan: SoftwarePlan
    decisions: tuple[PlanningDecision, ...]
    unresolved_questions: tuple[PlanningQuestion, ...]
    conflicts: tuple[PlanningConflict, ...]
    history: tuple[PlanClarificationHistoryEntry, ...]
    effective_ready_for_architecture: bool
    schema: str = ARCADEV_PLAN_FINALIZATION_SCHEMA
    schema_version: int = ARCADEV_PLAN_FINALIZATION_SCHEMA_VERSION

    @staticmethod
    def _effective(plan: SoftwarePlan, unresolved: Iterable[PlanningQuestion], conflicts: Iterable[PlanningConflict]) -> bool:
        structural = set(plan.readiness.blocking_reasons) - {"blocking_planning_questions"}
        return not structural and not any(item.blocking for item in unresolved) and not tuple(conflicts)

    @classmethod
    def _build(cls, plan: SoftwarePlan, decisions=(), unresolved=(), conflicts=(), history=()) -> "PlanFinalization":
        decisions = tuple(sorted(decisions, key=lambda item: item.question_id))
        unresolved = tuple(sorted(unresolved, key=planning_question_id))
        conflicts = tuple(sorted(conflicts, key=lambda item: (item.question_id, item.code)))
        history = tuple(history)
        ready = cls._effective(plan, unresolved, conflicts)
        body = {"conflicts": [item.canonical_dict() for item in conflicts], "decisions": [item.canonical_dict() for item in decisions],
            "effective_ready_for_architecture": ready, "history": [item.canonical_dict() for item in history],
            "original_plan": plan.canonical_dict(), "schema": ARCADEV_PLAN_FINALIZATION_SCHEMA,
            "schema_version": ARCADEV_PLAN_FINALIZATION_SCHEMA_VERSION,
            "unresolved_questions": [item.canonical_dict() for item in unresolved]}
        digest = hashlib.sha256(("arcadev-plan-finalization-identity/v1\0" + _json(body)).encode("utf-8")).hexdigest()
        return cls(f"arcadev_plan_final_{digest[:32]}", plan, decisions, unresolved, conflicts, history, ready)

    @classmethod
    def start(cls, plan: SoftwarePlan, *, handoff: IdeaPlanHandoff) -> "PlanFinalization":
        handoff = validate_idea_plan_handoff(handoff.canonical_dict())
        plan = validate_software_plan_candidate(plan, handoff=handoff)
        return cls._build(plan, unresolved=plan.open_planning_questions)

    def resolve(self, answer: PlanClarificationAnswer, *, handoff: IdeaPlanHandoff) -> "PlanFinalization":
        if len(self.history) >= MAX_PLAN_HISTORY:
            raise ValueError("Plan finalization history exceeds its safety limit.")
        answer = PlanClarificationAnswer.from_dict(answer.canonical_dict())
        if answer.target_plan_id != self.original_plan.plan_id or answer.target_finalization_id != self.finalization_id:
            raise ValueError("Planning answer targets a different or stale plan finalization.")
        all_questions = _question_map(self.original_plan.open_planning_questions)
        if answer.target_question_id not in all_questions:
            raise ValueError("Planning answer targets a nonexistent question.")
        unresolved = _question_map(self.unresolved_questions)
        decisions = {item.question_id: item for item in self.decisions}
        before_unresolved = tuple(sorted(unresolved))
        before_conflicts = tuple(f"{item.question_id}:{item.code}" for item in self.conflicts)
        previous = decisions.get(answer.target_question_id)

        if answer.action is PlanResolutionAction.ANSWER:
            if answer.target_question_id not in unresolved:
                raise ValueError("Planning question is already resolved and cannot be replayed.")
        elif previous is None:
            raise ValueError("Planning decision replacement targets an unresolved question.")

        conflict = _idea_authority_conflict(answer, handoff)
        if conflict is None and answer.action is PlanResolutionAction.REPLACE_DECISION and answer.expected_prior_values != previous.accepted_values:
            conflict = PlanningConflict.create(answer.target_question_id, "accepted_decision_conflict", previous.accepted_values,
                answer.normalized_values, "Replacement does not match the exact accepted planning decision.")
        if conflict is not None:
            conflicts = tuple(item for item in self.conflicts if item.question_id != answer.target_question_id) + (conflict,)
            after = self._build(self.original_plan, decisions.values(), unresolved.values(), conflicts, self.history)
            record = PlanClarificationHistoryEntry(answer, PlanResolutionOutcome.CONFLICT,
                previous.accepted_values if previous else (), (), answer.normalized_values, previous.decision_id if previous else None,
                self.effective_ready_for_architecture, after.effective_ready_for_architecture, before_unresolved,
                tuple(sorted(unresolved)), before_conflicts, tuple(f"{item.question_id}:{item.code}" for item in after.conflicts))
            return self._build(self.original_plan, decisions.values(), unresolved.values(), conflicts, self.history + (record,))

        question = all_questions[answer.target_question_id]
        decision = PlanningDecision.create(question, answer.normalized_values, answer.evidence)
        decisions[answer.target_question_id] = decision
        unresolved.pop(answer.target_question_id, None)
        conflicts = tuple(item for item in self.conflicts if item.question_id != answer.target_question_id)
        after = self._build(self.original_plan, decisions.values(), unresolved.values(), conflicts, self.history)
        record = PlanClarificationHistoryEntry(answer, PlanResolutionOutcome.ACCEPTED,
            previous.accepted_values if previous else (), answer.normalized_values, (), decision.decision_id,
            self.effective_ready_for_architecture, after.effective_ready_for_architecture, before_unresolved,
            tuple(sorted(unresolved)), before_conflicts, tuple(f"{item.question_id}:{item.code}" for item in after.conflicts))
        return self._build(self.original_plan, decisions.values(), unresolved.values(), conflicts, self.history + (record,))

    @classmethod
    def from_dict(cls, value: Any, *, handoff: IdeaPlanHandoff) -> "PlanFinalization":
        fields = {"finalization_id", "original_plan", "decisions", "unresolved_questions", "conflicts", "history",
            "effective_ready_for_architecture", "schema", "schema_version"}
        value = _exact(value, fields, "Plan finalization")
        if value["schema"] != ARCADEV_PLAN_FINALIZATION_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != ARCADEV_PLAN_FINALIZATION_SCHEMA_VERSION:
            raise ValueError("Plan finalization schema or version is unsupported.")
        if type(value["effective_ready_for_architecture"]) is not bool or any(not isinstance(value[field], list) for field in ("decisions", "unresolved_questions", "conflicts", "history")):
            raise ValueError("Plan finalization is malformed.")
        if len(value["history"]) > MAX_PLAN_HISTORY:
            raise ValueError("Plan finalization history exceeds its safety limit.")
        plan = SoftwarePlan.from_dict(value["original_plan"], handoff=handoff)
        replayed = cls.start(plan, handoff=handoff)
        for raw in value["history"]:
            expected = PlanClarificationHistoryEntry.from_dict(raw)
            replayed = replayed.resolve(expected.answer, handoff=handoff)
            if replayed.history[-1].canonical_dict() != raw:
                raise ValueError("Plan finalization history is forged.")
        if replayed.canonical_dict() != value:
            raise ValueError("Plan finalization identity, readiness, or result is forged.")
        return replayed

    @classmethod
    def from_json(cls, text: str, *, handoff: IdeaPlanHandoff) -> "PlanFinalization":
        return cls.from_dict(_parse(text, "Plan finalization"), handoff=handoff)

    def canonical_dict(self) -> dict[str, Any]:
        return {"conflicts": [item.canonical_dict() for item in self.conflicts], "decisions": [item.canonical_dict() for item in self.decisions],
            "effective_ready_for_architecture": self.effective_ready_for_architecture, "finalization_id": self.finalization_id,
            "history": [item.canonical_dict() for item in self.history], "original_plan": self.original_plan.canonical_dict(),
            "schema": self.schema, "schema_version": self.schema_version,
            "unresolved_questions": [item.canonical_dict() for item in self.unresolved_questions]}

    def canonical_json(self) -> str:
        return _json(self.canonical_dict())


def resolve_plan_clarification(finalization: PlanFinalization, candidate: PlanClarificationAnswer | Mapping[str, Any] | str, *, handoff: IdeaPlanHandoff) -> PlanFinalization:
    if isinstance(candidate, PlanClarificationAnswer):
        answer = PlanClarificationAnswer.from_dict(candidate.canonical_dict())
    elif isinstance(candidate, str):
        answer = PlanClarificationAnswer.from_json(candidate)
    elif isinstance(candidate, Mapping):
        answer = PlanClarificationAnswer.from_dict(dict(candidate))
    else:
        raise ValueError("Planning clarification candidate must be a validated answer, object, or JSON text.")
    return finalization.resolve(answer, handoff=handoff)
