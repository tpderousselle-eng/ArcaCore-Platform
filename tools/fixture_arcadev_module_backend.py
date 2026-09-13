"""Explicit minimal module TEST FIXTURE, independent of Gaming Studio authority."""
from dataclasses import replace
from functools import lru_cache

from arcadev import (
    IdeaIntake, IdeaFinalization, ProjectMetadata, create_idea_plan_handoff,
    generate_baseline_plan, PlanFinalization, approve_plan, create_plan_architecture_handoff,
    generate_baseline_architecture, ArchitectureSpecification, ArchitectureQuestion,
    ArchitectureFinalization, approve_architecture, create_architecture_models_handoff,
    generate_baseline_domain_model, DomainModelSpecification, ModelField, ModelFact,
    model_element_id, ModelFinalization, approve_domain_model, create_models_backend_handoff,
    generate_baseline_backend_specification, BackendFinalization, approve_backend,
)
from arcadev.architecture_specification import _json
from arcadev.arcacore_generation_request import STANDARD_MODULE_CAPABILITY, STANDARD_TIMESTAMP_AUTHORITY, STANDARD_AUTHORITY
from tools.test_arcadev_idea_plan_handoff import _intent
from tools.test_arcadev_architecture_clarification import answer_for as architecture_answer
from tools.test_arcadev_model_clarification import answer_for as model_answer, fixture_choice as model_choice
from tools.test_arcadev_backend_clarification import answer_for as backend_answer


@lru_cache(maxsize=2)
def minimal_approved_backend(authentication=STANDARD_AUTHORITY):
    values = ("Module Certification", "api_service", "A standard record module", "test operators",
        "Manage records", STANDARD_MODULE_CAPABILITY, "Local API", authentication,
        "No integrations", "Local", "PostgreSQL", STANDARD_TIMESTAMP_AUTHORITY)
    transcript = "TEST FIXTURE ONLY: " + "; ".join(values)
    def intent(value, scalar=False):
        return _intent(value, transcript, scalar=scalar)
    intake = IdeaIntake.create(original_user_request=transcript,
        proposed_project_name=intent(values[0], True), project_type=intent(values[1], True),
        product_description=intent(values[2], True), target_users=(intent(values[3]),),
        primary_goal=intent(values[4], True), requested_features=(intent(STANDARD_MODULE_CAPABILITY),),
        platform_targets=(intent("Local API"),), authentication_requirements=(intent(authentication),),
        integration_requirements=(intent("No integrations"),), deployment_requirements=(intent("Local"),),
        technology_preferences=(intent("PostgreSQL"),), explicit_constraints=(intent(STANDARD_TIMESTAMP_AUTHORITY),))
    idea = IdeaFinalization.start(intake)
    project = idea.to_project(metadata=ProjectMetadata.create(created_at="2026-09-10T08:00:00Z"))
    handoff = create_idea_plan_handoff(project, idea)
    plan = generate_baseline_plan(handoff)
    assert not plan.open_planning_questions
    approved_plan = approve_plan(handoff=handoff, finalization=PlanFinalization.start(plan, handoff=handoff), approval_statement="TEST FIXTURE ONLY: explicitly approve this standard module scope.")
    ah = create_plan_architecture_handoff(source_project=handoff.resulting_project, approved_plan=approved_plan)
    architecture = generate_baseline_architecture(ah)
    owner = next(c for c in architecture.components if c.owned_capabilities and c.category == "service")
    payloads = []
    for name, kind, required, mutable, unique in (
        ("id", "string", True, False, True), ("title", "string", True, True, False),
        ("created_at", "datetime", False, False, False), ("updated_at", "datetime", False, True, False),
        ("external_principal_id", "string", True, True, False),
    ):
        payloads.append(dict(name=name, logical_type=kind, required=required, collection=False,
            mutable=mutable, unique=unique, classification="external_identifier" if name == "external_principal_id" else "internal", value_domain_id=None, default_json=None))
    questions = tuple(ArchitectureQuestion.create("TEST FIXTURE ONLY: approve exact " + p["name"] + " field authority?",
        False, owner.owned_capabilities, area, handoff=ah)
        for p, area in zip(payloads, ("context", "style", "component", "interface", "security")))
    args = {key: getattr(architecture, key) for key in ("objective", "system_boundary", "style", "external_entities",
        "approved_constraints", "components", "interfaces", "data_flows", "aspects", "open_architecture_questions")}
    args.update(components=tuple(replace(c, name="Record") if c == owner else c for c in architecture.components),
        open_architecture_questions=architecture.open_architecture_questions + questions)
    architecture = ArchitectureSpecification.create(handoff=ah, **args)
    state = ArchitectureFinalization.start(architecture, handoff=ah)
    answers = {q.question: _json(p).strip() for q, p in zip(questions, payloads)}
    for q in tuple(state.unresolved_questions):
        value = answers.get(q.question, "Local ArcaCore module runtime")
        state = state.resolve(architecture_answer(state, q, value), handoff=ah)
    approved = approve_architecture(handoff=ah, architecture=architecture, finalization=state, approval_statement="TEST FIXTURE ONLY: approve the standard module and exact field declarations.")
    mh = create_architecture_models_handoff(source_project=ah.resulting_project, approved_architecture=approved)
    model = generate_baseline_domain_model(mh)
    assert len(model.entities) == 1
    entity = model.entities[0]
    fixed = []
    for payload in payloads:
        decision = next(d for d in state.decisions if d.accepted_values == (_json(payload).strip(),))
        fact = ModelFact.create(handoff=mh, source_requirements=(decision.decision_id,))
        fid = model_element_id("field", name=payload["name"], source_requirements=fact.source_requirements, scope=(entity.entity_id,))
        fixed.append(ModelField(fid, evidence=fact, **payload))
    args = {key: getattr(model, key) for key in ("objective", "entities", "value_domains", "relationships", "constraints", "access_requirements", "open_model_questions")}
    args["entities"] = (replace(entity, fields=tuple(fixed)),)
    model = DomainModelSpecification.create(handoff=mh, **args)
    ms = ModelFinalization.start(model, handoff=mh)
    for q in model.open_model_questions:
        ms = ms.resolve(model_answer(ms, q, model_choice(q, model)), handoff=mh)
    am = approve_domain_model(handoff=mh, model=model, finalization=ms, approval_statement="TEST FIXTURE ONLY: approve named fields, timestamps, identity-only uniqueness and lookup.")
    bh = create_models_backend_handoff(source_project=mh.resulting_project, approved_domain_model=am)
    backend = generate_baseline_backend_specification(bh)
    bs = BackendFinalization.start(backend, handoff=bh)
    for q in backend.open_backend_questions:
        bs = bs.resolve(backend_answer(bs, q), handoff=bh)
    return approve_backend(handoff=bh, backend=backend, finalization=bs, approval_statement="TEST FIXTURE ONLY: explicitly approve full standard module backend authority.")
