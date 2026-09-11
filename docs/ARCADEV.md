# ArcaDev

ArcaDev is the deterministic development-orchestration layer between product intent and ArcaCore. The platform relationship is:

```text
ArcaCentum.ai
    -> ArcaDev
        -> ArcaCore v1
            -> Generated Application
```

ArcaCentum.ai supplies the user-facing product experience. ArcaDev owns the structured development lifecycle. ArcaCore remains the certified generator and runtime foundation. ArcaOS provides higher-level intelligence and operational oversight.

## Build lifecycle

Every ArcaDev project uses the ordered stages `IDEA`, `PLAN`, `ARCHITECTURE`, `MODELS`, `BACKEND`, `FRONTEND`, `TESTS`, `SECURITY`, `PREVIEW`, and `DEPLOYMENT`.

ArcaDev 1.1 introduced the canonical `IDEA` project foundation. ArcaDev 1.2 adds deterministic idea intake and intent normalization in front of that foundation. Neither release performs PLAN-stage work: they do not generate plans, architecture or models; invoke ArcaCore; write an application backend or frontend; create previews; deploy; or run generated content.

## IDEA intake and normalization

Schema `arcadev.idea_intake`, version `1`, accepts unchanged natural-language input and separates it into:

- the original user wording;
- proposed name, project type, product description, target users, and primary goal;
- requested features and platform targets;
- authentication, integration, and deployment requirements;
- explicit constraints, non-functional requirements, and technology preferences;
- inferred assumptions that require confirmation;
- structured unresolved clarification requirements; and
- a deterministic readiness evaluation.

`normalize_idea` is deliberately conservative and rule-based. It recognizes common explicit forms such as named web/mobile applications, purpose clauses, feature lists, authentication choices, integrations, deployment targets, accessibility/offline requirements, and named technology preferences. A value the rules cannot support remains absent and produces a clarification requirement; the normalizer does not fill gaps with product choices.

Collections and JSON object keys have canonical ordering. The normalizer does not read clocks, generate identifiers, consult the environment, or include provider/model metadata. Repeating the same intake produces byte-identical canonical JSON. The unchanged original request remains part of the result, so two differently worded requests intentionally remain distinguishable even when some normalized fields coincide.

## Provenance and ambiguity

Every normalized value is an `IntentValue` with a value, confidence (`high`, `medium`, or `low`), source evidence, and one of these provenance classifications:

- `explicitly_stated`: the value repeats a requirement directly supplied by the user;
- `deterministically_derived`: a canonical value follows from cited wording, such as `web_application` from “web application”;
- `inferred_assumption`: a tentative interpretation stored only in the assumptions collection; or
- `unresolved`: used by a `ClarificationRequirement`, never by a confirmed material field.

Evidence must be present in the original request. Material fields reject assumed or unresolved provenance, preventing a candidate from silently promoting uncertainty into project state. Clarifications contain a canonical requirement key, a direct question, optional source evidence, and an explicit blocking flag. Assumptions are always visible and block readiness until resolved.

## IDEA readiness

Readiness is recomputed from accepted content rather than trusted from serialized or AI-produced data. An intake reports `ready_for_plan: true` only when all of these are specified:

- proposed project name;
- project type and product description;
- target users and primary goal;
- at least one requested feature and platform target;
- an explicit authentication decision;
- an explicit integration decision; and
- an explicit deployment decision.

Any blocking clarification or unconfirmed assumption also makes the intake not ready. “No authentication” and “no integrations” are valid explicit decisions; silence is not. Readiness is information only. ArcaDev 1.2 never advances the lifecycle to `PLAN`.

## AI trust boundary

The contract is suitable for a future model adapter, but provider-specific code and metadata are outside the domain model. `validate_candidate` treats candidate mappings or JSON as untrusted input and requires the exact versioned shape, unchanged original request, supported provenance/confidence values, source-backed evidence, canonical project-type identifiers, and a readiness value that matches deterministic recomputation.

Validation rejects oversized input, disallowed control characters, credential/secret-like assignments, private keys, duplicate JSON keys, duplicate normalized values, unknown fields, schema/version confusion, and forged readiness. It performs JSON data parsing only. Prompt-like text, source code, paths, and commands are inert discussion content: the intake layer has no shell, code execution, import, deserialization, path access, generation, or network capability.

## Gaming Studio example

For:

```text
Build me a Gaming Studio where users can create and manage game projects, assets, builds, testing, and publishing.
```

