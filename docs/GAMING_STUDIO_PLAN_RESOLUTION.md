# Gaming Studio production PLAN resolution

This batch records exactly three actual user-approved planning clarifications.
It does not approve the complete SoftwarePlan or authorize architecture, models,
backend/frontend implementation, production generation, or Sprint 32.
Future strategic expansion remains non-authoritative in
[the separate strategy register](GAMING_STUDIO_FUTURE_STRATEGY.md).

The original SoftwarePlan, unanswered review and historical checkpoint remain
byte-for-byte unchanged in `authority/gaming_studio/production_plan/`.
All new authority lives in its versioned `plan_resolution/` subdirectory.

## PLAN Resolution 1: explicit authority

The envelope schema is `arcadev.gaming_studio.plan_clarification_authorization`,
version 1. The nested public answer schema is `arcadev.plan_clarification_answer`,
version 1. `arcadev/gaming_studio_plan_resolution.py` contains a fixed production
mapping of the supplied question, referent, exact response and accepted values.
It does not parse arbitrary approval messages. Each answer and envelope approval
has `explicit_user` provenance; evidence quotes the complete unchanged response.

`clarification_authorization.json` retains all referent text and normalized
accepted values, ordinal, question ID/text, proposal SHA-256, relationship and
both sides of each finalization binding. For publishing, the referent is the
user-supplied approved interpretation, not an invented preceding recommendation.
The entire canonical envelope is pinned to SHA-256
`360fb151709a031f49109726f2c3f3b73c4d0c13364baadf2edf87f3b0a5562c`.
Exact byte comparison against public-contract reconstruction also runs for valid
inputs. Unknown fields, duplicate keys, excessive bytes, secret additions,
fixture authority, rehashed proposals and stale IDs cannot introduce authority.

Answer order is storage/retention, build isolation, then publishing/release.
`PlanFinalization.start(plan, handoff=...)` starts with all three unresolved.
Each public `PlanClarificationAnswer` targets the current finalization; public
`resolve` computes the next identity before the next answer is constructed.

| State | PlanFinalization ID |
| --- | --- |
| Initial | `arcadev_plan_final_369adbc2e30f9e839416f5e39023099a` |
| After storage | `arcadev_plan_final_176bfa0c13ed2699e5acc21a9016055f` |
| After isolation | `arcadev_plan_final_f2536b26b828fcadc86789d9d7e86074` |
| After publishing | `arcadev_plan_final_d9698e456e67fae47ef46dbd11880dd2` |

The historical PLAN validator recognizes the separate local resolution directory
while continuing to validate only the three immutable historical PLAN files.
The current-resolution validator is introduced by increment 3.

Increment 1 changes this document, adds the resolution module, authorization JSON
and `tools/test_arcadev_gaming_studio_plan_resolution_1.py`, and extends
`arcadev/gaming_studio_plan.py` to recognize the separate resolution directory.
The dedicated tests cover exact authority, scope, tampering, sequential/stale and
duplicate resolution, and prohibit approval, architecture, generation, network,
process execution and writes during authority construction/validation.

## PLAN Resolution 2: finalization and current review

All three planning questions are explicitly resolved through the public
`PlanFinalization` contract (`arcadev.plan_finalization`, version 1). The original
plan remains `arcadev_plan_9aed1a01dad6e95cb75b6db67730dd5b`; the finalization is
`arcadev_plan_final_d9698e456e67fae47ef46dbd11880dd2`.

| Answer order | Accepted PlanningDecision ID | Outcome |
| --- | --- | --- |
| Storage/retention | `arcadev_decision_141775fe2b2e9d72c94e3606b02fd12f` | accepted |
| Build isolation | `arcadev_decision_304964ccfcaaa1217a914104d55355ec` | accepted |
| Publishing/release | `arcadev_decision_70fafefce78c86f108163a806313f81a` | accepted |

