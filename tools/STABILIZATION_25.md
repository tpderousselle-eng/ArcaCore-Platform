# Stabilization 25: Production validation

Stabilization begins after Sprint 24.4 Health Checks, locally tested, committed,
and pushed to GitHub main as `b5bbe7b`.

| Increment | Status |
| --- | --- |
| 25.1 Golden Application Generation Matrix | Complete and pushed to GitHub main as `60cba7c`; 8 dedicated and 315 discovery tests passed |
| 25.2 Generated Application Runtime Test | Complete and pushed to GitHub main as `7aff42b`; 10 dedicated and 325 discovery tests passed |
| 25.3 Real PostgreSQL Integration Test | Complete and pushed to GitHub main as `bd0d3b0`; 11 dedicated and 336 discovery tests passed |
| 25.4 Docker and Compose Production Validation | Implemented; 7 dedicated tests ran (6 passed, 1 skipped) and 343 discovery tests ran (342 passed, 1 skipped); real Docker execution awaits local verification |
| 25.5 and later | Not started |

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

## 25.3 scope

The PostgreSQL integration contract generates Account, Role, and Record models
through the normal pipeline in a temporary application root, then creates and
executes their schema against a fresh isolated PostgreSQL server. It never uses
SQLite as a substitute, writes generated files into the repository backend, or
repairs generated output before execution.

The contract proves native PostgreSQL UUID, Numeric, JSON, ARRAY, and enum
round trips; table creation; foreign keys; unique and check constraints;
composite, partial, and expression indexes; computed columns; encrypted field
storage; one-to-many and many-to-many persistence; database cascades with
passive deletes; soft deletion and restore; audit actors; and optimistic
version conflict detection. Generated Python sources must remain byte-for-byte
unchanged throughout the run.

The normal developer path uses `pgembed` for an isolated local PostgreSQL
server without Docker. Restricted root-only environments can supply a PGlite
socket server through `ARCACORE_PGLITE_SERVER`; both paths use the PostgreSQL
wire protocol and PostgreSQL behavior remains authoritative.

## 25.4 scope

The Docker and Compose production contract generates a representative two-model
application through the normal five-layer pipeline in a temporary project root.
It then generates the real Sprint 24 Dockerfile and Compose configuration for
that application. It never writes generated output into the repository
`backend/` directory or repairs generator-owned source before execution.

The always-on checks prove that every generated build input exists, generated
Python compiles, deployment generation is byte-for-byte deterministic, the API
and PostgreSQL services are connected through an external runtime secret, the
health endpoint probes the database, and the named PostgreSQL volume is present.

The opt-in Docker contract validates the Compose model, builds the generated API
image, starts API and PostgreSQL containers, checks database connectivity and
application boot, calls generated endpoints, verifies health and API restart,
recreates the environment without deleting its volume, and proves that a prior
record persisted. It also checks the random database password against generated
artifacts and image history, then removes containers, network, image, and volume
in a `finally` cleanup path.

This runner did not provide a Docker daemon, so the six always-on 25.4 tests
passed and the real container method was reported as one explicit skip. Setting
`ARCACORE_RUN_DOCKER_TESTS=1` makes missing Docker or Compose a test failure and
runs the full production contract when Docker Desktop is available.

## Verification

With Docker Desktop running, run the dedicated 25.4 production contract:

```powershell
$env:ARCACORE_RUN_DOCKER_TESTS = "1"
python -m unittest tools.test_docker_compose_runtime -v
Remove-Item Env:ARCACORE_RUN_DOCKER_TESTS
```

Install the dedicated PostgreSQL test dependencies:

```powershell
python -m pip install -r tools\requirements-postgresql.txt
```

Run the dedicated 25.3 PostgreSQL contract:

```powershell
python -m unittest tools.test_postgresql_runtime -v
```

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

Stop after delivering Stabilization 25.4. Wait for the user's local test,
commit, and push result, and remain paused until the user explicitly asks to
continue.
