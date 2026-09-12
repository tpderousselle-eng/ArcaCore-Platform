"""Deterministic final consistency and explicit approval of a frozen logical model.

Integrity, graph and frozen architecture authority checks reuse the certified specification and
finalization loaders. Replay validates decisions; it never changes source data.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
from functools import lru_cache

from .model_clarification import ModelFinalization, ModelClaim
from .architecture_specification import (
    Record, _exact, _identity, _json, _parse, _strings, _text,
)
from .domain_model_specification import (
    DomainModelSpecification, ModelField, ModelValueDomain, ModelRelationship,
    ModelConstraint, ModelAccessRequirement, DataClassification, _model_safe as _safe,
)
from .plan_approval import ApprovalDecision
from .architecture_models_handoff import ArchitectureModelsHandoff
from .project import ArcaDevProject, BuildStage, ProjectStatus

ARCADEV_APPROVED_DOMAIN_MODEL_SCHEMA = "arcadev.approved_domain_model"
ARCADEV_APPROVED_DOMAIN_MODEL_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ResolvedModelChoice(Record):
    """An accepted structured claim with exact decision provenance, never prose."""
    decision_id: str
    question_id: str
    claim: ModelClaim


@dataclass(frozen=True)
class ResolvedModelEntity(Record):
    entity_id: str
    name: str
    architecture_source_requirements: tuple[str, ...]
    owned_capabilities: tuple[str, ...]
    classification: DataClassification
    approved_fields: tuple[ModelField, ...]
    identity_field_ids: tuple[str, ...]
    lifecycle_domain_ids: tuple[str, ...]
    choices: tuple[ResolvedModelChoice, ...]


@dataclass(frozen=True)
class ResolvedLogicalModel(Record):
    """Certified original choices plus accepted claims, excluding mere proposals.

    Identity/reference/lifecycle/retention/relationship/uniqueness/lookup slots
    retain the bounded 4.3 ModelClaim semantics. Choices can define logical state
    without inventing a field name, a physical column, or an implementation.
    Original question-backed fields/domains/relationships/constraints/accesses
    are proposals, not defaults approved by resolving their question. They stay
    only in original_model. This view never parses user answers or evidence.
    """
    model_id: str
    model_finalization_id: str
    entities: tuple[ResolvedModelEntity, ...]
    value_domains: tuple[ModelValueDomain, ...]
    relationships: tuple[ModelRelationship, ...]
    constraints: tuple[ModelConstraint, ...]
    access_requirements: tuple[ModelAccessRequirement, ...]


def _resolved_model(finalization):
    model = finalization.original_model
    def approved(items):
        return tuple(item for item in items if item.evidence.question_id is None)
    entities = []
    for entity in model.entities:
        fixed = approved(entity.fields)
        choices = tuple(sorted((ResolvedModelChoice(d.decision_id, d.question_id, c)
            for d in finalization.decisions for c in d.claims if c.entity_id == entity.entity_id),
            key=lambda choice: choice.canonical_json()))
        entities.append(ResolvedModelEntity(entity.entity_id, entity.name,
            entity.responsibility.source_requirements, entity.owned_capabilities, entity.classification, fixed,
            tuple(fid for fid in entity.identity_field_ids if fid in {f.field_id for f in fixed}),
            tuple(did for did in entity.lifecycle_domain_ids if did in {d.domain_id for d in approved(model.value_domains)}), choices))
    return ResolvedLogicalModel(model.model_id, finalization.finalization_id,
        tuple(sorted(entities, key=lambda e: e.entity_id)), approved(model.value_domains),
        approved(model.relationships), approved(model.constraints), approved(model.access_requirements))


class ModelFindingSeverity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


@dataclass(frozen=True)
class ModelConsistencyFinding(Record):
    code: str
    message: str
    severity: ModelFindingSeverity
    fields: tuple[str, ...]

    @classmethod
    def create(cls, code, message, severity, fields):
        code = _text(code, maximum=240)
        if not code.replace("_", "").isalnum():
            raise ValueError("Invalid model finding code.")
        return cls(code, _text(message, maximum=2000), ModelFindingSeverity(severity), _strings(fields, required=True))

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if type(value["fields"]) is not list:
            raise ValueError("Model finding fields must be an array.")
        return cls.create(**value)


@dataclass(frozen=True)
class ModelConsistencyEvaluation(Record):
    consistent: bool
    blocking_findings: tuple[ModelConsistencyFinding, ...]
    warnings: tuple[ModelConsistencyFinding, ...]

    @classmethod
    def create(cls, findings=()):
        validated = []
        for finding in findings:
            if type(finding) is not ModelConsistencyFinding:
                raise ValueError("Expected model consistency findings.")
            validated.append(ModelConsistencyFinding.from_dict(finding.canonical_dict()))
        validated.sort(key=lambda f: (f.severity.value, f.code, f.fields))
        keys = [(f.severity, f.code, f.fields) for f in validated]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate model findings.")
        blockers = tuple(f for f in validated if f.severity is ModelFindingSeverity.BLOCKING)
        warnings = tuple(f for f in validated if f.severity is ModelFindingSeverity.WARNING)
        return cls(not blockers, blockers, warnings)

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if type(value["consistent"]) is not bool or any(type(value[k]) is not list for k in ("blocking_findings", "warnings")):
            raise ValueError("Malformed model consistency evaluation.")
        result = cls.create(ModelConsistencyFinding.from_dict(f) for f in value["blocking_findings"] + value["warnings"])
        if _json(result.canonical_dict()) != _json(value):
            raise ValueError("Forged model consistency evaluation.")
        return result


@lru_cache(maxsize=8)
def _certified_sources(handoff_json, model_json, finalization_json):
    # Like the certified model-handoff cache, keys contain complete content,
    # never asserted IDs. Only successful replay of immutable values is cached.
    handoff = ArchitectureModelsHandoff.from_json(handoff_json)
    model = DomainModelSpecification.from_json(model_json, handoff=handoff)
    finalization = ModelFinalization.from_json(finalization_json, handoff=handoff)
    if model.canonical_json() != finalization.original_model.canonical_json():
        raise ValueError("Model finalization belongs to another or stale model.")
    return handoff, model, finalization


def _validated_sources(handoff, model, finalization):
    if type(handoff) is not ArchitectureModelsHandoff or type(model) is not DomainModelSpecification or type(finalization) is not ModelFinalization:
        raise ValueError("Model approval requires certified upstream objects.")
    return _certified_sources(handoff.canonical_json(), model.canonical_json(), finalization.canonical_json())


def _relationship_semantics(source, target, values):
    """Compare the same logical edge independently of endpoint orientation."""
    if source <= target:
        return (source, target), values
    ownership = {"source_owns_target": "target_owns_source", "target_owns_source": "source_owns_target"}
    return (target, source), (values[1], values[0], ownership.get(values[2], values[2]), values[3])


def _evaluate(finalization):
    # Certified 4.1/4.2 validation checks graph/types, persistent capability and
    # owner coverage, exact upstream authority, credentials and supported scope.
    # 4.3 replay checks the bounded choices and complete decision/history chain.
    # Final checks below concern the combined logical authority only.
    findings = []
    for condition, code, message, field in (
        (any(q.blocking for q in finalization.unresolved_questions), "unresolved_model_blockers", "Blocking model questions remain unresolved.", "unresolved_questions"),
        (bool(finalization.conflicts), "active_model_conflicts", "Model conflicts remain active.", "conflicts"),
        (not finalization.effective_ready_for_approval, "model_not_effectively_ready", "Model is not effectively ready for approval.", "effective_ready_for_approval"),
    ):
        if condition:
            findings.append(ModelConsistencyFinding.create(code, message, ModelFindingSeverity.BLOCKING, (field,)))
    resolved = _resolved_model(finalization)
    domains = {d.domain_id: d for d in resolved.value_domains}
    accepted_edges = {}
    for entity in resolved.entities:
        field_ids = {f.field_id for f in entity.approved_fields}
        for field in entity.approved_fields:
            if field.value_domain_id is not None and field.value_domain_id not in domains:
                findings.append(ModelConsistencyFinding.create("unresolved_frozen_value_domain",
                    "A frozen field refers to a value domain that has only proposed authority.",
                    ModelFindingSeverity.BLOCKING, (entity.entity_id, field.field_id)))
        for item in (*resolved.constraints, *resolved.access_requirements):
            if item.entity_id == entity.entity_id and not set(item.field_ids) <= field_ids:
                findings.append(ModelConsistencyFinding.create("unresolved_frozen_field_reference",
                    "A frozen logical requirement refers to fields that have only proposed authority.",
                    ModelFindingSeverity.BLOCKING, (entity.entity_id, *item.field_ids)))
        if not entity.identity_field_ids and not any(c.claim.slot == "identity" for c in entity.choices):
            findings.append(ModelConsistencyFinding.create("missing_resolved_identity",
                "Entity has no accepted stable logical identity.", ModelFindingSeverity.BLOCKING, (entity.entity_id,)))
        for choice in entity.choices:
            claim = choice.claim
            if claim.slot == "relationship" and claim.related_entity_id is not None:
                endpoints, semantics = _relationship_semantics(claim.entity_id, claim.related_entity_id, claim.values)
                if endpoints in accepted_edges and accepted_edges[endpoints] != semantics:
                    findings.append(ModelConsistencyFinding.create("accepted_relationship_conflict",
                        "Accepted claims disagree about the same logical relationship.",
                        ModelFindingSeverity.BLOCKING, tuple(set(endpoints))))
                accepted_edges[endpoints] = semantics
            if claim.slot == "uniqueness" and claim.values == ("identity_only",):
                extra_unique = any(f.unique and f.field_id not in entity.identity_field_ids for f in entity.approved_fields)
                extra_unique |= any(c.entity_id == entity.entity_id and c.kind in {"unique", "composite_unique"}
                    and not set(c.field_ids) <= set(entity.identity_field_ids) for c in resolved.constraints)
                if extra_unique:
                    findings.append(ModelConsistencyFinding.create("frozen_uniqueness_conflict",
                        "Identity-only uniqueness contradicts frozen non-identity uniqueness.",
                        ModelFindingSeverity.BLOCKING, (entity.entity_id, choice.decision_id)))
            if claim.slot == "lifecycle" and any(set(domains[did].values) != set(claim.values) for did in entity.lifecycle_domain_ids):
                findings.append(ModelConsistencyFinding.create("frozen_lifecycle_conflict",
                    "Accepted lifecycle values contradict the frozen entity lifecycle domain.",
                    ModelFindingSeverity.BLOCKING, (entity.entity_id, choice.decision_id)))
            for relationship in resolved.relationships:
                if claim.slot != "relationship":
                    continue
                contradicted = (claim.values == ("independent",) and entity.entity_id in
                    {relationship.source_entity_id, relationship.target_entity_id})
                if claim.related_entity_id is not None:
                    endpoints, semantics = _relationship_semantics(claim.entity_id, claim.related_entity_id, claim.values)
                    frozen_endpoints, frozen_semantics = _relationship_semantics(relationship.source_entity_id, relationship.target_entity_id,
                        (relationship.source_cardinality, relationship.target_cardinality, relationship.ownership, relationship.deletion_behavior))
                    if endpoints == frozen_endpoints:
                        contradicted |= semantics != frozen_semantics
                if contradicted:
                    findings.append(ModelConsistencyFinding.create("frozen_relationship_conflict",
                        "Accepted relationship choice contradicts a frozen architecture relationship.",
                        ModelFindingSeverity.BLOCKING, (entity.entity_id, relationship.relationship_id, choice.decision_id)))
    findings.append(ModelConsistencyFinding.create(
            "implementation_compatibility_not_proven", "Explicit logical decisions preserve frozen architecture authority; backend compatibility requires later implementation and testing.",
            ModelFindingSeverity.WARNING, ("decisions",)))
    if any(not q.blocking for q in finalization.unresolved_questions):
        findings.append(ModelConsistencyFinding.create(
            "unresolved_advisory_questions", "Non-blocking model questions remain for review.",
            ModelFindingSeverity.WARNING, ("unresolved_questions",)))
    return ModelConsistencyEvaluation.create(set(findings))


def evaluate_model_consistency(handoff, model, finalization):
    _, _, finalization = _validated_sources(handoff, model, finalization)
    return _evaluate(finalization)


@dataclass(frozen=True)
class FrozenApprovedDomainModelPackage(Record):
    architecture_handoff: ArchitectureModelsHandoff
    original_model: DomainModelSpecification
    model_finalization: ModelFinalization
    consistency: ModelConsistencyEvaluation
    resolved_model: ResolvedLogicalModel

    def canonical_dict(self):
        return {f.name: getattr(self, f.name).canonical_dict() for f in fields(self)}

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        handoff, model, finalization = _certified_sources(_json(value["architecture_handoff"]),
            _json(value["original_model"]), _json(value["model_finalization"]))
        consistency = ModelConsistencyEvaluation.from_dict(value["consistency"])
        if consistency != _evaluate(finalization):
            raise ValueError("Frozen model consistency is forged.")
        resolved = _resolved_model(finalization)
        if _json(value["resolved_model"]) != resolved.canonical_json():
            raise ValueError("Frozen resolved logical model is forged.")
        return cls(handoff, model, finalization, consistency, resolved)


@dataclass(frozen=True)
class ApprovedDomainModel(Record):
    approval_id: str
    source_project_id: str
    architecture_handoff_id: str
    plan_handoff_id: str
    approved_architecture_id: str
    architecture_id: str
    architecture_finalization_id: str
    model_id: str
    model_finalization_id: str
    package: FrozenApprovedDomainModelPackage
    effective_ready_for_approval: bool
    approval_eligible: bool
    decision: ApprovalDecision
    approval_statement: str
    approved: bool
    schema: str = ARCADEV_APPROVED_DOMAIN_MODEL_SCHEMA
    schema_version: int = ARCADEV_APPROVED_DOMAIN_MODEL_SCHEMA_VERSION

    @classmethod
    def create(cls, *, handoff, model, finalization, decision, approval_statement, source_project=None):
        handoff, model, finalization = _validated_sources(handoff, model, finalization)
        package = FrozenApprovedDomainModelPackage(handoff, model, finalization, _evaluate(finalization), _resolved_model(finalization))
        return cls._build(package, decision, approval_statement, source_project)

    @classmethod
    def _build(cls, package, decision, approval_statement, source_project=None):
        """Construct only from a package validated in this call's public boundary."""
        handoff, model, finalization = package.architecture_handoff, package.original_model, package.model_finalization
        project = handoff.resulting_project
        if source_project is not None and (type(source_project) is not ArcaDevProject or _json(source_project.canonical_dict()) != _json(project.canonical_dict())):
            raise ValueError("Model approval source project is stale or forged.")
        statement = _text(approval_statement, "Model approval statement", 20_000)
        try:
            decision = ApprovalDecision(decision)
        except (TypeError, ValueError) as error:
            raise ValueError("Unsupported model approval decision.") from error
        consistency = package.consistency
        eligible = bool(project.project_status is ProjectStatus.IN_PROGRESS and project.current_build_stage is BuildStage.MODELS
                        and finalization.effective_ready_for_approval and consistency.consistent
                        and not any(q.blocking for q in finalization.unresolved_questions) and not finalization.conflicts)
        if decision is ApprovalDecision.APPROVED and not eligible:
            raise ValueError("Model cannot be approved while readiness or consistency blockers remain.")
        result = cls("", handoff.source_project_id, handoff.handoff_id, handoff.plan_handoff_id,
                     handoff.approved_architecture_id, handoff.architecture_id, handoff.architecture_finalization_id,
                     model.model_id, finalization.finalization_id,
                     package,
                     finalization.effective_ready_for_approval, eligible, decision, statement, decision is ApprovalDecision.APPROVED and eligible)
        body = result.canonical_dict()
        body.pop("approval_id")
        result = replace(result, approval_id=_identity("approved_domain_model", body))
        _safe(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_APPROVED_DOMAIN_MODEL_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported approved domain model schema/version.")
        package = FrozenApprovedDomainModelPackage.from_dict(value["package"])
        result = cls._build(package, value["decision"], value["approval_statement"])
        if _json(result.canonical_dict()) != _json(value):
            raise ValueError("Approved domain model identity, eligibility, decision or frozen package is forged.")
        return result

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


def validate_approved_domain_model(candidate, *, source_project=None, handoff=None, model=None, finalization=None):
    if type(candidate) is ApprovedDomainModel:
        candidate = candidate.canonical_dict()
    result = ApprovedDomainModel.from_json(candidate) if type(candidate) is str else ApprovedDomainModel.from_dict(candidate)
    for supplied, expected, kind in (
        (source_project, result.package.architecture_handoff.resulting_project, ArcaDevProject),
        (handoff, result.package.architecture_handoff, ArchitectureModelsHandoff),
        (model, result.package.original_model, DomainModelSpecification),
        (finalization, result.package.model_finalization, ModelFinalization),
    ):
        if supplied is not None and (type(supplied) is not kind or _json(supplied.canonical_dict()) != _json(expected.canonical_dict())):
            raise ValueError("Approved domain model is stale or mismatched against current upstream authority.")
    return result


def approve_domain_model(*, handoff, model, finalization, approval_statement, source_project=None):
    return ApprovedDomainModel.create(handoff=handoff, model=model, finalization=finalization,
        decision=ApprovalDecision.APPROVED, approval_statement=approval_statement, source_project=source_project)


def reject_domain_model(*, handoff, model, finalization, approval_statement, source_project=None):
    return ApprovedDomainModel.create(handoff=handoff, model=model, finalization=finalization,
        decision=ApprovalDecision.REJECTED, approval_statement=approval_statement, source_project=source_project)