Public replay computes three decisions, three history entries, zero unresolved
questions, zero conflicts and `effective_ready_for_architecture = true`.
Readiness after each answer is false, false, true. These values are not forced.
The original SoftwarePlan still reports its historical unanswered readiness as
false. A conflict stops replay; a blocked or partial public result produces a
blocked review instead of a ready-for-approval status.

The current review schema is `arcadev.gaming_studio.plan_resolution_review`,
version 1. Project `arcadev_969321c8959864fe18393b9d2b551063` remains
`IN_PROGRESS` at `PLAN`, with status `PLAN_READY_FOR_APPROVAL` and next action
`REQUEST_EXPLICIT_PLAN_APPROVAL`. The user has **not approved the complete
SoftwarePlan**. `complete_plan_approved` and `architecture_authorized` are false;
no ApprovedPlan or PLAN-to-ARCHITECTURE handoff exists.

Increment 2 adds `arcadev/gaming_studio_plan_finalization.py`, canonical
`plan_finalization.json`, `resolution_review.json`, and
`tools/test_arcadev_gaming_studio_plan_resolution_2.py`, and extends this document.
The seven dedicated tests cover deterministic public replay and roundtrip,
history and decision integrity, actual partial/conflicted results, exact bounded
policy, frozen IDEA platform authority, future-strategy isolation and the
approval/execution boundary.

## Exact accepted authority

### Answer 1: What asset storage limits and retention rules are required?

Question ID: arcadev_question_64610a51eaf261a7116813cf9cb32d91

Exact response:

> I approve the recommended Gaming Studio asset storage and retention policy.

Approved referent (line wrapping normalized):

Gaming Studio uses configurable storage quotas tied to the user’s ArcaCentum entitlement rather than hard-coding storage into the product.

For initial production:

- provide 50 GB of active project-asset storage per paid Gaming Studio account
- user-created project assets are retained while the project/account remains active
- deleted assets/projects remain recoverable for 30 days before permanent deletion
- temporary build/intermediate files may be automatically purged after 7 days
- final/exported builds may be retained for 30 days unless the user explicitly keeps/pins them
- additional storage capacity can be offered later without changing the core storage architecture
- Marketplace asset retention is outside current initial scope

Proposal SHA-256: 15deebfbfcac41b368c6a93af052b1e822d2a377a4672a8893039a9f99dadaf4

Normalized accepted values (public canonical order):

- 50 GB of active project-asset storage per paid Gaming Studio account
- Additional storage capacity can be offered later without changing the core storage architecture
- Configurable storage quotas tied to the user's ArcaCentum entitlement
- Deleted assets/projects recoverable for 30 days before permanent deletion
- Final/exported builds may be retained for 30 days unless explicitly kept/pinned by the user
- Marketplace asset retention is outside current initial scope
- Temporary build/intermediate files may be automatically purged after 7 days
- User-created project assets retained while the project/account remains active

### Answer 2: Which build execution environments and isolation rules are required?

Question ID: arcadev_question_06fa970b49a43c4d5442756aa4361ccc

Exact response:

> I approve isolated disposable build environments with strict resource, network, secret, and filesystem boundaries for Gaming Studio.

Approved referent (line wrapping normalized):

All user-generated game code and builds run in isolated, disposable execution environments separate from the ArcaCentum control plane.

Each build gets a clean sandbox with explicit:

- CPU limits
- memory limits
- disk limits
- network limits
- execution-time limits

Additional approved rules:

- no host filesystem exposure
- no internal service exposure by default
- no secret-store exposure by default
- no access to another customer's data
- network denied by default and enabled only through approved allowlisted workflows when required
- build environment destroyed after completion
- only approved outputs, logs and metadata retained
- no privileged containers/processes
- no direct production database access
- no inherited secrets unless explicitly injected for one approved integration
- malware/static security checks on outputs before ArcaCentum hosting or publishing

Proposal SHA-256: 8a9606d8f35c70afabcef6bbef57eb1504a25c3bf0fd7dab9a3d5e3df891c79c

