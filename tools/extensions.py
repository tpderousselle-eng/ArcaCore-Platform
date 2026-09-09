"""Deterministic, capability-limited extension contracts."""
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json, re
from threading import BoundedSemaphore, Lock, Thread
from tools.authorization import SUPPORTED_ACTIONS, authorize
from tools.configuration_lifecycle import SecretReference
from tools.multitenancy import trusted_tenant_id

_ID=re.compile(r"[a-z][a-z0-9_.-]{0,126}\Z"); _KEY=re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
_VER=re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[a-z0-9.-]{1,32})?\Z")
_RESERVED=frozenset("command shell python code module import path environment env secret token credential release_gate security_gate".split())
def _raw(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
def _strings(v,label):
    if not isinstance(v,tuple) or len(v)>32 or tuple(sorted(set(v)))!=v or any(not isinstance(x,str) or not _KEY.fullmatch(x) for x in v): raise ValueError(f"{label} must be a bounded, sorted identifier tuple.")
def _enums(v,t,label):
    if not isinstance(v,tuple) or not v or len(v)>32 or any(not isinstance(x,t) for x in v) or tuple(sorted(set(v),key=lambda x:x.value))!=v: raise ValueError(f"{label} must be a non-empty, sorted enum tuple.")

class ExtensionCapability(str,Enum):
    READ_MANIFEST="read_manifest"; CONTRIBUTE_DIAGNOSTICS="contribute_diagnostics"; CONTRIBUTE_RESOURCE_METADATA="contribute_resource_metadata"; OBSERVE_RUNTIME="observe_runtime"; CONTRIBUTE_INTEGRATION_METADATA="contribute_integration_metadata"
class HookPoint(str,Enum):
    PRE_GENERATION_INSPECTION="pre_generation_inspection"; POST_GENERATION_VALIDATION="post_generation_validation"; PRE_RUNTIME_VALIDATION="pre_runtime_validation"; POST_RUNTIME_OBSERVATION="post_runtime_observation"; DIAGNOSTICS_ENRICHMENT="diagnostics_enrichment"; RESOURCE_METADATA_ENRICHMENT="resource_metadata_enrichment"; DEPLOYMENT_METADATA_PREPARATION="deployment_metadata_preparation"
class ExtensionScope(str,Enum): TENANT="tenant"; GLOBAL="global"
class FailurePolicy(str,Enum): MANDATORY="mandatory"; OPTIONAL="optional"
class ExtensionStatus(str,Enum): SUCCESS="success"; DEGRADED="degraded"; FAILED="failed"

@dataclass(frozen=True)
class ExtensionManifest:
    extension_id:str; version:str; api_version:str; scope:ExtensionScope
    capabilities:tuple[ExtensionCapability,...]; hooks:tuple[HookPoint,...]
    permissions:tuple[str,...]=(); configuration_references:tuple[str,...]=()
    secret_references:tuple[SecretReference,...]=(); failure_policy:FailurePolicy=FailurePolicy.MANDATORY
    def __post_init__(self):
        if not isinstance(self.extension_id,str) or not _ID.fullmatch(self.extension_id): raise ValueError("Extension id is invalid.")
        if not isinstance(self.version,str) or not _VER.fullmatch(self.version): raise ValueError("Extension version must be semantic.")
        if self.api_version!="v1": raise ValueError("Unsupported extension API version.")
        if not isinstance(self.scope,ExtensionScope) or not isinstance(self.failure_policy,FailurePolicy): raise ValueError("Extension policy is invalid.")
        _enums(self.capabilities,ExtensionCapability,"Capabilities"); _enums(self.hooks,HookPoint,"Hooks"); _strings(self.permissions,"Permissions"); _strings(self.configuration_references,"Configuration references")
        if not self.permissions or any(value not in SUPPORTED_ACTIONS for value in self.permissions): raise ValueError("Extension permissions must be declared supported actions.")
        if not isinstance(self.secret_references,tuple) or len(self.secret_references)>32 or any(not isinstance(x,SecretReference) for x in self.secret_references): raise ValueError("Secret references must be validated references.")
        ordered=tuple(sorted(self.secret_references,key=lambda x:_raw(x.canonical_dict())))
        if ordered!=self.secret_references or len({_raw(x.canonical_dict()) for x in ordered})!=len(ordered): raise ValueError("Secret references must be unique and sorted.")
    def canonical_dict(self):
        return {"api_version":self.api_version,"capabilities":[x.value for x in self.capabilities],"configuration_references":list(self.configuration_references),"extension_id":self.extension_id,"failure_policy":self.failure_policy.value,"hooks":[x.value for x in self.hooks],"permissions":list(self.permissions),"scope":self.scope.value,"secret_references":[x.canonical_dict() for x in self.secret_references],"version":self.version}
    @property
    def digest(self): return sha256(_raw(self.canonical_dict())).hexdigest()

@dataclass(frozen=True)
class ExtensionContext:
    hook:HookPoint; tenant_id:object; correlation_id:str; manifest_digest:str; configuration_references:tuple[str,...]=()
    def __post_init__(self):
        if not isinstance(self.hook,HookPoint) or self.tenant_id is None: raise ValueError("Hook and tenant are required.")
        if not isinstance(self.correlation_id,str) or not _ID.fullmatch(self.correlation_id): raise ValueError("Correlation id is invalid.")
        if not isinstance(self.manifest_digest,str) or not re.fullmatch(r"[0-9a-f]{64}",self.manifest_digest): raise ValueError("Manifest digest is invalid.")
        _strings(self.configuration_references,"Configuration references")

@dataclass(frozen=True)
class ExtensionResult:
    status:ExtensionStatus; contributions:tuple[tuple[str,object],...]=(); message:str=""
    def __post_init__(self):
        if not isinstance(self.status,ExtensionStatus) or not isinstance(self.message,str) or len(self.message)>1024: raise ValueError("Extension result status or message is invalid.")
        if not isinstance(self.contributions,tuple) or len(self.contributions)>32 or tuple(sorted(self.contributions,key=lambda x:x[0]))!=self.contributions: raise ValueError("Contributions must be bounded and sorted.")
        seen=set()
        for item in self.contributions:
            if not isinstance(item,tuple) or len(item)!=2: raise ValueError("Contribution is malformed.")
            k,v=item
            if not isinstance(k,str) or not _KEY.fullmatch(k) or k in _RESERVED or k in seen: raise ValueError("Contribution key is unsafe.")
            seen.add(k)
            if isinstance(v,str):
                if len(v)>1024: raise ValueError("Contribution is too large.")
            elif type(v) not in (bool,int) or type(v) is int and abs(v)>2**63-1: raise ValueError("Contribution type is unsupported.")
        if len(_raw(self.canonical_dict()))>8192: raise ValueError("Extension result exceeds size limit.")
    def canonical_dict(self): return {"contributions":dict(self.contributions),"message":self.message,"status":self.status.value}

class ExtensionInvocationError(RuntimeError): pass
class ExtensionRegistry:
    def __init__(self,*,maximum_concurrency=16,trusted_global_extensions=()):
        if type(maximum_concurrency) is not int or not 1<=maximum_concurrency<=32: raise ValueError("Concurrency limit is invalid.")
        self._entries={}; self._sem=BoundedSemaphore(maximum_concurrency); self._lock=Lock(); self._active=set()
        if not isinstance(trusted_global_extensions,tuple) or len(trusted_global_extensions)>32: raise ValueError("Trusted global extensions must be a bounded tuple.")
        for entry in trusted_global_extensions:
            if not isinstance(entry,tuple) or len(entry)!=2: raise ValueError("Trusted global extension entry is malformed.")
            manifest,implementation=entry
            if not isinstance(manifest,ExtensionManifest) or manifest.scope is not ExtensionScope.GLOBAL or not callable(implementation): raise ValueError("Trusted global extension entry is invalid.")
            if manifest.extension_id in {key[1] for key in self._entries}: raise ValueError("Duplicate extension registration.")
            self._entries[(None,manifest.extension_id)]=(manifest,implementation)
    def register(self,manifest,implementation,*,principal,policy,tenant=None):
        if not isinstance(manifest,ExtensionManifest) or not callable(implementation): raise ValueError("Validated manifest and trusted callable required.")
        if manifest.scope is ExtensionScope.GLOBAL: raise PermissionError("Global extensions require trusted host pre-registration.")
        tenant_id=trusted_tenant_id(tenant)
        if not authorize(policy,principal,"create",resource_tenant_id=tenant_id): raise PermissionError("Extension registration denied.")
        key=(tenant_id,manifest.extension_id)
        with self._lock:
            if manifest.extension_id in {entry_key[1] for entry_key in self._entries}: raise ValueError("Duplicate extension registration.")
            self._entries[key]=(manifest,implementation)
    def manifests(self,*,principal,policy,tenant):
        tenant_id=trusted_tenant_id(tenant)
        if not authorize(policy,principal,"read",resource_tenant_id=tenant_id): raise PermissionError("Extension discovery denied.")
        with self._lock: values=[m for (t,_),(m,_) in self._entries.items() if t is None or t==tenant_id]
        return tuple(sorted(values,key=lambda x:x.extension_id))
    def invoke(self,hook,capability,*,principal,policy,tenant,correlation_id,timeout_seconds=1.0):
        if not isinstance(hook,HookPoint) or not isinstance(capability,ExtensionCapability): raise ValueError("Unsupported hook or capability.")
        if type(timeout_seconds) not in (int,float) or not .01<=timeout_seconds<=5: raise ValueError("Timeout must be bounded.")
        tenant_id=trusted_tenant_id(tenant)
        if not authorize(policy,principal,"read",resource_tenant_id=tenant_id): raise PermissionError("Extension invocation denied.")
        with self._lock: entries=[e for (t,_),e in self._entries.items() if (t is None or t==tenant_id) and hook in e[0].hooks and capability in e[0].capabilities]
        entries.sort(key=lambda e:e[0].extension_id)
        for manifest,_ in entries:
            if any(not authorize(policy,principal,permission,resource_tenant_id=tenant_id) for permission in manifest.permissions): raise PermissionError("Extension required permission denied.")
        return tuple(self._one(e,hook,tenant_id,correlation_id,timeout_seconds) for e in entries)
    def _one(self,entry,hook,tenant,correlation,timeout):
        manifest,fn=entry; key=(tenant,manifest.extension_id)
        with self._lock:
            if key in self._active: return self._failure(manifest,"Recursive extension invocation denied.")
            self._active.add(key)
        if not self._sem.acquire(timeout=timeout):
            with self._lock:self._active.discard(key)
            return self._failure(manifest,"Extension capacity unavailable.")
        box=[]; context=ExtensionContext(hook,tenant,correlation,manifest.digest,manifest.configuration_references)
        def run():
            try:
                try: box.append((True,fn(context)))
                except Exception: box.append((False,None))
            finally:
                self._sem.release()
                with self._lock:self._active.discard(key)
        thread=Thread(target=run,daemon=True,name="arcacore-extension"); thread.start(); thread.join(timeout)
        if thread.is_alive(): return self._failure(manifest,"Extension invocation timed out.")
        if not box or not box[0][0]: return self._failure(manifest,"Extension invocation failed.")
        result=box[0][1]
        try:
            if not isinstance(result,ExtensionResult): raise ValueError
            ExtensionResult(result.status,result.contributions,result.message)
        except ValueError:return self._failure(manifest,"Extension result validation failed.")
        if result.status is ExtensionStatus.FAILED and manifest.failure_policy is FailurePolicy.MANDATORY: raise ExtensionInvocationError("Mandatory extension reported failure.")
        return result
    @staticmethod
    def _failure(manifest,message):
        if manifest.failure_policy is FailurePolicy.MANDATORY: raise ExtensionInvocationError(message)
        return ExtensionResult(ExtensionStatus.DEGRADED,(),message)
