# Kubernetes generation

Sprint 24.3 adds deterministic Kubernetes resource generation for the ArcaCore
API and PostgreSQL without changing application source.

## Command

Generate `kubernetes/arcacore.yaml` from the project root:

```powershell
python -m tools kubernetes
```

The defaults are:

| Setting | Default |
| --- | --- |
| Resource prefix | `arcacore` |
| Namespace | `arcacore` |
| API image | `arcacore-api:latest` |
| API container port | `8000` |
| API service port | `80` |
| API replicas | `2` |
| PostgreSQL image | `postgres:16` |
| PostgreSQL port | `5432` |
| PostgreSQL storage | `10Gi` |
| Existing Secret | `arcacore-secrets` |

All settings are configurable and may appear once in any order:

```powershell
python -m tools kubernetes --name arca-api --namespace production --api-image ghcr.io/example/arca-api:1.0.0 --api-port 8000 --service-port 80 --replicas 3 --database-image postgres:17-alpine --database-port 5432 --storage-size 20Gi --secret-name arca-secrets
```

Names must be valid lowercase Kubernetes DNS labels. The resource prefix is
limited to 47 characters so every generated suffixed name remains within
Kubernetes's 63-character limit. Ports, replica counts, container image
references, and storage quantities are validated before output is written.

## Generated resources

The single multi-document manifest contains:

- the selected Namespace;
- a PostgreSQL ConfigMap;
- an API Deployment and ClusterIP Service;
- a PostgreSQL StatefulSet and ClusterIP Service; and
- a PostgreSQL PersistentVolumeClaim.

Both workloads include resource requests and limits. PostgreSQL runs as one
StatefulSet replica with persistent storage. Regeneration completely and
deterministically replaces `kubernetes/arcacore.yaml`.

## Required Secret

The generator never writes credentials. Create the referenced Secret before
applying the manifest. The database URL must use the generated PostgreSQL
Service name as its hostname:

```powershell
kubectl create namespace arcacore
kubectl create secret generic arcacore-secrets --namespace arcacore --from-literal=database-url="postgresql+psycopg2://arcacore:REPLACE_ME@arcacore-postgres:5432/arcacore" --from-literal=postgres-password="REPLACE_ME"
```

For customized names or namespaces, update the command to match the generator
options. Do not commit real secret values.

## Apply

```powershell
kubectl apply -f kubernetes/arcacore.yaml
```

## Scope boundary

Sprint 24.3 does not add health, readiness, or startup probes; ingress; TLS;
autoscaling; managed databases; migration jobs; secret stores; Redis; image
building or publishing; or CI/CD. Health checks remain the next separate
roadmap feature.

## Local verification

Run the dedicated smoke suite:

```powershell
python -m unittest tools.test_kubernetes -v
```

Run every tools test:

```powershell
python -m unittest discover -s tools -p "test_*.py" -v
```
