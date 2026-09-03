# Audit fields

Sprint 23.3 adds opt-in creator and updater attribution to generated models. It
extends the generator's existing `created_at` and `updated_at` timestamps with
trusted actor identifiers; it does not create an immutable audit-event log.

## DSL

Use the module-level option with its conventional target and type:

```text
audit_fields
```

This is equivalent to:

```text
audit_fields(users.id,int)
```

The target may be customized and the actor key may be `int`, `str`, or `uuid`:

```text
audit_fields(accounts.identifier,uuid)
audit_fields(operators.username,str)
```

The option can appear anywhere in the module declaration and can be specified
only once. Its target must use `table.column` form.

## Generated model contract

An audit-enabled model contains:

| Column | Contract |
| --- | --- |
| `created_by` | Non-null actor key with a foreign key to the configured target and a single-column index |
| `updated_by` | Nullable actor key with the same foreign key and a single-column index |
| `created_at` | Existing database-generated creation timestamp |
| `updated_at` | Existing database-generated and database-updated modification timestamp |

The actor columns use the configured key type. The actor target table remains
an application-owned model and must exist in the generated metadata before the
database schema is created.

The four names are reserved when `audit_fields` is enabled. They cannot also be
declared as ordinary fields or relationship names.

## Schema and service boundary

Create and Update schemas reject `created_by`, `updated_by`, `created_at`, and
`updated_at`, including explicit extra input. Response schemas expose all four
as required read-only audit metadata; `updated_by` remains nullable until a
trusted update occurs.

ArcaCore does not infer the current actor. Application code must take the actor
from authenticated server-side context and assign it when creating or updating
a model. Never copy an actor identifier from an untrusted request payload.

For a model combining `audit_fields` with `soft_delete`, generated delete and
restore methods require `actor_id`. Successful state changes assign that value
to `updated_by` in the same transaction. Repeated no-op delete or restore calls
retain the actor who performed the actual state change. Failed commits roll
back both the deletion state and actor attribution.

## Indexes and constraints

`created_by` and `updated_by` may be used in composite indexes, partial-index
columns and predicates, unique-together constraints, and checks. They may also
appear in an expression index predicate. Generated actor columns are not
available as expression-index keys in Sprint 23.3.

Registry metadata records the configured target, Python key type, and
SQLAlchemy key type in an `audit_fields` object. Generated actor columns do not
duplicate ordinary entries in the `fields` list.

## Compatibility and limits

Modules without `audit_fields` preserve their existing model, schema, CRUD,
service, and registry shapes. This feature composes with relationships,
computed fields, hybrid properties, encrypted fields, constraints, indexes,
and soft deletes.

Sprint 23.3 provides current-row attribution only. Historical values, request
metadata, diffs, append-only events, and automatic authenticated-user context
belong to a separate audit-log feature.

## Local verification

Run the dedicated smoke suite:

```powershell
python -m unittest tools.test_audit_fields -v
```

Run every tools test:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```
