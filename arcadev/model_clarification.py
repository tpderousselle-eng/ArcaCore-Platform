"""Explicit MODEL decisions and replay-verifiable immutable finalization."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
import re
import unicodedata

from .domain_model_engine import validate_domain_model_candidate
from .domain_model_specification import (
    ModelArea, ModelQuestion, DomainModelSpecification, Record,
    model_question_id, model_handoff, _model_safe as _safe, _norm,
)
from .architecture_specification import _exact, _identity, _json, _parse, _strings, _text

ARCADEV_MODEL_CLARIFICATION_ANSWER_SCHEMA = "arcadev.model_clarification_answer"
ARCADEV_MODEL_CLARIFICATION_ANSWER_SCHEMA_VERSION = 1
ARCADEV_MODEL_FINALIZATION_SCHEMA = "arcadev.model_finalization"
ARCADEV_MODEL_FINALIZATION_SCHEMA_VERSION = 1
MAX_MODEL_HISTORY = 256
MAX_MODEL_ANSWER_LENGTH = 100_000


class ModelResolutionAction(str, Enum):
    ANSWER = "answer"
    REPLACE_DECISION = "replace_decision"


class ModelResolutionOutcome(str, Enum):
    ACCEPTED = "accepted"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class ModelClarificationAnswer(Record):
    target_model_id: str
    target_finalization_id: str
    target_question_id: str
    user_answer: str
    normalized_values: tuple[str, ...]
    evidence: tuple[str, ...]
    action: ModelResolutionAction
    expected_prior_values: tuple[str, ...]
    provenance: str = "explicit_user"
    schema: str = ARCADEV_MODEL_CLARIFICATION_ANSWER_SCHEMA
    schema_version: int = ARCADEV_MODEL_CLARIFICATION_ANSWER_SCHEMA_VERSION

    @classmethod
    def create(cls, *, target_model_id, target_finalization_id, target_question_id, user_answer,
               normalized_values, evidence, action=ModelResolutionAction.ANSWER, expected_prior_values=()):
        answer = _text(user_answer, "model user answer", MAX_MODEL_ANSWER_LENGTH, preserve=True)
        values, citations = _strings(normalized_values, required=True), _strings(evidence, required=True)
        if len({_norm(v) for v in values}) != len(values):
            raise ValueError("Duplicate normalized model values.")
        if any(value not in answer for value in (*values, *citations)):
            raise ValueError("Model values and evidence must occur in the unchanged explicit user answer.")
        if any(not any(value in citation for citation in citations) for value in values):
            raise ValueError("Every normalized model value needs explicit quoted evidence.")
        try:
            action = ModelResolutionAction(action)
        except (TypeError, ValueError) as error:
            raise ValueError("Unsupported model resolution action.") from error
        prior = _strings(expected_prior_values)
        if action is ModelResolutionAction.ANSWER and prior:
            raise ValueError("An ordinary answer cannot claim replacement values.")
        if action is ModelResolutionAction.REPLACE_DECISION and not prior:
            raise ValueError("Deliberate replacement requires exact prior values.")
        for value, prefix in ((target_model_id, "domain_model"), (target_finalization_id, "model_final"), (target_question_id, "model_question")):
            if type(value) is not str or not re.fullmatch("arcadev_" + prefix + "_[0-9a-f]{32}", value):
                raise ValueError("Malformed target model/finalization/question identity.")
        result = cls(target_model_id, target_finalization_id, target_question_id, answer, values, citations, action, prior)
        _safe(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_MODEL_CLARIFICATION_ANSWER_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported model answer schema/version.")
        if value["provenance"] != "explicit_user":
            raise ValueError("Model answers require explicit user provenance.")
        if any(type(value[key]) is not list for key in ("normalized_values", "evidence", "expected_prior_values")):
            raise ValueError("Model answer collections must be arrays.")
        return cls.create(**{key: item for key, item in value.items() if key not in {"schema", "schema_version", "provenance"}})

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


@dataclass(frozen=True)
class ModelClaim(Record):
    """A bounded logical choice; never an instruction or implementation fragment."""
    slot: str
    entity_id: str
    related_entity_id: str | None
    values: tuple[str, ...]


@dataclass(frozen=True)
class ModelDecision(Record):
    decision_id: str
    question_id: str
    source_question: ModelQuestion
    user_answer: str
    accepted_values: tuple[str, ...]
    area: ModelArea
    architecture_source_requirements: tuple[str, ...]
    affected_entity_ids: tuple[str, ...]
    affected_field_ids: tuple[str, ...]
    affected_relationship_ids: tuple[str, ...]
    claims: tuple[ModelClaim, ...]
    evidence: tuple[str, ...]
    provenance: str
    replaces_decision_id: str | None
    previous_values: tuple[str, ...]

    @classmethod
    def create(cls, question, answer, claims, model, previous=None):
        provisional = cls("", model_question_id(question), question, answer.user_answer, answer.normalized_values,
                          question.area, question.source_requirements, question.entity_ids,
                          tuple(sorted(f.field_id for e in model.entities if e.entity_id in question.entity_ids for f in e.fields
                                       if f.evidence.question_id == question.question_id)),
                          question.relationship_ids, claims, answer.evidence, "explicit_user",
                          previous.decision_id if previous else None, previous.accepted_values if previous else ())
        body = provisional.canonical_dict()
        body.pop("decision_id")
        return replace(provisional, decision_id=_identity("model_decision", body))


@dataclass(frozen=True)
class ModelConflict(Record):
    question_id: str
    code: str
    existing_values: tuple[str, ...]
    proposed_values: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class ModelClarificationHistoryEntry(Record):
    answer: ModelClarificationAnswer
    outcome: ModelResolutionOutcome
    previous_values: tuple[str, ...]
    accepted_values: tuple[str, ...]
    rejected_values: tuple[str, ...]
    resulting_decision_id: str | None
    readiness_before: bool
    readiness_after: bool
    unresolved_before: tuple[str, ...]
    unresolved_after: tuple[str, ...]
    conflicts_before: tuple[ModelConflict, ...]
    conflicts_after: tuple[ModelConflict, ...]


def _attempt_identity(answer):
    body = answer.canonical_dict()
    body.pop("target_finalization_id")
    return _identity("model_attempt", body)


def _authority_conflict(answer, handoff):
    """Recognize explicit authority changes; bounded claims provide the backstop.

    This is not a general natural-language consistency evaluator. Unsupported
    normalized choices cannot resolve a question even when prose is ambiguous.
    """
    architecture = handoff.frozen_approved_architecture.package.original_architecture
    authority = unicodedata.normalize("NFKC", handoff.frozen_approved_architecture.canonical_json()).casefold()
    text = unicodedata.normalize("NFKC", answer.user_answer).casefold()
    patterns = (
        ("github", r"\b(?:remove|drop|disable|exclude|no)\s+(?:the\s+)?(?:github|repository\s*connection)\b"),
        ("asset", r"\bassets?\s+(?:(?:must|are)\s+)?(?:never|not)\s+(?:be\s+)?persisted\b|\b(?:no|remove|disable)\s+(?:asset\s+)?deletion\s+(?:state|controls)\b"),
        ("build", r"\bno\s+build\s+state\b|\bbuild\s+state\s+(?:is\s+)?(?:never|not)\s+(?:stored|tracked)\b|\bremove\s+build\s+management\b"),
    )
    for fragment, pattern in patterns:
        if fragment in authority and re.search(pattern, text):
            return ModelConflict(answer.target_question_id, "frozen_architecture_conflict", (architecture.architecture_id,),
                                 answer.normalized_values, "The answer removes required frozen architecture state or policy.")
    for component in architecture.components:
        for label in (component.name, *component.owned_capabilities):
            if re.search(r"\b(?:remove|drop|disable|exclude|without|no)\s+(?:the\s+)?" + re.escape(_norm(label)) + r"\b", text):
                return ModelConflict(answer.target_question_id, "frozen_architecture_conflict", (component.component_id,),
                                     answer.normalized_values, "A model answer cannot remove frozen architecture ownership or capability.")
    for feature in ("billing", "payment", "subscription", "marketplace", "multiplayer", "social feed", "social graph", "chat system", "chat message", "monetization", "ai npc", "analytics", "achievement"):
        if feature not in authority and re.search(r"\b" + re.escape(feature) + r"s?\b", text.replace("_", " ")):
            return ModelConflict(answer.target_question_id, "unsupported_product_scope", (), answer.normalized_values,
                                 "A model answer cannot introduce an unsupported product capability.")
    return None


def _claims(question, answer, model):
    """Normalize only explicit, question-scoped logical choices.

    Choices compose with the original specification in the decision layer. No
    SQL, ORM, physical indexes, ownership transfer or runtime behavior is emitted.
    """
    values = answer.normalized_values
    area = question.area
    for value in values:
        tagged = re.fullmatch(r"([a-z_]+)\s*[:=]\s*(.+)", value, re.I)
        if tagged and tagged[1].casefold() in {a.value for a in ModelArea}:
            if tagged[1].casefold() != area.value:
                return (), "question_area_conflict"
    ids = set(question.entity_ids)
    if not ids:
        return (), "unsupported_model_choice"
    normalized = tuple(_norm(v) for v in values)
    if area is ModelArea.IDENTITY:
        valid = len(values) == 1 and values[0] in {"uuid", "string", "integer", "external_reference"}
        # Already approved identities cannot be overridden by a second question.
        for entity in model.entities:
            if entity.entity_id in ids:
                for field in entity.fields:
                    if field.field_id in entity.identity_field_ids and field.evidence.question_id is None:
                        if values != (field.logical_type.value,):
                            return (), "frozen_architecture_conflict"
    elif area is ModelArea.PRINCIPAL_REFERENCE:
        valid = values == ("external_principal_id",)
    elif area is ModelArea.EXTERNAL_REFERENCE:
        valid = len(values) == 2 and len(set(values) & {"external_id", "repository_id", "repository_node_id"}) == 1 and len(set(values) & {"string", "integer", "external_reference"}) == 1
    elif area in {ModelArea.LIFECYCLE, ModelArea.RETENTION}:
        # State labels are explicit user choices, never built-in defaults.
        valid = 2 <= len(values) <= 64 and all(re.fullmatch(r"[a-z][a-z0-9_]{0,63}", v) for v in values)
    elif area is ModelArea.UNIQUENESS:
        valid = values == ("identity_only",)
    elif area is ModelArea.LOOKUP:
        valid = values == ("identity",)
    elif area is ModelArea.FIELD:
        # Outcome questions authorize references on an existing record, not new
        # persistence for a service with no frozen storage assignment.
        targets = ids & set(values)
        valid = len(values) == 2 and "outcome_reference" in values and len(targets) == 1 and "outcomes" in question.question.casefold()
        if valid:
            return (ModelClaim(area.value, next(iter(targets)), None, ("outcome_reference", "external_reference")),), None
    elif area is ModelArea.RELATIONSHIP:
        if values == ("independent",):
            return tuple(ModelClaim(area.value, eid, None, values) for eid in sorted(ids)), None
        claims, endpoints = [], set()
        for value in values:
            try:
                payload = _parse(value)
                _exact(payload, ("source_entity_id", "target_entity_id", "source_cardinality", "target_cardinality", "ownership", "deletion_behavior"))
            except ValueError:
                return (), "unsupported_model_choice"
            if any(type(v) is not str for v in payload.values()) or value != _json(payload).strip():
                return (), "unsupported_model_choice"
            source, target = payload["source_entity_id"], payload["target_entity_id"]
            if source not in ids or target not in ids or (source, target) in endpoints:
                return (), "question_scope_conflict"
            if (payload["source_cardinality"] not in {"one", "zero_or_one", "many"}
                    or payload["target_cardinality"] not in {"one", "zero_or_one", "many"}
                    or payload["ownership"] not in {"independent", "source_owns_target", "target_owns_source"}
                    or payload["deletion_behavior"] not in {"retain", "restrict", "detach", "delete_dependent"}):
                return (), "unsupported_model_choice"
            endpoints.add((source, target))
            claims.append(ModelClaim(area.value, source, target, (payload["source_cardinality"], payload["target_cardinality"], payload["ownership"], payload["deletion_behavior"])))
        # Cover every affected record; an all-independent choice is explicit.
        if {eid for pair in endpoints for eid in pair} != ids:
            return (), "question_scope_conflict"
        return tuple(sorted(claims, key=lambda c: (c.entity_id, c.related_entity_id))), None
    else:
        valid = False
    if not valid or len(set(normalized)) != len(values):
        return (), "unsupported_model_choice"
    return tuple(ModelClaim(area.value, eid, None, values) for eid in sorted(ids)), None


def _decision_conflict(answer, claims, decisions):
    proposed = {(c.slot, c.entity_id, c.related_entity_id): c.values for c in claims}
    for decision in decisions:
        if decision.question_id == answer.target_question_id:
            continue
        for claim in decision.claims:
            key = (claim.slot, claim.entity_id, claim.related_entity_id)
            independent_conflict = any(c.slot == claim.slot == ModelArea.RELATIONSHIP.value
                and bool({c.entity_id, c.related_entity_id} & {claim.entity_id, claim.related_entity_id} - {None})
                and ((c.values == ("independent",)) != (claim.values == ("independent",))) for c in claims)
            if independent_conflict or (key in proposed and proposed[key] != claim.values):
                return ModelConflict(answer.target_question_id, "accepted_decision_conflict", decision.accepted_values,
                                     answer.normalized_values, "An accepted model decision already governs this logical choice and entity scope.")
    return None

@dataclass(frozen=True)
class ModelFinalization(Record):
    finalization_id: str
    original_model: DomainModelSpecification
    decisions: tuple[ModelDecision, ...]
    unresolved_questions: tuple[ModelQuestion, ...]
    conflicts: tuple[ModelConflict, ...]
    history: tuple[ModelClarificationHistoryEntry, ...]
    effective_ready_for_approval: bool
    schema: str = ARCADEV_MODEL_FINALIZATION_SCHEMA
    schema_version: int = ARCADEV_MODEL_FINALIZATION_SCHEMA_VERSION

    @staticmethod
    def _effective(model, unresolved, conflicts):
        structural = set(model.readiness.blocking_reasons) - {"blocking_model_questions"}
        return model.readiness.structurally_valid and not structural and not any(q.blocking for q in unresolved) and not conflicts

    @classmethod
    def _build(cls, model, decisions=(), unresolved=(), conflicts=(), history=()):
        decisions = tuple(sorted(decisions, key=lambda d: d.question_id))
        unresolved = tuple(sorted(unresolved, key=model_question_id))
        conflicts = tuple(sorted(conflicts, key=lambda c: (c.question_id, c.code)))
        history = tuple(history)
        if len(history) > MAX_MODEL_HISTORY:
            raise ValueError("Model history exceeds its safety limit.")
        result = cls("", model, decisions, unresolved, conflicts, history, cls._effective(model, unresolved, conflicts))
        body = result.canonical_dict()
        body.pop("finalization_id")
        result = replace(result, finalization_id=_identity("model_final", body))
        _safe(result.canonical_dict())
        return result

    @classmethod
    def start(cls, model, *, handoff):
        model = validate_domain_model_candidate(handoff, model)
        return cls._build(model, unresolved=model.open_model_questions)

    def resolve(self, answer, *, handoff):
        # Public resolutions cannot trust forged dataclass instances or stale history.
        handoff = model_handoff(handoff)
        state = type(self).from_dict(self.canonical_dict(), handoff=handoff)
        if type(answer) is not ModelClarificationAnswer:
            raise ValueError("Model resolution requires a validated answer.")
        return state._resolve(ModelClarificationAnswer.from_dict(answer.canonical_dict()), handoff=handoff)

    def _resolve(self, answer, *, handoff):
        """Apply to an already replay-validated state; used internally by replay."""
        if len(self.history) >= MAX_MODEL_HISTORY:
            raise ValueError("Model history exceeds its safety limit.")
        if answer.target_model_id != self.original_model.model_id or answer.target_finalization_id != self.finalization_id:
            raise ValueError("Model answer targets a forged, different, or stale finalization.")
        questions = {model_question_id(q): q for q in self.original_model.open_model_questions}
        if answer.target_question_id not in questions:
            raise ValueError("Model answer targets a nonexistent or forged question.")
        if any(_attempt_identity(entry.answer) == _attempt_identity(answer) for entry in self.history):
            raise ValueError("Duplicate or replayed model answer.")
        unresolved = {model_question_id(q): q for q in self.unresolved_questions}
        decisions = {d.question_id: d for d in self.decisions}
        previous = decisions.get(answer.target_question_id)
        if answer.action is ModelResolutionAction.ANSWER and answer.target_question_id not in unresolved:
            raise ValueError("Model question is already resolved; deliberate replacement is required.")
        if answer.action is ModelResolutionAction.REPLACE_DECISION and previous is None:
            raise ValueError("Replacement requires an existing model decision.")
        conflict = _authority_conflict(answer, handoff)
        claims, choice_error = _claims(questions[answer.target_question_id], answer, self.original_model)
        if conflict is None and choice_error is not None:
            conflict = ModelConflict(answer.target_question_id, choice_error, (), answer.normalized_values,
                                     "The answer is not a supported logical choice for this question and frozen entity scope.")
        if conflict is None and previous is not None and answer.expected_prior_values != previous.accepted_values:
            conflict = ModelConflict(answer.target_question_id, "accepted_decision_conflict", previous.accepted_values,
                                            answer.normalized_values, "Replacement requires exact currently accepted prior values.")
        if conflict is None:
            conflict = _decision_conflict(answer, claims, decisions.values())
        if conflict is None and previous is not None and answer.normalized_values == previous.accepted_values:
            raise ValueError("An unchanged model decision cannot be replayed as a replacement.")
        before_unresolved = tuple(sorted(unresolved))
        conflicts = tuple(c for c in self.conflicts if c.question_id != answer.target_question_id)
        if conflict is not None:
            conflicts += (conflict,)
            outcome = ModelResolutionOutcome.CONFLICT
            accepted, rejected = (), answer.normalized_values
            decision_id = previous.decision_id if previous else None
        else:
            decision = ModelDecision.create(questions[answer.target_question_id], answer, claims, self.original_model, previous)
            decisions[answer.target_question_id] = decision
            unresolved.pop(answer.target_question_id, None)
            outcome = ModelResolutionOutcome.ACCEPTED
            accepted, rejected, decision_id = answer.normalized_values, (), decision.decision_id
        after = self._build(self.original_model, decisions.values(), unresolved.values(), conflicts, self.history)
        event = ModelClarificationHistoryEntry(answer, outcome, previous.accepted_values if previous else (), accepted, rejected,
            decision_id, self.effective_ready_for_approval, after.effective_ready_for_approval, before_unresolved,
            tuple(sorted(unresolved)), self.conflicts, after.conflicts)
        return self._build(self.original_model, decisions.values(), unresolved.values(), conflicts, self.history + (event,))

    @classmethod
    def from_dict(cls, value, *, handoff):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_MODEL_FINALIZATION_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported model finalization schema/version.")
        if type(value["effective_ready_for_approval"]) is not bool or any(type(value[key]) is not list for key in ("decisions", "unresolved_questions", "conflicts", "history")):
            raise ValueError("Malformed model finalization.")
        if len(value["history"]) > MAX_MODEL_HISTORY:
            raise ValueError("Model history exceeds its safety limit.")
        state = cls.start(value["original_model"], handoff=handoff)
        for entry in value["history"]:
            _exact(entry, (f.name for f in fields(ModelClarificationHistoryEntry)))
            answer = ModelClarificationAnswer.from_dict(entry["answer"])
            state = state._resolve(answer, handoff=handoff)
            if _json(state.history[-1].canonical_dict()) != _json(entry):
                raise ValueError("Model history is forged or not replay-verifiable.")
        if _json(state.canonical_dict()) != _json(value):
            raise ValueError("Model finalization identity, decisions, conflicts, or readiness is forged.")
        return state

    @classmethod
    def from_json(cls, text, *, handoff):
        return cls.from_dict(_parse(text), handoff=handoff)


def resolve_model_clarification(finalization, candidate, *, handoff):
    if type(candidate) is ModelClarificationAnswer:
        answer = ModelClarificationAnswer.from_dict(candidate.canonical_dict())
    elif type(candidate) is str:
        answer = ModelClarificationAnswer.from_json(candidate)
    elif type(candidate) is dict:
        answer = ModelClarificationAnswer.from_dict(candidate)
    else:
        raise ValueError("Model clarification requires an inert answer object or JSON text.")
    if type(finalization) is not ModelFinalization:
        raise ValueError("Model clarification requires a finalization state.")
    return finalization.resolve(answer, handoff=handoff)
