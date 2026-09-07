"""Contained, tenant-safe object storage contracts and local provider."""

from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json, os, re, tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from tools.authorization import PolicyContract, PrincipalContext, authorize
from tools.multitenancy import TenantContext, trusted_tenant_id

_SEGMENT=re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

def object_key(value):
    if not isinstance(value,str) or not value or len(value)>512 or "\0" in value or "\\" in value or unquote(value)!=value:
        raise ValueError("Object key is invalid.")
    if re.match(r"^[A-Za-z]:",value) or value.startswith(("/","//")): raise ValueError("Object key must be logical, not absolute.")
    path=PurePosixPath(value)
    if path.as_posix()!=value or any(part in {"",".",".."} or not _SEGMENT.fullmatch(part) for part in path.parts): raise ValueError("Object key escapes its namespace.")
    return value

@dataclass(frozen=True)
class StorageMetadata:
    object_id:str; key:str; tenant_digest:str; display_name:str|None; content_type:str; size:int; checksum:str
    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{64}",self.object_id) or not re.fullmatch(r"[0-9a-f]{64}",self.tenant_digest) or not re.fullmatch(r"[0-9a-f]{64}",self.checksum): raise ValueError("Storage metadata identity is invalid.")
        object_key(self.key)
        if self.display_name is not None and (not isinstance(self.display_name,str) or not self.display_name or len(self.display_name)>255 or any(v in self.display_name for v in "\0\r\n")): raise ValueError("Display name is invalid.")
        if not isinstance(self.content_type,str) or not re.fullmatch(r"[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+",self.content_type) or type(self.size)is not int or self.size<0: raise ValueError("Storage metadata is invalid.")
    def canonical_dict(self): return {"checksum":self.checksum,"content_type":self.content_type,"display_name":self.display_name,"key":self.key,"object_id":self.object_id,"size":self.size,"tenant_digest":self.tenant_digest}
    def canonical_json(self): return json.dumps(self.canonical_dict(),sort_keys=True,separators=(",",":"))+"\n"

class LocalStorageProvider:
    def __init__(self,root,max_object_size=10*1024*1024):
        self.root=Path(root).resolve()
        if type(max_object_size)is not int or not 1<=max_object_size<=1024*1024*1024: raise ValueError("Maximum object size is invalid.")
        self.max_object_size=max_object_size; self.root.mkdir(parents=True,exist_ok=True); self._metadata={}
        if self.root.is_symlink(): raise ValueError("Storage root cannot be a symbolic link.")
    def _scope(self,tenant_id): return sha256(("arcacore-tenant/v1:"+str(tenant_id)).encode()).hexdigest()
    def _path(self,tenant_id,key):
        key=object_key(key); scope=self._scope(tenant_id); current=self.root/scope
        current.mkdir(exist_ok=True)
        if current.is_symlink(): raise ValueError("Storage namespace contains a symbolic link.")
        for part in PurePosixPath(key).parts:
            current=current/part
            if current.exists() and current.is_symlink(): raise ValueError("Storage path contains a symbolic link.")
        current.resolve(strict=False).relative_to(self.root)
        return current,scope
    def _allowed(self,policy,principal,tenant_id,action):
        if not isinstance(principal,PrincipalContext) or not authorize(policy,principal,action,resource_tenant_id=tenant_id): raise PermissionError("Storage operation denied.")
    def upload(self,key,stream,principal,tenant,policy,*,display_name=None,content_type="application/octet-stream",replace=False):
        tenant_id=trusted_tenant_id(tenant); self._allowed(policy,principal,tenant_id,"update" if replace else "create")
        path,scope=self._path(tenant_id,key)
        if path.exists() and not replace: raise FileExistsError("Object already exists.")
        path.parent.mkdir(parents=True,exist_ok=True)
        for parent in (path.parent,*path.parent.parents):
            if parent==self.root.parent: break
            if parent.is_symlink(): raise ValueError("Storage path contains a symbolic link.")
        digest=sha256(); size=0; temporary=None
        try:
            fd,temporary=tempfile.mkstemp(prefix=".arcacore-",dir=path.parent); os.close(fd)
            with open(temporary,"wb") as output:
                while True:
                    chunk=stream.read(64*1024)
                    if not chunk: break
                    if not isinstance(chunk,(bytes,bytearray)): raise ValueError("Object stream must yield bytes.")
                    size+=len(chunk)
                    if size>self.max_object_size: raise ValueError("Object exceeds maximum size.")
                    digest.update(chunk); output.write(chunk)
                output.flush(); os.fsync(output.fileno())
            if path.exists() and path.is_symlink(): raise ValueError("Storage target became a symbolic link.")
            os.replace(temporary,path); temporary=None
        finally:
            if temporary is not None:
                try: os.unlink(temporary)
                except FileNotFoundError: pass
        object_id=sha256(json.dumps({"tenant":scope,"key":key},sort_keys=True,separators=(",",":")).encode()).hexdigest()
        metadata=StorageMetadata(object_id,key,scope,display_name,content_type,size,digest.hexdigest()); self._metadata[(scope,key)]=metadata; return metadata
    def download(self,key,principal,tenant,policy):
        tenant_id=trusted_tenant_id(tenant); self._allowed(policy,principal,tenant_id,"read"); path,scope=self._path(tenant_id,key)
        if (scope,key) not in self._metadata or not path.is_file() or path.is_symlink(): raise FileNotFoundError("Object unavailable.")
        digest=sha256(); size=0
        with open(path,"rb") as source:
            while True:
                chunk=source.read(64*1024)
                if not chunk: break
                size+=len(chunk); digest.update(chunk)
        metadata=self._metadata[(scope,key)]
        if size!=metadata.size or digest.hexdigest()!=metadata.checksum: raise ValueError("Stored object integrity verification failed.")
        return open(path,"rb")
    def list(self,principal,tenant,policy):
        tenant_id=trusted_tenant_id(tenant); self._allowed(policy,principal,tenant_id,"list"); scope=self._scope(tenant_id)
        return tuple(self._metadata[k] for k in sorted(self._metadata) if k[0]==scope)
    def delete(self,key,principal,tenant,policy):
        tenant_id=trusted_tenant_id(tenant); self._allowed(policy,principal,tenant_id,"delete"); path,scope=self._path(tenant_id,key)
        if (scope,key) not in self._metadata or not path.is_file() or path.is_symlink(): raise FileNotFoundError("Object unavailable.")
        path.unlink(); del self._metadata[(scope,key)]
