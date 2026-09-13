"""Explicit immutable revision approval; original model and backend history survive."""
from dataclasses import dataclass, replace
from functools import lru_cache

from .architecture_specification import Record, _json, _parse, _text
from .model_approval import ApprovedDomainModel, ResolvedLogicalModel
from .model_amendment_request import ModelAmendmentRequest, checked, exact_result, identified, inert, parent_model
from .model_amendment_finalization import ModelAmendmentFinalization, ModelAmendmentDecision
from .plan_approval import ApprovalDecision

ARCADEV_APPROVED_DOMAIN_MODEL_REVISION_SCHEMA = "arcadev.approved_domain_model_revision"
ARCADEV_APPROVED_DOMAIN_MODEL_REVISION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RevisedLogicalModel(ResolvedLogicalModel):
    """Parent model IDs remain source handles; revised_model_id identifies this view."""
    revised_model_id: str
    parent_approval_id: str
    amendment_finalization_id: str
    amendment_decisions: tuple[ModelAmendmentDecision, ...]


def _revised(finalization):
    parent = finalization.request.parent
    original = parent.package.resolved_model
    entities = []
    domains = list(original.value_domains)
    for entity in original.entities:
        amendments = [d for d in finalization.decisions if d.answer.entity_id == entity.entity_id]
        fields = entity.approved_fields + tuple(d.field for d in amendments)
        identities = entity.identity_field_ids + tuple(d.field.field_id for d in amendments if d.identity_binding)
        lifecycles = entity.lifecycle_domain_ids + tuple(d.value_domain.domain_id for d in amendments if d.lifecycle_binding)
        domains.extend(d.value_domain for d in amendments if d.value_domain is not None)
        entities.append(replace(entity, approved_fields=tuple(sorted(fields, key=lambda f: f.field_id)),
            identity_field_ids=tuple(sorted(identities)), lifecycle_domain_ids=tuple(sorted(lifecycles))))
    result = RevisedLogicalModel(original.model_id, original.model_finalization_id,
        tuple(entities), tuple(sorted(domains, key=lambda d: d.domain_id)), original.relationships,
        original.constraints, original.access_requirements, "", parent.approval_id,
        finalization.finalization_id, finalization.decisions)
    return identified(result, "revised_model_id", "revised_logical_model")


@dataclass(frozen=True)
class ModelRevisionConsistencyEvaluation(Record):
    consistent: bool
    blocking_reasons: tuple[str, ...]


def _consistency(finalization, revised):
    reasons = []
    if not finalization.effective_ready_for_approval or finalization.unresolved_question_ids:
        reasons.append("unresolved_amendment_questions")
    if finalization.conflicts:
        reasons.append("amendment_conflicts")
    if not finalization.decisions:
        reasons.append("no_materialized_amendments")
    domains = {d.domain_id: d for d in revised.value_domains}
    field_ids = [f.field_id for e in revised.entities for f in e.approved_fields]
    if len(set(field_ids)) != len(field_ids):
        reasons.append("duplicate_revised_field_ids")
    for entity in revised.entities:
        fields = {f.field_id: f for f in entity.approved_fields}
        if not entity.identity_field_ids or not set(entity.identity_field_ids) <= fields.keys():
            reasons.append("missing_revised_identity_binding")
        if not set(entity.lifecycle_domain_ids) <= domains.keys() or any(
            f.value_domain_id is not None and f.value_domain_id not in domains for f in fields.values()
        ):
            reasons.append("missing_revised_value_domain_binding")
    return ModelRevisionConsistencyEvaluation(not reasons, tuple(sorted(set(reasons))))


@dataclass(frozen=True)
class FrozenModelRevisionPackage(Record):
    parent: ApprovedDomainModel
    amendment_request: ModelAmendmentRequest
    amendment_finalization: ModelAmendmentFinalization
    revised_model: RevisedLogicalModel
    consistency: ModelRevisionConsistencyEvaluation

    @classmethod
    def create(cls, *, parent, request, finalization):
        parent = parent_model(parent)
        if type(request) is not ModelAmendmentRequest or type(finalization) is not ModelAmendmentFinalization:
            raise ValueError("Revision requires complete certified amendment objects.")
        request = ModelAmendmentRequest.from_json(request.canonical_json(), parent=parent)
        finalization = ModelAmendmentFinalization.from_json(finalization.canonical_json(), parent=parent, request=request)
        revised = _revised(finalization)
        return cls(parent, request, finalization, revised, _consistency(finalization, revised))

    @classmethod
    def from_dict(cls, value):
        checked(value, cls)
        return _package(_json(value))


