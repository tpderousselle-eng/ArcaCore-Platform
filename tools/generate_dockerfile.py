"""Generate a production-oriented Dockerfile without changing backend source."""

from tools.core.dockerfile_parser import (
    DockerfileDefinition,
    python_image_reference,
    validate_dockerfile_definition,
)
from tools.core.engine import PROJECT_ROOT, render_template


def generate_dockerfile(definition: DockerfileDefinition | None = None):
    definition = definition or DockerfileDefinition()
    validate_dockerfile_definition(definition)
    output_path = PROJECT_ROOT / "Dockerfile"
    render_template(
        template_name="Dockerfile.j2",
        output_path=output_path,
        python_image=python_image_reference(definition.python_version),
        port=definition.port,
        app=definition.app,
        requirements=definition.requirements,
        source=definition.source,
    )
    return output_path
