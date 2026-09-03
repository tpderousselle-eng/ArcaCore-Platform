# Sprint 22: Validation

Continue the user's Validation blueprint from GitHub main cd74c8d, the completed
Sprint 21.2 Expression Index feature. The baseline has 132 relevant smoke tests.
Existing capabilities are retained rather than implemented again.

| Feature | Status |
| --- | --- |
| Regex | Already implemented in Sprint 19.12 |
| Email | Sprint 22.1: implemented; 144 relevant smoke tests passed here; replacement ZIP prepared; awaiting user local test and commit |
| Phone | Pending |
| Slug | Pending |
| URL | Pending |
| Min/Max | Already implemented in Sprint 19.12 |
| Length | Already implemented in Sprint 19.12 |
| Custom validators | Pending |

Sprint 22.1 adds format=email for str and text fields. Generated Pydantic 2
Create, Update, and Response schemas use EmailStr; registry entries retain the
format. Database column types and the other generated layers are preserved.

The 12 new email smoke tests cover normalization without network requests,
malformed addresses, nullability, partial updates, defaults, length/regex
composition, JSON Schema, CLI and registry metadata, invalid DSL preflight,
programmatic metadata, database round trips and expression uniqueness, custom
email keys and relationships, field-name collisions, compatibility, and the
optional email-validator dependency.

See EMAIL_VALIDATION.md for installation and the full smoke command. Tests capture
all generated files in memory and use in-memory SQLite databases. Backend source
is not modified. PostgreSQL execution is not part of this email test increment.

Stop after delivering Sprint 22.1. Wait for the user's local test and commit
result before proceeding to another feature.
