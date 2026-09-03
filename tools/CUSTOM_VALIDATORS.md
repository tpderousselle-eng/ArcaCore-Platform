# Sprint 22.5: Custom validators

## DSL

| Declaration | Meaning |
| --- | --- |
| quantity:int:min=0:validator=validation_rules.require_even | Nonnegative integer checked by an application rule |
| slug:str:format=slug:validator=validation_rules.reject_reserved_slug | Slug syntax followed by a reserved-name check |
| value:int:validator=rules.first:validator=rules.second | Two rules in declaration order |
| value:int:nullable:validator=rules.check | Skip the rule for None |
| value:int:default=4:validator=rules.check | Check the literal default when Create is validated |

A reference has the form module.function or package.module.function. Every part
must be a public ASCII Python identifier, not a keyword. Empty references,
duplicates on one field, private names, expressions, calls, and subscription
syntax are rejected before generation. Put validator= before regex=, because
regex continues to consume the remaining declaration literally. Other modifiers
may appear between validator declarations without changing their relative order.

Field metadata stores an ordered validators list. Registry entries include this
list only for fields with rules. Reusing a rule on different fields is allowed;
generated imports are deduplicated. No new dependency is required.

## Application rule contract

The ZIP includes the complete example module tools/examples/validation_rules.py.
It defines require_even and reject_reserved_slug. The generator feature and
example live inside tools; no backend source is changed by installing this ZIP.

References identify developer-owned application code. When deploying a generated
application, package its rule modules so the configured imports resolve. For
example, validator=validation_rules.require_even requires an importable
validation_rules module. The example is not automatically copied into generated
applications. Generated schemas do not import the ArcaCore tools package.

Each rule must be synchronous, accept one positional value, and return a value.
Additional optional parameters are allowed but are not supplied. Missing modules
or exported names fail when the generated schema is imported. Noncallables,
incompatible signatures, async functions, and generator functions are rejected
at that time. A synchronous wrapper that returns an awaitable or generator is
rejected during validation.

Raise ValueError to reject user input; Pydantic reports the error at that field.
TypeError and other programming errors are not converted into successful values
or silently ignored. Always return the accepted value, even for a check that
does not transform it.

Use pure, deterministic rules with idempotent normalization. Rules also run on
Response validation, so a transformation can run again when a stored value is
read. Rules should not perform database writes or network requests. These are
trusted Python modules, not sandboxed DSL expressions: importing a module can
execute its top-level code in the generated application.

## Execution order

For each supplied field, the generated wrapper:

1. Runs the existing type, nullability, format, bounds, length, and regex checks.
2. Passes the resulting Python value to the first custom rule.
3. Revalidates the returned value through those same built-in checks.
4. Repeats steps 2 and 3 for each remaining rule in declaration order.

Each rule receives the output of the preceding validation step. For example,
numeric strings become integers before an integer rule runs, and email/phone/URL
rules see normalized strings. A rule cannot bypass the field's built-in
constraints by returning an invalid value. Normal Pydantic coercion remains
enabled: a numeric string returned by an integer rule can become an integer.

Earlier custom rules are not rerun after later rules transform the value. Rule
authors must choose an order that preserves their intended custom invariants.
Built-in checks are reapplied after every custom return.

Rules apply to whole fields. An array rule receives the validated list, and a
JSON rule receives the value accepted by the existing Any-based JSON schema.
This feature does not add JSON-serializability checks to Any. Choice and Enum
rules receive one of the existing allowed strings. Scalar foreign keys and
explicit primary keys can have rules; collection relationships cannot.

## Create, Update, and Response

| Case | Behavior |
| --- | --- |
| Supplied nonnullable value | Built-in checks and custom rules run |
| Explicit None on nonnullable field | Rejected before custom rules |
| Nullable None | Accepted without running custom rules |
| Nullable rule returns None | Accepted; remaining custom rules are skipped |
| Omitted Update field | No custom rule runs |
| Omitted generated integer/UUID key | No custom rule runs on Create |
| Literal Create default | Built-in checks and custom rules run |
| Database-expression default | Remains on the model; not executed in schemas |
| Computed field | Rules run on Response only; Create/Update stay read-only |
| Response validation | Declared fields remain required; rules run on supplied attributes |

Use model_dump(exclude_unset=True) for partial updates and to preserve omission
of generated keys or expression defaults. As before, schemas do not validate
attribute assignment after construction.

Custom rules are schema validation, not database constraints. Persist validated
schema values to retain transformations. Direct SQL/ORM writes bypass the rules;
Response validation does not update stored rows. Normalize both sides of a
custom primary/foreign key consistently. Custom validation on computed fields
can reject or transform response values but does not change the database
calculation.

JSON Schema retains existing type, format, constraint, and readOnly metadata,
and adds x-arca-validators with the ordered references. The extension documents
the configured rules; it cannot express or execute their Python behavior.

## Scope

Changes extend the existing field metadata, parser, validator preflight,
registry, schema generator, and templates. Models, CRUD, services, and routers
retain their previous output. Application rule modules are neither imported nor
executed while generating source, so availability and signature checks happen
when the generated application imports its schemas.

This increment covers synchronous field rules only. It does not introduce
cross-field callbacks, async validation, dependency injection, database hooks,
route wiring, migration logic, or a plugin system.

## Local verification

Extract tools-sprint-22-5.zip into C:\Projects\ArcaCore so the top-level tools
folder merges with the existing tools folder. Do not extract into tools itself.
Every included source file is a complete replacement.

No new package is needed. The full suite still requires the existing project
dependencies and the email and phone requirements from previous increments.

Run from the project root:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes tools.test_partial_indexes tools.test_expression_indexes tools.test_email tools.test_phone tools.test_slug tools.test_url tools.test_custom_validators -v
```

Expected: 198 tests, OK. The 16 new tests cover callable preflight, declaration
order, return-value validation, named formats, nullability, defaults, generated
keys, computed fields, collections and scalar types, schema inheritance,
CLI/registry/JSON Schema, database uniqueness and relationships, import failures,
standalone execution, and the complete example module.

Tests capture generated source in memory and use in-memory SQLite. They do not
write backend files. Verified here with Python 3.12, Pydantic 2.13.4, and
SQLAlchemy 2.0.52; live PostgreSQL execution is not part of this increment.

After your local tests pass:

```powershell
git add tools
git commit -m "Sprint 22.5 - Add Custom Validator support"
```

Send the local test and commit result. Stop here; Sprint 23 requires a new
explicit instruction to continue.

## Reference

The generated wrapper uses Pydantic's handler-based field validation and
field-level ValueError reporting. See
[Pydantic validators](https://docs.pydantic.dev/latest/concepts/validators/).
Ordering, reference syntax, return-value revalidation, and None handling above
are ArcaCore's policies.