the deterministic normalizer preserves that sentence unchanged, extracts `users`, derives the stated capability list and product description, and tentatively derives `Gaming Studio` as the proposed name. Because the wording does not explicitly say that this is the name, the result includes an assumption and a blocking confirmation question. Project type, platform, authentication, integrations, and deployment also remain unresolved. The IDEA therefore reports not ready and stays at IDEA; it does not guess “web,” a database, an identity system, or a hosting platform.

## Conversion to the ArcaDev 1.1 project

`IdeaIntake.to_project` is the only intake-to-project conversion. It refuses an intake that is not ready and requires caller-supplied validated `ProjectMetadata`, preserving the 1.1 rule against implicit timestamps. It builds `ProjectSpecification` and `ArcaDevProject` through their public constructors rather than duplicating the project schema. The resulting project has status `READY` but remains at build stage `IDEA`; no PLAN transition occurs. Non-functional requirements and technology preferences are carried into the existing 1.1 `user_constraints` field with explicit category prefixes.

## Clarification resolution and IDEA finalization

ArcaDev 1.3 resolves ambiguity without introducing PLAN-stage behavior. `IdeaFinalization` is an immutable, versioned session containing the initial 1.2 `IdeaIntake`, the current intake, active conflicts, and an ordered clarification history. The initial intake remains byte-for-byte available throughout the session. Each accepted or conflicting user answer is appended unchanged to the current intake's source transcript, so new explicit evidence can be validated by the 1.2 contract without overwriting earlier user wording.

Every intake state has a deterministic `arcadev_idea_...` identity derived only from canonical intake content. A `ClarificationAnswer` names that identity, one requirement, the unchanged user answer, its evidence, an action, accepted candidate values, and—only for deliberate explicit replacement—the expected previous values. Supported actions are:

- `answer`: resolve a currently open requirement;
- `confirm_assumption`: confirm an existing tentative interpretation without changing its normalized value;
- `reject_assumption`: remove a tentative interpretation and leave its requirement unresolved when needed;
- `replace_assumption`: replace a tentative interpretation with corrected explicit intent; and
- `replace_explicit`: deliberately resolve a recorded conflict against exact expected prior values.

Answers are accepted only for the named requirement. Scalar requirements accept exactly one normalized value; collection requirements accept one or more values, reject case-insensitive duplicates, and serialize in canonical order. Unrelated values retain their existing value, confidence, evidence, and provenance. Accepted clarification values are always `explicitly_stated` with high confidence and evidence drawn from the unchanged answer.

### Conflicts

An ordinary answer cannot silently replace established explicit or deterministically derived intent. A contradictory answer creates an `IntentConflict`, retains the existing value, records the proposed values as rejected for that attempt, and adds a blocking clarification. Resolving it requires `replace_explicit` against the current intake identity and the exact previous values. The deliberate replacement affects only that requirement; related fields are not guessed or silently changed.

### Deterministic history and replay

Each `ClarificationHistoryEntry` records the complete answer contract, outcome, previous/accepted/rejected normalized values, resulting intake identity, readiness before and after, and unresolved requirements and assumptions before and after. No clock or host metadata is present. History order reflects user resolution order; unordered values inside each event are canonicalized.

Deserialization replays every answer from the preserved initial intake and requires every history entry, conflict, current intake, identity, and readiness value to match the deterministic replay. A stale answer cannot be replayed against a newer intake identity. History is bounded to 256 entries.

### Gaming Studio finalization

The 1.2 Gaming Studio intake begins not ready, with a tentative name and unresolved type, platforms, authentication, integrations, and deployment. A representative 1.3 session explicitly confirms `Gaming Studio`, sets `web_application`, selects `Desktop web` and `Mobile web`, chooses `Email/password` and `Google OAuth`, integrates `GitHub`, and selects `ArcaCentum managed cloud` deployment.

After those six resolutions, the assumption list, blocking clarifications, and conflicts are empty, and the reused 1.2 readiness evaluator reports `ready_for_plan: true`. `IdeaFinalization.to_project` validates the entire history by replay, then calls the existing 1.2 conversion. The resulting ArcaDev 1.1 project has status `READY` and stage `IDEA`. Readiness authorizes a future transition; it does not perform one.

### Clarification trust boundary

