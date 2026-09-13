# Gaming Studio production authority

This is the first genuine Gaming Studio production authority. Earlier Gaming
Studio lifecycle objects and approvals in repository tests were **TEST FIXTURE
ONLY**. They are neither parents nor sources for this package.

## Approved intent root

`authority/gaming_studio/production_intent.json` is the authoritative verbatim
source, with schema `arcadev.gaming_studio.production_intent`, version 1. Its
`approved_intent` preserves the exact text from “Gaming Studio Production Intent”
through the final “later.” in the supplied approval block. Delimiter lines and
their separating blank lines are not part of the intent. Internal CRLF line
endings and Unicode punctuation are retained without normalization; the text
has 2,291 UTF-8 bytes and no terminal newline.

Intent SHA-256:
`352bd37d4ed3458030a3893f60fc36da4d360f8d55a4a0b5190688a9871690e8`.
The exact approval text is **I approve**.

The production loader pins that digest independently of the manifest. It rejects
modified text even when an attacker recomputes the claimed digest, altered
approval, unknown or missing fields, unsupported schema/version, duplicate keys,
noncanonical JSON, oversized records and invalid Unicode. Pinning the complete
approved bytes also rejects any added secret material. No timestamps or provider
metadata contribute to identity. Hash binding is an integrity check against the
repository trust root, not a digital signature or independent proof of who
supplied the approval.

Production code depends on no test helper. Validation reads bounded local files
and performs no network calls, child-process execution, application generation
or lifecycle transition. Dedicated tests are in
`tools/test_arcadev_gaming_studio_intent.py`.

The intent root grants no downstream lifecycle authority by itself.

## Canonical production IDEA

The source was reconstructed through the public `IdeaIntake.create`,
`IntentValue.create`, `ClarificationRequirement.create` and `validate_candidate`
contracts. `IdeaIntake.from_json` verifies canonical roundtrip and recomputes
readiness. The generic `normalize_idea` was inspected and attempted: its whole-
request description citation exceeds the existing 2,000-character evidence
limit on this exact request. No parser limit or certified contract was changed.
Instead, the audited mapping uses shorter literal quotations and retains the
entire original request unchanged. No fixture normalization helper is used.

The current result is **BLOCKED_PENDING_IDEA_CLARIFICATION**, at **IDEA**.
`ready_for_plan` is **false**. There is no production `ArcaDevProject`, project
metadata, finalization, PLAN transition or downstream authority. The checkpoint
is computed from the public readiness result, not from a desired outcome.

Canonical files: `authority/gaming_studio/idea_intake.json`,
`authority/gaming_studio/clarification_review.json`, and
`authority/gaming_studio/checkpoint.json`. The review schema is
`arcadev.gaming_studio.idea_review`, version 1.

### Normalized values

All 28 normalized values are EXPLICIT literal source quotations. Each carries
exact evidence. The five persistent-area entries additionally quote the required
persistence heading. There are **zero DERIVED values and zero assumptions**.
The broad `a user` reference and authentication boundary are retained while
blocking questions request their unresolved details. No canonical project type,
platform target, deployment value, domain schema, field or lifecycle enum is chosen.

- `authentication_requirements`: Authentication must identify the owner/user without storing authentication credentials inside Gaming Studio domain records.
- `explicit_constraints`: A build, integration or publishing capability must remain blocked when ArcaCore cannot represent it safely.
- `explicit_constraints`: ArcaDev determines what is authorized to be built; ArcaCore performs only capabilities it has certified support for.
- `explicit_constraints`: Gaming Studio should use ArcaDev as the development orchestrator and ArcaCore as the certified generation/runtime foundation.
- `explicit_constraints`: Initial Gaming Studio scope does not automatically include unrelated features such as multiplayer services, social networks, marketplace/e-commerce, subscriptions, achievements, analytics, AI NPC systems or other product capabilities unless they are explicitly added and approved later.
- `explicit_constraints`: The system must never silently omit unsupported approved functionality or claim a partial build is complete.
- `explicit_constraints`: Tokens, passwords, API keys and other credentials remain in dedicated secret/integration infrastructure.
- `integration_requirements`: External integrations such as GitHub must store only non-secret identifiers/references.
- `non_functional_requirements`: Game build execution must eventually occur in isolated execution environments rather than executing arbitrary user-generated code directly inside the ArcaCentum control plane.
- `primary_goal`: describe a game idea in natural language and move through a controlled software/game-development lifecycle
- `product_description`: Build an AI-native game development environment within the ArcaCentum ecosystem that allows a user to describe a game idea in natural language and move through a controlled software/game-development lifecycle.
- `proposed_project_name`: Gaming Studio
- `requested_features`: Assets — references and metadata for game assets used by the project.
- `requested_features`: Builds — build requests, status and validated build outcomes.
- `requested_features`: Game Project — the user’s game project and its controlled lifecycle.
- `requested_features`: GitHub Integration — non-secret repository identity/synchronization state.
- `requested_features`: Publishing — release/publishing workflow state and outcomes.
- `requested_features`: defining architecture and game systems
- `requested_features`: describe a game idea in natural language and move through a controlled software/game-development lifecycle
- `requested_features`: detecting and repairing failures
- `requested_features`: generating code and project files
- `requested_features`: maintaining version/history through GitHub integration
- `requested_features`: managing game-project state and assets
- `requested_features`: planning the game
- `requested_features`: producing distributable builds
- `requested_features`: supporting publishing workflows for approved target platforms
- `requested_features`: testing and previewing builds
- `target_users`: a user

