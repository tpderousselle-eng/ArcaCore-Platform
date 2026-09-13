"""Controlled public generation and immutable evidence; never an application workspace."""
from __future__ import annotations

import ast
from dataclasses import dataclass, fields, replace
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
from tempfile import TemporaryDirectory, gettempdir

from tools.core.module_definition import module_output_path
from tools.minimal_regeneration import GenerationManifest, OwnedFile

from ._generation_process import invoke_module
from .arcacore_generation_request import ArcaCoreGenerationRequest, module_definition, validate_arcacore_generation_request
from .architecture_specification import Record, _exact, _identity, _json, _pairs, _parse
from .domain_model_specification import _model_safe
from .generation_dependencies import generation_dependency_plan

ARCADEV_BACKEND_GENERATION_RUN_SCHEMA = "arcadev.backend_generation_run"
ARCADEV_BACKEND_GENERATION_RUN_SCHEMA_VERSION = 1
ARCADEV_BACKEND_ARTIFACT_MANIFEST_SCHEMA = "arcadev.backend_artifact_manifest"
ARCADEV_BACKEND_ARTIFACT_MANIFEST_SCHEMA_VERSION = 1
_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_LAYERS = ("models", "schemas", "crud", "services", "api")
_REGISTRY = "tools/registry/models.json"
_ENTRYPOINT = "tools.generate"
_GENERATOR = "tools.generate.generate_module"
_MAX_FILE_BYTES = 2_000_000
_PENDING = ("accepted_schema_revision", "application_manifest", "runtime_validation")
_TEMPLATES = ("model", "schema", "crud", "service", "router", "encrypted_type",
    "phone_validator", "slug_validator", "url_validator", "custom_validators")


class GenerationDisposition(str, Enum):
    GENERATED = "GENERATED"
    BLOCKED_INCOMPATIBLE = "BLOCKED_INCOMPATIBLE"
    FAILED_GENERATION = "FAILED_GENERATION"
    FAILED_VALIDATION = "FAILED_VALIDATION"


class GenerationDiagnostic(str, Enum):
    PROCESS_SETUP = "process_setup"
    NONZERO_EXIT = "nonzero_exit"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output_limit"
    PROCESS_CLEANUP = "process_cleanup"
    WORKSPACE_SETUP = "workspace_setup"
    ARTIFACT_VALIDATION = "artifact_validation"
    SOURCE_CHANGED = "source_changed"
    WORKSPACE_CLEANUP = "workspace_cleanup"


def _digest(value):
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _hex(value):
    if type(value) is not str or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Expected a SHA-256 digest.")


def _relative(value):
    if type(value) is not str or not re.fullmatch(r"[a-zA-Z0-9_./-]{1,240}", value):
        raise ValueError("Artifact path is invalid.")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(p in {".", ".."} for p in path.parts):
        raise ValueError("Artifact path is not canonical and contained.")
    return value


def _checked_path(root, relative):
    path = root
    for part in PurePosixPath(_relative(relative)).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symbolic links are forbidden in generation workspaces.")
        if path.exists():
            info = path.lstat()
            if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError("Reparse points are forbidden in generation workspaces.")
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ValueError("Linked generation files are forbidden.")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Generation path escapes workspace.")
    return path


@dataclass(frozen=True)
class ArcaCoreGenerationProvenance(Record):
    public_entrypoint: str
    trusted_source_digest: str
    interpreter_version: str

    def validate(self):
        if self.public_entrypoint != _ENTRYPOINT or type(self.interpreter_version) is not str or not re.fullmatch(r"\d+\.\d+\.\d+", self.interpreter_version):
            raise ValueError("Generation provenance is invalid.")
        _hex(self.trusted_source_digest)


@dataclass(frozen=True)
class GeneratedArtifact(Record):
    path: str
    content_digest: str
    byte_size: int
    surface: str
    module_request_ids: tuple[str, ...]

    def validate(self):
        _relative(self.path); _hex(self.content_digest)
        if type(self.byte_size) is not int or not 0 < self.byte_size <= _MAX_FILE_BYTES:
            raise ValueError("Artifact size is invalid.")
        if self.surface == "registry":
            valid = self.path == _REGISTRY
        else:
            valid = self.surface in _LAYERS and re.fullmatch(r"backend/app/" + re.escape(self.surface) + r"/[a-z][a-z0-9_]*\.py", self.path)
        if not valid:
            raise ValueError("Artifact is outside the certified generated surfaces.")
        ids = self.module_request_ids
        if type(ids) is not tuple or not ids or any(
            type(i) is not str or not re.fullmatch(r"arcadev_module_generation_request_[a-f0-9]{32}", i) for i in ids):
            raise ValueError("Artifact module provenance is invalid.")
        if ids != tuple(sorted(set(ids))):
            raise ValueError("Artifact module provenance is duplicated or unordered.")
        if self.surface != "registry" and len(ids) != 1:
            raise ValueError("A module surface must have one originating module.")


