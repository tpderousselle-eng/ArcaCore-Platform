"""Generate Docker Compose configuration without changing backend source."""

from tools.core.compose_parser import ComposeDefinition, validate_compose_definition
from tools.core.engine import PROJECT_ROOT, render_template


def generate_compose(definition: ComposeDefinition | None = None):
    definition = definition or ComposeDefinition()
    validate_compose_definition(definition)
    dockerfile_path = PROJECT_ROOT / definition.dockerfile
    if not dockerfile_path.is_file():
        raise FileNotFoundError(
            f"Dockerfile not found: {dockerfile_path}. "
            "Run python -m tools dockerfile first."
        )
    output_path = PROJECT_ROOT / "docker-compose.yml"
    render_template(
        template_name="compose.j2",
        output_path=output_path,
        project_name=definition.project_name,
        api_port=definition.api_port,
        container_port=definition.container_port,
        database_port=definition.database_port,
        database_image=definition.database_image,
        env_file=definition.env_file,
        dockerfile=definition.dockerfile,
    )
    return output_path
