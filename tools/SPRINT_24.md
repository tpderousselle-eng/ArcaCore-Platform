# Sprint 24: Deployment generation

Sprint 24 begins after Sprint 23.4 Version Columns, locally tested, committed,
and pushed to GitHub main as `b983e6b`.

| Feature | Status |
| --- | --- |
| Dockerfile generation | Sprint 24.1: implemented, locally tested, committed, and pushed |
| Docker Compose generation | Sprint 24.2: implemented, locally tested, committed, and pushed |
| Kubernetes generation | Sprint 24.3: implemented, locally tested, committed, and pushed |
| Health checks | Sprint 24.4: implemented; 13 dedicated and 307 discovery tests passed here; replacement ZIP prepared for local verification |

Sprint 24.1 adds `python -m tools dockerfile`, a deterministic generator for a
root application Dockerfile. The default output targets Python 3.13,
`backend.main:app`, `backend/requirements.txt`, and port 8000. Validated command
options can customize the Python version, port, ASGI target, requirements file,
and source directory without changing backend source.

The generated container installs requirements before source for dependency
layer reuse, copies only the configured source directory, runs as the
unprivileged `arcacore` user, and starts Uvicorn through Python's module entry
point. Regeneration is a complete deterministic replacement.

The 12 new tests cover defaults, configurable options, order independence,
Windows path normalization, invalid metadata, invalid CLI input, direct
generator preflight, real isolated generation, backend preservation,
deterministic replacement, security and layer-order invariants, CLI generation,
and help output.

See DOCKERFILE_GENERATION.md for the complete Sprint 24.1 command contract,
generated output, build instructions, and scope boundary.

Sprint 24.2 adds `python -m tools compose`, a deterministic generator for the
root `docker-compose.yml`. The generated project contains an API service built
from the Sprint 24.1 Dockerfile and a PostgreSQL service with persistent named
storage. It uses the Compose service hostname for the application's database
URL and requires the database password through environment interpolation
instead of embedding credentials.

Validated options configure the project name, published and container API
ports, published database port, PostgreSQL image, environment file, and
Dockerfile. Unsafe values and a missing Dockerfile fail before output is
written. Regeneration is a complete replacement and leaves backend source
untouched.

The 13 new tests cover defaults, custom option order, Windows path
normalization, invalid metadata, invalid CLI input, direct generator preflight,
the Dockerfile prerequisite, real isolated generation, backend preservation,
deterministic replacement, API/PostgreSQL/environment/volume output, secret and
scope boundaries, CLI generation, and help output.

See COMPOSE_GENERATION.md for the complete Sprint 24.2 command contract,
environment requirements, service topology, and scope boundary.

Sprint 24.3 adds `python -m tools kubernetes`, a deterministic generator for
`kubernetes/arcacore.yaml`. The multi-document manifest contains a Namespace,
PostgreSQL ConfigMap, API Deployment and Service, PostgreSQL StatefulSet and
Service, and a PersistentVolumeClaim. Workloads include fixed resource requests
and limits, while PostgreSQL uses persistent storage.

Validated options configure resource names, namespace, images, ports, API
replicas, storage, and the name of an existing Kubernetes Secret. The generated
manifest references that Secret for the database URL and PostgreSQL password;
it never writes credentials. Regeneration is a complete replacement and leaves
backend source untouched.

The 14 new tests cover defaults, custom option order, invalid metadata and CLI
input, direct generator preflight, real isolated generation, backend
preservation, deterministic replacement, resource kinds, API/PostgreSQL and
storage contracts, secret safety, scope boundaries, CLI generation, and help
output.

See KUBERNETES_GENERATION.md for the complete Sprint 24.3 command contract,
Secret setup, generated resources, apply instructions, and scope boundary.

Sprint 24.4 adds health checks to all three deployment outputs without changing
backend source. The Dockerfile and Compose API service request the existing
`/health` endpoint with Python's standard library. Compose checks PostgreSQL
with `pg_isready` and waits for database health before starting the API.

The Kubernetes API Deployment includes startup, readiness, and liveness HTTP
probes. Its PostgreSQL StatefulSet includes readiness and liveness `pg_isready`
probes. Timeouts, intervals, start periods, and retry or failure thresholds are
explicit and deterministic, and no credentials are embedded.

The 13 new tests cover the Docker endpoint, configured ports, standard-library
execution, Compose API and PostgreSQL checks, healthy dependency ordering,
runtime environment escaping, Kubernetes probe types and named ports,
PostgreSQL commands, credential safety, and backend preservation.

See HEALTH_CHECKS.md for the complete Sprint 24.4 behavior, regeneration
commands, and scope boundary.

Stop after delivering Sprint 24.4. Wait for the user's local test, commit, and
push result before starting any later sprint or feature.
