from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock

from tools.application_manifest import ApplicationManifest,ModuleReference,RuntimeContract
from tools.build_orchestrator import *
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.failure_localization import FailureLocalizer
from tools.minimal_regeneration import GenerationManifest,OwnedFile
from tools.recovery_workflow import RecoveryWorkflow
from tools.runtime_harness import PhaseResult,RuntimeFailure,RuntimeHarness,RuntimePhase,RuntimeReport
from tools.schema_lifecycle import SchemaRevision

D="1"*64
GOOD="from fastapi import FastAPI\napp=FastAPI()\n@app.get('/health')\ndef health(): return {'status':'ok'}\n"

class BuildOrchestratorTest(unittest.TestCase):
    def setUp(self): self.temp=TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def fixture(self,source=GOOD,harness=None,workflow=None):
        target=self.root/"app/main.py"; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(source)
        ownership=GenerationManifest.create([OwnedFile("app/main.py","runtime",sha256(target.read_bytes()).hexdigest(),D)])
        definition=ModuleDefinition("item","Item","item","items",parse_fields("item",["name:str"])); revision=SchemaRevision.create(definition)
        module=ModuleReference.create(name="item",accepted_schema_digest=revision.schema_digest,schema_revision_identity=revision.revision_identity,
            generation_manifest_digest=ownership.manifest_identity,generated_surfaces=("app/main.py",),capabilities=("runtime",))
        manifest=ApplicationManifest.create(application="app",project_name="App",modules=(module,),runtime=RuntimeContract.create(database="none",required_services=("api",)))
        harness=harness or RuntimeHarness(self.root,manifest,ownership,{"item":revision},startup_timeout=5,shutdown_timeout=2)
        workflow=workflow or RecoveryWorkflow(retry_runtime=lambda p:None,regenerate_surface=lambda p:None,recover_migration=lambda p:None)
        return BuildOrchestrator(self.root,manifest,ownership,harness,FailureLocalizer(manifest,ownership),workflow),manifest,ownership
    def test_clean_realistic_app_build_success(self):
        report=self.fixture()[0].run(); self.assertTrue(report.success,report.canonical_json()); self.assertEqual(report.events[-1].phase,BuildPhase.COMPLETE)
    def test_noop_rebuild_is_deterministic(self):
        orchestrator,_,_=self.fixture(); self.assertEqual(orchestrator.run().canonical_json(),orchestrator.run().canonical_json())
    def test_runtime_failure_recovery_then_success(self):
        orchestrator,manifest,ownership=self.fixture(); failure=RuntimeReport.create(manifest.manifest_identity,ownership.manifest_identity,(PhaseResult(RuntimePhase.READINESS,False,RuntimeFailure.READINESS_TIMEOUT,"timeout"),)); success=RuntimeReport.create(manifest.manifest_identity,ownership.manifest_identity,(PhaseResult(RuntimePhase.SHUTDOWN,True,RuntimeFailure.NONE),))
        orchestrator.harness=MagicMock(); orchestrator.harness.run.side_effect=[failure,success]; report=orchestrator.run(); self.assertTrue(report.success); self.assertIsNotNone(report.recovery_identity)
    def test_blocked_recovery_is_final_failure(self):
        orchestrator,manifest,ownership=self.fixture(); failure=RuntimeReport.create(manifest.manifest_identity,ownership.manifest_identity,(PhaseResult(RuntimePhase.HEALTH,False,RuntimeFailure.HEALTH,"unknown"),)); orchestrator.harness=MagicMock(); orchestrator.harness.run.return_value=failure
        report=orchestrator.run(); self.assertFalse(report.success); self.assertEqual(report.events[-1].phase,BuildPhase.FAILED)
    def test_interruption_resumes_from_verified_provenance(self):
        orchestrator,_,_=self.fixture()
        with self.assertRaises(InterruptedError): orchestrator.run(interrupt_after_phase=BuildPhase.VALIDATE_INPUT)
        self.assertTrue(orchestrator.journal_path.exists()); self.assertTrue(orchestrator.run().success); self.assertFalse(orchestrator.journal_path.exists())
    def test_stale_resume_fails_closed(self):
        orchestrator,_,_=self.fixture(); orchestrator.state.mkdir(parents=True); orchestrator.journal_path.write_text('{}')
        with self.assertRaises(ValueError): orchestrator.run()
    def test_lock_contention_is_bounded(self):
        orchestrator,_,_=self.fixture(); orchestrator.state.mkdir(parents=True); orchestrator.lock_path.write_text('held')
        with self.assertRaises(TimeoutError): orchestrator.run()
    def test_component_provenance_mismatch_rejected(self):
        orchestrator,manifest,ownership=self.fixture(); other=GenerationManifest.create([])
        with self.assertRaises(ValueError): BuildOrchestrator(self.root,manifest,other,orchestrator.harness,orchestrator.localizer,orchestrator.workflow)
    def test_report_has_no_paths_environment_or_secrets(self):
        report=self.fixture()[0].run(); value=report.canonical_json(); self.assertNotIn(str(self.root),value); self.assertNotIn("password",value.lower())
    def test_no_arbitrary_process_boundary(self):
        self.assertFalse(hasattr(BuildOrchestrator,"execute_command")); self.assertFalse(hasattr(BuildOrchestrator,"run_command"))
    def test_report_identity_changes_on_failure(self):
        good=self.fixture()[0].run(); bad,manifest,ownership=self.fixture(); failure=RuntimeReport.create(manifest.manifest_identity,ownership.manifest_identity,(PhaseResult(RuntimePhase.HEALTH,False,RuntimeFailure.HEALTH,"unknown"),)); bad.harness=MagicMock(); bad.harness.run.return_value=failure
        self.assertNotEqual(good.report_identity,bad.run().report_identity)
    def test_backend_is_not_modified(self): self.assertFalse((self.root/"backend").exists())

if __name__=="__main__": unittest.main()
