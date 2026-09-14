# Gaming Studio production SoftwarePlan

This document records the historical unanswered PLAN batch. The later
[production PLAN resolution](GAMING_STUDIO_PLAN_RESOLUTION.md) resolves the three
questions and records the current, still-unapproved PLAN checkpoint. The
historical JSON package described here remains unchanged.

This is the first genuine Gaming Studio production SoftwarePlan. The public
`generate_baseline_plan` engine consumes only the frozen approved IDEA from
`arcadev_handoff_2d8411540b13ce1eecd8c480e0f5a692`, after validating the complete
production intent, seed, explicit IDEA clarifications, finalization, metadata,
source project, handoff and resulting PLAN project.

The canonical plan is `authority/gaming_studio/production_plan/software_plan.json`.
Its schema is `arcadev.software_plan`, version 1; its deterministic identity is
`arcadev_plan_9aed1a01dad6e95cb75b6db67730dd5b`. Project
`arcadev_969321c8959864fe18393b9d2b551063` remains IN_PROGRESS at PLAN.
Readiness is computed by SoftwarePlan: false, with `blocking_planning_questions`.
No assumptions or planning answers have been supplied.

The generic engine previously emitted repeated questions and risks for distinct
features mentioning assets, builds or publishing. Unrelated delivery-console
regressions reproduced the failure before the fix. Canonical merging now retains
the union of approved source requirements, risk mitigations and blocking status.
There is no product-specific planner or readiness override.

Git's Windows checkout had converted historical IDEA-resolution JSON to CRLF.
Those files were restored to their exact committed LF bytes, and `.gitattributes`
preserves LF for authority JSON. No upstream committed content was changed.

The package deliberately stops before accepting PLAN clarification answers, finalization, approval
or architecture transition. Existing repository test suites may exercise their
own generators in temporary workspaces; production generation is not invoked.

## Production Plan 1 validation

Python 3.13.15: seven dedicated tests passed. Complete repository discovery ran
all 1,335 tests, including 603 ArcaDev tests and 36 PostgreSQL-backed tests across
seven classes. Two test-contract issues were corrected: the historical validator's
exact import allowlist now includes the PLAN authority module, and the new execution
guard patches the actual `generate_module` API. Both affected modules passed
again (19 historical authority tests and seven dedicated tests), and both exact
failed discovery IDs passed fresh recorded rechecks. No failures remain unresolved.
The only skip is the documented opt-in real Docker Compose contract.

The discovery manifest, original results and successful rechecks are retained in
`C:/Windows/Temp/arcadev-production-plan-1-full/`. Application trees, upstream
authority, protected local items and staged diff checks passed before commit.

## Production Plan 2 review

`production_plan/planning_review.json` uses schema
`arcadev.gaming_studio.planning_review`, version 1. It is reconstructed from the
validated SoftwarePlan, using `arcadev.plan_clarification.planning_question_id`.
The complete unresolved set is:

| Question ID | Exact question | Blocking |
| --- | --- | --- |
| `arcadev_question_64610a51eaf261a7116813cf9cb32d91` | What asset storage limits and retention rules are required? | yes |
| `arcadev_question_06fa970b49a43c4d5442756aa4361ccc` | Which build execution environments and isolation rules are required? | yes |
| `arcadev_question_3386cafaf9fe1e6672db5b0a9bed716f` | Which publishing targets and release controls are required? | yes |

There are no non-blocking questions. Every question retains its exact approved
IDEA source requirements; every accepted planning decision is null. The review
reports IN_PROGRESS / PLAN, zero assumptions, readiness false,
`BLOCKED_PENDING_PLAN_CLARIFICATION`, and
`COLLECT_EXPLICIT_PLAN_CLARIFICATIONS` as the next authorized action.

Advancement stops because these planning details are unresolved. A later
authorized increment must capture the user's actual words and evidence in
`PlanClarificationAnswer`, targeting the exact current plan, question and
finalization identities, and replay them through the public clarification
contract. Starting `PlanFinalization`, accepting decisions, approving PLAN and
creating a PLAN-to-ARCHITECTURE handoff are outside this batch. Existing IDEA
decisions must not be silently changed by planning answers.

