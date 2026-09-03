"""Parse and validate Dockerfile generator options."""

from dataclasses import dataclass
import re

_APP_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*" r":[A-Za-z_][A-Za-z0-9_]*"
)
_PATH_PART_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")
_PYTHON_PATTERN = re.compile(r"3\.[0-9]+(?:\.[0-9]+)?")


@dataclass(frozen=True)
class DockerfileDefinition:
    python_version: str = "3.13"
    port: int = 8000
    app: str = "backend.main:app"
    requirements: str = "backend/requirements.txt"
    source: str = "backend"

    def __post_init__(self):
        validate_dockerfile_definition(self)


def normalize_relative_path(value: str, option: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{option} must be a relative project path.")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or len(normalized) > 240
        or any(part in {"", ".", ".."} for part in parts)
        or not all(_PATH_PART_PATTERN.fullmatch(part) for part in parts)
    ):
        raise ValueError(f"{option} must be a safe relative project path.")
    return normalized


def validate_dockerfile_definition(definition):
    if not isinstance(definition, DockerfileDefinition):
        raise ValueError("Dockerfile metadata must be a DockerfileDefinition.")
    if not isinstance(definition.python_version, str) or not _PYTHON_PATTERN.fullmatch(
        definition.python_version
    ):
        raise ValueError("--python-version must be a Python 3 version such as 3.13.")
    if isinstance(definition.port, bool) or not isinstance(definition.port, int):
        raise ValueError("--port must be an integer from 1 through 65535.")
    if not 1 <= definition.port <= 65535:
        raise ValueError("--port must be an integer from 1 through 65535.")
    if not isinstance(definition.app, str) or not _APP_PATTERN.fullmatch(
        definition.app
    ):
        raise ValueError("--app must use dotted.module:attribute form.")
    requirements = normalize_relative_path(definition.requirements, "--requirements")
    source = normalize_relative_path(definition.source, "--source")
    if not requirements.endswith(".txt"):
        raise ValueError("--requirements must point to a .txt requirements file.")
    object.__setattr__(definition, "requirements", requirements)
    object.__setattr__(definition, "source", source)


def parse_dockerfile_options(arguments: list[str]) -> DockerfileDefinition:
    options = {
        "--python-version": "python_version",
        "--port": "port",
        "--app": "app",
        "--requirements": "requirements",
        "--source": "source",
    }
    values = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        attribute = options.get(option)
        if attribute is None:
            raise ValueError(f"Unknown dockerfile option: {option}")
        if attribute in values:
            raise ValueError(f"{option} can only be specified once.")
        index += 1
        if index >= len(arguments) or arguments[index].startswith("--"):
            raise ValueError(f"{option} requires a value.")
        value = arguments[index]
        if attribute == "port":
            try:
                value = int(value)
            except ValueError as error:
                raise ValueError(
                    "--port must be an integer from 1 through 65535."
                ) from error
        values[attribute] = value
        index += 1
    return DockerfileDefinition(**values)
