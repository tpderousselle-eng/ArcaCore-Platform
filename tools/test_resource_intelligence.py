import unittest
from tools.authorization import PolicyContract,PrincipalContext
from tools.health_intelligence import HealthAggregator,HealthState
from tools.multitenancy import TenantContext
from tools.observability import *
from tools.resource_intelligence import *
from tools.structured_logging import CorrelationContext,StructuredLogger
class ResourceIntelligenceTest(unittest.TestCase):
 def setUp(self):
  self.profile=ResourceProfile((ResourceRequirement("cpu",ResourceKind.CPU,1000,"millicores",800),ResourceRequirement("memory",ResourceKind.MEMORY,512,"mib",400),ResourceRequirement("queue",ResourceKind.QUEUE,100,"items",80),ResourceRequirement("storage",ResourceKind.STORAGE,10,"gib",8),ResourceRequirement("workers",ResourceKind.WORKERS,4,"workers",4)))
  self.intel=ResourceIntelligence(self.profile)
 def test_deterministic_declared_profile_and_runtime_separation(self):
  digest=self.profile.digest;report=self.intel.report((ResourceObservation("cpu",ResourceKind.CPU,50,"millicores",123),));self.assertEqual(self.profile.digest,digest);self.assertNotIn("observ",str(self.profile.canonical_dict()))
 def test_all_resource_kinds_and_threshold_health(self):
  for name in ("cpu","memory","queue","storage","workers"):self.assertIn(name,self.intel.requirements)
  report=self.intel.report((ResourceObservation("queue",ResourceKind.QUEUE,85,"items",1),));signal=self.intel.capacity_signal(report,observed_at=1);self.assertEqual(signal.state,HealthState.DEGRADED);self.assertTrue(HealthAggregator().aggregate((signal,),now=1).ready)
 def test_cost_classification_provenance_and_no_fabricated_pricing(self):
  values=tuple(CostSignal(v,2,"requests","trusted_source") for v in SignalClass);self.assertEqual({v.classification for v in values},set(SignalClass))
  with self.assertRaises(ValueError):CostSignal(SignalClass.ESTIMATED,2,"requests","source",currency="USD")
  self.assertEqual(CostSignal(SignalClass.ESTIMATED,2,"requests","source","price.ref","USD").currency,"USD")
 def test_ai_usage_contains_counts_not_content(self):
  value=AIUsage("logical.model",1,2,3,4,5).safe_dict();self.assertNotIn("prompt",value);self.assertNotIn("content",value)
 def test_malformed_negative_nonfinite_huge_and_dimensions_rejected(self):
  with self.assertRaises(ValueError):ResourceRequirement("x",ResourceKind.CPU,-1,"millicores")
  with self.assertRaises(ValueError):ResourceRequirement("x",ResourceKind.CPU,1,"dollars")
  with self.assertRaises(ValueError):ResourceObservation("cpu",ResourceKind.CPU,float("nan"),"millicores",1)
  with self.assertRaises(ValueError):self.intel.report(tuple(ResourceObservation("cpu",ResourceKind.CPU,i,"millicores",1) for i in range(65)))
 def test_tenant_isolation_rbac_and_public_aggregate(self):
  report=self.intel.report(tenant=TenantContext("a"));policy=PolicyContract.create({"viewer":{"read"}});principal=PrincipalContext("p","a",("viewer",));self.assertNotIn("tenant",str(report.public_dict()));self.assertEqual(self.intel.tenant_view(report,principal,TenantContext("a"),policy)["profile_digest"],self.profile.digest)
  with self.assertRaises(PermissionError):self.intel.tenant_view(report,principal,TenantContext("b"),policy)
  with self.assertRaises(PermissionError):self.intel.tenant_view(report,PrincipalContext("p","a",()),TenantContext("a"),policy)
 def test_observability_composition_contains_no_secrets(self):
  report=self.intel.report();events=[];logger=StructuredLogger("arca",events.append,known_secrets=("secret",));metrics=MetricRegistry((MetricDefinition("resource.observations",MetricKind.GAUGE),));exporter=LocalTraceExporter();tracer=Tracer(exporter)
  self.intel.record(report,logger=logger,log_context=CorrelationContext("c"),metrics=metrics,tracer=tracer,trace_context=TraceContext("a"*32,"b"*16));self.assertNotIn("secret",str(events));self.assertEqual(metrics.values[("resource.observations",())],0)
if __name__=="__main__":unittest.main()
