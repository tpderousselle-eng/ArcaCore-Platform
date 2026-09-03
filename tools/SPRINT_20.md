# Sprint 20: Relationships

This sprint follows the newer Relationships blueprint supplied in the development
conversation. The older docs/ROADMAP.md still labels Sprint 14 as current and
assigns different work to Sprint 20; it has not been edited during tools-only work.

Baseline: GitHub main at 6aba4b5, Sprint 19.13, with 62 relevant smoke tests.
One-to-One and Many-to-Many were already implemented during Sprint 19.

## Completed features

| Order | Feature | Confirmed local result |
| --- | --- | --- |
| 1 | One-to-Many | 71 tests passed; committed and pushed as 1810fd8 |
| 2 | Self Relationships | 80 tests passed; committed and pushed as cf46b70 |
| 3 | Cascade Delete | 94 tests passed; committed and pushed as 9dc38fc |
| 4 | Passive Deletes | 105 tests passed; duplicate nested tools folder removed; amended commit 043ef46 pushed |

The requested stop after the first three features was observed. The subsequent
instruction to continue authorized Passive Deletes. Sprint 20 Relationships is
complete. The user then authorized starting Sprint 21; its status is recorded
in tools/SPRINT_21.md.

Every delivery contains complete replacement files in a ZIP. All framework
changes stay inside tools/. No manual backend modifications.
