"""Generate Kubernetes resources without changing backend source."""

from tools.core.engine import PROJECT_ROOT, render_template
from tools.core.kubernetes_parser import (
    KubernetesDefinition,
    validate_kubernetes_definition,
)


def generate_kubernetes(definition: KubernetesDefinition | None = None):
    definition = definition or KubernetesDefinition()
    validate_kubernetes_definition(definition)
    output_path = PROJECT_ROOT / "kubernetes" / "arcacore.yaml"
    render_template(
        template_name="kubernetes.j2",
        output_path=output_path,
        name=definition.name,
        namespace=definition.namespace,
        api_image=definition.api_image,
        api_port=definition.api_port,
        service_port=definition.service_port,
        replicas=definition.replicas,
        database_image=definition.database_image,
        database_port=definition.database_port,
        storage_size=definition.storage_size,
        secret_name=definition.secret_name,
    )
    return output_path
