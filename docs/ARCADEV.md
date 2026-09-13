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

ArcaDev 3.5 moves lifecycle state only. It creates no entities, fields, tables, schemas, ORM definitions, migrations, relationships, indexes, API contracts, backend/frontend code or deployments, and invokes no ArcaCore generator. Domain/data-model design begins in 4.x. The future ArcaCentum intelligence direction and the rule that only validated/evaluated evidence may become trusted reusable knowledge remain unchanged and unimplemented here.

## ArcaDev 4.1: canonical logical domain model

`arcadev.domain_model_specification` version 1 introduces immutable
`DomainModelSpecification` records bound to the certified
`ArchitectureModelsHandoff`. The binding includes project, PLAN handoff,
approved architecture, original architecture, architecture finalization, and
MODELS handoff identities. The complete frozen approved package is validated
through the 3.5 public contract. A bounded cache keys validation by complete
canonical handoff bytes, never a caller's asserted identity.

MODELS describes logical entities, fields, reusable value domains, relationships,
declarative constraints, access requirements, classifications, and open model
questions. It does not describe SQL tables, ORM classes, indexes, migrations,
API code, or database-specific types. Its bounded logical types are string,
text, integer, decimal, boolean, date, datetime, UUID, enum, JSON, binary reference,
and external reference. Collection, required, mutable, and uniqueness semantics
are explicit. Unknown identifier representation stays an identity requirement
with a blocking question; no field type or generation strategy is guessed.

Entity graph handles derive from logical name, architecture source references,
and owned capabilities. Other graph handles derive from their name, sources,
and scope. The specification identity hashes the full canonical graph and
questions, excluding computed readiness. Graph collections sort canonically;
duplicate normalized names and values, forged handles, dangling references,
contradictory bounds, unsupported types, and ambiguous identity semantics fail
validation. Legitimate relationship cycles are supported. Cardinality `many`
means zero or more; `one` is required and `zero_or_one` is optional.

Material entity responsibility derives from exact frozen capability ownership.
Storage responsibilities identify required persistent capabilities; integration
adapters require safe external reference state or a blocking reference question.
Authentication remains an external credential ownership boundary. A capability
whose persistence is not assigned by architecture can be represented as a
proposal only with an explicit blocking lifecycle question. No new product
capabilities may be introduced. Names remain presentation labels, not evidence
of semantics. Sources address frozen architecture components, aspects, the
original objective, or accepted architecture decisions.

`ModelFact` distinguishes exact approved content, a small named deterministic
derivation, and a proposed choice attached to an unresolved question. A citation
alone cannot authorize arbitrary field types, enum states, ownership, or
constraints: approved choices must repeat an exact inert declarative payload,
otherwise they require a scoped blocking model question. Defaults additionally
require explicit approved authorization. Proposed defaults and credential
storage are rejected. Decimal constraint bounds use canonical decimal text;
patterns are inert and are never compiled or executed.

Readiness is recomputed. Structural validity requires complete required
capability coverage, stable identity requirements, and resolved graph references.
Blocking model questions prevent readiness for later finalization. The manual
Gaming Studio test fixture represents projects, assets, builds, test state,
publishing, and repository references. Its test persistence, type, lifecycle,
and relationship choices are unapproved fixture proposals, not product policy.
It exercises all logical types and a cyclic relationship graph.

Strict JSON boundaries reject unknown fields, duplicate keys, unsupported
versions, malformed Unicode, controls, literal secrets and recognizable tokens,
private keys, executable objects, and oversized data. SQL, code, shell text,
and paths are inert strings. This increment stops at the contract: it provides
no model engine, clarification resolution, approval, BACKEND transition,
ArcaCore invocation, or generated application artifacts.

## ArcaDev 4.2: deterministic domain models and candidate validation

`generate_baseline_domain_model` consumes the certified MODELS handoff and its
frozen approved architecture. Storage ownership determines required state;
integration adapters require a non-secret external identifier decision. The
engine groups state by frozen architecture owner, rather than creating an entity
for every noun or a table for every relationship. An exact scoped canonical
identity-field payload in an accepted architecture decision can supply a known
identifier without reopening that choice. Free-form implementation selections
do not imply identifier types or lifecycle states.

