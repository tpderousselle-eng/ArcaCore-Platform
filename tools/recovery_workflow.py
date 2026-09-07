"""Deterministic, bounded recovery for validated ArcaCore runtime failures."""

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

from tools.application_manifest import ApplicationManifest
from tools.core.engine import write_text_atomic
from tools.failure_localization import ConfidenceClass, FailureLocalization, ReasonCode
from tools.minimal_regeneration import GenerationManifest, OwnershipClass
from tools.runtime_harness import RuntimeFailure, RuntimeReport
from tools.schema_lifecycle import _digest


class RecoveryDisposition(str, Enum):
    RECOVERABLE="RECOVERABLE"; RETRYABLE_TRANSIENT="RETRYABLE_TRANSIENT"
    BLOCKED_USER_OWNED="BLOCKED_USER_OWNED"; AMBIGUOUS="AMBIGUOUS"
    UNSUPPORTED="UNSUPPORTED"; TERMINAL="TERMINAL"


class RecoveryAction(str, Enum):
    RETRY_RUNTIME="RETRY_RUNTIME"
    RECOVER_INTERRUPTED_GENERATION="RECOVER_INTERRUPTED_GENERATION"
    REGENERATE_RESPONSIBLE_SURFACE="REGENERATE_RESPONSIBLE_SURFACE"
    RECOVER_MIGRATION_STATE="RECOVER_MIGRATION_STATE"
    RERUN_VALIDATION="RERUN_VALIDATION"
    STOP="STOP"


@dataclass(frozen=True)
class RecoveryPlan:
    application_identity: str; generation_identity: str; failure_identity: str
    localization_identity: str; disposition: RecoveryDisposition; action: RecoveryAction
    surfaces: tuple[str,...]; attempt_number: int; maximum_attempts: int; plan_identity: str
    version: int=1

    @classmethod
    def create(cls, *, application_identity, generation_identity, failure_identity,
               localization_identity, disposition, action, surfaces=(), attempt_number=1,
               maximum_attempts=3):
        surfaces=tuple(sorted(surfaces))
        if type(attempt_number) is not int or type(maximum_attempts) is not int or not 1 <= attempt_number <= maximum_attempts <= 5:
            raise ValueError("Recovery attempt budget is invalid.")
        body={"action":RecoveryAction(action).value,"application_identity":application_identity,
            "attempt_number":attempt_number,"disposition":RecoveryDisposition(disposition).value,
            "failure_identity":failure_identity,"generation_identity":generation_identity,
            "localization_identity":localization_identity,"maximum_attempts":maximum_attempts,
            "surfaces":list(surfaces),"version":1}
        return cls(application_identity,generation_identity,failure_identity,localization_identity,
            RecoveryDisposition(disposition),RecoveryAction(action),surfaces,attempt_number,
            maximum_attempts,_digest("arcacore-recovery-plan/v1",body))

    def canonical_dict(self):
        return {"action":self.action.value,"application_identity":self.application_identity,
            "attempt_number":self.attempt_number,"disposition":self.disposition.value,
            "failure_identity":self.failure_identity,"generation_identity":self.generation_identity,
            "localization_identity":self.localization_identity,"maximum_attempts":self.maximum_attempts,
            "plan_identity":self.plan_identity,"surfaces":list(self.surfaces),"version":self.version}
    def canonical_json(self): return json.dumps(self.canonical_dict(),sort_keys=True,separators=(",",":"))+"\n"


@dataclass(frozen=True)
class RecoveryAttempt:
    plan_identity: str; number: int; predecessor_identity: str|None
    result_identity: str; success: bool; attempt_identity: str; version: int=1

    @classmethod
    def create(cls, plan, result_identity, success, predecessor=None):
        if not isinstance(plan,RecoveryPlan) or type(success) is not bool or not isinstance(result_identity,str) or len(result_identity)!=64:
            raise ValueError("Recovery attempt is invalid.")
        body={"number":plan.attempt_number,"plan_identity":plan.plan_identity,
            "predecessor_identity":predecessor,"result_identity":result_identity,
            "success":success,"version":1}
        return cls(plan.plan_identity,plan.attempt_number,predecessor,result_identity,success,
            _digest("arcacore-recovery-attempt/v1",body))
    def canonical_dict(self): return {"attempt_identity":self.attempt_identity,"number":self.number,
        "plan_identity":self.plan_identity,"predecessor_identity":self.predecessor_identity,
        "result_identity":self.result_identity,"success":self.success,"version":self.version}


