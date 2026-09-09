import time, unittest
from tools.authorization import PolicyContract, PrincipalContext
from tools.configuration_lifecycle import SecretReference
from tools.extensions import *
from tools.multitenancy import TenantContext

def policy(): return PolicyContract.create({"admin":{"create","read"},"reader":{"read"}})
ADMIN=PrincipalContext("admin","tenant_a",("admin",)); READER=PrincipalContext("reader","tenant_a",("reader",))
TENANT_A=TenantContext("tenant_a"); TENANT_B=TenantContext("tenant_b")
def manifest(name="example",failure=FailurePolicy.MANDATORY,scope=ExtensionScope.TENANT):
    return ExtensionManifest(name,"1.0.0","v1",scope,(ExtensionCapability.CONTRIBUTE_DIAGNOSTICS,),(HookPoint.DIAGNOSTICS_ENRICHMENT,),("read",),("public_config",),(SecretReference("DATABASE","vault/database","v1"),),failure)

class ExtensionContractTest(unittest.TestCase):
    def test_manifest_is_deterministic_and_rejects_malformed_contracts(self):
        item=manifest(); self.assertEqual(item.digest,manifest().digest); self.assertNotIn("secret_value",str(item.canonical_dict()))
        with self.assertRaises(ValueError): ExtensionManifest("../bad","1","v1",ExtensionScope.TENANT,item.capabilities,item.hooks)
        with self.assertRaises(ValueError): ExtensionManifest("ok","1.0.0","v2",ExtensionScope.TENANT,item.capabilities,item.hooks)
        with self.assertRaises(ValueError): ExtensionManifest("ok","1.0.0","v1",ExtensionScope.TENANT,(item.capabilities[0],item.capabilities[0]),item.hooks)
        with self.assertRaises(ValueError): ExtensionManifest("ok","1.0.0","v1",ExtensionScope.TENANT,item.capabilities,item.hooks,("execute",))
    def test_result_boundary_denies_control_channels_and_unbounded_values(self):
        self.assertEqual(2,ExtensionResult(ExtensionStatus.SUCCESS,(("count",2),("healthy",True))).canonical_dict()["contributions"]["count"])
        for key in ("command","python","path","secret","release_gate"):
            with self.assertRaises(ValueError): ExtensionResult(ExtensionStatus.SUCCESS,((key,"x"),))
        with self.assertRaises(ValueError): ExtensionResult(ExtensionStatus.SUCCESS,(("payload",object()),))
        with self.assertRaises(ValueError): ExtensionResult(ExtensionStatus.SUCCESS,(("payload","x"*1025),))
    def test_registration_is_explicit_tenant_bound_and_default_deny(self):
        reg=ExtensionRegistry(); fn=lambda c:ExtensionResult(ExtensionStatus.SUCCESS)
        with self.assertRaises(PermissionError): reg.register(manifest(),fn,principal=READER,policy=policy(),tenant=TENANT_A)
        reg.register(manifest(),fn,principal=ADMIN,policy=policy(),tenant=TENANT_A)
        with self.assertRaises(ValueError): reg.register(manifest(),fn,principal=ADMIN,policy=policy(),tenant=TENANT_A)
        with self.assertRaises(PermissionError): reg.manifests(principal=PrincipalContext("a","tenant_b",("admin",)),policy=policy(),tenant=TENANT_A)
        with self.assertRaises(PermissionError): reg.register(manifest("raw"),fn,principal=ADMIN,policy=policy(),tenant=0)
    def test_invocation_is_ordered_capability_scoped_and_has_no_environment(self):
        reg=ExtensionRegistry(); seen=[]
        for name in ("zeta","alpha"):
            reg.register(manifest(name),lambda ctx,n=name:(seen.append(ctx),ExtensionResult(ExtensionStatus.SUCCESS,(("source",n),)))[1],principal=ADMIN,policy=policy(),tenant=TENANT_A)
        out=reg.invoke(HookPoint.DIAGNOSTICS_ENRICHMENT,ExtensionCapability.CONTRIBUTE_DIAGNOSTICS,principal=READER,policy=policy(),tenant=TENANT_A,correlation_id="request_1")
        self.assertEqual(["alpha","zeta"],[x.contributions[0][1] for x in out]); self.assertFalse(hasattr(seen[0],"environment"))
        self.assertEqual((),reg.invoke(HookPoint.POST_RUNTIME_OBSERVATION,ExtensionCapability.OBSERVE_RUNTIME,principal=READER,policy=policy(),tenant=TENANT_A,correlation_id="request_2"))
    def test_invalid_provider_result_is_fail_closed_or_explicitly_degraded(self):
        for mode,error in ((FailurePolicy.MANDATORY,True),(FailurePolicy.OPTIONAL,False)):
            reg=ExtensionRegistry(); reg.register(manifest(failure=mode),lambda c:{"unsafe":True},principal=ADMIN,policy=policy(),tenant=TENANT_A)
            if error:
                with self.assertRaises(ExtensionInvocationError): reg.invoke(HookPoint.DIAGNOSTICS_ENRICHMENT,ExtensionCapability.CONTRIBUTE_DIAGNOSTICS,principal=READER,policy=policy(),tenant=TENANT_A,correlation_id="request_3")
            else:self.assertEqual(ExtensionStatus.DEGRADED,reg.invoke(HookPoint.DIAGNOSTICS_ENRICHMENT,ExtensionCapability.CONTRIBUTE_DIAGNOSTICS,principal=READER,policy=policy(),tenant=TENANT_A,correlation_id="request_3")[0].status)
    def test_timeout_fails_closed_and_provider_errors_do_not_leak(self):
        reg=ExtensionRegistry(); reg.register(manifest(),lambda c:(time.sleep(.1),ExtensionResult(ExtensionStatus.SUCCESS))[1],principal=ADMIN,policy=policy(),tenant=TENANT_A)
        with self.assertRaises(ExtensionInvocationError): reg.invoke(HookPoint.DIAGNOSTICS_ENRICHMENT,ExtensionCapability.CONTRIBUTE_DIAGNOSTICS,principal=READER,policy=policy(),tenant=TENANT_A,correlation_id="request_4",timeout_seconds=.01)
        reg=ExtensionRegistry(); reg.register(manifest(failure=FailurePolicy.OPTIONAL),lambda c:(_ for _ in ()).throw(RuntimeError("token=supersecret")),principal=ADMIN,policy=policy(),tenant=TENANT_A)
        result=reg.invoke(HookPoint.DIAGNOSTICS_ENRICHMENT,ExtensionCapability.CONTRIBUTE_DIAGNOSTICS,principal=READER,policy=policy(),tenant=TENANT_A,correlation_id="request_5")[0]; self.assertNotIn("supersecret",result.message)
    def test_global_and_tenant_scope_are_visible_without_cross_tenant_leakage(self):
        fn=lambda c:ExtensionResult(ExtensionStatus.SUCCESS); global_manifest=manifest("global_ext",scope=ExtensionScope.GLOBAL)
        reg=ExtensionRegistry(trusted_global_extensions=((global_manifest,fn),))
        with self.assertRaises(PermissionError): reg.register(global_manifest,fn,principal=ADMIN,policy=policy())
        reg.register(manifest("tenant_ext"),fn,principal=ADMIN,policy=policy(),tenant=TENANT_A)
        self.assertEqual(("global_ext","tenant_ext"),tuple(x.extension_id for x in reg.manifests(principal=READER,policy=policy(),tenant=TENANT_A)))
        with self.assertRaises(ValueError): reg.register(manifest("global_ext"),fn,principal=ADMIN,policy=policy(),tenant=TENANT_A)
    def test_manifest_permissions_are_enforced_at_execution_boundary(self):
        reg=ExtensionRegistry(); required=ExtensionManifest("writer","1.0.0","v1",ExtensionScope.TENANT,(ExtensionCapability.CONTRIBUTE_DIAGNOSTICS,),(HookPoint.DIAGNOSTICS_ENRICHMENT,),("create",))
        reg.register(required,lambda c:ExtensionResult(ExtensionStatus.SUCCESS),principal=ADMIN,policy=policy(),tenant=TENANT_A)
        with self.assertRaises(PermissionError): reg.invoke(HookPoint.DIAGNOSTICS_ENRICHMENT,ExtensionCapability.CONTRIBUTE_DIAGNOSTICS,principal=READER,policy=policy(),tenant=TENANT_A,correlation_id="request_6")
        self.assertEqual(ExtensionStatus.SUCCESS,reg.invoke(HookPoint.DIAGNOSTICS_ENRICHMENT,ExtensionCapability.CONTRIBUTE_DIAGNOSTICS,principal=ADMIN,policy=policy(),tenant=TENANT_A,correlation_id="request_7")[0].status)
if __name__=="__main__": unittest.main()