Clarification answers and future AI-produced candidates are untrusted data. Exact schemas reject unknown fields, unsupported versions/actions/provenance, duplicate JSON keys or collection values, invalid Unicode and controls, oversized answers/documents/history, credential-like assignments, private keys, invalid project-type identifiers, forged intake identities/readiness, stale replay, nonexistent requirements, mismatched assumptions, and incorrect prior values. Provider/model metadata is not accepted and cannot enter identity. Commands, source code, prompts, and paths discussed as product requirements remain inert strings: clarification resolution performs no imports, shell execution, filesystem access, network access, generation, or deserialization beyond strict JSON parsing.

## Canonical project schema

Schema `arcadev.project`, version `1`, separates three concerns:

- Original intent: the exact `original_user_request` supplied by the user.
- Normalized specification: project type, target users, primary goal, requested features, platform targets, authentication requirements, integration requirements, deployment targets, and user constraints.
- Future output: deliberately absent in version 1. Generated artifacts will belong to later lifecycle contracts rather than the project definition.

The project envelope also contains a content-addressed `project_id`, name, description, status, current stage, and explicit `created_at`/`updated_at` metadata. Equivalent input produces the same identity and canonical UTF-8 JSON. Collection ordering and JSON object ordering do not introduce nondeterminism. Timestamps are caller-supplied canonical UTC values and are never read from the host clock implicitly.

Supported statuses are `DRAFT`, `READY`, `IN_PROGRESS`, `BLOCKED`, `FAILED`, and `COMPLETED`. New projects default to `DRAFT` and are constrained to `IDEA`; ArcaDev 1.1 does not execute stage transitions.

## Validation and storage

The v1 loader rejects unknown or missing fields, duplicate JSON keys, unsupported schema versions, forged project identities, invalid enums, control characters, oversized data, duplicate collection values, noncanonical serialization, and values that resemble embedded credentials or private keys. Authentication intent such as “require password authentication” is allowed, but credential values are not.

`save_project` accepts only validated project objects and canonical relative paths. It rejects traversal, Windows path aliases, and symbolic-link components, then uses an atomic same-directory replacement so an interrupted write does not replace the prior accepted file. It has no deletion behavior and executes no commands, imports, templates, callbacks, or generated code.

## IDEA to PLAN transition gate

ArcaDev 1.4 closes the IDEA lifecycle with the versioned `arcadev.idea_plan_handoff` contract. The gate binds the certified project identity to the finalized `IdeaIntake` identity, freezes the approved project, accepted requirements, provenance, clarification history, readiness, and consistency evaluation, and derives a content-addressed handoff identity. Consumers must use this frozen snapshot instead of independently re-normalizing the original wording.

The consistency evaluator applies a deliberately small deterministic rule set. It blocks incompatible web/mobile platform combinations, authentication mechanisms combined with “no authentication,” integrations combined with “no external integrations,” and contradictory managed-cloud/self-hosted deployment choices. An unsupported project-type compatibility rule produces a warning rather than guessed intent.

Transition eligibility requires a READY project still at IDEA, a ready finalized intake, no blocking clarification, assumptions, conflicts, identity mismatch, or consistency blocker, and a structurally valid handoff. A successful gate returns a new immutable project value with status `IN_PROGRESS` and stage `PLAN`; the source project remains recoverable as READY at IDEA. A blocked gate retains the original lifecycle state. Neither outcome contains plan content.

For Gaming Studio, the approved Desktop web and Mobile web targets, Email/password and Google OAuth authentication, GitHub integration, and ArcaCentum managed-cloud deployment pass consistency. The deterministic handoff becomes eligible and yields the new PLAN-stage project while its frozen snapshot retains the complete approved IDEA and clarification trail. ArcaDev 1.4 controls the boundary only; software-plan definition and generation remain later responsibilities.

## Future extension boundary

## Canonical software planning contract

ArcaDev 2.1 defines the versioned `arcadev.software_plan` domain contract consumed at PLAN. A `SoftwarePlan` is bound to one approved 1.4 handoff and project identity and contains typed plan items, scope, capabilities, user roles and journeys, functional and non-functional requirements, milestones, dependencies, integrations, assumptions, risks and mitigations, planning questions, acceptance criteria, and constraints. Plan items record whether they reproduce approved IDEA content or are deterministic planning derivations, with source references back into the frozen IDEA; IDEA provenance itself is never rewritten.

The plan identity is derived only from canonical plan content and its approved handoff. Readiness is separately recomputed: scope, capabilities, workflows, functional and applicable non-functional requirements, milestones, dependencies, risks, and acceptance criteria must be present, and no blocking planning question may remain. Presence alone therefore cannot forge readiness. A 2.1 plan remains at PLAN and contains no architecture output.