class RecoveryPlanner:
    def __init__(self, manifest, ownership, *, maximum_attempts=3):
        if not isinstance(manifest,ApplicationManifest) or not isinstance(ownership,GenerationManifest):
            raise ValueError("Recovery provenance is invalid.")
        self.manifest=ApplicationManifest.from_dict(manifest.canonical_dict())
        self.ownership=GenerationManifest.from_dict(ownership.canonical_dict())
        if type(maximum_attempts) is not int or not 1 <= maximum_attempts <= 5: raise ValueError("Recovery attempt budget is invalid.")
        self.maximum_attempts=maximum_attempts

    def plan(self, report, localization, *, prior_attempts=()):
        if not isinstance(report,RuntimeReport) or RuntimeReport.create(report.application_manifest_digest,report.generation_manifest_digest,report.phases)!=report:
            raise ValueError("Runtime report identity mismatch.")
        if report.success or report.application_manifest_digest!=self.manifest.manifest_identity or report.generation_manifest_digest!=self.ownership.manifest_identity:
            raise ValueError("Runtime report is stale or has invalid provenance.")
        if not isinstance(localization,FailureLocalization): raise ValueError("Failure localization is invalid.")
        rebuilt=FailureLocalization.create(category=localization.category,phase=localization.phase,
            surfaces=localization.surfaces,reason_code=localization.reason_code,confidence=localization.confidence,
            application_manifest_digest=localization.application_manifest_digest,
            generation_manifest_digest=localization.generation_manifest_digest,evidence=localization.evidence)
        if rebuilt!=localization or localization.application_manifest_digest!=self.manifest.manifest_identity or localization.generation_manifest_digest!=self.ownership.manifest_identity:
            raise ValueError("Failure localization identity mismatch.")
        attempts=tuple(prior_attempts)
        if any(not isinstance(v,RecoveryAttempt) for v in attempts): raise ValueError("Recovery attempt history is invalid.")
        for index,item in enumerate(attempts):
            if item.number!=index+1 or item.predecessor_identity!=(attempts[index-1].attempt_identity if index else None):
                raise ValueError("Recovery attempt lineage is forked or replayed.")
        number=len(attempts)+1
        failure=next(v for v in report.phases if not v.success)
        disposition=RecoveryDisposition.TERMINAL; action=RecoveryAction.STOP; surfaces=()
        if number>self.maximum_attempts:
            number=self.maximum_attempts; disposition=RecoveryDisposition.TERMINAL
        elif localization.reason_code in (ReasonCode.USER_OWNED_SURFACE,ReasonCode.USER_MODIFIED_GENERATED_SURFACE):
            disposition=RecoveryDisposition.BLOCKED_USER_OWNED
        elif failure.category in (RuntimeFailure.READINESS_TIMEOUT,RuntimeFailure.INFRASTRUCTURE):
            disposition=RecoveryDisposition.RETRYABLE_TRANSIENT; action=RecoveryAction.RETRY_RUNTIME
        elif localization.confidence in (ConfidenceClass.UNKNOWN,ConfidenceClass.MULTIPLE_CANDIDATES):
            disposition=RecoveryDisposition.AMBIGUOUS
        elif localization.surfaces and len(localization.surfaces)==1 and localization.surfaces[0].ownership==OwnershipClass.GENERATOR_OWNED:
            disposition=RecoveryDisposition.RECOVERABLE
            action=RecoveryAction.RECOVER_MIGRATION_STATE if localization.surfaces[0].generator=="migration" else RecoveryAction.REGENERATE_RESPONSIBLE_SURFACE
            surfaces=(localization.surfaces[0].path,)
        return RecoveryPlan.create(application_identity=self.manifest.manifest_identity,
            generation_identity=self.ownership.manifest_identity,failure_identity=report.report_identity,
            localization_identity=localization.localization_identity,disposition=disposition,action=action,
            surfaces=surfaces,attempt_number=number,maximum_attempts=self.maximum_attempts)


