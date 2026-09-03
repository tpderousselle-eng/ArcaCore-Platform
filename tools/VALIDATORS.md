# Field validators: Sprint 19.12 and Sprint 22.1

Generated schemas require Pydantic 2. Validators apply when a generated Create,
Update, or Response schema is instantiated or validated. They do not add API
routes or database constraints. Existing database constraints remain separate.

## DSL modifiers

| Modifier | Fields | Meaning |
| --- | --- | --- |
| min=18 | int, float, decimal | Inclusive minimum |
| max=120 | int, float, decimal | Inclusive maximum |
| min_length=2 | str, text | Minimum string length |
| length=255 | str | Maximum string length and existing SQL column length |
| regex=^[A-Z][a-z]+$ | str, text | Python regular expression search |
| format=email | str, text | Pydantic EmailStr validation and normalization |

Regex must be the final modifier. Everything after regex= belongs to the
pattern, including colons and backslashes. Use anchors for whole-string
validation. Invalid patterns, reversed bounds, incompatible field types,
nonfinite numeric bounds, and duplicate bound/length modifiers fail before
any generated files are written. Unknown, empty, or repeated format= modifiers
also fail before generation.

## Schema behavior

Scalar fields receive Python types. Choice and Enum fields use string Literals.
Arrays validate their element types. JSON accepts JSON-compatible input through
the caller's JSON parser and uses Any internally. Relationship collections are
not included; scalar foreign-key columns remain available.

Create requires fields without a default, except nullable fields and generated
integer/UUID primary keys. Literal defaults are validated. Database-expression
defaults remain on the model and are omitted from supplied schema input.

Update allows omission of every field. Explicit null is allowed only for nullable
fields. Use model_dump(exclude_unset=True) to obtain supplied update values and
to preserve omission of generated keys or database defaults on Create. An omitted
field may appear as None in a plain model_dump; it is not an instruction to write
NULL to the database.

Response requires its declared scalar fields, supports from_attributes, and
preserves custom primary keys instead of adding an unconditional integer id.

Email fields additionally require the optional dependency installed with
python -m pip install -r tools/requirements-email.txt. EmailStr normalizes
addresses without checking DNS, deliverability, or ownership. Length and regex
rules apply after normalization. See EMAIL_VALIDATION.md for the exact behavior,
installation, compatibility boundaries, and full smoke command.

Named URL, phone, and slug formats, custom callable validators, and validation
inside generated API routes are not included in this increment.

## Smoke test

Run from the project root after installing the email dependency:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes tools.test_partial_indexes tools.test_expression_indexes tools.test_email -v
```

Expected: 144 tests, OK. The suite captures generated code in memory. It does not
write backend files.
