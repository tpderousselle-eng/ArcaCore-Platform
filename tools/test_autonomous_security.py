from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock,patch

from tools.build_orchestrator import BuildEvent,BuildPhase,BuildReport
from tools.recovery_workflow import RecoveryAction,RecoveryAttempt,RecoveryDisposition,RecoveryJournal,RecoveryPlan,RecoveryWorkflow

D="1"*64

def plan(**changes):
    values=dict(application_identity=D,generation_identity=D,failure_identity=D,localization_identity=D,
        disposition=RecoveryDisposition.RETRYABLE_TRANSIENT,action=RecoveryAction.RETRY_RUNTIME,
        attempt_number=1,maximum_attempts=3)
    values.update(changes); return RecoveryPlan.create(**values)

class AutonomousSecurityTest(unittest.TestCase):
    def test_identity_and_path_forgery_fail_closed(self):
        with self.assertRaises(ValueError): plan(application_identity="bad")
        with self.assertRaises(ValueError): plan(disposition=RecoveryDisposition.RECOVERABLE,action=RecoveryAction.REGENERATE_RESPONSIBLE_SURFACE,surfaces=("../backend/x",))
    def test_action_disposition_confusion_is_rejected(self):
        with self.assertRaises(ValueError): plan(action=RecoveryAction.STOP)
        with self.assertRaises(ValueError): plan(disposition=RecoveryDisposition.RECOVERABLE,action=RecoveryAction.RETRY_RUNTIME)
    def test_forged_plan_never_reaches_callback(self):
        callback=MagicMock(); workflow=RecoveryWorkflow(retry_runtime=callback,regenerate_surface=callback,recover_migration=callback)
        with self.assertRaises(ValueError): workflow.execute(replace(plan(),plan_identity="0"*64))
        callback.assert_not_called()
    def test_success_report_requires_verified_runtime(self):
        complete=BuildEvent(BuildPhase.COMPLETE,True,D,"VERIFIED")
        with self.assertRaises(ValueError): BuildReport.create(D,D,(complete,),runtime_identity=D)
        failed=BuildEvent(BuildPhase.RUNTIME_VALIDATE,False,D,"FAIL")
        with self.assertRaises(ValueError): BuildReport.create(D,D,(failed,complete),runtime_identity=D)
        claimed=BuildEvent(BuildPhase.RUNTIME_VALIDATE,True,D,"PASS")
        with self.assertRaises(ValueError): BuildReport.create(D,D,(claimed,complete),runtime_identity=D)
    def test_diagnostics_are_bounded_and_controls_rejected(self):
        with self.assertRaises(ValueError): BuildReport.create(D,D,(BuildEvent(BuildPhase.FAILED,False,D,"FAIL","x"*4097),))
        with self.assertRaises(ValueError): BuildReport.create(D,D,(BuildEvent(BuildPhase.FAILED,False,D,"FAIL\n"),))
    def test_recovery_attempt_identity_cannot_be_forged(self):
        attempt=RecoveryAttempt.create(plan(),D,False)
        journal_root=TemporaryDirectory(); self.addCleanup(journal_root.cleanup); journal=RecoveryJournal(Path(journal_root.name))
        with self.assertRaises(ValueError): journal.save(plan(),(replace(attempt,attempt_identity="0"*64),))
    def test_journal_symlink_escape_is_rejected(self):
        with TemporaryDirectory() as root:
            original=Path.is_symlink
            with patch.object(Path,"is_symlink",lambda value:value.name==".arcacore" or original(value)):
                with self.assertRaises(ValueError): RecoveryJournal(Path(root)).save(plan(),())
    def test_no_shell_or_eval_execution_surface(self):
        import inspect,tools.recovery_workflow as recovery,tools.build_orchestrator as build
        source=inspect.getsource(recovery)+inspect.getsource(build)
        self.assertNotIn("shell=True",source); self.assertNotIn("eval(",source); self.assertNotIn("exec(",source)
    def test_only_enum_actions_are_accepted(self):
        with self.assertRaises(ValueError): plan(action="RUN_COMMAND")

if __name__=="__main__": unittest.main()
