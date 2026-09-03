# Sprint 24: Deployment generation

Sprint 24 begins after Sprint 23.4 Version Columns, locally tested, committed,
and pushed to GitHub main as `b983e6b`.

| Feature | Status |
| --- | --- |
| Dockerfile generation | Sprint 24.1: implemented; 12 dedicated and 267 discovery tests passed here; replacement ZIP prepared for local verification |
| Docker Compose generation | Pending |
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

Stop after delivering Sprint 24.1. Wait for the user's local test, commit, and
push result before starting Docker Compose or any later feature.
