"""Deterministic final consistency and explicit approval of a frozen architecture.

Integrity, graph and PLAN authority checks reuse the certified specification and
finalization loaders. Replay validates decisions; it never changes source data.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum

from .architecture_clarification import ArchitectureFinalization
from .architecture_specification import (
    ArchitectureSpecification, Record, _exact, _identity, _json, _parse, _safe,
    _strings, _text, validate_architecture_specification,
)
from .plan_approval import ApprovalDecision
from .plan_architecture_handoff import PlanArchitectureHandoff, validate_plan_architecture_handoff
from .project import ArcaDevProject, BuildStage, ProjectStatus

ARCADEV_APPROVED_ARCHITECTURE_SCHEMA = "arcadev.approved_architecture"
ARCADEV_APPROVED_ARCHITECTURE_SCHEMA_VERSION = 1


class ArchitectureFindingSeverity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


@dataclass(frozen=True)
class ArchitectureConsistencyFinding(Record):
    code: str
    message: str
    severity: ArchitectureFindingSeverity
    fields: tuple[str, ...]

    @classmethod
    def create(cls, code, message, severity, fields):
        code = _text(code, maximum=240)
        if not code.replace("_", "").isalnum():
            raise ValueError("Invalid architecture finding code.")
        return cls(code, _text(message, maximum=2000), ArchitectureFindingSeverity(severity), _strings(fields, required=True))

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if type(value["fields"]) is not list:
            raise ValueError("Architecture finding fields must be an array.")
        return cls.create(**value)


@dataclass(frozen=True)
class ArchitectureConsistencyEvaluation(Record):
    consistent: bool
    blocking_findings: tuple[ArchitectureConsistencyFinding, ...]
    warnings: tuple[ArchitectureConsistencyFinding, ...]

    @classmethod
    def create(cls, findings=()):
        validated = []
        for finding in findings:
            if type(finding) is not ArchitectureConsistencyFinding:
                raise ValueError("Expected architecture consistency findings.")
            validated.append(ArchitectureConsistencyFinding.from_dict(finding.canonical_dict()))
        validated.sort(key=lambda f: (f.severity.value, f.code, f.fields))
        keys = [(f.severity, f.code, f.fields) for f in validated]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate architecture findings.")
        blockers = tuple(f for f in validated if f.severity is ArchitectureFindingSeverity.BLOCKING)
        warnings = tuple(f for f in validated if f.severity is ArchitectureFindingSeverity.WARNING)
        return cls(not blockers, blockers, warnings)

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if type(value["consistent"]) is not bool or any(type(value[k]) is not list for k in ("blocking_findings", "warnings")):
            raise ValueError("Malformed architecture consistency evaluation.")
        result = cls.create(ArchitectureConsistencyFinding.from_dict(f) for f in value["blocking_findings"] + value["warnings"])
        if _json(result.canonical_dict()) != _json(value):
            raise ValueError("Forged architecture consistency evaluation.")
        return result


def _validated_sources(handoff, architecture, finalization):
    if type(handoff) is not PlanArchitectureHandoff or type(architecture) is not ArchitectureSpecification or type(finalization) is not ArchitectureFinalization:
        raise ValueError("Architecture approval requires certified upstream objects.")
    handoff = validate_plan_architecture_handoff(handoff)
    architecture = validate_architecture_specification(architecture, handoff=handoff)
    finalization = ArchitectureFinalization.from_dict(finalization.canonical_dict(), handoff=handoff)
    if architecture.canonical_json() != finalization.original_architecture.canonical_json():
        raise ValueError("Architecture finalization belongs to another or stale architecture.")
    return handoff, architecture, finalization


def _evaluate(finalization):
    # Called only after certified source validation: ownership, boundary coverage,
    # platform/deployment constraints, graph integrity, supported scope and every
    # decision's PLAN authority/compatibility have already been checked by replay.
    findings = []
    for condition, code, message, field in (
        (any(q.blocking for q in finalization.unresolved_questions), "unresolved_architecture_blockers", "Blocking architecture questions remain unresolved.", "unresolved_questions"),
        (bool(finalization.conflicts), "active_architecture_conflicts", "Architecture conflicts remain active.", "conflicts"),
        (not finalization.effective_ready_for_approval, "architecture_not_effectively_ready", "Architecture is not effectively ready for approval.", "effective_ready_for_approval"),
    ):
        if condition:
            findings.append(ArchitectureConsistencyFinding.create(code, message, ArchitectureFindingSeverity.BLOCKING, (field,)))
    if finalization.decisions:
        findings.append(ArchitectureConsistencyFinding.create(
            "implementation_compatibility_not_proven", "Explicit implementation decisions preserve frozen PLAN authority; runtime compatibility still requires later implementation and testing.",
            ArchitectureFindingSeverity.WARNING, ("decisions",)))
    if any(not q.blocking for q in finalization.unresolved_questions):
        findings.append(ArchitectureConsistencyFinding.create(
            "unresolved_advisory_questions", "Non-blocking architecture questions remain for review.",
            ArchitectureFindingSeverity.WARNING, ("unresolved_questions",)))
    return ArchitectureConsistencyEvaluation.create(findings)


def evaluate_architecture_consistency(handoff, architecture, finalization):
    _, _, finalization = _validated_sources(handoff, architecture, finalization)
    return _evaluate(finalization)


@dataclass(frozen=True)
class FrozenApprovedArchitecturePackage(Record):
    plan_handoff: PlanArchitectureHandoff
    original_architecture: ArchitectureSpecification
    architecture_finalization: ArchitectureFinalization
    consistency: ArchitectureConsistencyEvaluation

    def canonical_dict(self):
        return {f.name: getattr(self, f.name).canonical_dict() for f in fields(self)}

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        handoff = PlanArchitectureHandoff.from_dict(value["plan_handoff"])
        architecture = ArchitectureSpecification.from_dict(value["original_architecture"], handoff=handoff)
        finalization = ArchitectureFinalization.from_dict(value["architecture_finalization"], handoff=handoff)
        if architecture.canonical_json() != finalization.original_architecture.canonical_json():
            raise ValueError("Frozen architecture/finalization binding is stale or forged.")
        consistency = ArchitectureConsistencyEvaluation.from_dict(value["consistency"])
        if consistency != _evaluate(finalization):
            raise ValueError("Frozen architecture consistency is forged.")
        return cls(handoff, architecture, finalization, consistency)


@dataclass(frozen=True)
class ApprovedArchitecture(Record):
    approval_id: str
    source_project_id: str
    plan_handoff_id: str
    architecture_id: str
    architecture_finalization_id: str
    package: FrozenApprovedArchitecturePackage
    effective_ready_for_approval: bool
    approval_eligible: bool
    decision: ApprovalDecision
    approval_statement: str
    approved: bool
    schema: str = ARCADEV_APPROVED_ARCHITECTURE_SCHEMA
    schema_version: int = ARCADEV_APPROVED_ARCHITECTURE_SCHEMA_VERSION

    @classmethod
    def create(cls, *, handoff, architecture, finalization, decision, approval_statement, source_project=None):
        handoff, architecture, finalization = _validated_sources(handoff, architecture, finalization)
        package = FrozenApprovedArchitecturePackage(handoff, architecture, finalization, _evaluate(finalization))
        return cls._build(package, decision, approval_statement, source_project)

    @classmethod
    def _build(cls, package, decision, approval_statement, source_project=None):
        """Construct only from a package validated in this call's public boundary."""
        handoff, architecture, finalization = package.plan_handoff, package.original_architecture, package.architecture_finalization
        project = handoff.resulting_project
        if source_project is not None and (type(source_project) is not ArcaDevProject or source_project.canonical_dict() != project.canonical_dict()):
            raise ValueError("Architecture approval source project is stale or forged.")
        statement = _text(approval_statement, "Architecture approval statement", 20_000)
        try:
            decision = ApprovalDecision(decision)
        except (TypeError, ValueError) as error:
            raise ValueError("Unsupported architecture approval decision.") from error
        consistency = package.consistency
        eligible = bool(project.project_status is ProjectStatus.IN_PROGRESS and project.current_build_stage is BuildStage.ARCHITECTURE
                        and finalization.effective_ready_for_approval and consistency.consistent
                        and not any(q.blocking for q in finalization.unresolved_questions) and not finalization.conflicts)
        if decision is ApprovalDecision.APPROVED and not eligible:
            raise ValueError("Architecture cannot be approved while readiness or consistency blockers remain.")
        result = cls("", handoff.source_project_id, handoff.handoff_id, architecture.architecture_id, finalization.finalization_id,
                     package,
                     finalization.effective_ready_for_approval, eligible, decision, statement, decision is ApprovalDecision.APPROVED and eligible)
        body = result.canonical_dict()
        body.pop("approval_id")
        result = replace(result, approval_id=_identity("approved_architecture", body))
        _safe(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_APPROVED_ARCHITECTURE_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported approved architecture schema/version.")
        package = FrozenApprovedArchitecturePackage.from_dict(value["package"])
        result = cls._build(package, value["decision"], value["approval_statement"])
        if _json(result.canonical_dict()) != _json(value):
            raise ValueError("Approved architecture identity, eligibility, decision or frozen package is forged.")
        return result

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


def validate_approved_architecture(candidate, *, source_project=None, handoff=None, architecture=None, finalization=None):
    if type(candidate) is ApprovedArchitecture:
        candidate = candidate.canonical_dict()
    result = ApprovedArchitecture.from_json(candidate) if type(candidate) is str else ApprovedArchitecture.from_dict(candidate)
    for supplied, expected, kind in (
        (source_project, result.package.plan_handoff.resulting_project, ArcaDevProject),
        (handoff, result.package.plan_handoff, PlanArchitectureHandoff),
        (architecture, result.package.original_architecture, ArchitectureSpecification),
        (finalization, result.package.architecture_finalization, ArchitectureFinalization),
    ):
        if supplied is not None and (type(supplied) is not kind or _json(supplied.canonical_dict()) != _json(expected.canonical_dict())):
            raise ValueError("Approved architecture is stale or mismatched against current upstream authority.")
    return result


def approve_architecture(*, handoff, architecture, finalization, approval_statement, source_project=None):
    return ApprovedArchitecture.create(handoff=handoff, architecture=architecture, finalization=finalization,
        decision=ApprovalDecision.APPROVED, approval_statement=approval_statement, source_project=source_project)


def reject_architecture(*, handoff, architecture, finalization, approval_statement, source_project=None):
    return ApprovedArchitecture.create(handoff=handoff, architecture=architecture, finalization=finalization,
        decision=ApprovalDecision.REJECTED, approval_statement=approval_statement, source_project=source_project)
