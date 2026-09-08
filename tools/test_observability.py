import unittest
from tools.observability import *
class ObservabilityTest(unittest.TestCase):
 def test_metric_definitions_and_behaviors(self):
  defs=(MetricDefinition("requests.total",MetricKind.COUNTER,("method",)),MetricDefinition("queue.depth",MetricKind.GAUGE),MetricDefinition("request.duration",MetricKind.HISTOGRAM,(),(.1,1.0)))
  r=MetricRegistry(defs);self.assertEqual(defs[0].digest,defs[0].digest);self.assertEqual(r.observe("requests.total",2,{"method":"GET"}),2);self.assertEqual(r.observe("queue.depth",3),3);self.assertEqual(r.observe("request.duration",.2),{"count":1,"sum":.2,"buckets":[0,1]})
  for _ in range(10000):r.observe("request.duration",.2)
  self.assertEqual(len(r.values[("request.duration",())]["buckets"]),2)
 def test_metric_labels_and_cardinality_fail_closed(self):
  with self.assertRaises(ValueError):MetricDefinition("bad",MetricKind.COUNTER,("tenant_id",))
  with self.assertRaises(ValueError):MetricDefinition("bad",MetricKind.COUNTER,("credential",))
  with self.assertRaises(ValueError):MetricDefinition("bad",MetricKind.HISTOGRAM,(),(float("inf"),))
  r=MetricRegistry((MetricDefinition("jobs.total",MetricKind.COUNTER,("status",)),),max_series=1);r.observe("jobs.total",1,{"status":"ok"})
  with self.assertRaises(ValueError):r.observe("jobs.total",1,{"status":"bad"})
  with self.assertRaises(ValueError):r.observe("jobs.total",1,{"unknown":"x"})
  with self.assertRaises(ValueError):r.observe("jobs.total",float("inf"),{"status":"ok"})
 def test_trace_parent_child_redaction_and_false_success(self):
  e=LocalTraceExporter();t=Tracer(e,known_secrets=("secret",));root=t.start("request",TraceContext("a"*32,"b"*16),attributes={"value":"secret"});child=t.start("db.read",TraceContext("a"*32,"c"*16),parent=root);t.finish(child,False);self.assertEqual(child.status,SpanStatus.ERROR);self.assertEqual(child.parent_span_id,"b"*16);self.assertNotIn("secret",str(root.attributes))
 def test_trace_malformed_sensitive_and_depth_rejected(self):
  with self.assertRaises(ValueError):TraceContext("x","y")
  t=Tracer(LocalTraceExporter(),max_depth=1);root=t.start("request",TraceContext("a"*32,"b"*16))
  with self.assertRaises(ValueError):t.start("child",TraceContext("a"*32,"c"*16),parent=root)
  with self.assertRaises(ValueError):Tracer(LocalTraceExporter()).start("db",TraceContext("a"*32,"b"*16),attributes={"sql_parameters":"password"})
  with self.assertRaises(ValueError):Tracer(LocalTraceExporter()).start("db",TraceContext("a"*32,"b"*16),attributes={"nested":{"db.statement":"select secret"}})
  with self.assertRaises(ValueError):Tracer(LocalTraceExporter()).start("child",TraceContext("c"*32,"d"*16),parent=root)
 def test_local_exporter_bounded_no_network(self):
  e=LocalTraceExporter(1);t=Tracer(e);s=t.start("job",TraceContext("a"*32,"b"*16));t.finish(s,True)
  with self.assertRaises(ValueError):e.export(s)
if __name__=="__main__":unittest.main()
