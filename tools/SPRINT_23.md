# Sprint 23: Advanced fields

Sprint 23 begins after Sprint 22.5 Custom Validators, committed and pushed to
GitHub main as 4c242ab. The pushed tools source was fetched and matched against
the working source after normalizing line endings.

| Feature | Status |
| --- | --- |
| Computed fields | Already implemented in Sprint 19.13 |
| Hybrid properties | Sprint 23.1: implemented, locally tested, committed, and pushed |
| Encrypted fields | Sprint 23.2: implemented, locally tested, committed, and pushed |
| Audit fields | Sprint 23.3: implemented, locally tested, committed, and pushed |
| Soft deletes | Already implemented in Sprint 19.10 |
| Version columns | Sprint 23.4: implemented; 254 relevant tests and 255 discovery tests passed here; replacement ZIP prepared for local verification |

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

See HYBRID_PROPERTIES.md for the complete Sprint 23.1 DSL contract.

Sprint 23.2 adds encrypted and encrypted=KEY_ENV modifiers for str and text
fields. Generated SQLAlchemy models use a TypeDecorator backed by AES-256-GCM,
with a fresh nonce per write, table-and-field associated data, authenticated
decryption, versioned ciphertext, and first-key-active keyring rotation. Key
values are read only at runtime and never enter generated source or registry
metadata.

Generated Pydantic schemas continue to accept and return plaintext and expose
x-arca-encrypted metadata. Randomized encrypted fields are deliberately excluded
from keys, defaults, relationships, searches, indexes, unique constraints,
checks, computed inputs, and hybrid inputs. Modules without encrypted fields do
not import cryptography and retain their prior generated output.

The 14 new tests cover real database encryption, randomized writes, updates,
Unicode and nullable data, schema validation, CLI/registry metadata, missing and
invalid keys, authenticated tamper detection, wrong keys, cross-column swaps,
key rotation, query rejection, PostgreSQL DDL, invalid declarations,
index/constraint boundaries, computed/hybrid boundaries, direct programmatic
preflight, soft-delete composition, custom primary keys, and compatibility.

See ENCRYPTED_FIELDS.md for the complete Sprint 23.2 contract, dependency, key
setup, rotation guidance, security boundaries, and local commands.

Sprint 23.3 adds a module-level `audit_fields` option. It supplements the
existing timestamps with indexed `created_by` and `updated_by` foreign-key
columns using conventional `users.id` integer actors or a configured int, str,
or UUID actor key. Generated input schemas reject all four service-managed
audit values, while Response schemas expose them as read-only metadata.

Audit-enabled soft delete and restore operations require a trusted actor ID and
update the row attribution transactionally. Composite and partial indexes,
constraints, and index predicates can reference generated actor columns.
Registry metadata records the actor target and type without changing the
ordinary field list. Modules without audit fields retain their previous
generated and registry shapes.

The 14 new tests cover parser defaults and custom actor keys, SQLite round
trips, PostgreSQL DDL, timestamps, schemas and JSON metadata, soft-delete and
restore attribution, idempotency, rollback, CLI/registry output, indexes,
constraints, expression-index boundaries, reserved names, direct generator
preflight, advanced-field composition, and compatibility.

See AUDIT_FIELDS.md for the complete Sprint 23.3 contract and trust boundary.

Sprint 23.4 adds a module-level `version_column` option. Generated models use a
non-null integer `version_id` initialized to 1 as SQLAlchemy's mapper version
column. ORM updates advance it and include the previous version in the update
predicate, so concurrent stale writes raise `StaleDataError` instead of
silently overwriting newer state.

Generated Create and Update schemas reject the service-managed value, while
Response schemas expose it as required read-only metadata. Composite and
partial indexes, constraints, and index predicates may reference the generated
column. Registry metadata records its name, types, and initial value without
changing the ordinary field list.

Versioning composes transactionally with audit attribution, soft delete and
restore, advanced fields, custom keys, and relationships. No-op delete and
restore calls do not advance a version. Modules without versioning retain their
previous generated and registry shapes. The feature covers per-instance ORM
flushes; bulk DML and historical revision storage remain outside its scope.

The 14 new tests cover declaration order, generated model and PostgreSQL DDL,
registry metadata, inserts and repeated updates, stale-write rejection, custom
primary keys, soft delete and restore, audit composition, schema input and
response boundaries, indexes, constraints, CLI output, invalid declarations,
reserved names, direct generator preflight, advanced-field composition, and
compatibility.

See VERSION_COLUMNS.md for the complete Sprint 23.4 contract and concurrency
boundary.

Stop after delivering Sprint 23.4. Wait for the user's local test, commit, and
push result before starting any later feature or sprint.
