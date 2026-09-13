# Gaming Studio IDEA resolution authority

The four files at `authority/gaming_studio/` remain immutable seed history.
The `idea_resolution/` directory records actual user clarification authority
supplied in the controlled production batch, independently of test fixtures.

## Resolution 1

`clarification_authorization.json` uses
`arcadev.gaming_studio.clarification_authorization`, version 1. The trusted,
fixed mapping in `arcadev/gaming_studio_resolution.py` is the approval anchor.
Strict canonical byte comparison covers all five requirement/proposal/response
bindings, normalized values, literal evidence, ordinal, current and resulting
intake identities, schema and deferred notes. Recomputing a proposal hash does
not authorize a different proposal. Unknown fields, versions, extra answers,
duplicate JSON keys, oversized documents, secret additions and stale identities
fail closed. This is not a general approval parser or blanket authorization.

The answer order follows the user's numbered decisions: project type, target
users, platforms, authentication, deployment. Each public `ClarificationAnswer`
targets the current intake produced by the preceding resolution. Evidence quotes
only the unchanged response; the separate proposal supplies the conversational
referent. No proposal is falsely inserted into the user's answer.
The envelope records `explicit_user` provenance; its public answer uses the
certified `IntentProvenance.EXPLICIT` serialized value `explicitly_stated`.

The public resolver previously treated clarification of the seed's broad
`a user` and credential boundary as conflicts. The user explicitly authorized
adding a narrowly validated refinement operation in this conversation. The new
`refine_explicit` action requires an unresolved audience or authentication
question, existing explicit values, exact expected prior values, a changed
decision, and no active conflict for the requirement or outstanding assumptions.
It never activates automatically for ordinary `answer` records, which retain
their previous conflict behavior. History preserves both previous and accepted
values, and replay validates the action. The production envelope additionally
pins the semantic authority to these two approved proposals and responses.
The generic contract validates structure and provenance, not natural-language
entailment. It does not grant an unrelated production caller approval authority.
The existing answer/finalization version 1 shapes remain unchanged; this is a
new explicit action variant. Older readers reject the unsupported action.

Gaming Studio targets Web. Created games separately target PC, Web, Android and
iOS; labeled IDEA text values preserve this distinction and the certified web
compatibility rule. No console or other target is selected. Authentication keeps
the existing owner/credential-separation requirement and adds centralized
ArcaCentum identity, email/password and Google sign-in. Deployment selects cloud
hosting and isolated build execution without choosing infrastructure technology.

Social/community context is deferred outside requested features. The paid-access
note records the need for upgraded ArcaCentum access but authorizes no pricing,
tiers, trials, limits or billing implementation. Its quoted text and undecided
dimensions are protected by the same fixed envelope. Neither note is consumed
as a lifecycle decision or authentication mechanism.

Resolution 1 persists only the authorization envelope. Replaying it validates
the five resolutions but creates no project, transition or downstream artifact.
Dedicated tests: `tools.test_arcadev_gaming_studio_resolution_1`.

## Resolution 2

The persisted `idea_finalization.json` uses the public `arcadev.idea_finalization`
version 1 shape. All five entries replay as accepted; there are zero conflicts,
assumptions and unresolved requirements. The public intake computes readiness as
true. `current_intake.json` stores its canonical result separately, while the
initial intake remains byte-identical to the seed. Finalization identity is its
canonical SHA-256 digest plus the public current intake ID; no new public ID
scheme is invented.

The repository's metadata convention requires caller-supplied canonical UTC
timestamps and provides no production-specific timestamp default. This batch
explicitly permits verified non-product administrative provenance from the
certified checkpoint commit. `metadata_authority.json` (schema
`arcadev.gaming_studio.project_metadata_authority`, version 1) retains the actual
raw Git commit object for `e47123a13f380dd73dd0aa7a36b5036713ef0fd8`.
The validator computes the Git object hash over `commit <byte-length>\0<bytes>`
and requires that exact pinned object before extracting its committer epoch.
That epoch yields `2026-09-13T16:19:57Z` for both timestamps, validated through
`ProjectMetadata.create`. The proof is self-contained and needs no Git process,
network, host clock, fixture timestamp or environment variable during replay.

