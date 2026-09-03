# Sprint 22.2: Phone validation

## Installation

Use the existing Python environment with Pydantic 2. From the project root:

```powershell
python -m pip install -r tools/requirements-phone.txt
```

The same dependency is required in every generated application using phone
fields. Apps without phone fields do not import phonenumbers. Missing dependencies
produce an installation message when a generated phone schema is imported.
Generation itself does not require phonenumbers. No backend requirement file is
edited and no package is installed automatically by the generator.

The complete smoke suite also uses the email dependency installed in Sprint 22.1.
For a fresh environment, additionally install tools/requirements-email.txt.

## DSL

| Declaration | Meaning |
| --- | --- |
| phone:str:format=phone | Required international phone string |
| phone:str:format=phone:length=16 | Phone with room for the E.164 plus sign and up to 15 digits |
| backup:text:nullable:format=phone | Optional nullable phone backed by Text |
| phone:str:format=phone:default='+1 650-253-0000' | Validated literal default |
| phone:str:format=phone:unique | Phone validation plus existing database uniqueness |
| phone:str:format=phone:regex=^\+44 | Restrict normalized values to the +44 calling code |

format=phone is a modifier on str or text, not a new database type. Metadata keeps
the original Python/SQLAlchemy types and adds format: phone to the existing
registry entry. The generated schema includes one reusable Annotated string
validator and imports phonenumbers only when a phone field is present. Generated
code does not import tools/ or require ArcaCore at application runtime.

format= must precede regex= when both are present. As before, every character
after regex= belongs to the pattern. Other modifiers may be reordered. Only one
format is allowed per field. Unknown formats, incompatible types, and duplicate
format modifiers fail before any generator or registry write runs. Arrays, JSON,
Enum, Choice, and relationship collections cannot use format=phone.

## Accepted inputs and output

Inputs must be strings in international form beginning with + and a country
calling code. ASCII digits, spaces, parentheses, hyphens, and periods are allowed.
Surrounding ASCII spaces are trimmed. The raw input limit is 128 characters.
The phonenumbers parser handles supported presentation punctuation, then validates
the number against its bundled numbering-plan metadata.

| Input | Normalized output |
| --- | --- |
| +1 (650) 253-0000 | +16502530000 |
| +44 20 8366 1177 | +442083661177 |
| +39 02 3661 8300 | +390236618300 |
| +800 1234 5678 | +80012345678 |

The output is a plain Python string in E.164 form: + followed by at most 15 digits.
Significant leading zeros within a national number are preserved by phonenumbers.
Valid non-geographic international calling codes are supported by the library.

National-only numbers, international dialing prefixes such as 00, short codes,
letters/vanity numbers, tel: URIs, extensions, control characters, non-ASCII
digits, numeric Python inputs, and raw PhoneNumber objects are rejected. A default
country is not guessed. Extensions are rejected rather than discarded.

This is offline validation against numbering-plan metadata. It makes no network
requests, sends no SMS, and does not establish assignment, reachability, ownership,
or consent. Newly allocated ranges can require updated phonenumbers metadata.

## Schema behavior and composition

Create requires nonnullable fields without defaults. Update allows omission of
all fields; use model_dump(exclude_unset=True) to retain only supplied values.
Explicit None requires nullable. Response validates all declared scalar fields,
including objects passed through from_attributes; nullable fields must still be
present in a response.

Literal defaults are normalized and validated when Create is instantiated.
Database expression defaults remain on the model and are not executed by schemas.
Length and regex constraints run on the normalized value. Existing numeric,
email, computed-field, and relationship behavior is retained.

JSON Schema describes a string with format: phone. This is descriptive metadata;
clients must not assume every JSON Schema consumer enforces phone validation.
Nullable fields expose string/phone and null alternatives. Existing length and
regex metadata is retained.

Database column types, model output, CRUD, services, routers, indexes, and
constraints are unchanged by adding the format modifier. Persist values returned
by the generated schemas to obtain normalization and consistent unique keys.
For example, differently formatted inputs normalize to the same value before an
existing unique constraint is applied. Direct SQL or ORM writes bypass schemas.

String primary and foreign keys may use phone formatting. Validate both sides
consistently before persistence. Existing unnormalized keys and rows are not
migrated. Response validation may normalize its returned value without changing
the stored database row.

As with Sprint 19.12 and Email Validation, this feature executes when generated
schemas are used. It does not add routes, wire schemas into existing routes,
send messages, or create database phone-format constraints.

## Local verification

Run from C:\Projects\ArcaCore after installing the dependency:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes tools.test_partial_indexes tools.test_expression_indexes tools.test_email tools.test_phone -v
```

Expected: 156 tests, OK. The suite renders generated code in memory and uses
in-memory SQLite databases. It does not create backend files.

Validated here with Python 3.12, Pydantic 2.13.4, phonenumbers 9.0.38,
email-validator 2.3.0, and SQLAlchemy 2.0.52. Windows verification is required in
the user's environment. No live PostgreSQL execution was added in this increment.

After the local suite passes:

```powershell
git add tools
git commit -m "Sprint 22.2 - Add Phone Validation support"
```

Send the local test and commit result before proceeding to another feature.

## References

- [phonenumbers parsing, validation, and formatting](https://github.com/daviddrysdale/python-phonenumbers)
- [Pydantic phone-number documentation](https://docs.pydantic.dev/latest/api/pydantic_extra_types_phone_numbers/)

ArcaCore uses phonenumbers directly in a generated Pydantic BeforeValidator.
It does not require pydantic-extra-types. The international-only input rules,
rejection of extensions, and raw-input limit are the policy for this increment.
