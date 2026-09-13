"""Fixed production clarification authority, bounded to five approved referents.

The trusted mapping below records this batch's actual user authority. It is not
a conversational parser: changing a response, proposal or decision in a supplied
file cannot authorize anything. Public clarification contracts perform replay.
"""

from .clarification import ClarificationAnswer, IdeaFinalization, ResolutionAction
from .gaming_studio_idea import AUTHENTICATION, materialize_idea, validate_production_idea
from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, canonical_bytes, digest_bytes, parse_authority,
)


AUTHORIZATION_SCHEMA = "arcadev.gaming_studio.clarification_authorization"
AUTHORIZATION_VERSION = 1
ORDER = (
    "project_type", "target_users", "platform_targets",
    "authentication_requirements", "deployment_requirements",
)
# Exact responses supplied by the user in the controlled production batch.
RESPONSES = (
    "Yes cause I want them to be able to do what ever they want with their game after it's build, maybe in the long run we create a social platform where they can show off their game. But yes for pc web mobile other approve targets, web applications all sound good to me",
    "I approve",
    "yes i wanted A & B I approve all best decisions",
    "Yes, but with the gaming studio they will have to upgrade for that access . we can dicuss that more later",
    "I approve cloud-hosted ArcaCentum deployment with isolated build environments for Gaming Studio.",
)
PROPOSALS = (
    "Gaming Studio itself is primarily a browser-based ArcaCentum application. Games created through Gaming Studio are not thereby limited to web delivery.",
    "Individual game creators and small/indie game-development teams, including both non-programmers and experienced developers who want to turn game ideas into playable software using AI-assisted development.",
    "A. Gaming Studio itself runs as a Web application. B. Games created with Gaming Studio initially may target: PC, Web, Android, iOS. Additional targets require later explicit approval and safe support.",
    "Gaming Studio uses centralized ArcaCentum authentication with email/password and Google sign-in. Credentials, OAuth tokens, passwords and secrets remain outside Gaming Studio domain records in dedicated ArcaCentum identity/secret infrastructure.",
    "Gaming Studio is a cloud-hosted ArcaCentum application with isolated build environments for user-generated game execution.",
)
VALUES = (
    ("web_application",),
    (PROPOSALS[1],),
    ("Gaming Studio: Web application", "Created games: PC", "Created games: Web",
     "Created games: Android", "Created games: iOS"),
    (AUTHENTICATION, "Centralized ArcaCentum authentication", "Email/password", "Google sign-in"),
    ("Cloud-hosted ArcaCentum deployment", "Isolated build environments for user-generated game execution"),
)
EVIDENCE = (
    "web applications all sound good to me", "I approve",
    "yes i wanted A & B I approve all best decisions", "Yes", RESPONSES[4],
)


def authorization_package(intent):
    """Build the only authorized envelope and sequential public answer records."""
    finalization = IdeaFinalization.start(materialize_idea(intent))
    approvals = []
    for index, key in enumerate(ORDER):
        refine = key in {"target_users", "authentication_requirements"}
        previous = tuple(item.value for item in getattr(finalization.current_intake, key)) if refine else ()
        answer = ClarificationAnswer.create(
            target_intake_id=finalization.current_intake_id, requirement=key,
            user_answer=RESPONSES[index], normalized_values=VALUES[index],
            evidence=(EVIDENCE[index],),
            action=ResolutionAction.REFINE_EXPLICIT if refine else ResolutionAction.ANSWER,
            expected_previous_values=previous,
        )
        result = finalization.resolve(answer)
        proposal = PROPOSALS[index]
        approvals.append({
            "ordinal": index + 1, "requirement": key,
            "provenance": "explicit_user",
            "approved_proposal": proposal,
            "proposal_digest": digest_bytes(proposal.encode("utf-8")),
            "relationship": "response_approves_only_this_immediately_preceding_requirement_proposal",
            "answer": answer.canonical_dict(),
            "resulting_intake_id": result.current_intake_id,
        })
        finalization = result
    return {
        "schema": AUTHORIZATION_SCHEMA, "schema_version": AUTHORIZATION_VERSION,
        "production_intent_digest": APPROVED_INTENT_DIGEST,
        "seed_intake_id": finalization.initial_intake_id,
        "answer_order": list(ORDER), "approvals": approvals,
        "deferred_context": {
            "social_community": {
                "source_ordinal": 1,
                "quote": "maybe in the long run we create a social platform where they can show off their game",
                "disposition": "future_context_only_not_initial_scope",
            },
            "upgraded_access": {
                "source_ordinal": 4,
                "quote": "with the gaming studio they will have to upgrade for that access . we can dicuss that more later",
                "meaning": "Gaming Studio requires an upgraded/paid ArcaCentum access level.",
                "undecided": ["exact price", "plan name", "tier design", "trial rules", "usage limits", "billing mechanics"],
                "disposition": "deferred_product_access_context_no_implementation_authority",
            },
        },
    }


def validate_authorization(data, intent):
    """Exact allowlisting rejects unknown authority, secrets and fabricated answers."""
    value = parse_authority(data)
    expected = authorization_package(intent)
    if data != canonical_bytes(expected):
        raise ValueError("Clarification authorization differs from the five approved decisions.")
    return value


def replay_authorization(data, intent):
    value = validate_authorization(data, intent)
    seed = validate_production_idea(intent, materialize_idea(intent))
    result = IdeaFinalization.start(seed)
    for approval in value["approvals"]:
        answer = ClarificationAnswer.from_dict(approval["answer"])
        result = result.resolve(answer)
        if result.current_intake_id != approval["resulting_intake_id"]:
            raise ValueError("Clarification authority has stale intake lineage.")
    return IdeaFinalization.from_dict(result.canonical_dict())