The Gaming Studio example contract can represent its product objective, five approved core capabilities, the game-project workflow, GitHub dependency/integration, web constraints, milestone, deterministic risk, and acceptance criteria. Authentication and deployment decisions remain traceable to the frozen approved IDEA. This increment defines what a plan is and how it validates; it deliberately does not call an AI model or generate a plan.

## Plan generation and candidate validation

ArcaDev 2.2 adds a conservative deterministic planner. It consumes only the certified 1.4 frozen snapshot, turns approved capabilities into traceable functional requirements and acceptance criteria, groups approved work into milestones, carries constraints, authentication, integrations, and deployment forward, and records deterministic dependencies and risks. It does not infer unsupported business features.

The provider-neutral `PlanCandidateAdapter` boundary allows future model integrations to return JSON-like candidate data without coupling the domain to a vendor, model name, response format, or network client. Every candidate is untrusted: exact schema and binding are validated, unknown and duplicate fields are rejected, identities and readiness are recomputed, material scope is checked against deterministically grounded capabilities, and secret, malformed, control-character, and oversized data fails closed. Provider claims and metadata never enter canonical identity.

Gaming Studio generation preserves Desktop web, Mobile web, Email/password, Google OAuth, GitHub, and ArcaCentum managed cloud while planning its game-project, asset, build, test, publishing, authentication, and integration workflows. It exposes genuinely unresolved questions for build execution, asset storage, publishing targets, and GitHub synchronization, so its initial plan is not yet ready for architecture. IDEA questions are not reopened. ArcaDev 2.2 stops at PLAN: it performs no ARCHITECTURE transition and invokes no model, backend, frontend, file, shell, network, or ArcaCore generation behavior.

## PLAN clarification and finalization

ArcaDev 2.3 resolves blocking PLAN questions through versioned `arcadev.plan_clarification_answer` and `arcadev.plan_finalization` contracts. Every question has a deterministic identity derived from its canonical text, blocking status, and approved IDEA sources. An answer targets the exact plan, current finalization, and question identities; preserves the unchanged user answer; and creates an explicit, content-addressed `PlanningDecision` with evidence and IDEA traceability.

The finalization layer retains the original `SoftwarePlan`, current decisions, unresolved questions, active conflicts, and replay-verifiable history. History records accepted or rejected values, prior values, decision identity, readiness changes, unresolved-question identities, and conflict changes without timestamps. Effective architecture readiness reuses the SoftwarePlan's structural blockers and becomes true only when required questions are resolved and conflicts are absent.

PLAN decisions may add implementation details such as storage policy, isolated build execution, repository synchronization, and release controls, but they cannot rewrite frozen IDEA authority. A tagged contradiction such as replacing approved web targets with iOS-only becomes an explicit blocking conflict. Accepted decisions can be replaced only through a deliberate action naming the exact prior value. In the Gaming Studio certification fixture, four explicit answers resolve asset storage, build execution, publishing, and GitHub synchronization; the base plan and frozen IDEA remain canonical and the project stays at PLAN with no architecture output.

## Final PLAN consistency and approval

ArcaDev 2.4 introduces the versioned `arcadev.approved_plan` contract. Its frozen package embeds the valid IDEA handoff, original SoftwarePlan, finalized planning decisions and history, plus a freshly recomputed PLAN consistency evaluation. That package is sufficient for a later architecture stage to consume without rerunning IDEA normalization or planning.

Consistency checks require resolved questions, no conflicts, correct project/handoff/plan/finalization binding, matching scope and capabilities, and preservation of approved integrations, authentication, platform, and deployment constraints. Deterministically recognizable scope conflicts block approval; unclassified explicit decision semantics are preserved as warnings instead of guessed failures.

Readiness never implies approval. Approval requires a nonempty explicit statement and an eligible, consistent finalization; rejection is a separate immutable result that retains the full plan and history without marking it approved. The Gaming Studio certification fixture becomes eligible only after all four planning decisions are resolved, then produces a deterministic approved snapshot while the original SoftwarePlan and IN_PROGRESS/PLAN project remain unchanged. Approval does not transition to ARCHITECTURE or generate architecture content.

## PLAN to ARCHITECTURE transition

ArcaDev 2.5 completes the PLAN lifecycle with the versioned `arcadev.plan_architecture_handoff` contract. The handoff binds the source project, IDEA handoff, approved-plan package, SoftwarePlan, and PlanFinalization identities, then freezes the entire approved PLAN package as the authoritative input for future architecture work. It never re-normalizes IDEA content or reruns planning.