@dataclass(frozen=True)
class BackendArtifactManifest(Record):
    manifest_id: str
    request_id: str
    request_digest: str
    provenance: ArcaCoreGenerationProvenance
    artifacts: tuple[GeneratedArtifact, ...]
    pending_authority: tuple[str, ...] = _PENDING
    schema: str = ARCADEV_BACKEND_ARTIFACT_MANIFEST_SCHEMA
    schema_version: int = ARCADEV_BACKEND_ARTIFACT_MANIFEST_SCHEMA_VERSION

    @property
    def generation_manifest(self):
        """Legitimate public ownership evidence derived from observed artifact hashes."""
        return GenerationManifest.create(OwnedFile(a.path, _GENERATOR, a.content_digest, self.request_digest)
            for a in self.artifacts)

    def canonical_dict(self):
        result = super().canonical_dict()
        result["generation_manifest"] = self.generation_manifest.canonical_dict()
        return result

    @classmethod
    def _build(cls, request_id, request_digest, provenance, artifacts):
        _hex(request_digest); provenance.validate()
        if type(request_id) is not str or not re.fullmatch(r"arcadev_arcacore_generation_request_[a-f0-9]{32}", request_id):
            raise ValueError("Artifact request identity is invalid.")
        artifacts = tuple(artifacts)
        for artifact in artifacts: artifact.validate()
        artifacts = tuple(sorted(artifacts, key=lambda a: a.path))
        if not 1 <= len(artifacts) <= 256 or len({a.path.casefold() for a in artifacts}) != len(artifacts):
            raise ValueError("Artifact inventory is empty, duplicated or oversized.")
        result = cls("", request_id, request_digest, provenance, artifacts)
        body = result.canonical_dict(); body.pop("manifest_id")
        return replace(result, manifest_id=_identity("backend_artifact_manifest", body))

    @classmethod
    def from_dict(cls, value):
        _model_safe(value); _exact(value, [f.name for f in fields(cls)] + ["generation_manifest"])
        if value["schema"] != ARCADEV_BACKEND_ARTIFACT_MANIFEST_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported backend artifact manifest schema/version.")
        _exact(value["provenance"], [f.name for f in fields(ArcaCoreGenerationProvenance)])
        provenance = ArcaCoreGenerationProvenance(**value["provenance"])
        if type(value["artifacts"]) is not list:
            raise ValueError("Artifact inventory must be an array.")
        artifacts = []
        for row in value["artifacts"]:
            _exact(row, [f.name for f in fields(GeneratedArtifact)])
            if type(row["module_request_ids"]) is not list:
                raise ValueError("Artifact origins must be an array.")
            artifacts.append(GeneratedArtifact(**{**row, "module_request_ids": tuple(row["module_request_ids"])}))
        result = cls._build(value["request_id"], value["request_digest"], provenance, artifacts)
        if result.canonical_dict() != value:
            raise ValueError("Backend artifact manifest integrity mismatch.")
        return result

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


def _expected(request, root):
    result = {}
    for module in request.module_requests:
        definition = module_definition(module)
        for layer in _LAYERS:
            path = module_output_path(root, layer, definition).relative_to(root.resolve()).as_posix()
            result[path] = (layer, (module.module_request_id,))
    result[_REGISTRY] = ("registry", tuple(sorted(m.module_request_id for m in request.module_requests)))
    return result


def validate_backend_artifact_manifest(manifest, *, request=None):
    value = manifest.canonical_dict() if type(manifest) is BackendArtifactManifest else manifest
    result = BackendArtifactManifest.from_json(value) if type(value) is str else BackendArtifactManifest.from_dict(value)
    if request is not None:
        request = validate_arcacore_generation_request(request)
        if not request.eligible_for_generation or result.request_id != request.request_id or result.request_digest != _digest(request.canonical_dict()):
            raise ValueError("Artifact manifest is bound to different generation authority.")
        expected = _expected(request, _SOURCE_ROOT)
        if {a.path: (a.surface, a.module_request_ids) for a in result.artifacts} != expected:
            raise ValueError("Artifact manifest omits or changes required generated surfaces.")
    return result


