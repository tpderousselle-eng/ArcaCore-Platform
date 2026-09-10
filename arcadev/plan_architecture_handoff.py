"""Controlled transition from an explicitly approved PLAN to ARCHITECTURE."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
from typing import Any, Mapping

from .plan_approval import ApprovedPlan
from .project import ArcaDevProject, BuildStage, ProjectStatus


ARCADEV_PLAN_ARCHITECTURE_HANDOFF_SCHEMA = "arcadev.plan_architecture_handoff"
ARCADEV_PLAN_ARCHITECTURE_HANDOFF_SCHEMA_VERSION = 1
MAX_PLAN_ARCHITECTURE_HANDOFF_BYTES = 15_000_000


class ArchitectureTransitionDecision(str, Enum):
    TRANSITIONED = "transitioned"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"PLAN architecture handoff contains duplicate key: {key}")
        result[key] = value
    return result


def _exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has an invalid shape or unsupported fields.")
    return value


@dataclass(frozen=True)
class PlanArchitectureHandoff:
    handoff_id: str
    source_project_id: str
    idea_handoff_id: str
    approved_plan_id: str
    software_plan_id: str
    plan_finalization_id: str
    frozen_approved_plan: ApprovedPlan
    transition_eligible: bool
    decision: ArchitectureTransitionDecision
    resulting_project: ArcaDevProject
    schema: str = ARCADEV_PLAN_ARCHITECTURE_HANDOFF_SCHEMA
    schema_version: int = ARCADEV_PLAN_ARCHITECTURE_HANDOFF_SCHEMA_VERSION

    @classmethod
    def create(cls, *, source_project: ArcaDevProject, approved_plan: ApprovedPlan) -> "PlanArchitectureHandoff":
        if not isinstance(source_project, ArcaDevProject) or not isinstance(approved_plan, ApprovedPlan):
            raise ValueError("PLAN architecture handoff requires validated project and approved-plan values.")
        approved_plan = ApprovedPlan.from_dict(approved_plan.canonical_dict())
        expected_source = approved_plan.package.idea_handoff.resulting_project
        if source_project.canonical_dict() != expected_source.canonical_dict():
            raise ValueError("PLAN architecture handoff source project is forged, stale, or belongs to another approval.")
        if source_project.project_status is not ProjectStatus.IN_PROGRESS or source_project.current_build_stage is not BuildStage.PLAN:
            raise ValueError("PLAN architecture handoff requires an IN_PROGRESS project at PLAN.")
        if not approved_plan.approved or not approved_plan.approval_eligible:
            raise ValueError("PLAN architecture transition requires explicit approved-plan approval.")
        if not approved_plan.effective_ready_for_architecture or not approved_plan.package.consistency.consistent:
            raise ValueError("PLAN architecture transition requires readiness and passing consistency.")
        finalization = approved_plan.package.plan_finalization
        if finalization.unresolved_questions or finalization.conflicts:
            raise ValueError("PLAN architecture transition cannot contain unresolved questions or conflicts.")
        result = replace(source_project, project_status=ProjectStatus.IN_PROGRESS, current_build_stage=BuildStage.ARCHITECTURE)
        body = {
            "approved_plan_id": approved_plan.approval_id,
            "decision": ArchitectureTransitionDecision.TRANSITIONED.value,
            "frozen_approved_plan": approved_plan.canonical_dict(),
            "idea_handoff_id": approved_plan.idea_handoff_id,
            "plan_finalization_id": approved_plan.plan_finalization_id,
            "resulting_project": result.canonical_dict(),
            "schema": ARCADEV_PLAN_ARCHITECTURE_HANDOFF_SCHEMA,
            "schema_version": ARCADEV_PLAN_ARCHITECTURE_HANDOFF_SCHEMA_VERSION,
            "software_plan_id": approved_plan.software_plan_id,
            "source_project_id": source_project.project_id,
            "transition_eligible": True,
        }
        digest = hashlib.sha256(("arcadev-plan-architecture-handoff-identity/v1\0" + _json(body)).encode("utf-8")).hexdigest()
        return cls(f"arcadev_arch_handoff_{digest[:32]}", source_project.project_id, approved_plan.idea_handoff_id,
            approved_plan.approval_id, approved_plan.software_plan_id, approved_plan.plan_finalization_id,
            approved_plan, True, ArchitectureTransitionDecision.TRANSITIONED, result)

    @classmethod
    def from_dict(cls, value: Any) -> "PlanArchitectureHandoff":
        fields = {"handoff_id", "source_project_id", "idea_handoff_id", "approved_plan_id", "software_plan_id",
            "plan_finalization_id", "frozen_approved_plan", "transition_eligible", "decision", "resulting_project",
            "schema", "schema_version"}
        value = _exact(value, fields, "PLAN architecture handoff")
        if value["schema"] != ARCADEV_PLAN_ARCHITECTURE_HANDOFF_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != ARCADEV_PLAN_ARCHITECTURE_HANDOFF_SCHEMA_VERSION:
            raise ValueError("PLAN architecture handoff schema or version is unsupported.")
        if type(value["transition_eligible"]) is not bool:
            raise ValueError("PLAN architecture handoff eligibility is malformed.")
        approved = ApprovedPlan.from_dict(value["frozen_approved_plan"])
        expected = cls.create(source_project=approved.package.idea_handoff.resulting_project, approved_plan=approved)
        if expected.canonical_dict() != value:
            raise ValueError("PLAN architecture handoff identity, eligibility, decision, binding, or result is forged.")
        return expected

    @classmethod
    def from_json(cls, text: str) -> "PlanArchitectureHandoff":
        if not isinstance(text, str):
            raise ValueError("PLAN architecture handoff must be JSON text.")
        try:
            if len(text.encode("utf-8")) > MAX_PLAN_ARCHITECTURE_HANDOFF_BYTES:
                raise ValueError("PLAN architecture handoff exceeds the safety limit.")
            value = json.loads(text, object_pairs_hook=_unique)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("PLAN architecture handoff is not valid JSON.") from error
        return cls.from_dict(value)

    def canonical_dict(self) -> dict[str, Any]:
        return {"approved_plan_id": self.approved_plan_id, "decision": self.decision.value,
            "frozen_approved_plan": self.frozen_approved_plan.canonical_dict(), "handoff_id": self.handoff_id,
            "idea_handoff_id": self.idea_handoff_id, "plan_finalization_id": self.plan_finalization_id,
            "resulting_project": self.resulting_project.canonical_dict(), "schema": self.schema,
            "schema_version": self.schema_version, "software_plan_id": self.software_plan_id,
            "source_project_id": self.source_project_id, "transition_eligible": self.transition_eligible}

    def canonical_json(self) -> str:
        return _json(self.canonical_dict())


def create_plan_architecture_handoff(*, source_project: ArcaDevProject, approved_plan: ApprovedPlan) -> PlanArchitectureHandoff:
    return PlanArchitectureHandoff.create(source_project=source_project, approved_plan=approved_plan)


def validate_plan_architecture_handoff(candidate: PlanArchitectureHandoff | Mapping[str, Any] | str, *,
                                         source_project: ArcaDevProject | None = None,
                                         approved_plan: ApprovedPlan | None = None) -> PlanArchitectureHandoff:
    if isinstance(candidate, PlanArchitectureHandoff):
        result = PlanArchitectureHandoff.from_dict(candidate.canonical_dict())
    elif isinstance(candidate, str):
        result = PlanArchitectureHandoff.from_json(candidate)
    elif isinstance(candidate, Mapping):
        result = PlanArchitectureHandoff.from_dict(dict(candidate))
    else:
        raise ValueError("PLAN architecture handoff candidate must be a validated value, object, or JSON text.")
    if source_project is not None:
        if source_project.current_build_stage is not BuildStage.PLAN:
            raise ValueError("PLAN architecture handoff replay requires the still-current PLAN project.")
        if source_project.canonical_dict() != result.frozen_approved_plan.package.idea_handoff.resulting_project.canonical_dict():
            raise ValueError("PLAN architecture handoff is for another or stale source project.")
    if approved_plan is not None and approved_plan.approval_id != result.approved_plan_id:
        raise ValueError("PLAN architecture handoff is stale for the supplied approval.")
    return result
