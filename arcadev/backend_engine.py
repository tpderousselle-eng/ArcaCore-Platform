"""Deterministic backend authority and an untrusted provider-neutral boundary."""
from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from .models_backend_handoff import ModelsBackendHandoff
from .backend_specification import (
    BackendSpecification, BackendFact, BackendComponent, BackendDataBinding,
    BackendOperation, BackendPolicy, BackendQuestion, BackendArea, BackendRole,
    backend_handoff, backend_architecture, backend_owners, backend_operation_entities,
    backend_policy_entities, backend_policy_operations, identify_backend_record, validate_backend_specification,
)


@runtime_checkable
class BackendSpecificationCandidateAdapter(Protocol):
    """Trusted adapter code returns untrusted inert data; vendors stay outside."""
    def create_candidate(self, handoff: ModelsBackendHandoff) -> Mapping[str, Any] | str: ...

def _assemble_backend(h):
    """Preserve frozen ownership without automatic per-entity services or CRUD."""

    owners, entities = backend_owners(h), h.frozen_approved_domain_model.package.resolved_model.entities
    fact = lambda sources, rule=None: BackendFact.create(handoff=h, source_ids=tuple(sorted(sources)), derivation=rule)
    roles = {"application": BackendRole.APPLICATION_SERVICE, "service": BackendRole.APPLICATION_SERVICE, "storage": BackendRole.PERSISTENCE,
             "identity": BackendRole.IDENTITY_BOUNDARY, "adapter": BackendRole.INTEGRATION_ADAPTER,
             "worker": BackendRole.EXTERNAL_WORKER}
    components = []
    for group in [(s,) for s in owners]:
        caps = tuple(sorted({cap for s in group for cap in owners[s].owned_capabilities}))
        mids = tuple(sorted(e.entity_id for e in entities if set(caps) & set(e.owned_capabilities)))
        interfaces = tuple(sorted({i for s in group for i in owners[s].exposed_interfaces}))
        c = BackendComponent("", " + ".join(owners[s].name for s in group), fact(group, "capability_implementation"),
            tuple(sorted(group)), caps, mids, roles[owners[group[0]].category], (), interfaces)
        components.append(identify_backend_record(c, "component", "component_id", exclude=("name", "dependencies")))
    mapping = {s: c.component_id for c in components for s in c.architecture_source_ids}
    components = [replace(c, dependencies=tuple(sorted({mapping[d] for s in c.architecture_source_ids
        for d in owners[s].dependencies if d in mapping and mapping[d] != c.component_id}))) for c in components]
    capability_owners = {cap: mapping[s] for s, owner in owners.items() for cap in owner.owned_capabilities}
    bindings = [identify_backend_record(BackendDataBinding("", e.entity_id,
        min({capability_owners[cap] for cap in e.owned_capabilities}),
        fact((e.entity_id,), "persistence_binding")), "binding", "binding_id") for e in entities]
    operations = []
    for s, owner in owners.items():
        for cap in owner.owned_capabilities:
            mids = backend_operation_entities(h, s, cap)
            op = BackendOperation("", owner.name, mapping[s], cap,
                "integration_action" if owner.category == "adapter" else "workflow_action", mids, mids, (), (), (),
                fact((s,), "operation_from_requirement"))
            operations.append(identify_backend_record(op, "operation", "operation_id",
                exclude=("name", "authorization_ids", "transaction_ids", "failure_ids")))
    policies = []
    kinds = {"authentication": "authorization", "integration": "integration", "storage": "storage", "background": "background"}
    for a in backend_architecture(h).original_architecture.aspects:
        if a.area.value not in kinds:
            continue
        kind = kinds[a.area.value]
        cids = tuple(sorted({mapping[s] for s in a.component_ids if s in mapping}))
        mids = backend_policy_entities(h, a, kind, components)
        oids = backend_policy_operations(h, a, kind, operations)
        policy = BackendPolicy("", kind, cids, oids, mids, fact((a.aspect_id,)), (a.aspect_id,), mids, (a.aspect_id,))
        policies.append(identify_backend_record(policy, "policy", "policy_id"))
    auth = tuple(sorted(p.policy_id for p in policies if p.kind == "authorization"))
    operations = [replace(o, authorization_ids=auth) for o in operations]
    return BackendSpecification.create(handoff=h, objective=fact((h.architecture_id,), "backend_objective"),
        components=components, data_bindings=bindings, operations=operations, policies=policies)


