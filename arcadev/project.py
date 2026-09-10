"""Canonical ArcaDev build-project representation for the IDEA stage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable


ARCADEV_PROJECT_SCHEMA = "arcadev.project"
ARCADEV_PROJECT_SCHEMA_VERSION = 1
MAX_PROJECT_BYTES = 1_000_000
MAX_COLLECTION_ITEMS = 256
MAX_ITEM_LENGTH = 512
MAX_REQUEST_LENGTH = 100_000

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_PROJECT_ID = re.compile(r"arcadev_[0-9a-f]{32}\Z")
_UTC_TIMESTAMP = re.compile(
    r"(?:19|20)\d\d-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r"T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\dZ\Z"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:password|passwd|secret|api[_ -]?key|access[_ -]?token|private[_ -]?key)"
    r"\s*(?:=|:)\s*[^\s,;]{4,}"
)
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")


class BuildStage(str, Enum):
    IDEA = "IDEA"
    PLAN = "PLAN"
    ARCHITECTURE = "ARCHITECTURE"
    MODELS = "MODELS"
    BACKEND = "BACKEND"
    FRONTEND = "FRONTEND"
    TESTS = "TESTS"
    SECURITY = "SECURITY"
    PREVIEW = "PREVIEW"
    DEPLOYMENT = "DEPLOYMENT"


class ProjectStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"ArcaDev project contains duplicate key: {key}")
        result[key] = value
    return result


def _require_exact_dict(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} has an invalid shape or unsupported fields.")
    return value


def _validate_text(value: Any, label: str, *, maximum: int, preserve: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    normalized = value if preserve else " ".join(value.split())
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{label} is empty or exceeds its size limit.")
    if any(ord(character) < 32 and character not in "\n\r\t" for character in normalized):
        raise ValueError(f"{label} contains control characters.")
    if _SECRET_ASSIGNMENT.search(normalized) or _PRIVATE_KEY.search(normalized):
        raise ValueError(f"{label} appears to contain a credential or secret value.")
    return normalized


def _validate_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{label} must be a canonical lowercase identifier.")
    return value


def _canonical_collection(values: Iterable[str], label: str, *, required: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{label} must be a collection of text values.")
    try:
        normalized = tuple(_validate_text(value, label, maximum=MAX_ITEM_LENGTH) for value in values)
    except TypeError as error:
        raise ValueError(f"{label} must be a collection of text values.") from error
    if required and not normalized:
        raise ValueError(f"{label} must not be empty.")
    if len(normalized) > MAX_COLLECTION_ITEMS:
        raise ValueError(f"{label} exceeds its item limit.")
    canonical = tuple(sorted(normalized, key=lambda value: (value.casefold(), value)))
    if len(set(canonical)) != len(canonical):
        raise ValueError(f"{label} contains duplicate values.")
    return canonical


@dataclass(frozen=True)
class ProjectMetadata:
    created_at: str
    updated_at: str
    schema: str = ARCADEV_PROJECT_SCHEMA
    schema_version: int = ARCADEV_PROJECT_SCHEMA_VERSION

    @classmethod
    def create(cls, *, created_at: str, updated_at: str | None = None) -> ProjectMetadata:
        updated_at = created_at if updated_at is None else updated_at
        if not _UTC_TIMESTAMP.fullmatch(created_at if isinstance(created_at, str) else ""):
            raise ValueError("created_at must be a canonical UTC timestamp.")
        if not _UTC_TIMESTAMP.fullmatch(updated_at if isinstance(updated_at, str) else ""):
            raise ValueError("updated_at must be a canonical UTC timestamp.")
        try:
            datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
            datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as error:
            raise ValueError("Project timestamps must contain valid calendar dates.") from error
        if updated_at < created_at:
            raise ValueError("updated_at cannot precede created_at.")
        return cls(created_at=created_at, updated_at=updated_at)

    @classmethod
    def from_dict(cls, value: Any) -> ProjectMetadata:
        value = _require_exact_dict(
            value, {"created_at", "updated_at", "schema", "schema_version"}, "Project metadata"
        )
        if value["schema"] != ARCADEV_PROJECT_SCHEMA:
            raise ValueError("ArcaDev project schema is unsupported.")
        if type(value["schema_version"]) is not int or value["schema_version"] != ARCADEV_PROJECT_SCHEMA_VERSION:
            raise ValueError("ArcaDev project schema version is unsupported.")
        return cls.create(created_at=value["created_at"], updated_at=value["updated_at"])

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "schema": self.schema,
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ProjectSpecification:
    project_type: str
    target_users: tuple[str, ...]
    primary_goal: str
    requested_features: tuple[str, ...]
    platform_targets: tuple[str, ...]
    authentication_requirements: tuple[str, ...]
    integration_requirements: tuple[str, ...]
    deployment_targets: tuple[str, ...]
    user_constraints: tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        project_type: str,
        target_users: Iterable[str],
        primary_goal: str,
        requested_features: Iterable[str],
        platform_targets: Iterable[str],
        authentication_requirements: Iterable[str] = (),
        integration_requirements: Iterable[str] = (),
        deployment_targets: Iterable[str] = (),
        user_constraints: Iterable[str] = (),
    ) -> ProjectSpecification:
        return cls(
            project_type=_validate_identifier(project_type, "project_type"),
            target_users=_canonical_collection(target_users, "target_users", required=True),
            primary_goal=_validate_text(primary_goal, "primary_goal", maximum=4_000),
            requested_features=_canonical_collection(requested_features, "requested_features", required=True),
            platform_targets=_canonical_collection(platform_targets, "platform_targets", required=True),
            authentication_requirements=_canonical_collection(
                authentication_requirements, "authentication_requirements"
            ),
            integration_requirements=_canonical_collection(integration_requirements, "integration_requirements"),
            deployment_targets=_canonical_collection(deployment_targets, "deployment_targets"),
            user_constraints=_canonical_collection(user_constraints, "user_constraints"),
        )

    @classmethod
    def from_dict(cls, value: Any) -> ProjectSpecification:
        keys = {
            "project_type", "target_users", "primary_goal", "requested_features", "platform_targets",
            "authentication_requirements", "integration_requirements", "deployment_targets", "user_constraints",
        }
        value = _require_exact_dict(value, keys, "Normalized project specification")
        for key in keys - {"project_type", "primary_goal"}:
            if not isinstance(value[key], list):
                raise ValueError(f"{key} must be a JSON array.")
        return cls.create(**value)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "authentication_requirements": list(self.authentication_requirements),
            "deployment_targets": list(self.deployment_targets),
            "integration_requirements": list(self.integration_requirements),
            "platform_targets": list(self.platform_targets),
            "primary_goal": self.primary_goal,
            "project_type": self.project_type,
            "requested_features": list(self.requested_features),
            "target_users": list(self.target_users),
            "user_constraints": list(self.user_constraints),
        }


@dataclass(frozen=True)
class ArcaDevProject:
    project_id: str
    project_name: str
    project_description: str
    original_user_request: str
    specification: ProjectSpecification
    project_status: ProjectStatus
    current_build_stage: BuildStage
    metadata: ProjectMetadata

    @classmethod
    def create(
        cls,
        *,
        project_name: str,
        project_description: str,
        original_user_request: str,
        specification: ProjectSpecification,
        metadata: ProjectMetadata,
        project_status: ProjectStatus | str = ProjectStatus.DRAFT,
        current_build_stage: BuildStage | str = BuildStage.IDEA,
    ) -> ArcaDevProject:
        name = _validate_text(project_name, "project_name", maximum=120)
        description = _validate_text(project_description, "project_description", maximum=8_000)
        request = _validate_text(
            original_user_request, "original_user_request", maximum=MAX_REQUEST_LENGTH, preserve=True
        )
        if not isinstance(specification, ProjectSpecification) or not isinstance(metadata, ProjectMetadata):
            raise ValueError("Project specification and metadata must be validated ArcaDev values.")
        try:
            status = ProjectStatus(project_status)
            stage = BuildStage(current_build_stage)
        except (TypeError, ValueError) as error:
            raise ValueError("Project status or build stage is unsupported.") from error
        if stage is not BuildStage.IDEA:
            raise ValueError("ArcaDev 1.1 projects must begin at the IDEA stage.")
        identity_body = {
            "original_user_request": request,
            "project_description": description,
            "project_name": name,
            "specification": specification.canonical_dict(),
        }
        digest = hashlib.sha256(
            ("arcadev-project-identity/v1\0" + _canonical_json(identity_body)).encode("utf-8")
        ).hexdigest()
        return cls(
            project_id=f"arcadev_{digest[:32]}",
            project_name=name,
            project_description=description,
            original_user_request=request,
            specification=specification,
            project_status=status,
            current_build_stage=stage,
            metadata=metadata,
        )

    @classmethod
    def from_dict(cls, value: Any) -> ArcaDevProject:
        keys = {
            "project_id", "project_name", "project_description", "original_user_request", "specification",
            "project_status", "current_build_stage", "metadata",
        }
        value = _require_exact_dict(value, keys, "ArcaDev project")
        if not isinstance(value["project_id"], str) or not _PROJECT_ID.fullmatch(value["project_id"]):
            raise ValueError("ArcaDev project ID is invalid.")
        result = cls.create(
            project_name=value["project_name"],
            project_description=value["project_description"],
            original_user_request=value["original_user_request"],
            specification=ProjectSpecification.from_dict(value["specification"]),
            project_status=value["project_status"],
            current_build_stage=value["current_build_stage"],
            metadata=ProjectMetadata.from_dict(value["metadata"]),
        )
        if result.project_id != value["project_id"]:
            raise ValueError("ArcaDev project identity does not match its canonical intent.")
        return result

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "current_build_stage": self.current_build_stage.value,
            "metadata": self.metadata.canonical_dict(),
            "original_user_request": self.original_user_request,
            "project_description": self.project_description,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "project_status": self.project_status.value,
            "specification": self.specification.canonical_dict(),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_dict())


def load_project(path: Path) -> ArcaDevProject:
    path = Path(path)
    try:
        if path.stat().st_size > MAX_PROJECT_BYTES:
            raise ValueError("ArcaDev project exceeds the safety limit.")
        text = path.read_text(encoding="utf-8")
        value = json.loads(text, object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Cannot load ArcaDev project.") from error
    result = ArcaDevProject.from_dict(value)
    if text != result.canonical_json():
        raise ValueError("ArcaDev project serialization is not canonical.")
    return result


def save_project(root: Path, relative_path: str, project: ArcaDevProject) -> Path:
    root = Path(root).resolve()
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        raise ValueError("ArcaDev project path is not a canonical relative path.")
    parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in parts) or relative_path.startswith("/"):
        raise ValueError("ArcaDev project path escapes its storage root.")
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise ValueError("ArcaDev project path contains a symbolic link.")
    target = root.joinpath(*parts)
    try:
        target.resolve().relative_to(root)
    except ValueError as error:
        raise ValueError("ArcaDev project path escapes its storage root.") from error
    if not isinstance(project, ArcaDevProject):
        raise ValueError("Only validated ArcaDev projects may be saved.")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(project.canonical_json())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return target
