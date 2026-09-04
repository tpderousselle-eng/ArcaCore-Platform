# Stabilization 25.4: Docker and Compose production validation

This contract generates a representative ArcaCore application, its Dockerfile,
and its Compose configuration into one isolated temporary project. It never
edits the repository `backend/` directory or repairs generated source.

The normal test path validates the real generated files, build inputs,
deterministic replacement, PostgreSQL connection wiring, database-backed health
endpoint, persistent volume, and external secret references. The opt-in runtime
path additionally uses Docker Compose v2 to:

1. validate the Compose configuration;
2. build the generated API image;
3. start the generated API and PostgreSQL;
4. verify PostgreSQL connectivity and application health;
5. call generated create and read endpoints;
6. restart the API and verify recovery;
7. stop and recreate the project without deleting its volume;
8. verify the created record persisted;
9. inspect image history for the random runtime password; and
10. remove the containers, network, image, and volume cleanly.

Docker execution is explicit because it builds images and starts local
containers. With Docker Desktop running, use PowerShell from the repository
root:

```powershell
$env:ARCACORE_RUN_DOCKER_TESTS = "1"
python -m unittest tools.test_docker_compose_runtime -v
Remove-Item Env:ARCACORE_RUN_DOCKER_TESTS
```

When the environment variable is absent, the real container method is reported
as skipped while every non-container validation still runs. When it is set but
the Docker daemon or Compose v2 is unavailable, the contract fails clearly.
