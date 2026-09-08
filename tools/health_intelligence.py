"""Bounded, fail-closed runtime health and readiness intelligence."""
from dataclasses import dataclass
from enum import Enum
import math, queue, re, threading, time
from typing import Callable
from tools.authorization import PolicyContract, PrincipalContext, authorize
from tools.multitenancy import TenantContext, trusted_tenant_id
from tools.observability import MetricRegistry, TraceContext, Tracer
from tools.configuration_lifecycle import SecretValue
from tools.structured_logging import CorrelationContext, StructuredLogger, _redact

_CODE = re.compile(r"[a-z][a-z0-9_.]{0,126}\Z")
_PROVIDER_SLOTS = threading.BoundedSemaphore(64)
class HealthState(str, Enum):
    HEALTHY="HEALTHY"; DEGRADED="DEGRADED"; UNHEALTHY="UNHEALTHY"; UNKNOWN="UNKNOWN"
class DiagnosticSeverity(str, Enum):
    INFO="INFO"; WARNING="WARNING"; ERROR="ERROR"

@dataclass(frozen=True)
class DiagnosticFinding:
    code:str; subsystem:str; severity:DiagnosticSeverity; summary:str; remediation:str
    def __post_init__(self):
        if not _CODE.fullmatch(self.code or "") or not _CODE.fullmatch(self.subsystem or "") or not isinstance(self.severity,DiagnosticSeverity): raise ValueError("Diagnostic identity is invalid.")
        if any(not isinstance(v,str) or not v or len(v)>512 or any(ord(c)<32 for c in v) for v in (self.summary,self.remediation)): raise ValueError("Diagnostic text is invalid.")

@dataclass(frozen=True)
class HealthSignal:
    subsystem:str; state:HealthState; required:bool; observed_at:float; finding:DiagnosticFinding|None=None
    def __post_init__(self):
        if not _CODE.fullmatch(self.subsystem or "") or not isinstance(self.state,HealthState) or type(self.required) is not bool: raise ValueError("Health signal is invalid.")
        if isinstance(self.observed_at,bool) or not isinstance(self.observed_at,(int,float)) or not math.isfinite(self.observed_at): raise ValueError("Health observation time is invalid.")
        if self.finding is not None and (not isinstance(self.finding,DiagnosticFinding) or self.finding.subsystem!=self.subsystem): raise ValueError("Health finding is invalid.")

@dataclass(frozen=True)
class HealthCheck:
    subsystem:str; required:bool; provider:Callable[[],HealthSignal]
    def __post_init__(self):
        if not _CODE.fullmatch(self.subsystem or "") or type(self.required) is not bool or not callable(self.provider): raise ValueError("Health provider is invalid.")

@dataclass(frozen=True)
class HealthReport:
    state:HealthState; live:bool; ready:bool; findings:tuple[DiagnosticFinding,...]; tenant_id:str|None=None
    def public_dict(self):
        return {"state":self.state.value,"live":self.live,"ready":self.ready}
    def diagnostic_dict(self):
        value=self.public_dict(); value["findings"]=[{"code":f.code,"subsystem":f.subsystem,"severity":f.severity.value,"summary":f.summary,"remediation":f.remediation} for f in self.findings]; return value

