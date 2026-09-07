import unittest

from tools.authorization import PolicyContract, PrincipalContext
from tools.jobs import JobDefinition, JobExecutor, JobRegistry, JobSchedule, JobStatus, RetryPolicy
from tools.multitenancy import TenantContext


def registry(handler, **changes):
    values=dict(identifier="rebuild",handler="trusted_handler",allowed_fields=("value",),permission="create",retry=RetryPolicy())
    values.update(changes); definition=JobDefinition(**values)
    return JobRegistry((definition,), {"trusted_handler":handler})


class JobTest(unittest.TestCase):
    def setUp(self):
        self.policy=PolicyContract.create({"worker":{"create"}})
        self.principal=PrincipalContext("p1","tenant_a",("worker",))

    def executor(self, handler=lambda payload,tenant: payload["value"], **changes): return JobExecutor(registry(handler,**changes),self.policy)
    def enqueue(self, executor, tenant="tenant_a", payload=None, key="once"):
        return executor.enqueue("rebuild", payload or {"value":1}, self.principal, TenantContext(tenant) if tenant else None, key)

    def test_success_and_idempotency(self):
        executor=self.executor(); one=self.enqueue(executor); self.assertIs(one,self.enqueue(executor)); executor.execute(one)
        self.assertEqual((one.status,one.result,one.attempts),(JobStatus.SUCCEEDED,1,1))
    def test_failure_and_bounded_retry(self):
        calls=[]
        def bad(payload,tenant): calls.append(1); raise RuntimeError("secret material")
        item=self.enqueue(self.executor(bad,retry=RetryPolicy(2,0))); self.executor
        executor=self.executor(bad,retry=RetryPolicy(2,0)); item=self.enqueue(executor); executor.execute(item)
        self.assertEqual((item.status,item.attempts,item.error_class),(JobStatus.FAILED,2,"RuntimeError")); self.assertNotIn("secret",item.error_class)
    def test_retry_succeeds(self):
        calls=[]
        def flaky(payload,tenant): calls.append(1); return 7 if len(calls)==2 else (_ for _ in ()).throw(ConnectionError())
        executor=self.executor(flaky,retry=RetryPolicy(2)); item=self.enqueue(executor); executor.execute(item); self.assertEqual(item.result,7)
    def test_timeout_fails(self):
        executor=self.executor(timeout_seconds=.1); item=self.enqueue(executor)
        ticks=iter((0,.2)); executor.execute(item,clock=lambda:next(ticks)); self.assertEqual(item.error_class,"TimeoutError")
    def test_payload_and_handler_validation(self):
        executor=self.executor()
        for payload in ({"unknown":1},{"tenant_id":"b"},{"value":"x"*70000}):
            with self.assertRaises(ValueError): self.enqueue(executor,payload=payload)
        with self.assertRaises((ValueError,LookupError)): executor.enqueue("os_system",{},self.principal,TenantContext("tenant_a"),"once")
        with self.assertRaises(ValueError): JobRegistry((JobDefinition("x","evil",(),"create"),),{"trusted_handler":lambda:None})
    def test_context_and_authorization_fail_closed(self):
        executor=self.executor()
        with self.assertRaises(PermissionError): self.enqueue(executor,tenant=None)
        with self.assertRaises(PermissionError): self.enqueue(executor,tenant="tenant_b")
        denied=PrincipalContext("p","tenant_a",("unknown",))
        with self.assertRaises(PermissionError): executor.enqueue("rebuild",{"value":1},denied,TenantContext("tenant_a"),"once")
    def test_tenant_idempotency_isolation(self):
        policy=PolicyContract.create({"worker":{"create"}}); executor=JobExecutor(registry(lambda p,t:t),policy)
        a=executor.enqueue("rebuild",{"value":1},PrincipalContext("a","a",("worker",)),TenantContext("a"),"once")
        b=executor.enqueue("rebuild",{"value":1},PrincipalContext("b","b",("worker",)),TenantContext("b"),"once")
        self.assertNotEqual(a.identity,b.identity)
    def test_state_machine_and_false_success(self):
        executor=self.executor(lambda p,t:(_ for _ in ()).throw(ValueError())); item=self.enqueue(executor); executor.execute(item)
        self.assertEqual(item.status,JobStatus.FAILED)
        with self.assertRaises(ValueError): item.transition(JobStatus.SUCCEEDED)
    def test_schedule_determinism_and_deduplication(self):
        first=registry(lambda p,t:None,schedule=JobSchedule("0 0 * * *")); second=registry(lambda p,t:None,schedule=JobSchedule("0 0 * * *"))
        self.assertEqual(first.digest,second.digest); executor=JobExecutor(first,self.policy); self.assertEqual(executor.register_schedules(),1); self.assertEqual(executor.register_schedules(),1)
        with self.assertRaises(ValueError): JobSchedule("@daily")
        with self.assertRaises(ValueError): JobSchedule("0 0 * * *","America/Los_Angeles")


if __name__ == "__main__": unittest.main()
