"""Explicit minimal module TEST FIXTURE, independent of Gaming Studio authority."""
from dataclasses import replace
from functools import lru_cache

from arcadev import (
    IdeaIntake, IdeaFinalization, ProjectMetadata, create_idea_plan_handoff,
    generate_baseline_plan, SoftwarePlan, PlanningQuestion, PlanClarificationAnswer,
    planning_question_id, PlanFinalization, approve_plan, create_plan_architecture_handoff,
    generate_baseline_architecture, ArchitectureSpecification, ArchitectureQuestion,
    ArchitectureFinalization, approve_architecture, create_architecture_models_handoff,
    generate_baseline_domain_model, DomainModelSpecification, ModelField, ModelFact,
    model_element_id, ModelFinalization, approve_domain_model, create_models_backend_handoff,
    generate_baseline_backend_specification, BackendFinalization, approve_backend,
)
from arcadev.architecture_specification import _json
from arcadev.arcacore_generation_request import STANDARD_MODULE_CAPABILITY, STANDARD_TIMESTAMP_AUTHORITY, STANDARD_AUTHORITY, standard_module_capability
from arcadev.domain_model_specification import ModelConstraint, ModelAccessRequirement, ModelValueDomain
from tools.test_arcadev_idea_plan_handoff import _intent
from tools.test_arcadev_architecture_clarification import answer_for as architecture_answer
from tools.test_arcadev_model_clarification import answer_for as model_answer, fixture_choice as model_choice
from tools.test_arcadev_backend_clarification import answer_for as backend_answer


