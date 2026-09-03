# Sprint 20.4: Passive Deletes

Add passive_deletes to a foreign-key field that already declares an explicit
relationship and cascade_delete. The generator sets passive_deletes=True on the
reverse parent relationship. This avoids loading an unloaded child collection
solely to delete its rows.

## Declarations

| Module | Field declaration | Reverse relationship |
| --- | --- | --- |
| Post | user_id:int:fk=users.id:one_to_many:cascade_delete:passive_deletes | User.posts |
| Profile | user_id:int:fk=users.id:one_to_one:cascade_delete:passive_deletes | User.profile |
| Node | parent_id:int:nullable:fk=nodes.id:self_relationship:cascade_delete:passive_deletes | Node.children |
| Post | owner_id:uuid:fk=users.identifier:one_to_many(User,posts):cascade_delete:passive_deletes | User.posts |

Integer, UUID, and string keys retain their existing relationship rules. The
flag takes no arguments and may appear before or after cascade_delete and fk.
Omitting the flag keeps the prior ORM loading behavior.

## Behavior and requirements

For an unloaded child collection, the ORM deletes the parent and delegates child
deletion to the database's ON DELETE CASCADE constraint. For children already
loaded through the relationship, the ORM still issues child DELETE statements
and tracks their deleted state. One-to-One uses the same behavior on its scalar
reverse relationship. Self Relationships can delegate unloaded descendants.

The DSL requires cascade_delete on the same field, ensuring the generated foreign
key includes ON DELETE CASCADE. The database must enforce this constraint. Existing
applications must install the constraint through their normal migration workflow;
replacing generator files does not change an existing database.

The flag applies on the parent side. Deleting a child keeps its parent.
Detaching or reparenting keeps the existing behavior and does not enable orphan
deletion. Soft-delete CRUD methods still mark deleted_at and permit restoration.
Other constraints can block a hard delete and roll back the transaction.

Objects loaded separately from an unloaded collection may remain stale in the
session after the database deletes their rows. Use a fresh session or expire
state before relying on such objects. ORM hooks for individual child deletes
are not run for rows deleted solely by the database.

This feature supports the bare flag, not passive_deletes="all", false/true value
arguments, or Many-to-Many declarations. Association-table constraints are not
changed. Other dependent rows, including association links, can block delegated
deletion unless their database constraints also support it or they are removed
first. Loaded and unloaded relationships can therefore differ in whether ORM
cleanup handles those additional dependencies.

Registry metadata stores passive_deletes as a boolean. Schemas expose the usual
foreign-key value. Missing cascade_delete, duplicate flags, malformed values,
and unsupported relationships fail before generation.

## Installation and smoke suite

Extract the ZIP and copy its tools folder into C:\Projects\ArcaCore, replacing
matching files. Run from that project root in the existing virtual environment:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships tools.test_cascade_delete tools.test_passive_deletes -v
```

Expected result: 105 tests, OK. The 11 new tests cover emitted SQL, loaded and
unloaded children, One-to-One, self hierarchies, UUID/string keys, detachment,
rollback, soft deletion, CLI metadata, invalid flags, and absent-option behavior.

Tests render generated files in memory, use SQLite with foreign keys enabled,
and compile PostgreSQL DDL. They do not connect to live PostgreSQL or write
backend files or persistent registry data.

After the local suite passes:

```powershell
git add tools
git commit -m "Sprint 20.4 - Add Passive Delete support"
```

Return the local test and commit results before proceeding to another feature.

Reference: [SQLAlchemy passive deletes and foreign-key cascades](https://docs.sqlalchemy.org/en/20/orm/cascades.html#using-foreign-key-on-delete-cascade-with-orm-relationships).
