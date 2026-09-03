# Generated PostgreSQL runtime contract

Stabilization 25.3 executes an advanced generated model set against a fresh,
isolated PostgreSQL server. It does not substitute SQLite for PostgreSQL and it
does not write or repair files under the repository's `backend/` directory.

## Boundary

The test generates Account, Role, and Record through the normal five-layer
module pipeline in a temporary project root. The fixture supplies only package
markers, a declarative base, and a database session bound to the temporary
PostgreSQL server. Generated Python source is snapshotted before execution and
must remain byte-for-byte unchanged.

`pgembed` supplies the local PostgreSQL binaries and starts the isolated server
without Docker or an existing PostgreSQL installation. A restricted root-only
test environment can point `ARCACORE_PGLITE_SERVER` at the PGlite socket server;
that fallback still runs PostgreSQL through its wire protocol and never uses
SQLite.

## Executed checks

The contract proves PostgreSQL table creation and native UUID, Numeric, JSON,
ARRAY, and enum behavior. It executes foreign keys, unique and check
constraints, composite indexes, partial indexes, expression indexes, computed
columns, encrypted storage, many-to-many and one-to-many persistence,
database-side cascade with passive deletes, soft deletion and restore, audit
actors, and optimistic version conflict detection.

PostgreSQL behavior is authoritative for this contract, including its native
type, constraint, index, computed-column, and referential-integrity semantics.

## Verification

Install the isolated PostgreSQL test dependencies once per environment:

```powershell
python -m pip install -r tools\requirements-postgresql.txt
```

Run only the PostgreSQL contract:

```powershell
python -m unittest tools.test_postgresql_runtime -v
```

Run every generator test:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```
