# Sprint 22: Validation

Continue the user's Validation blueprint. Existing capabilities are retained
rather than implemented again. Sprint 22 began after Sprint 21.2 Expression
Indexes, GitHub main cd74c8d, with 132 relevant smoke tests.

| Feature | Status |
| --- | --- |
| Regex | Already implemented in Sprint 19.12 |
| Email | Sprint 22.1: 144 tests passed locally; committed and pushed as 9176879 |
| Phone | Sprint 22.2: 156 tests passed locally; committed and pushed as 7b5c87e |
| Slug | Sprint 22.3: 168 tests passed locally; committed and pushed as 99e94ac |
| URL | Sprint 22.4: implemented; 182 relevant smoke tests passed here; replacement ZIP prepared; awaiting user local test and commit |
| Min/Max | Already implemented in Sprint 19.12 |
| Length | Already implemented in Sprint 19.12 |
| Custom validators | Pending |

The user explicitly authorized Sprint 22.4 after the Slug Validation delivery.
GitHub main 99e94ac was fetched and its tools source compared with the working
copy before editing. Sources matched after normalizing line endings.

Sprint 22.1 added format=email for str and text fields. Generated Pydantic 2
Create, Update, and Response schemas use EmailStr; registry entries retain the
format. See EMAIL_VALIDATION.md for its behavior and dependency.

Sprint 22.2 added format=phone on the same field types. Generated schemas validate
international phone strings offline with phonenumbers and normalize them to E.164.
A country calling code is required. Extensions and national-only inputs are
rejected. See PHONE_VALIDATION.md for details.

Sprint 22.3 added format=slug on str and text. Slugs use lowercase ASCII letters
and digits with single hyphen separators. Validation preserves the supplied
value; it does not derive or rename identifiers. No new dependency is required.
See SLUG_VALIDATION.md for details.

Sprint 22.4 adds format=url on str and text. Generated schemas validate absolute
HTTP(S) URLs and return normalized plain strings. URL validation needs no new
package. It does not fetch destinations. The parser preserves colons inside
quoted defaults so URL literals can include schemes and ports. Actual regex
modifiers remain last and retain their literal contents.

The 14 new URL tests cover normalization across all schemas and JSON, strict
input types, invalid schemes/hosts/ports/escapes, credentials and whitespace,
nullability, partial updates, literal and database-expression defaults, quoted
colons and escaped quotes, malformed-default preflight, normalized length/regex,
CLI/registry/JSON Schema, all named formats together, computed fields, invalid
DSL preflight, programmatic metadata/direct generation, database uniqueness and
updates, URL keys/relationships, output compatibility, and standalone execution
without optional packages or network requests.

The earlier email suite now uses uri in its unsupported-format case, since url
is supported. The duplicate email/url format test remains a rejection case.
See URL_VALIDATION.md for the exact input policy and full local smoke command.

Tests capture generated source in memory and use in-memory SQLite databases.
Backend source is not modified. No live PostgreSQL execution is included in
this increment.

Stop after delivering Sprint 22.4. Wait for the user's local test and commit
result before proceeding to another feature.
