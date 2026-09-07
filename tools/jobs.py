"""Deterministic, tenant-safe background and scheduled job primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
import re
import time
from typing import Callable, Mapping

from tools.authorization import PolicyContract, PrincipalContext, authorize
from tools.multitenancy import TenantContext, trusted_tenant_id


_ID = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
_CRON = re.compile(r"(?:\*|[0-5]?\d) (?:\*|[01]?\d|2[0-3]) (?:\*|[1-9]|[12]\d|3[01]) (?:\*|[1-9]|1[0-2]) (?:\*|[0-6])\Z")
MAX_PAYLOAD_BYTES = 64 * 1024


def _identifier(value, label="Identifier"):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} is invalid.")
    return value


def _json_payload(value):
    if not isinstance(value, dict):
        raise ValueError("Job payload must be a JSON object.")
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("Job payload must contain only JSON-safe values.") from error
    if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("Job payload exceeds the bounded size.")
    return json.loads(raw), raw


@dataclass(frozen=True)
class RetryPolicy:
    maximum_attempts: int = 1
    delay_seconds: float = 0

    def __post_init__(self):
        if type(self.maximum_attempts) is not int or not 1 <= self.maximum_attempts <= 10:
            raise ValueError("Retry attempts must be between 1 and 10.")
        if isinstance(self.delay_seconds, bool) or not isinstance(self.delay_seconds, (int, float)) or not 0 <= self.delay_seconds <= 300:
            raise ValueError("Retry delay must be bounded.")

    def canonical_dict(self):
        return {"delay_seconds": self.delay_seconds, "maximum_attempts": self.maximum_attempts}


@dataclass(frozen=True)
class JobSchedule:
    expression: str
    timezone: str = "UTC"

    def __post_init__(self):
        if not isinstance(self.expression, str) or not _CRON.fullmatch(self.expression):
            raise ValueError("Schedule must use the supported five-field grammar.")
        if self.timezone != "UTC":
            raise ValueError("Canonical schedules use UTC.")

    def canonical_dict(self):
        return {"expression": self.expression, "timezone": self.timezone}


@dataclass(frozen=True)
class JobDefinition:
    identifier: str
    handler: str
    allowed_fields: tuple[str, ...]
    permission: str
    tenant_scoped: bool = True
    timeout_seconds: float = 30
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    schedule: JobSchedule | None = None
    enabled: bool = True

    def __post_init__(self):
        _identifier(self.identifier, "Job identifier"); _identifier(self.handler, "Handler")
        _identifier(self.permission, "Permission")
        if type(self.tenant_scoped) is not bool or type(self.enabled) is not bool:
            raise ValueError("Job flags are invalid.")
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float)) or not 0 < self.timeout_seconds <= 3600:
            raise ValueError("Job timeout must be bounded.")
        if tuple(sorted(set(self.allowed_fields))) != self.allowed_fields:
            raise ValueError("Allowed payload fields must be unique and sorted.")
        for item in self.allowed_fields: _identifier(item, "Payload field")
        if not isinstance(self.retry, RetryPolicy) or self.schedule is not None and not isinstance(self.schedule, JobSchedule):
            raise ValueError("Job policy is invalid.")

    def canonical_dict(self):
        return {"allowed_fields": list(self.allowed_fields), "enabled": self.enabled,
                "handler": self.handler, "identifier": self.identifier,
                "permission": self.permission, "retry": self.retry.canonical_dict(),
                "schedule": self.schedule.canonical_dict() if self.schedule else None,
                "tenant_scoped": self.tenant_scoped, "timeout_seconds": self.timeout_seconds}


class JobRegistry:
    def __init__(self, definitions, handlers: Mapping[str, Callable]):
        definitions = tuple(definitions)
        if tuple(sorted(definitions, key=lambda item: item.identifier)) != definitions or len({v.identifier for v in definitions}) != len(definitions):
            raise ValueError("Job definitions must be unique and sorted.")
        if any(not isinstance(v, JobDefinition) for v in definitions) or not isinstance(handlers, Mapping):
            raise ValueError("Job registry is invalid.")
        needed = {v.handler for v in definitions}
        if set(handlers) != needed or any(not callable(handlers[v]) for v in needed):
            raise ValueError("Every handler must be supplied by the trusted registry.")
        self.definitions = definitions
        self._handlers = dict(handlers)

    def canonical_dict(self): return {"jobs": [v.canonical_dict() for v in self.definitions], "version": 1}
    @property
    def digest(self): return sha256(json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    def definition(self, identifier):
        return next((v for v in self.definitions if v.identifier == identifier), None)
    def handler(self, identifier): return self._handlers[identifier]


class JobStatus(str, Enum):
    QUEUED="queued"; RUNNING="running"; SUCCEEDED="succeeded"; FAILED="failed"; CANCELLED="cancelled"


@dataclass
class JobInvocation:
    identity: str; definition: JobDefinition; payload: dict; tenant_id: object
    principal_id: object; idempotency_key: str; status: JobStatus = JobStatus.QUEUED
    attempts: int = 0; error_class: str | None = None; result: object = None

    def transition(self, target):
        target = JobStatus(target)
        allowed = {JobStatus.QUEUED:{JobStatus.RUNNING,JobStatus.CANCELLED},
                   JobStatus.RUNNING:{JobStatus.SUCCEEDED,JobStatus.FAILED},
                   JobStatus.FAILED:{JobStatus.RUNNING}}
        if target not in allowed.get(self.status, set()): raise ValueError("Impossible job state transition.")
        self.status = target


class JobExecutor:
    def __init__(self, registry: JobRegistry, policy: PolicyContract):
        if not isinstance(registry, JobRegistry) or not isinstance(policy, PolicyContract): raise ValueError("Executor policy is invalid.")
        self.registry=registry; self.policy=policy; self._invocations={}; self._schedules=set()

    def register_schedules(self):
        for definition in self.registry.definitions:
            if definition.schedule: self._schedules.add((definition.identifier, json.dumps(definition.schedule.canonical_dict(), sort_keys=True)))
        return len(self._schedules)

    def enqueue(self, identifier, payload, principal: PrincipalContext, tenant: TenantContext | None, idempotency_key):
        definition=self.registry.definition(identifier)
        if definition is None or not definition.enabled: raise LookupError("Unknown or disabled job.")
        if not isinstance(principal, PrincipalContext) or not authorize(self.policy, principal, definition.permission, resource_tenant_id=principal.tenant_id):
            raise PermissionError("Job enqueue denied.")
        tenant_id=trusted_tenant_id(tenant) if definition.tenant_scoped else None
        if definition.tenant_scoped and tenant_id != principal.tenant_id: raise PermissionError("Trusted job scopes do not match.")
        clean, raw=_json_payload(payload)
        if "tenant_id" in clean or set(clean) - set(definition.allowed_fields): raise ValueError("Job payload contains forbidden fields.")
        if not isinstance(idempotency_key, str) or not _ID.fullmatch(idempotency_key): raise ValueError("Idempotency key is invalid.")
        material=json.dumps({"job":identifier,"tenant":tenant_id,"key":idempotency_key,"payload":json.loads(raw)}, sort_keys=True, separators=(",", ":"), default=str)
        identity=sha256(material.encode()).hexdigest()
        if identity not in self._invocations:
            self._invocations[identity]=JobInvocation(identity,definition,clean,tenant_id,principal.principal_id,idempotency_key)
        return self._invocations[identity]

    def execute(self, invocation: JobInvocation, *, clock=time.monotonic, sleep=time.sleep):
        if self._invocations.get(invocation.identity) is not invocation or invocation.status not in {JobStatus.QUEUED,JobStatus.FAILED}:
            raise ValueError("Invocation is stale or not executable.")
        started=clock()
        while invocation.attempts < invocation.definition.retry.maximum_attempts:
            invocation.transition(JobStatus.RUNNING); invocation.attempts += 1
            try:
                value=self.registry.handler(invocation.definition.handler)(dict(invocation.payload), invocation.tenant_id)
                if clock()-started > invocation.definition.timeout_seconds: raise TimeoutError("Job timeout exceeded.")
                invocation.result=value; invocation.error_class=None; invocation.transition(JobStatus.SUCCEEDED); return invocation
            except Exception as error:
                invocation.error_class=type(error).__name__; invocation.transition(JobStatus.FAILED)
                if invocation.attempts >= invocation.definition.retry.maximum_attempts: return invocation
                sleep(invocation.definition.retry.delay_seconds)
        return invocation
