"""Conservative model derivation from frozen architecture; no code generation."""
from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from .architecture_models_handoff import ArchitectureModelsHandoff
from .domain_model_specification import (
    DomainModelSpecification, ModelEntity, ModelFact, ModelField, ModelQuestion,
    ModelArea, LogicalType, DataClassification, model_element_id,
    persistent_model_capabilities, model_handoff, validate_domain_model_specification,
)
from .architecture_specification import _parse, _json


@runtime_checkable
class DomainModelCandidateAdapter(Protocol):
    """Trusted adapter code returns untrusted inert data; vendors stay outside."""
    def create_candidate(self, handoff: ArchitectureModelsHandoff) -> Mapping[str, Any] | str: ...


def _approved_identity(handoff, component, entity_id):
    """Recognize only an exact, scoped, declarative identity-field decision.

Free-form architecture implementation choices never imply a logical type.
An unambiguous approved payload can prevent reopening an identifier choice.
"""
    choices = []
    for decision in handoff.frozen_approved_architecture.package.architecture_finalization.decisions:
        if not set(component.owned_capabilities) <= set(decision.plan_source_requirements):
            continue
        for value in decision.accepted_values:
            try:
                payload = _parse(value)
            except ValueError:
                continue
            keys = {"name", "logical_type", "required", "collection", "mutable", "unique", "classification", "value_domain_id", "default_json"}
            if type(payload) is not dict or set(payload) != keys or value != _json(payload).strip():
                continue
            if (payload["name"] != "id" or payload["logical_type"] not in {"uuid", "string", "integer", "external_reference"}
                    or payload["required"] is not True or payload["collection"] is not False
                    or payload["mutable"] is not False or payload["unique"] is not True
                    or payload["value_domain_id"] is not None or payload["default_json"] is not None):
                continue
            fact = ModelFact.create(handoff=handoff, source_requirements=(decision.decision_id,))
            field_id = model_element_id("field", name="id", source_requirements=fact.source_requirements, scope=(entity_id,))
            choices.append(ModelField(field_id, evidence=fact, **payload))
    if len({f.canonical_json() for f in choices}) == 1:
        return choices[0]
    return None


def generate_baseline_domain_model(handoff: ArchitectureModelsHandoff) -> DomainModelSpecification:
    handoff = model_handoff(handoff)
    architecture = handoff.frozen_approved_architecture.package.original_architecture
    required = persistent_model_capabilities(handoff)
    components = {c.component_id: c for c in architecture.components}
    entities, questions = [], []

    def question(area, sources, affected, text):
        q = ModelQuestion.create(handoff=handoff, question=text, blocking=True, area=area,
            source_requirements=tuple(sorted(set(sources))), entity_ids=tuple(sorted(set(affected))))
        questions.append(q)
        return q

    # One state structure per frozen owner, not one entity per word or SQL table.
    for owner in sorted(set(required.values())):
        component = components[owner]
        capabilities = tuple(sorted(c for c, source in required.items() if source == owner))
        name = component.name.removesuffix(" boundary") + " state"
        eid = model_element_id("entity", name=name, source_requirements=(owner,), scope=capabilities)
        identity = _approved_identity(handoff, component, eid)
        identity_question = None
        if identity is None:
            identity_question = question(ModelArea.IDENTITY, (owner,), (eid,),
                "Which logical identifier type represents the stable identity required by " + component.responsibility.value + "?")
        entity = ModelEntity(eid, name, ModelFact.create(handoff=handoff, source_requirements=(owner,), derivation="capability_state"),
            capabilities, fields=(identity,) if identity else (), identity_field_ids=(identity.field_id,) if identity else (),
            identity_question_id=identity_question.question_id if identity_question else None)
        entities.append(entity)
        question(ModelArea.UNIQUENESS, (owner,), (eid,),
            "Which logical uniqueness requirements beyond stable identity apply to " + component.responsibility.value + "?")
        question(ModelArea.LOOKUP, (owner,), (eid,),
            "Which logical lookup requirements support " + component.responsibility.value + "?")
        if component.category == "adapter":
            question(ModelArea.EXTERNAL_REFERENCE, (owner,), (eid,),
                "Which non-secret external identifiers and logical representations must persist for " + component.responsibility.value + "?")
        elif any(word in component.responsibility.value.casefold() for word in ("build", "publish", "workflow")):
            question(ModelArea.LIFECYCLE, (owner,), (eid,),
                "Which explicit lifecycle values must persist for " + component.responsibility.value + "?")

    owner_entities = {source: e for e in entities for source in e.responsibility.source_requirements}
    all_ids = tuple(e.entity_id for e in entities)
    all_sources = tuple(owner_entities)
    auth = tuple(a.aspect_id for a in architecture.aspects if a.area.value == "authentication")
    if auth and entities:
        question(ModelArea.PRINCIPAL_REFERENCE, (*auth, *all_sources), all_ids,
            "How should required domain records reference authenticated principals without storing credentials?")

    # A policy can ground the need for a choice without deciding that choice.
    for aspect in architecture.aspects:
        if aspect.area.value == "storage" and any("deletion" in fact.value.casefold() for fact in aspect.constraints):
            affected = tuple(owner_entities[c].entity_id for c in aspect.component_ids if c in owner_entities)
            if affected:
                question(ModelArea.RETENTION, (aspect.aspect_id, *[c for c in aspect.component_ids if c in owner_entities]), affected,
                    "Which logical retention/deletion state enforces " + aspect.responsibility.value + "?")

    # Relationships stay questions when architecture supplies no exact cardinality.
    # A shared persistence boundary is evidence for reviewing ownership/linkage,
    # not evidence for a foreign key, cascade, or join table.
    if len(entities) > 1:
        question(ModelArea.RELATIONSHIP, all_sources, all_ids,
            "Which ownership, cardinality and reference relationships connect the required domain state while preserving each frozen architecture owner?")
    for component in architecture.components:
        if component.owned_capabilities and component.category == "service" and not set(component.owned_capabilities) & set(required):
            question(ModelArea.FIELD, (component.component_id, *all_sources), all_ids,
                "How should outcomes of " + component.responsibility.value + " be represented or referenced without assuming additional persistent domain state?")

    return DomainModelSpecification.create(handoff=handoff,
        objective=ModelFact.create(handoff=handoff, source_requirements=(handoff.architecture_id,), derivation="model_objective"),
        entities=tuple(entities), open_model_questions=tuple(questions))


