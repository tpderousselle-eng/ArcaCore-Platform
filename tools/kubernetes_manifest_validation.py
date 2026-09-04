"""Validate generated Kubernetes manifests without requiring a live cluster."""

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

import yaml
from kubernetes_validate import validate


KUBERNETES_SCHEMA_VERSION = "1.36.0"


@dataclass(frozen=True)
class ValidatedManifest:
    """Parsed resources and the schema version selected for each resource."""

    documents: tuple[dict, ...]
    schema_versions: tuple[str, ...]

    def resource(self, kind: str, name: str) -> dict:
        matches = tuple(
            document
            for document in self.documents
            if document.get("kind") == kind
            and document.get("metadata", {}).get("name") == name
        )
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one {kind} named {name}, found {len(matches)}."
            )
        return matches[0]


def load_validated_manifest(
    path: Path,
    schema_version: str = KUBERNETES_SCHEMA_VERSION,
) -> ValidatedManifest:
    """Load every YAML document and validate it against strict bundled schemas."""

    with path.open("r", encoding="utf-8") as source:
        loaded = tuple(yaml.safe_load_all(source))
    if not loaded:
        raise ValueError("The Kubernetes manifest does not contain any resources.")
    if any(not isinstance(document, dict) for document in loaded):
        raise ValueError("Every Kubernetes YAML document must be an object.")
    versions = tuple(
        validate(document, schema_version, strict=True) for document in loaded
    )
    return ValidatedManifest(documents=loaded, schema_versions=versions)


def kubectl_client_dry_run(path: Path) -> tuple[str, ...] | None:
    """Use kubectl client dry-run when its discovery environment is usable."""

    executable = shutil.which("kubectl")
    if executable is None:
        return None
    availability_checks = (
        ([executable, "config", "current-context"], 10),
        (
            [
                executable,
                "get",
                "--raw=/api",
                "--request-timeout=5s",
            ],
            10,
        ),
    )
    for command, timeout in availability_checks:
        try:
            check = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if check.returncode != 0 or not check.stdout.strip():
            return None
    try:
        completed = subprocess.run(
            [
                executable,
                "create",
                "--dry-run=client",
                "--validate=false",
                "--filename",
                str(path),
                "--output",
                "name",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"kubectl client dry-run could not complete: {error}") from error
    if completed.returncode != 0:
        output = "\n".join(
            part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
        )
        raise RuntimeError(f"kubectl client dry-run failed:\n{output}")
    return tuple(line for line in completed.stdout.splitlines() if line)
