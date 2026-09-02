# Sprint 20: Relationships

This batch follows the newer Relationships blueprint supplied in the development
conversation. The older docs/ROADMAP.md still labels Sprint 14 as current and
assigns different work to Sprint 20; it has not been edited during tools-only work.

Baseline: GitHub main at 6aba4b5, Sprint 19.13, with 62 relevant smoke tests.
One-to-One and Many-to-Many are already implemented and are not new batch items.

## Authorized three-feature batch

| Order | Feature | Status |
| --- | --- | --- |
| 1 | One-to-Many | Local 71-test suite passed; user committed 1810fd3 |
| 2 | Self Relationships | 80-test suite passed here; prepared for local testing and commit |
| 3 | Cascade Delete | Queued; awaiting feature 2 local test and commit |

After each feature, deliver complete replacement files in a ZIP and wait for the
user's local smoke-test and commit result before implementing the next feature.
Stop after the third new feature. Passive Deletes, a fourth feature, and later
sprints require an explicit new instruction to continue.

All framework changes stay inside tools/. No manual backend modifications.
