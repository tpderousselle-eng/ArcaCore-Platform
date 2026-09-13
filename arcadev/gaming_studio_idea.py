"""Conservative production IDEA reconstruction through certified public contracts.

This is a fixed, evidence-audited mapping of one approved source, not a general
language parser or an adapter allowed to supply new product decisions.
"""

from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, ProductionIntent, digest_bytes,
)
from .idea_intake import (
    ClarificationRequirement, Confidence, IdeaIntake, IntentProvenance,
    IntentValue, validate_candidate,
)


CHECKPOINT_SCHEMA = "arcadev.gaming_studio.production_checkpoint"
CHECKPOINT_SCHEMA_VERSION = 1
REVIEW_SCHEMA = "arcadev.gaming_studio.idea_review"
REVIEW_SCHEMA_VERSION = 1

DESCRIPTION = "Build an AI-native game development environment within the ArcaCentum ecosystem that allows a user to describe a game idea in natural language and move through a controlled software/game-development lifecycle."
AUTHENTICATION = "Authentication must identify the owner/user without storing authentication credentials inside Gaming Studio domain records."
PLATFORMS = "supporting publishing workflows for approved target platforms"
ISOLATION = "Game build execution must eventually occur in isolated execution environments rather than executing arbitrary user-generated code directly inside the ArcaCentum control plane."
ORCHESTRATION = "Gaming Studio should use ArcaDev as the development orchestrator and ArcaCore as the certified generation/runtime foundation."
PERSISTENCE = "Required persistent product-state areas are:"
STATE_AREAS = (
    "Game Project — the user’s game project and its controlled lifecycle.",
    "Assets — references and metadata for game assets used by the project.",
    "Builds — build requests, status and validated build outcomes.",
    "GitHub Integration — non-secret repository identity/synchronization state.",
    "Publishing — release/publishing workflow state and outcomes.",
)
FEATURES = (
    "describe a game idea in natural language and move through a controlled software/game-development lifecycle",
    "planning the game",
    "defining architecture and game systems",
    "managing game-project state and assets",
    "generating code and project files",
    "testing and previewing builds",
    "detecting and repairing failures",
    "maintaining version/history through GitHub integration",
    "producing distributable builds",
    PLATFORMS,
)
CONSTRAINTS = (
    ORCHESTRATION,
    "ArcaDev determines what is authorized to be built; ArcaCore performs only capabilities it has certified support for.",
    "Tokens, passwords, API keys and other credentials remain in dedicated secret/integration infrastructure.",
    "A build, integration or publishing capability must remain blocked when ArcaCore cannot represent it safely.",
    "The system must never silently omit unsupported approved functionality or claim a partial build is complete.",
    "Initial Gaming Studio scope does not automatically include unrelated features such as multiplayer services, social networks, marketplace/e-commerce, subscriptions, achievements, analytics, AI NPC systems or other product capabilities unless they are explicitly added and approved later.",
)

# Each unresolved choice has its own question, source context and rationale.
# These are requests for authority, never proposed or default answers.
CLARIFICATIONS = {
    "project_type": (
        "What canonical software project type should Gaming Studio use?",
        (DESCRIPTION,),
        "The approved text describes a game development environment but does not select a canonical software project type.",
    ),
    "target_users": (
        "Who are the initial target users of Gaming Studio?",
        (DESCRIPTION,),
        "The text authorizes a user describing a game idea; it does not specify the initial target-user segment. The broad user reference is retained without choosing a segment.",
    ),
    "platform_targets": (
        "Which platforms must Gaming Studio support, and which initial game build/publishing target platforms are approved?",
        (PLATFORMS,),
        "Approved target platforms are mentioned but none are named; the environment's own platform targets are also unspecified.",
    ),
    "authentication_requirements": (
        "What authentication mechanism should identify the Gaming Studio owner/user while keeping credentials outside domain records?",
        (AUTHENTICATION,),
        "The identification and credential-separation boundary is explicit, but no authentication mechanism is selected.",
    ),
    "deployment_requirements": (
        "Where or how should Gaming Studio be deployed?",
        (DESCRIPTION, ISOLATION),
        "ArcaCentum membership and eventual isolated game-build execution do not select hosting or deployment topology for Gaming Studio.",
    ),
}


