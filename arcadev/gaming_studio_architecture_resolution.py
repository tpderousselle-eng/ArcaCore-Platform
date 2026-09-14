"""Eight verbatim user decisions, bound to immutable production architecture.

Only trusted repository constants supply authority. External JSON is compared
with this envelope and sequential public replay; it cannot approve architecture.
"""

from .architecture_clarification import ArchitectureClarificationAnswer, ArchitectureResolutionOutcome
from .architecture_specification import architecture_question_id
from .gaming_studio_architecture import ARCHITECTURE_AREA
from .gaming_studio_architecture_checkpoint import validate_production_architecture_checkpoint
from .gaming_studio_architecture_finalization import production_architecture_initial_state
from .gaming_studio_intent import (
    APPROVED_INTENT_DIGEST, AUTHORITY_DIRECTORY, canonical_bytes, digest_bytes,
    local_authority_path, parse_authority,
)


AUTHORIZATION_SCHEMA = "arcadev.gaming_studio.architecture_clarification_authorization"
AUTHORIZATION_VERSION = 1
AUTHORIZATION_PACKAGE_VERSION = 1
# A rejection filter only: successful validation still reconstructs all sources
# and all eight decisions through the public contracts below.
APPROVED_AUTHORIZATION_DIGEST = "416ee44e579e01121e737bc2281f827dd7a5e820d5fb680ec40aa9a1a3dc9c93"
RESOLUTION_AREA = ARCHITECTURE_AREA + "/architecture_resolution"
PROJECT_ID = "arcadev_969321c8959864fe18393b9d2b551063"
ARCHITECTURE_ID = "arcadev_architecture_1365b59c168d82ba7d9ac0fb604afadf"
INITIAL_FINALIZATION_ID = "arcadev_architecture_final_cca8f5b914aeeefc41b86ab649989135"
ORDER = (
    'arcadev_architecture_question_44f2ca1153bdd0c4e2ad35bb615ccfd4',
    'arcadev_architecture_question_4cbf21d1a4defc43dfb91fe5118fa277',
    'arcadev_architecture_question_76c105bf89ae20d9a442f2fc61314394',
    'arcadev_architecture_question_b44a16ef956c182be4dd1a9638001d5b',
    'arcadev_architecture_question_c36965b51d972beae7b149fd091f899d',
    'arcadev_architecture_question_c87ceb1a789975aa2101ea8343eb54b2',
    'arcadev_architecture_question_e4c9734adfb93686b76444ed068c6451',
    'arcadev_architecture_question_f031ffe0d00fcab1cb9d66feb9e37121',
)
QUESTIONS = (
    'Which asset storage implementation enforces the approved storage and deletion policy?',
    'Which worker isolation implementation enforces the approved build isolation?',
    'Which background job execution mechanism dispatches and tracks the approved isolated builds?',
    'Which logical deployment-unit topology realizes the approved deployment target?',
    'Which frontend implementation will deliver the approved web experience?',
    'Which logical deployment-unit topology realizes the approved deployment target?',
    'Which publishing implementation enforces the approved user-controlled release actions?',
    'Which primary persistence implementation supports the approved managed state?',
)
AREAS = (
    'storage',
    'background',
    'background',
    'deployment',
    'frontend',
    'deployment',
    'component',
    'storage',
)
RESPONSES = (
    'Asset storage implementation: Gaming Studio will use S3-compatible object storage, with AWS S3 as the initial provider. Storage will use private-by-default buckets, server-side encryption, object versioning where appropriate, presigned uploads and downloads, checksums, and lifecycle rules enforcing the approved temporary-file cleanup, recovery, retention, and deletion policies. Build and uploaded artifacts must pass required security validation before being promoted for hosting or publishing.',
    "Worker isolation implementation: Gaming Studio will use ephemeral Kubernetes Jobs with Kata Containers or an equivalent VM-isolated runtime for PC, Web, Android, Linux, and other compatible build workloads, with separate isolated ephemeral macOS runners for iOS builds. Every build receives an isolated execution identity and environment with CPU, memory, disk, network, and execution-time limits. Workers are unprivileged, have no host filesystem access, no direct production database access, no access to another customer's data, no inherited secrets, and deny network egress by default except explicitly approved allowlisted destinations. Any required credentials must be short-lived and scoped only to the specific approved build or integration.",
    'Background job execution mechanism: Temporal will orchestrate, dispatch, track, retry, cancel, time out, and recover Gaming Studio build, validation, export, and publishing workflows. Workflows must be durable and idempotent so retries cannot silently duplicate builds, releases, or publishing actions.',
    'Cloud deployment topology: Gaming Studio will use a containerized Kubernetes control plane with separately deployable web, API, workflow, and supporting services; managed PostgreSQL; S3-compatible object storage; managed secret storage; and private internal service networking. Public traffic will enter through an HTTPS edge protected by appropriate CDN, rate-limiting, and WAF controls. Production services will use centralized logs, metrics, traces, health checks, and audit events. The control plane and build-execution plane must remain separated.',
    'Frontend implementation: Gaming Studio will use Next.js with TypeScript and React for the web application. The frontend will communicate with controlled ArcaCentum APIs and will not directly access privileged infrastructure, databases, secret stores, or build workers.',
    'Isolated build deployment topology: Gaming Studio will maintain a separate build-execution plane from the ArcaCentum control plane. PC, Web, Android, Linux, and compatible workloads will use ephemeral sandboxed Kubernetes workers, while iOS builds will use isolated ephemeral macOS runners. Build environments are destroyed after completion. Only approved artifacts, logs, metadata, checksums, and provenance records may cross from the build plane back into controlled Gaming Studio storage and workflows.',
    "Publishing implementation: Gaming Studio will use a Publishing Orchestrator with platform-specific publishing adapters. Export and download remain separate from direct external-store submission. Direct publishing may occur only through explicitly supported integrations using the creator's connected developer or store account, after required validation gates pass and after an explicit final user-controlled release action. Publishing operations must be auditable and idempotent, and unsupported targets or failed validations must remain blocked rather than silently degrading.",
    "Primary persistence implementation: Managed PostgreSQL will be the system of record for Gaming Studio project state, asset metadata, build records, GitHub integration state, publishing state, permissions, workflow metadata, audit references, and other structured application state. Large binary assets and build artifacts will remain in object storage rather than PostgreSQL. Records must be bound to the correct account, project, or tenant, with database-level row isolation or equivalent enforced controls where appropriate so one customer's data cannot be accessed by another customer.",
)

