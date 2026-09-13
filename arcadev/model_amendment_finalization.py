"""Append-only explicit materialization. Invalid attempts fail atomically.

No replacement action is supported in version 1. Historical accepted answers
are replayed from the initial request before accepting any serialized state.
"""
from dataclasses import dataclass
from functools import lru_cache

from .architecture_specification import Record, _identity, _json, _parse
from .domain_model_specification import ModelFact, ModelField, ModelValueDomain, model_element_id, _norm
from .model_approval import ResolvedModelChoice
from .model_amendment_request import (
    ModelAmendmentRequest, ModelAmendmentArea, checked, exact_result,
    identified, validate_proposal, parent_model,
)
from .model_amendment_answer import ModelAmendmentAnswer

ARCADEV_MODEL_AMENDMENT_FINALIZATION_SCHEMA = "arcadev.model_amendment_finalization"
ARCADEV_MODEL_AMENDMENT_FINALIZATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ModelAmendmentFieldEvidence(ModelFact):
    """Revision-only evidence. Old ModelFact loaders reject this new provenance.

The inherited field semantics are reusable without pretending amendment consent
was present in the old architecture/model finalization.
"""
    provenance: str
    amendment_decision_id: str = ""
    source_choice: ResolvedModelChoice | None = None


@dataclass(frozen=True)
class ModelAmendmentDecision(Record):
    decision_id: str
    answer: ModelAmendmentAnswer
    source_choice: ResolvedModelChoice
    field: ModelField
    value_domain: ModelValueDomain | None
    identity_binding: bool
    lifecycle_binding: bool


@dataclass(frozen=True)
class ModelAmendmentHistoryEntry(Record):
    previous_finalization_id: str
    answer: ModelAmendmentAnswer
    decision_id: str
    outcome: str = "accepted"


def _materialize(answer, question):
    declaration = validate_proposal(answer.field, question)
    target = question.target
    # This ID binds the entire declaration and its exact question authority.
    # The derived field/evidence graph is reconstructed rather than trusted.
    decision_id = _identity("model_amendment_decision", {
        "answer": answer.canonical_dict(), "question": question.canonical_dict()})
    evidence = ModelAmendmentFieldEvidence(answer.declaration_quote, target.architecture_source_ids,
        "explicit_user", None, question.question_id, decision_id, target.source_choice)
    fid = model_element_id("field", name=declaration.name,
        source_requirements=target.architecture_source_ids, scope=(target.entity_id,))
    domain = None
    if declaration.value_domain_name is not None:
        domain = ModelValueDomain(model_element_id("domain", name=declaration.value_domain_name,
            source_requirements=target.architecture_source_ids), declaration.value_domain_name,
            declaration.value_domain_values, evidence)
    field = ModelField(fid, declaration.name, declaration.logical_type, declaration.required,
        declaration.collection, declaration.mutable, declaration.unique, declaration.classification,
        evidence, domain.domain_id if domain else None, declaration.default_json)
    return ModelAmendmentDecision(decision_id, answer, target.source_choice, field, domain,
        target.area is ModelAmendmentArea.IDENTITY_BINDING, target.area is ModelAmendmentArea.LIFECYCLE_FIELD)


def _no_collisions(request, decisions, new):
    parent = request.parent.package.resolved_model
    entity_id = new.answer.entity_id
    existing = [(e.entity_id, f) for e in parent.entities for f in e.approved_fields]
    existing += [(d.answer.entity_id, d.field) for d in decisions]
    for eid, field in existing:
        if field.field_id == new.field.field_id or (eid == entity_id and _norm(field.name) == _norm(new.field.name)):
            raise ValueError("Duplicate field identity or normalized field name in entity.")
    domains = list(parent.value_domains) + [d.value_domain for d in decisions if d.value_domain is not None]
    if new.value_domain and any(d.domain_id == new.value_domain.domain_id or _norm(d.name) == _norm(new.value_domain.name) for d in domains):
        raise ValueError("Duplicate value-domain identity or normalized name.")


