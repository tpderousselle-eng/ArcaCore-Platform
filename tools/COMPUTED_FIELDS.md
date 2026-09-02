# Sprint 19.13: Computed fields

Computed fields are stored database columns whose values are calculated from
other numeric columns in the same row. The generator uses SQLAlchemy Computed
with persisted=True. Values become available after a database insert/update and
fetch or refresh; this is not a Python property that calculates before saving.

## DSL

A module can declare quantity:int, price:decimal(12,2), and
`total:decimal(14,2):computed=quantity * price`.

| Element | Supported behavior |
| --- | --- |
| Result types | int, float, decimal(precision,scale) |
| Expressions | Column names, decimal numeric literals, +, -, *, parentheses |
| Unary operators | +value and -value |
| References | Explicit numeric fields in the same module, in any declaration order |
| Integer result | Requires integer source fields and integer literals |
| Nullable inputs | The computed field must also declare nullable |
| Indexes | index modifier and composite indexes can include computed fields |
| Constraints | unique, unique_together, and check can include computed fields |

Other modifiers can appear before or after computed=. Keep the complete field
declaration inside one quoted command-line argument when it contains spaces.

## Input and response schemas

Computed fields are excluded from Create and Update fields. Supplying a computed
field to either schema raises a validation error, including when its value is
null. Response includes the field with its declared type and marks it readOnly
in JSON Schema. Response validates the value fetched from the database.

Use model_dump(exclude_unset=True) for writable schema data as described in
VALIDATORS.md. A database refresh retrieves recalculated values when needed.
Existing CRUD and router capabilities are not expanded by this feature.

## Validation and limits

The parser builds SQL from a restricted expression tree and never evaluates
input as Python. Unknown fields, self references, references to other computed
fields, nonnumeric inputs, function calls, division, comparisons, and arbitrary
SQL are rejected before generation. Expressions must reference at least one
explicit field and are limited to 2000 characters and 100 syntax-tree nodes.

Computed fields cannot have primary-key, default, or foreign-key modifiers.
The generated names id, created_at, updated_at, and deleted_at are reserved for
this feature. Implicit columns cannot be used as expression inputs.

Decimal literal spelling is retained in generated SQL. Database numeric
precision, rounding, and overflow rules still apply. In particular, SQLite
numeric behavior is not a substitute for testing PostgreSQL decimal arithmetic.

This increment supports stored numeric expressions. It does not implement
string expressions, SQL functions, virtual columns, or computed-to-computed
chains. Existing tables still require a migration when adding a computed column.
No migration or backend file is changed by the smoke suite.

## Verification

Run from the project root:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed -v
```

The suite uses in-memory generated code and SQLite databases, plus PostgreSQL
DDL compilation. It does not connect to a live PostgreSQL instance.

Reference: [SQLAlchemy computed columns](https://docs.sqlalchemy.org/en/20/core/defaults.html#computed-columns-generated-always-as).