Transition requires an IN_PROGRESS project still at PLAN, explicit approval, effective readiness, passing PLAN consistency, no unresolved questions or conflicts, and exact identity binding with no stale state. Success returns a new immutable project value that remains IN_PROGRESS and advances to ARCHITECTURE; the source project remains recoverable at PLAN.

The Gaming Studio handoff is deterministic and retains the complete approved IDEA, SoftwarePlan, planning decisions, history, consistency evidence, and approval statement. No architecture specification is generated, and no ArcaCore, backend, or frontend generator is invoked. Architecture generation begins only in a later ArcaDev increment.

Later increments may add explicit versioned contracts for planning, architecture, models, generation requests, test/security evidence, previews, and deployments. Those stages should reference this project identity and integrate with ArcaCore only through its stable public manifests and orchestration contracts. ArcaDev must not weaken or patch ArcaCore internals to advance its own workflow.

## Canonical architecture specification (ArcaDev 3.1)

`arcadev.architecture_specification`, version 1, defines an immutable `ArchitectureSpecification` at ARCHITECTURE. Its sole authoritative input is a validated `PlanArchitectureHandoff`. The specification binds the project, IDEA handoff, SoftwarePlan, PlanFinalization, ApprovedPlan, and PLAN architecture handoff identities. It consumes their frozen approved content without rerunning normalization, planning, clarification, or approval.

The contract contains an objective, system boundary, architectural style/rationale, external actors and systems, preserved approved constraints, components, interfaces, directed data flows, typed architecture aspects, open questions, and recomputed readiness. Components have stable local IDs, presentation names, categories, responsibilities, owned capability references, dependencies, exposed interfaces, and trust classifications. Connections have explicit endpoints, purpose, optional approved protocol/interaction/data classification, direction, and a trust-boundary indicator. External endpoints use approved source IDs. Unknown protocol and synchronous/asynchronous choices remain absent.

`ArchitectureAspect` associates an area and logical responsibility with responsible components, traceable constraints, and an optional approved technology. Areas cover storage, integrations, authentication/authorization, background work, deployment, security, observability, resilience, and risks. Constraint facts represent retention/deletion, access, isolation, retry/failure, authorization, scaling, and mitigation requirements when supplied. Deployment component references identify logical deployment units. The contract represents descriptive architecture only; it contains no executable configuration or generated data schemas.

### Traceability and technology selection

Each material assertion is an `ArchitectureFact`. Provenance is `approved_plan`, `approved_planning_decision`, or `deterministic_architecture_derivation`. Source references address canonical PLAN items or accepted planning decision identities. Direct facts must exactly reproduce their source. Derived facts must match a bounded named rule for logical responsibility, boundary, interaction, storage, security, observability, resilience, style, risk, or mitigation. Arbitrary prose cannot be promoted to trusted facts by labelling it derived. Names are inert presentation labels, not additional product requirements.

Every approved capability has exactly one architectural owner. Ownership sources must be included in that component's responsibility. Validation rejects invented or missing capabilities, duplicate logical components, invalid dependencies or endpoints, self-dependencies, and inconsistent exposed interfaces. Platform/authentication/integration/deployment constraints and all accepted planning decisions are retained exactly; required authentication, integration, and deployment boundaries must cite their approved sources.

Logical architecture does not choose an implementation stack. A technology field must reproduce an explicit frozen technology preference or accepted planning decision. Unknown frameworks, persistence, queues, isolation mechanisms, protocols, and topology details belong in grounded architecture questions. No cloud vendor, framework, database, telemetry provider, SLA, or infrastructure technology is inferred by default.

### Readiness, fixture, and trust boundary

Structural readiness requires valid objective/boundary/style, complete unique capability ownership, defined components, preserved required boundaries, security and deployment aspects, risks, and interfaces for material dependencies. Blocking architecture questions prevent readiness for later finalization. Readiness is recomputed; loaders reject forged values and identities. Question identities already include canonical question text, blocking state, PLAN sources, and architecture area.

The 3.1 Gaming Studio test fixture demonstrates a logical application and persistent-storage boundary covering the approved capabilities, both web platforms, both authentication methods, GitHub, and managed-cloud deployment. Its approved asset deletion policy, isolated builds, controlled releases, and authorized synchronization are preserved as fixture decisions. Concrete technologies remain unchosen and a persistence implementation question blocks readiness. These are test examples, not permanent Gaming Studio product decisions.

