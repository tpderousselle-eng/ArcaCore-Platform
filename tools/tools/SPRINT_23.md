# Sprint 23: Advanced fields

Sprint 23 begins after Sprint 22.5 Custom Validators, committed and pushed to
GitHub main as 4c242ab. The pushed tools source was fetched and matched against
the working source after normalizing line endings.

| Feature | Status |
| --- | --- |
| Computed fields | Already implemented in Sprint 19.13 |
| Hybrid properties | Sprint 23.1: implemented; 212 relevant tests and 213 discovery tests passed here; replacement ZIP prepared; awaiting user local test and commit |
| Encrypted fields | Pending |
| Audit fields | Pending |
| Soft deletes | Already implemented in Sprint 19.10 |
| Version columns | Pending |

Sprint 23.1 adds read-only hybrid= expressions for int, float, decimal, str, and
text outputs. Generated SQLAlchemy models evaluate hybrids on instances and
translate them into class-level SQL expressions for query composition. Hybrid
fields are Response-only in generated Pydantic schemas and do not create
database columns.

The expression parser allows deterministic numeric arithmetic and text
concatenation over local stored scalar columns. It performs type, nullability,
modifier, reference, size, complexity, and AST allowlist checks before any
generation. Hybrid properties cannot act as keys, relationships, direct indexes,
constraints, defaults, or delete controls.

Registry metadata records the original and compiled expressions plus ordered
source references only for hybrid fields. Source generation for modules without
hybrids remains byte-for-byte compatible with Sprint 22.5 across the verified
representative configurations.

The 14 new tests exercise Python and SQL behavior, recalculation, text
concatenation, exact Decimal values, nullable sources, schema read-only rules,
response validation, custom validators, CLI/registry metadata, computed fields,
soft deletes, relationships, custom keys, pre-generation rejection, constraint
boundaries, direct generator calls, compatibility, SQLite execution, and
PostgreSQL compilation.

See HYBRID_PROPERTIES.md for the complete DSL contract and local commands.

Stop after delivering Sprint 23.1. Wait for the user's local test, commit, and
push result before starting Encrypted Fields or any other feature.
