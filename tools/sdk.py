"""Stable, versioned, tenant-safe internal ArcaCore SDK contract."""

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re

from tools.authorization import PolicyContract, PrincipalContext, authorize
from tools.extensions import ExtensionCapability, ExtensionRegistry, HookPoint
from tools.health_intelligence import HealthAggregator, HealthReport
from tools.jobs import JobExecutor, JobInvocation
from tools.multitenancy import TenantContext, trusted_tenant_id
from tools.observability import MetricRegistry, TraceContext, Tracer
from tools.resource_intelligence import ResourceIntelligence, ResourceReport
from tools.structured_logging import CorrelationContext, StructuredLogger, correlation_id


SDK_VERSION = "1.0"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
_VERSION = re.compile(r"([1-9][0-9]*)\.([0-9]+)\Z")
_ID = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN_KEYS = frozenset({
    "command", "shell", "python", "code", "import", "pickle",
    "environment", "env", "secret", "password", "token", "credential",
    "private_key", "traceback", "stack_trace", "absolute_path",
})
_RESPONSE_FORBIDDEN = frozenset({
    "secret", "password", "token", "credential", "private_key", "traceback",
    "stack_trace", "environment", "env", "absolute_path",
})


class SDKOperation(str, Enum):
    VALIDATE_SPECIFICATION = "validate_specification"
    PREPARE_BUILD = "prepare_build"
    RUN_VALIDATION = "run_validation"
    OPERATION_STATUS = "operation_status"
    RUNTIME_HEALTH = "runtime_health"
    DIAGNOSTICS = "diagnostics"
    RESOURCE_METADATA = "resource_metadata"
    INVOKE_EXTENSION = "invoke_extension"


def _compatible_version(value):
    if not isinstance(value, str):
        raise ValueError("SDK version is malformed.")
    match = _VERSION.fullmatch(value)
    if match is None:
        raise ValueError("SDK version is malformed.")
    if int(match.group(1)) != 1 or int(match.group(2)) > 0:
        raise ValueError("SDK version is unsupported.")
    return value


