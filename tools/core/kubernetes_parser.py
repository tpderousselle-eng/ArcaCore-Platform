"""Parse and validate Kubernetes generator options."""

from dataclasses import dataclass
import re

_DNS_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_IMAGE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9./:_@-]*")
_STORAGE_PATTERN = re.compile(r"[1-9][0-9]*(?:Mi|Gi|Ti)")


@dataclass(frozen=True)
class KubernetesDefinition:
    name: str = "arcacore"
    namespace: str = "arcacore"
    api_image: str = "arcacore-api:latest"
    api_port: int = 8000
    service_port: int = 80
    replicas: int = 2
    database_image: str = "postgres:16"
    database_port: int = 5432
    storage_size: str = "10Gi"
    secret_name: str = "arcacore-secrets"

    def __post_init__(self):
        validate_kubernetes_definition(self)


def _validate_dns_label(value, option: str, max_length: int = 63):
    if (
        not isinstance(value, str)
        or len(value) > max_length
        or not _DNS_LABEL_PATTERN.fullmatch(value)
    ):
        raise ValueError(
            f"{option} must be a lowercase Kubernetes DNS label of 1 to {max_length} "
            "letters, digits, or hyphens."
        )


def _validate_port(value, option: str):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError(f"{option} must be an integer from 1 through 65535.")


def _validate_image(value, option: str):
    if not isinstance(value, str) or not _IMAGE_PATTERN.fullmatch(value):
        raise ValueError(f"{option} must be a safe container image reference.")


def validate_kubernetes_definition(definition):
    if not isinstance(definition, KubernetesDefinition):
        raise ValueError("Kubernetes metadata must be a KubernetesDefinition.")
    _validate_dns_label(definition.name, "--name", max_length=47)
    _validate_dns_label(definition.namespace, "--namespace")
    _validate_dns_label(definition.secret_name, "--secret-name")
    _validate_image(definition.api_image, "--api-image")
    _validate_image(definition.database_image, "--database-image")
    _validate_port(definition.api_port, "--api-port")
    _validate_port(definition.service_port, "--service-port")
    _validate_port(definition.database_port, "--database-port")
    if (
        isinstance(definition.replicas, bool)
        or not isinstance(definition.replicas, int)
        or not 1 <= definition.replicas <= 100
    ):
        raise ValueError("--replicas must be an integer from 1 through 100.")
    if not isinstance(definition.storage_size, str) or not _STORAGE_PATTERN.fullmatch(
        definition.storage_size
    ):
        raise ValueError("--storage-size must use a positive Mi, Gi, or Ti quantity.")


def parse_kubernetes_options(arguments: list[str]) -> KubernetesDefinition:
    options = {
        "--name": "name",
        "--namespace": "namespace",
        "--api-image": "api_image",
        "--api-port": "api_port",
        "--service-port": "service_port",
        "--replicas": "replicas",
        "--database-image": "database_image",
        "--database-port": "database_port",
        "--storage-size": "storage_size",
        "--secret-name": "secret_name",
    }
    integer_options = {"api_port", "service_port", "replicas", "database_port"}
    values = {}
    index = 0
    while index < len(arguments):
        option = arguments[index]
        attribute = options.get(option)
        if attribute is None:
            raise ValueError(f"Unknown kubernetes option: {option}")
        if attribute in values:
            raise ValueError(f"{option} can only be specified once.")
        index += 1
        if index >= len(arguments) or arguments[index].startswith("--"):
            raise ValueError(f"{option} requires a value.")
        value = arguments[index]
        if attribute in integer_options:
            try:
                value = int(value)
            except ValueError as error:
                raise ValueError(f"{option} requires an integer value.") from error
        values[attribute] = value
        index += 1
    return KubernetesDefinition(**values)
