"""Tenant-safe deterministic events and hardened webhook primitives."""

from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import hmac, ipaddress, json, re, socket, time
from urllib.parse import urlsplit

from tools.authorization import PolicyContract, PrincipalContext, authorize
from tools.configuration_lifecycle import SecretValue
from tools.jobs import RetryPolicy
from tools.multitenancy import TenantContext, trusted_tenant_id

_ID=re.compile(r"[a-z][a-z0-9_.]{0,126}\Z")
MAX_EVENT_BYTES=64*1024

def _id(value):
    if not isinstance(value,str) or not _ID.fullmatch(value): raise ValueError("Event identifier is invalid.")
    return value
def _payload(value):
    if not isinstance(value,dict): raise ValueError("Event payload must be an object.")
    try: raw=json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)
    except (TypeError,ValueError) as error: raise ValueError("Event payload is not JSON safe.") from error
    if len(raw.encode())>MAX_EVENT_BYTES: raise ValueError("Event payload is too large.")
    if "tenant_id" in value: raise ValueError("Tenant authority cannot come from event payload.")
    return json.loads(raw),raw

@dataclass(frozen=True)
class EventDefinition:
    event_type:str; allowed_fields:tuple[str,...]; version:int=1; tenant_scoped:bool=True
    def __post_init__(self):
        _id(self.event_type)
        if type(self.version) is not int or not 1<=self.version<=100 or type(self.tenant_scoped) is not bool: raise ValueError("Event definition is invalid.")
        if tuple(sorted(set(self.allowed_fields)))!=self.allowed_fields: raise ValueError("Event fields must be unique and sorted.")
        for v in self.allowed_fields:_id(v)
    def canonical_dict(self): return {"allowed_fields":list(self.allowed_fields),"event_type":self.event_type,"tenant_scoped":self.tenant_scoped,"version":self.version}

class EventRegistry:
    def __init__(self,definitions,handlers):
        definitions=tuple(definitions)
        if tuple(sorted(definitions,key=lambda v:v.event_type))!=definitions or len({v.event_type for v in definitions})!=len(definitions): raise ValueError("Events must be unique and sorted.")
        if any(not isinstance(v,EventDefinition) for v in definitions) or set(handlers)-{v.event_type for v in definitions} or any(any(not callable(h) for h in hs) for hs in handlers.values()): raise ValueError("Event registry handlers are invalid.")
        self.definitions=definitions; self.handlers={k:tuple(v) for k,v in handlers.items()}
    def definition(self,value): return next((v for v in self.definitions if v.event_type==value),None)
    def canonical_dict(self): return {"events":[v.canonical_dict() for v in self.definitions],"version":1}
    @property
    def digest(self): return sha256(json.dumps(self.canonical_dict(),sort_keys=True,separators=(",",":")).encode()).hexdigest()

@dataclass(frozen=True)
class EventEnvelope:
    identity:str; event_type:str; version:int; tenant_id:object; payload:dict; correlation_id:str; causation_id:str|None; depth:int

class EventBus:
    def __init__(self,registry:EventRegistry,*,maximum_depth=8):
        if not isinstance(registry,EventRegistry) or type(maximum_depth)is not int or not 1<=maximum_depth<=16: raise ValueError("Event bus is invalid.")
        self.registry=registry; self.maximum_depth=maximum_depth
    def publish(self,event_type,payload,tenant:TenantContext|None,*,correlation_id,causation_id=None,depth=0):
        definition=self.registry.definition(event_type)
        if definition is None: raise LookupError("Unknown event type.")
        tenant_id=trusted_tenant_id(tenant) if definition.tenant_scoped else None
        clean,raw=_payload(payload)
        if set(clean)-set(definition.allowed_fields): raise ValueError("Event contains unknown fields.")
        _id(correlation_id)
        if causation_id is not None and (not isinstance(causation_id,str) or not re.fullmatch(r"[0-9a-f]{64}",causation_id)): raise ValueError("Causation identity is invalid.")
        if type(depth)is not int or not 0<=depth<self.maximum_depth: raise RuntimeError("Event causation depth exceeded.")
        material=json.dumps({"type":event_type,"version":definition.version,"tenant":tenant_id,"payload":json.loads(raw),"correlation":correlation_id,"causation":causation_id,"depth":depth},sort_keys=True,separators=(",",":"),default=str)
        envelope=EventEnvelope(sha256(material.encode()).hexdigest(),event_type,definition.version,tenant_id,clean,correlation_id,causation_id,depth)
        for handler in self.registry.handlers.get(event_type,()): handler(envelope)
        return envelope

