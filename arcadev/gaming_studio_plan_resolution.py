"""Three fixed production PLAN approvals; no general conversational parser.

The trusted constants record the user's bounded authority. Supplied documents
cannot change a referent, response, accepted value or finalization lineage.
The original PLAN package remains an immutable historical checkpoint.
"""

from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes,
    local_authority_path, parse_authority, read_authority,
)
from .gaming_studio_plan import production_plan_inputs, validate_production_plan_package
from .plan_clarification import (
    PlanClarificationAnswer, PlanFinalization, planning_question_id,
)
from .software_plan import SoftwarePlan


AUTHORIZATION_SCHEMA = "arcadev.gaming_studio.plan_clarification_authorization"
AUTHORIZATION_VERSION = 1
# Pinned canonical production envelope, including the sequential public IDs.
# Check before expensive upstream reconstruction; rehashing altered input cannot
# replace this trusted root. Successful validation still replays current sources.
APPROVED_AUTHORIZATION_DIGEST = "360fb151709a031f49109726f2c3f3b73c4d0c13364baadf2edf87f3b0a5562c"
PLAN_ID = "arcadev_plan_9aed1a01dad6e95cb75b6db67730dd5b"
ORDER = (
    "arcadev_question_64610a51eaf261a7116813cf9cb32d91",
    "arcadev_question_06fa970b49a43c4d5442756aa4361ccc",
    "arcadev_question_3386cafaf9fe1e6672db5b0a9bed716f",
)
QUESTIONS = (
    "What asset storage limits and retention rules are required?",
    "Which build execution environments and isolation rules are required?",
    "Which publishing targets and release controls are required?",
)
RESPONSES = (
    "I approve the recommended Gaming Studio asset storage and retention policy.",
    "I approve isolated disposable build environments with strict resource, network, secret, and filesystem boundaries for Gaming Studio.",
    "I approve PC, Web, Android, and iOS publishing/export with validation gates, user-controlled releases, and direct store publishing only through explicitly supported integrations.",
)
# Preserve the approved wording; line wrapping is presentation only.
PROPOSALS = (
    "Gaming Studio uses configurable storage quotas tied to the user’s ArcaCentum entitlement rather than hard-coding storage into the product.\n\n"
    "For initial production:\n\n"
    "- provide 50 GB of active project-asset storage per paid Gaming Studio account\n"
    "- user-created project assets are retained while the project/account remains active\n"
    "- deleted assets/projects remain recoverable for 30 days before permanent deletion\n"
    "- temporary build/intermediate files may be automatically purged after 7 days\n"
    "- final/exported builds may be retained for 30 days unless the user explicitly keeps/pins them\n"
    "- additional storage capacity can be offered later without changing the core storage architecture\n"
    "- Marketplace asset retention is outside current initial scope",

    "All user-generated game code and builds run in isolated, disposable execution environments separate from the ArcaCentum control plane.\n\n"
    "Each build gets a clean sandbox with explicit:\n\n"
    "- CPU limits\n- memory limits\n- disk limits\n- network limits\n- execution-time limits\n\n"
    "Additional approved rules:\n\n"
    "- no host filesystem exposure\n- no internal service exposure by default\n"
    "- no secret-store exposure by default\n- no access to another customer's data\n"
    "- network denied by default and enabled only through approved allowlisted workflows when required\n"
    "- build environment destroyed after completion\n"
    "- only approved outputs, logs and metadata retained\n- no privileged containers/processes\n"
    "- no direct production database access\n"
    "- no inherited secrets unless explicitly injected for one approved integration\n"
    "- malware/static security checks on outputs before ArcaCentum hosting or publishing",

    "- initial publishing/export targets are PC, Web, Android and iOS\n"
    "- releases are user-controlled\n- publication/export workflows use validation gates\n"
    "- build/test requirements must pass where required\n- required release metadata must be present\n"
    "- platform-specific requirements must be satisfied\n"
    "- export/download is distinct from direct store submission\n"
    "- users may export approved build artifacts\n"
    "- direct external-store publishing occurs only through explicitly supported integrations\n"
    "- store/developer credentials belong to the user's connected developer accounts\n"
    "- unsupported targets or failed validation block direct publishing\n"
    "- consoles are outside initial scope",
)
VALUES = (
    (
        "Configurable storage quotas tied to the user's ArcaCentum entitlement",
        "50 GB of active project-asset storage per paid Gaming Studio account",
        "User-created project assets retained while the project/account remains active",
        "Deleted assets/projects recoverable for 30 days before permanent deletion",
        "Temporary build/intermediate files may be automatically purged after 7 days",
        "Final/exported builds may be retained for 30 days unless explicitly kept/pinned by the user",
        "Additional storage capacity can be offered later without changing the core storage architecture",
        "Marketplace asset retention is outside current initial scope",
    ),
    (
        "All user-generated game code and builds run in isolated, disposable execution environments separate from the ArcaCentum control plane",
        "Each build gets a clean sandbox with explicit CPU, memory, disk, network and execution-time limits",
        "No host filesystem exposure",
        "No internal service exposure by default",
        "No secret-store exposure by default",
        "No access to another customer's data",
        "Network denied by default; enabled only through approved allowlisted workflows when required",
        "Build environment destroyed after completion",
        "Only approved outputs, logs and metadata retained",
        "No privileged containers/processes",
        "No direct production database access",
        "No inherited secrets unless explicitly injected for one approved integration",
        "Malware/static security checks on outputs before ArcaCentum hosting or publishing",
    ),
    (
        "Initial created-game publishing/export targets: PC, Web, Android and iOS",
        "Releases are user-controlled",
        "Publication/export workflows use validation gates",
        "Build/test requirements must pass where required",
        "Required release metadata must be present",
        "Platform-specific requirements must be satisfied",
        "Export/download is distinct from direct store submission",
        "Users may export approved build artifacts",
        "Direct external-store publishing only through explicitly supported integrations",
        "Store/developer credentials belong to the user's connected developer accounts",
        "Unsupported targets or failed validation block direct publishing",
        "Consoles are outside initial scope",
    ),
)
RELATIONSHIPS = (
    "response_approves_only_this_question_and_immediately_preceding_policy",
    "response_approves_only_this_question_and_immediately_preceding_isolation_controls",
    "direct_response_and_user_supplied_approved_interpretation_for_only_this_question",
)