def _backend_questions(handoff, spec):
    """Questions refine implementation, never the existence of approved scope."""
    questions = []
    architecture = backend_architecture(handoff).original_architecture
    model = spec.resolved_model
    component_map = {c.component_id: c for c in spec.components}

    def question(area, text, sources, *, mids=(), cids=(), oids=()):
        questions.append(BackendQuestion.create(handoff=handoff, question=text, blocking=True, area=area,
            architecture_source_ids=tuple(sorted(set(sources))), model_source_ids=tuple(sorted(set(mids))),
            component_ids=tuple(sorted(set(cids))), operation_ids=tuple(sorted(set(oids)))))

    all_models = tuple(e.entity_id for e in model.entities)
    if model.entities:
        question(BackendArea.PERSISTENCE_MAPPING,
            "Which physical naming convention should later translation apply to approved logical state without adding fields or changing accepted choices?",
            (handoff.architecture_id,), mids=all_models, cids=(b.component_id for b in spec.data_bindings),
            oids=(o.operation_id for o in spec.operations if o.input_entity_ids or o.output_entity_ids))
    if spec.operations:
        # Logical operations exist independently of their eventual transport.
        question(BackendArea.API_BOUNDARY,
            "Which transport exposure should implement the approved logical operations while preserving their authorization boundaries?",
            (handoff.architecture_id,), mids=all_models, cids=(o.component_id for o in spec.operations),
            oids=(o.operation_id for o in spec.operations))
    related = {e.entity_id for e in model.entities for choice in e.choices if choice.claim.related_entity_id is not None}
    related.update(choice.claim.related_entity_id for e in model.entities for choice in e.choices if choice.claim.related_entity_id is not None)
    related.update(r.source_entity_id for r in model.relationships)
    related.update(r.target_entity_id for r in model.relationships)
    if related:
        question(BackendArea.TRANSACTION,
            "Which atomic write boundary should preserve the approved related domain state and its existing relationship constraints?",
            (handoff.architecture_id,), mids=related,
            cids=(b.component_id for b in spec.data_bindings if b.entity_id in related),
            oids=(o.operation_id for o in spec.operations if set(o.output_entity_ids) & related))
    for policy in spec.policies:
        if policy.kind != "background":
            continue
        callers = {c.component_id for c in spec.components if set(c.dependencies) & set(policy.component_ids)}
        question(BackendArea.ASYNC_EXECUTION,
            "How should completion reach authoritative domain state while preserving the already approved worker isolation and execution mechanism?",
            policy.authority.source_ids, mids=policy.resulting_entity_ids, cids=policy.component_ids,
            oids=(o.operation_id for o in spec.operations if o.component_id in callers))
    for operation in spec.operations:
        owner = component_map[operation.component_id]
        frozen = [c for c in architecture.components if c.component_id in owner.architecture_source_ids
                  and operation.capability_id in c.owned_capabilities]
        is_release = any("publish" in c.responsibility.value.casefold() or "release" in c.responsibility.value.casefold() for c in frozen)
        sources = tuple(c.component_id for c in frozen)
        if operation.kind == "integration_action":
            question(BackendArea.FAILURE_SEMANTICS,
                "How should failures of this approved external integration be surfaced without promoting unsuccessful domain state?",
                sources, mids=operation.output_entity_ids, cids=(operation.component_id,), oids=(operation.operation_id,))
            question(BackendArea.EXTERNAL_INTEGRATION,
                "Which retry policy should govern this approved external integration while retaining explicit user authorization?",
                sources, mids=operation.output_entity_ids, cids=(operation.component_id,), oids=(operation.operation_id,))
        if operation.kind == "integration_action" or is_release:
            # Build-job identifiers are already an architecture choice. This
            # question concerns remaining release/sync action deduplication.
            question(BackendArea.IDEMPOTENCY,
                "Which deduplication boundary should govern repeated invocations of this approved user-controlled action?",
                sources, mids=operation.output_entity_ids, cids=(operation.component_id,), oids=(operation.operation_id,))
    for entity in model.entities:
        if any(c.claim.slot == "retention" for c in entity.choices):
            binding = next(b for b in spec.data_bindings if b.entity_id == entity.entity_id)
            question(BackendArea.STORAGE,
                "Which non-secret storage reference mapping should preserve this entity's approved retention and deletion policy?",
                entity.architecture_source_requirements, mids=(entity.entity_id,), cids=(binding.component_id,),
                oids=(o.operation_id for o in spec.operations if entity.entity_id in o.output_entity_ids))
    if spec.components:
        question(BackendArea.IMPLEMENTATION_TECHNOLOGY,
            "Which certification precondition must a later ArcaCore translation satisfy before generating all approved module, integration and worker responsibilities?",
            (handoff.architecture_id,), mids=all_models, cids=(c.component_id for c in spec.components),
            oids=(o.operation_id for o in spec.operations))
    return tuple(questions)