Normalized accepted values (public canonical order):

- All user-generated game code and builds run in isolated, disposable execution environments separate from the ArcaCentum control plane
- Build environment destroyed after completion
- Each build gets a clean sandbox with explicit CPU, memory, disk, network and execution-time limits
- Malware/static security checks on outputs before ArcaCentum hosting or publishing
- Network denied by default; enabled only through approved allowlisted workflows when required
- No access to another customer's data
- No direct production database access
- No host filesystem exposure
- No inherited secrets unless explicitly injected for one approved integration
- No internal service exposure by default
- No privileged containers/processes
- No secret-store exposure by default
- Only approved outputs, logs and metadata retained

### Answer 3: Which publishing targets and release controls are required?

Question ID: arcadev_question_3386cafaf9fe1e6672db5b0a9bed716f

Exact response:

> I approve PC, Web, Android, and iOS publishing/export with validation gates, user-controlled releases, and direct store publishing only through explicitly supported integrations.

Approved referent (line wrapping normalized):

- initial publishing/export targets are PC, Web, Android and iOS
- releases are user-controlled
- publication/export workflows use validation gates
- build/test requirements must pass where required
- required release metadata must be present
- platform-specific requirements must be satisfied
- export/download is distinct from direct store submission
- users may export approved build artifacts
- direct external-store publishing occurs only through explicitly supported integrations
- store/developer credentials belong to the user's connected developer accounts
- unsupported targets or failed validation block direct publishing
- consoles are outside initial scope

Proposal SHA-256: 06a1aab39fe12638e52d6f21f8a0a0ef8a6dc2edfe5d56ea7fc71ea6061833ec

Normalized accepted values (public canonical order):

- Build/test requirements must pass where required
- Consoles are outside initial scope
- Direct external-store publishing only through explicitly supported integrations
- Export/download is distinct from direct store submission
- Initial created-game publishing/export targets: PC, Web, Android and iOS
- Platform-specific requirements must be satisfied
- Publication/export workflows use validation gates
- Releases are user-controlled
- Required release metadata must be present
- Store/developer credentials belong to the user's connected developer accounts
- Unsupported targets or failed validation block direct publishing
- Users may export approved build artifacts

## PLAN Resolution 3: current checkpoint validation

`arcadev/gaming_studio_plan_checkpoint.py` reconstructs the complete current
package. Its checkpoint schema is
`arcadev.gaming_studio.plan_resolution_checkpoint`, schema version 1, package
version 3. The exact file allowlist is `clarification_authorization.json`,
`plan_finalization.json`, `resolution_review.json` and `checkpoint.json`.

The complete lineage is ProductionIntent → seed IDEA authority → explicit IDEA
clarifications → IdeaFinalization → ProjectMetadata authority → source IDEA
project → IdeaPlanHandoff → PLAN project → original SoftwarePlan → original
unanswered review and historical checkpoint → three explicit PLAN authorizations
→ PlanningDecision history → PlanFinalization → current resolution review →
current checkpoint. The checkpoint binds all 16 historical artifacts and the
three current parent artifacts by SHA-256. Its own digest is returned separately
by the validator. It retains the production-intent text digest separately from
the JSON-file digest.

The validator first rejects unknown/missing/non-regular files, invalid or
noncanonical JSON, incorrect approval bytes and broken digest bindings. These
checks are only rejection filters: even a fully rehashed candidate must equal
trusted reconstruction through the certified public contracts. Supplied
finalization, review or checkpoint fields never supply decisions to replay.
A self-consistent public finalization with altered accepted values also fails
the exact production-authority comparison.

The top-level production validator automatically validates a present resolution
area and reports its current checkpoint, retaining the original checkpoint as
`unanswered_plan_checkpoint`. Use the explicit required-resolution gate to
prevent fallback to a historical package when the resolution area is absent:

