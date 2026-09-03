# Docker Compose generation

Sprint 24.2 adds deterministic Docker Compose generation for the ArcaCore API
and PostgreSQL. It composes the Dockerfile produced by Sprint 24.1 without
changing application source.

## Command

Generate `docker-compose.yml` from the project root:

```powershell
python -m tools dockerfile
python -m tools compose
```

The Compose generator requires the configured Dockerfile to exist before it
writes output. The defaults are:

| Setting | Default |
| --- | --- |
| Project name | `arcacore` |
| Published API port | `8000` |
| API container port | `8000` |
| Published PostgreSQL port | `5432` |
| PostgreSQL image | `postgres:16` |
| Environment file | `.env` |
| Dockerfile | `Dockerfile` |

All settings are configurable and may appear once in any order:

```powershell
python -m tools compose --project-name arca_core --api-port 9000 --container-port 8000 --database-port 5544 --database-image postgres:17-alpine --env-file config/runtime.env --dockerfile deploy/Dockerfile.prod
```

Ports must be between 1 and 65535. Paths are normalized to forward slashes and
must be safe relative project paths. Invalid options and a missing Dockerfile
fail before `docker-compose.yml` is written.

## Generated services

The `api` service builds the configured Dockerfile, loads the configured
environment file, publishes the API port, and depends on the `postgres`
service. Its internal `DATABASE_URL` uses the Compose service hostname
`postgres` rather than localhost. It checks the existing `/health` endpoint and
starts only after PostgreSQL reports healthy.

The `postgres` service uses the selected image, publishes its port, and stores
database files in the named `postgres_data` volume. Its user and database
default to `arcacore`. `POSTGRES_PASSWORD` is required through environment
interpolation and is never embedded in generated source. PostgreSQL health is
checked with `pg_isready` and runtime environment values.

Add these values to the selected environment file before starting Compose:

```dotenv
POSTGRES_USER=arcacore
POSTGRES_PASSWORD=replace-with-a-strong-password
POSTGRES_DB=arcacore
SECRET_KEY=replace-with-a-strong-application-secret
```

Do not commit the environment file.

## Run

```powershell
docker compose up --build
```

Regeneration completely and deterministically replaces the root
`docker-compose.yml`. It never writes inside `backend/`.

## Scope boundary

The Compose generator does not add Redis, Kubernetes, database migrations,
secret stores, TLS, external networks, replicas, image publishing, or CI/CD.

## Local verification

Run the dedicated smoke suite:

```powershell
python -m unittest tools.test_compose -v
```

Run every tools test:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```
