"""Vendor-neutral bounded metrics and tracing primitives."""
from dataclasses import dataclass,field
from enum import Enum
from hashlib import sha256
import json,math,re
from tools.configuration_lifecycle import SecretValue
from tools.structured_logging import _redact
_NAME=re.compile(r"[a-z][a-z0-9_.]{0,126}\Z");_HEX=re.compile(r"[0-9a-f]+\Z")
ALLOWED_LABELS=frozenset({"kind","method","operation","outcome","state","status","subsystem"})
FORBIDDEN_TRACE_KEYS=frozenset({"body","request_body","response_body","sql","sql_parameters","db.statement","http.request.body","http.response.body"})
class MetricKind(str,Enum):COUNTER="counter";GAUGE="gauge";HISTOGRAM="histogram"
@dataclass(frozen=True)
class MetricDefinition:
 name:str;kind:MetricKind;labels:tuple[str,...]=();buckets:tuple[float,...]=()
 def __post_init__(self):
  if not _NAME.fullmatch(self.name or "") or not isinstance(self.kind,MetricKind):raise ValueError("Metric definition is invalid.")
  if tuple(sorted(set(self.labels)))!=self.labels or any(not _NAME.fullmatch(v) or v not in ALLOWED_LABELS for v in self.labels):raise ValueError("Metric labels are unsafe.")
  if self.kind==MetricKind.HISTOGRAM and (not self.buckets or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in self.buckets) or tuple(sorted(set(self.buckets)))!=self.buckets):raise ValueError("Histogram buckets are invalid.")
  if self.kind!=MetricKind.HISTOGRAM and self.buckets:raise ValueError("Only histograms have buckets.")
 def canonical_dict(self):return {"buckets":list(self.buckets),"kind":self.kind.value,"labels":list(self.labels),"name":self.name}
 @property
 def digest(self):return sha256(json.dumps(self.canonical_dict(),sort_keys=True,separators=(",",":")).encode()).hexdigest()
class MetricRegistry:
 def __init__(self,definitions,max_series=128):
  definitions=tuple(definitions);self.definitions={v.name:v for v in definitions};self.values={};self.max_series=max_series
  if len(self.definitions)!=len(definitions) or any(not isinstance(v,MetricDefinition) for v in definitions) or not 1<=max_series<=1024:raise ValueError("Metric registry is invalid.")
 def observe(self,name,value=1,labels=None):
  definition=self.definitions.get(name);labels=labels or {}
  if definition is None or set(labels)!=set(definition.labels) or any(not isinstance(v,str) or len(v)>64 or any(ord(c)<32 for c in v) for v in labels.values()):raise ValueError("Metric observation is invalid.")
  if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError("Metric value is invalid.")
  key=(name,tuple(sorted(labels.items())))
  if key not in self.values and len(self.values)>=self.max_series:raise ValueError("Metric cardinality limit exceeded.")
  if definition.kind==MetricKind.COUNTER and value<0:raise ValueError("Counter cannot decrease.")
  if definition.kind==MetricKind.COUNTER:self.values[key]=self.values.get(key,0)+value
  elif definition.kind==MetricKind.GAUGE:self.values[key]=value
  else:
   aggregate=self.values.setdefault(key,{"count":0,"sum":0.0,"buckets":[0 for _ in definition.buckets]})
   aggregate["count"]+=1;aggregate["sum"]+=value
   for index,bucket in enumerate(definition.buckets):
    if value<=bucket:aggregate["buckets"][index]+=1
  return self.values[key]
@dataclass(frozen=True)
class TraceContext:
 trace_id:str;span_id:str
 def __post_init__(self):
  if len(self.trace_id)!=32 or len(self.span_id)!=16 or not _HEX.fullmatch(self.trace_id) or not _HEX.fullmatch(self.span_id):raise ValueError("Trace context is invalid.")
class SpanStatus(str,Enum):UNSET="UNSET";OK="OK";ERROR="ERROR"
@dataclass
class Span:
 context:TraceContext;name:str;parent_span_id:str|None;depth:int;attributes:dict;status:SpanStatus=SpanStatus.UNSET
 def finish(self,success):self.status=SpanStatus.OK if success else SpanStatus.ERROR;return self
class LocalTraceExporter:
 def __init__(self,max_spans=1024):
  if isinstance(max_spans,bool) or not isinstance(max_spans,int) or not 1<=max_spans<=4096:raise ValueError("Trace export bound is invalid.")
  self.max_spans=max_spans;self.spans=[]
 def export(self,span):
  if len(self.spans)>=self.max_spans:raise ValueError("Trace export buffer is full.")
  self.spans.append(span)
class Tracer:
 def __init__(self,exporter,max_depth=16,known_secrets=()):
  if not isinstance(exporter,LocalTraceExporter) or isinstance(max_depth,bool) or not isinstance(max_depth,int) or not 1<=max_depth<=64:raise ValueError("Tracer bounds are invalid.")
  self.exporter=exporter;self.max_depth=max_depth;self.secrets=tuple(v.reveal() if isinstance(v,SecretValue) else v for v in known_secrets)
  if any(not isinstance(v,str) for v in self.secrets):raise ValueError("Trace redaction values are invalid.")
 def start(self,name,context,*,parent=None,attributes=None):
  if not _NAME.fullmatch(name or "") or not isinstance(context,TraceContext):raise ValueError("Span is invalid.")
  if parent is not None and (not isinstance(parent,Span) or parent.context.trace_id!=context.trace_id):raise ValueError("Trace parent is invalid.")
  depth=0 if parent is None else parent.depth+1
  if depth>=self.max_depth:raise ValueError("Trace nesting limit exceeded.")
  safe=_redact(attributes or {},self.secrets)
  pending=[safe]
  while pending:
   value=pending.pop()
   if isinstance(value,dict):
    if any(key.lower() in FORBIDDEN_TRACE_KEYS or "sql" in key.lower() or key.lower().endswith("body") for key in value):raise ValueError("Sensitive span attribute is forbidden.")
    pending.extend(value.values())
   elif isinstance(value,list):pending.extend(value)
  return Span(context,name,parent.context.span_id if parent else None,depth,safe)
 def finish(self,span,success):span.finish(success);self.exporter.export(span);return span