```powershell
C:\ac259\Scripts\python.exe -m arcadev.gaming_studio_authority --require-plan-resolution
```

This gate stops at `PLAN_READY_FOR_APPROVAL`, `IN_PROGRESS`, `PLAN`, with
`REQUEST_EXPLICIT_PLAN_APPROVAL`. The user has not approved the complete
SoftwarePlan; architecture remains unauthorized. Unknown approval, architecture,
models, backend, generation or future-strategy artifacts are rejected.

The 12 dedicated checkpoint tests cover complete digests and lineage, altered
historical authority, rehashed historical records, changed responses/referents,
changed accepted values, stale history, forged readiness/reviews/checkpoints,
unknown and fake later-stage authority, bounded local-file handling, fixture
dependencies, CLI downgrade prevention, and no execution/generation/writes.
Historical checkpoint tests retain their strict unanswered-state assertions by
copying the historical package explicitly, excluding the later resolution area.

## Final test gates and integrity

All gates used the requested `C:\ac259\Scripts\python.exe`, Python 3.13.15.
Each complete discovery manifest is accounted for by isolated module results;
the ArcaDev and PostgreSQL counts below are included in those full gates.

| Increment | Dedicated cases verified | Complete ArcaDev | Repository discovery | PostgreSQL-backed |
| --- | ---: | ---: | ---: | ---: |
| PLAN Resolution 1 | 8 | 627 | 1,359 | 36 |
| PLAN Resolution 2 | 7 | 634 | 1,366 | 36 |
| PLAN Resolution 3 | 12 | 646 | 1,378 | 36 |

Every increment has exactly one documented real Docker Compose opt-in skip.
All seven PostgreSQL-backed classes passed in every increment. No failures or
errors remain unresolved. Full manifests, individual test IDs, logs, original
results and rechecks are retained in the ignored local evidence directories
`.env.plan-resolution-1/`, `.env.plan-resolution-2/` and `.env.plan-resolution-3/`.

Increment 1 initially encountered a concurrent-load startup-classification
timeout in the runtime harness. All 16 unchanged runtime-harness tests passed
when repeated serially; increments 2 and 3 run that module serially, matching
the prior certified procedure. No runtime limit or test assertion was weakened.
Increment 1 therefore has 1,359 distinct tests and 1,375 executions with rechecks.

Increment 3 corrected two file reads in an adversarial test to explicitly use
UTF-8 instead of Windows' cp1252 default. Its in-flight process had already
loaded the earlier reader and reported an identity mismatch from incorrectly
decoded historical text. The exact corrected case passed in a fresh process;
the other 11 dedicated checkpoint cases passed in the full run. This gives
1,378 distinct tests and 1,379 executions with the recheck. Production code and
authority were unchanged by this test-reader correction.

The current checkpoint SHA-256 is
`8d065da2fdfa2afcbadd83efc4907712b0005cbca1562361d18bfe2d8fe77c76`.
All 16 historical authority files match certified baseline
`82523d9031b7633eeda95e0a4a32dbc1c0888baf` byte for byte, including the original
SoftwarePlan, unanswered review and historical PLAN checkpoint. Backend,
frontend, shared and the future-strategy register are unchanged. No generated
production application artifacts were added; repository tests use their own
temporary fixtures.

The branch is `arcadev-gaming-studio-plan-resolution`. The three commit messages
are exactly the requested PLAN Resolution 1, 2 and 3 messages. Their identities
are recorded in the final completion report. The batch stops at the resolved,
unapproved PLAN. No ApprovedPlan, PLAN-to-ARCHITECTURE handoff,
ArchitectureSpecification, MODELS or production backend/frontend work was
created. ArcaCore production generation and Sprint 32 were not started.

Protected local state remains ` D tools.zip` and `?? .codex/`; neither item was
modified, restored, staged or committed by this batch. Nothing was pushed and
no PR was created. The next authorized action is to request explicit approval
of the complete SoftwarePlan, including these three accepted decisions.