# Preserve the original response including its internal CRLF paragraph breaks.
FULL_RESPONSE = (
    'I approve the following final Gaming Studio architecture decisions:\r\n\r\n'
    + "\r\n\r\n".join(f"{i}. {text}" for i, text in enumerate(RESPONSES, 1))
    + '\r\n\r\nI explicitly approve these eight decisions as the answers to the eight current blocking Gaming Studio architecture questions. I authorize them to be recorded as explicit architecture clarification decisions for the current ArchitectureSpecification. This approval does not by itself approve the complete architecture, authorize the ARCHITECTURE → MODELS transition, or authorize later lifecycle stages.'
)
FULL_RESPONSE_DIGEST = '1b6eb81b0d0152373c674d86eda2150857458ee8e9f8554804ba5057b3cd9755'
# Complete sentence values preserve every implementation and security constraint.
# Split only sentence-ending period/space, leaving Next.js and all wording intact.
VALUES = tuple(tuple(part + ("." if i < len(parts) - 1 else "")
                     for i, part in enumerate(parts))
               for parts in (text.split(". ") for text in RESPONSES))


def _production_inputs(directory):
    directory = local_authority_path(directory)
    validate_production_architecture_checkpoint(directory)
    handoff, initial = production_architecture_initial_state(directory)
    architecture = initial.original_architecture
    questions = tuple(sorted(initial.unresolved_questions, key=architecture_question_id))
    if (architecture.project_id != PROJECT_ID or architecture.architecture_id != ARCHITECTURE_ID
            or initial.finalization_id != INITIAL_FINALIZATION_ID
            or tuple(architecture_question_id(q) for q in questions) != ORDER
            or tuple(q.question for q in questions) != QUESTIONS
            or tuple(q.area.value for q in questions) != AREAS
            or not all(q.blocking for q in questions)):
        raise ValueError("Architecture clarification authority has stale architecture or question bindings.")
    return handoff, initial


def _replay_authorized_decisions(handoff, initial):
    """The public resolver is the sole decision, conflict, lineage and readiness engine."""
    current, approvals = initial, []
    for index, question_id in enumerate(ORDER):
        answer = ArchitectureClarificationAnswer.create(
            target_architecture_id=ARCHITECTURE_ID,
            target_finalization_id=current.finalization_id,
            target_question_id=question_id, user_answer=RESPONSES[index],
            normalized_values=VALUES[index], evidence=(RESPONSES[index],),
        )
        current = current.resolve(answer, handoff=handoff)
        if current.history[-1].outcome is not ArchitectureResolutionOutcome.ACCEPTED or current.conflicts:
            raise ValueError(f"Architecture resolution conflict; stop at {question_id}.")
        approvals.append({
            "ordinal": index + 1, "question_id": question_id, "question": QUESTIONS[index],
            "area": AREAS[index], "provenance": "explicit_user",
            "answer": answer.canonical_dict(), "resulting_finalization_id": current.finalization_id,
        })
    return current, approvals


def _authorization(approvals):
    if digest_bytes(FULL_RESPONSE.encode("utf-8")) != FULL_RESPONSE_DIGEST:
        raise ValueError("The exact architecture user response has changed.")
    return {
        "schema": AUTHORIZATION_SCHEMA, "schema_version": AUTHORIZATION_VERSION,
        "package_version": AUTHORIZATION_PACKAGE_VERSION, "product_key": "gaming_studio",
        "production_intent_digest": APPROVED_INTENT_DIGEST, "project_id": PROJECT_ID,
        "architecture_id": ARCHITECTURE_ID, "initial_finalization_id": INITIAL_FINALIZATION_ID,
        "full_user_response": FULL_RESPONSE, "full_user_response_digest": FULL_RESPONSE_DIGEST,
        "provenance": "explicit_user", "answer_order": list(ORDER), "approvals": approvals,
        "authority_scope": "only_eight_architecture_clarifications",
        "complete_architecture_approved": False, "models_authorized": False,
        "backend_authorized": False, "frontend_authorized": False,
    }


def architecture_authorization_package(directory=AUTHORITY_DIRECTORY):
    handoff, initial = _production_inputs(directory)
    _, approvals = _replay_authorized_decisions(handoff, initial)
    return _authorization(approvals)


def validate_architecture_authorization(data, directory=AUTHORITY_DIRECTORY):
    value = parse_authority(data)
    if digest_bytes(data) != APPROVED_AUTHORIZATION_DIGEST:
        raise ValueError("Architecture authorization differs from the eight exact user decisions.")
    if data != canonical_bytes(architecture_authorization_package(directory)):
        raise ValueError("Architecture authorization differs from the eight exact user decisions.")
    return value