[The future strategy register](GAMING_STUDIO_FUTURE_STRATEGY.md) preserves the
user's major future directions under the explicit label
**FUTURE STRATEGIC EXPANSION — NOT CURRENT PLAN AUTHORITY**. The planner and
validator never read it as authority. It changes neither plan identity nor
readiness and cannot answer any current planning question.

Production Plan 2 validation: five dedicated review tests passed. Complete
discovery ran 1,340 tests, including 608 ArcaDev tests and all 36 PostgreSQL-backed
tests: zero failures and errors, with the single documented Docker opt-in skip.
The manifest and results are retained in
`C:/Windows/Temp/arcadev-production-plan-2-full/`. The original SoftwarePlan,
historical IDEA authority and application trees remain unchanged.

## Production Plan 3 checkpoint and validation

The production PLAN area accepts exactly `software_plan.json`,
`planning_review.json` and `checkpoint.json`. The checkpoint uses
`arcadev.gaming_studio.production_plan_checkpoint`, schema version 1, production
package version 3. It extends the immutable historical packages.

The complete validation lineage is ProductionIntent → seed IdeaIntake → explicit
IDEA clarification authority → IdeaFinalization → metadata authority → source
IDEA project → IdeaPlanHandoff → PLAN-stage project → baseline SoftwarePlan →
unanswered planning review → PLAN checkpoint. The checkpoint binds all 13
upstream authority files and both new parent artifacts by SHA-256. The pinned
production-intent text digest is retained separately from its JSON-file digest.

`production_plan_package` validates the full upstream chain, calls the public
baseline engine, and reconstructs the review and checkpoint without consuming
supplied PLAN bytes as decisions. `validate_production_plan_package` checks the
exact file allowlist, local regular-file boundaries, strict canonical JSON and
complete byte equality against that reconstruction. Recomputing a plan identity,
review or checkpoint hash cannot authorize altered questions, invented scope,
answers or readiness. Unknown files, including approvals and architecture
handoffs, fail validation.

SHA-256 digests:

| Artifact | Digest |
| --- | --- |
| SoftwarePlan | `66f05a1355cc010cd452a54ecea31b271048152a1481d37e85aa7f07af847db4` |
| Planning review | `58750977de471f006f531555fcdddf7abd8012b5ff387c7279fecc3d1d0dfdf6` |
| PLAN checkpoint | `815669002156f2d3a4594f70673e0ed0eda33b0ba1568a1a459d01cf360cfe9e` |

Validate the complete current package with:

```powershell
& 'C:\ac259\Scripts\python.exe' -B -m arcadev.gaming_studio_authority --require-plan
```

`--require-plan` rejects a missing production PLAN area. Default validation
includes it whenever present. `--seed-only` explicitly validates historical seed
authority; `--require-current` continues to require IDEA-resolution authority and
also validates the PLAN package if present. A historical seed-plus-resolution
copy remains valid history, but cannot satisfy `--require-plan`.

The computed checkpoint is IN_PROGRESS / PLAN, readiness false, three unresolved
blocking questions, zero assumptions, `BLOCKED_PENDING_PLAN_CLARIFICATION`, and
`COLLECT_EXPLICIT_PLAN_CLARIFICATIONS`. It contains no planning answers,
PlanningDecision, PlanFinalization, ApprovedPlan or architecture handoff. No
ArchitectureSpecification, DomainModel, backend/frontend work, production ArcaCore
generation or Sprint 32 work is authorized by this package.

The production validator is read-only. Tests guard answer/finalization/approval,
architecture/model/backend generation, ArcaCore generation, process execution,
network calls and writes. Existing repository suites still use their own test-only
fixtures and temporary generated applications; these never supply production
planning authority.

## Canonical plan inventory

The objective is the baseline engine's exact deterministic derivation from the
approved AI-native game-development environment and controlled lifecycle goal:

> Provide build an ai-native game development environment within the arcacentum ecosystem that allows a user to describe a game idea in natural language and move through a controlled software/game-development lifecycle. that enables users to describe a game idea in natural language and move through a controlled software/game-development lifecycle.

Scope covers the approved game-project lifecycle, planning and game systems,
project/asset state, code and project-file generation, build testing and preview,
failure repair, GitHub history and non-secret integration references, distributable
builds, publishing workflows and approved authentication requirements. These are
planned product capabilities, not permission to execute production generation.

The single canonical user-role item is: Individual game creators and small/indie
game-development teams, including both non-programmers and experienced developers
who want to turn game ideas into playable software using AI-assisted development.

