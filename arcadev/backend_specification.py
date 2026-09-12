"""Immutable BACKEND authority. No transport, SQL, or application generation.

Material facts are exact frozen records or bounded reference-preserving
derivations. Presentation names never grant capabilities or change ownership.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
from functools import lru_cache

from .architecture_specification import Record, _exact, _identity, _json, _parse, _strings, _text
from .domain_model_specification import _model_safe as _safe, _norm
from .model_approval import ResolvedLogicalModel
from .models_backend_handoff import ModelsBackendHandoff, validate_models_backend_handoff
from .project import BuildStage

ARCADEV_BACKEND_SPECIFICATION_SCHEMA = "arcadev.backend_specification"
ARCADEV_BACKEND_SPECIFICATION_SCHEMA_VERSION = 1


class BackendRole(str, Enum):
    APPLICATION_SERVICE = "application_service"
    PERSISTENCE = "persistence"
    API = "api"
    INTEGRATION_ADAPTER = "integration_adapter"
    IDENTITY_BOUNDARY = "identity_boundary"
    BACKGROUND_JOB = "background_job"
    STORAGE = "storage"
    ORCHESTRATION = "orchestration"
    DOMAIN_SERVICE = "domain_service"
    EXTERNAL_WORKER = "external_worker"
    PUBLISHING_ADAPTER = "publishing_adapter"


class BackendArea(str, Enum):
    PERSISTENCE_MAPPING = "persistence_mapping"
    API_BOUNDARY = "api_boundary"
    AUTHORIZATION = "authorization"
    TRANSACTION = "transaction"
    ASYNC_EXECUTION = "async_execution"
    EXTERNAL_INTEGRATION = "external_integration"
    STORAGE = "storage"
    FAILURE_SEMANTICS = "failure_semantics"
    IDEMPOTENCY = "idempotency"
    CONCURRENCY = "concurrency"
    IMPLEMENTATION_TECHNOLOGY = "implementation_technology"


class BackendFailure(str, Enum):
    VALIDATION_ERROR = "validation_error"
    AUTHORIZATION_ERROR = "authorization_error"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    DEPENDENCY_FAILURE = "dependency_failure"
    EXTERNAL_INTEGRATION_FAILURE = "external_integration_failure"
    TRANSIENT_EXECUTION_FAILURE = "transient_execution_failure"


@lru_cache(maxsize=8)
def _certified_backend_handoff(text):
    return validate_models_backend_handoff(text)


def backend_handoff(handoff):
    if type(handoff) is not ModelsBackendHandoff:
        raise ValueError("BACKEND requires a certified ModelsBackendHandoff.")
    return _certified_backend_handoff(handoff.canonical_json())


def backend_architecture(handoff):
    return handoff.frozen_approved_domain_model.package.architecture_handoff.frozen_approved_architecture.package


def backend_sources(handoff):
    """Complete source payloads, including accepted choices, not paraphrased prose."""
    package = backend_architecture(handoff)
    architecture = package.original_architecture
    result = {architecture.architecture_id: (architecture.objective.value, "approved_architecture")}
    for collection, key in ((architecture.components, "component_id"), (architecture.aspects, "aspect_id"),
                            (architecture.interfaces, "connection_id")):
        for item in collection:
            result[getattr(item, key)] = (_json(item.canonical_dict()).strip(), "approved_architecture")
    for decision in package.architecture_finalization.decisions:
        result[decision.decision_id] = (_json(decision.canonical_dict()).strip(), "architecture_decision")
    model = handoff.frozen_approved_domain_model.package.resolved_model
    for entity in model.entities:
        result[entity.entity_id] = (_json(entity.canonical_dict()).strip(), "approved_domain_model")
    for decision in handoff.frozen_approved_domain_model.package.model_finalization.decisions:
        result[decision.decision_id] = (_json(decision.canonical_dict()).strip(), "model_decision")
    return result


DERIVATIONS = frozenset({"backend_objective", "capability_implementation", "persistence_binding",
    "operation_from_requirement", "authorization_boundary", "integration_boundary", "workflow_operation",
    "background_work_unit", "transaction_requirement", "failure_requirement", "storage_boundary"})


@dataclass(frozen=True)
class BackendFact(Record):
    value: str
    source_ids: tuple[str, ...]
    provenance: str
    derivation: str | None = None

    @classmethod
    def create(cls, *, handoff, source_ids, derivation=None):
        sources = _strings(source_ids, required=True)
        catalog = backend_sources(handoff)
        if not set(sources) <= catalog.keys():
            raise ValueError("Backend fact has nonexistent frozen sources.")
        if derivation is not None and derivation not in DERIVATIONS:
            raise ValueError("Unsupported backend derivation.")
        if derivation is None and len(sources) != 1:
            raise ValueError("An exact frozen fact requires one source.")
        # A derivation means preservation of these exact payloads. It does not
        # authorize a new operation, physical field, policy, or technology.
        value = " | ".join(catalog[s][0] for s in sources)
        result = cls(value, sources, "deterministic_backend_derivation" if derivation else catalog[sources[0]][1], derivation)
        _safe(result.canonical_dict())
        return result


def backend_element_id(kind, body):
    return _identity("backend_" + kind, body)


@dataclass(frozen=True)
class BackendComponent(Record):
    component_id: str
    name: str
    responsibility: BackendFact
    architecture_source_ids: tuple[str, ...]
    owned_capabilities: tuple[str, ...]
    model_entity_ids: tuple[str, ...]
    implementation_role: BackendRole
    dependencies: tuple[str, ...]
    exposed_interfaces: tuple[str, ...]


@dataclass(frozen=True)
class BackendDataBinding(Record):
    binding_id: str
    entity_id: str
    component_id: str
    authority: BackendFact
    # Exact resolved entity holds fields, identity, lifecycle, relationships,
    # retention, external references and accepted ModelDecision provenance.
    # Cross-entity approved domains/relationships/accesses live in resolved_model.


@dataclass(frozen=True)
class BackendOperation(Record):
    operation_id: str
    name: str
    component_id: str
    capability_id: str
    kind: str
    input_entity_ids: tuple[str, ...]
    output_entity_ids: tuple[str, ...]
    authorization_ids: tuple[str, ...]
    transaction_ids: tuple[str, ...]
    failure_ids: tuple[str, ...]
    authority: BackendFact


@dataclass(frozen=True)
class BackendPolicy(Record):
    """A frozen logical boundary; optional semantics require exact frozen facts.

