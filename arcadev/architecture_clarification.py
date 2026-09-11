"""Explicit ARCHITECTURE decisions and replay-verifiable immutable finalization."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
import re

from .architecture_engine import validate_architecture_candidate
from .architecture_specification import (
    ArchitectureArea, ArchitectureQuestion, ArchitectureSpecification, Record,
    architecture_question_id, _exact, _identity, _json, _parse, _safe, _strings, _text,
)
from .plan_architecture_handoff import validate_plan_architecture_handoff

ARCADEV_ARCHITECTURE_CLARIFICATION_ANSWER_SCHEMA = "arcadev.architecture_clarification_answer"
ARCADEV_ARCHITECTURE_CLARIFICATION_ANSWER_SCHEMA_VERSION = 1
ARCADEV_ARCHITECTURE_FINALIZATION_SCHEMA = "arcadev.architecture_finalization"
ARCADEV_ARCHITECTURE_FINALIZATION_SCHEMA_VERSION = 1
MAX_ARCHITECTURE_HISTORY = 256
MAX_ARCHITECTURE_ANSWER_LENGTH = 100_000


class ArchitectureResolutionAction(str, Enum):
    ANSWER = "answer"
    REPLACE_DECISION = "replace_decision"


class ArchitectureResolutionOutcome(str, Enum):
    ACCEPTED = "accepted"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class ArchitectureClarificationAnswer(Record):
    target_architecture_id: str
    target_finalization_id: str
    target_question_id: str
    user_answer: str
    normalized_values: tuple[str, ...]
    evidence: tuple[str, ...]
    action: ArchitectureResolutionAction
    expected_prior_values: tuple[str, ...]
    provenance: str = "explicit_user"
    schema: str = ARCADEV_ARCHITECTURE_CLARIFICATION_ANSWER_SCHEMA
    schema_version: int = ARCADEV_ARCHITECTURE_CLARIFICATION_ANSWER_SCHEMA_VERSION

    @classmethod
    def create(cls, *, target_architecture_id, target_finalization_id, target_question_id, user_answer,
               normalized_values, evidence, action=ArchitectureResolutionAction.ANSWER, expected_prior_values=()):
        answer = _text(user_answer, "architecture user answer", MAX_ARCHITECTURE_ANSWER_LENGTH, preserve=True)
        values, citations = _strings(normalized_values, required=True), _strings(evidence, required=True)
        if any(value not in answer for value in (*values, *citations)):
            raise ValueError("Architecture values and evidence must occur in the unchanged explicit user answer.")
        if any(not any(value in citation for citation in citations) for value in values):
            raise ValueError("Every normalized architecture value needs explicit quoted evidence.")
        try:
            action = ArchitectureResolutionAction(action)
        except (TypeError, ValueError) as error:
            raise ValueError("Unsupported architecture resolution action.") from error
        prior = _strings(expected_prior_values)
        if action is ArchitectureResolutionAction.ANSWER and prior:
            raise ValueError("An ordinary answer cannot claim replacement values.")
        if action is ArchitectureResolutionAction.REPLACE_DECISION and not prior:
            raise ValueError("Deliberate replacement requires exact prior values.")
        for value, prefix in ((target_architecture_id, "architecture"), (target_finalization_id, "architecture_final"), (target_question_id, "architecture_question")):
            if type(value) is not str or not re.fullmatch("arcadev_" + prefix + "_[0-9a-f]{32}", value):
                raise ValueError("Malformed target architecture/finalization/question identity.")
        result = cls(target_architecture_id, target_finalization_id, target_question_id, answer, values, citations, action, prior)
        _safe(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_ARCHITECTURE_CLARIFICATION_ANSWER_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported architecture answer schema/version.")
        if value["provenance"] != "explicit_user":
            raise ValueError("Architecture answers require explicit user provenance.")
        if any(type(value[key]) is not list for key in ("normalized_values", "evidence", "expected_prior_values")):
            raise ValueError("Architecture answer collections must be arrays.")
        return cls.create(**{key: item for key, item in value.items() if key not in {"schema", "schema_version", "provenance"}})

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


@dataclass(frozen=True)
class ArchitectureDecision(Record):
    decision_id: str
    question_id: str
    source_question: ArchitectureQuestion
    user_answer: str
    accepted_values: tuple[str, ...]
    area: ArchitectureArea
    plan_source_requirements: tuple[str, ...]
    evidence: tuple[str, ...]
    provenance: str
    replaces_decision_id: str | None
    previous_values: tuple[str, ...]

    @classmethod
    def create(cls, question, answer, previous=None):
        provisional = cls("", architecture_question_id(question), question, answer.user_answer, answer.normalized_values,
                          question.area, question.source_requirements, answer.evidence, "explicit_user",
                          previous.decision_id if previous else None, previous.accepted_values if previous else ())
        body = provisional.canonical_dict()
        body.pop("decision_id")
        return replace(provisional, decision_id=_identity("architecture_decision", body))


@dataclass(frozen=True)
class ArchitectureConflict(Record):
    question_id: str
    code: str
    existing_values: tuple[str, ...]
    proposed_values: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class ArchitectureClarificationHistoryEntry(Record):
    answer: ArchitectureClarificationAnswer
    outcome: ArchitectureResolutionOutcome
    previous_values: tuple[str, ...]
    accepted_values: tuple[str, ...]
    rejected_values: tuple[str, ...]
    resulting_decision_id: str | None
    readiness_before: bool
    readiness_after: bool
    unresolved_before: tuple[str, ...]
    unresolved_after: tuple[str, ...]
    conflicts_before: tuple[ArchitectureConflict, ...]
    conflicts_after: tuple[ArchitectureConflict, ...]


def _attempt_identity(answer):
    body = answer.canonical_dict()
    body.pop("target_finalization_id")
    return _identity("architecture_attempt", body)


def _authority_conflict(answer, handoff):
    """Bounded deterministic conflict rules, not a general natural-language judge.

