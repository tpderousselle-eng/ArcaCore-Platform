from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.authorization import PolicyContract,PrincipalContext
from tools.multitenancy import TenantContext
from tools.storage import LocalStorageProvider,object_key

class BrokenStream:
    def __init__(self):self.calls=0
    def read(self,n):
        self.calls+=1
        if self.calls==1:return b"partial"
        raise OSError("interrupted")

class StorageTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.provider=LocalStorageProvider(self.temp.name,max_object_size=100000)
        self.policy=PolicyContract.create({"writer":{"create","delete","list","read","update"}})
        self.a=PrincipalContext("a","tenant_a",("writer",)); self.b=PrincipalContext("b","tenant_b",("writer",))
    def upload(self,data=b"hello",key="folder/item",principal=None,tenant="tenant_a",**kw): return self.provider.upload(key,BytesIO(data),principal or self.a,TenantContext(tenant),self.policy,**kw)
    def test_upload_download_list_replace_delete_and_checksum(self):
        meta=self.upload(display_name="../../display.txt",content_type="text/plain"); self.assertEqual(meta.size,5); self.assertNotIn(str(Path(self.temp.name)),meta.canonical_json())
        with self.provider.download("folder/item",self.a,TenantContext("tenant_a"),self.policy) as stream:self.assertEqual(stream.read(),b"hello")
        self.assertEqual(self.provider.list(self.a,TenantContext("tenant_a"),self.policy),(meta,))
        changed=self.upload(b"new",replace=True); self.assertNotEqual(meta.checksum,changed.checksum)
        self.provider.delete("folder/item",self.a,TenantContext("tenant_a"),self.policy); self.assertEqual(self.provider.list(self.a,TenantContext("tenant_a"),self.policy),())
    def test_path_attacks_rejected(self):
        for key in ("/etc/passwd","../x","a/../x","%2e%2e/x","C:/x","C:\\x","\\\\server\\x","a\0b","a\\b","./x"):
            with self.assertRaises(ValueError,msg=key): object_key(key)
    def test_size_streaming_and_interruption_are_safe(self):
        small=LocalStorageProvider(self.temp.name,max_object_size=5)
        with self.assertRaises(ValueError): small.upload("x",BytesIO(b"123456"),self.a,TenantContext("tenant_a"),self.policy)
        with self.assertRaises(OSError): self.provider.upload("broken",BrokenStream(),self.a,TenantContext("tenant_a"),self.policy)
        self.assertEqual(list(Path(self.temp.name).rglob("broken")),[])
    def test_external_content_tampering_fails_integrity(self):
        self.upload(); path,_=self.provider._path("tenant_a","folder/item"); path.write_bytes(b"forged")
        with self.assertRaises(ValueError): self.provider.download("folder/item",self.a,TenantContext("tenant_a"),self.policy)
    def test_tenant_isolation_and_spoofing(self):
        self.upload(); self.assertEqual(self.provider.list(self.b,TenantContext("tenant_b"),self.policy),())
        for operation in (lambda:self.provider.download("folder/item",self.b,TenantContext("tenant_b"),self.policy),lambda:self.provider.delete("folder/item",self.b,TenantContext("tenant_b"),self.policy)):
            with self.assertRaises((FileNotFoundError,FileExistsError)): operation()
        self.provider.upload("folder/item",BytesIO(b"tenant-b"),self.b,TenantContext("tenant_b"),self.policy,replace=True)
        with self.provider.download("folder/item",self.a,TenantContext("tenant_a"),self.policy) as stream:self.assertEqual(stream.read(),b"hello")
        with self.assertRaises(PermissionError): self.provider.download("folder/item",self.a,TenantContext("tenant_b"),self.policy)
    def test_rbac_default_deny(self):
        denied=PrincipalContext("x","tenant_a",("unknown",))
        with self.assertRaises(PermissionError): self.provider.list(denied,TenantContext("tenant_a"),self.policy)
    def test_symlink_escape_rejected_when_supported(self):
        scope=self.provider._scope("tenant_a"); namespace=Path(self.temp.name)/scope; namespace.mkdir(); outside=Path(self.temp.name).parent/"outside-target"
        try: (namespace/"link").symlink_to(outside,target_is_directory=True)
        except OSError:
            with patch("pathlib.Path.is_symlink", return_value=True):
                with self.assertRaises(ValueError): self.upload(key="link/file")
            return
        with self.assertRaises(ValueError): self.upload(key="link/file")
    def test_untrusted_metadata_does_not_execute_or_extract(self):
        meta=self.upload(b"not python",key="archive.zip",display_name="module.py",content_type="application/zip")
        self.assertEqual(meta.key,"archive.zip"); self.assertFalse(any(p.is_dir() and p.name=="archive" for p in Path(self.temp.name).rglob("*")))

if __name__=="__main__":unittest.main()
