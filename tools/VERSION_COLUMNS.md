# Version columns

Sprint 23.4 adds opt-in optimistic concurrency control to generated SQLAlchemy
models. It detects stale ORM writes to the same row; it does not store revision
history or expose a client-controlled version value.

## DSL

Enable the feature with the module-level option:

```text
version_column
```

The option takes no arguments or modifiers. It can appear anywhere in the
module declaration and can be specified only once.

## Generated model contract

An enabled model contains:

```python
version_id = Column(Integer, nullable=False, default=1)
__mapper_args__ = {"version_id_col": version_id}
```

New ORM-managed rows start at version 1. Each successful ORM flush that updates
the row includes its current version in the `UPDATE` predicate and advances the
stored value. If another transaction has already changed the row, SQLAlchemy
raises `sqlalchemy.orm.exc.StaleDataError` instead of silently overwriting that
change. The failed session must be rolled back before it is reused.

The `version_id` name is reserved when the option is enabled. It cannot also be
declared as an ordinary field or relationship name.

## Schema boundary

Create and Update schemas reject `version_id`, including explicit extra input.
Response schemas expose it as a required read-only integer with
`x-arca-version-column` JSON Schema metadata.

Clients may retain a returned version for their own conflict workflow, but the
generated input schemas do not accept it as an assignment. The database and
SQLAlchemy mapper own version advancement.

## Indexes and constraints

`version_id` may be used in composite indexes, partial-index columns and
predicates, unique-together constraints, and checks. It may also appear in an
expression-index predicate. Generated version columns are not available as
expression-index keys in Sprint 23.4.

Registry metadata records the generated name, Python and SQLAlchemy types, and
initial value in a `version_column` object. The generated column does not
duplicate an ordinary entry in the `fields` list.

## Composition and limits

Version columns compose with relationships, computed fields, hybrid
properties, encrypted fields, audit fields, constraints, indexes, and soft
deletes. Successful soft-delete and restore state changes advance the version;
repeated no-op calls do not. Audit attribution and the version advance occur in
the same transaction when both features are enabled.

Modules without `version_column` preserve their existing model, schema, CRUD,
service, and registry shapes.

SQLAlchemy performs this version check only while flushing individual ORM
instances. Bulk operations such as `Query.update()`, `Query.delete()`, and Core
bulk DML do not perform row-by-row optimistic checks. Sprint 23.4 does not add
historical revisions, diffs, automatic retries, HTTP precondition handling, or
conflict merging.

## Local verification

Run the dedicated smoke suite:

```powershell
python -m unittest tools.test_version_columns -v
```

Run every tools test:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```
