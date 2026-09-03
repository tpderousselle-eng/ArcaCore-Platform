# Sprint 22: Validation

Continue the user's Validation blueprint. Existing capabilities are retained
rather than implemented again. Sprint 22 began after Sprint 21.2 Expression
Indexes, GitHub main cd74c8d, with 132 relevant smoke tests.

| Feature | Status |
| --- | --- |
| Regex | Already implemented in Sprint 19.12 |
| Email | Sprint 22.1: 144 tests passed locally; committed and pushed as 9176879 |
| Phone | Sprint 22.2: 156 tests passed locally; committed and pushed as 7b5c87e |
| Slug | Sprint 22.3: implemented; 168 relevant smoke tests passed here; replacement ZIP prepared; awaiting user local test and commit |
| URL | Pending |
| Min/Max | Already implemented in Sprint 19.12 |
| Length | Already implemented in Sprint 19.12 |
| Custom validators | Pending |

The user explicitly authorized Sprint 22.3 after the Phone Validation delivery.
GitHub main 7b5c87e was fetched and its tools source compared with the working
copy before editing. Sources matched after normalizing line endings.

Sprint 22.1 added format=email for str and text fields. Generated Pydantic 2
Create, Update, and Response schemas use EmailStr; registry entries retain the
format. See EMAIL_VALIDATION.md for its behavior and dependency.

Sprint 22.2 added format=phone on the same field types. Generated schemas validate
international phone strings offline with phonenumbers and normalize them to E.164.
A country calling code is required. Extensions and national-only inputs are
rejected. See PHONE_VALIDATION.md for details.

Sprint 22.3 adds format=slug on str and text. Slugs use lowercase ASCII letters
and digits with single hyphen separators. Validation preserves the supplied
value; it does not derive or rename identifiers. No new dependency is required.
See SLUG_VALIDATION.md for the policy, examples, and full smoke command.

The 12 new slug tests cover accepted and invalid inputs across all schemas,
JSON round trips, strict input types, nullability and partial updates, literal
and database-expression defaults, length/regex composition, CLI and registry
metadata, JSON Schema, email/phone coexistence, computed fields, invalid DSL
preflight, programmatic metadata and direct generation, database uniqueness
and updates, slug keys and relationships, output compatibility, field-name
collisions, and standalone execution without optional dependencies or network.

The earlier email suite now uses unknown in its unsupported-format case, since
slug is supported. Direct schema generation also validates field formats before
skipping relationship collections, preventing invalid programmatic metadata
from being silently ignored.

Tests capture generated source in memory and use in-memory SQLite databases.
Backend source is not modified. No live PostgreSQL execution is included in
this increment.

Stop after delivering Sprint 22.3. Wait for the user's local test and commit
result before proceeding to another feature.
