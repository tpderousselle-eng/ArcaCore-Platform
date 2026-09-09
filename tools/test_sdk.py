import inspect, json, unittest
from tools.authorization import PolicyContract, PrincipalContext
from tools.extensions import ExtensionCapability, ExtensionManifest, ExtensionRegistry, ExtensionResult, ExtensionScope, ExtensionStatus, FailurePolicy, HookPoint
from tools.health_intelligence import HealthAggregator, HealthCheck, HealthSignal, HealthState
from tools.jobs import JobDefinition, JobExecutor, JobRegistry
from tools.multitenancy import TenantContext
from tools.observability import LocalTraceExporter, MetricDefinition, MetricKind, MetricRegistry, TraceContext, Tracer
from tools.resource_intelligence import ResourceIntelligence, ResourceKind, ResourceObservation, ResourceProfile, ResourceRequirement
from tools.sdk import ArcaCoreClient, ArcaCoreService, SDKContract, SDKResponse, SDK_VERSION
from tools.structured_logging import StructuredLogger

TENANT_A=TenantContext("tenant_a"); TENANT_B=TenantContext("tenant_b")
ADMIN_A=PrincipalContext("admin_a","tenant_a",("admin",)); READER_A=PrincipalContext("reader_a","tenant_a",("reader",))
ADMIN_B=PrincipalContext("admin_b","tenant_b",("admin",)); DENIED_A=PrincipalContext("denied_a","tenant_a",("denied",))
def request(operation,payload=None,correlation="corr_1",version=SDK_VERSION): return {"version":version,"operation":operation,"correlation_id":correlation,"payload":payload or {}}

