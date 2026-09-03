# Sprint 23.1: Hybrid properties

## Purpose

A hybrid property is a calculated, read-only model attribute that works in two
contexts:

- Accessing an ORM instance evaluates ordinary Python values.
- Accessing the model class produces a SQLAlchemy expression for SELECT, WHERE,
  ORDER BY, and other query composition.

Unlike computed fields, hybrids do not create stored or virtual database
columns. They are recalculated from their source attributes whenever accessed.
The generated implementation uses SQLAlchemy's hybrid_property extension.

## DSL

| Declaration | Result |
| --- | --- |
| total:decimal(12,2):hybrid=quantity * price | Decimal multiplication |
| doubled:int:hybrid=quantity * 2 | Integer arithmetic |
| adjusted:float:hybrid=score * 1.5 + 2 | Floating-point arithmetic |
| display_name:str:hybrid=first_name + ': ' + last_name | Text concatenation |
| doubled:int:nullable:hybrid=amount * 2 | Nullable result when amount is nullable |
| total:int:min=0:hybrid=quantity * price | Read-time schema constraint |
| total:int:hybrid=quantity * price:validator=rules.check | Response custom validator |

hybrid= accepts a restricted expression, not arbitrary Python. It supports
stored local scalar columns, decimal numeric literals, quoted string literals,
parentheses, unary + and -, and binary +, -, and *. Text expressions use + only.
The expression must reference at least one stored column.

Forward references are supported: a hybrid may appear before its source fields
in the module declaration. Modifier order is flexible, but regex= remains the
final literal modifier. Colons inside quoted hybrid string literals are
preserved by the field parser.

## Supported result and source types

Hybrid outputs may be int, float, decimal(precision,scale), str, or text.
Numeric expressions use int, float, and decimal stored sources. Text expressions
use str, text, choice, and enum stored sources.

Integer outputs require an integer result. Float outputs accept integer and
float arithmetic. Decimal outputs accept decimal and integer arithmetic; decimal
literals are rendered as exact Decimal values. Decimal and float sources cannot
be mixed because their Python instance behavior is incompatible.

String/text outputs require text concatenation. Automatic casts, string
formatting, function calls, comparisons, division, floor division, modulo,
powers, subscripts, attributes, comprehensions, conditionals, lambdas, and
imports are not supported in this increment.

## Generated model behavior

For each declaration, the generated SQLAlchemy model contains one read-only
hybrid_property and a class-level SQL expression. There is no Column for the
hybrid name and no setter.

For an instance, source values are read at access time. Updating a source field
immediately changes the hybrid result; no synchronization step or database
write is needed. A nullable source requires the hybrid field to be nullable.
The Python property returns None when any referenced nullable source is None,
while the class expression keeps normal SQL NULL propagation.

At class level, the same expression can be selected, filtered, and ordered.
Text + is translated by SQLAlchemy for the active database dialect. Hybrid
properties can be used with aliases and ordinary SQLAlchemy query composition
supported by the generated expression.

The feature does not create migrations, database-generated columns, triggers,
setters, bulk-update handlers, relationship-dependent hybrids, correlated
subqueries, custom comparators, or hybrid methods.

## Schema behavior

Hybrid fields are omitted from generated Create and Update schemas. Supplying
one is rejected by the same read-only input protection used for computed fields.
They appear as required, readOnly fields in Response schemas and are loaded
through from_attributes.

Existing response validation still applies. A hybrid can use min, max,
min_length, length, regex, format, and custom validator metadata when compatible
with its declared type. Those checks run when the Response schema reads the
property. They do not constrain the SQL expression or prevent direct ORM query
results from containing a value the schema would reject.

Custom rules on hybrids run on Response only. They can reject or transform the
serialized response value, but they do not alter the model property, its source
columns, or stored data.

## Registry and composition

Registry field metadata adds hybrid, hybrid_python, hybrid_class, and ordered
hybrid_references only for hybrid fields. Models without hybrids retain their
previous registry shape and byte-for-byte generated source.

Hybrid properties compose with custom and implicit primary keys, foreign-key
source columns, one-to-many relationships, cascade/passive deletes, soft
deletes, custom validators, and stored computed fields in the same module.
A hybrid cannot reference another hybrid or a computed field, and a computed
field cannot reference a hybrid.

A hybrid is not a database column. Therefore it cannot be:

- A primary or foreign key.
- Unique or directly indexed.
- Included in index(), partial_index(), expression_index(), unique_together(),
  or check().
- Given a model default.
- Used as a relationship declaration or delete-control field.

Use an equivalent expression_index() when query acceleration is needed. Direct
foreign keys in other modules must target actual stored columns.

## Safety and validation

Expressions are parsed with Python's AST and rendered from an allowlist. They
are never evaluated during generation. Unknown references, self-references,
unsupported nodes/types, type mismatches, nonfinite literals, excessive length
or complexity, reserved generated names, incompatible modifiers, and nullable
source mismatches fail before any generator or registry write.

The limits are 2,000 expression characters and 100 AST nodes. Quoted text cannot
contain control characters. These restrictions keep generated source
deterministic and prevent the DSL from becoming an arbitrary-code execution
path.

## Local verification

Extract tools-sprint-23-1.zip into C:\Projects\ArcaCore so the top-level tools
folder merges with the project's tools folder. Do not extract into tools itself.
Every included source file is a complete replacement.

No new package is required. Run the relevant suite from the project root:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes tools.test_partial_indexes tools.test_expression_indexes tools.test_email tools.test_phone tools.test_slug tools.test_url tools.test_custom_validators tools.test_hybrid_properties -v
```

Expected: 212 tests, OK.

To verify normal discovery, run:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```

Expected: 213 tests, OK. The 14 new tests cover instance and SQL expression
behavior, numeric and text calculations, exact decimals, nullable propagation,
read-only schemas, constraints/formats/custom rules, registry metadata, stored
computed fields, relationships, keys, soft deletes, invalid expressions and
modifiers, non-column constraint rejection, direct-generator preflight,
backward compatibility, security limits, SQLite execution, and PostgreSQL SQL
compilation.

Tests capture generated source in memory and use in-memory SQLite. They do not
write backend files. Verified here with Python 3.12, Pydantic 2.13.4, and
SQLAlchemy 2.0.52. No live PostgreSQL execution was added.

After both local runs pass:

```powershell
git add tools
git commit -m "Sprint 23.1 - Add Hybrid Property support"
git push
```

Send the local test, commit, and push result before continuing to Sprint 23.2.

## Reference

SQLAlchemy documents hybrid attributes as descriptors with distinct
instance-level Python and class-level SQL expression behavior:
[SQLAlchemy Hybrid Attributes](https://docs.sqlalchemy.org/en/20/orm/extensions/hybrid.html).

The DSL grammar, type rules, null handling, read-only schema behavior, and
security limits above are ArcaCore policies.