@dataclass(frozen=True)
class ModelAmendmentFinalization(Record):
    finalization_id: str
    request: ModelAmendmentRequest
    decisions: tuple[ModelAmendmentDecision, ...]
    history: tuple[ModelAmendmentHistoryEntry, ...]
    unresolved_question_ids: tuple[str, ...]
    conflicts: tuple[str, ...]
    effective_ready_for_approval: bool
    schema: str = ARCADEV_MODEL_AMENDMENT_FINALIZATION_SCHEMA
    schema_version: int = 1

    @classmethod
    def _build(cls, request, decisions=(), history=()):
        resolved = {d.answer.question_id for d in decisions}
        unresolved = tuple(q.question_id for q in request.questions if q.question_id not in resolved)
        result = cls("", request, tuple(sorted(decisions, key=lambda d: d.decision_id)), tuple(history),
            unresolved, (), not unresolved)
        return identified(result, "finalization_id", "model_amendment_finalization")

    @classmethod
    def start(cls, request, *, parent=None):
        if type(request) is not ModelAmendmentRequest:
            raise ValueError("Expected an amendment request.")
        return cls._build(ModelAmendmentRequest.from_json(request.canonical_json(), parent=parent))

    def resolve(self, answer, *, parent):
        state = self.from_json(self.canonical_json(), parent=parent)
        raw = answer.canonical_dict() if type(answer) is ModelAmendmentAnswer else answer
        answer = ModelAmendmentAnswer.from_json(raw) if type(raw) is str else ModelAmendmentAnswer.from_dict(raw)
        return state._resolve(answer)

    def _resolve(self, answer):
        request = self.request
        if (answer.request_id != request.request_id or answer.parent_approval_id != request.parent.approval_id or
                answer.target_finalization_id != self.finalization_id):
            raise ValueError("Stale amendment request, parent or finalization target.")
        question = next((q for q in request.questions if q.question_id == answer.question_id), None)
        if question is None or question.question_id not in self.unresolved_question_ids:
            raise ValueError("Nonexistent question, duplicate resolution or replay.")
        if len(self.history) >= 256:
            raise ValueError("Amendment history exceeds its bound.")
        decision = _materialize(answer, question)
        _no_collisions(request, self.decisions, decision)
        event = ModelAmendmentHistoryEntry(self.finalization_id, answer, decision.decision_id)
        return self._build(request, self.decisions + (decision,), self.history + (event,))

    @classmethod
    def from_dict(cls, value, *, parent=None, request=None):
        checked(value, cls, ARCADEV_MODEL_AMENDMENT_FINALIZATION_SCHEMA)
        state = _replay(_json(value))
        if parent is not None and parent_model(parent).canonical_json() != state.request.parent.canonical_json():
            raise ValueError("Stale finalization parent content.")
        if request is not None and (type(request) is not ModelAmendmentRequest or
                ModelAmendmentRequest.from_json(request.canonical_json()).canonical_json() != state.request.canonical_json()):
            raise ValueError("Finalization belongs to a different request.")
        return state

    @classmethod
    def from_json(cls, text, *, parent=None, request=None):
        return cls.from_dict(_parse(text), parent=parent, request=request)


@lru_cache(maxsize=8)
def _replay(text):
    value = _parse(text)
    checked(value, ModelAmendmentFinalization, ARCADEV_MODEL_AMENDMENT_FINALIZATION_SCHEMA)
    request = ModelAmendmentRequest.from_dict(value["request"])
    if type(value["history"]) is not list:
        raise ValueError("History must be an array.")
    state = ModelAmendmentFinalization._build(request)
    for event in value["history"]:
        checked(event, ModelAmendmentHistoryEntry)
        state = state._resolve(ModelAmendmentAnswer.from_dict(event["answer"]))
        exact_result(state.history[-1], event)
    return exact_result(state, value)