Strict loaders reject unknown fields, duplicate JSON keys, unsupported schemas/versions, malformed references, forged binding/readiness, duplicate collections, malformed Unicode, control characters, credential/private-key material, excessive size/nesting, and non-JSON objects. Immutable objects are reconstructed at the validation boundary. Commands, code, prompts, URLs, paths, and shell text remain inert labels or user discussion. This increment defines the contract only: no architecture engine, question resolution, approval, MODELS transition, code/data-model generation, or ArcaCore invocation.

## Future ArcaCentum Learning and Intelligence Layer

The deliberate future platform direction is ArcaKnowledge (validated reusable engineering knowledge), ArcaMemory (approved project/build decisions and history), ArcaEval (quality scoring, regression detection, and validation), ArcaTelemetry (build/test/deploy/failure observations), and ArcaModelRouter (provider-neutral selection for each task).

The ArcaLearning Loop is Build → Test → Observe → Evaluate → Repair → Validate → Promote trusted lessons. Only validated/evaluated evidence may become trusted reusable knowledge. Raw AI output, unverified user behavior, and failed builds must never be learned blindly. This layer is a future ArcaCentum platform responsibility; ArcaDev 3.1–3.3 neither implements it nor couples generated application architecture to it. ArcaOS retains higher-level company/product operational intelligence.

## Architecture generation and candidate validation (ArcaDev 3.2)

`generate_baseline_architecture` consumes only the certified frozen PLAN architecture handoff and its approved package. It creates source-derived local graph identities, logical capability owners, an application experience, required authentication and integration boundaries, and approved deployment units. Managed project/asset/build/release capabilities justify logical persistence. Explicit isolated-build planning decisions justify a separate isolated worker; explicit storage, release, and repository decisions are attached to their responsible boundaries. Security, operation outcomes, failure isolation, risks, and mitigation directions use the bounded 3.1 derivation rules. No live model, provider SDK, network, clock, filesystem, or ArcaCore generator is involved.

Implementation remains unspecified unless explicit approved evidence resolves it. Recognized bare frontend/persistence technology preferences and explicit `frontend implementation: ...`, `primary persistence implementation: ...`, or analogous implementation-slot declarations can carry an approved choice. Ambiguous or unsupported preference wording remains preserved as a constraint and leaves an implementation question open. This deliberately bounded interpretation never guesses a technology from a product capability.

The Gaming Studio fixture produces logical ownership for all five core workflows plus approved authentication and GitHub integration. It includes persistent storage, an isolated background build worker, authorization boundaries, controlled publishing, and the managed-cloud deployment target. Eight blocking questions cover frontend implementation, primary persistence, asset storage, worker isolation, background job execution, repository synchronization implementation, publishing implementation, and deployment-unit topology. They ask how to implement approved behavior, without reopening platforms, authentication methods, the integration choice, the deployment target, or resolved planning policies. The baseline remains IN_PROGRESS/ARCHITECTURE and not ready for finalization. Fixture decisions remain test-only product context.

`ArchitectureCandidateAdapter.create_candidate` is a provider-neutral interface. A trusted adapter implementation may return strict JSON text or inert mapping data; adapter execution metadata stays outside canonical artifacts. `validate_architecture_candidate` reconstructs the 3.1 contract, recomputes identity/readiness, checks exact source binding and capability ownership, and enforces the source-backed boundary and question requirements derived from the approved PLAN. A candidate may rename or regroup components while preserving those semantics. Dedicated tests merge two service responsibilities with updated edges and aspect owners, rather than requiring baseline component-name equality.

Candidates cannot invent/remove material capabilities, alter approved platform/authentication/integration/deployment decisions, remove required storage or isolation boundaries, introduce unsupported workers, discard planning-decision constraints, erase unresolved material questions, or supply broken graph references. Unknown/provider fields, duplicate JSON keys, forged identities/readiness, malformed or oversized data, secrets/private keys, invalid Unicode, and controls fail closed. Commands/code remain inert text. This increment performs no clarification, approval, MODELS transition, data-model generation, or backend/frontend generation.

## Architecture clarification and finalization (ArcaDev 3.3)

`arcadev.architecture_clarification_answer` and `arcadev.architecture_finalization`, both version 1, resolve implementation questions through explicit user evidence. `ArchitectureFinalization.start` validates the 3.2 candidate boundary before preserving the original `ArchitectureSpecification`. Every answer targets the exact architecture ID, current finalization ID, and deterministic architecture question ID. A question's identity covers its text, blocking status, approved PLAN sources, and architecture area. An ordinary answer resolves only an existing unresolved question; every other question retains its original canonical content.