class HealthAggregator:
    def __init__(self,max_age_seconds=60,provider_timeout_seconds=1.0,known_secrets=()):
        if isinstance(max_age_seconds,bool) or not isinstance(max_age_seconds,(int,float)) or not 1<=max_age_seconds<=3600: raise ValueError("Health freshness bound is invalid.")
        if isinstance(provider_timeout_seconds,bool) or not isinstance(provider_timeout_seconds,(int,float)) or not .01<=provider_timeout_seconds<=10: raise ValueError("Health provider timeout is invalid.")
        self.max_age=float(max_age_seconds); self.provider_timeout=float(provider_timeout_seconds); self.secrets=tuple(v.reveal() if isinstance(v,SecretValue) else v for v in known_secrets)
        if any(not isinstance(v,str) for v in self.secrets): raise ValueError("Health redaction values are invalid.")
    def evaluate(self,checks,*,now=None,live=True,tenant=None):
        checks=tuple(checks)
        if not checks or len(checks)>64 or any(not isinstance(c,HealthCheck) for c in checks): raise ValueError("Health providers are invalid.")
        return self.aggregate((self._evaluate_check(c,now) for c in checks),now=now,live=live,tenant=tenant)
    def _evaluate_check(self,check,now):
        result=queue.Queue(maxsize=1)
        observed=time.monotonic() if now is None else now
        if not _PROVIDER_SLOTS.acquire(blocking=False): return self._failed(check,observed,"dependency.capacity","Health provider capacity is exhausted.")
        def invoke():
            try: result.put((True,check.provider()),block=False)
            except Exception: result.put((False,None),block=False)
            finally: _PROVIDER_SLOTS.release()
        worker=threading.Thread(target=invoke,name=f"health-{check.subsystem}",daemon=True); worker.start(); worker.join(self.provider_timeout)
        if worker.is_alive(): return self._failed(check,observed,"dependency.timeout","Health provider timed out.")
        try: succeeded,signal=result.get_nowait()
        except queue.Empty: return self._failed(check,observed,"dependency.failed","Health provider failed.")
        if not succeeded or not isinstance(signal,HealthSignal): return self._failed(check,observed,"dependency.failed","Health provider failed.")
        if signal.subsystem!=check.subsystem or signal.required!=check.required: return self._failed(check,observed,"dependency.invalid","Health provider returned an invalid signal.")
        return signal
    @staticmethod
    def _failed(check,observed,code,summary):
        finding=DiagnosticFinding(code,check.subsystem,DiagnosticSeverity.ERROR,summary,"inspect_dependency")
        return HealthSignal(check.subsystem,HealthState.UNKNOWN,check.required,observed,finding)
    def aggregate(self,signals,*,now=None,live=True,tenant=None):
        signals=tuple(signals); current=time.monotonic() if now is None else now
        if isinstance(current,bool) or not isinstance(current,(int,float)) or not math.isfinite(current): raise ValueError("Health evaluation time is invalid.")
        if type(live) is not bool or not signals or len(signals)>64 or any(not isinstance(v,HealthSignal) for v in signals): raise ValueError("Health signals are invalid.")
        if len({v.subsystem for v in signals})!=len(signals): raise ValueError("Duplicate health subsystem is invalid.")
        findings=[]; required_unhealthy=False; required_unknown=False; optional_bad=False
        for signal in signals:
            stale=current-signal.observed_at>self.max_age or signal.observed_at>current+1
            unknown=stale or signal.state==HealthState.UNKNOWN; unhealthy=signal.state==HealthState.UNHEALTHY
            if signal.required and unhealthy: required_unhealthy=True
            elif signal.required and unknown: required_unknown=True
            elif unhealthy or unknown or signal.state==HealthState.DEGRADED: optional_bad=True
            if signal.finding:
                f=signal.finding; findings.append(DiagnosticFinding(f.code,f.subsystem,f.severity,_redact(f.summary,self.secrets),_redact(f.remediation,self.secrets)))
            elif stale: findings.append(DiagnosticFinding("dependency.stale",signal.subsystem,DiagnosticSeverity.ERROR if signal.required else DiagnosticSeverity.WARNING,"Health observation is stale.","refresh_dependency"))
        state=HealthState.UNHEALTHY if required_unhealthy else HealthState.UNKNOWN if required_unknown else HealthState.DEGRADED if optional_bad else HealthState.HEALTHY
        tenant_id=trusted_tenant_id(tenant) if tenant is not None else None
        return HealthReport(state,live,live and state in {HealthState.HEALTHY,HealthState.DEGRADED},tuple(sorted(findings,key=lambda f:(f.subsystem,f.code))),tenant_id)
    def record(self,report,*,logger=None,log_context=None,metrics=None,tracer=None,trace_context=None):
        if not isinstance(report,HealthReport): raise ValueError("Health report is invalid.")
        if logger is not None:
            if not isinstance(logger,StructuredLogger) or not isinstance(log_context,CorrelationContext): raise ValueError("Health logger is invalid.")
            logger.emit("INFO" if report.ready else "ERROR","health.evaluated","health",log_context,"Runtime health evaluated.",attributes={"state":report.state.value,"ready":report.ready})
        if metrics is not None:
            if not isinstance(metrics,MetricRegistry): raise ValueError("Health metrics registry is invalid.")
            metrics.observe("health.ready",1 if report.ready else 0)
        if tracer is not None:
            if not isinstance(tracer,Tracer) or not isinstance(trace_context,TraceContext): raise ValueError("Health tracing is invalid.")
            tracer.finish(tracer.start("health.evaluate",trace_context,attributes={"state":report.state.value}),report.ready)
    def tenant_view(self,report,principal,tenant,policy):
        if not isinstance(report,HealthReport) or not isinstance(principal,PrincipalContext) or not isinstance(tenant,TenantContext) or not isinstance(policy,PolicyContract): raise ValueError("Diagnostic access context is invalid.")
        tenant_id=trusted_tenant_id(tenant)
        if report.tenant_id is None or report.tenant_id!=tenant_id: raise PermissionError("Diagnostic tenant mismatch.")
        if not authorize(policy,principal,"read",resource_tenant_id=tenant_id): raise PermissionError("Diagnostic access denied.")
        return report.diagnostic_dict()