@lru_cache(maxsize=8)
def minimal_approved_backend(authentication=STANDARD_AUTHORITY, *, planning_decision=False, literal_default=False,
                             constraints=False, module_count=1, domains=False):
    assert module_count in {1, 2}
    capabilities = (STANDARD_MODULE_CAPABILITY,) if module_count == 1 else tuple(standard_module_capability(s) for s in ("first", "second"))
    values = ("Module Certification", "api_service", "A standard record module", "test operators",
        "Manage records", STANDARD_MODULE_CAPABILITY, "Local API", authentication,
        "No integrations", "Local", "PostgreSQL", STANDARD_TIMESTAMP_AUTHORITY)
    transcript = "TEST FIXTURE ONLY: " + "; ".join(values if module_count == 1 else (*values, *capabilities))
    def intent(value, scalar=False):
        return _intent(value, transcript, scalar=scalar)
    intake = IdeaIntake.create(original_user_request=transcript,
        proposed_project_name=intent(values[0], True), project_type=intent(values[1], True),
        product_description=intent(values[2], True), target_users=(intent(values[3]),),
        primary_goal=intent(values[4], True), requested_features=tuple(intent(c) for c in capabilities),
        platform_targets=(intent("Local API"),), authentication_requirements=(intent(authentication),),
        integration_requirements=(intent("No integrations"),), deployment_requirements=(intent("Local"),),
        technology_preferences=(intent("PostgreSQL"),), explicit_constraints=(intent(STANDARD_TIMESTAMP_AUTHORITY),))
    idea = IdeaFinalization.start(intake)
    project = idea.to_project(metadata=ProjectMetadata.create(created_at="2026-09-10T08:00:00Z"))
    handoff = create_idea_plan_handoff(project, idea)
    plan = generate_baseline_plan(handoff)
    assert not plan.open_planning_questions
    if planning_decision:
        question = PlanningQuestion.create("TEST FIXTURE ONLY: What implementation control applies to record updates?",
            False, (STANDARD_MODULE_CAPABILITY,), handoff=handoff)
        arguments = {key: getattr(plan, key) for key in ("product_objective", "user_problem_statement", "scope",
            "in_scope_capabilities", "user_roles", "user_journeys", "functional_requirements", "non_functional_requirements",
            "milestones", "dependencies", "integrations", "assumptions", "risks", "acceptance_criteria", "planning_constraints")}
        plan = SoftwarePlan.create(handoff=handoff, open_planning_questions=(question,), **arguments)
    plan_state = PlanFinalization.start(plan, handoff=handoff)
    if planning_decision:
        value = "Require an explicitly approved manual checkpoint for every record update."
        answer = PlanClarificationAnswer.create(target_plan_id=plan.plan_id, target_finalization_id=plan_state.finalization_id,
            target_question_id=planning_question_id(question), user_answer=value, normalized_values=(value,), evidence=(value,))
        plan_state = plan_state.resolve(answer, handoff=handoff)
    approved_plan = approve_plan(handoff=handoff, finalization=plan_state, approval_statement="TEST FIXTURE ONLY: explicitly approve this standard module scope.")
    ah = create_plan_architecture_handoff(source_project=handoff.resulting_project, approved_plan=approved_plan)
    architecture = generate_baseline_architecture(ah)
    owners = tuple(c for c in architecture.components if c.owned_capabilities and c.category == "service")
    assert len(owners) == module_count
    owner = owners[0]
    owner_capabilities = tuple(sorted(c for owner in owners for c in owner.owned_capabilities))
    owner_names = {owner.component_id: "Record" if module_count == 1 else "Record" + str(i + 1) for i, owner in enumerate(owners)}
    payloads = []
    for name, kind, required, mutable, unique in (
        ("id", "string", True, False, True), ("title", "string", True, True, False),
        ("created_at", "datetime", False, False, False), ("updated_at", "datetime", False, True, False),
        ("external_principal_id", "string", True, True, False),
    ):
        payloads.append(dict(name=name, logical_type=kind, required=required, collection=False,
            mutable=mutable, unique=unique, classification="external_identifier" if name == "external_principal_id" else "internal", value_domain_id=None, default_json=None))
    if literal_default:
        payloads[1]["default_json"] = _json("Untitled: record").strip()
    if constraints:
        payloads.append(dict(name="quantity", logical_type="integer", required=True, collection=False,
            mutable=True, unique=False, classification="internal", value_domain_id=None, default_json=None))
    if domains:
        payloads.append(dict(name="state", logical_type="enum", required=True, collection=False,
            mutable=True, unique=False, classification="internal", value_domain_id=None, default_json='"draft"'))
    areas = ("context", "style", "component", "interface", "security", "data_flow", "observability")
    questions = tuple(ArchitectureQuestion.create("TEST FIXTURE ONLY: approve exact " + p["name"] + " field authority?",
        False, owner_capabilities, areas[i % len(areas)], handoff=ah)
        for i, p in enumerate(payloads))
    extra_questions = tuple(ArchitectureQuestion.create("TEST FIXTURE ONLY: approve exact " + name + " authority?",
        False, owner_capabilities, area, handoff=ah) for name, area in
        (zip(("min_value", "max_value", "identity_access"), ("risk", "resilience", "authentication")) if constraints else ()))
    domain_question = ArchitectureQuestion.create("TEST FIXTURE ONLY: approve exact state value domain?",
        False, owner_capabilities, "integration", handoff=ah) if domains else None
    args = {key: getattr(architecture, key) for key in ("objective", "system_boundary", "style", "external_entities",
        "approved_constraints", "components", "interfaces", "data_flows", "aspects", "open_architecture_questions")}
    args.update(components=tuple(replace(c, name=owner_names[c.component_id]) if c.component_id in owner_names else c for c in architecture.components),
        open_architecture_questions=architecture.open_architecture_questions + questions + extra_questions + ((domain_question,) if domains else ()))
    architecture = ArchitectureSpecification.create(handoff=ah, **args)
    state = ArchitectureFinalization.start(architecture, handoff=ah)
    domain_payload = {"name": "State values", "values": ["draft", "published"]}
    if domains:
        state = state.resolve(architecture_answer(state, domain_question, _json(domain_payload).strip()), handoff=ah)
        domain_decision = next(d for d in state.decisions if d.accepted_values == (_json(domain_payload).strip(),))
        domain_id = model_element_id("domain", name=domain_payload["name"], source_requirements=(domain_decision.decision_id,))
        next(p for p in payloads if p["name"] == "state")["value_domain_id"] = domain_id
    answers = {q.question: _json(p).strip() for q, p in zip(questions, payloads)}
    for q in tuple(state.unresolved_questions):
        if q in extra_questions:
            continue
        value = answers.get(q.question, "Local ArcaCore module runtime")
        state = state.resolve(architecture_answer(state, q, value), handoff=ah)
    extra_payloads = []
    if constraints:
        constrained_entity = model_element_id("entity", name=owner_names[owner.component_id] + " state",
            source_requirements=(owner.component_id,), scope=owner.owned_capabilities)
        field_ids = {}
        for payload in payloads:
            decision = next(d for d in state.decisions if d.accepted_values == (_json(payload).strip(),))
            field_ids[payload["name"]] = model_element_id("field", name=payload["name"],
                source_requirements=(decision.decision_id,), scope=(constrained_entity,))
        extra_payloads = [
            dict(kind="min_value", entity_id=constrained_entity, field_ids=[field_ids["quantity"]], value_json="0"),
            dict(kind="max_value", entity_id=constrained_entity, field_ids=[field_ids["quantity"]], value_json="100"),
            dict(name="Identity lookup", entity_id=constrained_entity, field_ids=[field_ids["id"]], unique=True),
        ]
        for q, payload in zip(extra_questions, extra_payloads):
            state = state.resolve(architecture_answer(state, q, _json(payload).strip()), handoff=ah)
    approved = approve_architecture(handoff=ah, architecture=architecture, finalization=state, approval_statement="TEST FIXTURE ONLY: approve the standard module and exact field declarations.")
    mh = create_architecture_models_handoff(source_project=ah.resulting_project, approved_architecture=approved)
    model = generate_baseline_domain_model(mh)
    assert len(model.entities) == module_count
    entities = []
    for entity in model.entities:
        fixed = []
        for payload in payloads:
            decision = next(d for d in state.decisions if d.accepted_values == (_json(payload).strip(),))
            fact = ModelFact.create(handoff=mh, source_requirements=(decision.decision_id,))
            fid = model_element_id("field", name=payload["name"], source_requirements=fact.source_requirements, scope=(entity.entity_id,))
            fixed.append(ModelField(fid, evidence=fact, **payload))
        entities.append(replace(entity, fields=tuple(fixed), lifecycle_domain_ids=(domain_id,) if domains else ()))
    args = {key: getattr(model, key) for key in ("objective", "entities", "value_domains", "relationships", "constraints", "access_requirements", "open_model_questions")}
    args["entities"] = tuple(entities)
    if domains:
        args["value_domains"] = (ModelValueDomain(domain_id, domain_payload["name"], tuple(domain_payload["values"]),
            ModelFact.create(handoff=mh, source_requirements=(domain_decision.decision_id,))),)
    if constraints:
        constrained = []
        accesses = []
        for payload in extra_payloads:
            decision = next(d for d in state.decisions if d.accepted_values == (_json(payload).strip(),))
            fact = ModelFact.create(handoff=mh, source_requirements=(decision.decision_id,))
            is_constraint = "kind" in payload
            identity = model_element_id("constraint" if is_constraint else "access", name=payload.get("kind", payload.get("name")),
                source_requirements=fact.source_requirements, scope=(constrained_entity, *payload["field_ids"]))
            body = {**payload, "field_ids": tuple(payload["field_ids"]), "evidence": fact}
            if is_constraint:
                constrained.append(ModelConstraint(identity, **body))
            else:
                accesses.append(ModelAccessRequirement(identity, **body))
        args["constraints"], args["access_requirements"] = tuple(constrained), tuple(accesses)
    model = DomainModelSpecification.create(handoff=mh, **args)
    ms = ModelFinalization.start(model, handoff=mh)
    for q in model.open_model_questions:
        choice = ("independent",) if q.area.value == "relationship" and module_count > 1 else model_choice(q, model)
        ms = ms.resolve(model_answer(ms, q, choice), handoff=mh)
    statement = "TEST FIXTURE ONLY: approve named fields, timestamps, identity-only uniqueness and lookup."
    if constraints:
        statement = "TEST FIXTURE ONLY: approve named fields, timestamps, declared constraints and identity lookup."
    am = approve_domain_model(handoff=mh, model=model, finalization=ms, approval_statement=statement)
    bh = create_models_backend_handoff(source_project=mh.resulting_project, approved_domain_model=am)
    backend = generate_baseline_backend_specification(bh)
    bs = BackendFinalization.start(backend, handoff=bh)
    for q in backend.open_backend_questions:
        bs = bs.resolve(backend_answer(bs, q), handoff=bh)
    return approve_backend(handoff=bh, backend=backend, finalization=bs, approval_statement="TEST FIXTURE ONLY: explicitly approve full standard module backend authority.")