The Gaming Studio fixture produces five required state structures: project,
asset, build, publishing, and GitHub integration state. It has 22 blocking
questions covering identifier representation, uniqueness, lookups, external and
principal references, build/publication lifecycle values, deletion policy,
ownership/cardinality, and testing-outcome representation. The frozen architecture
does not assign separate testing persistence, so that responsibility stays an
explicit question about representing/referencing outcomes. It does not become
an invented persistent Test Run entity. No passwords, OAuth secrets, timestamps,
generic metadata, guessed fields, lifecycle values, cascade rules, or join tables
are generated. The fixture remains structurally valid but not ready for later
finalization, at IN_PROGRESS/MODELS.

`DomainModelCandidateAdapter.create_candidate` is a provider-neutral protocol.
Trusted adapter code may return plain inert mappings, a mapping proxy, or JSON.
The canonical module includes no provider SDK or live network call. Arbitrary
mapping subclasses are rejected before their methods can execute. Candidate
validation uses the 4.1 contract to recompute identity, readiness, exact binding,
and all graph/type/provenance checks, then enforces required capability coverage,
frozen ownership boundaries, and preservation of every unresolved material
question. Required question wording is deterministic and refers to frozen
architecture responsibility rather than candidate entity labels.

Entity renaming is accepted when capability coverage and question scope remain
complete. Grouping follows the approved owner: a separate test fixture explicitly
groups architecture responsibilities and chooses a UUID identifier upstream;
the model preserves both decisions. A candidate cannot merge distinct frozen
owners for convenience. Proposed fields, value domains, relationships, constraints,
and access requirements must cite the appropriate retained model question or
an exact approved declarative payload. Additional unrelated questions cannot
launder invented material content into a candidate. Logical proposals remain
unapproved while their questions are open.

Dedicated adversarial tests cover candidate adapters, alternate grounded
reference/lifecycle/relationship proposals, renaming, approved grouping,
state/question removal, invented scope, forged binding/readiness, malformed and
oversized JSON, unknown metadata, secrets, and inert hostile labels. Neither
the engine nor its candidate boundary resolves questions, approves models,
transitions to BACKEND, generates SQL/ORM/migrations/APIs, or invokes ArcaCore.

## ArcaDev 4.3: explicit model clarification

`arcadev.model_clarification_answer` and `arcadev.model_finalization` are version
1 immutable contracts. `ModelFinalization.start` validates the original model
through the 4.2 candidate boundary. A clarification targets its exact model ID,
current finalization ID, and a question ID already present in that original.
Question identities reuse 4.1 canonical question text, blocking status, area,
architecture sources, and affected entity/relationship references. An answer
preserves the raw user text and requires literal evidence for every normalized
choice; it cannot infer consent or resolve another question as a side effect.

Each accepted `ModelDecision` records its deterministic identity, original
question, unchanged answer, accepted values, affected model elements, architecture
source references, explicit-user provenance, evidence, and replacement metadata.
Typed `ModelClaim` records bound the chosen logical details to existing entities.
The original specification and every upstream frozen package remain unchanged;
the effective model is the original plus its explicit decision layer. Proposed
choices in the original remain proposals unless supported by accepted decisions.

The initial bounded vocabulary supports logical identity types (`uuid`, `string`,
`integer`, `external_reference`), external principal IDs, non-secret external
identifier references, explicit lifecycle/retention labels, identity-only
uniqueness and identity lookups, and testing-outcome references on existing state.
Relationship answers use canonical inert JSON with source/target entity IDs,
source/target cardinality, ownership, and deletion behavior, covering the affected
records. The explicit `independent` choice represents no relationships among
those records. Logical cardinality and ownership use the 4.1 vocabulary. These
choices describe domain intent; they specify no physical index, database key
generation, foreign key, migration, or runtime operation. Unsupported choices
remain blocking conflicts rather than receiving guessed semantics.

ARCHITECTURE remains authoritative for responsibilities, capabilities, persistence
requirements, and accepted implementation boundaries. MODELS can choose unresolved
logical details. Bounded rules detect explicit removal of required architecture
state/policies, unsupported product capabilities, another question's area, and
contradictory decisions governing the same logical choice and entity scope.
This is a deterministic contract boundary, not a general natural-language judge.
Conflicts preserve accepted decisions and unresolved questions and block effective
readiness. A later valid answer for the same question can clear its conflict.
Stale, replayed, forged, nonexistent, or already-resolved targets are rejected.

