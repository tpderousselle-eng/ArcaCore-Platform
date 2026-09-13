"""Non-destructive stale-authority evidence. No rebuild, deletion or execution."""
from dataclasses import dataclass

from .architecture_specification import Record, _json, _parse
from .model_amendment_request import checked, exact_result, identified
from .approved_domain_model_revision import ApprovedDomainModelRevision, validate_approved_domain_model_revision
from .models_backend_handoff import ModelsBackendHandoff
from .backend_specification import BackendSpecification
from .backend_clarification import BackendFinalization
from .backend_approval import ApprovedBackend
from .arcacore_generation_request import ArcaCoreGenerationRequest
from .backend_generation import BackendGenerationRun

ARCADEV_DOWNSTREAM_AUTHORITY_INVALIDATION_SCHEMA = "arcadev.downstream_authority_invalidation"
ARCADEV_DOWNSTREAM_AUTHORITY_INVALIDATION_SCHEMA_VERSION = 1

_TYPES = {"models_backend_handoff": ModelsBackendHandoff, "backend_specification": BackendSpecification,
    "backend_finalization": BackendFinalization, "approved_backend": ApprovedBackend,
    "generation_request": ArcaCoreGenerationRequest, "generation_run": BackendGenerationRun}


def _downstream(raw, revision):
    """Validate exact supplied content; nested history supplies validation context only."""
    values = {}
    def load(name, expected=None, **context):
        if raw[name] is None:
            values[name] = None
            return expected
        if expected is not None:
            # Complete canonical content was already validated inside the outer
            # historical package. Compare all bytes, never asserted IDs alone.
            if _json(raw[name]) != expected.canonical_json():
                raise ValueError("Unrelated or mixed downstream " + name + " authority.")
            values[name] = expected
        else:
            values[name] = _TYPES[name].from_dict(raw[name], **context)
        return values[name]
    run = load("generation_run")
    request = load("generation_request", run.request if run else None)
    approved = load("approved_backend", request.approved_backend if request else None)
    handoff = load("models_backend_handoff", approved.package.models_backend_handoff if approved else None)
    if handoff is not None and handoff.frozen_approved_domain_model.canonical_json() != revision.package.parent.canonical_json():
        raise ValueError("Downstream authority does not freeze this exact revision parent.")
    if handoff is None and any(raw[name] is not None for name in ("backend_specification", "backend_finalization")):
        raise ValueError("Standalone backend specification/finalization requires supplied frozen handoff context.")
    finalization = load("backend_finalization", approved.package.backend_finalization if approved else None, handoff=handoff)
    load("backend_specification", finalization.original_backend if finalization else None, handoff=handoff)
    return values


@dataclass(frozen=True)
class DownstreamAuthorityInvalidation(Record):
    invalidation_id: str
    revision: ApprovedDomainModelRevision
    parent_approval_id: str
    models_backend_handoff: ModelsBackendHandoff | None
    backend_specification: BackendSpecification | None
    backend_finalization: BackendFinalization | None
    approved_backend: ApprovedBackend | None
    generation_request: ArcaCoreGenerationRequest | None
    generation_run: BackendGenerationRun | None
    reason_codes: tuple[str, ...]
    stale_for_future_execution: bool
    schema: str = ARCADEV_DOWNSTREAM_AUTHORITY_INVALIDATION_SCHEMA
    schema_version: int = 1

    @classmethod
    def create(cls, revision, *, models_backend_handoff=None, backend_specification=None,
               backend_finalization=None, approved_backend=None, generation_request=None, generation_run=None):
        supplied = locals()
        raw = {}
        for name, typ in _TYPES.items():
            item = supplied[name]
            if item is not None and type(item) is not typ:
                raise ValueError("Expected complete typed downstream authority.")
            raw[name] = None if item is None else item.canonical_dict()
        return cls._build(validate_approved_domain_model_revision(revision), raw)

    @classmethod
    def _build(cls, revision, raw):
        if not revision.approved:
            raise ValueError("Only an explicitly approved revision supersedes parent authority.")
        values = _downstream(raw, revision)
        reasons = ("approved_domain_model_superseded",) + tuple(name + "_stale" for name in _TYPES if values[name] is not None)
        result = cls("", revision, revision.parent_approval_id, **values,
            reason_codes=tuple(sorted(reasons)), stale_for_future_execution=True)
        return identified(result, "invalidation_id", "downstream_authority_invalidation")

    @classmethod
    def from_dict(cls, value, *, revision=None):
        checked(value, cls, ARCADEV_DOWNSTREAM_AUTHORITY_INVALIDATION_SCHEMA)
        frozen = validate_approved_domain_model_revision(value["revision"])
        if revision is not None and validate_approved_domain_model_revision(revision).canonical_json() != frozen.canonical_json():
            raise ValueError("Invalidation is stale against supplied revision authority.")
        return exact_result(cls._build(frozen, {name: value[name] for name in _TYPES}), value)

    @classmethod
    def from_json(cls, text, *, revision=None):
        return cls.from_dict(_parse(text), revision=revision)

    def assert_current(self, kind, authority):
        """Explicit fail-closed guard; this record never grants new execution authority.

        Callers select current lineage externally. Legacy historical validators
        alone cannot know about revisions that were never supplied to them.
        """
        record = self.from_json(self.canonical_json())
        if type(kind) is not str or kind not in _TYPES:
            raise ValueError("Unknown downstream authority kind.")
        frozen = getattr(record, kind)
        if frozen is None or type(authority) is not _TYPES[kind] or authority.canonical_json() != frozen.canonical_json():
            raise ValueError("Unrelated or unevaluated authority cannot be treated as current.")
        raise ValueError("Supplied downstream authority is stale for future execution.")


def invalidate_downstream_authority(revision, **downstream):
    return DownstreamAuthorityInvalidation.create(revision, **downstream)