def _production_inputs(directory):
    directory = local_authority_path(directory)
    validate_production_plan_package(directory)
    handoff = production_plan_inputs(directory)
    plan = SoftwarePlan.from_json(read_authority(
        directory / "production_plan" / "software_plan.json").decode("utf-8"), handoff=handoff)
    if plan.plan_id != PLAN_ID or tuple(planning_question_id(q) for q in plan.open_planning_questions) != ORDER:
        raise ValueError("PLAN clarification authority targets a different production plan or questions.")
    if tuple(q.question for q in plan.open_planning_questions) != QUESTIONS:
        raise ValueError("Production planning questions have been rewritten.")
    return plan, handoff


def _authorization(plan, handoff):
    current = PlanFinalization.start(plan, handoff=handoff)
    initial_id = current.finalization_id
    approvals = []
    for index, question_id in enumerate(ORDER):
        answer = PlanClarificationAnswer.create(
            target_plan_id=plan.plan_id, target_finalization_id=current.finalization_id,
            target_question_id=question_id, user_answer=RESPONSES[index],
            normalized_values=VALUES[index], evidence=(RESPONSES[index],),
        )
        result = current.resolve(answer, handoff=handoff)
        approvals.append({
            "ordinal": index + 1, "question_id": question_id, "question": QUESTIONS[index],
            "approved_proposal": PROPOSALS[index],
            "proposal_digest": digest_bytes(PROPOSALS[index].encode("utf-8")),
            "relationship": RELATIONSHIPS[index], "provenance": "explicit_user",
            "answer": answer.canonical_dict(), "resulting_finalization_id": result.finalization_id,
        })
        current = result
        if current.conflicts:
            break
    return {
        "schema": AUTHORIZATION_SCHEMA, "schema_version": AUTHORIZATION_VERSION,
        "product_key": "gaming_studio", "production_intent_digest": APPROVED_INTENT_DIGEST,
        "plan_id": plan.plan_id, "initial_finalization_id": initial_id,
        "answer_order": list(ORDER), "approvals": approvals,
        "authority_scope": "only_three_planning_clarifications_not_complete_plan_approval",
    }


def plan_authorization_package(directory=AUTHORITY_DIRECTORY):
    """Return inert authority bytes' contents, bound through sequential public replay."""
    return _authorization(*_production_inputs(directory))


def validate_plan_authorization(data, directory=AUTHORITY_DIRECTORY):
    value = parse_authority(data)
    if digest_bytes(data) != APPROVED_AUTHORIZATION_DIGEST:
        raise ValueError("PLAN authorization differs from the three exact approved decisions.")
    if data != canonical_bytes(plan_authorization_package(directory)):
        raise ValueError("PLAN authorization differs from the three exact approved decisions.")
    return value