class StableSDKTest(unittest.TestCase):
 def setUp(self):
  self.logs=[];self.policy=PolicyContract.create({"admin":{"create","read"},"denied":{"create"},"reader":{"read"}})
  definition=JobDefinition("sdk_build","build",("input",),"read");self.jobs=JobExecutor(JobRegistry((definition,),{"build":lambda payload,tenant:{"artifact_digest":"a"*64}}),self.policy)
  self.health=HealthAggregator();self.health_report=self.health.evaluate((HealthCheck("database",True,lambda:HealthSignal("database",HealthState.HEALTHY,True,1.0)),),now=1.0,tenant=TENANT_A)
  self.resources=ResourceIntelligence(ResourceProfile((ResourceRequirement("workers",ResourceKind.WORKERS,4,"workers",3),)))
  self.resource_report=self.resources.report((ResourceObservation("workers",ResourceKind.WORKERS,1,"workers",1.0),),tenant=TENANT_A)
  ext=ExtensionManifest("diagnostic","1.0.0","v1",ExtensionScope.TENANT,(ExtensionCapability.CONTRIBUTE_DIAGNOSTICS,),(HookPoint.DIAGNOSTICS_ENRICHMENT,),("read",),failure_policy=FailurePolicy.MANDATORY)
  self.extensions=ExtensionRegistry();self.extensions.register(ext,lambda context:ExtensionResult(ExtensionStatus.SUCCESS,(("healthy",True),)),principal=ADMIN_A,policy=self.policy,tenant=TENANT_A)
  self.metrics=MetricRegistry((MetricDefinition("sdk.operations",MetricKind.COUNTER,("operation","outcome")),));self.exporter=LocalTraceExporter();self.tracer=Tracer(self.exporter)
  self.service=ArcaCoreService(policy=self.policy,jobs=self.jobs,build_job="sdk_build",specification_validator=self._validate_specification,validation_provider=lambda value:{"valid":value.get("digest")=="a"*64},health_aggregator=self.health,health_provider=lambda:self.health_report,resource_intelligence=self.resources,resource_provider=lambda:self.resource_report,extensions=self.extensions,logger=StructuredLogger("arcacore",self.logs.append),metrics=self.metrics,tracer=self.tracer)
  self.client=ArcaCoreClient(self.service,READER_A,TENANT_A)
 @staticmethod
 def _validate_specification(value):
  if not isinstance(value,dict) or set(value)!={"module"} or not isinstance(value["module"],str):raise ValueError("invalid")
  return {"module":value["module"],"valid":True}
 def test_contract_version_and_response_identity_are_deterministic(self):
  self.assertEqual(SDKContract().digest,SDKContract().digest);self.assertEqual(SDKContract().canonical_dict()["version"],"1.0")
  first=self.client.request(request("runtime_health"));second=self.client.request(request("runtime_health"));self.assertEqual(first.canonical_dict(),second.canonical_dict());self.assertEqual(first.digest,second.digest);self.assertEqual(SDKResponse(**first.__dict__).canonical_dict(),first.canonical_dict())
 def test_unknown_major_malformed_version_operation_and_fields_rejected(self):
  for value in (request("runtime_health",version="2.0"),request("runtime_health",version="v1"),request("release_gate"),{**request("runtime_health"),"extra":True},request("runtime_health",{"extra":True})):self.assertEqual("error",self.client.request(value).status)
 def test_specification_and_validation_use_bounded_typed_contracts(self):
  result=self.client.request(request("validate_specification",{"specification":{"module":"orders"}}));self.assertEqual({"module":"orders","valid":True},result.data)
  validated=self.client.request(request("run_validation",{"manifest":{"digest":"a"*64}}));self.assertEqual({"valid":True},validated.data)
  self.assertEqual("error",self.client.request(request("validate_specification",{"specification":{"module":object()}})).status)
 def test_async_build_reuses_jobs_and_status_is_tenant_isolated(self):
  queued=self.client.request(request("prepare_build",{"idempotency_key":"build_1","input":{"module":"orders"}}));identity=queued.data["operation_id"];self.assertEqual("queued",queued.data["status"])
  self.assertEqual("queued",self.client.request(request("operation_status",{"operation_id":identity})).data["status"])
  other=ArcaCoreClient(self.service,ADMIN_B,TENANT_B);self.assertEqual("access_denied",other.request(request("operation_status",{"operation_id":identity})).error["code"])
  self.assertEqual(identity,self.client.request(request("prepare_build",{"idempotency_key":"build_1","input":{"module":"orders"}})).data["operation_id"])
 def test_health_diagnostics_and_resource_views_preserve_tenant_rbac(self):
  self.assertEqual(HealthState.HEALTHY.value,self.client.request(request("runtime_health")).data["state"]);self.assertEqual([],self.client.request(request("diagnostics")).data["findings"]);self.assertEqual("healthy",self.client.request(request("resource_metadata")).data["capacity_state"].lower())
  self.assertEqual("access_denied",ArcaCoreClient(self.service,DENIED_A,TENANT_A).request(request("diagnostics")).error["code"]);self.assertEqual("access_denied",ArcaCoreClient(self.service,ADMIN_B,TENANT_A).request(request("runtime_health")).error["code"])
 def test_extension_surface_is_capability_bounded(self):
  value=self.client.request(request("invoke_extension",{"hook":"diagnostics_enrichment","capability":"contribute_diagnostics"}));self.assertEqual(True,value.data["results"][0]["contributions"]["healthy"]);self.assertEqual("error",self.client.request(request("invoke_extension",{"hook":"bad","capability":"contribute_diagnostics"})).status)
 def test_payload_objects_executable_channels_and_size_fail_closed(self):
  hostile=(request("validate_specification",{"specification":{"module":object()}}),request("validate_specification",{"specification":{"command":"whoami"}}),request("validate_specification",{"specification":{"module":"x"*70000}}))
  for value in hostile:self.assertEqual("invalid_request",self.client.request(value).error["code"])
  source=inspect.getsource(__import__("tools.sdk",fromlist=["x"]));self.assertNotIn("pickle.loads",source);self.assertNotIn("eval(",source);self.assertNotIn("exec(",source)
 def test_provider_failures_are_redacted_without_paths_secrets_or_stacks(self):
  self.service.specification_validator=lambda value:{"secret":"supersecret"};response=self.client.request(request("validate_specification",{"specification":{"module":"orders"}}));raw=json.dumps(response.canonical_dict());self.assertEqual("error",response.status);self.assertNotIn("supersecret",raw);self.assertNotIn("C:\\",raw);self.assertNotIn("Traceback",raw)
 def test_correlation_logging_metrics_and_traces_exclude_request_contents(self):
  response=self.client.request(request("validate_specification",{"specification":{"module":"private_module"}},"correlation_7"),trace_context=TraceContext("a"*32,"b"*16));self.assertEqual("correlation_7",response.correlation_id);self.assertEqual(1,len(self.logs));self.assertNotIn("private_module",self.logs[0]);self.assertEqual(1,self.metrics.values[("sdk.operations",(("operation","validate_specification"),("outcome","ok")))]);self.assertEqual("sdk.operation",self.exporter.spans[0].name)
 def test_representative_consumer_uses_only_stable_sdk_surface(self):
  def arcacentum_consumer(client):return client.request({"version":"1.0","operation":"runtime_health","correlation_id":"consumer_1","payload":{}}).canonical_dict()
  value=arcacentum_consumer(self.client);self.assertEqual({"correlation_id","data","error","operation","status","version"},set(value));self.assertEqual("ok",value["status"])
if __name__=="__main__":unittest.main()
