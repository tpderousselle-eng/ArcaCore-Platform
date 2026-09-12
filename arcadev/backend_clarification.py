"""Explicit BACKEND decisions and replay-verifiable immutable finalization."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
import re
import unicodedata

from .backend_engine import validate_backend_specification_candidate
from .backend_specification import (
    BackendArea, BackendQuestion, BackendSpecification, Record,
    backend_question_id, backend_handoff, backend_architecture, _safe, _norm,
)
from .architecture_specification import _exact, _identity, _json, _parse, _strings, _text

ARCADEV_BACKEND_CLARIFICATION_ANSWER_SCHEMA = "arcadev.backend_clarification_answer"
ARCADEV_BACKEND_CLARIFICATION_ANSWER_SCHEMA_VERSION = 1
ARCADEV_BACKEND_FINALIZATION_SCHEMA = "arcadev.backend_finalization"
ARCADEV_BACKEND_FINALIZATION_SCHEMA_VERSION = 1
MAX_BACKEND_HISTORY = 256
MAX_BACKEND_ANSWER_LENGTH = 100_000


class BackendResolutionAction(str, Enum):
    ANSWER = "answer"
    REPLACE_DECISION = "replace_decision"


class BackendResolutionOutcome(str, Enum):
    ACCEPTED = "accepted"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class BackendClarificationAnswer(Record):
    target_backend_id: str
    target_finalization_id: str
    target_question_id: str
    user_answer: str
    normalized_values: tuple[str, ...]
    evidence: tuple[str, ...]
    action: BackendResolutionAction
    expected_prior_values: tuple[str, ...]
    provenance: str = "explicit_user"
    schema: str = ARCADEV_BACKEND_CLARIFICATION_ANSWER_SCHEMA
    schema_version: int = ARCADEV_BACKEND_CLARIFICATION_ANSWER_SCHEMA_VERSION

    @classmethod
    def create(cls, *, target_backend_id, target_finalization_id, target_question_id, user_answer,
               normalized_values, evidence, action=BackendResolutionAction.ANSWER, expected_prior_values=()):
        answer = _text(user_answer, "backend user answer", MAX_BACKEND_ANSWER_LENGTH, preserve=True)
        values, citations = _strings(normalized_values, required=True), _strings(evidence, required=True)
        if len({_norm(v) for v in values}) != len(values):
            raise ValueError("Duplicate normalized backend values.")
        if any(value not in answer for value in (*values, *citations)):
            raise ValueError("Backend values and evidence must occur in the unchanged explicit user answer.")
        if any(not any(value in citation for citation in citations) for value in values):
            raise ValueError("Every normalized backend value needs explicit quoted evidence.")
        try:
            action = BackendResolutionAction(action)
        except (TypeError, ValueError) as error:
            raise ValueError("Unsupported backend resolution action.") from error
        prior = _strings(expected_prior_values)
        if action is BackendResolutionAction.ANSWER and prior:
            raise ValueError("An ordinary answer cannot claim replacement values.")
        if action is BackendResolutionAction.REPLACE_DECISION and not prior:
            raise ValueError("Deliberate replacement requires exact prior values.")
        for value, prefix in ((target_backend_id, "backend_specification"), (target_finalization_id, "backend_final"), (target_question_id, "backend_question")):
            if type(value) is not str or not re.fullmatch("arcadev_" + prefix + "_[0-9a-f]{32}", value):
                raise ValueError("Malformed target backend/finalization/question identity.")
        result = cls(target_backend_id, target_finalization_id, target_question_id, answer, values, citations, action, prior)
        _safe(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_BACKEND_CLARIFICATION_ANSWER_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported backend answer schema/version.")
        if value["provenance"] != "explicit_user":
            raise ValueError("Backend answers require explicit user provenance.")
        if any(type(value[key]) is not list for key in ("normalized_values", "evidence", "expected_prior_values")):
            raise ValueError("Backend answer collections must be arrays.")
        return cls.create(**{key: item for key, item in value.items() if key not in {"schema", "schema_version", "provenance"}})

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


@dataclass(frozen=True)
class BackendClaim(Record):
    """A bounded implementation profile over exact frozen question scope."""
    slot: str
    component_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    model_source_ids: tuple[str, ...]
    values: tuple[str, ...]


@dataclass(frozen=True)
class BackendDecision(Record):
    decision_id: str
    question_id: str
    source_question: BackendQuestion
    user_answer: str
    accepted_values: tuple[str, ...]
    area: BackendArea
    architecture_source_ids: tuple[str, ...]
    model_source_ids: tuple[str, ...]
    component_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    claims: tuple[BackendClaim, ...]
    evidence: tuple[str, ...]
    provenance: str
    replaces_decision_id: str | None
    previous_values: tuple[str, ...]

    @classmethod
    def create(cls, question, answer, claims, previous=None):
        provisional = cls("", backend_question_id(question), question, answer.user_answer, answer.normalized_values,
                          question.area, question.architecture_source_ids, question.model_source_ids,
                          question.component_ids, question.operation_ids, claims, answer.evidence, "explicit_user",
                          previous.decision_id if previous else None, previous.accepted_values if previous else ())
        body = provisional.canonical_dict()
        body.pop("decision_id")
        return replace(provisional, decision_id=_identity("backend_decision", body))


@dataclass(frozen=True)
class BackendConflict(Record):
    question_id: str
    code: str
    existing_values: tuple[str, ...]
    proposed_values: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class BackendClarificationHistoryEntry(Record):
    answer: BackendClarificationAnswer
    outcome: BackendResolutionOutcome
    previous_values: tuple[str, ...]
    accepted_values: tuple[str, ...]
    rejected_values: tuple[str, ...]
    resulting_decision_id: str | None
    readiness_before: bool
    readiness_after: bool
    unresolved_before: tuple[str, ...]
    unresolved_after: tuple[str, ...]
    conflicts_before: tuple[BackendConflict, ...]
    conflicts_after: tuple[BackendConflict, ...]


def _attempt_identity(answer):
    body = answer.canonical_dict()
    body.pop("target_finalization_id")
    return _identity("backend_attempt", body)


def _authority_conflict(answer, handoff):
    """Recognize explicit authority changes; bounded profiles are the backstop.

    This is not a general natural-language consistency evaluator. Answer prose
    remains evidence, never instructions for a translator or executable code.
    """
    package = backend_architecture(handoff)
    architecture = package.original_architecture
    authority = unicodedata.normalize("NFKC", package.canonical_json()).casefold()
    text = unicodedata.normalize("NFKC", answer.user_answer).casefold()

    def conflict(code, references, message):
        return BackendConflict(answer.target_question_id, code, references, answer.normalized_values, message)

    patterns = (
        ("github", r"\b(?:do\s+not\s+implement|remove|drop|disable|exclude|no)\s+(?:the\s+)?github\b"),
        ("isolat", r"\b(?:run|execute)\s+builds?\s+(?:directly\s+)?(?:inside|in)\s+(?:the\s+)?main\s+request\s+process\b|\b(?:remove|disable|no)\s+(?:build\s+|worker\s+)?isolation\b"),
        ("postgresql", r"\b(?:replace|remove|drop)\s+postgresql\b|\b(?:use|switch\s+to)\s+(?:sqlite|mysql|mongodb)\s+instead\b"),
        ("managed object storage", r"\b(?:remove|disable|no)\s+(?:managed\s+)?object\s+storage\b"),
        ("authentication", r"\b(?:remove|disable|no)\s+(?:authentication|authorization)\b"),
    )
    for fragment, pattern in patterns:
        if fragment in authority and re.search(pattern, text):
            return conflict("frozen_architecture_conflict", (architecture.architecture_id,),
                            "A backend answer cannot remove or replace frozen architecture authority.")
    for component in architecture.components:
        for label in (component.name, *component.owned_capabilities):
            if re.search(r"\b(?:remove|drop|disable|exclude|without|no)\s+(?:the\s+)?" + re.escape(_norm(label)) + r"\b", text):
                return conflict("frozen_architecture_conflict", (component.component_id,),
                                "A backend answer cannot remove an approved responsibility or capability.")
    model = handoff.frozen_approved_domain_model.package.resolved_model
    related = {(r.source_entity_id, r.target_entity_id) for r in model.relationships}
    related.update((choice.claim.entity_id, choice.claim.related_entity_id) for e in model.entities
                   for choice in e.choices if choice.claim.related_entity_id is not None)
    names = {e.entity_id: _norm(e.name) for e in model.entities}
    if related and re.search(r"\b(?:remove|drop|erase|discard)\s+(?:all\s+)?(?:approved\s+|logical\s+|model\s+)*relationships\b", text):
        return conflict("approved_domain_model_conflict", (model.model_id,),
                        "Approved logical relationships cannot be removed by backend decisions.")
    for source, target in sorted(related):
        # Only actual resolved pairs, including accepted claims, are authority.
        labels = (names[source], names[target])
        if all(label in text or eid in text for label, eid in zip(labels, (source, target))) and re.search(
            r"\b(?:does\s+not|do\s+not|must\s+not|never)\s+(?:retain|keep|preserve)\s+(?:any\s+)?[^.\n]{0,150}\brelationship\b|\b(?:remove|drop|discard)\s+[^.\n]{0,150}\brelationship\b", text):
            return conflict("approved_domain_model_conflict", (source, target),
                            "A backend choice contradicts an approved relationship between these records.")
    if re.search(r"\b(?:remove|drop|change|replace)\s+(?:all\s+)?(?:approved|logical|model)\s+(?:fields|identit(?:y|ies)|lifecycle|retention|constraints)\b", text):
        return conflict("approved_domain_model_conflict", (model.model_id,),
                        "Backend profiles must preserve approved logical state and constraints.")
    for feature in ("billing", "payment", "subscription", "marketplace", "multiplayer", "social feed", "social graph", "chat system", "monetization", "ai npc", "analytics", "achievement"):
        if feature not in authority and re.search(r"\b" + re.escape(feature) + r"s?\b", text.replace("_", " ")):
            return conflict("unsupported_product_scope", (), "A backend answer cannot add unsupported product capabilities.")
    return None


def _claims(question, answer, backend):
    """Explicit named profiles, never generated source or executable expressions.

    Expanded values are bounded semantics for a later authority translator. No
    profile asserts certification of an application-specific generator handler.
    """
    profiles = {
        BackendArea.PERSISTENCE_MAPPING: ("persistence_mapping", {
            "snake_case_unfixed_names": ("snake_case", "unfixed_physical_names_only", "preserve_approved_state"),
        }),
        BackendArea.API_BOUNDARY: ("transport", {
            "http_json": ("http_json", "preserve_authorization"),
        }),
        BackendArea.TRANSACTION: ("transaction_boundary", {
            "operation_atomic": ("atomic_related_state_writes_per_operation", "preserve_approved_constraints"),
        }),
        BackendArea.ASYNC_EXECUTION: ("async_execution", {
            "authenticated_completion_callback": ("authenticated_completion_callback", "preserve_frozen_execution_mechanism"),
            "authorized_status_polling": ("authorized_status_polling", "preserve_frozen_execution_mechanism"),
        }),
        BackendArea.EXTERNAL_INTEGRATION: ("retry_policy", {
            "no_automatic_retry": ("maximum_attempts_1", "delay_seconds_0", "explicit_user_authorization"),
            "transient_retry_twice_no_delay": ("maximum_attempts_2", "delay_seconds_0", "transient_failures_only", "explicit_user_authorization"),
        }),
        BackendArea.FAILURE_SEMANTICS: ("integration_failure", {
            "return_failure_without_state_promotion": ("external_integration_failure", "do_not_promote_unsuccessful_state"),
        }),
        BackendArea.IDEMPOTENCY: ("idempotency", {
            "caller_request_key": ("caller_request_key", "principal_and_operation_scope", "preserve_explicit_action_control"),
        }),
        BackendArea.STORAGE: ("storage_mapping", {
            "entity_identity_reference": ("approved_entity_identity_reference", "preserve_retention_and_deletion"),
        }),
        BackendArea.IMPLEMENTATION_TECHNOLOGY: ("implementation_technology", {
            "require_generator_capability_certification": ("certify_all_approved_responsibilities_before_generation", "fail_closed_on_unrepresented_capability"),
        }),
    }
    for value in answer.normalized_values:
        tagged = re.fullmatch(r"([a-z_]+)\s*[:=]\s*(.+)", value, re.I)
        if tagged and tagged[1].casefold() in {a.value for a in BackendArea} and tagged[1].casefold() != question.area.value:
            return (), "question_area_conflict"
    if len(answer.normalized_values) != 1:
        return (), "unsupported_backend_choice"
    selected = answer.normalized_values[0]
    if question.area not in profiles or selected not in profiles[question.area][1]:
        if any(selected in choices for area, (_, choices) in profiles.items() if area != question.area):
            return (), "question_area_conflict"
        return (), ("uncertified_generator_representation" if question.area is BackendArea.IMPLEMENTATION_TECHNOLOGY else "unsupported_backend_choice")
    if not question.component_ids or (question.area is not BackendArea.STORAGE and not question.operation_ids):
        return (), "question_scope_conflict"
    if question.area in {BackendArea.PERSISTENCE_MAPPING, BackendArea.TRANSACTION, BackendArea.STORAGE} and not question.model_source_ids:
        return (), "question_scope_conflict"
    operations = [o for o in backend.operations if o.operation_id in question.operation_ids]
    if question.area in {BackendArea.EXTERNAL_INTEGRATION, BackendArea.FAILURE_SEMANTICS} and any(o.kind != "integration_action" for o in operations):
        return (), "question_scope_conflict"
    slot, choices = profiles[question.area]
    return (BackendClaim(slot, question.component_ids, question.operation_ids, question.model_source_ids, choices[selected]),), None


def _decision_conflict(answer, claims, decisions):
    def overlaps(left, right):
        # Operation scope keeps distinct release/sync actions separate even
        # after grouping their owners. Fall back to state, then component scope.
        for axis in ("operation_ids", "model_source_ids", "component_ids"):
            a, b = getattr(left, axis), getattr(right, axis)
            if a and b:
                return bool(set(a) & set(b))
        return False

    for decision in decisions:
        if decision.question_id == answer.target_question_id:
            continue
        if any(old.slot == new.slot and old.values != new.values and overlaps(old, new)
               for old in decision.claims for new in claims):
            return BackendConflict(answer.target_question_id, "accepted_decision_conflict", decision.accepted_values,
                answer.normalized_values, "An accepted backend decision already governs this implementation choice and scope.")
    return None

@dataclass(frozen=True)
class BackendFinalization(Record):
    finalization_id: str
    original_backend: BackendSpecification
    decisions: tuple[BackendDecision, ...]
    unresolved_questions: tuple[BackendQuestion, ...]
    conflicts: tuple[BackendConflict, ...]
    history: tuple[BackendClarificationHistoryEntry, ...]
    effective_ready_for_approval: bool
    schema: str = ARCADEV_BACKEND_FINALIZATION_SCHEMA
    schema_version: int = ARCADEV_BACKEND_FINALIZATION_SCHEMA_VERSION

    @staticmethod
    def _effective(backend, unresolved, conflicts):
        structural = set(backend.readiness.blocking_reasons) - {"blocking_backend_questions"}
        return backend.readiness.structurally_valid and not structural and not any(q.blocking for q in unresolved) and not conflicts

    @classmethod
    def _build(cls, backend, decisions=(), unresolved=(), conflicts=(), history=()):
        decisions = tuple(sorted(decisions, key=lambda d: d.question_id))
        unresolved = tuple(sorted(unresolved, key=backend_question_id))
        conflicts = tuple(sorted(conflicts, key=lambda c: (c.question_id, c.code)))
        history = tuple(history)
        if len(history) > MAX_BACKEND_HISTORY:
            raise ValueError("Backend history exceeds its safety limit.")
        result = cls("", backend, decisions, unresolved, conflicts, history, cls._effective(backend, unresolved, conflicts))
        body = result.canonical_dict()
        body.pop("finalization_id")
        result = replace(result, finalization_id=_identity("backend_final", body))
        _safe(result.canonical_dict())
        return result

    @classmethod
    def start(cls, backend, *, handoff):
        backend = validate_backend_specification_candidate(handoff, backend)
        return cls._build(backend, unresolved=backend.open_backend_questions)

    def resolve(self, answer, *, handoff):
        # Public resolutions cannot trust forged dataclass instances or stale history.
        handoff = backend_handoff(handoff)
        state = type(self).from_dict(self.canonical_dict(), handoff=handoff)
        if type(answer) is not BackendClarificationAnswer:
            raise ValueError("Backend resolution requires a validated answer.")
        return state._resolve(BackendClarificationAnswer.from_dict(answer.canonical_dict()), handoff=handoff)

    def _resolve(self, answer, *, handoff):
        """Apply to an already replay-validated state; used internally by replay."""
        if len(self.history) >= MAX_BACKEND_HISTORY:
            raise ValueError("Backend history exceeds its safety limit.")
        if answer.target_backend_id != self.original_backend.backend_id or answer.target_finalization_id != self.finalization_id:
            raise ValueError("Backend answer targets a forged, different, or stale finalization.")
        questions = {backend_question_id(q): q for q in self.original_backend.open_backend_questions}
        if answer.target_question_id not in questions:
            raise ValueError("Backend answer targets a nonexistent or forged question.")
        if any(_attempt_identity(entry.answer) == _attempt_identity(answer) for entry in self.history):
            raise ValueError("Duplicate or replayed backend answer.")
        unresolved = {backend_question_id(q): q for q in self.unresolved_questions}
        decisions = {d.question_id: d for d in self.decisions}
        previous = decisions.get(answer.target_question_id)
        if answer.action is BackendResolutionAction.ANSWER and answer.target_question_id not in unresolved:
            raise ValueError("Backend question is already resolved; deliberate replacement is required.")
        if answer.action is BackendResolutionAction.REPLACE_DECISION and previous is None:
            raise ValueError("Replacement requires an existing backend decision.")
        conflict = _authority_conflict(answer, handoff)
        claims, choice_error = _claims(questions[answer.target_question_id], answer, self.original_backend)
        if conflict is None and choice_error is not None:
            conflict = BackendConflict(answer.target_question_id, choice_error, (), answer.normalized_values,
                                     "The answer is not a supported implementation choice for this question and frozen scope.")
        if conflict is None and previous is not None and answer.expected_prior_values != previous.accepted_values:
            conflict = BackendConflict(answer.target_question_id, "accepted_decision_conflict", previous.accepted_values,
                                            answer.normalized_values, "Replacement requires exact currently accepted prior values.")
        if conflict is None:
            conflict = _decision_conflict(answer, claims, decisions.values())
        if conflict is None and previous is not None and answer.normalized_values == previous.accepted_values:
            raise ValueError("An unchanged backend decision cannot be replayed as a replacement.")
        before_unresolved = tuple(sorted(unresolved))
        conflicts = tuple(c for c in self.conflicts if c.question_id != answer.target_question_id)
        if conflict is not None:
            conflicts += (conflict,)
            outcome = BackendResolutionOutcome.CONFLICT
            accepted, rejected = (), answer.normalized_values
            decision_id = previous.decision_id if previous else None
        else:
            decision = BackendDecision.create(questions[answer.target_question_id], answer, claims, previous)
            decisions[answer.target_question_id] = decision
            unresolved.pop(answer.target_question_id, None)
            outcome = BackendResolutionOutcome.ACCEPTED
            accepted, rejected, decision_id = answer.normalized_values, (), decision.decision_id
        after = self._build(self.original_backend, decisions.values(), unresolved.values(), conflicts, self.history)
        event = BackendClarificationHistoryEntry(answer, outcome, previous.accepted_values if previous else (), accepted, rejected,
            decision_id, self.effective_ready_for_approval, after.effective_ready_for_approval, before_unresolved,
            tuple(sorted(unresolved)), self.conflicts, after.conflicts)
        return self._build(self.original_backend, decisions.values(), unresolved.values(), conflicts, self.history + (event,))

    @classmethod
    def from_dict(cls, value, *, handoff):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_BACKEND_FINALIZATION_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported backend finalization schema/version.")
        if type(value["effective_ready_for_approval"]) is not bool or any(type(value[key]) is not list for key in ("decisions", "unresolved_questions", "conflicts", "history")):
            raise ValueError("Malformed backend finalization.")
        if len(value["history"]) > MAX_BACKEND_HISTORY:
            raise ValueError("Backend history exceeds its safety limit.")
        state = cls.start(value["original_backend"], handoff=handoff)
        for entry in value["history"]:
            _exact(entry, (f.name for f in fields(BackendClarificationHistoryEntry)))
            answer = BackendClarificationAnswer.from_dict(entry["answer"])
            state = state._resolve(answer, handoff=handoff)
            if _json(state.history[-1].canonical_dict()) != _json(entry):
                raise ValueError("Backend history is forged or not replay-verifiable.")
        if _json(state.canonical_dict()) != _json(value):
            raise ValueError("Backend finalization identity, decisions, conflicts, or readiness is forged.")
        return state

    @classmethod
    def from_json(cls, text, *, handoff):
        return cls.from_dict(_parse(text), handoff=handoff)


def resolve_backend_clarification(finalization, candidate, *, handoff):
    if type(candidate) is BackendClarificationAnswer:
        answer = BackendClarificationAnswer.from_dict(candidate.canonical_dict())
    elif type(candidate) is str:
        answer = BackendClarificationAnswer.from_json(candidate)
    elif type(candidate) is dict:
        answer = BackendClarificationAnswer.from_dict(candidate)
    else:
        raise ValueError("Backend clarification requires an inert answer object or JSON text.")
    if type(finalization) is not BackendFinalization:
        raise ValueError("Backend clarification requires a finalization state.")
    return finalization.resolve(answer, handoff=handoff)