@dataclass(frozen=True)
class BackendGenerationRun(Record):
    run_id: str
    request: ArcaCoreGenerationRequest
    disposition: GenerationDisposition
    artifact_manifest: BackendArtifactManifest | None
    invocation_count: int
    diagnostics: tuple[GenerationDiagnostic, ...]
    source_before_digest: str | None
    source_after_digest: str | None
    workspace_cleaned: bool
    schema: str = ARCADEV_BACKEND_GENERATION_RUN_SCHEMA
    schema_version: int = ARCADEV_BACKEND_GENERATION_RUN_SCHEMA_VERSION

    @property
    def blocking_findings(self):
        return self.request.blocking_findings

    @property
    def source_tree_unchanged(self):
        return self.source_before_digest is not None and self.source_before_digest == self.source_after_digest

    @classmethod
    def _build(cls, request, disposition, manifest=None, count=0, diagnostics=(), before=None, after=None, cleaned=True):
        if type(count) is not int or not 0 <= count <= len(request.module_requests) or type(cleaned) is not bool:
            raise ValueError("Run execution evidence is invalid.")
        if any(type(d) is not GenerationDiagnostic for d in diagnostics):
            raise ValueError("Unknown generation diagnostic.")
        if disposition is GenerationDisposition.BLOCKED_INCOMPATIBLE:
            if request.eligible_for_generation or manifest is not None or count or diagnostics or before is not None or after is not None or not cleaned:
                raise ValueError("Incompatible requests cannot execute or produce artifacts.")
        else:
            if not request.eligible_for_generation:
                raise ValueError("Incompatible generation cannot be reported as executed.")
            _hex(before); _hex(after)
            if disposition is GenerationDisposition.GENERATED:
                if count != len(request.module_requests) or not count or diagnostics or before != after or not cleaned or manifest is None:
                    raise ValueError("Successful generation requires complete validated evidence.")
                validate_backend_artifact_manifest(manifest, request=request)
            elif disposition in {GenerationDisposition.FAILED_GENERATION, GenerationDisposition.FAILED_VALIDATION}:
                if manifest is not None or not diagnostics:
                    raise ValueError("Failed runs cannot accept artifact authority.")
            else:
                raise ValueError("Unknown generation disposition.")
        result = cls("", request, disposition, manifest, count, tuple(diagnostics), before, after, cleaned)
        body = result.canonical_dict(); body.pop("run_id")
        return replace(result, run_id=_identity("backend_generation_run", body))

    @classmethod
    def from_dict(cls, value):
        _model_safe(value); _exact(value, [f.name for f in fields(cls)])
        if value["schema"] != ARCADEV_BACKEND_GENERATION_RUN_SCHEMA or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported backend generation run schema/version.")
        request = ArcaCoreGenerationRequest.from_dict(value["request"])
        manifest = None if value["artifact_manifest"] is None else BackendArtifactManifest.from_dict(value["artifact_manifest"])
        if type(value["diagnostics"]) is not list:
            raise ValueError("Run diagnostics must be an array.")
        result = cls._build(request, GenerationDisposition(value["disposition"]), manifest, value["invocation_count"],
            tuple(GenerationDiagnostic(d) for d in value["diagnostics"]), value["source_before_digest"],
            value["source_after_digest"], value["workspace_cleaned"])
        if result.canonical_dict() != value:
            raise ValueError("Backend generation run integrity mismatch.")
        return result

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(_parse(text))


def validate_backend_generation_run(run, *, request=None):
    value = run.canonical_dict() if type(run) is BackendGenerationRun else run
    result = BackendGenerationRun.from_json(value) if type(value) is str else BackendGenerationRun.from_dict(value)
    if request is not None and result.request.canonical_json() != validate_arcacore_generation_request(request).canonical_json():
        raise ValueError("Backend generation run is stale against supplied request authority.")
    return result


def _source_snapshot():
    result = {}
    for surface in ("backend", "frontend", "shared", "tools"):
        for directory, dirs, names in os.walk(_SOURCE_ROOT / surface):
            dirs[:] = [d for d in dirs if d not in {".venv", "__pycache__", "node_modules"}]
            linked_dirs = set()
            for name in dirs + names:
                path = Path(directory) / name
                relative = path.relative_to(_SOURCE_ROOT).as_posix()
                # Source links are fingerprinted without following them.
                if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    result[relative] = "link:" + str(os.readlink(path)); linked_dirs.add(name); continue
                if path.is_file(): result[relative] = sha256(path.read_bytes()).hexdigest()
            dirs[:] = [d for d in dirs if d not in linked_dirs]
    return _digest(result)


