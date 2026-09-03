# Dockerfile generation

Sprint 24.1 begins ArcaCore deployment generation with one deterministic,
production-oriented Dockerfile. It adds a generator command; it does not alter
backend source or generate Compose, Kubernetes, or health-check configuration.

## Command

Generate the default Dockerfile from the project root:

```powershell
python -m tools dockerfile
```

The defaults target the current ArcaCore FastAPI application:

| Setting | Default |
| --- | --- |
| Python | `3.13` |
| Container port | `8000` |
| ASGI application | `backend.main:app` |
| Requirements | `backend/requirements.txt` |
| Source directory | `backend` |

All settings are configurable:

```powershell
python -m tools dockerfile --python-version 3.12 --port 9000 --app src.main:app --requirements config/runtime.txt --source src
```

Every option may appear once in any order. Paths are normalized to Docker's
forward-slash form and must remain safe, relative project paths. The ASGI target
must use `dotted.module:attribute` form, and ports must be between 1 and 65535.
Invalid input fails before the Dockerfile is written.

## Generated contract

The generated Dockerfile:

- uses the selected official `python:<version>-slim` base image;
- configures unbuffered Python and disables bytecode and pip caching;
- copies and installs the requirements file before application source so normal
  source edits can reuse the dependency layer;
- copies only the configured source directory;
- runs the application as the unprivileged `arcacore` user;
- exposes the configured port; and
- starts the selected ASGI application through Uvicorn's Python module entry
  point.

Running the command again completely and deterministically replaces the root
`Dockerfile`. It never writes inside `backend/`.

## Scope boundary

Sprint 24.1 does not generate `.dockerignore`, Docker Compose services,
Kubernetes resources, health checks, database migrations, secrets, environment
values, TLS, registries, CI/CD workflows, or image publishing. Those deployment
concerns require their own roadmap features.

## Build and run

After generation, Docker users can build and run the application from the
project root:

```powershell
docker build -t arcacore .
docker run --rm -p 8000:8000 --env-file .env arcacore
```

The `.env` file is supplied at runtime and is not copied or embedded by the
generator.

## Local verification

Run the dedicated smoke suite:

```powershell
python -m unittest tools.test_dockerfile -v
```

Run every tools test:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```
