# Sprint 22.3: Slug validation

## DSL

| Declaration | Meaning |
| --- | --- |
| slug:str:format=slug | Required slug stored as String |
| slug:str:format=slug:length=80 | Slug with a maximum of 80 characters |
| slug:str:format=slug:unique | Slug with the existing database unique constraint |
| alias:text:nullable:format=slug | Optional nullable slug stored as Text |
| slug:str:format=slug:default='first-article' | Validated literal default |
| slug:str:format=slug:regex=^product- | Slug additionally restricted to the product- prefix |

format=slug uses the existing Field.format metadata. Registry entries retain
format: slug. It is a modifier on str or text, not a new database type.

Generated Create, Update, and Response schemas include one reusable Annotated
string validator. It requires Pydantic 2 and Python's standard library only.
There is no new dependency, network request, or runtime import from tools/.

## Accepted values

A slug contains one or more lowercase ASCII letters or digits. Groups may be
separated by single ASCII hyphens. Every value must match the entire expression
[a-z0-9]+(?:-[a-z0-9]+)*. Numeric-only values and values beginning with a digit
are accepted. The result is a string with the same value as the supplied input.

| Input | Result |
| --- | --- |
| my-product-2 | Accepted unchanged |
| article | Accepted unchanged |
| 123 | Accepted when supplied as a string |
| My-Product | Rejected: uppercase letters |
| my_product | Rejected: underscore |
| my--product | Rejected: repeated hyphen |
| -product or product- | Rejected: leading or trailing hyphen |
| my product | Rejected: whitespace |
| café | Rejected: non-ASCII character |

Empty strings, Unicode letters/digits, Unicode dash lookalikes, path separators,
punctuation other than hyphens, control characters, and trailing newlines are
rejected. Integer, boolean, byte-string, and other non-string inputs are rejected.

Validation does not lowercase, trim, transliterate, replace separators, or derive
a slug from a title. There is no implicit maximum length; use length= on a str
field to set one. Existing min_length and regex rules impose additional limits
without weakening the slug rules. min_length=0 does not permit an empty slug.

format= must precede regex= when both are present, because regex remains the
final modifier and consumes its remaining characters literally. Other modifiers
may be reordered. A field can have only one format. Unsupported types and
unknown, duplicate, empty, or incompatible formats fail before generation.

## Schema behavior

Create requires a nonnullable slug without a default. Nullable slugs accept None.
Update permits omission; model_dump(exclude_unset=True) returns only supplied
values. Explicit None is rejected for nonnullable slugs. Response requires all
its scalar fields, including nullable fields, and validates from_attributes.

Literal defaults are validated when a Create schema is instantiated. Invalid
literal defaults raise validation errors. Database-expression defaults stay on
the model; schemas neither execute them nor supply them as user input.

JSON Schema describes a string with format: slug and preserves length/regex
metadata. Nullable fields expose string/slug and null alternatives. The custom
format is descriptive; clients must not assume every JSON Schema consumer
implements this slug policy. Generated Python schemas enforce it at runtime.

Email and phone formats can coexist with slug fields. Computed fields remain
read-only. Existing scalar primary and foreign keys may use format=slug; use the
same policy on both sides. No identifiers or stored rows are renamed or migrated.

## Persistence and composition

Adding format=slug preserves SQLAlchemy column types and the generated model,
CRUD, service, and router output. Slug formatting does not imply uniqueness or
add a database format constraint. Use unique, unique_together, or an existing
unique index where uniqueness is required, and persist validated schema values.
Existing partial/expression indexes, computed fields, constraints, soft deletion,
and relationship options compose with slug formatting.

Direct SQL and ORM writes bypass schema validation. Response validation can
reject a stored value that does not follow the policy. This increment does not
wire schemas into routes, reserve application-specific names, generate slugs
from titles, or resolve slug collisions automatically.

## Local verification

Extract the ZIP into C:\Projects\ArcaCore so its top-level tools folder merges
with the project's tools folder. Do not extract into tools itself.

No new installation is needed for slug validation. The full suite still requires
the existing email and phone dependencies. A fresh environment needs both
requirements files in addition to the project's existing test dependencies.

Run from the project root:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes tools.test_partial_indexes tools.test_expression_indexes tools.test_email tools.test_phone tools.test_slug -v
```

Expected: 168 tests, OK. All generated source is captured in memory; database
checks use in-memory SQLite. The suite does not write backend files. This
increment was tested with Python 3.12, Pydantic 2.13.4, and SQLAlchemy 2.0.52.
No live PostgreSQL test was added. Run the command above in your Windows
environment before committing.

```powershell
git add tools
git commit -m "Sprint 22.3 - Add Slug Validation support"
```

Send the local test and commit result before proceeding to another feature.
