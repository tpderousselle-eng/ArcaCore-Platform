# Sprint 21.1: Partial Indexes

Partial indexes index only rows satisfying a predicate. Add a module-level
`partial_index()` declaration alongside field definitions. Field arguments keep
their declared order; one or more indexed columns are required.

| Purpose | DSL declaration |
| --- | --- |
| Find open records by tenant | `partial_index(tenant_id,where=status == 'Open')` |
| Find open records by tenant and date | `partial_index(tenant_id,created_at,where=status == 'Open')` |
| Unique email among active records | `partial_index(email,where=active == True,unique=True)` |
| Unique email per tenant among active records | `partial_index(tenant_id,email,where=active == True,unique=True)` |
| Unique email among records not soft-deleted | `partial_index(email,where=deleted_at is None,unique=True)` plus `soft_delete` |
| Index a numeric subset | `partial_index(amount,where=amount >= 10 and amount < 100)` |

Quote each complete DSL declaration when passing it to the CLI. Both existing
entry points, `python -m tools generate` and `python -m tools.generate`, accept
these declarations. Normal generation writes its configured backend output;
the smoke command below renders in memory and does not write backend files.

## Supported predicates

Predicates use the existing restricted comparison grammar from `check()`:

- Comparisons: `==`, `!=`, `<`, `<=`, `>`, `>=`.
- Null checks: `is None` and `is not None`.
- Boolean combinations: `and`, `or`, `not`, with parentheses.
- Operands: local column names, quoted strings, decimal numeric literals,
  booleans, and `None` for null checks.
- Every comparison must reference a column.

The compiler validates the syntax tree without executing the expression. It
quotes column names and escapes string literals. Original numeric literal text
is retained when emitting SQL. Numeric literals overflowing to infinity are
rejected. Strings containing control characters or backslashes are rejected.
Commas, colons, apostrophes, and parentheses inside quoted strings are supported.

`where` is required. `unique` is optional and accepts only `True` or `False`;
its default is `False`. Keyword order does not matter. Repeated keywords,
repeated indexed columns, unknown columns, calls, attributes, subscripts,
parameter bindings, arithmetic, and chained comparisons are rejected before any
generator or registry write runs. Indexed keys must be plain column names;
expression indexes are a separate unfinished feature.

Predicates and indexed keys can reference physical fields, computed columns,
`created_at`, `updated_at`, the implicit `id` when present, and `deleted_at` when
soft deletes are enabled. With a custom primary key there is no implicit `id`.
Relationship attributes and many-to-many collection names are not columns.
Database type compatibility remains subject to the selected database's rules.

## Generated behavior

The existing index metadata carries optional normalized SQL `where` and
`unique` attributes. Partial indexes render as SQLAlchemy `Index` declarations
with `postgresql_where` and `sqlite_where`, using the same validated predicate.
A conditional import supplies the SQL expression constructor.

The registry records `name`, `columns`, `where`, and `unique` for partial indexes.
Ordinary composite-index registry entries keep their existing shape. Names are
stable, include a predicate/uniqueness digest, and fit PostgreSQL's 63-byte
identifier limit. Multiple predicates can index the same columns. Duplicate
normalized declarations are rejected; logically equivalent expressions are not
otherwise simplified.

Uniqueness applies only to rows satisfying the predicate. Inserts and updates
entering that subset must satisfy the index. Rows outside it remain stored and
can repeat values. SQL null semantics still apply; null keys have the database's
normal unique-index behavior. A query must imply the predicate for the planner
to consider using the index, and the planner may still choose another plan.

With `where=deleted_at is None,unique=True`, soft deletion releases a key. If
another active row claims it, restoring the original row raises the existing
database integrity error and rolls back. This does not change API error mapping.
Existing full-column uniqueness and unique-together constraints continue to
apply independently; remove neither implicitly.

Supported databases are PostgreSQL and SQLite with partial-index support.
Generated partial indexes use SQLAlchemy 2.x conditional DDL and are omitted
when creating metadata on other dialects. No partial uniqueness is enforced on
those unsupported dialects. Existing databases need an appropriate migration to
create the new index; this feature does not generate or apply migrations.

SQLite database behavior and PostgreSQL DDL compilation are smoke-tested.
A live PostgreSQL server was not used for this delivery.

References:

- [SQLAlchemy PostgreSQL partial indexes](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#partial-indexes)
- [SQLAlchemy SQLite partial indexes](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#partial-indexes)
- [PostgreSQL partial-index behavior](https://www.postgresql.org/docs/current/indexes-partial.html)

## Install and verify

1. Extract `tools-sprint-21-1.zip` outside the project.
2. Copy its `tools` folder into `C:\Projects\ArcaCore` and replace matching files.
   The destination is the project root, so the paths become
   `C:\Projects\ArcaCore\tools\core\index_parser.py` and
   `C:\Projects\ArcaCore\tools\test_partial_indexes.py`.
3. From the project root with the existing virtual environment active, run:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes tools.test_partial_indexes -v
```

Expected result: 118 tests, OK. After the local suite passes:

```powershell
git add tools
git commit -m "Sprint 21.1 - Add Partial Index support"
```

Send the local test and commit result before the next feature starts.
