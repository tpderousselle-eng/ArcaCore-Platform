"""Deterministic resource declarations and bounded runtime usage signals."""
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json,math,re
from tools.authorization import PolicyContract,PrincipalContext,authorize
from tools.health_intelligence import DiagnosticFinding,DiagnosticSeverity,HealthSignal,HealthState
from tools.multitenancy import TenantContext,trusted_tenant_id
from tools.observability import MetricRegistry,TraceContext,Tracer
from tools.structured_logging import CorrelationContext,StructuredLogger

_NAME=re.compile(r"[a-z][a-z0-9_.]{0,126}\Z")
_UNITS=frozenset({"millicores","mib","gib","bytes","workers","items","requests","input_tokens","output_tokens","cached_tokens","milliseconds"})
MAX_VALUE=2**63-1
class ResourceKind(str,Enum):
 CPU="cpu";MEMORY="memory";STORAGE="storage";WORKERS="workers";QUEUE="queue";DATABASE="database";OBJECT_STORAGE="object_storage";NETWORK="network";AI="ai"
class SignalClass(str,Enum):CONFIGURED="configured";OBSERVED="observed";ESTIMATED="estimated"
@dataclass(frozen=True)
class ResourceRequirement:
 name:str;kind:ResourceKind;quantity:int;unit:str;warning_at:int|None=None
 def __post_init__(self):
  if not _NAME.fullmatch(self.name or "") or not isinstance(self.kind,ResourceKind) or self.unit not in _UNITS:raise ValueError("Resource requirement is invalid.")
  if isinstance(self.quantity,bool) or not isinstance(self.quantity,int) or not 0<=self.quantity<=MAX_VALUE:raise ValueError("Resource quantity is invalid.")
  if self.warning_at is not None and (isinstance(self.warning_at,bool) or not isinstance(self.warning_at,int) or not 0<=self.warning_at<=self.quantity):raise ValueError("Resource threshold is invalid.")
 def canonical_dict(self):return {"kind":self.kind.value,"name":self.name,"quantity":self.quantity,"unit":self.unit,"warning_at":self.warning_at}
@dataclass(frozen=True)
class ResourceProfile:
 requirements:tuple[ResourceRequirement,...]
 def __post_init__(self):
  if not self.requirements or len(self.requirements)>32 or any(not isinstance(v,ResourceRequirement) for v in self.requirements):raise ValueError("Resource profile is invalid.")
  names=[v.name for v in self.requirements]
  if names!=sorted(set(names)):raise ValueError("Resource requirements must be uniquely ordered.")
 def canonical_dict(self):return {"requirements":[v.canonical_dict() for v in self.requirements]}
 @property
 def digest(self):return sha256(json.dumps(self.canonical_dict(),sort_keys=True,separators=(",",":")).encode()).hexdigest()
@dataclass(frozen=True)
class ResourceObservation:
 name:str;kind:ResourceKind;quantity:float;unit:str;observed_at:float
 def __post_init__(self):
  if not _NAME.fullmatch(self.name or "") or not isinstance(self.kind,ResourceKind) or self.unit not in _UNITS:raise ValueError("Resource observation is invalid.")
  for value in (self.quantity,self.observed_at):
   if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError("Resource observation value is invalid.")
  if self.quantity<0 or self.quantity>MAX_VALUE:raise ValueError("Resource observation value is invalid.")
@dataclass(frozen=True)
class CostSignal:
 classification:SignalClass;quantity:float;unit:str;provenance:str;pricing_reference:str|None=None;currency:str|None=None
 def __post_init__(self):
  if not isinstance(self.classification,SignalClass) or self.unit not in _UNITS or not _NAME.fullmatch(self.provenance or ""):raise ValueError("Cost signal is invalid.")
  if isinstance(self.quantity,bool) or not isinstance(self.quantity,(int,float)) or not math.isfinite(self.quantity) or not 0<=self.quantity<=MAX_VALUE:raise ValueError("Cost quantity is invalid.")
  if self.currency is not None and (not re.fullmatch(r"[A-Z]{3}",self.currency) or not self.pricing_reference):raise ValueError("Currency cost requires trusted pricing provenance.")
  if self.pricing_reference is not None and not _NAME.fullmatch(self.pricing_reference):raise ValueError("Pricing reference is invalid.")
@dataclass(frozen=True)
class AIUsage:
 logical_model:str;requests:int=0;input_tokens:int=0;output_tokens:int=0;cached_tokens:int=0;duration_ms:int=0
 def __post_init__(self):
  if not _NAME.fullmatch(self.logical_model or ""):raise ValueError("AI usage identity is invalid.")
  for value in (self.requests,self.input_tokens,self.output_tokens,self.cached_tokens,self.duration_ms):
   if isinstance(value,bool) or not isinstance(value,int) or not 0<=value<=MAX_VALUE:raise ValueError("AI usage count is invalid.")
 def safe_dict(self):return {"cached_tokens":self.cached_tokens,"duration_ms":self.duration_ms,"input_tokens":self.input_tokens,"logical_model":self.logical_model,"output_tokens":self.output_tokens,"requests":self.requests}
