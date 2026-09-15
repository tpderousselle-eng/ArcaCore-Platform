# Gaming Studio architecture resolution (historical)

The current approved architecture and MODELS-entry checkpoint is documented in
[architecture approval](GAMING_STUDIO_ARCHITECTURE_APPROVAL.md). The statements
below describe the immutable, still-unapproved resolution checkpoint.

This versioned package records exactly the eight user-authorized architecture clarifications. The architecture remains unapproved. MODELS and later lifecycle stages remain unauthorized. No application generation occurred.

## Historical resolved checkpoint

- Architecture: `arcadev_architecture_1365b59c168d82ba7d9ac0fb604afadf`
- Initial finalization: `arcadev_architecture_final_cca8f5b914aeeefc41b86ab649989135`
- Resolved finalization: `arcadev_architecture_final_17fe8c2deb6ed3712f04cdd3df6e074e`
- Accepted decisions: **8**; history entries: **8**; unresolved questions: **0**; conflicts: **0**.
- Effective ready for approval: **true**.
- Current stage: **ARCHITECTURE**; project status: **IN_PROGRESS**.
- Status: **ARCHITECTURE_READY_FOR_APPROVAL**.
- Next authorized action: **REQUEST_EXPLICIT_ARCHITECTURE_APPROVAL**.
- Architecture approved: **false**; MODELS authorized: **false**.
- Complete historical/current authority digests: **33**, excluding the checkpoint itself.

## Exact user authority

The following response is preserved verbatim in `clarification_authorization.json`, including its internal CRLF paragraph breaks. Its UTF-8 SHA-256 is:

`1b6eb81b0d0152373c674d86eda2150857458ee8e9f8554804ba5057b3cd9755`

I approve the following final Gaming Studio architecture decisions:

1. Asset storage implementation: Gaming Studio will use S3-compatible object storage, with AWS S3 as the initial provider. Storage will use private-by-default buckets, server-side encryption, object versioning where appropriate, presigned uploads and downloads, checksums, and lifecycle rules enforcing the approved temporary-file cleanup, recovery, retention, and deletion policies. Build and uploaded artifacts must pass required security validation before being promoted for hosting or publishing.

2. Worker isolation implementation: Gaming Studio will use ephemeral Kubernetes Jobs with Kata Containers or an equivalent VM-isolated runtime for PC, Web, Android, Linux, and other compatible build workloads, with separate isolated ephemeral macOS runners for iOS builds. Every build receives an isolated execution identity and environment with CPU, memory, disk, network, and execution-time limits. Workers are unprivileged, have no host filesystem access, no direct production database access, no access to another customer's data, no inherited secrets, and deny network egress by default except explicitly approved allowlisted destinations. Any required credentials must be short-lived and scoped only to the specific approved build or integration.

3. Background job execution mechanism: Temporal will orchestrate, dispatch, track, retry, cancel, time out, and recover Gaming Studio build, validation, export, and publishing workflows. Workflows must be durable and idempotent so retries cannot silently duplicate builds, releases, or publishing actions.

4. Cloud deployment topology: Gaming Studio will use a containerized Kubernetes control plane with separately deployable web, API, workflow, and supporting services; managed PostgreSQL; S3-compatible object storage; managed secret storage; and private internal service networking. Public traffic will enter through an HTTPS edge protected by appropriate CDN, rate-limiting, and WAF controls. Production services will use centralized logs, metrics, traces, health checks, and audit events. The control plane and build-execution plane must remain separated.

5. Frontend implementation: Gaming Studio will use Next.js with TypeScript and React for the web application. The frontend will communicate with controlled ArcaCentum APIs and will not directly access privileged infrastructure, databases, secret stores, or build workers.

6. Isolated build deployment topology: Gaming Studio will maintain a separate build-execution plane from the ArcaCentum control plane. PC, Web, Android, Linux, and compatible workloads will use ephemeral sandboxed Kubernetes workers, while iOS builds will use isolated ephemeral macOS runners. Build environments are destroyed after completion. Only approved artifacts, logs, metadata, checksums, and provenance records may cross from the build plane back into controlled Gaming Studio storage and workflows.

7. Publishing implementation: Gaming Studio will use a Publishing Orchestrator with platform-specific publishing adapters. Export and download remain separate from direct external-store submission. Direct publishing may occur only through explicitly supported integrations using the creator's connected developer or store account, after required validation gates pass and after an explicit final user-controlled release action. Publishing operations must be auditable and idempotent, and unsupported targets or failed validations must remain blocked rather than silently degrading.

8. Primary persistence implementation: Managed PostgreSQL will be the system of record for Gaming Studio project state, asset metadata, build records, GitHub integration state, publishing state, permissions, workflow metadata, audit references, and other structured application state. Large binary assets and build artifacts will remain in object storage rather than PostgreSQL. Records must be bound to the correct account, project, or tenant, with database-level row isolation or equivalent enforced controls where appropriate so one customer's data cannot be accessed by another customer.

I explicitly approve these eight decisions as the answers to the eight current blocking Gaming Studio architecture questions. I authorize them to be recorded as explicit architecture clarification decisions for the current ArchitectureSpecification. This approval does not by itself approve the complete architecture, authorize the ARCHITECTURE → MODELS transition, or authorize later lifecycle stages.

## Exact question, answer, and decision bindings

Each numbered decision above answers only the question with the same ordinal below. Normalized values are complete literal sentences from that paragraph; evidence is the entire unchanged paragraph. The public contract canonically sorts values. The scope-limiting final paragraph is never an implementation value.