class RecoveryJournal:
    def __init__(self, root:Path):
        self.root=Path(root).resolve(); self.path=self.root/".arcacore"/"recovery-journal.json"

    def save(self, plan, attempts):
        attempts=tuple(attempts); self._validate(plan,attempts)
        body={"attempts":[v.canonical_dict() for v in attempts],"plan":plan.canonical_dict(),"version":1}
        body["journal_identity"]=_digest("arcacore-recovery-journal/v1",body)
        write_text_atomic(self.path,json.dumps(body,sort_keys=True,separators=(",",":"))+"\n")

    def _validate(self, plan, attempts):
        if not isinstance(plan,RecoveryPlan): raise ValueError("Recovery journal plan is invalid.")
        expected=RecoveryPlan.create(application_identity=plan.application_identity,generation_identity=plan.generation_identity,
            failure_identity=plan.failure_identity,localization_identity=plan.localization_identity,
            disposition=plan.disposition,action=plan.action,surfaces=plan.surfaces,
            attempt_number=plan.attempt_number,maximum_attempts=plan.maximum_attempts)
        if expected!=plan: raise ValueError("Recovery plan identity mismatch.")
        for index,item in enumerate(attempts):
            if item.number!=index+1 or item.predecessor_identity!=(attempts[index-1].attempt_identity if index else None):
                raise ValueError("Recovery attempt lineage is forked or replayed.")

    def load(self):
        try:
            if self.path.stat().st_size>1_000_000: raise ValueError("Recovery journal exceeds safety limit.")
            value=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,UnicodeError,json.JSONDecodeError) as error: raise ValueError("Recovery journal is invalid.") from error
        if not isinstance(value,dict) or set(value)!={"attempts","journal_identity","plan","version"} or value["version"]!=1:
            raise ValueError("Recovery journal is invalid.")
        body=dict(value); identity=body.pop("journal_identity")
        if identity!=_digest("arcacore-recovery-journal/v1",body): raise ValueError("Recovery journal identity mismatch.")
        p=value["plan"]
        plan=RecoveryPlan.create(application_identity=p["application_identity"],generation_identity=p["generation_identity"],
            failure_identity=p["failure_identity"],localization_identity=p["localization_identity"],disposition=p["disposition"],
            action=p["action"],surfaces=p["surfaces"],attempt_number=p["attempt_number"],maximum_attempts=p["maximum_attempts"])
        if plan.canonical_dict()!=p: raise ValueError("Recovery plan identity mismatch.")
        attempts=[]
        for row in value["attempts"]:
            body={k:row[k] for k in ("number","plan_identity","predecessor_identity","result_identity","success","version")}
            expected=_digest("arcacore-recovery-attempt/v1",body)
            if expected!=row.get("attempt_identity"): raise ValueError("Recovery attempt identity mismatch.")
            attempts.append(RecoveryAttempt(row["plan_identity"],row["number"],row["predecessor_identity"],row["result_identity"],row["success"],expected,row["version"]))
        self._validate(plan,attempts); return plan,tuple(attempts)


class RecoveryWorkflow:
    def __init__(self, *, retry_runtime, regenerate_surface, recover_migration):
        self._actions={RecoveryAction.RETRY_RUNTIME:retry_runtime,
            RecoveryAction.REGENERATE_RESPONSIBLE_SURFACE:regenerate_surface,
            RecoveryAction.RECOVER_MIGRATION_STATE:recover_migration}

    def execute(self, plan):
        if not isinstance(plan,RecoveryPlan): raise ValueError("Recovery plan is invalid.")
        expected=RecoveryPlan.create(application_identity=plan.application_identity,generation_identity=plan.generation_identity,
            failure_identity=plan.failure_identity,localization_identity=plan.localization_identity,
            disposition=plan.disposition,action=plan.action,surfaces=plan.surfaces,
            attempt_number=plan.attempt_number,maximum_attempts=plan.maximum_attempts)
        if expected!=plan: raise ValueError("Recovery plan identity mismatch.")
        if plan.action==RecoveryAction.STOP: return None
        return self._actions[plan.action](plan)