`ArchitectureDecision` records the targeted question, unchanged user answer, normalized accepted values, area, PLAN sources, explicit-user provenance, quoted evidence, and optional replacement linkage and previous values. Normalized values must appear in both the unchanged answer and its evidence. Decision identities derive from that complete canonical content. No source specification, approved IDEA, PLAN, planning finalization, approval, or handoff is mutated.

### Authority, conflicts, and deliberate replacements

Architecture answers may choose previously unspecified implementations. They cannot replace upstream product authority. Whole-category tags (`platform=...`, `authentication=...`, `integration=...`, `deployment=...`, `capability=...`) must exactly preserve the corresponding approved value set. These tags describe upstream authority, not implementation slots. Common removal/replacement and exclusive wording is checked as well: removing GitHub, switching to native-only platforms, passkeys-only authentication, self-hosted-only deployment, or discarding approved storage, build-isolation, release-control, or user-authorization policies creates a blocking `ArchitectureConflict` with rejected values. PLAN remains frozen.

Conflict rules are bounded and deterministic; the resolver does not claim general natural-language equivalence. Other explicit answer text is stored only as a choice for the targeted architecture area and has no authority to edit the upstream package. Explicit architecture-area tags cannot resolve a different area. A different accepted value for the same area and exact PLAN source scope creates an accepted-decision conflict; unrelated scopes can have distinct implementations.

An already-resolved question cannot be answered again. Changing its decision requires `replace_decision` plus exact currently accepted prior values. Incorrect prior values create a blocking conflict and retain the existing decision. A valid replacement records the prior decision ID and values; it cannot override upstream authority or an incompatible accepted decision in another question. Unchanged replacement attempts, stale targets, and duplicate attempts are rejected. Correcting a conflict clears only that question's conflict and leaves unrelated state intact.

### Replay and effective readiness

Every accepted or conflicting resolution appends an `ArchitectureClarificationHistoryEntry` containing the full answer, action/outcome, previous/accepted/rejected values, resulting decision identity, readiness before/after, unresolved question IDs before/after, and full conflicts before/after. History is ordered, bounded to 256 entries, content-addressed, and contains no host timestamps. Deserialization starts from the original validated architecture, replays each answer, and compares every entry and final result using exact canonical JSON. Public resolution also replay-validates supplied finalization objects, preventing forged dataclass instances from bypassing the trust boundary.

Effective readiness reuses the 3.1 structural blocking reasons, replaces the original question blocker with the current unresolved blocking questions, and requires no active conflicts. `effective_ready_for_approval` therefore becomes true only after valid grounded decisions resolve all blockers and finalization integrity passes. This is readiness for a later approval increment, not architecture approval itself.

The Gaming Studio certification fixture resolves its eight implementation questions with explicit test-only answers: a web frontend, relational persistence, policy-controlled object storage, per-build isolated containers, persisted jobs with leased execution, an authorized repository adapter, user-triggered releases, and separate logical units inside the approved managed cloud. Concrete names such as React and PostgreSQL are fixture answers only. The test demonstrates readiness changing from false to true while the original architecture, frozen PLAN package, unrelated questions, and IN_PROGRESS/ARCHITECTURE project remain unchanged.

Strict answer/finalization loaders reject unknown fields, unsupported schemas/actions, duplicate JSON keys or normalized values, malformed Unicode/controls, secrets/private keys, oversized answers/documents/history, executable objects, forged identities/readiness/history, stale state, duplicate attempts, and nonexistent questions. Commands/code remain inert user text. ArcaDev 3.3 performs no architecture approval, MODELS transition, data-model/backend/frontend generation, deployment, or ArcaCore generator invocation.

## Final architecture consistency and explicit approval (ArcaDev 3.4)

`arcadev.approved_architecture`, version 1, consumes the certified `PlanArchitectureHandoff`, original `ArchitectureSpecification`, and replay-verifiable `ArchitectureFinalization`. Finalization records resolved decisions and effective readiness. `ApprovedArchitecture` separately records an explicit `approved` or `rejected` decision and a non-empty validated approval statement. Readiness alone never approves architecture.

The final consistency gate reconstructs upstream contracts through their certified public loaders. These enforce exact project and PLAN binding, unique capability ownership, authentication/integration/deployment boundaries, approved platform intent, supported scope, component/interface/data-flow references, and valid decision history preserving frozen PLAN authority. Invalid contracts fail closed before an evaluation is issued. Valid but unresolved blocking questions, active conflicts, or ineffective readiness produce blocking findings. Implementation compatibility that cannot be proven by deterministic rules produces a warning; approval makes no claim that concrete technologies have been tested together. Advisory questions are warnings at approval, while a later transition may require every question resolved.