Background records are work units: their identity, owners, input authority,
    resulting logical state and external boundary are explicit references. None in
    retry/idempotency/transaction means no additional structured backend choice;
    the exact frozen facts and architecture decisions still govern.
"""
    policy_id: str
    kind: str
    component_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    model_entity_ids: tuple[str, ...]
    authority: BackendFact
    input_authority_ids: tuple[str, ...] = ()
    resulting_entity_ids: tuple[str, ...] = ()
    external_boundary_ids: tuple[str, ...] = ()
    retry_semantics: BackendFact | None = None
    idempotency_semantics: BackendFact | None = None
    transaction_semantics: BackendFact | None = None
    failure_classes: tuple[BackendFailure, ...] = ()


@dataclass(frozen=True)
class BackendQuestion(Record):
    question_id: str
    question: str
    blocking: bool
    area: BackendArea
    architecture_source_ids: tuple[str, ...]
    model_source_ids: tuple[str, ...]
    component_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]

    @classmethod
    def create(cls, *, handoff, question, blocking, area, architecture_source_ids,
               model_source_ids=(), component_ids=(), operation_ids=()):
        if type(blocking) is not bool:
            raise ValueError("Backend blocking flag must be boolean.")
        result = cls("", _text(question, maximum=2000), blocking, BackendArea(area),
            _strings(architecture_source_ids, required=True), _strings(model_source_ids),
            _strings(component_ids), _strings(operation_ids))
        catalog = backend_sources(handoff)
        for ids, origins in ((result.architecture_source_ids, {"approved_architecture", "architecture_decision"}),
                             (result.model_source_ids, {"approved_domain_model", "model_decision"})):
            if any(s not in catalog or catalog[s][1] not in origins for s in ids):
                raise ValueError("Backend question has invalid architecture/model sources.")
        result = replace(result, question_id=backend_question_id(result))
        _safe(result.canonical_dict())
        return result


def backend_question_id(question):
    body = question.canonical_dict()
    body.pop("question_id")
    return backend_element_id("question", body)


@dataclass(frozen=True)
class BackendReadiness(Record):
    structurally_valid: bool
    ready_for_approval: bool
    blocking_reasons: tuple[str, ...]


ROLE_CATEGORIES = {
    "application": {BackendRole.APPLICATION_SERVICE, BackendRole.API, BackendRole.ORCHESTRATION},
    "service": {BackendRole.APPLICATION_SERVICE, BackendRole.API, BackendRole.ORCHESTRATION,
                BackendRole.DOMAIN_SERVICE, BackendRole.PUBLISHING_ADAPTER},
    "adapter": {BackendRole.INTEGRATION_ADAPTER}, "identity": {BackendRole.IDENTITY_BOUNDARY},
    "worker": {BackendRole.EXTERNAL_WORKER, BackendRole.BACKGROUND_JOB},
    "storage": {BackendRole.PERSISTENCE, BackendRole.STORAGE},
}


def backend_owners(handoff):
    return {c.component_id: c for c in backend_architecture(handoff).original_architecture.components
            if c.category in ROLE_CATEGORIES and (c.category != "application" or c.owned_capabilities)}


def backend_operation_entities(handoff, source, capability):
    model = handoff.frozen_approved_domain_model.package.resolved_model
    decisions = {d.decision_id: d for d in handoff.frozen_approved_domain_model.package.model_finalization.decisions}
    owns_state = any(capability in e.owned_capabilities for e in model.entities)
    # A field-choice question can cite other owners as review context. Only a
    # capability without its own persisted state consumes the accepted outcome
    # placement; that context must not grant unrelated operations extra state.
    return tuple(sorted(e.entity_id for e in model.entities if capability in e.owned_capabilities or
        (not owns_state and any(c.claim.slot == "field" and
         source in decisions[c.decision_id].architecture_source_requirements for c in e.choices))))


def backend_policy_entities(handoff, aspect, kind, components):
    model = handoff.frozen_approved_domain_model.package.resolved_model
    if kind == "authorization":
        return tuple(sorted(e.entity_id for e in model.entities))
    sources = set(aspect.component_ids)
    # Background input/result state belongs to callers of the isolated worker.
    if kind == "background":
        sources.update(edge.source for edge in backend_architecture(handoff).original_architecture.interfaces
                       if edge.destination in aspect.component_ids)
    return tuple(sorted({eid for c in components if sources & set(c.architecture_source_ids) for eid in c.model_entity_ids}))


def _fact(raw, handoff):
    if type(raw) is BackendFact:
        raw = raw.canonical_dict()
    _exact(raw, (f.name for f in fields(BackendFact)))
    result = BackendFact.create(handoff=handoff, source_ids=raw["source_ids"], derivation=raw["derivation"])
    if _json(raw) != result.canonical_json():
        raise ValueError("Backend fact changes frozen authority or forges provenance.")
    return result


def _records(values, cls, handoff):
    if type(values) not in (tuple, list) or len(values) > 256:
        raise ValueError("Backend records require bounded collections.")
    result = []
    for raw in values:
        raw = raw.canonical_dict() if type(raw) is cls else raw
        _safe(raw)
        _exact(raw, (f.name for f in fields(cls)))
        args = dict(raw)
        if cls is BackendQuestion:
            args.pop("question_id")
            item = BackendQuestion.create(handoff=handoff, **args)
            if item.question_id != raw["question_id"]:
                raise ValueError("Forged backend question identity.")
        else:
            for key, value in args.items():
                if key in {"responsibility", "authority", "retry_semantics", "idempotency_semantics", "transaction_semantics"}:
                    args[key] = None if value is None else _fact(value, handoff)
                elif key == "implementation_role":
                    args[key] = BackendRole(value)
                elif key == "failure_classes":
                    args[key] = tuple(BackendFailure(v) for v in _strings(value))
                elif key.endswith("_ids") or key in {"owned_capabilities", "dependencies", "exposed_interfaces"}:
                    args[key] = _strings(value)
                elif type(value) is str:
                    args[key] = _text(value, maximum=240)
                else:
                    raise ValueError("Malformed backend record.")
            item = cls(**args)
        result.append(item)
    result.sort(key=lambda item: item.canonical_json())
    if len({item.canonical_json() for item in result}) != len(result):
        raise ValueError("Duplicate backend records.")
    return tuple(result)


def _check_identity(item, kind, identity_key, *, exclude=()):
    body = item.canonical_dict()
    actual = body.pop(identity_key)
    for key in exclude:
        body.pop(key)
    if actual != backend_element_id(kind, body):
        raise ValueError("Forged backend element identity.")


def identify_backend_record(item, kind, identity_key, *, exclude=()):
    body = item.canonical_dict()
    body.pop(identity_key)
    for key in exclude:
        body.pop(key)
    return replace(item, **{identity_key: backend_element_id(kind, body)})


@dataclass(frozen=True)
class BackendSpecification(Record):
    backend_id: str
    source_project_id: str
    models_backend_handoff_id: str
    upstream_authority_id: str
    approved_domain_model_id: str
    model_id: str
    model_finalization_id: str
    approved_architecture_id: str
    architecture_id: str
    architecture_finalization_id: str
    objective: BackendFact
    approved_architecture_decisions: tuple[BackendFact, ...]
    resolved_model: ResolvedLogicalModel
    components: tuple[BackendComponent, ...]
    data_bindings: tuple[BackendDataBinding, ...]
    operations: tuple[BackendOperation, ...]
    policies: tuple[BackendPolicy, ...]
    open_backend_questions: tuple[BackendQuestion, ...]
    readiness: BackendReadiness
    project_stage: BuildStage = BuildStage.BACKEND
    schema: str = ARCADEV_BACKEND_SPECIFICATION_SCHEMA
    schema_version: int = ARCADEV_BACKEND_SPECIFICATION_SCHEMA_VERSION

    @classmethod
    def create(cls, *, handoff, objective, components=(), data_bindings=(), operations=(), policies=(), open_backend_questions=()):
        handoff = backend_handoff(handoff)
        objective = _fact(objective, handoff)
        expected_objective = BackendFact.create(handoff=handoff, source_ids=(handoff.architecture_id,), derivation="backend_objective")
        if objective != expected_objective:
            raise ValueError("Backend objective must preserve the frozen objective.")
        components = _records(components, BackendComponent, handoff)
        data_bindings = _records(data_bindings, BackendDataBinding, handoff)
        operations = _records(operations, BackendOperation, handoff)
        policies = _records(policies, BackendPolicy, handoff)
        questions = _records(open_backend_questions, BackendQuestion, handoff)
        resolved = handoff.frozen_approved_domain_model.package.resolved_model
        _validate_graph(handoff, components, data_bindings, operations, policies, questions)
        reasons = ("blocking_backend_questions",) if any(q.blocking for q in questions) else ()
        result = cls("", handoff.source_project_id, handoff.handoff_id,
            _identity("backend_upstream", handoff.canonical_dict()), handoff.approved_domain_model_id,
            handoff.model_id, handoff.model_finalization_id, handoff.approved_architecture_id,
            handoff.architecture_id, handoff.architecture_finalization_id, objective,
            tuple(BackendFact.create(handoff=handoff, source_ids=(d.decision_id,)) for d in
                  backend_architecture(handoff).architecture_finalization.decisions), resolved,
            components, data_bindings, operations, policies, questions, BackendReadiness(True, not reasons, reasons))
        body = result.canonical_dict()
        body.pop("backend_id")
        result = replace(result, backend_id=backend_element_id("specification", body))
        _safe(result.canonical_dict())
        return result

    @classmethod
    def from_dict(cls, value, *, handoff):
        _safe(value)
        _exact(value, (f.name for f in fields(cls)))
        if value["schema"] != ARCADEV_BACKEND_SPECIFICATION_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported backend specification schema/version.")
        result = cls.create(handoff=handoff, **{key: value[key] for key in
            ("objective", "components", "data_bindings", "operations", "policies", "open_backend_questions")})
        if _json(value) != result.canonical_json():
            raise ValueError("Backend identity, upstream binding, resolved model, stage or readiness is forged.")
        return result

    @classmethod
    def from_json(cls, text, *, handoff):
        return cls.from_dict(_parse(text), handoff=handoff)


def _validate_graph(handoff, components, bindings, operations, policies, questions):
    owners = backend_owners(handoff)
    model = handoff.frozen_approved_domain_model.package.resolved_model
    entities = {e.entity_id: e for e in model.entities}
    component_map = {c.component_id: c for c in components}
    operation_map = {o.operation_id: o for o in operations}
    policy_map = {p.policy_id: p for p in policies}
    for items, mapping in ((components, component_map), (operations, operation_map), (policies, policy_map)):
        if len(items) != len(mapping):
            raise ValueError("Duplicate backend element identities.")
    if len({_norm(c.name) for c in components}) != len(components):
        raise ValueError("Duplicate normalized backend component names.")
    # A grouping can collect compatible frozen owners, but each source retains
    # its exact capabilities, interfaces and persistence ownership.
    source_owner = {}
    for component in components:
        sources = set(component.architecture_source_ids)
        if not sources or not sources <= owners.keys() or sources & source_owner.keys():
            raise ValueError("Invalid or duplicate frozen backend ownership.")
        if any(component.implementation_role not in ROLE_CATEGORIES[owners[s].category] for s in sources):
            raise ValueError("Backend implementation role contradicts its frozen owner.")
        caps = {cap for s in sources for cap in owners[s].owned_capabilities}
        mids = {eid for eid, e in entities.items() if caps & set(e.owned_capabilities)}
        interfaces = {i for s in sources for i in owners[s].exposed_interfaces}
        if set(component.owned_capabilities) != caps or set(component.model_entity_ids) != mids or set(component.exposed_interfaces) != interfaces:
            raise ValueError("Backend component changes capability, model or interface ownership.")
        if component.responsibility != BackendFact.create(handoff=handoff, source_ids=tuple(sources), derivation="capability_implementation"):
            raise ValueError("Backend responsibility is not grounded in its exact owners.")
        # Identity omits presentation name and graph edges to avoid hash cycles.
        _check_identity(component, "component", "component_id", exclude=("name", "dependencies"))
        source_owner.update({s: component.component_id for s in sources})
    if set(source_owner) != set(owners):
        raise ValueError("Missing required backend architecture responsibility.")
    for component in components:
        expected = {source_owner[d] for s in component.architecture_source_ids for d in owners[s].dependencies
                    if d in source_owner and source_owner[d] != component.component_id}
        if set(component.dependencies) != expected:
            raise ValueError("Invalid backend dependency graph.")
    bound = set()
    for binding in bindings:
        if binding.entity_id not in entities or binding.entity_id in bound:
            raise ValueError("Invented or duplicate persisted entity.")
        entity = entities[binding.entity_id]
        possible = {source_owner[s] for s, owner in owners.items() if set(entity.owned_capabilities) & set(owner.owned_capabilities)}
        if possible != {binding.component_id}:
            raise ValueError("Data binding changes frozen persistence ownership.")
        if binding.authority != BackendFact.create(handoff=handoff, source_ids=(binding.entity_id,), derivation="persistence_binding"):
            raise ValueError("Data binding changes accepted logical model authority.")
        _check_identity(binding, "binding", "binding_id")
        bound.add(binding.entity_id)
    if bound != set(entities):
        raise ValueError("Missing approved data authority.")
    required_caps = {cap: s for s, c in owners.items() for cap in c.owned_capabilities}
    seen = set()
    for operation in operations:
        if operation.capability_id not in required_caps or operation.capability_id in seen:
            raise ValueError("Invented or duplicate backend operation capability.")
        source = required_caps[operation.capability_id]
        if operation.component_id != source_owner[source]:
            raise ValueError("Invalid operation ownership.")
        expected_kind = "integration_action" if owners[source].category == "adapter" else "workflow_action"
        expected_models = set(backend_operation_entities(handoff, source, operation.capability_id))
        if operation.kind != expected_kind or set(operation.input_entity_ids) != expected_models or set(operation.output_entity_ids) != expected_models:
            raise ValueError("Backend operation invents behavior or changes approved model references.")
        if operation.authority != BackendFact.create(handoff=handoff, source_ids=(source,), derivation="operation_from_requirement"):
            raise ValueError("Operation authority is not grounded.")
        for ids, kind in ((operation.authorization_ids, "authorization"), (operation.transaction_ids, "transaction"), (operation.failure_ids, "failure")):
            if any(pid not in policy_map or policy_map[pid].kind != kind for pid in ids):
                raise ValueError("Invalid operation policy reference.")
        _check_identity(operation, "operation", "operation_id", exclude=("name", "authorization_ids", "transaction_ids", "failure_ids"))
        seen.add(operation.capability_id)
    if seen != set(required_caps):
        raise ValueError("Missing required approved backend capability operation.")
    architecture = backend_architecture(handoff).original_architecture
    areas = {"authentication": "authorization", "integration": "integration", "background": "background", "storage": "storage"}
    required_policies = {a.aspect_id: areas[a.area.value] for a in architecture.aspects if a.area.value in areas}
    covered = set()
    catalog = backend_sources(handoff)
    for policy in policies:
        if not set(policy.component_ids) <= component_map.keys() or not set(policy.operation_ids) <= operation_map.keys():
            raise ValueError("Invalid backend policy owners or operations.")
        if not set((*policy.model_entity_ids, *policy.resulting_entity_ids)) <= entities.keys():
            raise ValueError("Invalid policy logical state references.")
        if not set((*policy.input_authority_ids, *policy.external_boundary_ids)) <= catalog.keys():
            raise ValueError("Invalid work-unit input or external boundary.")
        if len(policy.authority.source_ids) != 1:
            raise ValueError("Backend policies require exact frozen boundary evidence.")
        source = policy.authority.source_ids[0]
        if source not in required_policies or policy.kind != required_policies[source] or source in covered:
            raise ValueError("Unsupported backend boundary, transaction or failure behavior.")
        aspect = next(a for a in architecture.aspects if a.aspect_id == source)
        scope = {source_owner[s] for s in aspect.component_ids if s in source_owner}
        if set(policy.component_ids) != scope:
            raise ValueError("Backend boundary changes frozen component scope.")
        expected_ops = set(operation_map) if policy.kind == "authorization" else {o.operation_id for o in operations if o.component_id in scope}
        if set(policy.operation_ids) != expected_ops:
            raise ValueError("Backend boundary changes operation scope.")
        if policy.authority != BackendFact.create(handoff=handoff, source_ids=(source,)):
            raise ValueError("Backend boundary changes frozen authority.")
        # Unknown runtime policies cannot become concrete through candidate text.
        if any(v is not None for v in (policy.retry_semantics, policy.idempotency_semantics, policy.transaction_semantics)) or policy.failure_classes:
            raise ValueError("Runtime policy choices require later explicit backend decisions.")
        expected_entities = set(backend_policy_entities(handoff, aspect, policy.kind, components))
        if set(policy.model_entity_ids) != expected_entities or set(policy.resulting_entity_ids) != expected_entities:
            raise ValueError("Backend boundary changes approved data authority.")
        if policy.input_authority_ids != (source,) or policy.external_boundary_ids != (source,):
            raise ValueError("Backend work boundary must retain exact frozen input/external authority.")
        _check_identity(policy, "policy", "policy_id")
        covered.add(source)
    if covered != set(required_policies):
        raise ValueError("Missing required authorization/integration/storage/background boundary.")
    auth_ids = {p.policy_id for p in policies if p.kind == "authorization"}
    for operation in operations:
        if set(operation.authorization_ids) != auth_ids:
            raise ValueError("Operation drops approved authentication/principal boundary.")
    for question in questions:
        if not set(question.component_ids) <= component_map.keys() or not set(question.operation_ids) <= operation_map.keys():
            raise ValueError("Backend question has invalid affected components or operations.")


def validate_backend_specification(candidate, *, handoff):
    if type(candidate) is BackendSpecification:
        candidate = candidate.canonical_dict()
    return (BackendSpecification.from_json(candidate, handoff=handoff) if type(candidate) is str
            else BackendSpecification.from_dict(candidate, handoff=handoff))
