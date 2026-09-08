import time, unittest
from tools.authorization import PolicyContract,PrincipalContext
from tools.health_intelligence import *
from tools.multitenancy import TenantContext
from tools.observability import LocalTraceExporter,MetricDefinition,MetricKind,MetricRegistry,TraceContext,Tracer
from tools.structured_logging import CorrelationContext,StructuredLogger

def sig(name,state=HealthState.HEALTHY,required=True,at=100,finding=None): return HealthSignal(name,state,required,at,finding)
class HealthIntelligenceTest(unittest.TestCase):
    def test_health_state_and_liveness_readiness_semantics(self):
        a=HealthAggregator(); healthy=a.aggregate((sig("database"),),now=100); degraded=a.aggregate((sig("webhook",HealthState.UNHEALTHY,False),),now=100); unhealthy=a.aggregate((sig("database",HealthState.UNHEALTHY),),now=100); unknown=a.aggregate((sig("database",HealthState.UNKNOWN),),now=100)
        self.assertEqual(healthy.state,HealthState.HEALTHY); self.assertTrue(healthy.ready); self.assertEqual(degraded.state,HealthState.DEGRADED); self.assertTrue(degraded.ready); self.assertEqual(unhealthy.state,HealthState.UNHEALTHY); self.assertTrue(unhealthy.live); self.assertFalse(unhealthy.ready); self.assertEqual(unknown.state,HealthState.UNKNOWN); self.assertFalse(unknown.ready)
    def test_mandatory_failures_never_report_healthy(self):
        for name in ("database","migration","configuration","secret_reference","worker","jobs","events","storage"):
            with self.subTest(name=name):
                report=HealthAggregator().aggregate((sig(name,HealthState.UNHEALTHY),),now=100); self.assertEqual(report.state,HealthState.UNHEALTHY); self.assertFalse(report.ready)
    def test_provider_failure_timeout_and_spoofing_fail_closed(self):
        a=HealthAggregator(provider_timeout_seconds=.01); failing=HealthCheck("database",True,lambda:(_ for _ in ()).throw(RuntimeError("secret host"))); timeout=HealthCheck("worker",True,lambda:(time.sleep(.2),sig("worker"))[1]); spoofed=HealthCheck("storage",True,lambda:sig("other"))
        for check,code in ((failing,"dependency.failed"),(timeout,"dependency.timeout"),(spoofed,"dependency.invalid")):
            report=a.evaluate((check,),now=100); self.assertFalse(report.ready); self.assertEqual(report.state,HealthState.UNKNOWN); self.assertEqual(report.findings[0].code,code); self.assertNotIn("secret host",str(report.public_dict()))
    def test_stale_future_duplicate_and_malformed_rejected(self):
        a=HealthAggregator(10); self.assertFalse(a.aggregate((sig("database",at=1),),now=100).ready); self.assertFalse(a.aggregate((sig("database",at=102),),now=100).ready)
        with self.assertRaises(ValueError): a.aggregate((sig("database"),sig("database")),now=100)
        with self.assertRaises(ValueError): a.evaluate((object(),),now=100)
        with self.assertRaises(ValueError): a.aggregate(tuple(sig(f"source{i}") for i in range(65)),now=100)
    def test_diagnostics_safe_deterministic_and_recovery(self):
        finding=DiagnosticFinding("db.unavailable","database",DiagnosticSeverity.ERROR,"password secret","use secret"); a=HealthAggregator(known_secrets=("secret",)); failed=a.aggregate((sig("database",HealthState.UNHEALTHY,finding=finding),),now=100); recovered=a.aggregate((sig("database"),),now=100)
        self.assertNotIn("findings",failed.public_dict()); self.assertNotIn("secret",str(failed.diagnostic_dict())); self.assertEqual(failed.findings[0].code,"db.unavailable"); self.assertEqual(recovered.state,HealthState.HEALTHY); self.assertTrue(recovered.ready)
    def test_logging_metrics_and_trace_integration(self):
        events=[]; logger=StructuredLogger("health",events.append); metrics=MetricRegistry((MetricDefinition("health.ready",MetricKind.GAUGE),)); exporter=LocalTraceExporter(); tracer=Tracer(exporter); report=HealthAggregator().aggregate((sig("database"),),now=100)
        HealthAggregator().record(report,logger=logger,log_context=CorrelationContext("correlation"),metrics=metrics,tracer=tracer,trace_context=TraceContext("a"*32,"b"*16)); self.assertEqual(len(events),1); self.assertEqual(metrics.values[("health.ready",())],1); self.assertEqual(exporter.spans[0].name,"health.evaluate")
    def test_tenant_diagnostics_require_trusted_context_and_rbac(self):
        policy=PolicyContract.create({"operator":{"read"}}); principal=PrincipalContext("principal","tenant-a",("operator",)); report=HealthAggregator().aggregate((sig("database"),),now=100,tenant=TenantContext("tenant-a")); view=HealthAggregator().tenant_view(report,principal,TenantContext("tenant-a"),policy); self.assertTrue(view["ready"]); self.assertIn("findings",view)
        with self.assertRaises(PermissionError): HealthAggregator().tenant_view(report,principal,TenantContext("tenant-b"),policy)
        with self.assertRaises(PermissionError): HealthAggregator().tenant_view(HealthAggregator().aggregate((sig("database"),),now=100),principal,TenantContext("tenant-a"),policy)
if __name__=="__main__": unittest.main()
