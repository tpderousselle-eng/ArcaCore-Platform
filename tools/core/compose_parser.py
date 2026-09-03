"""Parse and validate Docker Compose generator options."""

from dataclasses import dataclass
import re

from tools.core.dockerfile_parser import normalize_relative_path

_IMAGE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9./:_@-]*")
_PROJECT_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")


@dataclass(frozen=True)
class ComposeDefinition:
    project_name: str = "arcacore"
    api_port: int = 8000
    container_port: int = 8000
    database_port: int = 5432
    database_image: str = "postgres:16"
    env_file: str = ".env"
    dockerfile: str = "Dockerfile"

    def __post_init__(self):
        validate_compose_definition(self)


def _validate_port(value, option: str):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError(f"{option} must be an integer from 1 through 65535.")


def validate_compose_definition(definition):
    if not isinstance(definition, ComposeDefinition):
        raise ValueError("Compose metadata must be a ComposeDefinition.")
    if not isinstance(definition.project_name, str) or not _PROJECT_PATTERN.fullmatch(
        definition.project_name
    ):
        raise ValueError(
            "--project-name must start with a lowercase letter or digit and use "
            "only lowercase letters, digits, hyphens, or underscores."
        )
    _validate_port(definition.api_port, "--api-port")
    _validate_port(definition.container_port, "--container-port")
    _validate_port(definition.database_port, "--database-port")
    if not isinstance(definition.database_image, str) or not _IMAGE_PATTERN.fullmatch(
        definition.database_image
    ):
        raise ValueError("--database-image must be a safe container image reference.")
    env_file = normalize_relative_path(definition.env_file, "--env-file")
    dockerfile = normalize_relative_path(definition.dockerfile, "--dockerfile")
    object.__setattr__(definition, "env_file", env_file)
    object.__setattr__(definition, "dockerfile", dockerfile)


def parse_compose_options(arguments: list[str]) -> ComposeDefinition:
    options = {
        "--project-name": "project_name",
        "--api-port": "api_port",
        "--container-port": "container_port",
        "--database-port": "database_port",
        "--database-image": "database_image",
        "--env-file": "env_file",
        "--dockerfile": "dockerfile",
    }
    port_options = {"api_port", "container_port", "database_port"}
    values = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        attribute = options.get(option)
        if attribute is None:
            raise ValueError(f"Unknown compose option: {option}")
        if attribute in values:
            raise ValueError(f"{option} can only be specified once.")
        index += 1
        if index >= len(arguments) or arguments[index].startswith("--"):
            raise ValueError(f"{option} requires a value.")
        value = arguments[index]
        if attribute in port_options:
            try:
                value = int(value)
            except ValueError as error:
                raise ValueError(
                    f"{option} must be an integer from 1 through 65535."
                ) from error
        values[attribute] = value
        index += 1
    return ComposeDefinition(**values)