### Unresolved clarification review

Every requirement below is **blocking**. These questions contain no approved
answer or suggested default. Their evidence and rationale are also preserved
in the canonical JSON review packet.

#### authentication_requirements

What authentication mechanism should identify the Gaming Studio owner/user while keeping credentials outside domain records?

Available evidence:

> Authentication must identify the owner/user without storing authentication credentials inside Gaming Studio domain records.

The identification and credential-separation boundary is explicit, but no authentication mechanism is selected.

#### deployment_requirements

Where or how should Gaming Studio be deployed?

Available evidence:

> Build an AI-native game development environment within the ArcaCentum ecosystem that allows a user to describe a game idea in natural language and move through a controlled software/game-development lifecycle.
> Game build execution must eventually occur in isolated execution environments rather than executing arbitrary user-generated code directly inside the ArcaCentum control plane.

ArcaCentum membership and eventual isolated game-build execution do not select hosting or deployment topology for Gaming Studio.

#### platform_targets

Which platforms must Gaming Studio support, and which initial game build/publishing target platforms are approved?

Available evidence:

> supporting publishing workflows for approved target platforms

Approved target platforms are mentioned but none are named; the environment's own platform targets are also unspecified.

#### project_type

What canonical software project type should Gaming Studio use?

Available evidence:

> Build an AI-native game development environment within the ArcaCentum ecosystem that allows a user to describe a game idea in natural language and move through a controlled software/game-development lifecycle.

The approved text describes a game development environment but does not select a canonical software project type.

#### target_users

Who are the initial target users of Gaming Studio?

Available evidence:

> Build an AI-native game development environment within the ArcaCentum ecosystem that allows a user to describe a game idea in natural language and move through a controlled software/game-development lifecycle.

The text authorizes a user describing a game idea; it does not specify the initial target-user segment. The broad user reference is retained without choosing a segment.

### Exact approved intent

The following display is reproduced from the approved source. The JSON root
remains the exact byte-preserving authority, including its internal CRLFs.

```text
Gaming Studio Production Intent

Build an AI-native game development environment within the ArcaCentum ecosystem that allows a user to describe a game idea in natural language and move through a controlled software/game-development lifecycle.

The platform should support planning the game, defining architecture and game systems, managing game-project state and assets, generating code and project files, testing and previewing builds, detecting and repairing failures, maintaining version/history through GitHub integration, producing distributable builds, and supporting publishing workflows for approved target platforms.

Gaming Studio should use ArcaDev as the development orchestrator and ArcaCore as the certified generation/runtime foundation. ArcaDev determines what is authorized to be built; ArcaCore performs only capabilities it has certified support for.

Required persistent product-state areas are:

Game Project — the user’s game project and its controlled lifecycle.
Assets — references and metadata for game assets used by the project.
Builds — build requests, status and validated build outcomes.
GitHub Integration — non-secret repository identity/synchronization state.
Publishing — release/publishing workflow state and outcomes.

Authentication must identify the owner/user without storing authentication credentials inside Gaming Studio domain records.

External integrations such as GitHub must store only non-secret identifiers/references. Tokens, passwords, API keys and other credentials remain in dedicated secret/integration infrastructure.

Game build execution must eventually occur in isolated execution environments rather than executing arbitrary user-generated code directly inside the ArcaCentum control plane.

A build, integration or publishing capability must remain blocked when ArcaCore cannot represent it safely. The system must never silently omit unsupported approved functionality or claim a partial build is complete.

Initial Gaming Studio scope does not automatically include unrelated features such as multiplayer services, social networks, marketplace/e-commerce, subscriptions, achievements, analytics, AI NPC systems or other product capabilities unless they are explicitly added and approved later.
```
