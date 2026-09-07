"""Deterministic coordinator for the trusted ArcaCore build lifecycle."""

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

from tools.application_manifest import ApplicationManifest
from tools.core.engine import write_text_atomic, write_text_atomic_exclusive
from tools.failure_localization import FailureLocalizer
from tools.minimal_regeneration import GenerationManifest
from tools.recovery_workflow import RecoveryAction,RecoveryAttempt,RecoveryPlanner,RecoveryWorkflow
from tools.runtime_harness import RuntimeReport,safe_diagnostic
from tools.schema_lifecycle import _digest


class BuildPhase(str,Enum):
    VALIDATE_INPUT="VALIDATE_INPUT"; SCHEMA_PLAN="SCHEMA_PLAN"; SCHEMA_APPLY="SCHEMA_APPLY"
    GENERATE="GENERATE"; VALIDATE_GENERATION="VALIDATE_GENERATION"; RUNTIME_VALIDATE="RUNTIME_VALIDATE"
    LOCALIZE_FAILURE="LOCALIZE_FAILURE"; RECOVER="RECOVER"; REVALIDATE="REVALIDATE"
    COMPLETE="COMPLETE"; FAILED="FAILED"


@dataclass(frozen=True)
class BuildEvent:
    phase:BuildPhase; success:bool; component_identity:str; category:str; detail:str=""
    def canonical_dict(self): return {"category":self.category,"component_identity":self.component_identity,
        "detail":self.detail,"phase":self.phase.value,"success":self.success}


@dataclass(frozen=True)
class BuildReport:
    application_identity:str; generation_identity:str; events:tuple[BuildEvent,...]
    runtime_identity:str|None; localization_identity:str|None; recovery_identity:str|None
    success:bool; report_identity:str; version:int=1

    @classmethod
    def create(cls,application_identity,generation_identity,events,*,runtime_identity=None,
               localization_identity=None,recovery_identity=None):
        events=tuple(events); success=bool(events) and events[-1].phase==BuildPhase.COMPLETE and events[-1].success
        body={"application_identity":application_identity,"events":[v.canonical_dict() for v in events],
            "generation_identity":generation_identity,"localization_identity":localization_identity,
            "recovery_identity":recovery_identity,"runtime_identity":runtime_identity,"success":success,"version":1}
        return cls(application_identity,generation_identity,events,runtime_identity,localization_identity,
            recovery_identity,success,_digest("arcacore-build-report/v1",body))
    def canonical_dict(self): return {"application_identity":self.application_identity,
        "events":[v.canonical_dict() for v in self.events],"generation_identity":self.generation_identity,
        "localization_identity":self.localization_identity,"recovery_identity":self.recovery_identity,
        "report_identity":self.report_identity,"runtime_identity":self.runtime_identity,
        "success":self.success,"version":self.version}
    def canonical_json(self): return json.dumps(self.canonical_dict(),sort_keys=True,separators=(",",":"))+"\n"


