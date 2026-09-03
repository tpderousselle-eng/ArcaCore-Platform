# Sprint 21: Indexes

Follow the newer Indexes blueprint supplied by the user. Baseline is GitHub
main at 043ef46, Sprint 20.4 Passive Deletes, with 105 relevant smoke tests.
Source files were compared with that revision before implementing this feature.

| Feature | Status |
| --- | --- |
| Composite Indexes | Already implemented in Sprint 19.9; retained |
| Unique Together | Already implemented with Sprint 19.11 constraints; retained |
| Partial Indexes | Sprint 21.1: 118 relevant smoke tests passed here; complete replacement ZIP prepared; awaiting local test and commit |
| Expression Indexes | Not started |

Sprint 21.1 includes 13 new smoke tests: filtered nonunique indexes, PostgreSQL
and SQLite DDL, SQLite reflection/query planning, filtered uniqueness, updates,
soft-delete/restore conflicts, boolean and null predicates, literal escaping,
numeric precision, stable names, invalid-input preflight, custom keys, CLI,
registry, schema compatibility, relationships, and unsupported-dialect handling.

All source changes are complete file replacements inside tools/. Generated
code and databases used by the suite stay in memory. No backend files are edited.

Wait for the user's local test and commit result before starting the next
feature. This delivery contains no Expression Index implementation.