`replace_decision` requires an existing decision and exact currently accepted
prior values. A mismatch records a conflict without overwriting that decision.
A successful replacement records the predecessor decision ID and previous values;
an unchanged replacement is rejected. Replacement cannot override architecture.
Every attempt appends deterministic history containing the answer/action,
accepted/rejected/prior values, outcome, resulting decision, readiness before and
after, unresolved question IDs, and conflicts before and after. Round trips and
public resolution replay the full history and compare every event and canonical
state; asserted identities, decisions, histories, and readiness are never trusted.

Effective readiness reuses original structural validity and structural blockers,
then requires all blocking model questions resolved and no active conflict.
Nonblocking questions alone do not prevent readiness. Safety limits are 256
history entries, 100,000 characters per answer, 5 MB per serialized document,
and the shared bounded JSON depth/collection rules. Unknown fields, duplicate
JSON keys, duplicate Unicode-normalized values, malformed Unicode, controls,
literal secrets/tokens/private keys, and executable serialized objects fail
validation. SQL/code/commands in permitted text remain inert.

The Gaming Studio test fixture explicitly resolves all 22 baseline questions:
UUID identities, external principal IDs, repository references, build/publication
states, deletion/retention labels, project relationships, identity uniqueness and
lookups, and a build-owned testing-outcome reference. These are TEST FIXTURE ONLY
decisions, not production defaults. Each answer removes exactly one question;
effective readiness moves from false to true while the five original entities,
original model bytes, approved architecture, and IN_PROGRESS/MODELS project remain
unchanged. This increment stops before model approval and before BACKEND: it adds
no approval contract, transition, SQL/ORM/migrations/API generation, or ArcaCore
invocation.

## Final logical model consistency and explicit approval (ArcaDev 4.4)

`arcadev.approved_domain_model`, version 1, separates effective model readiness
from explicit approval. `approve_domain_model` and `reject_domain_model` consume
the certified `ArchitectureModelsHandoff`, original `DomainModelSpecification`,
and replay-valid `ModelFinalization`. They preserve complete frozen authority;
they do not run an adapter, obtain new decisions, or replace earlier stages.
Certified candidate validation may reconstruct a deterministic baseline solely
to validate the original state, as required by the existing 4.3 replay contract.

`FrozenApprovedDomainModelPackage` contains the complete architecture handoff,
original model, finalization (including all decisions, questions, conflicts and
history), final consistency, and `ResolvedLogicalModel`. The resolved view
combines original choices already authorized by frozen architecture with accepted
structured `ModelClaim` records and their decision/question IDs. It retains
entity identity and capability ownership. Identity, principal/external/outcome
references, lifecycle/value domains, retention, relationship cardinality and
ownership/deletion, uniqueness and lookup slots have the bounded 4.3 semantics.
Consumers need no interpretation of user answers or quoted evidence.

Question-backed candidate fields, domains, relationships, constraints and access
requirements remain proposals in the immutable original specification. They are
excluded from the resolved view; resolving their question authorizes its accepted
claims, not every proposed detail. The view deliberately does not invent physical
fields, storage technology, SQL, tables, ORM classes, migrations or APIs.

Final consistency reuses certified 4.1/4.2 structural, logical type, capability,
ownership, source, credential and scope validation and full 4.3 decision/history
replay. It checks accepted identity coverage, closed references and contradictions
with frozen lifecycle, relationships and uniqueness in the combined view. Invalid
or forged source inputs fail loading. A bounded source-replay cache uses complete
canonical content, never asserted IDs, and stores only validated immutable values.
Valid unresolved blockers, active conflicts, ineffective readiness, missing
accepted identity or a frozen relationship contradiction yield BLOCKING findings.
Unknown backend implementation compatibility is a WARNING, not a logical blocker;
unresolved advisory questions also produce a warning.

Explicit APPROVED requires IN_PROGRESS/MODELS, effective readiness, passing
consistency, zero blocking findings, zero blocking questions and zero conflicts,
plus a nonempty validated statement. Readiness alone grants no approval.
Explicit REJECTED records an immutable non-approved artifact even for a valid
unready or conflicted model, preserving all original and finalization content.
Neither decision changes the source project or transitions to BACKEND.

