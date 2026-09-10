"""Deterministic, auditable IDEA-to-PLAN transition gate."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from .clarification import IdeaFinalization, idea_intake_id
from .idea_intake import IdeaIntake
from .project import ArcaDevProject, BuildStage, ProjectStatus


ARCADEV_IDEA_PLAN_HANDOFF_SCHEMA = "arcadev.idea_plan_handoff"
ARCADEV_IDEA_PLAN_HANDOFF_SCHEMA_VERSION = 1
MAX_IDEA_PLAN_HANDOFF_BYTES = 5_000_000


class FindingSeverity(str, Enum):
    BLOCKING = "blocking"
    WARNING = "warning"


class TransitionDecision(str, Enum):
    BLOCKED = "blocked"
    TRANSITIONED = "transitioned"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"IDEA handoff contains duplicate key: {key}")
        result[key] = value
    return result


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has an invalid shape or unsupported fields.")
    return value


@dataclass(frozen=True)
class ConsistencyFinding:
    code: str
    message: str
    severity: FindingSeverity
    fields: tuple[str, ...]

    @classmethod
    def create(cls, code: str, message: str, severity: FindingSeverity | str, fields) -> "ConsistencyFinding":
        if not isinstance(code, str) or not code or not code.replace("_", "").isalnum():
            raise ValueError("Consistency finding code is invalid.")
        if not isinstance(message, str) or not message.strip() or len(message) > 2_000:
            raise ValueError("Consistency finding message is invalid.")
        try:
            severity = FindingSeverity(severity)
            fields = tuple(sorted(fields))
        except (TypeError, ValueError) as error:
            raise ValueError("Consistency finding is malformed.") from error
        if not fields or any(not isinstance(item, str) or not item for item in fields):
            raise ValueError("Consistency finding fields are invalid.")
        if len(set(fields)) != len(fields):
            raise ValueError("Consistency finding fields contain duplicates.")
        return cls(code, " ".join(message.split()), severity, fields)

    @classmethod
    def from_dict(cls, value: Any) -> "ConsistencyFinding":
        value = _exact(value, {"code", "message", "severity", "fields"}, "Consistency finding")
        if not isinstance(value["fields"], list):
            raise ValueError("Consistency finding fields must be an array.")
        return cls.create(**value)

    def canonical_dict(self) -> dict[str, Any]:
        return {"code": self.code, "fields": list(self.fields), "message": self.message, "severity": self.severity.value}


@dataclass(frozen=True)
class ConsistencyEvaluation:
    consistent: bool
    blocking_findings: tuple[ConsistencyFinding, ...]
    warnings: tuple[ConsistencyFinding, ...]

    @classmethod
    def create(cls, findings=()) -> "ConsistencyEvaluation":
        try:
            items = tuple(findings)
        except TypeError as error:
            raise ValueError("Consistency findings must be a collection.") from error
        if any(not isinstance(item, ConsistencyFinding) for item in items):
            raise ValueError("Consistency findings must be validated values.")
        items = tuple(sorted(items, key=lambda item: (item.severity.value, item.code, item.fields)))
        keys = [(item.severity.value, item.code, item.fields) for item in items]
        if len(set(keys)) != len(keys):
            raise ValueError("Consistency evaluation contains duplicate findings.")
        blockers = tuple(item for item in items if item.severity is FindingSeverity.BLOCKING)
        warnings = tuple(item for item in items if item.severity is FindingSeverity.WARNING)
        return cls(not blockers, blockers, warnings)

    @classmethod
    def from_dict(cls, value: Any) -> "ConsistencyEvaluation":
        value = _exact(value, {"consistent", "blocking_findings", "warnings"}, "Consistency evaluation")
        if type(value["consistent"]) is not bool or not isinstance(value["blocking_findings"], list) or not isinstance(value["warnings"], list):
            raise ValueError("Consistency evaluation is malformed.")
        findings = [ConsistencyFinding.from_dict(item) for item in value["blocking_findings"] + value["warnings"]]
        result = cls.create(findings)
        if result.canonical_dict() != value:
            raise ValueError("Consistency evaluation does not match deterministic findings.")
        return result

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "blocking_findings": [item.canonical_dict() for item in self.blocking_findings],
            "consistent": self.consistent,
            "warnings": [item.canonical_dict() for item in self.warnings],
        }


def evaluate_idea_consistency(intake: IdeaIntake) -> ConsistencyEvaluation:
    intake = IdeaIntake.from_dict(intake.canonical_dict())
    project_type = intake.project_type.value.casefold() if intake.project_type else ""
    platforms = tuple(item.value.casefold() for item in intake.platform_targets)
    authentication = tuple(item.value.casefold() for item in intake.authentication_requirements)
    integrations = tuple(item.value.casefold() for item in intake.integration_requirements)
    deployment = tuple(item.value.casefold() for item in intake.deployment_requirements)
    findings: list[ConsistencyFinding] = []

    def blocker(code: str, message: str, *fields: str) -> None:
        findings.append(ConsistencyFinding.create(code, message, FindingSeverity.BLOCKING, fields))

    if project_type == "web_application" and platforms and not any("web" in item for item in platforms):
        blocker("web_without_web_target", "A web application requires at least one compatible web platform target.", "project_type", "platform_targets")
    if project_type == "mobile_application" and platforms and not any(
        token in item for item in platforms for token in ("mobile", "ios", "android")
    ):
        blocker("mobile_without_mobile_target", "A mobile application requires at least one compatible mobile platform target.", "project_type", "platform_targets")

    auth_none = any(item in {"no authentication", "no authentication required", "authentication not required", "without authentication"} for item in authentication)
    if auth_none and len(authentication) > 1:
        blocker("authentication_contradiction", "No authentication cannot be combined with required authentication mechanisms.", "authentication_requirements")
    integration_none = any(item in {"no external integrations", "no integrations", "without integrations"} for item in integrations)
    if integration_none and len(integrations) > 1:
        blocker("integration_contradiction", "No external integrations cannot be combined with explicit integrations.", "integration_requirements")

    managed = any("managed cloud" in item for item in deployment)
    self_hosted = any(token in item for item in deployment for token in ("self-hosted", "self hosted", "on-premises", "on premises"))
    if managed and self_hosted:
        blocker("deployment_contradiction", "Managed-only and self-hosted deployment choices are mutually exclusive.", "deployment_requirements")
    if project_type not in {"web_application", "mobile_application"}:
        findings.append(ConsistencyFinding.create(
            "platform_compatibility_not_determined",
            "No deterministic platform compatibility rule exists for this project type.",
            FindingSeverity.WARNING,
            ("project_type", "platform_targets"),
        ))
    return ConsistencyEvaluation.create(findings)


@dataclass(frozen=True)
class FrozenIdeaSnapshot:
    project: ArcaDevProject
    finalization: IdeaFinalization
    consistency: ConsistencyEvaluation

    @property
    def intake(self) -> IdeaIntake:
        return self.finalization.current_intake

    @classmethod
    def from_dict(cls, value: Any) -> "FrozenIdeaSnapshot":
        value = _exact(value, {"project", "finalization", "consistency"}, "Frozen IDEA snapshot")
        return cls(
            ArcaDevProject.from_dict(value["project"]),
            IdeaFinalization.from_dict(value["finalization"]),
            ConsistencyEvaluation.from_dict(value["consistency"]),
        )

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "consistency": self.consistency.canonical_dict(),
            "finalization": self.finalization.canonical_dict(),
            "project": self.project.canonical_dict(),
        }


def _transitioned_project(project: ArcaDevProject) -> ArcaDevProject:
    return replace(project, project_status=ProjectStatus.IN_PROGRESS, current_build_stage=BuildStage.PLAN)


@dataclass(frozen=True)
class IdeaPlanHandoff:
    handoff_id: str
    source_project_id: str
    source_intake_id: str
    snapshot: FrozenIdeaSnapshot
    eligible: bool
    decision: TransitionDecision
    resulting_project: ArcaDevProject
    schema: str = ARCADEV_IDEA_PLAN_HANDOFF_SCHEMA
    schema_version: int = ARCADEV_IDEA_PLAN_HANDOFF_SCHEMA_VERSION

    @classmethod
    def create(cls, project: ArcaDevProject, finalization: IdeaFinalization) -> "IdeaPlanHandoff":
        if not isinstance(project, ArcaDevProject) or not isinstance(finalization, IdeaFinalization):
            raise ValueError("IDEA handoff requires validated project and finalization values.")
        project = ArcaDevProject.from_dict(project.canonical_dict())
        finalization = IdeaFinalization.from_dict(finalization.canonical_dict())
        intake = finalization.current_intake
        expected_project = finalization.to_project(metadata=project.metadata) if intake.readiness.ready_for_plan and not finalization.conflicts else None
        identities_match = expected_project is not None and expected_project.canonical_dict() == project.canonical_dict()
        consistency = evaluate_idea_consistency(intake)
        eligible = bool(
            project.project_status is ProjectStatus.READY
            and project.current_build_stage is BuildStage.IDEA
            and intake.readiness.ready_for_plan
            and not intake.unresolved_requirements
            and not intake.assumptions
            and not finalization.conflicts
            and identities_match
            and consistency.consistent
        )
        snapshot = FrozenIdeaSnapshot(project, finalization, consistency)
        decision = TransitionDecision.TRANSITIONED if eligible else TransitionDecision.BLOCKED
        result = _transitioned_project(project) if eligible else project
        body = {
            "decision": decision.value,
            "eligible": eligible,
            "resulting_project": result.canonical_dict(),
            "schema": ARCADEV_IDEA_PLAN_HANDOFF_SCHEMA,
            "schema_version": ARCADEV_IDEA_PLAN_HANDOFF_SCHEMA_VERSION,
            "snapshot": snapshot.canonical_dict(),
            "source_intake_id": idea_intake_id(intake),
            "source_project_id": project.project_id,
        }
        digest = hashlib.sha256(("arcadev-idea-plan-handoff-identity/v1\0" + _canonical_json(body)).encode("utf-8")).hexdigest()
        return cls(f"arcadev_handoff_{digest[:32]}", project.project_id, idea_intake_id(intake), snapshot, eligible, decision, result)

    @classmethod
    def from_dict(cls, value: Any) -> "IdeaPlanHandoff":
        keys = {"handoff_id", "source_project_id", "source_intake_id", "snapshot", "eligible", "decision", "resulting_project", "schema", "schema_version"}
        value = _exact(value, keys, "IDEA handoff")
        if value["schema"] != ARCADEV_IDEA_PLAN_HANDOFF_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != ARCADEV_IDEA_PLAN_HANDOFF_SCHEMA_VERSION:
            raise ValueError("IDEA handoff schema or version is unsupported.")
        snapshot = FrozenIdeaSnapshot.from_dict(value["snapshot"])
        expected = cls.create(snapshot.project, snapshot.finalization)
        if value != expected.canonical_dict():
            raise ValueError("IDEA handoff contains a forged, stale, or inconsistent transition result.")
        return expected

    @classmethod
    def from_json(cls, text: str) -> "IdeaPlanHandoff":
        if not isinstance(text, str):
            raise ValueError("IDEA handoff must be JSON text.")
        try:
            if len(text.encode("utf-8")) > MAX_IDEA_PLAN_HANDOFF_BYTES:
                raise ValueError("IDEA handoff exceeds the safety limit.")
            value = json.loads(text, object_pairs_hook=_unique_object)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("IDEA handoff is not valid JSON.") from error
        return cls.from_dict(value)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "eligible": self.eligible,
            "handoff_id": self.handoff_id,
            "resulting_project": self.resulting_project.canonical_dict(),
            "schema": self.schema,
            "schema_version": self.schema_version,
            "snapshot": self.snapshot.canonical_dict(),
            "source_intake_id": self.source_intake_id,
            "source_project_id": self.source_project_id,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_dict())


def create_idea_plan_handoff(project: ArcaDevProject, finalization: IdeaFinalization) -> IdeaPlanHandoff:
    return IdeaPlanHandoff.create(project, finalization)


def validate_idea_plan_handoff(candidate: Mapping[str, Any] | str, *, project: ArcaDevProject | None = None, finalization: IdeaFinalization | None = None) -> IdeaPlanHandoff:
    if isinstance(candidate, str):
        handoff = IdeaPlanHandoff.from_json(candidate)
    elif isinstance(candidate, Mapping):
        handoff = IdeaPlanHandoff.from_dict(dict(candidate))
    else:
        raise ValueError("IDEA handoff candidate must be an object or JSON text.")
    if project is not None and handoff.source_project_id != project.project_id:
        raise ValueError("IDEA handoff is a replay against another project.")
    if finalization is not None and handoff.source_intake_id != finalization.current_intake_id:
        raise ValueError("IDEA handoff is stale for the current finalized intake.")
    return handoff
