"""Conservative architecture derivation and a provider-neutral candidate boundary."""
from __future__ import annotations

from dataclasses import replace
import re
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from .plan_architecture_handoff import PlanArchitectureHandoff, validate_plan_architecture_handoff
from .architecture_specification import (
    ArchitectureArea, ArchitectureAspect, ArchitectureComponent, ArchitectureConnection,
    ArchitectureFact, ArchitectureQuestion, ArchitectureSpecification,
    approved_architecture_sources, plan_source_id, validate_architecture_specification, _identity,
)


@runtime_checkable
class ArchitectureCandidateAdapter(Protocol):
    """Trusted adapter code returns untrusted inert JSON data; no vendor metadata."""
    def create_candidate(self, handoff: PlanArchitectureHandoff) -> Mapping[str, Any] | str: ...


def generate_baseline_architecture(handoff: PlanArchitectureHandoff) -> ArchitectureSpecification:
    handoff = validate_plan_architecture_handoff(handoff)
    package = handoff.frozen_approved_plan.package
    plan, decisions = package.plan_finalization.original_plan, package.plan_finalization.decisions
    intake = package.idea_handoff.snapshot.intake
    catalog = approved_architecture_sources(handoff)
    components, interfaces, flows, aspects, questions = [], [], [], [], []

    def fact(sources, rule=None):
        return ArchitectureFact.create(handoff=handoff, source_requirements=tuple(sources), derivation=rule)

    def source_for(value):
        matches = [key for key, (text, _) in catalog.items() if text == value]
        matches.extend(d.decision_id for d in decisions if value in d.accepted_values)
        return min(matches)

    def component(name, category, sources, owns=(), trust="application", rule="responsibility"):
        identity = _identity("component", {"category": category, "sources": sorted(sources), "owned": sorted(owns)})
        components.append(ArchitectureComponent(identity, name, category, fact(sources, rule), tuple(owns), (), (), trust))
        return identity

    def aspect(area, sources, owners, rule="boundary", constraints=(), technology=None):
        identity = _identity("aspect", {"area": area, "sources": sorted(sources)})
        aspects.append(ArchitectureAspect(identity, ArchitectureArea(area), fact(sources, rule), tuple(owners), tuple(constraints), technology))

    def connection(source, destination, sources):
        identity = _identity("interface", {"source": source, "destination": destination, "requirements": sorted(sources)})
        edge = ArchitectureConnection(identity, source, destination, fact(sources, "interaction"))
        interfaces.append(edge)
        flows.append(replace(edge, connection_id=_identity("flow", edge.canonical_dict())))

    explicit_implementations = [item.value for item in intake.technology_preferences]
    explicit_implementations.extend(value for d in decisions for value in d.accepted_values)

    def implementation(kind):
        # An explicit slot label is a deterministic interpretation, not a stack guess.
        pattern = re.compile(r"(?i)^(?:use )?" + re.escape(kind) + r"(?: implementation)?\s*[:=]\s*\S.+$")
        values = sorted({value for value in explicit_implementations if pattern.fullmatch(value)})
        if len(values) == 1:
            return fact([source_for(values[0])])
        # Bare, recognized technology preferences already carry explicit user authority.
        known = {"frontend": {"react", "next.js", "vue", "angular"}, "primary persistence": {"postgresql", "sqlite", "mysql"}}
        values = sorted({item.value for item in intake.technology_preferences if item.value.casefold() in known.get(kind, set())})
        return fact([source_for(values[0])]) if len(values) == 1 else None

    def question(kind, area, sources, owners, text):
        chosen = implementation(kind)
        if chosen is None:
            questions.append(ArchitectureQuestion.create(text, True, tuple(sources), area, handoff=handoff))
        else:
            for index, item in enumerate(aspects):
                if item.area.value == area and set(item.responsibility.source_requirements) == set(sources):
                    constraints = {fact.canonical_json(): fact for fact in (*item.constraints, chosen)}
                    aspects[index] = replace(item, constraints=tuple(constraints.values()), technology=chosen)
                    break
            else:
                aspect(area, tuple(sources), tuple(owners), constraints=(chosen,), technology=chosen)

    capabilities = {plan_source_id(item): item for item in plan.in_scope_capabilities}
    capability_sources = tuple(sorted(capabilities))
    objective_source = plan_source_id(plan.product_objective)
    platform_sources = tuple(source_for(item.value) for item in intake.platform_targets)
    client_sources = platform_sources or (objective_source,)
    client = component("Application experience", "application", client_sources)
    if any("web" in item.value.casefold() for item in intake.platform_targets):
        question("frontend", "frontend", client_sources, (client,), "Which frontend implementation will deliver the approved web experience?")

    owners = {}
    integration_values = {item.value for item in plan.integrations if not item.value.casefold().startswith("no ")}
    auth_values = {item.value for item in intake.authentication_requirements if not item.value.casefold().startswith("no ")}
    for source, item in sorted(capabilities.items()):
        category = "service"
        if item.value.casefold() == "authentication" and auth_values:
            category = "identity"
        elif set(item.source_requirements) & integration_values and "integration" in item.value.casefold():
            category = "adapter"
        owners[source] = component(item.value + " boundary", category, (source,), (source,))
        connection(client, owners[source], (source,))

    persistent = tuple(source for source, item in capabilities.items() if any(word in item.value.casefold() for word in ("manage", "project", "asset", "build", "publish")))
    if persistent:
        storage = component("Logical persistent storage", "storage", persistent, rule="storage")
        aspect("storage", persistent, (storage,), rule="storage")
        for source in persistent:
            connection(owners[source], storage, (source,))
        question("primary persistence", "storage", persistent, (storage,), "Which primary persistence implementation supports the approved managed state?")

    for decision in decisions:
        source = (decision.decision_id,)
        text = " ".join(decision.accepted_values).casefold()
        related = tuple(key for key, item in capabilities.items() if set(item.source_requirements) & set(decision.idea_source_requirements))
        responsible = tuple(owners[key] for key in related) or (client,)
        constraint = (fact(source),)
        if "asset" in decision.source_question.question.casefold():
            aspect("storage", source, responsible, rule="storage", constraints=constraint)
            question("asset storage", "storage", source, responsible, "Which asset storage implementation enforces the approved storage and deletion policy?")
        elif "build" in decision.source_question.question.casefold() and "isolated" in text and ("worker" in text or "execution" in text):
            worker = component("Isolated background build worker", "worker", source, trust="isolated")
            aspect("background", source, (worker,), constraints=constraint)
            aspect("security", source, (worker,), rule="security", constraints=constraint)
            for owner in responsible:
                connection(owner, worker, source)
            question("worker isolation", "background", source, (worker,), "Which worker isolation implementation enforces the approved build isolation?")
            job_sources = related or source
            question("background job", "background", job_sources, (worker,), "Which background job execution mechanism dispatches and tracks the approved isolated builds?")
        elif "publish" in decision.source_question.question.casefold():
            aspect("component", source, responsible, constraints=constraint)
            question("publishing", "component", source, responsible, "Which publishing implementation enforces the approved user-controlled release actions?")
        elif "synchronization" in decision.source_question.question.casefold():
            aspect("integration", source, responsible, constraints=constraint)
            question("integration", "integration", source, responsible, "Which synchronization implementation preserves the approved user-authorized repository behavior?")
        else:
            aspect("context", source, responsible, constraints=constraint)

    for values, area in ((intake.authentication_requirements, "authentication"), (intake.integration_requirements, "integration")):
        for value in values:
            if value.value.casefold().startswith("no "):
                continue
            source = source_for(value.value)
            responsible = tuple(owners[key] for key, item in capabilities.items() if value.value in item.source_requirements) or (client,)
            aspect(area, (source,), responsible, constraints=(fact((source,)),))
            if area == "integration":
                for owner in responsible:
                    connection(owner, source, (source,))

    all_owners = tuple(c.component_id for c in components)
    for value in intake.deployment_requirements:
        source = source_for(value.value)
        aspect("deployment", (source,), all_owners, constraints=(fact((source,)),))
        question("deployment topology", "deployment", (source,), all_owners, "Which logical deployment-unit topology realizes the approved deployment target?")
    for area, rule in (("security", "security"), ("observability", "observability"), ("resilience", "resilience"), ("risk", "risk")):
        aspect(area, capability_sources, all_owners, rule=rule,
               constraints=(fact(capability_sources, "mitigation"),) if area == "risk" else ())
    # Local graph IDs are derived from source references; names do not constrain grouping.
    component_ids = set(all_owners)
    components = [replace(item,
        dependencies=tuple(edge.destination for edge in interfaces if edge.source == item.component_id and edge.destination in component_ids),
        exposed_interfaces=tuple(edge.connection_id for edge in interfaces if item.component_id in (edge.source, edge.destination)),
    ) for item in components]
    constraints = {plan_source_id(item) for item in (*plan.planning_constraints, *plan.integrations)} | {d.decision_id for d in decisions}
    external = {plan_source_id(item): item for item in (*plan.user_roles, *plan.integrations)}
    return ArchitectureSpecification.create(handoff=handoff, objective=fact((objective_source,)),
        system_boundary=fact(capability_sources, "boundary"), style=fact(capability_sources, "style"),
        external_entities=tuple(fact((key,)) for key in sorted(external)), approved_constraints=tuple(fact((key,)) for key in sorted(constraints)),
        components=tuple(components), interfaces=tuple(interfaces), data_flows=tuple(flows), aspects=tuple(aspects), open_architecture_questions=tuple(questions))


