# Gaming Studio production SoftwarePlan

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

The package deliberately stops before PLAN clarification, finalization, approval
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