Whole-category claims use explicit tags. Common destructive/exclusive wording
is also recognized so upstream changes are recorded as blocking conflicts.
Unclassified text can only be an explicit choice for the targeted area; it
never edits or overrides the frozen authority package.
"""
    package = handoff.frozen_approved_plan.package
    intake = package.idea_handoff.snapshot.intake
    authority = {
        "platform": tuple(v.value for v in intake.platform_targets),
        "authentication": tuple(v.value for v in intake.authentication_requirements),
        "integration": tuple(v.value for v in intake.integration_requirements),
        "deployment": tuple(v.value for v in intake.deployment_requirements),
        "capability": tuple(v.value for v in package.plan_finalization.original_plan.in_scope_capabilities),
    }
    tagged = {}
    for value in answer.normalized_values:
        match = re.fullmatch(r"(?i)(platform|authentication|integration|deployment|capability)\s*[:=]\s*(.+)", value)
        if match:
            tagged.setdefault(match[1].casefold(), []).append(match[2].casefold())
    for category, proposed in tagged.items():
        if set(proposed) != {v.casefold() for v in authority[category]}:
            return ArchitectureConflict(answer.target_question_id, "frozen_plan_conflict", _strings(authority[category]), answer.normalized_values,
                                        "The proposed " + category + " claim changes frozen PLAN authority.")
    statements = (*answer.normalized_values, answer.user_answer)
    for category, approved in authority.items():
        for item in approved:
            removal = r"(?i)\b(?:remove|drop|disable|exclude|without|no|replace|instead of|rather than)\s+(?:the\s+)?" + re.escape(item) + r"\b"
            if any(re.search(removal, text) for text in statements):
                return ArchitectureConflict(answer.target_question_id, "frozen_plan_conflict", _strings(approved), answer.normalized_values,
                                            "The answer removes approved " + category + " intent.")
            exclusive = r"(?i)(?:\bonly\s+" + re.escape(item) + r"\b|\b" + re.escape(item) + r"\s+only\b)"
            if len(approved) > 1 and any(re.search(exclusive, text) for text in statements):
                if not all(any(other.casefold() in text.casefold() for text in statements) for other in approved):
                    return ArchitectureConflict(answer.target_question_id, "frozen_plan_conflict", _strings(approved), answer.normalized_values,
                                                "An exclusive architecture choice removes other approved " + category + " values.")
    natural = (
        ("platform", r"(?i)\b(?:ios|android)(?:\s+native)?\s+only\b|\bnative\s+only\b", "web"),
        ("authentication", r"(?i)\bonly\s+passkeys?\b|\bpasskeys?\s+only\b|\bno authentication\b", "password"),
        ("deployment", r"(?i)\bself[ -]hosted\s+only\b|\bonly\s+self[ -]hosted\b", "managed cloud"),
    )
    for category, pattern, approved_fragment in natural:
        if any(approved_fragment in value.casefold() for value in authority[category]) and any(re.search(pattern, text) for text in statements):
            return ArchitectureConflict(answer.target_question_id, "frozen_plan_conflict", _strings(authority[category]), answer.normalized_values,
                                        "The answer contradicts the approved " + category + " decision.")
    policies = (
        ("isolated", r"(?i)\bunisolated\b|\b(?:remove|disable|no|without)\s+(?:build\s+)?isolation\b|\bshared\s+build\s+(?:workers|execution)\b"),
        ("deletion controls", r"(?i)\b(?:remove|disable|no)\s+deletion controls\b"),
        ("user-controlled", r"(?i)\b(?:automatic|uncontrolled)\s+(?:publishing|releases?)\b"),
        ("user-authorized", r"(?i)\b(?:unauthorized|without user authorization)\b"),
    )
    for decision in package.plan_finalization.decisions:
        for fragment, pattern in policies:
            if any(fragment in value.casefold() for value in decision.accepted_values) and any(re.search(pattern, text) for text in statements):
                return ArchitectureConflict(answer.target_question_id, "frozen_plan_conflict", decision.accepted_values, answer.normalized_values,
                                            "The answer contradicts an accepted frozen planning policy.")
    return None


def _decision_conflict(answer, question, decisions):
    for decision in decisions:
        if decision.question_id == answer.target_question_id:
            continue  # Own replacements are separately guarded by exact prior values.
        if decision.area is question.area and decision.plan_source_requirements == question.source_requirements:
            if {v.casefold() for v in decision.accepted_values} != {v.casefold() for v in answer.normalized_values}:
                return ArchitectureConflict(answer.target_question_id, "accepted_decision_conflict", decision.accepted_values,
                                            answer.normalized_values, "An accepted architecture decision already governs this area and source scope.")
    area_names = {area.value for area in ArchitectureArea} - {"authentication", "integration", "deployment"}
    for value in answer.normalized_values:
        match = re.fullmatch(r"([a-z_]+)\s*[:=]\s*(.+)", value, flags=re.I)
        if match and match[1].casefold() in area_names and match[1].casefold() != question.area.value:
            existing = tuple(v for d in decisions if d.area.value == match[1].casefold() for v in d.accepted_values)
            return ArchitectureConflict(answer.target_question_id, "accepted_decision_conflict" if existing else "question_area_conflict",
                                        _strings(tuple(set(existing))), answer.normalized_values, "An answer may resolve only its targeted architecture area.")
    return None


@dataclass(frozen=True)
class ArchitectureFinalization(Record):
    finalization_id: str
    original_architecture: ArchitectureSpecification
    decisions: tuple[ArchitectureDecision, ...]
    unresolved_questions: tuple[ArchitectureQuestion, ...]
    conflicts: tuple[ArchitectureConflict, ...]
    history: tuple[ArchitectureClarificationHistoryEntry, ...]
    effective_ready_for_approval: bool
    schema: str = ARCADEV_ARCHITECTURE_FINALIZATION_SCHEMA
    schema_version: int = ARCADEV_ARCHITECTURE_FINALIZATION_SCHEMA_VERSION

    @staticmethod
    def _effective(architecture, unresolved, conflicts):
        structural = set(architecture.readiness.blocking_reasons) - {"blocking_architecture_questions"}
        return not structural and not any(q.blocking for q in unresolved) and not conflicts

    @classmethod
    def _build(cls, architecture, decisions=(), unresolved=(), conflicts=(), history=()):
        decisions = tuple(sorted(decisions, key=lambda d: d.question_id))
        unresolved = tuple(sorted(unresolved, key=architecture_question_id))
        conflicts = tuple(sorted(conflicts, key=lambda c: (c.question_id, c.code)))
        history = tuple(history)
        if len(history) > MAX_ARCHITECTURE_HISTORY:
            raise ValueError("Architecture history exceeds its safety limit.")
        result = cls("", architecture, decisions, unresolved, conflicts, history, cls._effective(architecture, unresolved, conflicts))
        body = result.canonical_dict()
        body.pop("finalization_id")
        result = replace(result, finalization_id=_identity("architecture_final", body))
        _safe(result.canonical_dict())
        return result

    @classmethod
    def start(cls, architecture, *, handoff):
        architecture = validate_architecture_candidate(handoff, architecture)
        return cls._build(architecture, unresolved=architecture.open_architecture_questions)

    def resolve(self, answer, *, handoff):
        # Public resolutions cannot trust forged dataclass instances or stale history.
        handoff = validate_plan_architecture_handoff(handoff)
        state = type(self).from_dict(self.canonical_dict(), handoff=handoff)
        if type(answer) is not ArchitectureClarificationAnswer:
            raise ValueError("Architecture resolution requires a validated answer.")
        return state._resolve(ArchitectureClarificationAnswer.from_dict(answer.canonical_dict()), handoff=handoff)

    def _resolve(self, answer, *, handoff):
        """Apply to an already replay-validated state; used internally by replay."""
        if len(self.history) >= MAX_ARCHITECTURE_HISTORY:
            raise ValueError("Architecture history exceeds its safety limit.")
        if answer.target_architecture_id != self.original_architecture.architecture_id or answer.target_finalization_id != self.finalization_id:
            raise ValueError("Architecture answer targets a forged, different, or stale finalization.")
        questions = {architecture_question_id(q): q for q in self.original_architecture.open_architecture_questions}
        if answer.target_question_id not in questions:
            raise ValueError("Architecture answer targets a nonexistent or forged question.")
        if any(_attempt_identity(entry.answer) == _attempt_identity(answer) for entry in self.history):
            raise ValueError("Duplicate or replayed architecture answer.")
        unresolved = {architecture_question_id(q): q for q in self.unresolved_questions}
        decisions = {d.question_id: d for d in self.decisions}
        previous = decisions.get(answer.target_question_id)
        if answer.action is ArchitectureResolutionAction.ANSWER and answer.target_question_id not in unresolved:
            raise ValueError("Architecture question is already resolved; deliberate replacement is required.")
        if answer.action is ArchitectureResolutionAction.REPLACE_DECISION and previous is None:
            raise ValueError("Replacement requires an existing architecture decision.")
        conflict = _authority_conflict(answer, handoff)
        if conflict is None and previous is not None and answer.expected_prior_values != previous.accepted_values:
            conflict = ArchitectureConflict(answer.target_question_id, "accepted_decision_conflict", previous.accepted_values,
                                            answer.normalized_values, "Replacement requires exact currently accepted prior values.")
        if conflict is None:
            conflict = _decision_conflict(answer, questions[answer.target_question_id], decisions.values())
        if conflict is None and previous is not None and answer.normalized_values == previous.accepted_values:
            raise ValueError("An unchanged architecture decision cannot be replayed as a replacement.")
        before_unresolved = tuple(sorted(unresolved))
        conflicts = tuple(c for c in self.conflicts if c.question_id != answer.target_question_id)
        if conflict is not None:
            conflicts += (conflict,)
            outcome = ArchitectureResolutionOutcome.CONFLICT
            accepted, rejected = (), answer.normalized_values
            decision_id = previous.decision_id if previous else None
        else:
            decision = ArchitectureDecision.create(questions[answer.target_question_id], answer, previous)
            decisions[answer.target_question_id] = decision
            unresolved.pop(answer.target_question_id, None)
            outcome = ArchitectureResolutionOutcome.ACCEPTED
            accepted, rejected, decision_id = answer.normalized_values, (), decision.decision_id
        after = self._build(self.original_architecture, decisions.values(), unresolved.values(), conflicts, self.history)
        event = ArchitectureClarificationHistoryEntry(answer, outcome, previous.accepted_values if previous else (), accepted, rejected,
            decision_id, self.effective_ready_for_approval, after.effective_ready_for_approval, before_unresolved,
            tuple(sorted(unresolved)), self.conflicts, after.conflicts)
        return self._build(self.original_architecture, decisions.values(), unresolved.values(), conflicts, self.history + (event,))

    @classmethod
    def from_dict(cls, value, *, handoff):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_ARCHITECTURE_FINALIZATION_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported architecture finalization schema/version.")
        if type(value["effective_ready_for_approval"]) is not bool or any(type(value[key]) is not list for key in ("decisions", "unresolved_questions", "conflicts", "history")):
            raise ValueError("Malformed architecture finalization.")
        if len(value["history"]) > MAX_ARCHITECTURE_HISTORY:
            raise ValueError("Architecture history exceeds its safety limit.")
        state = cls.start(value["original_architecture"], handoff=handoff)
        for entry in value["history"]:
            _exact(entry, (f.name for f in fields(ArchitectureClarificationHistoryEntry)))
            answer = ArchitectureClarificationAnswer.from_dict(entry["answer"])
            state = state._resolve(answer, handoff=handoff)
            if _json(state.history[-1].canonical_dict()) != _json(entry):
                raise ValueError("Architecture history is forged or not replay-verifiable.")
        if _json(state.canonical_dict()) != _json(value):
            raise ValueError("Architecture finalization identity, decisions, conflicts, or readiness is forged.")
        return state

    @classmethod
    def from_json(cls, text, *, handoff):
        return cls.from_dict(_parse(text), handoff=handoff)


def resolve_architecture_clarification(finalization, candidate, *, handoff):
    if type(candidate) is ArchitectureClarificationAnswer:
        answer = ArchitectureClarificationAnswer.from_dict(candidate.canonical_dict())
    elif type(candidate) is str:
        answer = ArchitectureClarificationAnswer.from_json(candidate)
    elif type(candidate) is dict:
        answer = ArchitectureClarificationAnswer.from_dict(candidate)
    else:
        raise ValueError("Architecture clarification requires an inert answer object or JSON text.")
    if type(finalization) is not ArchitectureFinalization:
        raise ValueError("Architecture clarification requires a finalization state.")
    return finalization.resolve(answer, handoff=handoff)
