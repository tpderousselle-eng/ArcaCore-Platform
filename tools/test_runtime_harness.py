from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from tools.application_manifest import ApplicationManifest, ModuleReference, RuntimeContract
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.minimal_regeneration import GenerationManifest, OwnedFile
from tools.runtime_harness import RuntimeFailure, RuntimeHarness, RuntimePhase, safe_diagnostic
from tools.schema_lifecycle import SchemaRevision


D1="1"*64


class RuntimeHarnessTest(unittest.TestCase):
    def setUp(self): self.temp=TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def fixture(self, source, *, health="/health", database="none", timeout=5):
        target=self.root/"app/main.py"; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(source,encoding="utf-8")
        content=target.read_bytes(); ownership=GenerationManifest.create([OwnedFile("app/main.py","runtime",sha256(content).hexdigest(),D1)])
        definition=ModuleDefinition("item","Item","item","items",parse_fields("item",["name:str"])); revision=SchemaRevision.create(definition)
        module=ModuleReference.create(name="item",accepted_schema_digest=revision.schema_digest,
            schema_revision_identity=revision.revision_identity,schema_parent_digest=None,migration_revision=None,
            generation_manifest_digest=ownership.manifest_identity,generated_surfaces=("app/main.py",),capabilities=("runtime",))
        runtime=RuntimeContract.create(database=database,required_services=("api",) if database=="none" else ("api","postgresql"),health_path=health)
        manifest=ApplicationManifest.create(application="runtime_app",project_name="Runtime",modules=(module,),runtime=runtime)
        return RuntimeHarness(self.root,manifest,ownership,{"item":revision},startup_timeout=timeout,shutdown_timeout=2), manifest, ownership

    def test_real_generated_application_starts_and_health_succeeds(self):
        harness,_,_=self.fixture("from fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef health(): return {'status':'ok'}\n")
        report=harness.run(); self.assertTrue(report.success,report.canonical_json())
        self.assertIn(RuntimePhase.HEALTH,[v.phase for v in report.phases])

    def test_import_or_startup_failure_is_structured_and_bounded(self):
        harness,_,_=self.fixture("raise RuntimeError('broken import')\n",timeout=2)
        report=harness.run(); self.assertFalse(report.success)
        self.assertEqual(next(v for v in report.phases if not v.success).category,RuntimeFailure.STARTUP)
        self.assertLessEqual(len(next(v for v in report.phases if not v.success).diagnostic),4096)

    def test_readiness_timeout_still_fails_closed(self):
        harness,_,_=self.fixture("import time\ntime.sleep(30)\n",timeout=.3)
        report=harness.run(); self.assertFalse(report.success); self.assertEqual(next(v for v in report.phases if not v.success).category,RuntimeFailure.READINESS_TIMEOUT)

    def test_health_failure_and_runtime_mismatch_fail(self):
        harness,_,_=self.fixture("from fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef health(): return {'status':'bad'}\n",timeout=10)
        report=harness.run(); self.assertFalse(report.success); self.assertEqual(next(v for v in report.phases if not v.success).category,RuntimeFailure.HEALTH)
        harness,_,_=self.fixture("from fastapi import FastAPI\napp=FastAPI()\n",timeout=.3)
        self.assertFalse(harness.run().success)

    def test_manifest_forgery_and_generated_digest_mismatch_never_execute(self):
        harness,manifest,ownership=self.fixture("raise RuntimeError('must not run')\n")
        (self.root/"app/main.py").write_text("forged")
        report=harness.run(); self.assertEqual(report.phases[0].category,RuntimeFailure.MANIFEST)

    def test_path_escape_and_symlink_are_rejected(self):
        harness,_,_=self.fixture("x=1")
        with self.assertRaises(ValueError): harness._source("../escape.py")
        from unittest.mock import patch
        original=Path.is_symlink
        with patch.object(Path,"is_symlink",lambda p:p.name=="app" or original(p)):
            with self.assertRaisesRegex(ValueError,"symbolic link"): harness._source("app/main.py")

    def test_secret_logs_controls_ansi_and_absolute_paths_are_redacted(self):
        value=safe_diagnostic("\x1b[31mpassword=hunter2\x00 "+str(self.root),self.root)
        self.assertNotIn("hunter2",value); self.assertNotIn("\x1b",value); self.assertNotIn(str(self.root),value)

    def test_hostile_output_is_drained_bounded_and_secrets_are_redacted(self):
        harness,_,_=self.fixture("print('x'*200000)\nprint('token=topsecret')\nraise RuntimeError('failed')\n",timeout=2)
        report=harness.run(); failure=next(v for v in report.phases if not v.success)
        self.assertLessEqual(len(failure.diagnostic),4096); self.assertNotIn("topsecret",failure.diagnostic)

    def test_report_is_deterministic_and_contains_no_port_or_workspace(self):
        source="from fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef health(): return {'status':'ok'}\n"
        harness,_,_=self.fixture(source); one=harness.run().canonical_json(); two=harness.run().canonical_json()
        self.assertEqual(one,two); self.assertNotIn(str(self.root),one); self.assertNotIn("127.0.0.1",one)

    def test_process_is_terminated_and_workspace_is_cleaned(self):
        harness,_,_=self.fixture("from fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef health(): return {'status':'ok'}\n")
        created=[]
        def tracked(*args,**kwargs):
            directory=TemporaryDirectory(*args,**kwargs); created.append(directory.name); return directory
        with patch("tools.runtime_harness.TemporaryDirectory",side_effect=tracked):
            self.assertTrue(harness.run().phases[-1].phase==RuntimePhase.SHUTDOWN)
        self.assertTrue(created); self.assertTrue(all(not Path(value).exists() for value in created))

    def test_shutdown_uses_bounded_process_tree_policy(self):
        harness,_,_=self.fixture("x=1")
        process=MagicMock(); process.poll.return_value=None
        process.wait.side_effect=[__import__('subprocess').TimeoutExpired('runtime',2),0]
        with patch("tools.runtime_harness.os.name","nt"), patch("tools.runtime_harness.subprocess.run") as run:
            harness._shutdown_tree(process)
        process.send_signal.assert_called_once(); run.assert_called_once()
        command=run.call_args.args[0]; self.assertEqual(command[:2],["taskkill","/PID"]); self.assertFalse(run.call_args.kwargs["shell"])

    def test_trusted_bootstrap_releases_only_after_job_assignment(self):
        harness,_,_=self.fixture("from fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef health(): return {'status':'ok'}\n")
        events=[]
        import tools.runtime_harness as target
        real_job=target._WindowsJob; real_write=target.write_bytes_atomic
        class Job:
            def __init__(self,process): events.append("contained"); self.job=real_job(process)
            def close(self): self.job.close()
        def write(path,content):
            if path.name==".arcacore-runtime-ready": events.append("released")
            return real_write(path,content)
        with patch.object(target,"_WindowsJob",Job),patch.object(target,"write_bytes_atomic",side_effect=write):
            self.assertTrue(harness.run().success)
        self.assertEqual(events[:2],["contained","released"])

    def test_reserved_bootstrap_release_path_cannot_be_a_generated_surface(self):
        target=self.root/".arcacore-runtime-ready"; target.write_text("forged")
        content=target.read_bytes(); ownership=GenerationManifest.create([OwnedFile(target.name,"runtime",sha256(content).hexdigest(),D1)])
        definition=ModuleDefinition("item","Item","item","items",parse_fields("item",["name:str"])); revision=SchemaRevision.create(definition)
        module=ModuleReference.create(name="item",accepted_schema_digest=revision.schema_digest,schema_revision_identity=revision.revision_identity,
            generation_manifest_digest=ownership.manifest_identity,generated_surfaces=(target.name,))
        manifest=ApplicationManifest.create(application="runtime_app",project_name="Runtime",modules=(module,),runtime=RuntimeContract.create(database="none",required_services=("api",)))
        report=RuntimeHarness(self.root,manifest,ownership,{"item":revision}).run()
        self.assertEqual(report.phases[0].category,RuntimeFailure.MANIFEST)


if __name__=="__main__": unittest.main()
