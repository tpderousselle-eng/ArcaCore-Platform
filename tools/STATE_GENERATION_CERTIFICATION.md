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

## 31.3 isolated multi-module execution and actual state report

Re-audited `arcadev/backend_generation.py`, `_generation_process.py`, the public
`tools.generate` entrypoint, transactional registry, artifact validation and
model/schema templates. The existing controller already isolated multi-module
generation and rejected incomplete inventories. It now explicitly executes the
derived dependency plan through the same bounded subprocess transport. Only
the full validated request may earn a complete artifact manifest. The internal
module executor returns invocation/diagnostic evidence, never approval or an
application-completion claim. A failed later module discards the overall manifest
and the entire temporary workspace.

`arcadev.state_certification.state_certification_report(request, previous_counts=...)`
reconstructs current request authority before reporting per-entity dispositions,
exact reasons, module IDs, dependency evidence and every capability group.
Historical totals are explicitly supplied comparison context. Current totals
and support are always computed; changing historical context cannot grant support.
The report distinguishes `all_state_generatable` from
`eligible_for_backend_generation`. Even a fully representable state model cannot
bypass an unsupported authentication or application responsibility.

The approved two-module fixture exercises exact choice values/defaults and
integer checks through all five public generator layers. Two fresh runs compare
artifact bytes, hashes, inventory, registry and canonical run evidence. A separate
explicit physical Parent/Child fixture executes the same dependency transport
and verifies exact FK, reverse, cascade and passive-delete output. This proves
public relationship execution; it does not invent the missing logical FK binding
needed to approve an application relationship.

### Gaming Studio result reconstructed from frozen authority

The original model and finalization identities remain
`arcadev_domain_model_fa14437a45ef581d1da735a1f2c22d5a` and
`arcadev_model_final_69a80476151dcf829cee5d282af6de9a`.
Every entity below is **BLOCKED** with the same exact reconstructed reason:
“Approved logical choices have no named approved fields or bound identity;
physical fields and defaults cannot be invented.”

| Frozen entity | Entity ID |
| --- | --- |
| build management state | `arcadev_model_entity_4935d6f577e3901634ec8e38f30e4200` |
| game project management state | `arcadev_model_entity_4f2a09fa4cdda29266fb2715bfe64ae6` |
| GitHub integration state | `arcadev_model_entity_591a87513228eb7ae3d6d22573264131` |
| publishing workflow state | `arcadev_model_entity_7271c84ed97605a31a93482b6267a8ad` |
| asset management state | `arcadev_model_entity_feb97c2c6ca333bca2718663710def20` |

No testing-outcome entity or field is inferred. Zero entities are generatable,
zero module requests are created, and no workspace or generator starts for this
request. Backend authority remains APPROVED, project IN_PROGRESS / BACKEND,
generation BLOCKED_INCOMPATIBLE. No FRONTEND transition occurs.

| Remaining capability | Unsupported | Requires certification | Total |
| --- | ---: | ---: | ---: |
| LOGICAL_STATE | 0 | 5 | 5 |
| STANDARD_MODULE | 0 | 5 | 5 |
| AUTHORIZATION | 0 | 3 | 3 |
| APPLICATION_OPERATION | 0 | 12 | 12 |
| EXTERNAL_INTEGRATION | 3 | 0 | 3 |
| PUBLISHING | 1 | 0 | 1 |
| ISOLATED_WORKER | 1 | 0 | 1 |
| APPLICATION_JOB | 1 | 0 | 1 |
| STORAGE | 0 | 2 | 2 |
| IMPLEMENTATION_CHOICE | 0 | 24 | 24 |
| **Total** | **6** | **51** | **57** |

Before: 57 / 6 / 51. After: 57 / 6 / 51. Delta: zero in every count.
These are observed results, not targets imposed on the translator. GitHub
integration, publishing, isolated workers, jobs and application-specific handlers
remain unsupported or uncertified; state certification does not implement them.

Dedicated verification: `python -B -m unittest tools.test_arcadev_state_generation -v`.
The final repository runner schedules the two startup-timing modules serially
after the remaining discovered modules, with unchanged tests and timeouts.

Final certification of the completed 31.3 implementation: all three dedicated
suites passed (14 field, 20 relation, 14 multi-module/report tests). Complete
ArcaDev discovery passed 471 tests with zero failures, errors or skips. Complete
repository discovery executed all 1,203 tests across 97 modules with zero
failures/errors and one allowed Docker runtime opt-in skip; both startup-timing
modules passed on their first serial execution in this final run. The separate
PostgreSQL runtime/migration invocation passed all 16 tests. No source application
files were generated or patched; successful fixture manifests contain temporary
evidence only and still require accepted schema, application-manifest and runtime
authority before any application-completion claim.
