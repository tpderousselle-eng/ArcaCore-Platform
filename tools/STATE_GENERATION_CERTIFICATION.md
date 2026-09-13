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

## 31.2 relationship, constraint, access and dependency audit

Audited public contracts: `core/relationship_parser.py`,
`core/self_relationship_parser.py`, `core/cascade_parser.py`,
`core/constraint_parser.py`, `core/index_parser.py`,
`core/expression_index_parser.py`, `core/module_definition.py`, all five module
generators, their templates, the SQLAlchemy renderer and registry. Existing
one-to-many, one-to-one, many-to-many, self-relationship, cascade, passive-delete,
constraint, index, expression-index and PostgreSQL suites exercise these paths.

The public field grammar already supports explicit child FK-backed one-to-many
collections, one-to-one reverse scalar relationships, association-table
many-to-many, and adjacency-list self relationships. `cascade_delete` adds ORM
parent-to-child deletion and database `ON DELETE CASCADE`; `passive_deletes`
delegates unloaded child deletion to the database. Neither is inferred.

Approved logical relationships contain entity endpoints, cardinalities,
ownership and deletion labels. They do **not** bind a source FK field, reverse
attribute, association-table authority or tenant scope. No relationship type
is therefore certified for ApprovedDomainModel translation merely because its
cardinality resembles a public parser option. `retain`, `restrict`, `detach`
and `delete_dependent` all remain blocked without complete bindings. The public
relationship contracts and dependency handling are tested independently of
approved-application eligibility.

| Logical requirement | Exact translation or remaining boundary |
| --- | --- |
| Required scalar field uniqueness | Existing `unique`; primary-key uniqueness is intrinsic |
| Nullable or JSON uniqueness | Blocked: null/equality behavior is not certified |
| Composite uniqueness over required fields with database equality | `unique_together(...)`, preserving all columns and canonical public naming |
| Integer minimum/maximum | Public `check(field >= value)` / `check(field <= value)`, integral values within PostgreSQL Integer bounds |
| Unique identity lookup | Existing CRUD identity lookup; no extra index |
| Other access/lookup requirements | Blocked; lookup does not mean database index |
| Arbitrary check expressions, patterns, lifecycle/ownership invariants | Blocked; no prose compiler |

The current baseline model clarification offers `identity_only` uniqueness.
It cannot approve an additional composite-uniqueness requirement by silently
dropping that material question. This authority-policy limit remains intact.
Composite translation is verified with logical records and the public parser;
the full approved fixture exercises integer bounds and unique identity access.
Every translated constraint/access keeps its own source ID and decision evidence.

`generation_dependency_plan` derives dependencies from public field metadata:
exact table, class, single identity, key type, FK name and reverse attribute.
Missing targets, incomplete legacy bare FKs, reverse collisions and module cycles
are rejected. The public self-adjacency contract is a field-level self reference,
not a module-order cycle. Ready modules sort by physical module name; edges retain
both entity IDs, both request IDs and exact source/target field names. Reordering
input records or moving workspaces cannot change the plan.

Multiple explicitly approved CRUD responsibilities may use the exact authority
form returned by `standard_module_capability(scope)`: the existing standard CRUD
sentence plus a bounded parenthesized scope identifier. A scope label alone,
similar wording or additional application behavior grants no capability. This
allows separate approved CRUD modules without duplicating a logical capability
owner or weakening the frozen model. It does not make Gaming Studio eligible.

Gaming Studio remains five blocked state entities, zero module requests and
57 findings (6 unsupported, 51 requiring certification). Its relationship choices
remain in frozen authority; no FK fields or deletion behavior are manufactured.

Dedicated verification: `python -B -m unittest tools.test_arcadev_state_relations -v`.

31.2 passed 20 dedicated relation tests (34 with the 31.1 field suite),
457 complete ArcaDev tests, and all 1,189 discovered repository tests, with
one allowed Docker runtime opt-in skip. The parallel run initially hit four
startup/readiness timing assertions in the build-orchestrator and runtime-harness
modules. Both modules passed unchanged with lower worker load (12 and 16 tests);
the initial logs are retained and every discovered test identity was reconciled.
No production timeout or test assertion was relaxed. PostgreSQL runtime and
migration suites separately passed all 16 tests. Protected-file hash comparison
found zero differences, including the initial absence of `tools.zip`.