def _safe_json(value, *, response=False, depth=0):
    if depth > 8:
        raise ValueError("SDK value is too deeply nested.")
    if value is None or type(value) in (bool, int, float):
        if isinstance(value, float) and (value != value or abs(value) == float("inf")):
            raise ValueError("SDK value is not finite.")
        return value
    if isinstance(value, str):
        if len(value) > 4096 or any(ord(char) < 32 for char in value):
            raise ValueError("SDK text is invalid.")
        if response and (value.startswith(("/", "\\\\")) or re.search(r"(?:^|[ (])[A-Za-z]:[\\/]", value)):
            raise ValueError("SDK response contains a host path.")
        return value
    if isinstance(value, list):
        if len(value) > 64:
            raise ValueError("SDK collection is too large.")
        return [_safe_json(item, response=response, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 64:
            raise ValueError("SDK mapping is too large.")
        result = {}
        forbidden = _RESPONSE_FORBIDDEN if response else _FORBIDDEN_KEYS
        for key in sorted(value):
            if not isinstance(key, str) or not _ID.fullmatch(key) or key.lower() in forbidden:
                raise ValueError("SDK field is invalid.")
            result[key] = _safe_json(value[key], response=response, depth=depth + 1)
        return result
    raise ValueError("SDK accepts only JSON-safe values.")


def _bounded(value, *, response=False):
    clean = _safe_json(value, response=response)
    raw = json.dumps(clean, sort_keys=True, separators=(",", ":"), allow_nan=False)
    limit = MAX_RESPONSE_BYTES if response else MAX_REQUEST_BYTES
    if len(raw.encode("utf-8")) > limit:
        raise ValueError("SDK payload exceeds the bounded size.")
    return clean


@dataclass(frozen=True)
class SDKContract:
    version: str = SDK_VERSION

    def __post_init__(self):
        _compatible_version(self.version)

    def canonical_dict(self):
        return {"operations": [item.value for item in SDKOperation], "version": self.version}

    @property
    def digest(self):
        return sha256(json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class SDKRequest:
    version: str
    operation: SDKOperation
    correlation_id: str
    payload: dict

    def __post_init__(self):
        _compatible_version(self.version)
        if not isinstance(self.operation, SDKOperation):
            raise ValueError("SDK operation is unsupported.")
        correlation_id(self.correlation_id)
        object.__setattr__(self, "payload", _bounded(self.payload))
        expected = {
            SDKOperation.VALIDATE_SPECIFICATION: {"specification"},
            SDKOperation.PREPARE_BUILD: {"input", "idempotency_key"},
            SDKOperation.RUN_VALIDATION: {"manifest"},
            SDKOperation.OPERATION_STATUS: {"operation_id"},
            SDKOperation.RUNTIME_HEALTH: set(),
            SDKOperation.DIAGNOSTICS: set(),
            SDKOperation.RESOURCE_METADATA: set(),
            SDKOperation.INVOKE_EXTENSION: {"capability", "hook"},
        }[self.operation]
        if set(self.payload) != expected:
            raise ValueError("SDK request fields do not match the operation contract.")
        if self.operation is SDKOperation.PREPARE_BUILD and not _ID.fullmatch(self.payload["idempotency_key"] or ""):
            raise ValueError("SDK idempotency key is invalid.")
        if self.operation is SDKOperation.OPERATION_STATUS and not _HEX64.fullmatch(self.payload["operation_id"] or ""):
            raise ValueError("SDK operation identity is invalid.")

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {"correlation_id", "operation", "payload", "version"}:
            raise ValueError("SDK request is malformed.")
        try:
            operation = SDKOperation(value["operation"])
        except (TypeError, ValueError) as error:
            raise ValueError("SDK operation is unsupported.") from error
        return cls(value["version"], operation, value["correlation_id"], value["payload"])

    def canonical_dict(self):
        return {"correlation_id": self.correlation_id, "operation": self.operation.value, "payload": self.payload, "version": self.version}


@dataclass(frozen=True)
class SDKResponse:
    version: str
    operation: str
    correlation_id: str
    status: str
    data: dict
    error: dict | None = None

    def __post_init__(self):
        _compatible_version(self.version); correlation_id(self.correlation_id)
        if self.status not in {"ok", "error"} or not isinstance(self.operation, str) or not _ID.fullmatch(self.operation):
            raise ValueError("SDK response is invalid.")
        object.__setattr__(self, "data", _bounded(self.data, response=True))
        if self.status == "ok" and self.error is not None or self.status == "error" and self.error is None:
            raise ValueError("SDK response status is invalid.")
        if self.error is not None:
            object.__setattr__(self, "error", _bounded(self.error, response=True))

    def canonical_dict(self):
        return {"correlation_id": self.correlation_id, "data": self.data, "error": self.error, "operation": self.operation, "status": self.status, "version": self.version}

    @property
    def digest(self):
        return sha256(json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class ArcaCoreService:
    """Trusted composition root behind the stable SDK front door."""

    def __init__(self, *, policy, jobs, build_job, specification_validator,
                 validation_provider, health_aggregator, health_provider,
                 resource_intelligence, resource_provider, extensions,
                 logger=None, metrics=None, tracer=None, maximum_operations=1024):
        if not isinstance(policy, PolicyContract) or not isinstance(jobs, JobExecutor):
            raise ValueError("SDK policy and job service are required.")
        if not _ID.fullmatch(build_job or "") or jobs.registry.definition(build_job) is None:
            raise ValueError("SDK build job is not registered.")
        if any(not callable(item) for item in (specification_validator, validation_provider, health_provider, resource_provider)):
            raise ValueError("SDK providers must be trusted callables.")
        if not isinstance(health_aggregator, HealthAggregator) or not isinstance(resource_intelligence, ResourceIntelligence) or not isinstance(extensions, ExtensionRegistry):
            raise ValueError("SDK subsystem contracts are invalid.")
        if logger is not None and not isinstance(logger, StructuredLogger) or metrics is not None and not isinstance(metrics, MetricRegistry) or tracer is not None and not isinstance(tracer, Tracer):
            raise ValueError("SDK observability contracts are invalid.")
        if type(maximum_operations) is not int or not 1<=maximum_operations<=4096: raise ValueError("SDK operation bound is invalid.")
        self.policy=policy; self.jobs=jobs; self.build_job=build_job
        self.specification_validator=specification_validator; self.validation_provider=validation_provider
        self.health_aggregator=health_aggregator; self.health_provider=health_provider
        self.resource_intelligence=resource_intelligence; self.resource_provider=resource_provider
        self.extensions=extensions; self.logger=logger; self.metrics=metrics; self.tracer=tracer
        self._operations={}; self.maximum_operations=maximum_operations

    def execute(self, request, *, principal, tenant, trace_context=None):
        if not isinstance(request, SDKRequest) or not isinstance(principal, PrincipalContext):
            raise ValueError("Validated SDK request and principal are required.")
        tenant_id=trusted_tenant_id(tenant)
        if tenant_id != principal.tenant_id or not authorize(self.policy,principal,"read",resource_tenant_id=tenant_id):
            raise PermissionError("SDK access denied.")
        if trace_context is not None and not isinstance(trace_context, TraceContext):
            raise ValueError("SDK trace context is invalid.")
        span=self.tracer.start("sdk.operation",trace_context,attributes={"operation":request.operation.value}) if self.tracer and trace_context else None
        try:
            data=self._dispatch(request,principal,tenant,tenant_id)
            response=SDKResponse(SDK_VERSION,request.operation.value,request.correlation_id,"ok",data)
            self._record(request,tenant,"ok",span)
            return response
        except Exception:
            self._record(request,tenant,"error",span)
            raise

    def _dispatch(self,request,principal,tenant,tenant_id):
        op=request.operation; payload=request.payload
        if op is SDKOperation.VALIDATE_SPECIFICATION:
            return _bounded(self.specification_validator(payload["specification"]),response=True)
        if op is SDKOperation.RUN_VALIDATION:
            return _bounded(self.validation_provider(payload["manifest"]),response=True)
        if op is SDKOperation.PREPARE_BUILD:
            if len(self._operations)>=self.maximum_operations: raise RuntimeError("SDK operation capacity is unavailable.")
            invocation=self.jobs.enqueue(self.build_job,{"input":payload["input"]},principal,tenant,payload["idempotency_key"])
            self._operations[invocation.identity]=(invocation,tenant_id,principal.principal_id)
            return {"operation_id":invocation.identity,"status":invocation.status.value}
        if op is SDKOperation.OPERATION_STATUS:
            entry=self._operations.get(payload["operation_id"])
            if entry is None or entry[1]!=tenant_id or entry[2]!=principal.principal_id:
                raise PermissionError("SDK operation access denied.")
            invocation=entry[0]
            data={"operation_id":invocation.identity,"status":invocation.status.value}
            if invocation.result is not None: data["result"]=_bounded(invocation.result,response=True)
            return data
        if op in {SDKOperation.RUNTIME_HEALTH,SDKOperation.DIAGNOSTICS}:
            report=self.health_provider()
            if not isinstance(report,HealthReport) or report.tenant_id!=tenant_id: raise PermissionError("SDK health tenant mismatch.")
            return report.public_dict() if op is SDKOperation.RUNTIME_HEALTH else self.health_aggregator.tenant_view(report,principal,tenant,self.policy)
        if op is SDKOperation.RESOURCE_METADATA:
            report=self.resource_provider()
            if not isinstance(report,ResourceReport): raise ValueError("SDK resource provider returned an invalid report.")
            return self.resource_intelligence.tenant_view(report,principal,tenant,self.policy)
        if op is SDKOperation.INVOKE_EXTENSION:
            try: hook=HookPoint(payload["hook"]); capability=ExtensionCapability(payload["capability"])
            except (TypeError,ValueError) as error: raise ValueError("SDK extension request is invalid.") from error
            results=self.extensions.invoke(hook,capability,principal=principal,policy=self.policy,tenant=tenant,correlation_id=request.correlation_id)
            return {"results":[{"contributions":item.canonical_dict()["contributions"],"status":item.status.value} for item in results]}
        raise LookupError("SDK operation is unsupported.")

    def _record(self,request,tenant,outcome,span):
        if self.logger:
            self.logger.emit("INFO" if outcome=="ok" else "ERROR","sdk.operation","sdk",CorrelationContext(request.correlation_id),"SDK operation completed.",{"operation":request.operation.value,"outcome":outcome},tenant=tenant)
        if self.metrics: self.metrics.observe("sdk.operations",1,{"operation":request.operation.value,"outcome":outcome})
        if self.tracer and span: self.tracer.finish(span,outcome=="ok")


class ArcaCoreClient:
    """Consumer-facing adapter that returns bounded, redacted responses."""

    def __init__(self, service, principal, tenant):
        if not isinstance(service,ArcaCoreService) or not isinstance(principal,PrincipalContext) or not isinstance(tenant,TenantContext):
            raise ValueError("SDK client context is invalid.")
        self._service=service; self._principal=principal; self._tenant=tenant

    def request(self,value,*,trace_context=None):
        operation=value.get("operation","unknown") if isinstance(value,dict) else "unknown"
        correlation=value.get("correlation_id","invalid") if isinstance(value,dict) else "invalid"
        try:
            request=SDKRequest.from_dict(value)
            return self._service.execute(request,principal=self._principal,tenant=self._tenant,trace_context=trace_context)
        except Exception as error:
            code="access_denied" if isinstance(error,PermissionError) else "invalid_request" if isinstance(error,(ValueError,TypeError)) else "not_found" if isinstance(error,LookupError) else "operation_failed"
            if not isinstance(correlation,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}",correlation): correlation="invalid"
            if not isinstance(operation,str) or not _ID.fullmatch(operation): operation="unknown"
            return SDKResponse(SDK_VERSION,operation,correlation,"error",{}, {"code":code,"message":"SDK request failed."})