def generate_baseline_backend_specification(handoff: ModelsBackendHandoff) -> BackendSpecification:
    handoff = backend_handoff(handoff)
    spec = _assemble_backend(handoff)
    return BackendSpecification.create(handoff=handoff, objective=spec.objective, components=spec.components,
        data_bindings=spec.data_bindings, operations=spec.operations, policies=spec.policies,
        open_backend_questions=_backend_questions(handoff, spec))


def validate_backend_specification_candidate(handoff, candidate):
    handoff = backend_handoff(handoff)
    if type(candidate) is MappingProxyType:
        candidate = dict(candidate)
    spec = validate_backend_specification(candidate, handoff=handoff)
    baseline = generate_baseline_backend_specification(handoff)
    original_components = {c.component_id: c for c in baseline.components}
    target_components = {source: c.component_id for c in spec.components for source in c.architecture_source_ids}
    original_operations = {o.operation_id: o for o in baseline.operations}
    target_operations = {o.capability_id: o.operation_id for o in spec.operations}
    matched = set()
    for question in baseline.open_backend_questions:
        # A grouped unit can contain additional frozen owners; target precisely
        # the units containing the original owners, retaining exact model and
        # operation scope. Presentation names play no role in equivalence.
        cids = {target_components[source] for cid in question.component_ids
                for source in original_components[cid].architecture_source_ids}
        oids = {target_operations[original_operations[oid].capability_id] for oid in question.operation_ids}
        matches = [q for q in spec.open_backend_questions if
            (q.question, q.blocking, q.area, q.architecture_source_ids, q.model_source_ids) ==
            (question.question, question.blocking, question.area, question.architecture_source_ids, question.model_source_ids)
            and set(q.component_ids) == cids and set(q.operation_ids) == oids]
        if len(matches) != 1:
            raise ValueError("Candidate removes, reopens, or changes a material backend question or its scope.")
        matched.add(matches[0].question_id)
    for extra in spec.open_backend_questions:
        if extra.question_id in matched:
            continue
        # An advisory refinement may narrow an existing implementation question.
        # It grants no material authority and cannot introduce another area.
        if extra.blocking or not any(q.area == extra.area
            and extra.question == "Advisory review: " + q.question
            and set(extra.architecture_source_ids) <= set(q.architecture_source_ids)
            and set(extra.model_source_ids) <= set(q.model_source_ids)
            and set(extra.component_ids) <= set(q.component_ids)
            and set(extra.operation_ids) <= set(q.operation_ids)
            and (extra.component_ids or extra.operation_ids) for q in spec.open_backend_questions if q.question_id in matched):
            raise ValueError("Unsupported additional backend question scope or wording.")
    return spec


def validate_backend_specification_adapter_candidate(handoff, adapter: BackendSpecificationCandidateAdapter):
    handoff = backend_handoff(handoff)
    if not isinstance(adapter, BackendSpecificationCandidateAdapter):
        raise ValueError("Backend adapter must implement the provider-neutral candidate protocol.")
    return validate_backend_specification_candidate(handoff, adapter.create_candidate(handoff))
