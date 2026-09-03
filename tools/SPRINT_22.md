# Sprint 22: Validation

Continue the user's Validation blueprint. Existing capabilities are retained
rather than implemented again. Sprint 22 began after Sprint 21.2 Expression
Indexes, GitHub main cd74c8d, with 132 relevant smoke tests.

| Feature | Status |
| --- | --- |
| Regex | Already implemented in Sprint 19.12 |
| Email | Sprint 22.1: 144 tests passed locally; committed and pushed as 9176879 |
| Phone | Sprint 22.2: implemented; 156 relevant smoke tests passed here; replacement ZIP prepared; awaiting user local test and commit |
| Slug | Pending |
| URL | Pending |
| Min/Max | Already implemented in Sprint 19.12 |
| Length | Already implemented in Sprint 19.12 |
| Custom validators | Pending |

The user explicitly authorized Sprint 22.2 after the Email Validation delivery.
GitHub main 9176879 was fetched and its tools source compared with the working
copy before editing. Sources matched after normalizing line endings.

Sprint 22.1 added format=email for str and text fields. Generated Pydantic 2
Create, Update, and Response schemas use EmailStr; registry entries retain the
format. See EMAIL_VALIDATION.md for its behavior and dependency.

Sprint 22.2 adds format=phone on the same field types. Generated schemas validate
international phone strings offline with phonenumbers and normalize them to E.164.
A country calling code is required. Extensions and national-only inputs are
rejected. Database column types and the other generated layers are preserved.

The 12 new phone tests cover international normalization without network requests,
invalid numbers and input types, extensions, nullability and partial updates,
defaults, normalized length/regex checks, CLI and registry metadata, JSON Schema,
email coexistence, computed fields, invalid DSL preflight, programmatic metadata,
database round trips and uniqueness, phone keys and relationships, field-name
collisions, compatibility, and missing dependencies. The earlier email suite's
unsupported-format case now uses fax, since phone is supported.

See PHONE_VALIDATION.md for installation and the full smoke command. Tests capture
all generated files in memory and use in-memory SQLite databases. Backend source
is not modified. No live PostgreSQL execution is included in the phone increment.

Stop after delivering Sprint 22.2. Wait for the user's local test and commit result
before proceeding to another feature.
