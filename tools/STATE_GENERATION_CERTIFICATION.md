# Approved state generation certification

## 31.1 public contract audit

The audit covers `core/field_parser.py`, `core/module_definition.py`,
`generate_model.py`, `generate_schema.py`, `generate_crud.py`, their templates,
`renderers/sqlalchemy_renderer.py`, `validators/field_validator.py`, and existing
array, choice, enum, primary-key, schema, CRUD and PostgreSQL tests.

ArcaCore already implements scalar fields, decimal precision/scale, ARRAY,
native enum, string choice domains, safe defaults and immutable primary-key
updates. No duplicate generators were added. One real gap was corrected:
non-nullable public fields now emit `nullable=False` at the database boundary,
matching their existing schema contract. Implicit timestamp columns retain
their explicitly authorized server-managed semantics.

| Approved authority | Certification |
| --- | --- |
| string, text, integer, boolean, date, datetime, UUID, JSON | Existing scalar declarations; UUID here is a non-identity field |
| required/nullable and uniqueness | Exact public flags; uniqueness must be explicit |
| immutable string identity | `str:pk`; schema and CRUD reject key updates |
| integer identity with approved integer literal default | `int:pk:default=<literal>`; key stays immutable |
| UUID identity; integer identity without literal default | Blocked: generator introduces UUID factory/autoincrement semantics not expressible by current logical default authority |
| complete enum domain, including a lifecycle domain bound to an approved field | Public `choice(...)`: exact string values, deterministic `<physical_field>_choice` constraint name; no native enum member normalization |
| literal string/text/integer/boolean/enum defaults | Type checked and emitted as Python literals; nullable non-JSON null is supported |
| decimal | Blocked: logical authority has no precision/scale |
| collections | Blocked: a collection boolean does not specify ordering, duplicates or nesting |
| external/binary reference logical types | Blocked: physical encoding is unspecified |
| approved string classified as an external identifier | Existing string declaration; classification and provenance remain frozen |
| arbitrary default expressions or callable references | Blocked; JSON strings stay literal strings |

Public choice grammar cannot preserve empty values, leading/trailing whitespace,
commas, parentheses or control characters. These values and overlong physical
constraint names are rejected, never normalized or truncated. Native enum
templates uppercase member names and SQLAlchemy stores member names by default;
choice is the existing exact value-preserving representation. Lifecycle values
without a bound approved field remain blocked. Non-identity immutability also
remains blocked because standard CRUD cannot enforce it.

### Actual Gaming Studio authority

The frozen model contains five entities and **zero approved fields**, identity
field bindings, value-domain records, relationship records, constraint records
or access records. It does retain accepted logical claims. The proposed fields
in the original model are not approved merely because clarification completed.
31.1 therefore creates zero module requests: 57 findings before and after,
6 UNSUPPORTED and 51 REQUIRES_CERTIFICATION, including five logical-state
findings. No approved model is changed to obtain a smaller count.

Dedicated verification: `python -B -m unittest tools.test_arcadev_state_fields -v`.

31.1 dedicated result: 14 passed. PostgreSQL runtime plus migration result:
16 passed, using fresh pgembed PostgreSQL servers. Complete discovery uses
`python -B -m unittest discover -s tools -t . -p 'test_*.py' -v`;
the ArcaDev-only pattern is `test_arcadev_*.py`. The explicit top-level directory
keeps imports package-qualified so fixtures share their existing caches.

The complete 31.1 ArcaDev suite passed 437 tests. Full repository discovery
covered 1,169 tests in 95 isolated module processes, with one existing Docker
runtime opt-in skip. Its partial-index escaping fixture omitted a required
numeric value; the fixture now supplies zero and all 13 partial-index tests
passed on rerun. The temporary parallel reporter was also corrected to serialize
the Docker skip, and that module's 12 tests were re-recorded. Reconciliation
compares every discovered test identity with the completed module records;
no test is omitted. PostgreSQL runtime and migration suites passed all 16 tests.
