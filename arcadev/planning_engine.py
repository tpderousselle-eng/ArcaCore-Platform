"""Deterministic baseline planning and untrusted candidate validation."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from .idea_plan_handoff import IdeaPlanHandoff, validate_idea_plan_handoff
from .software_plan import (
    Milestone,
    PlanItem,
    PlanProvenance,
    PlanRisk,
    PlanScope,
    PlanningQuestion,
    SoftwarePlan,
    UserJourney,
    validate_software_plan_candidate,
)


@runtime_checkable
class PlanCandidateAdapter(Protocol):
    """Provider-neutral boundary; implementations return inert candidate data only."""

    def create_candidate(self, handoff: IdeaPlanHandoff) -> Mapping[str, Any] | str: ...


def _direct(handoff: IdeaPlanHandoff, value: str) -> PlanItem:
    return PlanItem.create(value, PlanProvenance.APPROVED_IDEA, [value], handoff=handoff)


def _derived(handoff: IdeaPlanHandoff, value: str, *sources: str) -> PlanItem:
    return PlanItem.create(value, PlanProvenance.DERIVED, sources, handoff=handoff)


def _unique_items(items):
    result = {}
    for item in items:
        result.setdefault(item.value.casefold(), item)
    return tuple(result.values())


def generate_baseline_plan(handoff: IdeaPlanHandoff) -> SoftwarePlan:
    """Create a conservative plan using only the frozen approved IDEA."""

    handoff = validate_idea_plan_handoff(handoff.canonical_dict())
    if not handoff.eligible:
        raise ValueError("Baseline planning requires an eligible IDEA handoff.")
    intake = handoff.snapshot.intake
    features = tuple(item.value for item in intake.requested_features)
    platforms = tuple(item.value for item in intake.platform_targets)
    authentication = tuple(item.value for item in intake.authentication_requirements)
    integrations = tuple(item.value for item in intake.integration_requirements)
    deployments = tuple(item.value for item in intake.deployment_requirements)
    goal = intake.primary_goal.value
    description = intake.product_description.value

    capabilities = [_direct(handoff, value) for value in features]
    if authentication and not any(value.casefold() in {"no authentication", "no authentication required"} for value in authentication):
        capabilities.append(_derived(handoff, "Authentication", *authentication))
    capabilities.extend(_derived(handoff, f"{value} integration", value) for value in integrations if "no integration" not in value.casefold())
    capabilities = _unique_items(capabilities)

    objective = _derived(handoff, f"Provide {description.lower()} that enables users to {goal.rstrip('.').lower()}.", description, goal)
    problem = _derived(handoff, f"The intended users need a reliable way to {goal.rstrip('.').lower()}.", goal)
    scope = PlanScope.create(capabilities, (), handoff=handoff)

    journeys = []
    for feature in features:
        journeys.append(UserJourney.create(
            f"{feature} workflow",
            [_derived(handoff, f"A user completes {feature}.", feature)],
            handoff=handoff,
        ))
    functional = [_derived(handoff, f"The product shall support {item.value}.", *item.source_requirements) for item in capabilities]
    nonfunctional = [_direct(handoff, item.value) for item in intake.non_functional_requirements]
    if not nonfunctional:
        nonfunctional = [_derived(handoff, f"The product experience shall support {platform}.", platform) for platform in platforms]

    milestones = []
    feature_items = tuple(_direct(handoff, value) for value in features)
    if feature_items:
        milestones.append(Milestone.create("Core product workflows", feature_items, handoff=handoff))
    access_delivery = []
    access_delivery.extend(_direct(handoff, value) for value in authentication)
    access_delivery.extend(_direct(handoff, value) for value in integrations)
    access_delivery.extend(_direct(handoff, value) for value in deployments)
    if access_delivery:
        milestones.append(Milestone.create("Access, integration, and delivery", access_delivery, handoff=handoff))

    dependencies = [_derived(handoff, f"Availability of {value}", value) for value in integrations]
    if not dependencies:
        dependencies = [_derived(handoff, f"Compatibility with {platform}", platform) for platform in platforms]
    risks = []
    for feature in features:
        lowered = feature.casefold()
        if "build" in lowered:
            risks.append(PlanRisk(
                _derived(handoff, "Build execution requirements may vary by project.", feature),
                _derived(handoff, "Resolve the build execution environment before architecture.", feature),
            ))
        elif "publish" in lowered:
            risks.append(PlanRisk(
                _derived(handoff, "Publishing targets may impose different constraints.", feature),
                _derived(handoff, "Confirm publishing targets before architecture.", feature),
            ))
    if not risks:
        source = features[0] if features else goal
        risks.append(PlanRisk(
            _derived(handoff, "Implementation details may reveal additional constraints.", source),
            _derived(handoff, "Resolve material planning questions before architecture.", source),
        ))

    questions = []
    for feature in features:
        lowered = feature.casefold()
        if "asset" in lowered:
            questions.append(PlanningQuestion.create("What asset storage limits and retention rules are required?", True, [feature], handoff=handoff))
        if "build" in lowered:
            questions.append(PlanningQuestion.create("Which build execution environments and isolation rules are required?", True, [feature], handoff=handoff))
        if "publish" in lowered:
            questions.append(PlanningQuestion.create("Which publishing targets and release controls are required?", True, [feature], handoff=handoff))
    for integration in integrations:
        if integration.casefold() == "github":
            questions.append(PlanningQuestion.create("What GitHub repository synchronization behavior is required?", True, [integration], handoff=handoff))

    acceptance = [_derived(handoff, f"A user can complete {feature} through a validated workflow.", feature) for feature in features]
    acceptance.extend(_derived(handoff, f"The product supports {method} authentication as approved.", method) for method in authentication if "no authentication" not in method.casefold())
    constraints = []
    for collection in (intake.platform_targets, intake.authentication_requirements, intake.deployment_requirements, intake.explicit_constraints, intake.technology_preferences):
        constraints.extend(_direct(handoff, item.value) for item in collection)

    return SoftwarePlan.create(
        handoff=handoff,
        product_objective=objective,
        user_problem_statement=problem,
        scope=scope,
        in_scope_capabilities=capabilities,
        user_roles=[_direct(handoff, item.value) for item in intake.target_users],
        user_journeys=journeys,
        functional_requirements=functional,
        non_functional_requirements=nonfunctional,
        milestones=milestones,
        dependencies=dependencies,
        integrations=[_direct(handoff, value) for value in integrations],
        assumptions=(),
        risks=risks,
        open_planning_questions=questions,
        acceptance_criteria=acceptance,
        planning_constraints=_unique_items(constraints),
    )


def _material_capability_keys(plan: SoftwarePlan) -> set[str]:
    return {item.value.casefold() for item in (*plan.scope.in_scope, *plan.in_scope_capabilities)}


def validate_plan_candidate(handoff: IdeaPlanHandoff, candidate: SoftwarePlan | Mapping[str, Any] | str) -> SoftwarePlan:
    """Validate untrusted model/adapter output and recompute identity/readiness."""

    handoff = validate_idea_plan_handoff(handoff.canonical_dict())
    if isinstance(candidate, Mapping):
        candidate = dict(candidate)
    plan = validate_software_plan_candidate(candidate, handoff=handoff)
    baseline = generate_baseline_plan(handoff)
    approved = {
        item.value.casefold()
        for item in (
            *baseline.scope.in_scope,
            *baseline.in_scope_capabilities,
        )
    }
    invented = _material_capability_keys(plan) - approved
    if invented:
        raise ValueError("Plan candidate contains unsupported invented scope; represent uncertainty as a planning question.")
    return plan


def validate_adapter_candidate(handoff: IdeaPlanHandoff, adapter: PlanCandidateAdapter) -> SoftwarePlan:
    if not isinstance(adapter, PlanCandidateAdapter):
        raise ValueError("Planning adapter does not implement the provider-neutral candidate interface.")
    return validate_plan_candidate(handoff, adapter.create_candidate(handoff))