class BuildOrchestrator:
    def __init__(self,root:Path,manifest:ApplicationManifest,ownership:GenerationManifest,
                 runtime_harness,localizer:FailureLocalizer,recovery_workflow:RecoveryWorkflow,*,maximum_attempts=3):
        self.root=Path(root).resolve(); self.manifest=ApplicationManifest.from_dict(manifest.canonical_dict())
        self.ownership=GenerationManifest.from_dict(ownership.canonical_dict())
        if localizer.manifest.manifest_identity!=self.manifest.manifest_identity or localizer.ownership.manifest_identity!=self.ownership.manifest_identity:
            raise ValueError("Build component provenance mismatch.")
        self.harness=runtime_harness; self.localizer=localizer; self.workflow=recovery_workflow
        self.planner=RecoveryPlanner(self.manifest,self.ownership,maximum_attempts=maximum_attempts)
        self.state=self.root/".arcacore"; self.lock_path=self.state/"build.lock"; self.journal_path=self.state/"build-journal.json"

    def _journal(self,phase,predecessor=None):
        body={"application_identity":self.manifest.manifest_identity,"generation_identity":self.ownership.manifest_identity,
            "phase":phase.value,"predecessor":predecessor,"version":1}
        value=dict(body); value["journal_identity"]=_digest("arcacore-build-journal/v1",body)
        write_text_atomic(self.journal_path,json.dumps(value,sort_keys=True,separators=(",",":"))+"\n"); return value["journal_identity"]

    def _resume(self):
        if not self.journal_path.exists(): return None
        try:
            if self.journal_path.stat().st_size>100_000: raise ValueError("Build journal exceeds safety limit.")
            value=json.loads(self.journal_path.read_text(encoding="utf-8"))
        except (OSError,UnicodeError,json.JSONDecodeError) as error: raise ValueError("Build journal is invalid.") from error
        if not isinstance(value,dict) or set(value)!={"application_identity","generation_identity","phase","predecessor","version","journal_identity"} or value["version"]!=1:
            raise ValueError("Build journal is invalid.")
        body=dict(value); identity=body.pop("journal_identity")
        if identity!=_digest("arcacore-build-journal/v1",body) or value["application_identity"]!=self.manifest.manifest_identity or value["generation_identity"]!=self.ownership.manifest_identity:
            raise ValueError("Build journal provenance mismatch.")
        BuildPhase(value["phase"]); return identity

    def run(self,*,interrupt_after_phase=None):
        prior=self._resume(); lock_body={"application_identity":self.manifest.manifest_identity,"version":1}
        try: write_text_atomic_exclusive(self.lock_path,json.dumps(lock_body,sort_keys=True,separators=(",",":"))+"\n")
        except FileExistsError as error: raise TimeoutError("Application build is already locked.") from error
        events=[]; runtime=None; localization=None; recovery=None
        try:
            events.append(BuildEvent(BuildPhase.VALIDATE_INPUT,True,self.manifest.manifest_identity,"VALID"))
            prior=self._journal(BuildPhase.VALIDATE_INPUT,prior)
            if interrupt_after_phase==BuildPhase.VALIDATE_INPUT: raise InterruptedError("Simulated build interruption.")
            events.append(BuildEvent(BuildPhase.VALIDATE_GENERATION,True,self.ownership.manifest_identity,"VALID"))
            prior=self._journal(BuildPhase.VALIDATE_GENERATION,prior)
            runtime=self.harness.run(); events.append(BuildEvent(BuildPhase.RUNTIME_VALIDATE,runtime.success,runtime.report_identity,"PASS" if runtime.success else "FAIL"))
            prior=self._journal(BuildPhase.RUNTIME_VALIDATE,prior)
            if runtime.success:
                events.append(BuildEvent(BuildPhase.COMPLETE,True,runtime.report_identity,"VERIFIED")); self.journal_path.unlink(missing_ok=True)
                return BuildReport.create(self.manifest.manifest_identity,self.ownership.manifest_identity,events,runtime_identity=runtime.report_identity)
            localization=self.localizer.localize(runtime); events.append(BuildEvent(BuildPhase.LOCALIZE_FAILURE,True,localization.localization_identity,localization.confidence.value))
            plan=self.planner.plan(runtime,localization)
            if plan.action==RecoveryAction.STOP:
                events.append(BuildEvent(BuildPhase.FAILED,False,plan.plan_identity,plan.disposition.value))
            else:
                result=self.workflow.execute(plan)
                result_identity=result.report_identity if isinstance(result,RuntimeReport) else _digest("arcacore-recovery-result/v1",str(result))
                recovery=RecoveryAttempt.create(plan,result_identity,True)
                events.append(BuildEvent(BuildPhase.RECOVER,True,recovery.attempt_identity,plan.action.value))
                runtime=self.harness.run(); events.append(BuildEvent(BuildPhase.REVALIDATE,runtime.success,runtime.report_identity,"PASS" if runtime.success else "FAIL"))
                events.append(BuildEvent(BuildPhase.COMPLETE if runtime.success else BuildPhase.FAILED,runtime.success,runtime.report_identity,"VERIFIED" if runtime.success else "RECOVERY_FAILED"))
            self.journal_path.unlink(missing_ok=True)
            return BuildReport.create(self.manifest.manifest_identity,self.ownership.manifest_identity,events,
                runtime_identity=runtime.report_identity,localization_identity=localization.localization_identity,
                recovery_identity=None if recovery is None else recovery.attempt_identity)
        except InterruptedError: raise
        except Exception as error:
            events.append(BuildEvent(BuildPhase.FAILED,False,self.manifest.manifest_identity,"INVARIANT",safe_diagnostic(error,self.root)))
            return BuildReport.create(self.manifest.manifest_identity,self.ownership.manifest_identity,events)
        finally: self.lock_path.unlink(missing_ok=True)