The approval identity hashes canonical schema/version, every upstream identity
(project, PLAN handoff, architecture approval/specification/finalization, models
handoff, model specification/finalization), the complete package, consistency,
readiness, eligibility, explicit decision and statement. No new timestamps,
randomness or provider metadata are introduced. Equal authority and decision
content produce identical canonical approval. Loaders reconstruct derived fields,
reject unknown fields/duplicate JSON keys/unsupported versions/oversize data and
credentials, and treat permitted SQL/code/shell-looking text as inert data.

`validate_approved_domain_model` proves embedded integrity standalone. Optional
current project, handoff, model and finalization references must match complete
canonical content, not asserted IDs. Without current references, a historical
artifact cannot establish that newer external authority does not exist.

The complete Gaming Studio 4.3 TEST FIXTURE ONLY decisions resolve all 22 original
blocking questions. Certification verifies false initial readiness, true effective
readiness, passing consistency with an implementation warning, deterministic
explicit approval and canonical round trip, immutable rejection, and unchanged
approved architecture, models handoff, original model, finalization and source
IN_PROGRESS/MODELS project. These choices remain fixture decisions, not universal
Gaming Studio defaults. ArcaDev 4.4 stops before the BACKEND transition.

## MODELS to BACKEND transition (ArcaDev 4.5)

`arcadev.models_backend_handoff`, version 1, completes the MODELS lifecycle.
`create_models_backend_handoff` requires the current source project and a certified
explicitly approved `ApprovedDomainModel`. The 4.4 validator reconstructs the
complete frozen package, final consistency and resolved logical-model authority.
This gate consumes that authority without changing decisions or interpreting
clarification prose. Certified replay is validation only, as described for 4.4.

The source must be IN_PROGRESS/MODELS. Transition requires explicit APPROVED,
`approved` and `approval_eligible` true, effective model readiness, passing
consistency, zero blocking findings and zero active conflicts. It is stricter
than approval: **every unresolved model question, including an advisory question,
must be resolved before BACKEND**. Rejected, forged, stale, unready, conflicted,
wrong-stage and already-transitioned current sources are refused.

`ModelsBackendHandoff` embeds the complete `frozen_approved_domain_model`. It binds
project identity, PLAN handoff, approved architecture, architecture specification
and finalization, architecture/models handoff, original model specification,
model finalization and model approval identities. Its content-derived handoff ID
hashes schema/version, those bindings, the full frozen approval, eligibility,
explicit `BackendTransitionDecision.TRANSITIONED`, and resulting project. Equal
unchanged authority yields equal canonical bytes and identity. It introduces no
timestamps, random material or provider metadata.

Success returns a new immutable IN_PROGRESS/BACKEND project value with the same
project identity and metadata. The source remains IN_PROGRESS/MODELS, and the
frozen model, history, decisions and complete upstream authority remain unchanged.
Repeated use of the same unchanged MODELS snapshot is deterministic; supplying
the resulting BACKEND project as a current source is rejected.

Standalone loading reconstructs the embedded approval and verifies every asserted
identity, flag, decision and resulting project. `validate_models_backend_handoff`
additionally accepts optional current project, approved model, architecture/models
handoff, model specification and model finalization references. These must match
complete canonical content, not IDs alone. Standalone historical integrity does
not establish external freshness without current references. Shared bounded JSON
validation rejects unknown fields, duplicate keys, unsupported versions, secrets,
tokens, private keys and executable objects; permitted hostile-looking text is
inert data.

The Gaming Studio certification follows the complete MODELS lifecycle: original
unready model, 22 explicit TEST FIXTURE ONLY decisions, effective readiness,
final consistency, explicit model approval, then deterministic BACKEND handoff.
It verifies exact upstream binding, canonical round trip, deep immutability,
unchanged source/architecture/model/finalization/approval, stale-current-reference
checks, rejection of already-transitioned sources, and the stricter advisory rule.

