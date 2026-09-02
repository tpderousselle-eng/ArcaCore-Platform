# Sprint 20.3: Cascade Delete

Add cascade_delete to an explicit relationship's foreign-key field to delete its
child rows when the referenced parent row is hard-deleted. This is opt-in.

## Declarations

| Module | Field declaration | Hard-delete behavior |
| --- | --- | --- |
| Post | user_id:int:fk=users.id:one_to_many:cascade_delete | Deleting User deletes its Posts |
| Profile | user_id:int:fk=users.id:one_to_one:cascade_delete | Deleting User deletes its Profile |
| Node | parent_id:int:nullable:fk=nodes.id:self_relationship:cascade_delete | Deleting Node deletes its descendants |
| Post | owner_id:uuid:fk=users.identifier:one_to_many(User,posts):cascade_delete | Deleting User deletes Posts referencing its UUID key |

The flag accepts no arguments and may appear before or after the relationship
and fk modifiers. Int, UUID, and string foreign keys are supported. Existing
relationship rules still apply, including matching key types and valid names.
External target keys must be primary or unique keys in the database.

## Generated behavior

The child foreign key gains ondelete="CASCADE". The reverse parent relationship
gains cascade="save-update, merge, delete" through backref. This keeps the existing
save/update and merge behavior and adds parent-to-child ORM deletion. One-to-One
retains its scalar reverse relationship. Self Relationships retain remote_side.
The backref import is generated automatically when needed.

Deleting a child does not delete its parent. For multiple foreign keys, each flag
applies to its declared relationship. Fields without the flag retain their prior
behavior. Registry field metadata stores cascade_delete as a boolean; schemas
continue to expose the foreign-key value rather than a cascade setting.

Both Session.delete(parent) and a database DELETE can remove dependent rows.
The ORM handles loaded and unloaded child collections. Database-side cascading
requires the generated foreign-key constraint to be installed and enforced.
Changing generated source does not update an existing database constraint; the
normal database migration workflow must apply that change when an application
adopts this feature.

ORM cascades do not apply to bulk DELETE statements. Bulk/direct database deletes
rely on ON DELETE CASCADE. If objects were already loaded in an ORM session,
expire them or use a fresh session before inspecting database-side results.
Other foreign keys can still block deletion and roll back the transaction.

Removing a child from a nullable collection or reassigning its parent does not
delete the row: delete-orphan is not enabled. Non-nullable foreign keys still
reject detachment. Self-relationship cascade tests cover acyclic hierarchies;
cycle enforcement is not added.

Soft-delete CRUD methods continue to set deleted_at, retain child rows, and allow
restoration. A deliberate hard delete still physically deletes descendants even
when a model has soft-delete columns. This feature configures generated model
relationships; it does not add hard-delete CRUD methods or router endpoints.

Many-to-Many fields do not accept cascade_delete. ORM deletion of a cascaded
child continues to remove that child's association links without deleting shared
target objects. Existing association-table foreign keys are not changed; direct
SQL deletion can therefore be blocked by those links until they are removed.

Passive Deletes are outside this batch. No passive_deletes setting is generated.

## Validation

Invalid or duplicate cascade flags, missing foreign keys, plain fk declarations
without an explicit relationship, unsupported field types, name collisions, and
self-referencing One-to-One declarations fail before generation. Use the
self_relationship modifier for a self-referencing cascade.

## Installation and tests

The ZIP contains complete replacement files under tools/. Copy its tools folder
into C:\Projects\ArcaCore and replace matching files. Run from that project root
using the existing virtual environment:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete -v
```

Expected result: 94 tests, OK. The 14 new tests cover delete direction, loaded and
unloaded collections, database deletes, One-to-One, self subtrees, custom keys,
detachment, selective flags, rollback, soft deletion, association cleanup, CLI
metadata, invalid DSL, and unchanged behavior when the option is absent.

The tests render all generated files in memory and use SQLite with foreign keys
enabled. PostgreSQL DDL is compiled; no live PostgreSQL connection is used.
No backend files or persistent registry data are written by this suite.

After the local suite passes:

```powershell
git add tools
git commit -m "Sprint 20.3 - Add Cascade Delete support"
```

This is feature three of the authorized batch. Return the local test and commit
results, then stop. No fourth feature or later sprint begins without an explicit
new instruction.

Reference: [SQLAlchemy cascade behavior](https://docs.sqlalchemy.org/en/20/orm/cascades.html).
