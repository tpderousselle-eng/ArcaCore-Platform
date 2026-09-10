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

## Future extension boundary

Later increments may add explicit versioned contracts for planning, architecture, models, generation requests, test/security evidence, previews, and deployments. Those stages should reference this project identity and integrate with ArcaCore only through its stable public manifests and orchestration contracts. ArcaDev must not weaken or patch ArcaCore internals to advance its own workflow. ArcaDev 1.3 ends at deterministic IDEA finalization and does not implement any of those future stages.