`FrozenApprovedArchitecturePackage` preserves the complete authoritative PLAN handoff, original architecture, finalization with decisions/conflicts/history, and recomputed consistency. The approval identity hashes that complete canonical package, all source identities, readiness, eligibility, explicit decision/statement, and schema/version. Loaders recompute the result and reject forged consistency, eligibility, identities, decisions, or snapshots. No randomness, host clock, or provider metadata enters identity. Strict inert JSON boundaries retain the architecture size/depth limits and reject unknown fields, duplicate keys, executable objects, secrets and private keys.

Approval requires an IN_PROGRESS project at ARCHITECTURE, effective readiness, no blocking questions/conflicts, and passing consistency. An ineligible `approved` decision fails. Rejection creates an immutable non-approved result for either ready or unresolved valid architecture, preserving all original content and history. `validate_approved_architecture` can compare the complete package against caller-supplied current project, handoff, architecture, and finalization; callers supply current authority to detect a valid but superseded snapshot. Standalone deserialization proves integrity, not external freshness.

The fully resolved Gaming Studio 3.3 fixture supplies eight explicit test-only implementation decisions. Its consistency gate passes with an implementation-compatibility warning, explicit approval yields a deterministic round-trippable immutable snapshot, and rejection preserves the same architecture without approval. Both paths leave the source project IN_PROGRESS/ARCHITECTURE. Concrete technologies remain fixture choices, not permanent ArcaCentum product decisions. ArcaDev 3.4 does not transition to MODELS, generate schemas/code, or invoke ArcaCore. Certified replay internally uses the existing deterministic candidate validator and its baseline comparison; it does not regenerate or replace authoritative content or run adapters.

## ARCHITECTURE to MODELS transition (ArcaDev 3.5)

`arcadev.architecture_models_handoff`, version 1, completes the ARCHITECTURE lifecycle. `create_architecture_models_handoff` requires the current source project and an explicitly approved `ApprovedArchitecture`. It reconstructs the entire frozen package through the certified 3.4 loader, verifies an exact current project snapshot, and requires IN_PROGRESS/ARCHITECTURE, effective readiness, passing consistency, approval eligibility, explicit approval, no active conflicts, and no unresolved architecture questions. Unlike approval, transition requires even advisory questions to be resolved.

`ArchitectureModelsHandoff` embeds the complete immutable `frozen_approved_architecture`, binds the source project, PLAN handoff, approval, original architecture and finalization identities, and records transition eligibility, the `transitioned` decision and resulting project. Its deterministic content identity covers the full canonical package and resulting state. Loading recomputes the transition and rejects forged identities, eligibility, decisions, results or frozen inputs. Strict inert JSON parsing retains the architecture size/depth limits and rejects malformed/duplicate/unknown fields, unsupported schemas, secrets and executable objects.

Success returns a new project value at IN_PROGRESS/MODELS. The original project remains IN_PROGRESS/ARCHITECTURE, with unchanged identity, specification and caller-supplied metadata. Passing an already transitioned project as the current source fails. The creation and validation helpers accept current PLAN handoff, architecture and finalization references for exact full-content freshness checks; validation can also check the expected approval. A valid historical package is an integrity-proven snapshot, not evidence of external freshness unless the caller supplies current authority. Repeating the same unchanged valid source yields the same handoff identity without mutating any state.

The Gaming Studio certification starts with the explicitly approved 3.4 fixture. It verifies complete upstream identity binding, canonical round trip, frozen PLAN/architecture/finalization preservation, source immutability, and the new MODELS stage. Implementation choices remain test-only decisions. Future ArcaDev 4.x must consume this frozen approved architecture as its authoritative input rather than rerunning planning or architecture workflows, reinterpreting approval, or silently replacing technology choices.

ArcaDev 3.5 moves lifecycle state only. It creates no entities, fields, tables, schemas, ORM definitions, migrations, relationships, indexes, API contracts, backend/frontend code or deployments, and invokes no ArcaCore generator. Domain/data-model design begins in 4.x; ArcaDev 4.1 is not part of this batch. The future ArcaCentum intelligence direction and the rule that only validated/evaluated evidence may become trusted reusable knowledge remain unchanged and unimplemented here.
