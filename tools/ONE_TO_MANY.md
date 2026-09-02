# Sprint 20.1: One-to-Many

Declare the relationship on the child model's foreign-key field. For a Post
module, `user_id:int:fk=users.id:one_to_many` creates a scalar Post.user and a
User.posts collection. Multiple Post rows may reference the same User.

The parent model must exist and both models must be imported before SQLAlchemy
configures their mappings. The reverse collection is installed by SQLAlchemy
when the models are configured; no parent source file needs to be rewritten.

## Declarations

| Declaration on Post | Scalar relationship | Parent collection |
| --- | --- | --- |
| user_id:int:fk=users.id:one_to_many | Post.user | User.posts |
| author_id:int:fk=users.id:one_to_many(User,authored_posts) | Post.author | User.authored_posts |
| reviewer_id:int:fk=users.id:one_to_many(User,reviewed_posts) | Post.reviewer | User.reviewed_posts |
| owner_id:uuid:fk=users.identifier:one_to_many(User,posts) | Post.owner | User.posts |

The bare modifier uses the existing foreign-key name inference and the child
module's lowercase name plus s for the collection. Use the explicit Model and
collection form for role names or custom collection names. The generator retains
its existing model-class capitalization convention.

Modifiers may appear in any order, except regex remains the final modifier.
Int, UUID, and string foreign keys are supported; use a type matching the parent
key. Parent keys must be primary or unique database keys. The referenced parent
table, key, type, and existing parent attributes are checked by SQLAlchemy/the
database when the complete application is loaded, not by this single-module DSL.
Choose a collection name that does not collide with an existing parent attribute.

## Behavior

Appending a child to the parent collection sets its scalar relationship.
Reassigning it updates both collections and its foreign key after flushing.
Removing it from a nullable relationship clears the foreign key without deleting
the row. Non-nullable relationships reject detachment at database flush/commit.

The new modifier explicitly generates nullable=False unless nullable is supplied.
It does not add a uniqueness constraint. It selects the exact foreign-key column,
so separate author/reviewer relationships to one model are unambiguous.

Schemas continue to expose the foreign-key value. Nested relationship input or
response schemas are not added. Registry metadata uses many_to_one for the child
side and records the parent model, foreign-key reference, and reverse collection
in the existing backref metadata.

Malformed declarations, conflicting one_to_one/unique/pk/computed modifiers,
local relationship-name collisions, duplicate reverse names for the same target
within one module, and self relationships are rejected before generation.
Ordinary fk declarations and existing One-to-One/Many-to-Many behavior retain
their existing meaning.

Delete cascading and passive deletes are not part of this feature.

## Smoke suite

```powershell
python -m unittest tools.test_array tools.test_choice tools.test_one_to_one tools.test_many_to_many tools.test_composite_indexes tools.test_soft_delete tools.test_constraints tools.test_validators tools.test_computed tools.test_one_to_many -v
```

Tests capture the full generation pipeline in memory and use SQLite with foreign
keys enabled. They do not write backend files or connect to a live PostgreSQL
instance.

References: [SQLAlchemy one-to-many relationships](https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#one-to-many) and [backref behavior](https://docs.sqlalchemy.org/en/20/orm/backref.html).