def _trusted_bundle():
    """Copy the static tools import closure, package initializers and known templates.

    This reads implementation only to transport it. Invocation and validation use
    public contracts; ArcaDev never renders or patches generated implementation.
    """
    pending, bundle = {"tools.generate"}, {}
    while pending:
        name = pending.pop()
        base = name.replace(".", "/")
        relative = base + ".py"
        if not (_SOURCE_ROOT / relative).is_file(): relative = base + "/__init__.py"
        if relative in bundle: continue
        path = _checked_path(_SOURCE_ROOT, relative)
        content = path.read_bytes(); bundle[relative] = content
        if len(bundle) > 128 or len(content) > _MAX_FILE_BYTES:
            raise ValueError("Trusted generation closure exceeds bounds.")
        parts = name.split(".")
        pending.update(".".join(parts[:i]) for i in range(1, len(parts)))
        for node in ast.walk(ast.parse(content)):
            imports = []
            if isinstance(node, ast.Import): imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level: raise ValueError("Relative generator imports require closure certification.")
                imports = [node.module] if node.module else []
                imports += [node.module + "." + alias.name for alias in node.names if node.module
                    and (_SOURCE_ROOT / (node.module.replace(".", "/") + "/" + alias.name + ".py")).is_file()]
            pending.update(n for n in imports if n == "tools" or n.startswith("tools."))
    for name in _TEMPLATES:
        relative = "tools/templates/" + name + ".j2"
        bundle[relative] = _checked_path(_SOURCE_ROOT, relative).read_bytes()
    return bundle