ArcaDev 4.5 changes lifecycle state only. It generates no backend/frontend source,
routers, services, repositories, API contracts, SQL, tables, ORM/Pydantic
implementation models, migrations, indexes, physical constraints, Docker or
Kubernetes changes, or deployment files, and invokes no ArcaCore generator.
BACKEND implementation begins in ArcaDev 5.x; 5.1 is not implemented here.

## Canonical backend authority (ArcaDev 5.1)

`arcadev.backend_specification`, version 1, describes implementation obligations
and consumes the public `ModelsBackendHandoff` validator. Its immutable
`BackendSpecification` binds project, handoff, approved architecture/specification/
finalization and approved model/specification/finalization identities. An additional
content identity binds the **complete** handoff, including all upstream packages
and the resulting IN_PROGRESS/BACKEND project. Loading requires that handoff;
standalone asserted IDs cannot establish source integrity or freshness.

`resolved_model` retains the complete 4.4 `ResolvedLogicalModel`. Data bindings
assign each approved persisted entity to its frozen capability owner. The resolved
view carries approved fields, value domains, relationships, constraints, accesses,
and accepted structured choices with ModelDecision provenance. Proposed fields in
the original model never become approved implementation fields. Every accepted
architecture decision is also retained as exact evidence, including persistence
technology, isolated execution, authorized synchronization and release control.

Backend components retain exact architecture responsibilities, capabilities,
interfaces, dependencies and model ownership. A bounded `BackendRole` constrains
their implementation role. Names are inert presentation labels; compatible
components may be grouped without transferring their frozen capability ownership.
Operations express the approved capability as a logical workflow or integration
action. They retain exact owner and model references, including test outcomes
accepted on build state. This deliberately avoids automatic per-entity CRUD.

`BackendPolicy` represents authentication/principal, integration, storage and
background boundaries with exact evidence, owners, operation scope, input
authority, resulting logical state and external-boundary references. Principal
ownership is the accepted non-secret model reference, not local credentials.
Background state follows the approved worker's callers. Optional retry,
idempotency, transaction and bounded failure fields reserve explicit semantics;
unspecified runtime choices cannot be asserted by a candidate. Frozen boundary
payloads remain intact. Accepted architecture decisions still govern when an
optional backend refinement is null; null does not erase an upstream choice.
Material implementation unknowns use `BackendQuestion`,
whose identity includes text, blocking flag, area, architecture/model sources and
affected components/operations. Resolving backend questions cannot reopen approval
of authentication, GitHub, lifecycle, persistence or isolation.

Facts either retain one exact frozen source or use a named derivation that
preserves exact source payloads. They cannot paraphrase unsupported behavior into
authority. Structural validation recomputes complete coverage, references,
ownership and boundaries; blocking backend questions separately prevent readiness
for later approval. 5.1 structural readiness alone is not backend approval and is
not proof that all material implementation questions have been enumerated.

Canonical loaders reconstruct all derived values and reject unknown fields,
duplicate JSON keys, unsupported versions, malformed Unicode/control characters,
credentials/private keys/tokens, executable objects, forged IDs/readiness and
invalid graph/model references. Shared limits are 5 MB per document, 256 items per
collection, depth 40 and 100,000 characters per general inert text value; component
and operation labels are bounded to 240 characters. SQL/code/commands are never
executed. Gaming Studio is representable with nine frozen backend responsibilities,
seven logical capability operations and five exact persisted-entity bindings.

This authority layer does not generate source, SQL, ORM, migrations, transport
routes or ArcaCore inputs. It invokes no generator and performs no approval or
FRONTEND transition. Deterministic baseline generation and clarification follow
in 5.2 and 5.3 respectively.

## Backend specification generation and candidates (ArcaDev 5.2)

`generate_baseline_backend_specification` consumes the certified public handoff
and its complete resolved model. It retains architecture ownership units rather
than creating a service or generic CRUD set per entity. Each approved capability
has one logical workflow/integration operation. Shared storage, identity and
worker boundaries remain separate when frozen architecture requires them.
Testing uses its accepted build-owned outcome reference; contextual citations to
other owners do not grant those operations additional model state.

