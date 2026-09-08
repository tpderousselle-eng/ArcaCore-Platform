import json,unittest
from datetime import datetime,timezone
from tools.configuration_lifecycle import SecretValue
from tools.multitenancy import TenantContext
from tools.structured_logging import *
class LoggingTest(unittest.TestCase):
 def setUp(self): self.out=[];self.logger=StructuredLogger("arca",self.out.append,known_secrets=(SecretValue("s3cr3t"),))
 def test_canonical_schema_and_event(self):
  self.assertEqual(LogSchema().digest,LogSchema().digest);e=self.logger.emit("INFO","request.done","api",CorrelationContext("corr_1","req_1"),"done",{"count":1},tenant=TenantContext("a"),now=datetime(2026,1,1,tzinfo=timezone.utc));self.assertEqual(json.loads(self.out[0])["tenant"],"a");self.assertEqual(e.level,LogLevel.INFO)
 def test_recursive_secret_and_header_redaction(self):
  self.logger.emit("ERROR","job.failed","jobs",CorrelationContext("c"),"bad s3cr3t",{"authorization":"Bearer x","email":"person@example.com","nested":{"value":"s3cr3t"},"exception":"s3cr3t"});self.assertNotIn("s3cr3t",self.out[0]);self.assertNotIn("Bearer",self.out[0]);self.assertNotIn("person@example.com",self.out[0])
 def test_injection_and_malformed_identity_rejected(self):
  for message in ("x\ny","x\r y","x\x00y"):
   with self.assertRaises(ValueError):self.logger.emit("INFO","ok","api",CorrelationContext("c"),message)
  with self.assertRaises(ValueError):self.logger.emit("BOGUS","ok","api",CorrelationContext("c"),"x")
  with self.assertRaises(ValueError):self.logger.emit("INFO","BAD EVENT","api",CorrelationContext("c"),"x")
  with self.assertRaises(ValueError):CorrelationContext("bad value")
 def test_attributes_bounded_and_tenant_trusted(self):
  with self.assertRaises(ValueError):self.logger.emit("INFO","ok","api",CorrelationContext("c"),"x",{f"k{i}":i for i in range(33)})
  with self.assertRaises(PermissionError):self.logger.emit("INFO","ok","api",CorrelationContext("c"),"x",{"tenant_id":"b"},tenant="a")
  with self.assertRaises(ValueError):self.logger.emit("INFO","ok","api",CorrelationContext("c"),"x",{"tenant_id":"b"},tenant=TenantContext("a"))
if __name__=="__main__":unittest.main()