@dataclass(frozen=True)
class ResourceReport:
 profile_digest:str;observations:tuple[ResourceObservation,...];cost_signals:tuple[CostSignal,...];ai_usage:tuple[AIUsage,...];capacity_state:HealthState;tenant_id:object|None=None
 def public_dict(self):return {"capacity_state":self.capacity_state.value,"profile_digest":self.profile_digest}
 def safe_dict(self):
  return {**self.public_dict(),"observations":[{"kind":v.kind.value,"name":v.name,"quantity":v.quantity,"unit":v.unit} for v in self.observations],"cost_signals":[{"classification":v.classification.value,"currency":v.currency,"pricing_reference":v.pricing_reference,"provenance":v.provenance,"quantity":v.quantity,"unit":v.unit} for v in self.cost_signals],"ai_usage":[v.safe_dict() for v in self.ai_usage]}
class ResourceIntelligence:
 def __init__(self,profile):
  if not isinstance(profile,ResourceProfile):raise ValueError("Resource profile is required.")
  self.profile=profile;self.requirements={v.name:v for v in profile.requirements}
 def report(self,observations=(),cost_signals=(),ai_usage=(),*,tenant=None):
  observations=tuple(observations);cost_signals=tuple(cost_signals);ai_usage=tuple(ai_usage)
  if len(observations)>64 or len(cost_signals)>32 or len(ai_usage)>32 or any(not isinstance(v,ResourceObservation) for v in observations) or any(not isinstance(v,CostSignal) for v in cost_signals) or any(not isinstance(v,AIUsage) for v in ai_usage):raise ValueError("Resource report is invalid.")
  for observation in observations:
   requirement=self.requirements.get(observation.name)
   if requirement is None or requirement.kind!=observation.kind or requirement.unit!=observation.unit:raise ValueError("Resource observation is undeclared.")
  tenant_id=trusted_tenant_id(tenant) if tenant is not None else None
  pressured=any(self.requirements[v.name].warning_at is not None and v.quantity>=self.requirements[v.name].warning_at for v in observations)
  return ResourceReport(self.profile.digest,tuple(sorted(observations,key=lambda v:v.name)),cost_signals,ai_usage,HealthState.DEGRADED if pressured else HealthState.HEALTHY,tenant_id)
 def capacity_signal(self,report,*,observed_at):
  if not isinstance(report,ResourceReport) or report.profile_digest!=self.profile.digest:raise ValueError("Resource report provenance is invalid.")
  pressured=[v for v in report.observations if self.requirements[v.name].warning_at is not None and v.quantity>=self.requirements[v.name].warning_at]
  finding=DiagnosticFinding("capacity.pressure","capacity",DiagnosticSeverity.WARNING,"Configured capacity threshold reached.","inspect_capacity") if pressured else None
  return HealthSignal("capacity",HealthState.DEGRADED if pressured else HealthState.HEALTHY,False,observed_at,finding)
 def tenant_view(self,report,principal,tenant,policy):
  if not isinstance(report,ResourceReport) or not isinstance(principal,PrincipalContext) or not isinstance(tenant,TenantContext) or not isinstance(policy,PolicyContract):raise ValueError("Resource access context is invalid.")
  tenant_id=trusted_tenant_id(tenant)
  if report.tenant_id!=tenant_id or not authorize(policy,principal,"read",resource_tenant_id=tenant_id):raise PermissionError("Resource report access denied.")
  return report.safe_dict()
 def record(self,report,*,logger=None,log_context=None,metrics=None,tracer=None,trace_context=None):
  if not isinstance(report,ResourceReport):raise ValueError("Resource report is invalid.")
  if logger is not None:
   if not isinstance(logger,StructuredLogger) or not isinstance(log_context,CorrelationContext):raise ValueError("Resource logger is invalid.")
   logger.emit("INFO","resource.observed","resource",log_context,"Resource capacity observed.",{"state":report.capacity_state.value})
  if metrics is not None:
   if not isinstance(metrics,MetricRegistry):raise ValueError("Resource metrics are invalid.")
   metrics.observe("resource.observations",len(report.observations))
  if tracer is not None:
   if not isinstance(tracer,Tracer) or not isinstance(trace_context,TraceContext):raise ValueError("Resource tracing is invalid.")
   tracer.finish(tracer.start("resource.observe",trace_context,attributes={"state":report.capacity_state.value}),True)
