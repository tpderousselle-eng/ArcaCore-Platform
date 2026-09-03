# Sprint 21.2: Expression Indexes

Add module-level `expression_index()` declarations to index the result of a
function or calculation while retaining the original field values.

| Purpose | DSL declaration |
| --- | --- |
| Find an email through its lowercase form | `expression_index(lower(email))` |
| Enforce uniqueness of lowercase email | `expression_index(lower(email),unique=True)` |
| Scope lowercase-email uniqueness to a tenant | `expression_index(tenant_id,lower(email),unique=True)` |
| Index a calculated amount | `expression_index(price * quantity)` |
| Index text length | `expression_index(length(title))` |
| Index a numeric magnitude | `expression_index(abs(amount))` |
| Combine calculated keys | `expression_index(upper(title),length(title))` |
| Keep uniqueness among active records | `expression_index(lower(email),where=deleted_at is None,unique=True)` plus `soft_delete` |

Pass each complete declaration as one quoted CLI argument. Both existing entry
points, `python -m tools generate` and `python -m tools.generate`, support these
options. Regular generation writes the configured backend output. The smoke
suite below captures all generated files in memory.

## Supported expression language

One or more ordered index keys are required. At least one must be a function or
arithmetic expression; other keys can be plain columns. Every key must reference
a physical column of the same table. The same column may appear in distinct
keys, such as `lower(email)` and `length(email)`, but repeated normalized keys
are rejected.

| Operation | Supported arguments |
| --- | --- |
| `lower(value)`, `upper(value)` | One `str`, `text`, or `choice` value |
| `length(value)` | One `str`, `text`, or `choice` value; returns a numeric result |
| `abs(value)` | One `int`, `float`, or `decimal` value |
| `+`, `-`, `*` | Numeric operands; unary plus/minus and grouping are supported |
| Nested expressions | Results of supported operations with compatible types |

Plain keys can also use UUID, boolean, date, datetime, and enum columns. Text
functions do not implicitly cast UUIDs, numbers, booleans, or native enum values.
JSON, arrays, relationship attributes, and many-to-many collections are not
supported expression-index keys.

Numeric and string constants can participate in an expression referencing a
column. A constant-only key is rejected. Decimal literal text is retained in
SQL rather than rounded through a Python float. Non-decimal literal syntax and
numbers overflowing to infinity are rejected. String quotes are escaped, and
strings containing control characters or backslashes are rejected.

Computed columns can be referenced as physical columns. Implicit `id`, timestamps,
custom primary keys, and soft-delete `deleted_at` follow the same availability
rules as ordinary indexes. Field declarations may come after index declarations.

Expressions are parsed and type-checked without executing input code. Arbitrary
functions, attributes, subscripts, lambdas, comprehensions, assignments, parameter
bindings, casts, division, and custom SQL are rejected. Declarations are limited
to 4000 characters and 150 syntax-tree nodes.

## Options and composition

`unique` accepts only `True` or `False`, defaulting to `False`.

An optional `where` uses the existing Partial Index predicate grammar: column
comparisons joined by `and`, `or`, or `not`, and `is None` / `is not None` for null
checks. It does not accept expression functions or arithmetic. See
`tools/PARTIAL_INDEXES.md` for predicate details. Keyword order does not matter;
repeated or unknown options are rejected before generation and registry writes.

Unique expression indexes are enforced by the database on insert and update.
Original field values and schemas are unchanged. Null expression results follow
the database's normal unique-index semantics. Existing column uniqueness and
unique-together constraints remain independently enforced.

With a filter on `deleted_at is None`, soft deletion releases the indexed value.
Restoring a row can raise an integrity error if another active row now has the
same expression result; the existing service rolls back that failed operation.
This feature does not change API error mapping.

## Metadata and supported databases

Expression-index metadata records:

- `name`: a stable generated identifier, limited to 63 bytes.
- `columns`: referenced key columns, deduplicated in first-use order.
- `expressions`: normalized SQL keys in their declared order.
- `where`: normalized SQL predicate, or `null` if absent.
- `unique`: a boolean.

Predicates and uniqueness participate in the name digest. Repeated normalized
declarations are rejected. Algebraically equivalent expressions are not otherwise
simplified. Ordinary and partial indexes keep their existing metadata format and
can coexist with expression indexes.

Generated SQLAlchemy indexes attach to the model table and are enabled for
PostgreSQL and SQLite. SQLAlchemy 2.x and SQLite 3.9.0 or newer are required for
this feature. Conditional DDL omits these indexes on other dialects, where their
uniqueness is not enforced. Existing databases require an appropriate migration;
this feature does not create or apply migrations.

Queries must use the matching expression to make the index eligible, and the
planner may choose a different plan. For example, indexing `lower(email)` does
not change existing queries into lowercase comparisons. SQLite requires the
expression to match structurally and does not equate reordered arithmetic.
See the [SQLite expression-index documentation](https://www.sqlite.org/expridx.html).

Case conversion and collation follow the database's rules. The tests verify
ASCII case-insensitive behavior, not universal Unicode case folding. Numeric
range, rounding, overflow, and decimal storage likewise follow the database.
SQLite numeric tests do not establish PostgreSQL decimal equivalence.

Validation includes SQLite database behavior, SQL query plans, and PostgreSQL
DDL compilation. A live PostgreSQL server was not used for this delivery.

References:

- [SQLAlchemy functional indexes](https://docs.sqlalchemy.org/en/20/core/constraints.html#functional-indexes)
- [PostgreSQL indexes on expressions](https://www.postgresql.org/docs/current/indexes-expressional.html)

## Install, smoke-test, and commit

1. Extract `tools-sprint-21-2.zip` outside the project.
2. Copy its `tools` folder into `C:\Projects\ArcaCore`, replacing matching files.
   Paste into the project root so the new parser is at
   `C:\Projects\ArcaCore\tools\core\expression_index_parser.py`.
3. Run this from the project root with your existing virtual environment active:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes tools.test_partial_indexes tools.test_expression_indexes -v
```

Expected: 132 tests, OK. After the local suite passes:

```powershell
git add tools
git commit -m "Sprint 21.2 - Add Expression Index support"
```

Send the local test and commit result. No later sprint starts with this delivery.
