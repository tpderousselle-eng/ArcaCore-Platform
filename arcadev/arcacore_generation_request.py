"""Non-executing, complete-scope translation from approved BACKEND authority.

The v1 translator certifies a deliberately narrow standard-module scope. Other
approved products remain valid authority with explicit compatibility blockers.
No presentation label or caller-supplied support assertion grants a capability.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
import re

from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition, valid_public_identifier, validate_module_definition

from .architecture_specification import Record, _exact, _identity, _json, _parse, plan_source_id
from .backend_approval import ApprovedBackend, validate_approved_backend
from .backend_specification import BackendRole, backend_architecture
from .domain_model_specification import _model_safe as _safe

ARCADEV_ARCACORE_GENERATION_REQUEST_SCHEMA = "arcadev.arcacore_generation_request"
ARCADEV_ARCACORE_GENERATION_REQUEST_SCHEMA_VERSION = 1

# Exact approved product/implementation requirements for the certified v1
# standard-module profile. These are opt-in authority, never inferred defaults.
STANDARD_MODULE_CAPABILITY = "Manage records with standard ArcaCore CRUD"
STANDARD_AUTHORITY = "ArcaCore router principal and read/write scope checks against existing trusted middleware"
STANDARD_TIMESTAMP_AUTHORITY = (
    "ArcaCore manages created_at and updated_at as nullable timezone-aware timestamps "
    "with server time defaults and an update-time hook."
)


class ArcaCoreCapabilityStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    REQUIRES_CERTIFICATION = "REQUIRES_CERTIFICATION"


class ArcaCoreCapability(str, Enum):
    STANDARD_MODULE = "standard_module"
    LOGICAL_STATE = "logical_state"
    AUTHORIZATION = "authorization"
    APPLICATION_OPERATION = "application_operation"
    EXTERNAL_INTEGRATION = "external_integration"
    PUBLISHING = "publishing"
    ISOLATED_WORKER = "isolated_worker"
    APPLICATION_JOB = "application_job"
    STORAGE = "storage"
    IMPLEMENTATION_CHOICE = "implementation_choice"


@dataclass(frozen=True)
class ArcaCoreCapabilityMapping(Record):
    responsibility_id: str
    capability: ArcaCoreCapability
    status: ArcaCoreCapabilityStatus
    public_contracts: tuple[str, ...]
    reason: str
    module_request_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArcaCoreCompatibilityFinding(Record):
    responsibility_id: str
    capability: ArcaCoreCapability
    status: ArcaCoreCapabilityStatus
    reason: str


@dataclass(frozen=True)
class ModuleGenerationRequest(Record):
    module_request_id: str
    entity_id: str
    module_name: str
    field_declarations: tuple[str, ...]
    generator_managed_field_ids: tuple[str, ...]
    source_field_ids: tuple[str, ...]
    source_decision_ids: tuple[str, ...]
    naming_decision_id: str


def module_definition(request):
    """Validate the public declaration grammar without invoking any generator."""
    if type(request) is not ModuleGenerationRequest or not valid_public_identifier(request.module_name):
        raise ValueError("Unsupported public module identifier.")
    if type(request.field_declarations) is not tuple or not 1 <= len(request.field_declarations) <= 128:
        raise ValueError("Module declarations must be bounded.")
    # v1 emits only scalar, nullable, primary-key and uniqueness declarations.
    # Never accept executable expressions, paths, defaults, or arbitrary grammar.
    for value in request.field_declarations:
        if type(value) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,127}:(?:str|text|int|bool|date|datetime|uuid|json)(?::(?:pk|nullable|unique))*", value):
            raise ValueError("Uncertified module declaration.")
    name = request.module_name
    result = ModuleDefinition(name, name.capitalize(), name.lower(), name.lower() + "s", parse_fields(name, list(request.field_declarations)))
    validate_module_definition(result)
    return result


def _physical_name(value):
    # Only ordinary labels can be named. Never sanitize a path/command into a
    # seemingly safe identifier, or allow names to decide semantic identity.
    if type(value) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_ ]{0,127}", value):
        raise ValueError("Physical naming rejects paths, shell fragments and unsupported identifiers.")
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    value = re.sub(r"[ _]+", "_", value).lower()
    if not valid_public_identifier(value):
        raise ValueError("Physical name is not a public identifier.")
    return value


def _scope(approved):
    package = backend_architecture(approved.package.models_backend_handoff)
    plan = package.plan_handoff.frozen_approved_plan.package.plan_finalization.original_plan
    capabilities = {plan_source_id(item): item for item in plan.in_scope_capabilities}
    standard = {key for key, item in capabilities.items() if item.value == STANDARD_MODULE_CAPABILITY}
    timestamps = any(item.value == STANDARD_TIMESTAMP_AUTHORITY for item in plan.planning_constraints)
    storage = [a for a in package.original_architecture.aspects if a.area.value == "storage"]
    postgres = bool(storage) and all(a.technology is not None and a.technology.value == "PostgreSQL" for a in storage)
    intake = package.plan_handoff.frozen_approved_plan.package.idea_handoff.snapshot.intake
    authentication = {v.value for v in intake.authentication_requirements} == {STANDARD_AUTHORITY}
    auth_capabilities = {key for key, item in capabilities.items() if item.value == "Authentication"}
    return standard, timestamps, postgres, plan, capabilities, authentication, auth_capabilities


def _translate_entity(approved, entity, timestamps):
    choices = approved.package.resolved_backend.accepted_choices
    naming = [c for c in choices if c.claim.slot == "persistence_mapping" and entity.entity_id in c.claim.model_source_ids
        and c.claim.values == ("snake_case", "unfixed_physical_names_only", "preserve_approved_state")]
    if len(naming) != 1:
        return None, "A unique accepted persistence-mapping decision is required."
    name = _physical_name(entity.name)
    model = approved.package.original_backend.resolved_model
    fixed = {f.name: f for f in entity.approved_fields}
    if any(c.claim.slot not in {"uniqueness", "lookup", "relationship", "principal_reference"}
        or (c.claim.slot == "uniqueness" and c.claim.values != ("identity_only",))
        or (c.claim.slot == "lookup" and c.claim.values != ("identity",))
        or (c.claim.slot == "relationship" and c.claim.values != ("independent",))
        or (c.claim.slot == "principal_reference" and (c.claim.values != ("external_principal_id",)
            or "external_principal_id" not in fixed or fixed["external_principal_id"].logical_type.value != "string"
            or fixed["external_principal_id"].classification.value != "external_identifier")) for c in entity.choices):
        return None, "Accepted logical choices need certified physical representation; no fields may be invented."
    if (model.relationships or model.constraints or model.access_requirements or model.value_domains or entity.lifecycle_domain_ids):
        return None, "Approved relationship, constraint, access or value-domain translation requires certification."
    if not timestamps or not {"created_at", "updated_at"} <= fixed.keys():
        return None, "The public generator adds timestamps; their fields and implementation semantics require explicit authority."
    if len(entity.identity_field_ids) != 1 or not entity.approved_fields:
        return None, "An explicitly named, typed single identity field is required."
    managed = []
    declarations = []
    types = {"string": "str", "text": "text", "integer": "int", "boolean": "bool", "date": "date", "datetime": "datetime", "uuid": "uuid", "json": "json"}
    for f in entity.approved_fields:
        physical = _physical_name(f.name)
        if f.collection or f.value_domain_id is not None or f.default_json is not None or f.logical_type.value not in types:
            return None, "This approved field needs a certified collection, domain, default or type translator."
        if f.name in {"created_at", "updated_at"}:
            if f.logical_type.value != "datetime" or f.required or f.unique or f.mutable is not (f.name == "updated_at"):
                return None, "Timestamp authority differs from the public generator-managed field contract."
            managed.append(f.field_id)
            continue
        primary = f.field_id in entity.identity_field_ids
        if primary and f.logical_type.value in {"uuid", "integer"}:
            return None, "Generator-managed primary-key defaults require additional explicit default certification."
        if not primary and f.mutable is not True:
            return None, "Non-identity field mutability is not representable by standard CRUD."
        declaration = physical + ":" + types[f.logical_type.value]
        if primary:
            declaration += ":pk"
        elif not f.required:
            declaration += ":nullable"
        if f.unique and not primary:
            declaration += ":unique"
        declarations.append(declaration)
    if len({d.split(":")[0] for d in declarations}) != len(declarations):
        raise ValueError("Physical field names collide.")
    result = ModuleGenerationRequest("", entity.entity_id, name, tuple(sorted(declarations)), tuple(sorted(managed)),
        tuple(sorted(f.field_id for f in entity.approved_fields)), tuple(sorted({c.decision_id for c in entity.choices}
            | {sid for f in entity.approved_fields for sid in f.evidence.source_requirements})), naming[0].decision_id)
    module_definition(result)
    body = result.canonical_dict(); body.pop("module_request_id")
    return replace(result, module_request_id=_identity("module_generation_request", body)), "All approved fields and bounded choices have certified representation."


@dataclass(frozen=True)
class ApplicationManifestPlan(Record):
    requested_module_ids: tuple[str, ...]
    runtime_requirements: tuple[str, ...]
    environment_requirement_names: tuple[str, ...]
    pending_authority: tuple[str, ...]


@dataclass(frozen=True)
class ArcaCoreGenerationRequest(Record):
    request_id: str
    approved_backend: ApprovedBackend
    module_requests: tuple[ModuleGenerationRequest, ...]
    capability_mappings: tuple[ArcaCoreCapabilityMapping, ...]
    blocking_findings: tuple[ArcaCoreCompatibilityFinding, ...]
    eligible_for_generation: bool
    application_manifest_plan: ApplicationManifestPlan
    schema: str = ARCADEV_ARCACORE_GENERATION_REQUEST_SCHEMA
    schema_version: int = ARCADEV_ARCACORE_GENERATION_REQUEST_SCHEMA_VERSION

    @property
    def supported_mappings(self):
        return tuple(m for m in self.capability_mappings if m.status is ArcaCoreCapabilityStatus.SUPPORTED)

    @property
    def unsupported_mappings(self):
        return tuple(m for m in self.capability_mappings if m.status is ArcaCoreCapabilityStatus.UNSUPPORTED)

    @property
    def required_certification_mappings(self):
        return tuple(m for m in self.capability_mappings if m.status is ArcaCoreCapabilityStatus.REQUIRES_CERTIFICATION)

    @classmethod
    def create(cls, approved_backend, **current_authority):
        approved = validate_approved_backend(approved_backend, **current_authority)
        if not approved.approved:
            raise ValueError("Generation requires explicit approved backend authority.")
        return cls._build(approved)

    @classmethod
    def _build(cls, approved):
        spec = approved.package.original_backend
        standard, timestamps, postgres, frozen_plan, capabilities, authentication, auth_capabilities = _scope(approved)
        mappings, modules = [], []
        S, U, R = ArcaCoreCapabilityStatus
        C = ArcaCoreCapability
        def mapping(identity, capability, status, reason, contracts, requests=()):
            mappings.append(ArcaCoreCapabilityMapping(identity, capability, status, contracts, reason, tuple(sorted(requests))))
        for entity in spec.resolved_model.entities:
            module, reason = _translate_entity(approved, entity, timestamps)
            if module:
                modules.append(module)
            mapping(entity.entity_id, C.LOGICAL_STATE, S if module else R, reason,
                ("tools.core.field_parser.parse_fields", "tools.core.module_definition.validate_module_definition"),
                (module.module_request_id,) if module else ())
        by_entity = {m.entity_id: m.module_request_id for m in modules}
        if len({m.module_name for m in modules}) != len(modules):
            raise ValueError("Physical module names collide.")
        for binding in spec.data_bindings:
            identity = by_entity.get(binding.entity_id)
            mapping(binding.binding_id, C.STANDARD_MODULE, S if identity else R,
                "Exact approved data binding is representable." if identity else "Bound logical state requires certification.",
                ("tools.generate.generate_module",), (identity,) if identity else ())
        supported_components = set()
        for component in spec.components:
            ids = tuple(by_entity[eid] for eid in component.model_entity_ids if eid in by_entity)
            standard_owner = bool(component.owned_capabilities) and set(component.owned_capabilities) <= standard
            supported = ((standard_owner and authentication and len(ids) == len(component.model_entity_ids) and bool(ids)
                and component.implementation_role in {BackendRole.APPLICATION_SERVICE, BackendRole.API, BackendRole.DOMAIN_SERVICE})
                or (component.implementation_role is BackendRole.PERSISTENCE and not component.owned_capabilities and postgres)
                or (component.implementation_role is BackendRole.IDENTITY_BOUNDARY and authentication
                    and set(component.owned_capabilities) <= auth_capabilities))
            if supported:
                supported_components.add(component.component_id)
                mapping(component.component_id, C.AUTHORIZATION if component.implementation_role is BackendRole.IDENTITY_BOUNDARY else C.STANDARD_MODULE,
                    S, "Explicit standard CRUD, PostgreSQL persistence or generated principal/scope checks are supported.", ("tools.generate.generate_module",), ids)
            else:
                cap, status, contract = {
                    BackendRole.INTEGRATION_ADAPTER: (C.EXTERNAL_INTEGRATION, U, "tools.generate.generate_module"),
                    BackendRole.PUBLISHING_ADAPTER: (C.PUBLISHING, U, "tools.generate.generate_module"),
                    BackendRole.EXTERNAL_WORKER: (C.ISOLATED_WORKER, U, "tools.jobs.JobExecutor"),
                    BackendRole.BACKGROUND_JOB: (C.APPLICATION_JOB, U, "tools.jobs.JobExecutor"),
                    BackendRole.IDENTITY_BOUNDARY: (C.AUTHORIZATION, R, "tools.authorization.PolicyContract"),
                    BackendRole.STORAGE: (C.STORAGE, U, "tools.storage"),
                }.get(component.implementation_role, (C.APPLICATION_OPERATION, R, "tools.generate.generate_module"))
                if any(capabilities[c].value == "publishing workflow" for c in component.owned_capabilities):
                    cap, status = C.PUBLISHING, U
                mapping(component.component_id, cap, status,
                    "No certified public generator produces the approved responsibility: " + component.name + ".", (contract,))
        for operation in spec.operations:
            supported = operation.capability_id in (standard | auth_capabilities) and operation.component_id in supported_components and authentication
            mapping(operation.operation_id, C.APPLICATION_OPERATION, S if supported else R,
                "Explicit standard module operation or principal/scope check maps to the generated service/router." if supported else "Logical workflow or integration operation is not generic CRUD; handler certification is required.",
                ("tools.generate.generate_module",))
        for policy in spec.policies:
            supported = ((policy.kind == "storage" and postgres) or (policy.kind == "authorization" and authentication)) and set(policy.component_ids) <= supported_components
            cap = {"authorization": C.AUTHORIZATION, "background": C.APPLICATION_JOB, "integration": C.EXTERNAL_INTEGRATION, "storage": C.STORAGE}[policy.kind]
            mapping(policy.policy_id, cap, S if supported else (U if policy.kind in {"background", "integration"} else R),
                "Approved standard persistence or principal/scope boundary is representable." if supported else "Infrastructure primitives do not certify application-specific boundary generation.",
                ("tools.generate.generate_module", "tools.authorization.PolicyContract", "tools.jobs.JobExecutor"))
        for choice in approved.package.resolved_backend.accepted_choices:
            supported = choice.claim.slot in {"persistence_mapping", "transport", "implementation_technology"}
            # A certification precondition is recorded, never a self-certification
            # of the other mappings. Unsupported choices remain explicit blockers.
            mapping(choice.decision_id, C.IMPLEMENTATION_CHOICE, S if supported else R,
                "Bounded naming, transport or certification precondition is preserved." if supported else "Accepted implementation choice requires a certified application translator.",
                ("tools.generate.generate_module",))
        represented_sources = {sid for module in modules for sid in module.source_decision_ids}
        # Approved planning decisions remain implementation authority through the
        # entire frozen chain. Retaining their bytes is not a translation: each
        # needs an explicit capability mapping before execution is authorized.
        for decision in backend_architecture(approved.package.models_backend_handoff).plan_handoff.frozen_approved_plan.package.plan_finalization.decisions:
            mapping(decision.decision_id, C.IMPLEMENTATION_CHOICE, R,
                "Accepted PLAN implementation decision requires certified generation representation.",
                ("tools.generate.generate_module", "tools.application_manifest.ApplicationManifest"))
        architecture_decisions = {d.decision_id: d for d in backend_architecture(
            approved.package.models_backend_handoff).architecture_finalization.decisions}
        for fact in spec.approved_architecture_decisions:
            identity = fact.source_ids[0]
            # Explicit field declarations are checked against the logical model.
            # This exact local topology is planning authority, not a claim that
            # generation starts or validates an application runtime.
            decision = architecture_decisions[identity]
            supported = identity in represented_sources or (bool(standard) and decision.area.value == "deployment"
                and decision.accepted_values == ("Local ArcaCore module runtime",))
            mapping(identity, C.IMPLEMENTATION_CHOICE, S if supported else R,
                "Exact declared fields or deferred local runtime planning are preserved." if supported else
                "Frozen architecture implementation choice has no certified complete-generation mapping.",
                ("tools.generate.generate_module", "tools.application_manifest.ApplicationManifest"))
        known_constraints = {"Local API", STANDARD_AUTHORITY, "No integrations", "Local", "PostgreSQL", STANDARD_TIMESTAMP_AUTHORITY}
        for item in frozen_plan.planning_constraints:
            mapping(plan_source_id(item), C.IMPLEMENTATION_CHOICE, S if item.value in known_constraints else R,
                "Explicit standard-module constraint is preserved." if item.value in known_constraints else
                "Frozen implementation constraint needs certification for this generation scope.",
                ("tools.generate.generate_module", "tools.application_manifest.RuntimeContract"))
        # Every required entity, binding, component, operation, policy and accepted
        # decision is regenerated here on load: omission cannot enable eligibility.
        mappings = tuple(sorted(mappings, key=lambda m: m.responsibility_id))
        if len({m.responsibility_id for m in mappings}) != len(mappings):
            raise ValueError("Duplicate responsibility mappings.")
        blockers = tuple(ArcaCoreCompatibilityFinding(m.responsibility_id, m.capability, m.status, m.reason) for m in mappings if m.status is not S)
        modules = tuple(sorted(modules, key=lambda m: m.entity_id))
        plan = ApplicationManifestPlan(tuple(m.module_request_id for m in modules),
            ("fastapi", "postgresql", "pydantic", "python>=3.11", "sqlalchemy", "trusted_principal_scope_middleware"), (),
            ("observed_generation_manifest", "accepted_schema_revision", "application_manifest", "runtime_validation"))
        result = cls("", approved, modules, mappings, blockers, bool(modules) and not blockers, plan)
        body = result.canonical_dict(); body.pop("request_id")
        result = replace(result, request_id=_identity("arcacore_generation_request", body))
        _safe(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_ARCACORE_GENERATION_REQUEST_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported generation request schema/version.")
        approved = validate_approved_backend(value["approved_backend"])
        if not approved.approved:
            raise ValueError("Generation requires explicit approval.")
        result = cls._build(approved)
        if result.canonical_json() != _json(value):
            raise ValueError("Forged generation request, capability support, scope, declarations or eligibility.")
        return result

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


def validate_arcacore_generation_request(candidate, *, approved_backend=None, **current_authority):
    if type(candidate) is ArcaCoreGenerationRequest:
        candidate = candidate.canonical_dict()
    result = ArcaCoreGenerationRequest.from_json(candidate) if type(candidate) is str else ArcaCoreGenerationRequest.from_dict(candidate)
    expected = validate_approved_backend(result.approved_backend, **current_authority)
    if approved_backend is not None and validate_approved_backend(approved_backend).canonical_json() != expected.canonical_json():
        raise ValueError("Generation request is stale against current approved backend content.")
    return result
