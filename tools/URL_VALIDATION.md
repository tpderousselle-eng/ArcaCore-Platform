# Sprint 22.4: URL validation

## DSL

| Declaration | Meaning |
| --- | --- |
| website:str:format=url | Required HTTP or HTTPS URL stored as String |
| website:str:format=url:length=200 | URL with a maximum normalized length of 200 |
| website:str:format=url:unique | URL plus the existing database unique constraint |
| backup:text:nullable:format=url | Optional nullable URL stored as Text |
| website:str:format=url:default='https://example.com' | Validated literal URL default |
| website:str:format=url:regex=^https:// | Additionally require HTTPS |

format=url uses the existing Field.format metadata. Registry entries retain
format: url. It is a modifier on str or text, not a new database type.

Generated Create, Update, and Response schemas contain one reusable Annotated
string validator. It validates through Pydantic AnyHttpUrl and returns a plain
Python string. Values from model_dump() can therefore be passed directly to
SQLAlchemy String or Text columns. No new dependency is required beyond the
existing Pydantic 2 installation, and generated schemas do not import tools/.

## Input policy

Inputs must be strings beginning with http:// or https://, with a nonempty host.
The scheme is case-insensitive. Domain names, international domain names, IP
addresses, IPv6 addresses in brackets, localhost, and explicit valid ports are
supported. A top-level domain is not required.

Relative URLs, missing //, other schemes, embedded credentials/user information,
raw whitespace, control characters, backslashes, and malformed percent escapes
are rejected. Numeric inputs, byte strings, and prebuilt Pydantic URL objects
are also rejected; supply URL strings. Percent-encoded characters are retained
according to Pydantic's URL parsing rules.

No DNS lookup, HTTP request, redirect following, or availability check occurs.
Local/private addresses are permitted. This is syntax validation and does not
establish that a destination is public, trustworthy, reachable, or safe for a
server to fetch. Applications performing network requests need their own
outbound destination policy.

## Normalization and constraints

| Input | Stored schema value |
| --- | --- |
| HTTPS://EXAMPLE.COM | https://example.com/ |
| http://EXAMPLE.COM:80 | http://example.com/ |
| https://example.com:443/a/../b | https://example.com/b |
| https://bücher.de/über | https://xn--bcher-kva.de/%C3%BCber |
| http://localhost:8000/path | http://localhost:8000/path |

Normalization follows Pydantic AnyHttpUrl, including scheme/host casing, default
ports, empty paths, international domains, and path encoding. Path/query/fragment
case is not globally lowercased. Query parameters are not sorted. This is not a
complete test of whether different URLs identify the same resource.

There is no implicit maximum length. Use length= on a str field to set one.
Length and regex constraints run on the normalized string, including any added
trailing slash or expanded international characters. They also apply in Update
and Response schemas.

JSON Schema describes a string with format: uri and preserves length/regex
metadata. Nullable fields expose string/uri and null alternatives. The uri format
is broader than ArcaCore's HTTP(S) input policy; consumers must not assume the
JSON Schema format alone implements every rule above.

## Quoted defaults and parser behavior

URL literals contain colons. The field parser now preserves colons inside a
single-quoted or double-quoted default literal, including port numbers and IPv6
addresses. For example:

| Declaration | Default schema value |
| --- | --- |
| website:str:default='HTTPS://EXAMPLE.COM:443':format=url | https://example.com/ |
| website:str:format=url:default="http://localhost:8000/path" | http://localhost:8000/path |

Backslash-escaped quotes inside a quoted default are preserved for Python literal
parsing. An unterminated quote or unexpected text after its closing quote fails
before generation. Quote the entire URL literal, not just its host or path.

A regex= modifier remains last and consumes all remaining characters literally,
including colons, quotes, and backslashes. A :regex= sequence inside a quoted
default is part of that default. Actual format= and other modifiers must appear
before the regex modifier. Other modifier order remains flexible.

A field can have only one format. Unknown formats, duplicate or empty format
modifiers, unsupported types, and incompatible validation options fail before
any generator or registry write. Collection relationships cannot carry formats.

## Schema and persistence behavior

Create requires nonnullable URL fields without defaults. Nullable fields accept
None. Update permits omission; use model_dump(exclude_unset=True) to retain only
supplied values. Explicit None is rejected for nonnullable fields. Response
requires every declared scalar field and supports from_attributes validation.

Literal defaults normalize and validate when a Create schema is instantiated.
Invalid literal defaults raise validation errors. Database-expression defaults
remain on the model and are never executed by generated schemas.

Adding format=url preserves model, CRUD, service, and router output. It does not
add a database URL-format constraint or imply uniqueness. Use the existing
unique/unique_together/index options as appropriate and persist validated schema
values for consistent normalization. Direct SQL and ORM writes bypass schemas.

Existing data is not migrated. Response validation may return a normalized value
without changing its stored row. String primary and foreign keys can use URLs;
normalize both sides consistently before persistence. The feature composes with
email, phone, slug, computed fields, relationships, indexes, and constraints.
It does not wire schemas into existing API routes.

## Local verification

Extract the ZIP into C:\Projects\ArcaCore so its top-level tools folder merges
with the project's tools folder. Do not extract into tools itself.

There is no new package to install for this increment. The full suite still
requires the previously installed email and phone dependencies. In a fresh
environment, install tools/requirements-email.txt and tools/requirements-phone.txt
alongside the project's existing test dependencies.

Run from the project root:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes tools.test_partial_indexes tools.test_expression_indexes tools.test_email tools.test_phone tools.test_slug tools.test_url -v
```

Expected: 182 tests, OK. Generated source is captured in memory and database tests
use in-memory SQLite. The suite does not write backend files. This increment
was tested with Python 3.12, Pydantic 2.13.4, and SQLAlchemy 2.0.52. No live
PostgreSQL execution was added. Run the suite in your Windows environment
before committing.

```powershell
git add tools
git commit -m "Sprint 22.4 - Add URL Validation support"
```

Send the local test and commit result before proceeding to another feature.

## References

- [Pydantic URL types and normalization](https://docs.pydantic.dev/latest/api/networks/)
- [Pydantic Annotated validators](https://docs.pydantic.dev/latest/concepts/validators/)

The strict string input, explicit // requirement, rejection of credentials and
whitespace, and percent-escape checks are ArcaCore policies layered before
Pydantic's URL parser.
