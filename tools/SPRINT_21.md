# Sprint 21: Indexes

Follow the newer Indexes blueprint supplied by the user. Sprint 21 began at
GitHub main 043ef46, Sprint 20.4 Passive Deletes, with 105 relevant smoke tests.

| Feature | Status |
| --- | --- |
| Composite Indexes | Already implemented in Sprint 19.9; retained |
| Unique Together | Already implemented with Sprint 19.11 constraints; retained |
| Partial Indexes | Sprint 21.1: 118 tests passed locally; committed and pushed as 793e787 |
| Expression Indexes | Sprint 21.2: 132 relevant smoke tests passed here; complete replacement ZIP prepared; awaiting local test and commit |

The Expression Index baseline was compared with GitHub main at 793e787 before
editing. The user explicitly authorized proceeding after the previous delivery.

Sprint 21.2 adds 14 smoke tests covering functions and numeric arithmetic,
PostgreSQL and SQLite DDL, SQLite query plans, uniqueness on insert/update, mixed
keys, nulls, partial-index filters, soft-delete/restore conflicts, literal escaping,
stable names, invalid-input preflight, custom keys, CLI, registry, schema and
computed-column compatibility, relationships, and unsupported-dialect handling.

All source changes are complete file replacements inside tools/. Generated code
and databases used by the suite stay in memory. No backend files are edited.

Wait for the user's local test and commit result. Expression Indexes is the final
unfinished feature in this Sprint 21 blueprint; no Sprint 22 work is included.