def materialize_idea(intent: ProductionIntent) -> IdeaIntake:
    """Reconstruct only exact quoted facts; let IdeaIntake compute readiness."""
    intent = ProductionIntent.from_bytes(intent.canonical_bytes())
    request = intent.approved_intent

    def explicit(value: str, *additional_evidence: str) -> IntentValue:
        evidence = (value, *additional_evidence)
        if any(quote not in request for quote in evidence):
            raise ValueError("Production mapping evidence must be an exact source quote.")
        return IntentValue.create(value=value, provenance=IntentProvenance.EXPLICIT,
                                  confidence=Confidence.HIGH, evidence=evidence,
                                  original_user_request=request)

    questions = [
        ClarificationRequirement.create(
            requirement=key, question=question, blocking=True,
            evidence=evidence, original_user_request=request,
        )
        for key, (question, evidence, _) in CLARIFICATIONS.items()
    ]
    intake = IdeaIntake.create(
        original_user_request=request,
        proposed_project_name=explicit("Gaming Studio"),
        product_description=explicit(DESCRIPTION),
        primary_goal=explicit(FEATURES[0]),
        target_users=[explicit("a user", DESCRIPTION)],
        requested_features=[*(explicit(value) for value in FEATURES),
                            *(explicit(value, PERSISTENCE) for value in STATE_AREAS)],
        authentication_requirements=[explicit(AUTHENTICATION)],
        integration_requirements=[explicit("External integrations such as GitHub must store only non-secret identifiers/references.")],
        explicit_constraints=[explicit(value) for value in CONSTRAINTS],
        non_functional_requirements=[explicit(ISOLATION)],
        unresolved_requirements=questions,
    )
    return validate_candidate(request, intake.canonical_json())


def validate_production_idea(intent: ProductionIntent, intake: IdeaIntake) -> IdeaIntake:
    expected = materialize_idea(intent)
    actual = validate_candidate(intent.approved_intent, intake.canonical_json())
    if actual.canonical_json() != expected.canonical_json():
        raise ValueError("IDEA differs from the evidence-audited production reconstruction.")
    return actual


def checkpoint_manifest(intent: ProductionIntent, intake: IdeaIntake) -> dict:
    intake = validate_production_idea(intent, intake)
    ready = intake.readiness.ready_for_plan
    return {
        "schema": CHECKPOINT_SCHEMA,
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        "current_stage": "IDEA",
        "status": "IDEA_READY" if ready else "BLOCKED_PENDING_IDEA_CLARIFICATION",
        "idea_intake_digest": digest_bytes(intake.canonical_json().encode("utf-8")),
        "project_id": None,
        "ready_for_plan": ready,
        "blocking_requirement_keys": list(intake.readiness.blocking_requirements),
        "next_authorized_action": (
            "COLLECT_AUTHORIZED_PROJECT_METADATA" if ready
            else "COLLECT_EXPLICIT_IDEA_CLARIFICATIONS"
        ),
    }


def clarification_review(intent: ProductionIntent, intake: IdeaIntake) -> dict:
    intake = validate_production_idea(intent, intake)
    normalized = {source.value: [] for source in (
        IntentProvenance.EXPLICIT, IntentProvenance.DERIVED, IntentProvenance.ASSUMED,
    )}
    for field, raw in intake.canonical_dict().items():
        values = raw if isinstance(raw, list) else [raw]
        for item in values:
            if isinstance(item, dict) and "value" in item:
                normalized[item["provenance"]].append({"field": field, **item})
    for values in normalized.values():
        values.sort(key=lambda item: (item["field"], item["value"]))
    requirements = [
        {**item.canonical_dict(), "why_unresolved": CLARIFICATIONS[item.requirement][2]}
        for item in intake.unresolved_requirements
    ]
    checkpoint = checkpoint_manifest(intent, intake)
    return {
        "schema": REVIEW_SCHEMA,
        "schema_version": REVIEW_SCHEMA_VERSION,
        "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        "normalization_method": "Evidence-audited reconstruction through public IdeaIntake.create and IntentValue.create contracts.",
        "normalized_values": normalized,
        "unresolved_requirements": requirements,
        "readiness": intake.readiness.canonical_dict(),
        "current_stage": checkpoint["current_stage"],
        "status": checkpoint["status"],
        "next_authorized_action": checkpoint["next_authorized_action"],
        "plan_transition_performed": False,
        "project_created": False,
    }
