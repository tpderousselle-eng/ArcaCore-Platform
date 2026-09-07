import socket, unittest
from types import SimpleNamespace
from tools.authorization import PolicyContract,PrincipalContext
from tools.configuration_lifecycle import SecretValue
from tools.events import *
from tools.jobs import RetryPolicy
from tools.multitenancy import TenantContext

def resolved(ip): return lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,"",(ip,443))]

class EventTest(unittest.TestCase):
    def setUp(self):
        self.seen=[]; definition=EventDefinition("invoice.created",("amount",))
        self.registry=EventRegistry((definition,),{"invoice.created":(self.seen.append,)})
    def test_publish_subscribe_deterministic_and_tenant_scoped(self):
        bus=EventBus(self.registry); one=bus.publish("invoice.created",{"amount":3},TenantContext("a"),correlation_id="order_1")
        two=bus.publish("invoice.created",{"amount":3},TenantContext("a"),correlation_id="order_1")
        self.assertEqual(one,two); self.assertEqual(self.seen[0].tenant_id,"a"); self.assertEqual(self.registry.digest,self.registry.digest)
    def test_payload_unknown_oversize_forgery_and_type_rejected(self):
        bus=EventBus(self.registry)
        for payload in ({"tenant_id":"b","amount":1},{"unknown":1},{"amount":"x"*70000}):
            with self.assertRaises(ValueError): bus.publish("invoice.created",payload,TenantContext("a"),correlation_id="x")
        with self.assertRaises(LookupError): bus.publish("unknown",{},TenantContext("a"),correlation_id="x")
        with self.assertRaises(ValueError): EventRegistry((EventDefinition("x",()),),{"x":("os.system",)})
    def test_missing_context_and_recursive_loop_fail_closed(self):
        bus=EventBus(self.registry,maximum_depth=2)
        with self.assertRaises(PermissionError): bus.publish("invoice.created",{"amount":1},None,correlation_id="x")
        with self.assertRaises(RuntimeError): bus.publish("invoice.created",{"amount":1},TenantContext("a"),correlation_id="x",depth=2)
    def test_webhook_rbac(self):
        policy=PolicyContract.create({"admin":{"create"}}); principal=PrincipalContext("p","a",("admin",))
        self.assertEqual(authorize_webhook(policy,principal,TenantContext("a")),"a")
        with self.assertRaises(PermissionError): authorize_webhook(policy,principal,TenantContext("b"))
    def test_ssrf_and_scheme_rejection(self):
        bad=[("http://example.com",resolved("8.8.8.8")),("https://localhost",resolved("127.0.0.1")),("https://x",resolved("10.0.0.1")),("https://x",resolved("169.254.169.254")),("file:///x",resolved("8.8.8.8")),("https://x",resolved("::1"))]
        for url,resolver in bad:
            with self.assertRaises(ValueError,msg=url): validate_webhook_url(url,resolver=resolver)
        parsed,addresses=validate_webhook_url("https://example.com/hook",resolver=resolved("8.8.8.8")); self.assertEqual(addresses,("8.8.8.8",))
    def test_signature_expiry_replay_and_redaction(self):
        secret=SecretValue("top-secret"); sig=sign_webhook(secret,"delivery_1",100,{"amount":1}); guard=ReplayGuard(10)
        self.assertTrue(guard.verify(secret,"delivery_1",100,{"amount":1},sig,now=105))
        with self.assertRaises(PermissionError): guard.verify(secret,"delivery_1",100,{"amount":1},sig,now=105)
        with self.assertRaises(PermissionError): ReplayGuard(10).verify(secret,"delivery_1",100,{"amount":1},sig,now=200)
        with self.assertRaises(PermissionError): ReplayGuard().verify(secret,"delivery_1",100,{"amount":1},"bad",now=100)
        self.assertNotIn("top-secret",sig+repr(secret))
    def test_delivery_bounded_retry_redirect_disabled_and_terminal(self):
        delivery=WebhookDelivery("https://example.com/h",RetryPolicy(2),resolver=resolved("8.8.8.8")); calls=[]
        def sender(*args,**kwargs): calls.append(kwargs); return SimpleNamespace(status=204) if len(calls)==2 else (_ for _ in ()).throw(ConnectionError())
        self.assertEqual(delivery.deliver(sender,{},{}),2); self.assertFalse(calls[-1]["allow_redirects"]); self.assertEqual(calls[-1]["timeout"],10)
        self.assertEqual(delivery.target.connect_address,"8.8.8.8"); self.assertEqual(delivery.target.server_hostname,"example.com")
        with self.assertRaises(RuntimeError): delivery.deliver(lambda *a,**k:(_ for _ in ()).throw(TimeoutError()),{}, {})
        with self.assertRaises(RuntimeError): delivery.deliver(lambda *a,**k:SimpleNamespace(status=302),{}, {})

if __name__=="__main__":unittest.main()