def validate_architecture_candidate(handoff, candidate):
    """Validate exact contracts and grounded semantics without component-name equality."""
    handoff = validate_plan_architecture_handoff(handoff)
    if type(candidate) is MappingProxyType:
        candidate = dict(candidate)
    architecture = validate_architecture_specification(candidate, handoff=handoff)
    baseline = generate_baseline_architecture(handoff)
    if set(architecture.readiness.blocking_reasons) - {"blocking_architecture_questions"}:
        raise ValueError("Architecture candidate is structurally incomplete.")
    for edge in architecture.interfaces:
        if not any(flow.source == edge.source and flow.destination == edge.destination
                   and set(edge.purpose.source_requirements) <= set(flow.purpose.source_requirements) for flow in architecture.data_flows):
            raise ValueError("Architecture candidate omits a material interface data flow.")
    if not set(baseline.objective.source_requirements) <= set(architecture.objective.source_requirements):
        raise ValueError("Architecture candidate changes the approved objective.")
    for required in baseline.aspects:
        if not any(item.area is required.area and set(required.responsibility.source_requirements) <= set(item.responsibility.source_requirements)
                   and {fact.canonical_json() for fact in required.constraints} <= {fact.canonical_json() for fact in item.constraints}
                   for item in architecture.aspects):
            raise ValueError("Architecture candidate removes a grounded architecture boundary or planning decision.")
    for required in baseline.components:
        if required.category not in {"worker", "storage", "adapter", "identity"}:
            continue
        if not any(item.category == required.category and item.trust_classification == required.trust_classification
                   and set(required.responsibility.source_requirements) <= set(item.responsibility.source_requirements) for item in architecture.components):
            raise ValueError("Architecture candidate removes a required ownership or isolation boundary.")
    for item in architecture.components:
        if item.category == "worker" and not any(c.category == "worker" and set(item.responsibility.source_requirements) <= set(c.responsibility.source_requirements) for c in baseline.components):
            raise ValueError("Architecture candidate invents unsupported background work.")
    for required in baseline.open_architecture_questions:
        if not any(q.area is required.area and q.source_requirements == required.source_requirements and q.blocking for q in architecture.open_architecture_questions):
            raise ValueError("Architecture candidate removes an unresolved material architecture question.")
    return architecture


def validate_architecture_adapter_candidate(handoff, adapter: ArchitectureCandidateAdapter):
    handoff = validate_plan_architecture_handoff(handoff)
    if not isinstance(adapter, ArchitectureCandidateAdapter):
        raise ValueError("Architecture adapter must implement the provider-neutral candidate interface.")
    return validate_architecture_candidate(handoff, adapter.create_candidate(handoff))
