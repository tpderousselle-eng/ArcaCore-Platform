"""Versioned, inert requests for explicit logical materialization of frozen choices.

An accepted claim is necessary but never sufficient to approve a named field.
Historical model evidence and the original resolver are deliberately unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
from functools import lru_cache
import re
from typing import Protocol

from .architecture_specification import Record, _exact, _identity, _json, _parse, _text
from .domain_model_specification import (
    DataClassification, LogicalType, _model_safe, _norm,
)
from .model_approval import ApprovedDomainModel, ResolvedModelChoice
from .model_clarification import ModelClaim

ARCADEV_MODEL_AMENDMENT_REQUEST_SCHEMA = "arcadev.model_amendment_request"
ARCADEV_MODEL_AMENDMENT_REQUEST_SCHEMA_VERSION = 1


class ModelAmendmentArea(str, Enum):
    NAMED_FIELD = "named_field"
    IDENTITY_BINDING = "identity_binding"
    LIFECYCLE_FIELD = "lifecycle_field"
    PRINCIPAL_REFERENCE_FIELD = "principal_reference_field"
    EXTERNAL_REFERENCE_FIELD = "external_reference_field"
    OUTCOME_REFERENCE_FIELD = "outcome_reference_field"
    VALUE_DOMAIN_BINDING = "value_domain_binding"


def inert(value):
    """Additional amendment input boundary; never interpret text as executable data."""
    _model_safe(value)
    def visit(item):
        if type(item) is str and re.search(
            r"(?i)(?:[a-z]:[\\/]|\\\\|(?:^|\s)/[\w.]|\.\.[\\/]|https?://|"
            r"\b(?:select\s+.+\s+from|create\s+table|drop\s+table|alter\s+table|"
            r"import\s+\w+|exec\s*\(|eval\s*\(|subprocess|powershell|cmd\.exe)\b|[`;]|\$\()", item
        ):
            raise ValueError("Amendments cannot contain paths, SQL, code or execution metadata.")
        if type(item) is dict:
            for child in item.values():
                visit(child)
        elif type(item) is list:
            for child in item:
                visit(child)
    visit(value)


def checked(value, cls, schema=None):
    _model_safe(value)
    _exact(value, (f.name for f in fields(cls)))
    if schema is not None and (value["schema"] != schema or
            type(value["schema_version"]) is not int or value["schema_version"] != 1):
        raise ValueError("Unsupported amendment schema/version.")


def identified(record, key, kind):
    body = record.canonical_dict()
    body.pop(key)
    result = replace(record, **{key: _identity(kind, body)})
    _model_safe(result.canonical_dict())
    return result


def exact_result(result, value):
    if result.canonical_json() != _json(value):
        raise ValueError("Forged or stale amendment content, identity or history.")
    return result


@lru_cache(maxsize=8)
def _parent(text):
    result = ApprovedDomainModel.from_json(text)
    if not result.approved:
        raise ValueError("Amendments require an approved parent model.")
    return result


def parent_model(parent):
    if type(parent) is not ApprovedDomainModel:
        raise ValueError("Expected complete ApprovedDomainModel authority.")
    return _parent(parent.canonical_json())


@dataclass(frozen=True)
class ModelAmendmentTarget(Record):
    entity_id: str
    area: ModelAmendmentArea
    materialization_areas: tuple[ModelAmendmentArea, ...]
    source_choice: ResolvedModelChoice
    architecture_source_ids: tuple[str, ...]
    proposal_ids: tuple[str, ...]


@dataclass(frozen=True)
class ModelAmendmentQuestion(Record):
    question_id: str
    target: ModelAmendmentTarget
    question: str
    blocking: bool = True


@dataclass(frozen=True)
class ModelAmendmentFieldProposal(Record):
    """Complete suggestion or declaration. No defaults for omitted semantics."""
    entity_id: str
    name: str
    logical_type: LogicalType
    required: bool
    collection: bool
    mutable: bool
    unique: bool
    classification: DataClassification
    value_domain_name: str | None
    value_domain_values: tuple[str, ...]
    default_json: str | None
    source_decision_id: str
    source_claim: ModelClaim

    @classmethod
    def from_dict(cls, value):
        checked(value, cls)
        inert(value)
        args = dict(value)
        for key in ("entity_id", "source_decision_id"):
            args[key] = _text(args[key], maximum=240)
        for key in ("name", "value_domain_name"):
            if args[key] is not None:
                if type(args[key]) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", args[key]):
                    raise ValueError("Explicit logical names must be bounded identifiers.")
        if args["name"] is None:
            raise ValueError("A field name is required.")
        if re.search(r"(?i)password|passwd|credential|token|secret|private[_ -]?key|api[_ -]?key", args["name"]):
            raise ValueError("Credential storage remains outside logical amendment authority.")
        args["logical_type"] = LogicalType(args["logical_type"])
        args["classification"] = DataClassification(args["classification"])
        for key in ("required", "collection", "mutable", "unique"):
            if type(args[key]) is not bool:
                raise ValueError("Complete field declarations require explicit booleans.")
        values = args["value_domain_values"]
        if type(values) is not list or any(type(v) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", v) for v in values):
            raise ValueError("Invalid explicit value domain.")
        if len({_norm(v) for v in values}) != len(values):
            raise ValueError("Duplicate domain values.")
        args["value_domain_values"] = tuple(sorted(values))
        if (args["logical_type"] is LogicalType.ENUM) != bool(values):
            raise ValueError("Only ENUM fields require a complete domain.")
        if bool(values) != (args["value_domain_name"] is not None):
            raise ValueError("Domain name and values must be supplied together.")
        # This first bounded lifecycle has no source authority for defaults.
        if args["default_json"] is not None:
            raise ValueError("Default semantics are not authorized by this amendment lifecycle.")
        claim = args["source_claim"]
        _exact(claim, (f.name for f in fields(ModelClaim)))
        if type(claim["values"]) is not list or any(type(v) is not str for v in claim["values"]):
            raise ValueError("Malformed source claim.")
        args["source_claim"] = ModelClaim(claim["slot"], claim["entity_id"], claim["related_entity_id"], tuple(claim["values"]))
        return cls(**args)


_AREAS = {
    "identity": ModelAmendmentArea.IDENTITY_BINDING,
    "lifecycle": ModelAmendmentArea.LIFECYCLE_FIELD,
    "principal_reference": ModelAmendmentArea.PRINCIPAL_REFERENCE_FIELD,
    "external_reference": ModelAmendmentArea.EXTERNAL_REFERENCE_FIELD,
    "field": ModelAmendmentArea.OUTCOME_REFERENCE_FIELD,
}


def _questions(parent):
    result = []
    model = parent.package.resolved_model
    decisions = {d.decision_id: d for d in parent.package.model_finalization.decisions}
    for entity in model.entities:
        for choice in entity.choices:
            area = _AREAS.get(choice.claim.slot)
            if area is None:
                continue
            if choice.claim.slot == "field" and choice.claim.values != ("outcome_reference", "external_reference"):
                continue
            if area is ModelAmendmentArea.IDENTITY_BINDING and entity.identity_field_ids:
                continue
            if area is ModelAmendmentArea.LIFECYCLE_FIELD and any(
                f.value_domain_id in entity.lifecycle_domain_ids for f in entity.approved_fields
            ):
                continue
            decision = decisions[choice.decision_id]
            # Existing explicit fields are already materialized if their exact
            # source and logical semantic name match this accepted choice.
            if area not in {ModelAmendmentArea.IDENTITY_BINDING, ModelAmendmentArea.LIFECYCLE_FIELD} and any(
                f.name in choice.claim.values and set(f.evidence.source_requirements) == set(decision.architecture_source_requirements)
                for f in entity.approved_fields
            ):
                continue
            original = next(e for e in parent.package.original_model.entities if e.entity_id == entity.entity_id)
            areas = (ModelAmendmentArea.NAMED_FIELD, area)
            if area is ModelAmendmentArea.LIFECYCLE_FIELD:
                areas += (ModelAmendmentArea.VALUE_DOMAIN_BINDING,)
            target = ModelAmendmentTarget(entity.entity_id, area, areas, choice,
                decision.architecture_source_requirements,
                tuple(sorted(f.field_id for f in original.fields if f.evidence.question_id == choice.question_id)))
            question = ModelAmendmentQuestion("", target,
                "Explicitly declare the complete named logical field for " + area.value +
                " on " + entity.name + ". Accepted logical values: " + ", ".join(choice.claim.values) +
                ". No field name or declaration is approved by this question.")
            result.append(identified(question, "question_id", "model_amendment_question"))
    return tuple(sorted(result, key=lambda q: q.question_id))


def validate_proposal(proposal, question):
    if type(proposal) is ModelAmendmentFieldProposal:
        proposal = proposal.canonical_dict()
    result = ModelAmendmentFieldProposal.from_dict(proposal)
    target = question.target
    if (result.entity_id != target.entity_id or result.source_decision_id != target.source_choice.decision_id or
            result.source_claim != target.source_choice.claim):
        raise ValueError("Field escapes question entity or exact decision/claim authority.")
    claim = target.source_choice.claim
    if target.area is ModelAmendmentArea.IDENTITY_BINDING:
        if (claim.values != (result.logical_type.value,) or not result.required or result.collection or
                result.mutable or not result.unique or result.value_domain_name is not None):
            raise ValueError("Identity requires accepted type, required scalar immutable unique field.")
        if result.logical_type is LogicalType.EXTERNAL_REFERENCE and result.classification is not DataClassification.EXTERNAL_IDENTIFIER:
            raise ValueError("External identity classification contradiction.")
    else:
        if result.unique:
            raise ValueError("New non-identity uniqueness has no accepted authority.")
        if target.area is ModelAmendmentArea.LIFECYCLE_FIELD:
            if result.logical_type is not LogicalType.ENUM or result.value_domain_values != tuple(sorted(claim.values)) or result.collection:
                raise ValueError("Lifecycle values must match the accepted claim exactly.")
            if result.classification is DataClassification.EXTERNAL_IDENTIFIER:
                raise ValueError("Lifecycle state is not an external identifier.")
        else:
            if result.collection or result.classification is not DataClassification.EXTERNAL_IDENTIFIER:
                raise ValueError("References must be scalar external identifiers, never credentials.")
            if target.area is ModelAmendmentArea.PRINCIPAL_REFERENCE_FIELD:
                valid = claim.values == ("external_principal_id",) and result.logical_type in {LogicalType.STRING, LogicalType.EXTERNAL_REFERENCE}
            else:
                valid = result.logical_type.value in claim.values
            if not valid:
                raise ValueError("Reference type contradicts the accepted logical claim.")
    return result


@dataclass(frozen=True)
class ModelAmendmentCandidate(Record):
    question_id: str
    field: ModelAmendmentFieldProposal


class ModelAmendmentCandidateAdapter(Protocol):
    """Trusted local adapter returns untrusted data; no provider metadata is retained."""
    def create_candidate(self, request: ModelAmendmentRequest) -> dict | str: ...


@dataclass(frozen=True)
class ModelAmendmentRequest(Record):
    request_id: str
    parent: ApprovedDomainModel
    parent_model_id: str
    parent_model_finalization_id: str
    source_project_id: str
    questions: tuple[ModelAmendmentQuestion, ...]
    candidates: tuple[ModelAmendmentCandidate, ...]
    schema: str = "arcadev.model_amendment_request"
    schema_version: int = 1

    @classmethod
    def create(cls, parent, *, candidates=()):
        parent = parent_model(parent)
        questions = _questions(parent)
        catalog = {q.question_id: q for q in questions}
        if type(candidates) not in (tuple, list) or len(candidates) > 256:
            raise ValueError("Candidates must be a bounded collection.")
        validated = []
        for candidate in candidates:
            raw = candidate.canonical_dict() if type(candidate) is ModelAmendmentCandidate else candidate
            inert(raw)
            _exact(raw, ("question_id", "field"))
            if type(raw["question_id"]) is not str or raw["question_id"] not in catalog:
                raise ValueError("Candidate targets a nonexistent amendment question.")
            validated.append(ModelAmendmentCandidate(raw["question_id"], validate_proposal(raw["field"], catalog[raw["question_id"]])))
        if len({c.question_id for c in validated}) != len(validated):
            raise ValueError("Duplicate candidate question.")
        result = cls("", parent, parent.model_id, parent.model_finalization_id, parent.source_project_id,
            questions, tuple(sorted(validated, key=lambda c: c.question_id)))
        return identified(result, "request_id", "model_amendment_request")

    @classmethod
    def from_dict(cls, value, *, parent=None):
        checked(value, cls, "arcadev.model_amendment_request")
        frozen = _parent(_json(value["parent"]))
        if parent is not None and parent_model(parent).canonical_json() != frozen.canonical_json():
            raise ValueError("Stale parent approval content.")
        return exact_result(cls.create(frozen, candidates=value["candidates"]), value)

    @classmethod
    def from_json(cls, text, *, parent=None):
        return cls.from_dict(_parse(text), parent=parent)


def suggest_model_amendment(parent, adapter):
    request = ModelAmendmentRequest.create(parent)
    raw = adapter.create_candidate(request)
    raw = _parse(raw) if type(raw) is str else raw
    inert(raw)
    _exact(raw, ("candidates",))
    return ModelAmendmentRequest.create(parent, candidates=raw["candidates"])


def model_amendment_review(request):
    """Deterministic read-only packet. No answer values or approvals are generated."""
    request = ModelAmendmentRequest.from_json(request.canonical_json())
    return {"schema": "arcadev.model_amendment_review", "schema_version": 1,
        "request_id": request.request_id, "parent_approval_id": request.parent.approval_id,
        "status": "UNRESOLVED_REQUIRES_EXPLICIT_ANSWERS" if request.questions else "NO_MATERIALIZATION_QUESTIONS",
        "parent_approval_statement": request.parent.approval_statement,
        "entities": [{"entity_id": e.entity_id, "name": e.name,
            "accepted_logical_choices": [c.canonical_dict() for c in e.choices],
            "missing_identity_binding": not bool(e.identity_field_ids),
            "missing_named_fields": [q.target.area.value for q in request.questions if q.target.entity_id == e.entity_id],
            "questions": [q.canonical_dict() for q in request.questions if q.target.entity_id == e.entity_id],
            "candidate_suggestions_NON_AUTHORITATIVE": [c.canonical_dict() for c in request.candidates if c.field.entity_id == e.entity_id]}
            for e in request.parent.package.resolved_model.entities]}