The Gaming Studio baseline has nine components, seven logical operations, five
data bindings and ten blocking implementation questions. They address physical
naming, transport, related-state atomic writes, worker completion delivery,
integration failure handling and retry, release/sync deduplication, storage
reference mapping and certification before generation. They do not reopen
PostgreSQL, managed storage, authentication, GitHub, logical identities or
relationships, isolated containers, leased execution or idempotent build-job
identifiers. Readiness is false; the project stays IN_PROGRESS/BACKEND.

`BackendSpecificationCandidateAdapter.create_candidate` is a provider-neutral
protocol returning JSON text or inert mapping data. Trusted adapter implementation
code is separate from its untrusted return value. Canonical implementation imports
no provider SDK and makes no network calls. Validation uses the 5.1 loader to
reconstruct identities, readiness, exact resolved data, ownership and policy
boundaries. It then reconstructs required material questions and matches their
frozen sources and model/operation scope. Components may be renamed or compatible
owners grouped: question targets follow the units containing those exact owners,
not their presentation labels. Boundary record and operation scope is derived
from the original architecture owners even inside a grouped unit: grouping asset
and project services never grants asset storage policy authority over project
records or operations. An advisory refinement may narrow an existing
question using the exact `Advisory review: ` prefix and original question text;
it cannot introduce new scope, reopen a frozen choice or remove any blocker.

The ArcaCore compatibility inspection was read-only: `tools/generate.py` exposes
`generate_module(name, field_strings)`; `ModuleDefinition` supplies physical
module/class/table/field metadata; `ApplicationManifest`/`RuntimeContract` bind
accepted module provenance and a FastAPI runtime with PostgreSQL or no database.
`tools/jobs.py` supplies registered trusted handlers, bounded retry, authorization
and idempotency primitives; `tools/sdk.py` provides a bounded version 1.0 SDK.
These public contracts do **not** certify an application-specific GitHub adapter,
publishing adapter, persisted leased job implementation or OCI isolation launcher.
The explicit compatibility question requires a certification precondition before
any later generation. No capability is silently dropped or declared supported.
Backend authority approval readiness and certified generation eligibility are
different gates; later translation must fail closed when a required capability
has no certified generator representation.

No ArcaCore tool is invoked by this module. No source, module declaration, SQL,
migration, ORM, route, deployment configuration or generated application artifact
is emitted. Existing repository runtime tests retain their certified temporary
generation behavior. ArcaDev itself remains the authority/validation layer.

## Backend clarification and effective readiness (ArcaDev 5.3)

`BackendFinalization.start` validates the original specification through the 5.2
candidate boundary, including every material question. The immutable original
and complete frozen handoff remain unchanged. `arcadev.backend_clarification_answer`
and `arcadev.backend_finalization` use schema version 1. An answer targets the
exact backend, current finalization and original question. Canonical question
identity includes text, blocking flag, area, architecture/model sources and
affected component/operation IDs, with no time or randomness.

`BackendDecision` retains the complete source question, unchanged explicit user
answer, accepted values, quoted evidence, exact affected scope, structured claims
and explicit-user provenance. Decision identity hashes that complete record.
`BackendClaim` contains a bounded slot, component/operation/model references and
profile semantics. The supported profiles are deliberately small:

| Area | Explicit accepted profile | Bounded meaning |
| --- | --- | --- |
| Persistence mapping | `snake_case_unfixed_names` | Snake case for unfixed physical names only; preserve approved logical state. |
| API boundary | `http_json` | HTTP/JSON exposure preserving frozen authorization. |
| Transaction | `operation_atomic` | Atomic related-state writes per operation, preserving approved constraints. |
| Async execution | `authenticated_completion_callback` or `authorized_status_polling` | Completion delivery preserving frozen execution and isolation. |
| External integration | `no_automatic_retry` or `transient_retry_twice_no_delay` | One attempt, or at most two for transient failures with no delay, under explicit user authorization. |
| Failure semantics | `return_failure_without_state_promotion` | Surface external integration failure without promoting unsuccessful state. |
| Idempotency | `caller_request_key` | A request key scoped by principal and operation, preserving explicit action control. |
| Storage | `entity_identity_reference` | Existing entity identity reference, preserving retention/deletion. |
| Implementation technology | `require_generator_capability_certification` | Certify all approved responsibilities before generation; fail closed for missing representations. |