def _prepare(workspace, bundle):
    for relative, content in bundle.items():
        target = _checked_path(workspace, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _scan_secret_content(text):
    # Check individual literals/lines to retain the existing credential detector
    # without treating Python newlines as declarative authority text.
    for line in text.splitlines():
        if line.strip(): _model_safe(line)


def _validate_registry(content, request):
    registry = json.loads(content, object_pairs_hook=_pairs)
    definitions = {module_definition(m).class_name: module_definition(m) for m in request.module_requests}
    if type(registry) is not dict or set(registry) != set(definitions):
        raise ValueError("Registry does not contain exactly the generated modules.")
    for name, definition in definitions.items():
        row = registry[name]
        _exact(row, ("table", "fields", "soft_delete", "indexes", "unique_constraints", "check_constraints"))
        if row["table"] != definition.table_name or row["soft_delete"] is not False or row["indexes"] != []:
            raise ValueError("Registry module metadata differs from approved declarations.")
        if row["unique_constraints"] != [{"name": c.name, "columns": c.columns} for c in definition.unique_constraints] or row["check_constraints"] != [
            {"name": c.name, "expression": c.expression} for c in definition.check_constraints
        ]:
            raise ValueError("Registry constraints differ from approved declarations.")
        if type(row["fields"]) is not list or len(row["fields"]) != len(definition.fields):
            raise ValueError("Registry field inventory differs from declarations.")
        for actual, field in zip(row["fields"], definition.fields):
            attributes = {k: k for k in ("name", "python_type", "sqlalchemy_type", "nullable", "unique", "index", "default",
                "min_length", "max_length", "foreign_key", "relationship_name", "relationship_class", "relationship_type",
                "back_populates", "backref", "association_table", "relationship_table", "relationship_key", "cascade_delete", "passive_deletes")}
            attributes.update({"min": "minimum", "max": "maximum", "regex": "pattern", "computed": "computed_expression", "computed_sql": "computed_sql"})
            if actual != {key: getattr(field, attr) for key, attr in attributes.items()}:
                raise ValueError("Registry field metadata differs from approved declarations.")


def _validate_artifacts(workspace, request, bundle):
    expected = _expected(request, workspace)
    allowed = set(bundle) | set(expected)
    allowed_dirs = {p.as_posix() for name in allowed for p in PurePosixPath(name).parents if p.as_posix() != "."}
    observed, seen = {}, set()
    for directory, dirs, names in os.walk(workspace):
        for name in dirs + names:
            relative = (Path(directory) / name).relative_to(workspace).as_posix()
            path = _checked_path(workspace, relative)
            if path.is_dir():
                if relative not in allowed_dirs: raise ValueError("Unexpected generated directory.")
                continue
            if relative not in allowed or not path.is_file() or not 0 < path.stat().st_size <= _MAX_FILE_BYTES:
                # Empty trusted package initializers are allowed, never artifacts.
                if relative not in bundle or not path.is_file() or path.stat().st_size != 0:
                    raise ValueError("Unexpected, secret or oversized generated file.")
            content = path.read_bytes()
            seen.add(relative)
            if relative in bundle:
                if content != bundle[relative]: raise ValueError("Trusted generator implementation was modified.")
            else:
                observed[relative] = content
    if seen != allowed or set(observed) != set(expected):
        raise ValueError("Generated artifact or trusted implementation inventory is incomplete.")
    artifacts = []
    for relative, content in sorted(observed.items()):
        text = content.decode("utf-8"); _scan_secret_content(text)
        surface, origins = expected[relative]
        if surface == "registry":
            _validate_registry(text, request)
        else:
            tree = ast.parse(content, filename=relative)
            compile(tree, relative, "exec")  # In memory only; never import generated application code.
            module = next(m for m in request.module_requests if m.module_request_id == origins[0])
            class_name = module_definition(module).class_name
            required = {"models": class_name, "schemas": class_name + "Update", "crud": class_name + "CRUD", "services": class_name + "Service"}
            if surface in required and required[surface] not in {n.name for n in tree.body if isinstance(n, ast.ClassDef)}:
                raise ValueError("Generated Python surface has no expected public class.")
            if surface == "api" and "router" not in {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}:
                raise ValueError("Generated router surface is missing.")
        artifacts.append(GeneratedArtifact(relative, sha256(content).hexdigest(), len(content), surface, origins))
    provenance = ArcaCoreGenerationProvenance(_ENTRYPOINT,
        _digest({path: sha256(data).hexdigest() for path, data in sorted(bundle.items())}), platform.python_version())
    result = BackendArtifactManifest._build(request.request_id, _digest(request.canonical_dict()), provenance, artifacts)
    return validate_backend_artifact_manifest(result, request=request)


def _invoke_dependency_plan(modules, workspace, runtime):
    """Execute exact public declarations in derived order; return no artifact authority."""
    plan = generation_dependency_plan(modules)
    by_id = {m.module_request_id: m for m in modules}
    count = 0
    for identity in plan.ordered_module_request_ids:
        outcome = invoke_module(by_id[identity], workspace, runtime)
        count += int(outcome.started)
        if outcome.diagnostic is not None:
            return count, GenerationDiagnostic(outcome.diagnostic)
    return count, None


def generate_backend(request, **current_authority):
    """Execute only complete certified scope; generated files are temporary evidence."""
    request = validate_arcacore_generation_request(request, **current_authority)
    if not request.eligible_for_generation:
        return BackendGenerationRun._build(request, GenerationDisposition.BLOCKED_INCOMPATIBLE)
    before = _source_snapshot()
    disposition, manifest, count, diagnostics = GenerationDisposition.FAILED_GENERATION, None, 0, ()
    temporary = None
    try:
        base = Path(gettempdir()).resolve()
        if base.is_relative_to(_SOURCE_ROOT.resolve()):
            raise ValueError("Temporary generation must be outside the source repository.")
        bundle = _trusted_bundle()
        with TemporaryDirectory(prefix="arcadev-generation-", dir=base) as temporary:
            outer = Path(temporary).resolve()
            if outer.is_relative_to(_SOURCE_ROOT.resolve()): raise ValueError("Generation workspace is inside source repository.")
            workspace, runtime = outer / "workspace", outer / "runtime"
            workspace.mkdir(); runtime.mkdir()
            _prepare(workspace, bundle)
            count, diagnostic = _invoke_dependency_plan(request.module_requests, workspace, runtime)
            if diagnostic is not None:
                diagnostics = (diagnostic,)
            else:
                disposition = GenerationDisposition.FAILED_VALIDATION
                try:
                    manifest = _validate_artifacts(workspace, request, bundle)
                    disposition = GenerationDisposition.GENERATED
                except (ValueError, TypeError, SyntaxError, UnicodeError, OSError):
                    diagnostics = (GenerationDiagnostic.ARTIFACT_VALIDATION,)
    except (OSError, ValueError):
        manifest = None
        diagnostics = (GenerationDiagnostic.WORKSPACE_SETUP,)
        disposition = GenerationDisposition.FAILED_GENERATION
    cleaned = temporary is None or not Path(temporary).exists()
    after = _source_snapshot()
    if before != after or not cleaned:
        disposition, manifest = GenerationDisposition.FAILED_VALIDATION, None
        diagnostics = (GenerationDiagnostic.SOURCE_CHANGED if before != after else GenerationDiagnostic.WORKSPACE_CLEANUP,)
    return BackendGenerationRun._build(request, disposition, manifest, count, diagnostics, before, after, cleaned)
