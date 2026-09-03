# Sprint 24: Deployment generation

Sprint 24 begins after Sprint 23.4 Version Columns, locally tested, committed,
and pushed to GitHub main as `b983e6b`.

| Feature | Status |
| --- | --- |
| Dockerfile generation | Sprint 24.1: implemented, locally tested, committed, and pushed |
| Docker Compose generation | Sprint 24.2: implemented; 13 dedicated and 280 discovery tests passed here; replacement ZIP prepared for local verification |
| Kubernetes generation | Pending |
| Health checks | Pending |

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

Stop after delivering Sprint 24.2. Wait for the user's local test, commit, and
push result before starting Kubernetes or any later feature.