| Section | Count |
| --- | ---: |
| In-scope capabilities | 17 |
| User-role items | 1 |
| User journeys | 15 |
| Functional requirements | 17 |
| Non-functional requirements | 1 |
| Milestones | 2 |
| Dependencies | 1 |
| Integrations | 1 |
| Assumptions | 0 |
| Risks | 2 |
| Open planning questions | 3 |
| Blocking questions | 3 |
| Non-blocking questions | 0 |
| Acceptance criteria | 19 |
| Planning constraints | 17 |

The inspected public contracts are `arcadev/software_plan.py`,
`arcadev/planning_engine.py`, `arcadev/plan_clarification.py`,
`arcadev/plan_approval.py`, `arcadev/plan_architecture_handoff.py`,
`arcadev/idea_plan_handoff.py`, `arcadev/gaming_studio_transition.py`,
`arcadev/gaming_studio_authority.py`, and `arcadev/__init__.py`.

Production Plan 1 commit: `10e665c` — Gaming Studio Production Plan 1 - Generate canonical SoftwarePlan.
Production Plan 2 commit: `d9e0a1b` — Gaming Studio Production Plan 2 - Add planning clarification review.

## Change inventory

Production Plan 1 added `.gitattributes`, `arcadev/gaming_studio_plan.py`,
`authority/gaming_studio/production_plan/software_plan.json`, this document,
`tools/test_arcadev_gaming_studio_plan_1.py` and
`tools/test_arcadev_planning_duplicates.py`. It changed
`arcadev/planning_engine.py`, `arcadev/gaming_studio_authority.py` and the exact
import allowlist in `tools/test_arcadev_gaming_studio_authority.py`.

Production Plan 2 added `authority/gaming_studio/production_plan/planning_review.json`,
`docs/GAMING_STUDIO_FUTURE_STRATEGY.md` and
`tools/test_arcadev_gaming_studio_plan_2.py`; it changed
`arcadev/gaming_studio_plan.py` and this document.

Production Plan 3 adds `authority/gaming_studio/production_plan/checkpoint.json`
and `tools/test_arcadev_gaming_studio_plan_3.py`; it changes
`arcadev/gaming_studio_plan.py`, `arcadev/gaming_studio_authority.py` and this document.

## Final validation and stop point

Production Plan 3's 11 dedicated tests passed, with the upstream-mutation test
rechecked after correcting a no-op test mutation. The complete final discovery
also ran all 11 against the corrected source and passed without failures.

| Increment | Dedicated tests | Complete ArcaDev tests | Repository discovery | PostgreSQL-backed tests |
| --- | ---: | ---: | ---: | ---: |
| Production Plan 1 | 7 | 603 | 1,335 | 36 |
| Production Plan 2 | 5 | 608 | 1,340 | 36 |
| Production Plan 3 | 11 | 619 | 1,351 | 36 |

The final discovery result is zero failures, zero errors, and exactly one skip:
the documented real Docker Compose opt-in contract. Increment 1's two corrected
test-contract checks are documented above with successful rechecks. All seven
PostgreSQL-backed test classes passed at every increment. Complete manifests,
shard logs and the final certification record are retained under
`C:/Windows/Temp/arcadev-production-plan-3-full/` (and the corresponding increment
1 and 2 report directories).

Final integrity checks compared all 13 historical authority files byte-for-byte
with baseline `7bc10791ca61de11c7b6746bae9b634a3132474f`. The original SoftwarePlan
and planning review match their creation commits exactly. Backend source is
unchanged; frontend and shared remain empty. No generated application artifacts
were added. Future strategy remains isolated from production authority.

The branch is `arcadev-gaming-studio-production-plan`. The third commit's required
message is **Gaming Studio Production Plan 3 - Add production plan checkpoint validation**.
The final completion message reports all three commit SHAs. Protected local state
remains ` D tools.zip` and `?? .codex/`; neither item was staged or committed.
Nothing was pushed and no PR was created. Sprint 32 was not started.

The batch stops at the valid, unapproved PLAN checkpoint. No planning answers,
PlanningDecision, PlanFinalization, ApprovedPlan, PLAN-to-ARCHITECTURE handoff,
ArchitectureSpecification, DomainModel, backend/frontend production work or
ArcaCore production generation was created by this batch.
