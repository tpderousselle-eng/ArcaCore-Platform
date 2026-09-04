# Stabilization 25: Production validation

Stabilization begins after Sprint 24.4 Health Checks, locally tested, committed,
and pushed to GitHub main as `b5bbe7b`.

| Increment | Status |
| --- | --- |
| 25.1 Golden Application Generation Matrix | Complete and pushed to GitHub main as `60cba7c`; 8 dedicated and 315 discovery tests passed |
| 25.2 Generated Application Runtime Test | Complete and pushed to GitHub main as `7aff42b`; 10 dedicated and 325 discovery tests passed |
| 25.3 Real PostgreSQL Integration Test | Complete and pushed to GitHub main as `bd0d3b0`; 11 dedicated and 336 discovery tests passed |
| 25.4 Docker and Compose Production Validation | Complete and pushed to GitHub main as `d316255`; 7 dedicated and 343 discovery tests passed with real Docker execution |
| 25.5 Kubernetes and Health Validation | Complete and pushed to GitHub main as `a62e8e1`; 11 dedicated and 354 discovery tests passed |
| 25.6 Failure Injection and Regression Hardening | Implemented; 11 dedicated and 365 discovery tests passed, with the established opt-in Docker test skipped |
| 25.7 and later | Not started |

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

Local Docker execution confirmed API and PostgreSQL health, database queries,
generated CRUD operations, API restart, and PostgreSQL persistence. The final
contract passed all 7 dedicated tests and all 343 discovery tests before commit
`d316255` was pushed to GitHub main.

## 25.5 scope

The Kubernetes and health contract generates the real Sprint 24 Dockerfile and
seven-resource Kubernetes manifest in an isolated temporary project. Every YAML
document is safely parsed and validated against strict bundled Kubernetes 1.36
schemas without requiring a live cluster.

The semantic contract verifies Deployment selectors, labels, image, resources,
replicas, and container port; API Service routing; PostgreSQL StatefulSet,
governing headless Service, and persistent volume claim wiring; ConfigMap and
Secret references without embedded credentials; Dockerfile and container-port
alignment; responding `/health` behavior; valid startup, readiness, and
liveness probes; DNS-safe names; configurable replicas; and byte-identical
regeneration. When `kubectl` is installed, a cluster-free client dry-run is also
executed over the complete generated manifest.

Validation identified and corrected the PostgreSQL Service configuration so the
Service named by the StatefulSet is headless and can govern its stable network
identity. All changes remain inside `tools/`, and the repository `backend/`
tree is checked byte-for-byte throughout the contract.

## 25.6 scope

Failure injection now covers malformed DSL and parameter syntax; unsupported,
duplicate, and conflicting field modifiers; relationship, index, constraint,
validator, computed, hybrid, encryption, audit, version, and deployment metadata
failures; interrupted multi-file generation; registry persistence failure;
failed regeneration over valid output; atomic replacement failure; and repeated
invalid operations.

Module generation snapshots all five generated layers and registry metadata
before writing. Any exception, including interruption, restores prior files,
removes newly created outputs and empty directories, and re-raises the original
actionable error. Template output, rollback restoration, and registry metadata
use same-directory temporary files followed by atomic replacement, with cleanup
guaranteed when rendering or replacement fails.

## Verification

Install the dedicated Kubernetes schema-validation dependencies:

```powershell
python -m pip install -r tools\requirements-kubernetes.txt
```

Run the dedicated 25.5 Kubernetes and health contract:

```powershell
python -m unittest tools.test_kubernetes_validation -v
```

Run the dedicated 25.6 failure-injection contract:

```powershell
python -m unittest tools.test_failure_injection -v
```

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

Stop after delivering Stabilization 25.6. Wait for the user's local test,
commit, and push result, and remain paused until the user explicitly asks to
continue.
