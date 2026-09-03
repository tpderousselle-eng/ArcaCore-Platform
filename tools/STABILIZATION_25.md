# Stabilization 25: Production validation

Stabilization begins after Sprint 24.4 Health Checks, locally tested, committed,
and pushed to GitHub main as `b5bbe7b`.

| Increment | Status |
| --- | --- |
| 25.1 Golden Application Generation Matrix | Complete and pushed to GitHub main as `60cba7c`; 8 dedicated and 315 discovery tests passed |
| 25.2 Generated Application Runtime Test | Implemented; 10 dedicated and 325 discovery tests passed here; replacement ZIP prepared for local verification |
| 25.3 and later | Not started |

## 25.1 scope

The golden matrix generates five representative applications through the real
module pipeline:

1. Simple CRUD SaaS
2. E-commerce Product/Order
3. CRM Customer/Contact
4. Multi-tenant Workspace/User
5. An advanced combination of relationships, constraints, indexes, validation,
   computed and hybrid properties, encrypted fields, audit fields, optimistic
   versioning, and soft deletion

Every application is generated in its own temporary project root. The suite
checks all five generated layers, Python syntax, isolated imports, class and
module naming, registry completeness, schema/model/layer agreement,
deterministic complete replacement, module-order independence, pre-write
failure for invalid combinations, and cross-scenario isolation.

The canonical definitions live in `golden_matrix.py`; the executable contract
lives in `test_golden_matrix.py`. Neither the matrix nor its tests write to the
repository's `backend/` directory.

## 25.2 scope

The generated runtime test creates a representative two-module application in
an isolated temporary project root through the real module pipeline. The
fixture supplies only the application-owned package, database-session, and
FastAPI composition infrastructure that the generators intentionally do not
own. It never edits generated output or the repository's `backend/` directory.

The runtime contract proves that generated models, schemas, CRUD classes,
services, and routers work together under real SQLAlchemy, Pydantic, FastAPI,
SQLite, and `TestClient` execution. It covers module imports, metadata and table
creation, router registration, OpenAPI generation, create/read/list/update,
soft and hard deletion, restore, validation responses, foreign-key
serialization and ORM navigation, computed read-only values, audit actors,
optimistic version increments, and preservation of generated source during
execution.

The executable contract lives in `test_generated_runtime.py`. Generator-owned
CRUD, service, and router templates now provide the runtime operations required
by that contract.

## Verification

Run the dedicated 25.2 runtime contract:

```powershell
python -m unittest tools.test_generated_runtime -v
```

Run the dedicated 25.1 matrix:

```powershell
python -m unittest tools.test_golden_matrix -v
```

Run the complete generator suite:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```

Stop after delivering Stabilization 25.2. Wait for the user's local test,
commit, and push result before starting 25.3 or any later increment.
