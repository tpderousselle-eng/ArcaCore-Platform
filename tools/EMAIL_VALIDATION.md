# Sprint 22.1: Email validation

## Installation

Use the existing Python virtual environment with Pydantic 2. Install the email
validation dependency from the project root before running the smoke suite:

```powershell
python -m pip install -r tools/requirements-email.txt
```

The same dependency is required in each generated application environment that
uses email fields. It is optional for applications with only ordinary fields.
This feature does not edit backend requirements or install packages automatically.
Missing dependencies produce Pydantic's email-validator installation error when
an email schema is imported. Generation itself does not require email-validator.

## DSL

| Declaration | Meaning |
| --- | --- |
| email:str:format=email | Required email string |
| email:str:format=email:length=254 | Email with a maximum normalized string length |
| backup:text:nullable:format=email | Optional nullable email backed by Text |
| email:str:format=email:default='person@example.com' | Email with a validated literal default |
| email:str:format=email:unique | Email validation plus the existing database unique option |
| email:str:format=email:regex=@example\.com$ | Email restricted to the normalized example.com domain |

format=email is an opt-in modifier, not a new field type. The underlying str or
text type is retained in the metadata and SQLAlchemy model. No renderer or model
template changes are required. The generated schema annotation is Pydantic
EmailStr, and JSON Schema advertises a string with format: email.

format= must appear before regex= when both are present. As before, regex= is the
last modifier: every character following it is part of the pattern. Other
modifiers may be reordered. Unknown formats, empty values, duplicates, and
non-string fields fail before generators or registry writes are called. Numeric,
array, JSON, Enum, Choice, and relationship collection fields cannot use this
modifier. Other named formats belong to later features.

## Validation and normalization

The generated schemas follow Pydantic EmailStr and email-validator behavior.
Validation produces a plain Python string, supports international addresses and
IDNA domains, normalizes Unicode and domain casing, and preserves local-part
case. Surrounding whitespace is removed. Display-name input such as
Tyler <Person@example.com> becomes Person@example.com. No extra ArcaCore policy
for local-part length, provider-specific aliases, or address case is added.

Pydantic disables deliverability checks for EmailStr. Validation makes no DNS or
SMTP requests, sends no email, and does not establish mailbox existence or
ownership. Address verification workflows are separate.

Existing length and regex constraints apply to the normalized address. Invalid
literal defaults fail when a Create schema is instantiated, following the
existing default-validation workflow. Database expression defaults remain on the
model and are not evaluated by schema generation.

Create requires a nonnullable email without a default. Update allows omission;
use model_dump(exclude_unset=True) to retain only supplied values. Explicit None
requires nullable. Response validates all declared fields, including values
loaded through from_attributes, and requires nullable fields to be present.

## Database and application boundary

Persist the normalized values returned by the schemas. A plain unique option
retains the database's existing case and collation behavior; email validation
alone does not provide case-insensitive uniqueness. The existing expression
index feature can apply that separate database policy:

```text
email:str:format=email
expression_index(lower(email),unique=True)
```

String primary keys and foreign keys can use format=email. Validate both sides
consistently before persistence; existing unnormalized keys are not migrated.
Response validation can normalize the returned value without changing the stored
row. Direct SQL and ORM writes bypass schema validation.

As in Sprint 19.12, these rules execute when generated Create, Update, or Response
schemas are used. This increment does not change router, CRUD, service, or model
output, and does not wire schemas into routes or add database email constraints.
Unformatted fields retain their prior behavior and registry shape. Formatted
fields add only format: email to their registry metadata.

## Local verification

Install the dependency, then run from C:\Projects\ArcaCore:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes tools.test_partial_indexes tools.test_expression_indexes tools.test_email -v
```

Expected: 144 tests, OK. Generated files and SQLite databases stay in memory.
Validated here with Python 3.12, Pydantic 2.13.4, email-validator 2.3.0, and
SQLAlchemy 2.0.52. The user's Windows environment must run the same smoke suite.

After the local tests pass:

```powershell
git add tools
git commit -m "Sprint 22.1 - Add Email Validation support"
```

Send the local result before continuing to the next feature.

## References

- [Pydantic EmailStr and email validation](https://docs.pydantic.dev/latest/api/networks/#pydantic.networks.EmailStr)
- [email-validator behavior and normalization](https://github.com/JoshData/python-email-validator)
