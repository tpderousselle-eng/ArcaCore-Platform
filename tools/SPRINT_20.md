# Sprint 20: Relationships

This sprint follows the newer Relationships blueprint supplied in the development
conversation. The older docs/ROADMAP.md still labels Sprint 14 as current and
assigns different work to Sprint 20; it has not been edited during tools-only work.

Baseline: GitHub main at 6aba4b5, Sprint 19.13, with 62 relevant smoke tests.
One-to-One and Many-to-Many were already implemented during Sprint 19.

## Completed three-feature batch

| Order | Feature | Confirmed local result |
| --- | --- | --- |
| 1 | One-to-Many | 71 tests passed; committed and pushed as 1810fd8 |
| 2 | Self Relationships | 80 tests passed; committed and pushed as cf46b70 |
| 3 | Cascade Delete | 94 tests passed; committed and pushed as 9dc38fc |

The requested stop after three features was observed. The user's subsequent
instruction to continue authorized resuming with the next remaining feature.

## Current feature

Sprint 20.4: Passive Deletes. All 105 relevant smoke tests passed here, and the
complete replacement files are prepared for local testing and commit.

Wait for the user's local test and commit result before proceeding. No Sprint 21
feature is included in this delivery.

Every delivery contains complete replacement files in a ZIP. All framework
changes stay inside tools/. No manual backend modifications.