| # | Area | Exact question ID | ArchitectureDecision ID | Normalized values |
|---|---|---|---|---|
| 1 | storage | `arcadev_architecture_question_44f2ca1153bdd0c4e2ad35bb615ccfd4` | `arcadev_architecture_decision_c2bd66e5a0fbab550647965e9bf8afbd` | 3 |
| 2 | background | `arcadev_architecture_question_4cbf21d1a4defc43dfb91fe5118fa277` | `arcadev_architecture_decision_45190da0e2ecacaa0c14a1a95075e7d1` | 4 |
| 3 | background | `arcadev_architecture_question_76c105bf89ae20d9a442f2fc61314394` | `arcadev_architecture_decision_fad92fbb205933512e9c873dc6f67754` | 2 |
| 4 | deployment | `arcadev_architecture_question_b44a16ef956c182be4dd1a9638001d5b` | `arcadev_architecture_decision_42c2c1d1d8bf0479eb99e0b161a6ebb0` | 4 |
| 5 | frontend | `arcadev_architecture_question_c36965b51d972beae7b149fd091f899d` | `arcadev_architecture_decision_54da0291121894ccb6b22b8db698e62e` | 2 |
| 6 | deployment | `arcadev_architecture_question_c87ceb1a789975aa2101ea8343eb54b2` | `arcadev_architecture_decision_0ba501ae4f80f993b4f1c62223f74e89` | 4 |
| 7 | component | `arcadev_architecture_question_e4c9734adfb93686b76444ed068c6451` | `arcadev_architecture_decision_5ae139ba694a5fcfa5eb8c60d00bd413` | 4 |
| 8 | storage | `arcadev_architecture_question_f031ffe0d00fcab1cb9d66feb9e37121` | `arcadev_architecture_decision_1ff2fecdc6d137cd8620de76135a79e6` | 3 |

## Sequential finalization lineage

| Answer | Parent finalization | Resulting finalization |
|---|---|---|
| 1 | `arcadev_architecture_final_cca8f5b914aeeefc41b86ab649989135` | `arcadev_architecture_final_d34d78a0f6d4d3e7d74a25601aad8b9d` |
| 2 | `arcadev_architecture_final_d34d78a0f6d4d3e7d74a25601aad8b9d` | `arcadev_architecture_final_2ab14cda080f9a8432973cc0e3772b1c` |
| 3 | `arcadev_architecture_final_2ab14cda080f9a8432973cc0e3772b1c` | `arcadev_architecture_final_f8b8210d298ab058808205dbe2a446be` |
| 4 | `arcadev_architecture_final_f8b8210d298ab058808205dbe2a446be` | `arcadev_architecture_final_63ffd9299bc4e1e8b88eeb820253dcad` |
| 5 | `arcadev_architecture_final_63ffd9299bc4e1e8b88eeb820253dcad` | `arcadev_architecture_final_070dd7e02298991ce99326f935403a59` |
| 6 | `arcadev_architecture_final_070dd7e02298991ce99326f935403a59` | `arcadev_architecture_final_58d4afa4bc0be0af3c7a4ffca10dfb22` |
| 7 | `arcadev_architecture_final_58d4afa4bc0be0af3c7a4ffca10dfb22` | `arcadev_architecture_final_422863fcb4c6df115c9c38b4859206ba` |
| 8 | `arcadev_architecture_final_422863fcb4c6df115c9c38b4859206ba` | `arcadev_architecture_final_17fe8c2deb6ed3712f04cdd3df6e074e` |

## Validation and authority boundaries

ProductionIntent → IDEA authority → IDEA resolution → SoftwarePlan → PLAN resolution → ApprovedPlan → PLAN-to-ARCHITECTURE handoff → original ArchitectureSpecification → initial unresolved ArchitectureFinalization → original clarification request → eight-answer authorization → sequential public decision history → resolved ArchitectureFinalization → resolution review → current checkpoint.

All eight answers are constructed with the public `ArchitectureClarificationAnswer` contract and applied through `ArchitectureFinalization.resolve(...)`. Every answer targets the immediately preceding finalization. The first conflict aborts replay. No parallel resolution algorithm or manual decision/readiness mutation is used.

Trusted repository constants and pinned digests reject changed authority before expensive reconstruction. A matching digest is only a rejection filter: successful validation still reconstructs the complete lineage through public contracts. All file inventories and digest paths come from trusted code. Supplied JSON is inert and cannot grant authority or cause execution, network activity, or writes.

The original five files under `production_architecture/` remain immutable historical authority. The four new files are under `production_architecture/architecture_resolution/`.

`--require-architecture-resolution` explicitly selects this complete historical resolution package; missing or partial resolution cannot downgrade to unresolved architecture. Unqualified validation now requires architecture approval and MODELS entry, as does `--require-models-entry`. Current validation rejects DomainModel, model approval, MODELS-to-BACKEND handoffs, backend, frontend and unknown authority.

Explicit historical gates remain available: `--seed-only`, `--require-current` (IDEA resolution), `--require-plan`, `--require-plan-resolution`, `--require-plan-approval`, and `--require-architecture` (generated unresolved architecture). As before, the historical minimum gates validate later historical packages when present; `--require-architecture` explicitly selects the unresolved checkpoint even when resolution is present.

```powershell
& 'C:\ac259\Scripts\python.exe' -m arcadev.gaming_studio_authority --require-architecture-resolution
& 'C:\ac259\Scripts\python.exe' -m arcadev.gaming_studio_authority --require-architecture
```

Architecture approval requires a separate explicit user action. This batch stops at readiness and grants no approval, MODELS transition, DomainModel generation, application generation, or later lifecycle authority.
