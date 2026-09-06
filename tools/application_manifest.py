"""Canonical, declarative application manifest for generated ArcaCore projects."""

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any, Mapping

from tools.core.engine import write_text_atomic
from tools.core.module_definition import valid_public_identifier
from tools.minimal_regeneration import GenerationManifest
from tools.schema_lifecycle import LifecycleState, SchemaRevision, _digest


FORMAT_VERSION = 1
MAX_MANIFEST_BYTES = 2_000_000
HEX64 = frozenset("0123456789abcdef")
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
PYTHON_REQUIREMENT = re.compile(r"python(?:>=|==)3\.(?:1[0-9]|[89])(?:\.\d+)?\Z")
HEALTH_PATH = re.compile(r"/[A-Za-z0-9_./-]{0,127}\Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _hex64(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX64


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Application manifest contains duplicate key: {key}")
        result[key] = value
    return result


class TargetPlatform(str, Enum):
    LOCAL = "local"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"


class ExecutionMode(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class EnvironmentCategory(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    URL = "url"
    CREDENTIAL = "credential"


@dataclass(frozen=True)
class EnvironmentRequirement:
    name: str
    required: bool
    category: EnvironmentCategory
    secret: bool = False

    def canonical_dict(self):
        return {"category": self.category.value, "name": self.name,
                "required": self.required, "secret": self.secret}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"name", "required", "category", "secret"}:
            raise ValueError("Environment requirement has an invalid shape; values are forbidden.")
        if not ENV_NAME.fullmatch(value["name"] if isinstance(value["name"], str) else ""):
            raise ValueError("Environment variable name is invalid.")
        if type(value["required"]) is not bool or type(value["secret"]) is not bool:
            raise ValueError("Environment requirement flags are invalid.")
        try:
            category = EnvironmentCategory(value["category"])
        except (TypeError, ValueError) as error:
            raise ValueError("Environment category is unsupported.") from error
        if category == EnvironmentCategory.CREDENTIAL and not value["secret"]:
            raise ValueError("Credential requirements must be classified as secret.")
        return cls(value["name"], value["required"], category, value["secret"])


@dataclass(frozen=True)
class RuntimeContract:
    python: str = "python>=3.11"
    framework: str = "fastapi"
    database: str = "postgresql"
    health_path: str = "/health"
    required_services: tuple[str, ...] = ("api", "postgresql")
    platforms: tuple[TargetPlatform, ...] = (TargetPlatform.LOCAL,)
    execution_modes: tuple[ExecutionMode, ...] = (ExecutionMode.TEST,)

    def canonical_dict(self):
        return {"database": self.database, "execution_modes": [v.value for v in self.execution_modes],
                "framework": self.framework, "health_path": self.health_path,
                "platforms": [v.value for v in self.platforms], "python": self.python,
                "required_services": list(self.required_services)}

    @classmethod
    def create(cls, *, python="python>=3.11", framework="fastapi", database="postgresql",
               health_path="/health", required_services=("api", "postgresql"),
               platforms=(TargetPlatform.LOCAL,), execution_modes=(ExecutionMode.TEST,)):
        if not PYTHON_REQUIREMENT.fullmatch(python if isinstance(python, str) else ""):
            raise ValueError("Python runtime requirement is unsupported.")
        if framework not in {"fastapi"} or database not in {"postgresql", "none"}:
            raise ValueError("Runtime framework or database is unsupported.")
        if not HEALTH_PATH.fullmatch(health_path if isinstance(health_path, str) else "") or ".." in health_path:
            raise ValueError("Health path is invalid.")
        services = tuple(sorted(required_services))
        if len(services) != len(set(services)) or any(v not in {"api", "postgresql"} for v in services):
            raise ValueError("Required service is duplicated or unsupported.")
        if (database == "postgresql") != ("postgresql" in services):
            raise ValueError("Database and required service contract disagree.")
        try:
            targets = tuple(sorted((TargetPlatform(v) for v in platforms), key=lambda v: v.value))
            modes = tuple(sorted((ExecutionMode(v) for v in execution_modes), key=lambda v: v.value))
        except (TypeError, ValueError) as error:
            raise ValueError("Target platform or execution mode is unsupported.") from error
        if not targets or len(targets) != len(set(targets)) or not modes or len(modes) != len(set(modes)):
            raise ValueError("Runtime targets and modes must be non-empty and unique.")
        return cls(python, framework, database, health_path, services, targets, modes)

    @classmethod
    def from_dict(cls, value):
        keys = {"python", "framework", "database", "health_path", "required_services", "platforms", "execution_modes"}
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError("Runtime contract has an invalid shape or executable metadata.")
        if any(not isinstance(value[k], list) for k in ("required_services", "platforms", "execution_modes")):
            raise ValueError("Runtime contract collections are invalid.")
        return cls.create(**value)


@dataclass(frozen=True)
class ModuleReference:
    name: str
    dependencies: tuple[str, ...]
    accepted_schema_digest: str
    schema_revision_identity: str
    schema_parent_digest: str | None
    migration_revision: str | None
    generation_manifest_digest: str
    generated_surfaces: tuple[str, ...]
    capabilities: tuple[str, ...] = ()

    def canonical_dict(self):
        return {"accepted_schema_digest": self.accepted_schema_digest,
                "capabilities": list(self.capabilities), "dependencies": list(self.dependencies),
                "generated_surfaces": list(self.generated_surfaces),
                "generation_manifest_digest": self.generation_manifest_digest,
                "migration_revision": self.migration_revision, "name": self.name,
                "schema_parent_digest": self.schema_parent_digest,
                "schema_revision_identity": self.schema_revision_identity}

    @classmethod
    def create(cls, *, name, dependencies=(), accepted_schema_digest,
               schema_revision_identity, schema_parent_digest=None, migration_revision=None,
               generation_manifest_digest, generated_surfaces=(), capabilities=()):
        if not valid_public_identifier(name): raise ValueError("Module name is invalid.")
        dependencies = tuple(sorted(dependencies)); surfaces = tuple(sorted(generated_surfaces)); capabilities = tuple(sorted(capabilities))
        for collection, label in ((dependencies, "dependency"), (surfaces, "surface"), (capabilities, "capability")):
            if len(collection) != len(set(collection)) or len(collection) > 10_000:
                raise ValueError(f"Module {label} collection is duplicated or oversized.")
        if any(not valid_public_identifier(v) for v in dependencies): raise ValueError("Module dependency is invalid.")
        if name in dependencies: raise ValueError("Module cannot depend on itself.")
        if any(not isinstance(v, str) or not v or len(v) > 160 or "\\" in v or v.startswith("/") or ".." in v.split("/") for v in surfaces):
            raise ValueError("Generated surface reference is invalid.")
        if any(not valid_public_identifier(v) for v in capabilities): raise ValueError("Capability is invalid.")
        for digest in (accepted_schema_digest, schema_revision_identity, generation_manifest_digest):
            if not _hex64(digest): raise ValueError("Module provenance digest is invalid.")
        if schema_parent_digest is not None and not _hex64(schema_parent_digest): raise ValueError("Schema parent digest is invalid.")
        if migration_revision is not None and (not isinstance(migration_revision, str) or len(migration_revision) != 12 or set(migration_revision) > HEX64):
            raise ValueError("Migration revision is invalid.")
        return cls(name, dependencies, accepted_schema_digest, schema_revision_identity,
                   schema_parent_digest, migration_revision, generation_manifest_digest, surfaces, capabilities)

    @classmethod
    def from_dict(cls, value):
        keys = {"name", "dependencies", "accepted_schema_digest", "schema_revision_identity",
                "schema_parent_digest", "migration_revision", "generation_manifest_digest",
                "generated_surfaces", "capabilities"}
        if not isinstance(value, dict) or set(value) != keys or any(not isinstance(value[k], list) for k in ("dependencies", "generated_surfaces", "capabilities")):
            raise ValueError("Module reference has an invalid shape.")
        return cls.create(**value)


@dataclass(frozen=True)
class ApplicationManifest:
    application: str
    project_name: str
    modules: tuple[ModuleReference, ...]
    runtime: RuntimeContract
    environment: tuple[EnvironmentRequirement, ...]
    manifest_identity: str
    format_version: int = FORMAT_VERSION

    @classmethod
    def create(cls, *, application, project_name, modules, runtime, environment=()):
        if not valid_public_identifier(application) or not isinstance(project_name, str) or not (1 <= len(project_name) <= 120) or any(ord(c) < 32 for c in project_name):
            raise ValueError("Application identity is invalid.")
        modules = tuple(sorted(modules, key=lambda v: v.name)); environment = tuple(sorted(environment, key=lambda v: v.name))
        if not modules or any(not isinstance(v, ModuleReference) for v in modules) or len({v.name for v in modules}) != len(modules):
            raise ValueError("Application modules are invalid or duplicated.")
        if not isinstance(runtime, RuntimeContract) or any(not isinstance(v, EnvironmentRequirement) for v in environment) or len({v.name for v in environment}) != len(environment):
            raise ValueError("Application runtime or environment requirements are invalid.")
        names = {v.name for v in modules}
        for module in modules:
            missing = set(module.dependencies) - names
            if missing: raise ValueError(f"Module {module.name} references missing dependencies: {','.join(sorted(missing))}")
        visiting = set(); visited = set()
        by_name = {v.name: v for v in modules}
        def visit(name):
            if name in visiting: raise ValueError("Module dependency cycle detected.")
            if name in visited: return
            visiting.add(name)
            for dependency in by_name[name].dependencies: visit(dependency)
            visiting.remove(name); visited.add(name)
        for name in sorted(names): visit(name)
        body = {"application": application, "environment": [v.canonical_dict() for v in environment],
                "format_version": FORMAT_VERSION, "modules": [v.canonical_dict() for v in modules],
                "project_name": project_name, "runtime": runtime.canonical_dict()}
        return cls(application, project_name, modules, runtime, environment,
                   _digest("arcacore-application-manifest/v1", body))

    def canonical_dict(self):
        return {"application": self.application, "environment": [v.canonical_dict() for v in self.environment],
                "format_version": self.format_version, "manifest_identity": self.manifest_identity,
                "modules": [v.canonical_dict() for v in self.modules], "project_name": self.project_name,
                "runtime": self.runtime.canonical_dict()}

    def canonical_json(self): return _json(self.canonical_dict())

    @classmethod
    def from_dict(cls, value):
        keys = {"application", "project_name", "modules", "runtime", "environment", "manifest_identity", "format_version"}
        if not isinstance(value, dict) or set(value) != keys or value["format_version"] != FORMAT_VERSION:
            raise ValueError("Application manifest has an invalid shape or version.")
        if not isinstance(value["modules"], list) or not isinstance(value["environment"], list):
            raise ValueError("Application manifest collections are invalid.")
        result = cls.create(application=value["application"], project_name=value["project_name"],
            modules=[ModuleReference.from_dict(v) for v in value["modules"]],
            runtime=RuntimeContract.from_dict(value["runtime"]),
            environment=[EnvironmentRequirement.from_dict(v) for v in value["environment"]])
        if result.manifest_identity != value["manifest_identity"]:
            raise ValueError("Application manifest identity mismatch.")
        return result

    def validate_references(self, revisions: Mapping[str, SchemaRevision], ownership: GenerationManifest):
        if not isinstance(ownership, GenerationManifest): raise ValueError("Generation manifest is invalid.")
        owned = {v.path for v in ownership.files}
        for module in self.modules:
            revision = revisions.get(module.name)
            if not isinstance(revision, SchemaRevision) or revision.lifecycle_state != LifecycleState.ACCEPTED:
                raise ValueError(f"Module {module.name} does not reference an accepted schema.")
            if (revision.schema_digest != module.accepted_schema_digest or
                    revision.revision_identity != module.schema_revision_identity or
                    revision.parent_schema_digest != module.schema_parent_digest or
                    revision.migration_revision != module.migration_revision):
                raise ValueError(f"Module {module.name} schema provenance mismatch.")
            if module.generation_manifest_digest != ownership.manifest_identity:
                raise ValueError(f"Module {module.name} ownership manifest digest mismatch.")
            if not set(module.generated_surfaces) <= owned:
                raise ValueError(f"Module {module.name} references an unowned generated surface.")
        return True


def load_application_manifest(path: Path) -> ApplicationManifest:
    path = Path(path)
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES: raise ValueError("Application manifest exceeds the safety limit.")
        text = path.read_text(encoding="utf-8")
        value = json.loads(text, object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Cannot load application manifest.") from error
    result = ApplicationManifest.from_dict(value)
    if text != result.canonical_json(): raise ValueError("Application manifest is not canonical.")
    return result


def save_application_manifest(root: Path, relative_path: str, manifest: ApplicationManifest):
    root = Path(root).resolve()
    if not isinstance(relative_path, str) or "\\" in relative_path or relative_path.startswith("/") or ".." in relative_path.split("/"):
        raise ValueError("Application manifest path escapes the project root.")
    target = root.joinpath(*relative_path.split("/"))
    current = root
    for part in relative_path.split("/"):
        if not part or part == ".": raise ValueError("Application manifest path is not canonical.")
        current /= part
        if current.is_symlink(): raise ValueError("Application manifest path contains a symbolic link.")
    target.resolve().relative_to(root)
    if not isinstance(manifest, ApplicationManifest): raise ValueError("Application manifest is invalid.")
    write_text_atomic(target, manifest.canonical_json())
    return target