def _affected_capabilities(question, model):
    return frozenset(capability for e in model.entities if e.entity_id in question.entity_ids for capability in e.owned_capabilities)


def validate_domain_model_candidate(handoff, candidate):
    handoff = model_handoff(handoff)
    if type(candidate) is MappingProxyType:
        candidate = dict(candidate)
    model = validate_domain_model_specification(candidate, handoff=handoff)
    baseline = generate_baseline_domain_model(handoff)
    required = persistent_model_capabilities(handoff)
    if {c for e in model.entities for c in e.owned_capabilities} != set(required):
        raise ValueError("Candidate invents persistence not required by frozen architecture.")
    for entity in model.entities:
        if len({required[c] for c in entity.owned_capabilities}) != 1:
            raise ValueError("Candidate merges distinct frozen architecture ownership boundaries.")
    matched_questions = set()
    for q in baseline.open_model_questions:
        matches = [other for other in model.open_model_questions
                   if (other.area, other.source_requirements, other.question, other.blocking)
                   == (q.area, q.source_requirements, q.question, q.blocking)
                   and _affected_capabilities(other, model) == _affected_capabilities(q, baseline)]
        if len(matches) != 1:
            raise ValueError("Candidate removes, reinterprets or duplicates an unresolved material model question.")
        matched_questions.add(matches[0].question_id)
    questions = {q.question_id: q for q in model.open_model_questions}

    def proposal(fact, areas):
        if fact.question_id is None:
            return None  # 4.1 has already checked exact approved payload evidence.
        if fact.question_id not in matched_questions or questions[fact.question_id].area not in areas:
            raise ValueError("Candidate launders unsupported material model content through an unrelated question.")
        return questions[fact.question_id]

    for entity in model.entities:
        for field in entity.fields:
            q = proposal(field.evidence, {ModelArea.IDENTITY, ModelArea.EXTERNAL_REFERENCE, ModelArea.PRINCIPAL_REFERENCE,
                                         ModelArea.LIFECYCLE, ModelArea.RETENTION, ModelArea.FIELD})
            if q is None:
                continue
            if q.area is ModelArea.IDENTITY and field.field_id not in entity.identity_field_ids:
                raise ValueError("An identity question cannot authorize unrelated candidate fields.")
            if q.area in {ModelArea.LIFECYCLE, ModelArea.RETENTION} and field.logical_type is not LogicalType.ENUM:
                raise ValueError("Lifecycle proposals require an explicit value domain.")
            if q.area in {ModelArea.EXTERNAL_REFERENCE, ModelArea.PRINCIPAL_REFERENCE, ModelArea.FIELD}:
                if field.logical_type is not LogicalType.EXTERNAL_REFERENCE or field.classification is not DataClassification.EXTERNAL_IDENTIFIER:
                    raise ValueError("Unresolved integration/principal/outcome references must remain non-secret logical references.")
    for domain in model.value_domains:
        proposal(domain.evidence, {ModelArea.LIFECYCLE, ModelArea.RETENTION})
    for relationship in model.relationships:
        proposal(relationship.evidence, {ModelArea.RELATIONSHIP})
    for constraint in model.constraints:
        area = {"unique": ModelArea.UNIQUENESS, "composite_unique": ModelArea.UNIQUENESS,
                "lifecycle_invariant": ModelArea.LIFECYCLE, "ownership_invariant": ModelArea.RELATIONSHIP}.get(constraint.kind)
        proposal(constraint.evidence, {area} if area else set())
    for access in model.access_requirements:
        proposal(access.evidence, {ModelArea.LOOKUP})
    if not model.readiness.structurally_valid:
        raise ValueError("Candidate model is structurally incomplete.")
    return model


def validate_domain_model_adapter_candidate(handoff, adapter: DomainModelCandidateAdapter):
    handoff = model_handoff(handoff)
    if not isinstance(adapter, DomainModelCandidateAdapter):
        raise ValueError("Model adapter must implement the provider-neutral candidate protocol.")
    return validate_domain_model_candidate(handoff, adapter.create_candidate(handoff))
