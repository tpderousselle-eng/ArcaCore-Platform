# Generated application runtime contract

Stabilization 25.2 executes a representative ArcaCore-generated application
instead of limiting validation to generated source inspection.

## Boundary

The test generates every generator-owned application layer in a new temporary
project root:

- SQLAlchemy models
- Pydantic schemas
- CRUD classes
- services
- FastAPI routers
- registry metadata

The temporary fixture supplies only infrastructure outside those generators'
ownership: Python package markers, a declarative SQLAlchemy base, an isolated
SQLite session, and the application entry point that composes routers. Those
fixture files are not generated outputs and are never copied into the
repository's `backend/` directory.

After generation, the test snapshots every generated Python file. Runtime
setup and all HTTP operations must leave those files byte-for-byte unchanged.
Any incompatibility must therefore be corrected in `tools/` rather than patched
inside the generated application.

## Representative application

The runtime application contains:

- `User`, a normal CRUD entity
- `Record`, related to `User` by a one-to-many foreign key
- validated text and numeric fields
- a computed, read-only total
- audit timestamps and actor columns
- optimistic versioning
- soft deletion and restore

The non-soft-deleted `User` also exercises physical deletion, while `Record`
exercises filtered reads, retained rows, restore, actor recording, and version
increments.

## Executed checks

The dedicated suite verifies:

1. Generated modules import and SQLAlchemy metadata creates both tables.
2. Pydantic create, update, and response schemas load.
3. FastAPI starts, routers register, and OpenAPI includes generated operations.
4. Create, item read, collection read, update, and delete execute over HTTP.
5. Invalid field values, managed-field input, and missing audit actors return
   HTTP 422 responses.
6. Relationship keys serialize and both ORM relationship directions resolve.
7. Computed fields cannot be supplied and recalculate after updates.
8. Audit actors and version numbers are populated and incremented at runtime.
9. Soft-deleted rows disappear from reads and return after restore.
10. Generated sources and registry metadata remain intact throughout runtime.

## Verification

Install the isolated HTTP client used by FastAPI's test client once per
environment:

```powershell
python -m pip install -r tools\requirements-runtime.txt
```

Run only the runtime contract:

```powershell
python -m unittest tools.test_generated_runtime -v
```

Run every generator test:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```