The timestamp denotes administrative inception of certified production
authority, not the wall-clock creation of these replay artifacts or a build.
This is a documented administrative source, not a new product decision or a
relaxation of the metadata contract. An asserted or changed date, different
commit, changed proof, metadata fields or stale finalization binding is rejected.
Without a valid proof, materialization refuses to create a project; the bounded
pending checkpoint reports `IDEA_READY_PENDING_PROJECT_METADATA` with null ID.

`IdeaFinalization.to_project(metadata=...)` creates the production project only
after exact production replay and metadata validation. `source_project.json`
roundtrips through `ArcaDevProject` at READY/IDEA. `idea_checkpoint.json` records
`IDEA_READY_FOR_TRANSITION`, its project ID and the digests of the finalization,
current intake, metadata authority and source project. This checkpoint uses
`arcadev.gaming_studio.resolution_checkpoint`, schema version 1, package version
2, resolution 2. No handoff or PLAN content is created in this increment.

The production validator now reports the resolution checkpoint by default when
the resolution area exists; `--seed-only` retains verification of the original
historical seed. Every persisted resolution file must match reconstruction,
including the original five-approval envelope. Dedicated tests:
`tools.test_arcadev_gaming_studio_resolution_2`.

## Resolution 3

`arcadev/gaming_studio_transition.py` validates the complete source project
against production finalization and verified metadata, then calls the existing
`IdeaPlanHandoff.create` and roundtrips its result through `IdeaPlanHandoff`.
It implements no transition algorithm or planning engine. The actual result is
eligible and `transitioned`, with consistent IDEA authority, no blocking
findings and no warnings. The new `project.json` is IN_PROGRESS/PLAN; the source
project remains READY/IDEA, with identical project ID, metadata and specification.

`idea_plan_handoff.json` uses the public `arcadev.idea_plan_handoff` version 1
schema. It freezes the exact source project, five-entry finalization and
consistency evaluation. The PLAN project is read from that certified handoff:
the existing standalone `ArcaDevProject` loader intentionally accepts only
initial IDEA projects, so its semantics are unchanged. The persisted resulting
project must match the handoff's canonical result byte for byte.

The new `idea_resolution/checkpoint.json` records package version 2, resolution
3, stage PLAN, project status IN_PROGRESS, status `PLAN_READY_FOR_GENERATION`,
and next action `GENERATE_PRODUCTION_SOFTWARE_PLAN`. That next action describes
the future boundary; this batch does not execute it. A blocked public gate is
projected as `BLOCKED_IDEA_PLAN_HANDOFF` with its actual consistency findings;
the gate result is never overridden. The Resolution 2 `idea_checkpoint.json`
and all earlier files remain unchanged.

The current checkpoint includes canonical SHA-256 digests for all four seed
files and all eight preceding resolution files. The validator independently
reconstructs every artifact from the pinned production intent, fixed five
proposal/response bindings, public sequential answer replay, verified Git
metadata proof, public project materialization and certified handoff. Rebinding
hashes on forged documents cannot replace those sources. Unknown, missing or
non-regular entries and downstream authority files fail closed.

Validate current production authority with:

```powershell
C:\ac259\Scripts\python.exe -B -m arcadev.gaming_studio_authority --require-current
```

Use `--seed-only` for historical seed verification. Without `--require-current`,
an original four-file seed package remains verifiable as history; it cannot be
mistaken for the required current package when the strict flag is supplied.
The current validator rejects stripping the resolution area under that flag.

Dedicated tests: `tools.test_arcadev_gaming_studio_resolution_3`. They exercise
actual eligibility, immutable source state, complete lineage, coherent forged
replay with recomputed identities, stale project metadata with the same project
ID, altered answers/referents/history, forged handoffs/checkpoints, strict JSON,
missing authority and the no-generation boundary. Full regression discovery
includes fixture generation in temporary test workspaces only. No production
SoftwarePlan, architecture, model, backend, frontend or ArcaCore generation
artifact is produced. Sprint 32 is outside this batch.
