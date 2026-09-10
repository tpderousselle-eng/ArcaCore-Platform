"""Final PLAN consistency evaluation and explicit immutable approval."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any
import unicodedata

from .idea_plan_handoff import IdeaPlanHandoff, validate_idea_plan_handoff
from .plan_clarification import PlanFinalization
from .project import BuildStage, ProjectStatus


ARCADEV_APPROVED_PLAN_SCHEMA = "arcadev.approved_plan"
ARCADEV_APPROVED_PLAN_SCHEMA_VERSION = 1
MAX_APPROVED_PLAN_BYTES = 10_000_000
_SECRET = re.compile(r"(?i)(?:password|passwd|secret|api[_ -]?key|access[_ -]?token|private[_ -]?key)\s*(?:=|:)\s*[^\s,;]{4,}")
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


class PlanFindingSeverity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Approved plan contains duplicate key: {key}")
        result[key] = value
    return result


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has an invalid shape or unsupported fields.")
    return value


def _statement(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Approval statement must be text.")
    result = " ".join(value.split())
    if not result or len(result) > 20_000:
        raise ValueError("Approval statement is empty or exceeds its size limit.")
    try:
        result.encode("utf-8")
    except UnicodeError as error:
        raise ValueError("Approval statement is invalid Unicode.") from error
    if any(unicodedata.category(character) == "Cc" for character in result):
        raise ValueError("Approval statement contains control characters.")
    if _SECRET.search(result) or _PRIVATE_KEY.search(result):
        raise ValueError("Approval statement appears to contain a credential or secret value.")
    return result


@dataclass(frozen=True)
class PlanConsistencyFinding:
    code: str
    message: str
    severity: PlanFindingSeverity
    fields: tuple[str, ...]

    @classmethod
    def create(cls, code: str, message: str, severity: PlanFindingSeverity | str, fields) -> "PlanConsistencyFinding":
        try:
            severity = PlanFindingSeverity(severity)
            fields = tuple(sorted(fields))
        except (TypeError, ValueError) as error:
            raise ValueError("Plan consistency finding is malformed.") from error
        if not isinstance(code, str) or not code or not code.replace("_", "").isalnum():
            raise ValueError("Plan consistency code is invalid.")
        if not isinstance(message, str) or not message.strip() or len(message) > 2_000:
            raise ValueError("Plan consistency message is invalid.")
        if not fields or len(set(fields)) != len(fields) or any(not isinstance(item, str) or not item for item in fields):
            raise ValueError("Plan consistency fields are invalid.")
        return cls(code, " ".join(message.split()), severity, fields)

    @classmethod
    def from_dict(cls, value: Any) -> "PlanConsistencyFinding":
        value = _exact(value, {"code", "message", "severity", "fields"}, "Plan consistency finding")
        if not isinstance(value["fields"], list):
            raise ValueError("Plan consistency fields must be an array.")
        return cls.create(**value)

    def canonical_dict(self) -> dict[str, Any]:
        return {"code": self.code, "fields": list(self.fields), "message": self.message, "severity": self.severity.value}


@dataclass(frozen=True)
class PlanConsistencyEvaluation:
    consistent: bool
    blocking_findings: tuple[PlanConsistencyFinding, ...]
    warnings: tuple[PlanConsistencyFinding, ...]

    @classmethod
    def create(cls, findings=()) -> "PlanConsistencyEvaluation":
        findings = tuple(sorted(findings, key=lambda item: (item.severity.value, item.code, item.fields)))
        if any(not isinstance(item, PlanConsistencyFinding) for item in findings):
            raise ValueError("Plan consistency evaluation requires validated findings.")
        keys = [(item.severity.value, item.code, item.fields) for item in findings]
        if len(set(keys)) != len(keys):
            raise ValueError("Plan consistency evaluation contains duplicate findings.")
        blockers = tuple(item for item in findings if item.severity is PlanFindingSeverity.BLOCKING)
        warnings = tuple(item for item in findings if item.severity is PlanFindingSeverity.WARNING)
        return cls(not blockers, blockers, warnings)

    @classmethod
    def from_dict(cls, value: Any) -> "PlanConsistencyEvaluation":
        value = _exact(value, {"consistent", "blocking_findings", "warnings"}, "Plan consistency evaluation")
        if type(value["consistent"]) is not bool or not isinstance(value["blocking_findings"], list) or not isinstance(value["warnings"], list):
            raise ValueError("Plan consistency evaluation is malformed.")
        result = cls.create(PlanConsistencyFinding.from_dict(item) for item in value["blocking_findings"] + value["warnings"])
        if result.canonical_dict() != value:
            raise ValueError("Plan consistency evaluation is forged.")
        return result

    def canonical_dict(self) -> dict[str, Any]:
        return {"blocking_findings": [item.canonical_dict() for item in self.blocking_findings], "consistent": self.consistent,
            "warnings": [item.canonical_dict() for item in self.warnings]}


def evaluate_plan_consistency(handoff: IdeaPlanHandoff, finalization: PlanFinalization) -> PlanConsistencyEvaluation:
    handoff = validate_idea_plan_handoff(handoff.canonical_dict())
    finalization = PlanFinalization.from_dict(finalization.canonical_dict(), handoff=handoff)
    plan = finalization.original_plan
    intake = handoff.snapshot.intake
    findings: list[PlanConsistencyFinding] = []

    def finding(code, message, *fields, severity=PlanFindingSeverity.BLOCKING):
        findings.append(PlanConsistencyFinding.create(code, message, severity, fields))

    if finalization.unresolved_questions:
        finding("unresolved_planning_questions", "Required planning questions remain unresolved.", "unresolved_questions")
    if finalization.conflicts:
        finding("active_planning_conflicts", "Planning conflicts remain active.", "conflicts")
    if not finalization.effective_ready_for_architecture:
        finding("plan_not_effectively_ready", "The finalized plan is not effectively ready for architecture.", "effective_readiness")
    if plan.handoff_id != handoff.handoff_id or plan.project_id != handoff.source_project_id:
        finding("identity_binding_mismatch", "Plan identities do not bind to the approved IDEA handoff.", "handoff_id", "project_id")
    if {item.value.casefold() for item in plan.scope.in_scope} != {item.value.casefold() for item in plan.in_scope_capabilities}:
        finding("scope_capability_mismatch", "In-scope capabilities and scope are inconsistent.", "scope", "in_scope_capabilities")

    constraints = {item.value.casefold() for item in plan.planning_constraints}
    expected_collections = {
        "platform_consistency": tuple(item.value for item in intake.platform_targets),
        "authentication_consistency": tuple(item.value for item in intake.authentication_requirements),
        "deployment_consistency": tuple(item.value for item in intake.deployment_requirements),
    }
    for code, expected in expected_collections.items():
        if any(item.casefold() not in constraints for item in expected):
            finding(code, "The plan does not preserve an approved IDEA constraint.", "planning_constraints", code.removesuffix("_consistency"))
    planned_integrations = {item.value.casefold() for item in plan.integrations}
    expected_integrations = {item.value.casefold() for item in intake.integration_requirements}
    if planned_integrations != expected_integrations:
        finding("integration_consistency", "Plan integrations do not match the approved IDEA.", "integrations")

    in_scope = {item.value.casefold() for item in plan.scope.in_scope}
    out_scope = {item.value.casefold() for item in plan.scope.out_of_scope}
    unclassified = False
    for decision in finalization.decisions:
        for value in decision.accepted_values:
            lowered = value.casefold()
            if lowered.startswith("out_of_scope=") and lowered.split("=", 1)[1] in in_scope:
                finding("decision_scope_conflict", "A planning decision excludes an in-scope capability.", "decisions", "scope")
            elif lowered.startswith("in_scope=") and lowered.split("=", 1)[1] in out_scope:
                finding("decision_scope_conflict", "A planning decision includes an explicitly out-of-scope capability.", "decisions", "scope")
            elif not any(lowered.startswith(prefix) for prefix in ("out_of_scope=", "in_scope=", "platform=", "authentication=", "integration=", "deployment=")):
                unclassified = True
    if unclassified:
        finding("decision_semantics_not_machine_classified", "Some explicit decisions are preserved as text and have no additional deterministic compatibility rule.",
            "decisions", severity=PlanFindingSeverity.WARNING)
    return PlanConsistencyEvaluation.create(findings)


@dataclass(frozen=True)
class FrozenApprovedPlanPackage:
    idea_handoff: IdeaPlanHandoff
    plan_finalization: PlanFinalization
    consistency: PlanConsistencyEvaluation

    @classmethod
    def from_dict(cls, value: Any) -> "FrozenApprovedPlanPackage":
        value = _exact(value, {"idea_handoff", "plan_finalization", "consistency"}, "Frozen approved plan package")
        handoff = IdeaPlanHandoff.from_dict(value["idea_handoff"])
        return cls(handoff, PlanFinalization.from_dict(value["plan_finalization"], handoff=handoff), PlanConsistencyEvaluation.from_dict(value["consistency"]))

    def canonical_dict(self) -> dict[str, Any]:
        return {"consistency": self.consistency.canonical_dict(), "idea_handoff": self.idea_handoff.canonical_dict(),
            "plan_finalization": self.plan_finalization.canonical_dict()}


@dataclass(frozen=True)
class ApprovedPlan:
    approval_id: str
    source_project_id: str
    idea_handoff_id: str
    software_plan_id: str
    plan_finalization_id: str
    package: FrozenApprovedPlanPackage
    effective_ready_for_architecture: bool
    approval_eligible: bool
    decision: ApprovalDecision
    approval_statement: str
    approved: bool
    schema: str = ARCADEV_APPROVED_PLAN_SCHEMA
    schema_version: int = ARCADEV_APPROVED_PLAN_SCHEMA_VERSION

    @classmethod
    def create(cls, *, handoff: IdeaPlanHandoff, finalization: PlanFinalization, decision: ApprovalDecision | str,
               approval_statement: str) -> "ApprovedPlan":
        handoff = validate_idea_plan_handoff(handoff.canonical_dict())
        finalization = PlanFinalization.from_dict(finalization.canonical_dict(), handoff=handoff)
        statement = _statement(approval_statement)
        try:
            decision = ApprovalDecision(decision)
        except (TypeError, ValueError) as error:
            raise ValueError("Plan approval decision is unsupported.") from error
        consistency = evaluate_plan_consistency(handoff, finalization)
        project = handoff.resulting_project
        eligible = bool(project.project_status is ProjectStatus.IN_PROGRESS and project.current_build_stage is BuildStage.PLAN
            and finalization.effective_ready_for_architecture and not finalization.unresolved_questions and not finalization.conflicts
            and consistency.consistent)
        if decision is ApprovalDecision.APPROVED and not eligible:
            raise ValueError("Plan cannot be approved while readiness, consistency, conflict, or identity blockers remain.")
        approved = decision is ApprovalDecision.APPROVED and eligible
        package = FrozenApprovedPlanPackage(handoff, finalization, consistency)
        body = {"approval_eligible": eligible, "approval_statement": statement, "approved": approved, "decision": decision.value,
            "effective_ready_for_architecture": finalization.effective_ready_for_architecture, "idea_handoff_id": handoff.handoff_id,
            "package": package.canonical_dict(), "plan_finalization_id": finalization.finalization_id,
            "schema": ARCADEV_APPROVED_PLAN_SCHEMA, "schema_version": ARCADEV_APPROVED_PLAN_SCHEMA_VERSION,
            "software_plan_id": finalization.original_plan.plan_id, "source_project_id": handoff.source_project_id}
        digest = hashlib.sha256(("arcadev-approved-plan-identity/v1\0" + _json(body)).encode("utf-8")).hexdigest()
        return cls(f"arcadev_approved_plan_{digest[:32]}", handoff.source_project_id, handoff.handoff_id,
            finalization.original_plan.plan_id, finalization.finalization_id, package, finalization.effective_ready_for_architecture,
            eligible, decision, statement, approved)

    @classmethod
    def from_dict(cls, value: Any) -> "ApprovedPlan":
        fields = {"approval_id", "source_project_id", "idea_handoff_id", "software_plan_id", "plan_finalization_id", "package",
            "effective_ready_for_architecture", "approval_eligible", "decision", "approval_statement", "approved", "schema", "schema_version"}
        value = _exact(value, fields, "Approved plan")
        if value["schema"] != ARCADEV_APPROVED_PLAN_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != ARCADEV_APPROVED_PLAN_SCHEMA_VERSION:
            raise ValueError("Approved plan schema or version is unsupported.")
        if any(type(value[field]) is not bool for field in ("effective_ready_for_architecture", "approval_eligible", "approved")):
            raise ValueError("Approved plan booleans are malformed.")
        package = FrozenApprovedPlanPackage.from_dict(value["package"])
        result = cls.create(handoff=package.idea_handoff, finalization=package.plan_finalization,
            decision=value["decision"], approval_statement=value["approval_statement"])
        if result.canonical_dict() != value:
            raise ValueError("Approved plan identity, eligibility, decision, or frozen package is forged.")
        return result

    @classmethod
    def from_json(cls, text: str) -> "ApprovedPlan":
        if not isinstance(text, str):
            raise ValueError("Approved plan must be JSON text.")
        try:
            if len(text.encode("utf-8")) > MAX_APPROVED_PLAN_BYTES:
                raise ValueError("Approved plan exceeds the safety limit.")
            value = json.loads(text, object_pairs_hook=_unique)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Approved plan is not valid JSON.") from error
        return cls.from_dict(value)

    def canonical_dict(self) -> dict[str, Any]:
        return {"approval_eligible": self.approval_eligible, "approval_id": self.approval_id, "approval_statement": self.approval_statement,
            "approved": self.approved, "decision": self.decision.value, "effective_ready_for_architecture": self.effective_ready_for_architecture,
            "idea_handoff_id": self.idea_handoff_id, "package": self.package.canonical_dict(),
            "plan_finalization_id": self.plan_finalization_id, "schema": self.schema, "schema_version": self.schema_version,
            "software_plan_id": self.software_plan_id, "source_project_id": self.source_project_id}

    def canonical_json(self) -> str:
        return _json(self.canonical_dict())


def approve_plan(*, handoff: IdeaPlanHandoff, finalization: PlanFinalization, approval_statement: str) -> ApprovedPlan:
    return ApprovedPlan.create(handoff=handoff, finalization=finalization, decision=ApprovalDecision.APPROVED,
        approval_statement=approval_statement)


def reject_plan(*, handoff: IdeaPlanHandoff, finalization: PlanFinalization, approval_statement: str) -> ApprovedPlan:
    return ApprovedPlan.create(handoff=handoff, finalization=finalization, decision=ApprovalDecision.REJECTED,
        approval_statement=approval_statement)
