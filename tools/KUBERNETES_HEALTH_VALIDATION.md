# Stabilization 25.5: Kubernetes and health validation

This contract validates the real Sprint 24 Kubernetes output as deployable
infrastructure without requiring a live production cluster. It generates a
Dockerfile and seven-resource Kubernetes manifest in an isolated temporary
project root and never edits the repository `backend/` directory.

Every YAML document is loaded with safe YAML parsing and checked against the
strict bundled Kubernetes 1.36 schema. The semantic checks then verify:

- Deployment selectors, pod labels, image, replicas, resources, and port;
- API Service selectors, service port, and named target port;
- PostgreSQL StatefulSet, headless dependency name, Service, and persistent
  volume claim wiring;
- ConfigMap and Secret references without an embedded Secret resource or
  credential value;
- Dockerfile exposure, command port, and health-check alignment;
- startup, readiness, and liveness probes against a responding `/health`
  application route;
- DNS-safe resource and namespace names;
- configurable API replicas with a single PostgreSQL replica; and
- byte-identical deterministic regeneration.

If `kubectl` is installed, the contract also runs a cluster-free client dry-run
over the complete generated manifest. A live Kubernetes cluster is not needed.

## Verification

Install the validation dependencies:

```powershell
python -m pip install -r tools\requirements-kubernetes.txt
```

Run the dedicated contract:

```powershell
python -m unittest tools.test_kubernetes_validation -v
```

Run the complete tools suite:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```