These are supported choices, not automatically selected defaults. Profile names
and quoted evidence must occur in the unchanged explicit answer. A request key
is a non-secret invocation control reference, not a new logical field or a rule
preventing all future actions on the same entity. Failure handling adds no
lifecycle values. Profiles create no physical columns, routes, handlers or code.
Other profiles/areas remain unresolved until a supported contract exists.

The authority hierarchy remains IDEA/PLAN, frozen ARCHITECTURE, approved resolved
MODELS, then question-scoped BACKEND choices. A bounded deterministic recognizer
reports explicit architecture removal, isolation/technology changes and approved
relationship/state removal. Relationship checks use actual resolved edges and
accepted model claims, never merely proposed relationships. This is not a general
natural-language consistency evaluator: only whitelisted structured claims grant
implementation authority; raw prose must never become translator instructions.
Unsupported scope, area mismatch and uncertified generator representations create
conflicts. Existing decisions with different semantics for the same slot and
overlapping operation scope conflict; model/component scope is the fallback when
operations are absent. Grouped owners do not conflate unrelated release and
repository operations.

Ordinary answers cannot resolve an already resolved question. Deliberate
`replace_decision` requires an existing decision and its exact accepted prior
values; an unchanged replacement is rejected. Accepted replacements link the old
decision ID and preserve prior values/history. Conflicting replacements retain
the prior decision and create a blocking conflict. A corrected new answer can
clear its question's conflict while retaining the rejected attempt in history.

Every attempt records action, accepted/rejected/prior values, resulting decision,
readiness, unresolved question IDs and conflicts before/after. Loading and public
resolution replay all history, reject stale targets and duplicate attempts, and
compare recomputed complete state/identity. Inputs use strict inert JSON, exact
fields/version, Unicode/control/credential checks, duplicate-key/value rejection,
100,000-character answers, 256 history entries and the shared 5 MB document limit.
Source/SQL/shell-looking evidence stays inert; arbitrary executable claims and
serialized objects are rejected.

Effective readiness requires structural validity, every blocking question
resolved, no active conflicts and valid identity/replay. Advisory questions may
remain open but an active advisory conflict also blocks readiness. The Gaming
Studio TEST FIXTURE ONLY answers resolve the ten questions actually emitted by
5.2, yielding ten decisions and effective readiness while preserving the original
unready specification and IN_PROGRESS/BACKEND project. This does not approve the
backend, transition to FRONTEND or certify generation eligibility. In particular,
the compatibility decision preserves the mandatory future certification gate;
it does not assert that current ArcaCore represents GitHub/publishing handlers,
OCI execution or persisted leased jobs. No ArcaCore invocation, source generation,
provider call or application-file output occurs in this lifecycle.

## ArcaDev 5.4: explicit BACKEND approval

`approve_backend` creates immutable `ApprovedBackend`
(`arcadev.approved_backend`, version 1) only with an explicit nonempty human
approval statement and a current IN_PROGRESS/BACKEND project. Readiness alone
does not approve anything. `reject_backend` records explicit rejection without
changing the specification, finalization, or project stage.

The frozen package contains the complete ModelsBackendHandoff (including PLAN,
Architecture and approved logical model authority), original BackendSpecification,
replay-validated BackendFinalization with its complete history, reconstructed
consistency evaluation and deterministic resolved backend authority. The resolved
view separates frozen components/bindings/operations/policies from accepted
bounded implementation choices and remaining provisional questions. Each choice
retains its exact decision ID, question ID, slot and scope; user prose is evidence.

Final validation reconstructs upstream ownership, state, authorization and graph
contracts, and replays decisions to reject invalid history, contradictory claims,
unsupported scope and credentials. Blocking questions, active conflicts and
ineffective readiness prevent approval. ArcaCore compatibility is a warning:
approval certifies WHAT is authorized, not whether ArcaCore can generate it.

Identity includes the entire canonical package, decision and statement without
timestamps, randomness or provider metadata. `validate_approved_backend` compares
supplied current references by complete canonical content, including the project;
standalone integrity cannot establish external freshness. Deserialization
reconstructs consistency and resolved authority instead of trusting asserted IDs.
Neither approval nor rejection transitions to FRONTEND or invokes a generator.
The dedicated Gaming Studio fixture explicitly resolves all ten 5.3 blockers and
approves the backend. Those decisions are test data, never universal defaults.

