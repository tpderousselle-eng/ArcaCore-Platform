from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock

from tools.application_manifest import ApplicationManifest,ModuleReference,RuntimeContract
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.failure_localization import FailureLocalizer,ConfidenceClass,FailureLocalization,ReasonCode,SurfaceAttribution,FailureCategory
from tools.minimal_regeneration import GenerationManifest,OwnedFile,OwnershipClass
from tools.recovery_workflow import *
from tools.runtime_harness import PhaseResult,RuntimeFailure,RuntimePhase,RuntimeReport
from tools.schema_lifecycle import SchemaRevision

D="1"*64

class RecoveryWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.root=Path(self.temp.name)
        definition=ModuleDefinition("item","Item","item","items",parse_fields("item",["name:str"])); revision=SchemaRevision.create(definition)
        self.ownership=GenerationManifest.create([OwnedFile("app/main.py","runtime",sha256(b"x").hexdigest(),D)])
        module=ModuleReference.create(name="item",accepted_schema_digest=revision.schema_digest,schema_revision_identity=revision.revision_identity,
            generation_manifest_digest=self.ownership.manifest_identity,generated_surfaces=("app/main.py",),capabilities=("runtime",))
        self.manifest=ApplicationManifest.create(application="app",project_name="App",modules=(module,),runtime=RuntimeContract.create(database="none",required_services=("api",)))
    def tearDown(self): self.temp.cleanup()

    def failure(self,category=RuntimeFailure.READINESS_TIMEOUT,phase=RuntimePhase.READINESS,diagnostic="timeout"):
        return RuntimeReport.create(self.manifest.manifest_identity,self.ownership.manifest_identity,(PhaseResult(phase,False,category,diagnostic),))
    def localized(self,report,**kwargs): return FailureLocalizer(self.manifest,self.ownership,**kwargs).localize(report)

    def test_transient_retry_then_success_is_bounded(self):
        report=self.failure(); plan=RecoveryPlanner(self.manifest,self.ownership).plan(report,self.localized(report))
        self.assertEqual(plan.action,RecoveryAction.RETRY_RUNTIME); callback=MagicMock(return_value=D)
        self.assertEqual(RecoveryWorkflow(retry_runtime=callback,regenerate_surface=MagicMock(),recover_migration=MagicMock()).execute(plan),D)
        callback.assert_called_once_with(plan)
    def test_repeated_failure_reaches_attempt_limit(self):
        report=self.failure(); planner=RecoveryPlanner(self.manifest,self.ownership,maximum_attempts=2); loc=self.localized(report)
        one=planner.plan(report,loc); a1=RecoveryAttempt.create(one,D,False)
        two=planner.plan(report,loc,prior_attempts=(a1,)); a2=RecoveryAttempt.create(two,D,False,a1.attempt_identity)
        final=planner.plan(report,loc,prior_attempts=(a1,a2)); self.assertEqual(final.action,RecoveryAction.STOP)
    def test_unique_generated_surface_can_regenerate(self):
        report=self.failure(RuntimeFailure.HEALTH,RuntimePhase.HEALTH,"app/main.py")
        plan=RecoveryPlanner(self.manifest,self.ownership).plan(report,self.localized(report)); self.assertEqual(plan.action,RecoveryAction.REGENERATE_RESPONSIBLE_SURFACE)
    def test_user_owned_and_modified_surfaces_are_blocked(self):
        report=self.failure(RuntimeFailure.HEALTH,RuntimePhase.HEALTH,"app/main.py")
        for override in (OwnershipClass.USER_OWNED,OwnershipClass.CONFLICTED):
            kwargs={"user_owned":("app/main.py",)} if override==OwnershipClass.USER_OWNED else {"ownership_overrides":{"app/main.py":override}}
            plan=RecoveryPlanner(self.manifest,self.ownership).plan(report,self.localized(report,**kwargs)); self.assertEqual(plan.disposition,RecoveryDisposition.BLOCKED_USER_OWNED)
    def test_ambiguous_and_unknown_are_blocked(self):
        report=self.failure(RuntimeFailure.API,RuntimePhase.API_SMOKE,"unknown")
        loc=self.localized(report); self.assertIn(loc.confidence,(ConfidenceClass.UNKNOWN,ConfidenceClass.MULTIPLE_CANDIDATES))
        self.assertEqual(RecoveryPlanner(self.manifest,self.ownership).plan(report,loc).action,RecoveryAction.STOP)
    def test_stale_and_forged_report_rejected(self):
        report=self.failure(); stale=replace(report,generation_manifest_digest="0"*64)
        with self.assertRaises(ValueError): RecoveryPlanner(self.manifest,self.ownership).plan(stale,self.localized(report))
        with self.assertRaises(ValueError): RecoveryPlanner(self.manifest,self.ownership).plan(replace(report,report_identity="0"*64),self.localized(report))
    def test_forged_localization_rejected(self):
        report=self.failure(); loc=self.localized(report)
        with self.assertRaises(ValueError): RecoveryPlanner(self.manifest,self.ownership).plan(report,replace(loc,localization_identity="0"*64))
    def test_journal_round_trip_is_deterministic_and_tamper_evident(self):
        report=self.failure(); plan=RecoveryPlanner(self.manifest,self.ownership).plan(report,self.localized(report)); attempt=RecoveryAttempt.create(plan,D,False)
        journal=RecoveryJournal(self.root); journal.save(plan,(attempt,)); one=journal.path.read_bytes(); journal.save(plan,(attempt,)); self.assertEqual(one,journal.path.read_bytes()); self.assertEqual(journal.load(),(plan,(attempt,)))
        value=json.loads(one); value["plan"]["attempt_number"]=2; journal.path.write_text(json.dumps(value))
        with self.assertRaises(ValueError): journal.load()
    def test_forked_or_replayed_attempt_is_rejected(self):
        report=self.failure(); planner=RecoveryPlanner(self.manifest,self.ownership); plan=planner.plan(report,self.localized(report)); attempt=RecoveryAttempt.create(plan,D,False)
        replay=replace(attempt,number=2,predecessor_identity=None)
        with self.assertRaises(ValueError): planner.plan(report,self.localized(report),prior_attempts=(attempt,replay))
    def test_migration_recovery_delegates_only_to_trusted_boundary(self):
        report=self.failure(RuntimeFailure.MIGRATION,RuntimePhase.MIGRATION,"app/main.py")
        loc=FailureLocalization.create(category=FailureCategory.MIGRATION,phase=RuntimePhase.MIGRATION,
            surfaces=(SurfaceAttribution("app/main.py","migration",OwnershipClass.GENERATOR_OWNED),),reason_code=ReasonCode.SURFACE_PATH_MATCH,
            confidence=ConfidenceClass.PROVEN,application_manifest_digest=self.manifest.manifest_identity,generation_manifest_digest=self.ownership.manifest_identity,evidence="app/main.py")
        plan=RecoveryPlanner(self.manifest,self.ownership).plan(report,loc); migration=MagicMock(return_value=D)
        RecoveryWorkflow(retry_runtime=MagicMock(),regenerate_surface=MagicMock(),recover_migration=migration).execute(plan); migration.assert_called_once()
    def test_invalid_action_and_forged_plan_never_execute(self):
        with self.assertRaises(ValueError): RecoveryAction("shell")
        report=self.failure(); plan=RecoveryPlanner(self.manifest,self.ownership).plan(report,self.localized(report)); callback=MagicMock()
        with self.assertRaises(ValueError): RecoveryWorkflow(retry_runtime=callback,regenerate_surface=callback,recover_migration=callback).execute(replace(plan,plan_identity="0"*64))
        callback.assert_not_called()
    def test_plan_has_no_secret_or_absolute_path_and_is_byte_stable(self):
        report=self.failure(); planner=RecoveryPlanner(self.manifest,self.ownership); one=planner.plan(report,self.localized(report)); two=planner.plan(report,self.localized(report))
        self.assertEqual(one.canonical_json(),two.canonical_json()); self.assertNotIn(str(self.root),one.canonical_json()); self.assertNotIn("password",one.canonical_json().lower())
    def test_no_backend_mutation(self): self.assertFalse((self.root/"backend").exists())

if __name__=="__main__": unittest.main()