@lru_cache(maxsize=8)
def _package(text):
    value = _parse(text)
    checked(value, FrozenModelRevisionPackage)
    request = ModelAmendmentRequest.from_dict(value["amendment_request"])
    if request.parent.canonical_json() != _json(value["parent"]):
        raise ValueError("Revision package contains a stale or different parent.")
    finalization = ModelAmendmentFinalization.from_dict(value["amendment_finalization"], parent=request.parent, request=request)
    revised = _revised(finalization)
    result = FrozenModelRevisionPackage(request.parent, request, finalization, revised, _consistency(finalization, revised))
    return exact_result(result, value)


@dataclass(frozen=True)
class ApprovedDomainModelRevision(Record):
    revision_id: str
    parent_approval_id: str
    source_project_id: str
    package: FrozenModelRevisionPackage
    effective_ready_for_approval: bool
    approval_eligible: bool
    decision: ApprovalDecision
    approval_statement: str
    approved: bool
    schema: str = ARCADEV_APPROVED_DOMAIN_MODEL_REVISION_SCHEMA
    schema_version: int = 1

    @classmethod
    def create(cls, *, parent, request, finalization, decision, approval_statement):
        package = FrozenModelRevisionPackage.create(parent=parent, request=request, finalization=finalization)
        return cls._build(package, decision, approval_statement)

    @classmethod
    def _build(cls, package, decision, statement):
        decision = ApprovalDecision(decision)
        statement = _text(statement, "Explicit revision approval statement", 20_000, preserve=True)
        inert(statement)
        ready = package.amendment_finalization.effective_ready_for_approval
        eligible = ready and package.consistency.consistent
        if decision is ApprovalDecision.APPROVED and not eligible:
            raise ValueError("Revision approval requires complete, replay-valid, consistent materialization.")
        result = cls("", package.parent.approval_id, package.parent.source_project_id, package,
            ready, eligible, decision, statement, decision is ApprovalDecision.APPROVED and eligible)
        return identified(result, "revision_id", "approved_domain_model_revision")

    @classmethod
    def from_dict(cls, value, *, parent=None):
        checked(value, cls, ARCADEV_APPROVED_DOMAIN_MODEL_REVISION_SCHEMA)
        package = FrozenModelRevisionPackage.from_dict(value["package"])
        if parent is not None and parent_model(parent).canonical_json() != package.parent.canonical_json():
            raise ValueError("Revision is stale against supplied parent approval.")
        return exact_result(cls._build(package, value["decision"], value["approval_statement"]), value)

    @classmethod
    def from_json(cls, text, *, parent=None):
        return cls.from_dict(_parse(text), parent=parent)


def validate_approved_domain_model_revision(candidate, *, parent=None, request=None, finalization=None):
    raw = candidate.canonical_dict() if type(candidate) is ApprovedDomainModelRevision else candidate
    result = ApprovedDomainModelRevision.from_json(raw, parent=parent) if type(raw) is str else ApprovedDomainModelRevision.from_dict(raw, parent=parent)
    for supplied, frozen, cls in ((request, result.package.amendment_request, ModelAmendmentRequest),
            (finalization, result.package.amendment_finalization, ModelAmendmentFinalization)):
        if supplied is not None and (type(supplied) is not cls or supplied.canonical_json() != frozen.canonical_json()):
            raise ValueError("Revision is stale against supplied amendment authority.")
    return result


def evaluate_model_revision_consistency(*, parent, request, finalization):
    return FrozenModelRevisionPackage.create(parent=parent, request=request, finalization=finalization).consistency


def approve_domain_model_revision(*, parent, request, finalization, approval_statement):
    return ApprovedDomainModelRevision.create(parent=parent, request=request, finalization=finalization,
        decision=ApprovalDecision.APPROVED, approval_statement=approval_statement)


def reject_domain_model_revision(*, parent, request, finalization, approval_statement):
    return ApprovedDomainModelRevision.create(parent=parent, request=request, finalization=finalization,
        decision=ApprovalDecision.REJECTED, approval_statement=approval_statement)
