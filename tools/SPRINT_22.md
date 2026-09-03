# Sprint 22: Validation

Continue the user's Validation blueprint. Sprint 22 began after Sprint 21.2
Expression Indexes, GitHub main cd74c8d, with 132 relevant smoke tests.

| Feature | Status |
| --- | --- |
| Regex | Already implemented in Sprint 19.12 |
| Email | Sprint 22.1: 144 tests passed locally; committed and pushed as 9176879 |
| Phone | Sprint 22.2: 156 tests passed locally; committed and pushed as 7b5c87e |
| Slug | Sprint 22.3: 168 tests passed locally; committed and pushed as 99e94ac |
| URL | Sprint 22.4: 182 tests passed locally; committed and pushed as 74eae06 |
| Min/Max | Already implemented in Sprint 19.12 |
| Length | Already implemented in Sprint 19.12 |
| Custom validators | Sprint 22.5: implemented; 198 relevant smoke tests passed here; replacement ZIP prepared; awaiting user local test and commit |

The user authorized Sprint 22.5 after the URL Validation delivery. GitHub main
74eae06 was fetched and its tools source compared with the working copy before
editing. Sources matched after normalizing line endings.

Sprint 22.1 added format=email on str and text. Generated Pydantic 2 schemas use
EmailStr; see EMAIL_VALIDATION.md for normalization and the optional dependency.

Sprint 22.2 added format=phone. International phone strings are validated offline
with phonenumbers and normalized to E.164; see PHONE_VALIDATION.md.

Sprint 22.3 added format=slug. Lowercase ASCII letters/digits use single hyphen
separators, preserving the supplied value; see SLUG_VALIDATION.md.

Sprint 22.4 added format=url. Absolute HTTP(S) URLs become normalized plain
strings without fetching destinations. The parser preserves colons in quoted
default literals; see URL_VALIDATION.md.

Sprint 22.5 adds repeatable validator=package.module.function declarations.
Metadata retains ordered references, and generated schemas import the application
rules without depending on tools. Rules run after built-in validation and each
returned value is revalidated before proceeding. Generation never imports or
executes rule modules. See CUSTOM_VALIDATORS.md and the complete example at
examples/validation_rules.py.

The 16 new tests cover typed inputs and rejections across Create/Update/Response,
ordered transformations, return-value constraints, named format normalization,
nullability and defaults, synchronous callable contracts and runtime failures,
invalid DSL and programmatic preflight, CLI/registry/JSON Schema, computed fields,
arrays/JSON/scalar types, custom key relationships and database uniqueness,
backward compatibility, import isolation, and complete example modules.

Tests capture generated source in memory and use in-memory SQLite. Backend
source is not modified. No live PostgreSQL execution is included.

All listed Sprint 22 capabilities are implemented. The Custom Validators
delivery still requires the user's local test and commit result. Stop after
delivering Sprint 22.5; do not begin Sprint 23 without explicit authorization.