## ArcaDev 5.5: certified, non-executing generation request

`ArcaCoreGenerationRequest` (`arcadev.arcacore_generation_request`, version 1)
consumes only an explicitly approved `ApprovedBackend`. It retains that complete
canonical binding, including project, handoff, backend/finalization, approved model
and architecture identities. Optional current references must match full content.
Loading a request reconstructs all translations, mappings, findings and eligibility;
caller-supplied SUPPORTED flags, omitted responsibilities and partial scope fail.

Every entity, data binding, component, logical operation, backend policy, accepted
backend decision, frozen architecture implementation decision and PLAN constraint
has a deterministic mapping. SUPPORTED means a reviewed public generation contract
represents that scope. UNSUPPORTED identifies absent application generators.
REQUIRES_CERTIFICATION means a primitive or logical choice exists but its complete
translation has not been certified. Eligibility requires every mapping to be
SUPPORTED and at least one complete module. Supported subsets never authorize
partial generation of an ineligible backend.

The reviewed public contracts are `tools.generate.generate_module` and its public
`python -m tools.generate` entrypoint, `tools.core.module_definition` (including
`module_output_path`), `tools.core.field_parser`, `tools.application_manifest`,
`tools.minimal_regeneration`, `tools.schema_lifecycle`, `tools.runtime_harness`,
`tools.build_orchestrator`, `tools.authorization`, `tools.jobs`, `tools.sdk`, and
the public standard-layer generators and their generated router/model contracts.
The standard generator produces model, schema, CRUD, service, router and registry
surfaces. PolicyContract, JobExecutor and SDK operations are not proof that custom
authentication providers, GitHub/publishing handlers or isolated build workers
can be generated. BuildOrchestrator validates existing authority and runtime
evidence; it is not a universal application generator.

The initial certified translator is deliberately bounded: an explicit standard
ArcaCore CRUD capability, PostgreSQL persistence, and generated principal/read-write
scope checks against an existing trusted middleware contract. It does not generate
that middleware or an authentication provider. Its fixture approves named scalar
fields, a caller-supplied string identity, an external principal reference, and
the generator-managed `created_at`/`updated_at` fields and their time behavior.
This avoids silently adding CRUD, authorization, physical fields or identity
defaults. UUID/integer generated identity defaults, other logical choice profiles,
relationships, value domains, constraints and access translations require further
certification when not represented by this bounded translator.

Physical naming uses only the accepted 5.3 `snake_case_unfixed_names` decision.
Module requests preserve exact entity/field/decision provenance and pass the public
declaration parser and module validator without invocation. Paths, commands and
unsupported identifiers cannot become physical names. The request exposes no
output path, executable or arbitrary environment fields. Secret values, unknown
fields/capabilities, duplicate JSON keys, unsupported versions and excessive size
are rejected. Environment requirement names remain empty unless a certified
translation provides their authority; credentials are never inferred or embedded.

ApplicationManifest planning lists intended modules/runtime and explicitly pending
observed generation provenance, accepted schema revisions and runtime validation.
It does not fabricate GenerationManifest or ApplicationManifest digests.

Gaming Studio's approved backend remains valid but **ineligible for generation**.
Its GitHub adapter, publishing handler and isolated worker have no certified public
application generator. Persisted job behavior, storage, authorization and logical
state/implementation mappings also retain explicit compatibility blockers. The
independent minimal module fixture is eligible; Gaming Studio authority is not
weakened to obtain that result. 5.5 invokes no generator, creates no application
artifacts and keeps the project IN_PROGRESS/BACKEND.

One necessary public ArcaCore contract correction accompanies 5.5: standard
generated update schemas and CRUD methods now reject every primary-key field,
including implicit IDs and composite keys. Previously those surfaces permitted
identity mutation, contradicting every approved ArcaDev model's immutable logical
identity. The change is in the trusted generator inputs (`generate_schema.py`,
`generate_crud.py` and their templates), never a patch to generated application
source. Five separate public-generator tests generate only temporary evidence and
verify rejection before database access, normal updates, and unchanged creation.
This is the batch's explicit, necessary exception to preserving production
`tools/` byte-for-byte. ArcaDev's 5.5 request creation remains non-executing.
