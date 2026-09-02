# Sprint 20.2: Self Relationships

A foreign-key field can reference another row in its own model. The generator
creates a scalar parent relationship and a reverse collection on that same class.

## Declarations

| Module | Field declaration | Scalar link | Reverse collection |
| --- | --- | --- | --- |
| Node | parent_id:int:nullable:fk=nodes.id:self_relationship | Node.parent | Node.children |
| Employee | manager_id:int:nullable:fk=employees.id:self_relationship(reports) | Employee.manager | Employee.reports |
| Employee | mentor_id:int:nullable:fk=employees.id:self_relationship(mentees) | Employee.mentor | Employee.mentees |
| Node | parent_id:uuid:nullable:fk=nodes.identifier:self_relationship | Node.parent | Node.children |

The bare modifier uses children as the collection name. The parent relationship
name follows the existing foreign-key naming convention: parent_id becomes
parent, and manager_id becomes manager. The target class is the current model.
The generator retains its existing class-name capitalization and table-name
conventions.

The UUID declaration requires identifier:uuid:pk on the same module. Integer,
UUID, and string foreign keys are supported and must match the single local
primary key's type. The key may appear before or after the relationship field.
When no primary key is declared, the reference must target the generated int id.
An explicitly declared id must include pk. Composite and non-primary target keys
are outside this feature.

Use nullable to allow root rows without parents and to permit detaching children.
Without it, the foreign-key column is required by the database. Modifiers may be
reordered; regex still must be the final modifier.

## Generated behavior

The scalar relationship uses uselist=False, foreign_keys for the declared column,
and remote_side for the referenced primary key. A backref creates the named
collection on the same model. Multiple self links can coexist when their scalar
and collection names are distinct.

Appending and reparenting update both relationship directions and synchronize
the foreign-key value when flushed. Removing a child from a nullable collection
clears its foreign key and keeps its row. This feature does not enforce acyclic
trees or implement recursive queries, nested schemas, self-referencing
many-to-many associations, cascade deletion, or passive deletion.

Schemas continue to expose the foreign-key value rather than parent objects or
child collections. Registry metadata records self_many_to_one, the current
model and table, the referenced key, and the reverse collection in backref.
Existing indexes, constraints, validators, computed fields, and soft-delete
columns compose with the self link. Soft deletion retains its existing behavior;
relationship collections do not automatically filter soft-deleted rows.

## Validation

Before generation, the parser rejects malformed declarations, references to
another table or an unknown/non-primary key, key-type mismatches, conflicting
relationship modifiers, primary/unique/computed foreign-key modifiers, and
colliding or reserved relationship names. A self link requires its own foreign-key
column, separate from the primary key. Existing one_to_many declarations continue
to require an external target; use self_relationship for the same model.

## Installation and smoke suite

The ZIP contains complete replacement files under tools/. Copy its tools folder
into C:\Projects\ArcaCore and replace matching files. Run this from that project
root using the existing virtual environment:

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many tools.test_self_relationships -v
```

Expected result: 80 tests, OK. Tests capture generated files in memory, configure
real SQLAlchemy mappings, and exercise SQLite with foreign keys enabled.
PostgreSQL DDL is compiled without connecting to a PostgreSQL server. No backend
files or persistent registry data are written by this suite.

After the local suite passes, commit from the same project root:

```powershell
git add tools
git commit -m "Sprint 20.2 - Add Self Relationship support"
```

Return the local test and commit results before the third feature begins.

Reference: [SQLAlchemy adjacency-list relationships](https://docs.sqlalchemy.org/en/20/orm/self_referential.html).
