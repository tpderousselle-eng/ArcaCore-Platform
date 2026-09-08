"""Bounded structured logging with recursive secret redaction."""
from dataclasses import dataclass
from datetime import datetime,timezone
from enum import Enum
from hashlib import sha256
import json,re
from tools.configuration_lifecycle import SecretValue
from tools.multitenancy import TenantContext,trusted_tenant_id

_NAME=re.compile(r"[a-z][a-z0-9_.-]{0,126}\Z"); _CORR=re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_SENSITIVE=frozenset({"authorization","password","token","access_token","api_key","secret","private_key","database_password","email","phone","address","full_name"})
_RESERVED_ATTRIBUTES=frozenset({"tenant","tenant_id","correlation_id","request_id"})
MAX_ATTRIBUTES=32; MAX_SERIALIZED=16384
class LogLevel(str,Enum): DEBUG="DEBUG"; INFO="INFO"; WARNING="WARNING"; ERROR="ERROR"
def correlation_id(value):
    if not isinstance(value,str) or not _CORR.fullmatch(value): raise ValueError("Correlation identifier is invalid.")
    return value
def _text(value,label):
    if not isinstance(value,str) or not value or len(value)>1024 or any(ord(c)<32 or ord(c)==127 for c in value): raise ValueError(f"{label} is invalid.")
    return value
def _redact(value,secrets,depth=0):
    if depth>6: raise ValueError("Log attributes are too deeply nested.")
    if isinstance(value,SecretValue): return "[REDACTED]"
    if isinstance(value,str):
        result=value
        for secret in secrets:
            if secret: result=result.replace(secret,"[REDACTED]")
        return result
    if value is None or type(value) in (bool,int,float): return value
    if isinstance(value,(list,tuple)):
        if len(value)>32: raise ValueError("Log attribute collection is too large.")
        return [_redact(v,secrets,depth+1) for v in value]
    if isinstance(value,dict):
        if len(value)>MAX_ATTRIBUTES: raise ValueError("Too many log attributes.")
        out={}
        for k in sorted(value):
            if not isinstance(k,str) or not _NAME.fullmatch(k) or k.lower() in _RESERVED_ATTRIBUTES: raise ValueError("Log attribute name is invalid.")
            out[k]="[REDACTED]" if k.lower() in _SENSITIVE else _redact(value[k],secrets,depth+1)
        return out
    raise ValueError("Log attribute type is unsupported.")
@dataclass(frozen=True)
class CorrelationContext:
    correlation_id:str; request_id:str|None=None
    def __post_init__(self): correlation_id(self.correlation_id); self.request_id is None or correlation_id(self.request_id)
@dataclass(frozen=True)
class LogSchema:
    version:int=1
    def canonical_dict(self): return {"fields":["application","attributes","correlation_id","event","level","message","module","request_id","tenant","timestamp"],"version":self.version}
    @property
    def digest(self): return sha256(json.dumps(self.canonical_dict(),sort_keys=True,separators=(",",":")).encode()).hexdigest()
@dataclass(frozen=True)
class LogEvent:
    timestamp:str; level:LogLevel; event:str; application:str; module:str; correlation_id:str; request_id:str|None; tenant:object; message:str; attributes:dict
    def canonical_dict(self): return {"application":self.application,"attributes":self.attributes,"correlation_id":self.correlation_id,"event":self.event,"level":self.level.value,"message":self.message,"module":self.module,"request_id":self.request_id,"tenant":self.tenant,"timestamp":self.timestamp}
class StructuredLogger:
    def __init__(self,application,sink,*,known_secrets=()):
        _text(application,"Application");
        if not callable(sink): raise ValueError("Log sink is invalid.")
        self.application=application;self.sink=sink;self.secrets=tuple(v.reveal() if isinstance(v,SecretValue) else v for v in known_secrets)
        if any(not isinstance(v,str) for v in self.secrets): raise ValueError("Redaction values are invalid.")
    def emit(self,level,event,module,context,message,attributes=None,*,tenant=None,now=None):
        try: level=LogLevel(level)
        except ValueError as error: raise ValueError("Log level is invalid.") from error
        if not _NAME.fullmatch(event or "") or not _NAME.fullmatch(module or ""): raise ValueError("Log identity is invalid.")
        if not isinstance(context,CorrelationContext): raise ValueError("Correlation context is required.")
        tenant_id=trusted_tenant_id(tenant) if tenant is not None else None
        safe_message=_redact(_text(message,"Log message"),self.secrets); safe_attributes=_redact(attributes or {},self.secrets)
        stamp=(now or datetime.now(timezone.utc)).isoformat().replace("+00:00","Z")
        event_value=LogEvent(stamp,level,event,self.application,module,context.correlation_id,context.request_id,tenant_id,safe_message,safe_attributes)
        raw=json.dumps(event_value.canonical_dict(),sort_keys=True,separators=(",",":"),default=str)
        if len(raw.encode())>MAX_SERIALIZED: raise ValueError("Structured log event is too large.")
        self.sink(raw); return event_value
