"""Controlled ARCHITECTURE to MODELS transition; no model or code generation."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum

from .architecture_approval import ApprovedArchitecture, validate_approved_architecture
from .architecture_clarification import ArchitectureFinalization
from .architecture_specification import ArchitectureSpecification, Record, _exact, _identity, _json, _parse, _safe
from .plan_architecture_handoff import PlanArchitectureHandoff
from .plan_approval import ApprovalDecision
from .project import ArcaDevProject, BuildStage, ProjectStatus

ARCADEV_ARCHITECTURE_MODELS_HANDOFF_SCHEMA = "arcadev.architecture_models_handoff"
ARCADEV_ARCHITECTURE_MODELS_HANDOFF_SCHEMA_VERSION = 1


class ModelsTransitionDecision(str, Enum):
    TRANSITIONED = "transitioned"


@dataclass(frozen=True)
class ArchitectureModelsHandoff(Record):
    handoff_id: str
    source_project_id: str
    plan_handoff_id: str
    approved_architecture_id: str
    architecture_id: str
    architecture_finalization_id: str
    frozen_approved_architecture: ApprovedArchitecture
    transition_eligible: bool
    decision: ModelsTransitionDecision
    resulting_project: ArcaDevProject
    schema: str = ARCADEV_ARCHITECTURE_MODELS_HANDOFF_SCHEMA
    schema_version: int = ARCADEV_ARCHITECTURE_MODELS_HANDOFF_SCHEMA_VERSION

    @classmethod
    def create(cls, *, source_project, approved_architecture, handoff=None, architecture=None, finalization=None):
        if type(source_project) is not ArcaDevProject or type(approved_architecture) is not ApprovedArchitecture:
            raise ValueError("ARCHITECTURE models handoff requires a current project and approved architecture.")
        approved = validate_approved_architecture(approved_architecture, source_project=source_project,
            handoff=handoff, architecture=architecture, finalization=finalization)
        return cls._build(approved)

    @classmethod
    def _build(cls, approved):
        """Apply the gate only to an approval validated in this public call."""
        source = approved.package.plan_handoff.resulting_project
        if source.project_status is not ProjectStatus.IN_PROGRESS or source.current_build_stage is not BuildStage.ARCHITECTURE:
            raise ValueError("MODELS transition requires an IN_PROGRESS source at ARCHITECTURE.")
        if not approved.approved or not approved.approval_eligible or approved.decision is not ApprovalDecision.APPROVED:
            raise ValueError("MODELS transition requires explicit architecture approval.")
        if not approved.effective_ready_for_approval or not approved.package.consistency.consistent:
            raise ValueError("MODELS transition requires effective readiness and passing consistency.")
        finalization = approved.package.architecture_finalization
        if finalization.unresolved_questions or finalization.conflicts:
            raise ValueError("MODELS transition requires no unresolved architecture questions or active conflicts.")
        resulting = replace(source, project_status=ProjectStatus.IN_PROGRESS, current_build_stage=BuildStage.MODELS)
        result = cls("", approved.source_project_id, approved.plan_handoff_id, approved.approval_id,
                     approved.architecture_id, approved.architecture_finalization_id, approved,
                     True, ModelsTransitionDecision.TRANSITIONED, resulting)
        body = result.canonical_dict()
        body.pop("handoff_id")
        result = replace(result, handoff_id=_identity("architecture_models_handoff", body))
        _safe(result.canonical_dict())
        return result

    def canonical_dict(self):
        result = super().canonical_dict()
        result["resulting_project"] = self.resulting_project.canonical_dict()
        return result

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_ARCHITECTURE_MODELS_HANDOFF_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported architecture models handoff schema/version.")
        approved = ApprovedArchitecture.from_dict(value["frozen_approved_architecture"])
        result = cls._build(approved)
        if _json(result.canonical_dict()) != _json(value):
            raise ValueError("Architecture models handoff identity, binding, eligibility, decision or resulting project is forged.")
        return result

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


def create_architecture_models_handoff(*, source_project, approved_architecture, handoff=None, architecture=None, finalization=None):
    return ArchitectureModelsHandoff.create(source_project=source_project, approved_architecture=approved_architecture,
        handoff=handoff, architecture=architecture, finalization=finalization)


def validate_architecture_models_handoff(candidate, *, source_project=None, approved_architecture=None,
                                         handoff=None, architecture=None, finalization=None):
    if type(candidate) is ArchitectureModelsHandoff:
        candidate = candidate.canonical_dict()
    result = ArchitectureModelsHandoff.from_json(candidate) if type(candidate) is str else ArchitectureModelsHandoff.from_dict(candidate)
    frozen = result.frozen_approved_architecture
    # The envelope has already replay-validated this entire package. Current
    # references must match its complete canonical content, not only its IDs.
    for supplied, expected, kind in (
        (source_project, frozen.package.plan_handoff.resulting_project, ArcaDevProject),
        (approved_architecture, frozen, ApprovedArchitecture),
        (handoff, frozen.package.plan_handoff, PlanArchitectureHandoff),
        (architecture, frozen.package.original_architecture, ArchitectureSpecification),
        (finalization, frozen.package.architecture_finalization, ArchitectureFinalization),
    ):
        if supplied is not None and (type(supplied) is not kind or _json(supplied.canonical_dict()) != _json(expected.canonical_dict())):
            raise ValueError("Architecture models handoff is stale or mismatched against current source authority.")
    return result
