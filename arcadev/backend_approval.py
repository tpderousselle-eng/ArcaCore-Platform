"""Explicit immutable BACKEND approval, separate from generation capability."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
from functools import lru_cache

from .architecture_specification import Record, _exact, _identity, _json, _parse, _text
from .domain_model_specification import _model_safe as _safe
from .backend_specification import (
    BackendSpecification, BackendComponent, BackendDataBinding, BackendOperation,
    BackendPolicy, BackendQuestion,
)
from .backend_clarification import BackendFinalization, BackendClaim
from .models_backend_handoff import ModelsBackendHandoff
from .plan_approval import ApprovalDecision
from .project import ArcaDevProject, BuildStage, ProjectStatus

ARCADEV_APPROVED_BACKEND_SCHEMA = "arcadev.approved_backend"
ARCADEV_APPROVED_BACKEND_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ResolvedBackendChoice(Record):
    decision_id: str
    question_id: str
    claim: BackendClaim


@dataclass(frozen=True)
class ResolvedBackendAuthority(Record):
    """Frozen structure, accepted bounded choices and provisional questions.

    Choices retain their transaction/async/failure/idempotency/storage/technology
    slots and exact scopes. Prose is evidence only, never executable authority.
    The original specification retains every original proposal and question.
    """
    backend_id: str
    backend_finalization_id: str
    components: tuple[BackendComponent, ...]
    data_bindings: tuple[BackendDataBinding, ...]
    operations: tuple[BackendOperation, ...]
    policies: tuple[BackendPolicy, ...]
    accepted_choices: tuple[ResolvedBackendChoice, ...]
    unresolved_questions: tuple[BackendQuestion, ...]


def _resolved(finalization):
    backend = finalization.original_backend
    choices = tuple(sorted((ResolvedBackendChoice(d.decision_id, d.question_id, c)
        for d in finalization.decisions for c in d.claims), key=lambda c: c.canonical_json()))
    return ResolvedBackendAuthority(backend.backend_id, finalization.finalization_id,
        backend.components, backend.data_bindings, backend.operations, backend.policies,
        choices, finalization.unresolved_questions)


class BackendFindingSeverity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


@dataclass(frozen=True)
class BackendConsistencyFinding(Record):
    code: str
    message: str
    severity: BackendFindingSeverity
    fields: tuple[str, ...]


@dataclass(frozen=True)
class BackendConsistencyEvaluation(Record):
    consistent: bool
    blocking_findings: tuple[BackendConsistencyFinding, ...]
    warnings: tuple[BackendConsistencyFinding, ...]


@lru_cache(maxsize=8)
def _certified_sources(handoff_json, backend_json, finalization_json):
    # Full canonical content keys; successful replay only. IDs are not freshness.
    handoff = ModelsBackendHandoff.from_json(handoff_json)
    backend = BackendSpecification.from_json(backend_json, handoff=handoff)
    finalization = BackendFinalization.from_json(finalization_json, handoff=handoff)
    if backend.canonical_json() != finalization.original_backend.canonical_json():
        raise ValueError("Backend finalization belongs to another or stale specification.")
    return handoff, backend, finalization


def _validated_sources(handoff, backend, finalization):
    if type(handoff) is not ModelsBackendHandoff or type(backend) is not BackendSpecification or type(finalization) is not BackendFinalization:
        raise ValueError("Backend approval requires certified upstream objects.")
    return _certified_sources(handoff.canonical_json(), backend.canonical_json(), finalization.canonical_json())


def _evaluate(finalization):
    # Public source loaders validate frozen owners, logical state, component and
    # operation/model references, required authorization and bounded scope.
    # Finalization replay rejects invalid history and contradictory claims.
    blockers = []
    for condition, code, message, field in (
        (any(q.blocking for q in finalization.unresolved_questions), "unresolved_backend_blockers", "Blocking backend questions remain.", "unresolved_questions"),
        (bool(finalization.conflicts), "active_backend_conflicts", "Backend conflicts remain active.", "conflicts"),
        (not finalization.effective_ready_for_approval, "backend_not_effectively_ready", "Backend is not effectively ready.", "effective_ready_for_approval"),
    ):
        if condition:
            blockers.append(BackendConsistencyFinding(code, message, BackendFindingSeverity.BLOCKING, (field,)))
    warnings = (BackendConsistencyFinding("generation_capability_not_certified",
        "ArcaCore generation compatibility requires separate public capability certification.",
        BackendFindingSeverity.WARNING, ("accepted_choices",)),)
    return BackendConsistencyEvaluation(not blockers, tuple(blockers), warnings)


def evaluate_backend_consistency(handoff, backend, finalization):
    _, _, finalization = _validated_sources(handoff, backend, finalization)
    return _evaluate(finalization)


@dataclass(frozen=True)
class FrozenApprovedBackendPackage(Record):
    models_backend_handoff: ModelsBackendHandoff
    original_backend: BackendSpecification
    backend_finalization: BackendFinalization
    consistency: BackendConsistencyEvaluation
    resolved_backend: ResolvedBackendAuthority

    def canonical_dict(self):
        return {f.name: getattr(self, f.name).canonical_dict() for f in fields(self)}

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        handoff, backend, finalization = _certified_sources(_json(value["models_backend_handoff"]),
            _json(value["original_backend"]), _json(value["backend_finalization"]))
        result = cls(handoff, backend, finalization, _evaluate(finalization), _resolved(finalization))
        if result.canonical_json() != _json(value):
            raise ValueError("Frozen backend consistency or resolved authority is forged.")
        return result


@dataclass(frozen=True)
class ApprovedBackend(Record):
    approval_id: str
    source_project_id: str
    models_backend_handoff_id: str
    backend_id: str
    backend_finalization_id: str
    approved_domain_model_id: str
    approved_architecture_id: str
    package: FrozenApprovedBackendPackage
    effective_ready_for_approval: bool
    approval_eligible: bool
    decision: ApprovalDecision
    approval_statement: str
    approved: bool
    schema: str = ARCADEV_APPROVED_BACKEND_SCHEMA
    schema_version: int = ARCADEV_APPROVED_BACKEND_SCHEMA_VERSION

    @classmethod
    def create(cls, *, handoff, backend, finalization, decision, approval_statement, source_project=None):
        handoff, backend, finalization = _validated_sources(handoff, backend, finalization)
        package = FrozenApprovedBackendPackage(handoff, backend, finalization, _evaluate(finalization), _resolved(finalization))
        return cls._build(package, decision, approval_statement, source_project)

    @classmethod
    def _build(cls, package, decision, approval_statement, source_project=None):
        handoff, backend, finalization = package.models_backend_handoff, package.original_backend, package.backend_finalization
        project = handoff.resulting_project
        if source_project is not None and (type(source_project) is not ArcaDevProject or _json(source_project.canonical_dict()) != _json(project.canonical_dict())):
            raise ValueError("Backend approval source project is stale or forged.")
        statement = _text(approval_statement, "Backend approval statement", 20_000)
        decision = ApprovalDecision(decision)
        eligible = bool(project.project_status is ProjectStatus.IN_PROGRESS and project.current_build_stage is BuildStage.BACKEND
            and finalization.effective_ready_for_approval and package.consistency.consistent and not finalization.conflicts)
        if decision is ApprovalDecision.APPROVED and not eligible:
            raise ValueError("Backend cannot be approved while readiness or consistency blockers remain.")
        result = cls("", handoff.source_project_id, handoff.handoff_id, backend.backend_id, finalization.finalization_id,
            handoff.approved_domain_model_id, handoff.approved_architecture_id, package,
            finalization.effective_ready_for_approval, eligible, decision, statement, decision is ApprovalDecision.APPROVED and eligible)
        body = result.canonical_dict()
        body.pop("approval_id")
        result = replace(result, approval_id=_identity("approved_backend", body))
        _safe(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_APPROVED_BACKEND_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported approved backend schema/version.")
        package = FrozenApprovedBackendPackage.from_dict(value["package"])
        result = cls._build(package, value["decision"], value["approval_statement"])
        if result.canonical_json() != _json(value):
            raise ValueError("Approved backend identity, approval or package is forged.")
        return result

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


def validate_approved_backend(candidate, *, source_project=None, handoff=None, backend=None, finalization=None):
    if type(candidate) is ApprovedBackend:
        candidate = candidate.canonical_dict()
    result = ApprovedBackend.from_json(candidate) if type(candidate) is str else ApprovedBackend.from_dict(candidate)
    for supplied, expected, kind in (
        (source_project, result.package.models_backend_handoff.resulting_project, ArcaDevProject),
        (handoff, result.package.models_backend_handoff, ModelsBackendHandoff),
        (backend, result.package.original_backend, BackendSpecification),
        (finalization, result.package.backend_finalization, BackendFinalization),
    ):
        if supplied is not None and (type(supplied) is not kind or _json(supplied.canonical_dict()) != _json(expected.canonical_dict())):
            raise ValueError("Approved backend is stale or mismatched against current upstream authority.")
    return result


def approve_backend(*, handoff, backend, finalization, approval_statement, source_project=None):
    return ApprovedBackend.create(handoff=handoff, backend=backend, finalization=finalization,
        decision=ApprovalDecision.APPROVED, approval_statement=approval_statement, source_project=source_project)


def reject_backend(*, handoff, backend, finalization, approval_statement, source_project=None):
    return ApprovedBackend.create(handoff=handoff, backend=backend, finalization=finalization,
        decision=ApprovalDecision.REJECTED, approval_statement=approval_statement, source_project=source_project)
