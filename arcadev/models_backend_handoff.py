"""Controlled MODELS to BACKEND lifecycle gate; no implementation generation."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum

from .architecture_models_handoff import ArchitectureModelsHandoff
from .architecture_specification import Record, _exact, _identity, _json, _parse
from .domain_model_specification import DomainModelSpecification, _model_safe as _safe
from .model_approval import ApprovedDomainModel, validate_approved_domain_model
from .model_clarification import ModelFinalization
from .plan_approval import ApprovalDecision
from .project import ArcaDevProject, BuildStage, ProjectStatus

ARCADEV_MODELS_BACKEND_HANDOFF_SCHEMA = "arcadev.models_backend_handoff"
ARCADEV_MODELS_BACKEND_HANDOFF_SCHEMA_VERSION = 1


class BackendTransitionDecision(str, Enum):
    TRANSITIONED = "transitioned"


@dataclass(frozen=True)
class ModelsBackendHandoff(Record):
    handoff_id: str
    source_project_id: str
    plan_handoff_id: str
    approved_architecture_id: str
    architecture_id: str
    architecture_finalization_id: str
    architecture_handoff_id: str
    model_id: str
    model_finalization_id: str
    approved_domain_model_id: str
    frozen_approved_domain_model: ApprovedDomainModel
    transition_eligible: bool
    decision: BackendTransitionDecision
    resulting_project: ArcaDevProject
    schema: str = ARCADEV_MODELS_BACKEND_HANDOFF_SCHEMA
    schema_version: int = ARCADEV_MODELS_BACKEND_HANDOFF_SCHEMA_VERSION

    @classmethod
    def create(cls, *, source_project, approved_domain_model, handoff=None, model=None, finalization=None):
        if type(source_project) is not ArcaDevProject or type(approved_domain_model) is not ApprovedDomainModel:
            raise ValueError("MODELS backend handoff requires a current project and an approved domain model.")
        approved = validate_approved_domain_model(approved_domain_model, source_project=source_project,
            handoff=handoff, model=model, finalization=finalization)
        return cls._build(approved)

    @classmethod
    def _build(cls, approved):
        """Apply the lifecycle gate only to authority validated in this public call."""
        source = approved.package.architecture_handoff.resulting_project
        if source.project_status is not ProjectStatus.IN_PROGRESS or source.current_build_stage is not BuildStage.MODELS:
            raise ValueError("BACKEND transition requires an IN_PROGRESS source at MODELS.")
        if not approved.approved or not approved.approval_eligible or approved.decision is not ApprovalDecision.APPROVED:
            raise ValueError("BACKEND transition requires explicit domain model approval.")
        consistency = approved.package.consistency
        if not approved.effective_ready_for_approval or not consistency.consistent or consistency.blocking_findings:
            raise ValueError("BACKEND transition requires effective readiness and zero consistency blockers.")
        finalization = approved.package.model_finalization
        if finalization.unresolved_questions or finalization.conflicts:
            raise ValueError("BACKEND transition requires no unresolved model questions or active conflicts.")
        resulting = replace(source, project_status=ProjectStatus.IN_PROGRESS, current_build_stage=BuildStage.BACKEND)
        result = cls(
            handoff_id="", source_project_id=approved.source_project_id,
            plan_handoff_id=approved.plan_handoff_id, approved_architecture_id=approved.approved_architecture_id,
            architecture_id=approved.architecture_id, architecture_finalization_id=approved.architecture_finalization_id,
            architecture_handoff_id=approved.architecture_handoff_id, model_id=approved.model_id,
            model_finalization_id=approved.model_finalization_id, approved_domain_model_id=approved.approval_id,
            frozen_approved_domain_model=approved, transition_eligible=True,
            decision=BackendTransitionDecision.TRANSITIONED, resulting_project=resulting,
        )
        body = result.canonical_dict()
        body.pop("handoff_id")
        result = replace(result, handoff_id=_identity("models_backend_handoff", body))
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
        if value["schema"] != ARCADEV_MODELS_BACKEND_HANDOFF_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported models backend handoff schema/version.")
        approved = ApprovedDomainModel.from_dict(value["frozen_approved_domain_model"])
        result = cls._build(approved)
        if _json(result.canonical_dict()) != _json(value):
            raise ValueError("Models backend handoff identity, binding, eligibility, decision or resulting project is forged.")
        return result

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


def create_models_backend_handoff(*, source_project, approved_domain_model, handoff=None, model=None, finalization=None):
    return ModelsBackendHandoff.create(source_project=source_project, approved_domain_model=approved_domain_model,
        handoff=handoff, model=model, finalization=finalization)


def validate_models_backend_handoff(candidate, *, source_project=None, approved_domain_model=None,
                                   handoff=None, model=None, finalization=None):
    if type(candidate) is ModelsBackendHandoff:
        candidate = candidate.canonical_dict()
    result = ModelsBackendHandoff.from_json(candidate) if type(candidate) is str else ModelsBackendHandoff.from_dict(candidate)
    frozen = result.frozen_approved_domain_model
    # The envelope has reconstructed all embedded authority. External freshness
    # requires caller-supplied references matching complete canonical content.
    for supplied, expected, kind in (
        (source_project, frozen.package.architecture_handoff.resulting_project, ArcaDevProject),
        (approved_domain_model, frozen, ApprovedDomainModel),
        (handoff, frozen.package.architecture_handoff, ArchitectureModelsHandoff),
        (model, frozen.package.original_model, DomainModelSpecification),
        (finalization, frozen.package.model_finalization, ModelFinalization),
    ):
        if supplied is not None and (type(supplied) is not kind or _json(supplied.canonical_dict()) != _json(expected.canonical_dict())):
            raise ValueError("Models backend handoff is stale or mismatched against current source authority.")
    return result