def authorize_webhook(policy:PolicyContract,principal:PrincipalContext,tenant:TenantContext,action="create"):
    tenant_id=trusted_tenant_id(tenant)
    if principal.tenant_id!=tenant_id or not authorize(policy,principal,action,resource_tenant_id=tenant_id): raise PermissionError("Webhook operation denied.")
    return tenant_id

def validate_webhook_url(url,*,resolver=socket.getaddrinfo):
    if not isinstance(url,str) or len(url)>2048: raise ValueError("Webhook URL is invalid.")
    try: parsed=urlsplit(url)
    except ValueError as error: raise ValueError("Webhook URL is invalid.") from error
    if parsed.scheme!="https" or not parsed.hostname or parsed.username is not None or parsed.password is not None or parsed.fragment: raise ValueError("Webhook URL must be an HTTPS authority without credentials or fragments.")
    if parsed.hostname.lower() in {"localhost","localhost.localdomain"}: raise ValueError("Webhook destination is not public.")
    try: answers=resolver(parsed.hostname,parsed.port or 443,type=socket.SOCK_STREAM)
    except OSError as error: raise ValueError("Webhook destination cannot be safely resolved.") from error
    addresses=[]
    for answer in answers:
        address=ipaddress.ip_address(answer[4][0].split("%")[0])
        if not address.is_global: raise ValueError("Webhook destination is not public.")
        addresses.append(str(address))
    if not addresses: raise ValueError("Webhook destination cannot be safely resolved.")
    return parsed,tuple(sorted(set(addresses)))

def sign_webhook(secret:SecretValue,delivery_id,timestamp,payload):
    if not isinstance(secret,SecretValue): raise ValueError("A runtime secret is required.")
    _id(delivery_id)
    if type(timestamp)is not int or timestamp<0: raise ValueError("Webhook timestamp is invalid.")
    _,raw=_payload(payload); message=f"{timestamp}.{delivery_id}.{raw}".encode()
    return "sha256="+hmac.new(secret.reveal().encode(),message,sha256).hexdigest()

class ReplayGuard:
    def __init__(self,window_seconds=300):
        if type(window_seconds)is not int or not 1<=window_seconds<=3600: raise ValueError("Replay window is invalid.")
        self.window_seconds=window_seconds; self._seen=set()
    def verify(self,secret,delivery_id,timestamp,payload,signature,*,now=None):
        current=int(time.time() if now is None else now)
        if abs(current-timestamp)>self.window_seconds: raise PermissionError("Webhook timestamp expired.")
        expected=sign_webhook(secret,delivery_id,timestamp,payload)
        if not isinstance(signature,str) or not hmac.compare_digest(expected,signature): raise PermissionError("Webhook signature is invalid.")
        key=(delivery_id,timestamp)
        if key in self._seen: raise PermissionError("Webhook replay rejected.")
        self._seen.add(key); return True

@dataclass(frozen=True)
class WebhookTarget:
    connect_address:str; server_hostname:str; port:int; path:str

class WebhookDelivery:
    def __init__(self,url,retry=RetryPolicy(),*,resolver=socket.getaddrinfo):
        self.parsed,self.addresses=validate_webhook_url(url,resolver=resolver); self.retry=retry
        self.target=WebhookTarget(self.addresses[0],self.parsed.hostname,self.parsed.port or 443,
            self.parsed.path+(('?'+self.parsed.query) if self.parsed.query else ''))
    def deliver(self,sender,payload,headers):
        last=None
        for attempt in range(1,self.retry.maximum_attempts+1):
            try:
                result=sender(self.target,payload,dict(headers),timeout=10,allow_redirects=False)
                if getattr(result,"status",0) not in range(200,300): raise RuntimeError("Webhook endpoint rejected delivery.")
                return attempt
            except (ConnectionError,TimeoutError) as error: last=error
        raise RuntimeError("Webhook delivery exhausted its bounded retry policy.") from last
