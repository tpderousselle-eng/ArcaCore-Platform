"""Evidence-based localization of runtime failures to generated provenance."""

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import PurePosixPath
import re
from typing import Mapping

from tools.application_manifest import ApplicationManifest
from tools.minimal_regeneration import GenerationManifest, OwnershipClass
from tools.runtime_harness import RuntimeFailure, RuntimePhase, RuntimeReport, safe_diagnostic
from tools.schema_lifecycle import _digest


KNOWN_GENERATORS = frozenset({"model", "schema", "crud", "service", "router", "test",
    "configuration", "runtime", "health", "migration", "docker", "kubernetes", "module"})
MAX_EVIDENCE = 4096


class FailureCategory(str, Enum):
    MANIFEST="MANIFEST"; GENERATION="GENERATION"; IMPORT="IMPORT"; STARTUP="STARTUP"
    READINESS="READINESS"; HEALTH="HEALTH"; DATABASE="DATABASE"; API="API"; TEST="TEST"
    MIGRATION="MIGRATION"; INFRASTRUCTURE="INFRASTRUCTURE"
    USER_OWNED_EXTENSION="USER_OWNED_EXTENSION"; UNKNOWN="UNKNOWN"


class ConfidenceClass(str, Enum):
    PROVEN="PROVEN"; MULTIPLE_CANDIDATES="MULTIPLE_CANDIDATES"; BOUNDARY="BOUNDARY"; UNKNOWN="UNKNOWN"


class ReasonCode(str, Enum):
    SURFACE_PATH_MATCH="SURFACE_PATH_MATCH"
    PHASE_PROVENANCE="PHASE_PROVENANCE"
    EXTERNAL_DATABASE="EXTERNAL_DATABASE"
    EXTERNAL_INFRASTRUCTURE="EXTERNAL_INFRASTRUCTURE"
    USER_OWNED_SURFACE="USER_OWNED_SURFACE"
    USER_MODIFIED_GENERATED_SURFACE="USER_MODIFIED_GENERATED_SURFACE"
    AMBIGUOUS_GENERATED_SURFACES="AMBIGUOUS_GENERATED_SURFACES"
    HOSTILE_EVIDENCE="HOSTILE_EVIDENCE"
    NO_PROVABLE_SURFACE="NO_PROVABLE_SURFACE"


@dataclass(frozen=True)
class SurfaceAttribution:
    path: str
    generator: str | None
    ownership: OwnershipClass

    def canonical_dict(self):
        return {"generator":self.generator,"ownership":self.ownership.value,"path":self.path}


@dataclass(frozen=True)
class FailureLocalization:
    category: FailureCategory
    phase: RuntimePhase
    surfaces: tuple[SurfaceAttribution,...]
    reason_code: ReasonCode
    confidence: ConfidenceClass
    application_manifest_digest: str
    generation_manifest_digest: str
    evidence: str
    localization_identity: str
    version: int=1

    @classmethod
    def create(cls, *, category, phase, surfaces, reason_code, confidence,
               application_manifest_digest, generation_manifest_digest, evidence):
        surfaces=tuple(sorted(surfaces,key=lambda v:(v.path,v.generator or "")))
        body={"application_manifest_digest":application_manifest_digest,"category":category.value,
            "confidence":confidence.value,"evidence":evidence,"generation_manifest_digest":generation_manifest_digest,
            "phase":phase.value,"reason_code":reason_code.value,
            "surfaces":[v.canonical_dict() for v in surfaces],"version":1}
        return cls(category,phase,surfaces,reason_code,confidence,application_manifest_digest,
            generation_manifest_digest,evidence,_digest("arcacore-failure-localization/v1",body))

    def canonical_dict(self):
        return {"application_manifest_digest":self.application_manifest_digest,"category":self.category.value,
            "confidence":self.confidence.value,"evidence":self.evidence,
            "generation_manifest_digest":self.generation_manifest_digest,
            "localization_identity":self.localization_identity,"phase":self.phase.value,
            "reason_code":self.reason_code.value,"surfaces":[v.canonical_dict() for v in self.surfaces],"version":self.version}

    def canonical_json(self): return json.dumps(self.canonical_dict(),sort_keys=True,separators=(",",":"))+"\n"


def _path(value):
    if not isinstance(value,str) or not value or "\\" in value or len(value)>240: raise ValueError("Evidence path is invalid.")
    path=PurePosixPath(value)
    if path.is_absolute() or path.as_posix()!=value or any(v in ("",".","..") for v in path.parts): raise ValueError("Evidence path is noncanonical.")
    return value


PHASE_CATEGORY={
    RuntimePhase.PREPARE:FailureCategory.MANIFEST, RuntimePhase.IMPORT:FailureCategory.IMPORT,
    RuntimePhase.STARTUP:FailureCategory.STARTUP, RuntimePhase.READINESS:FailureCategory.READINESS,
    RuntimePhase.HEALTH:FailureCategory.HEALTH, RuntimePhase.DATABASE:FailureCategory.DATABASE,
    RuntimePhase.API_SMOKE:FailureCategory.API, RuntimePhase.GENERATED_TESTS:FailureCategory.TEST,
    RuntimePhase.MIGRATION:FailureCategory.MIGRATION, RuntimePhase.SHUTDOWN:FailureCategory.INFRASTRUCTURE}

PHASE_GENERATORS={
    RuntimePhase.HEALTH:{"runtime","health","configuration"},
    RuntimePhase.API_SMOKE:{"router","service","crud"},
    RuntimePhase.GENERATED_TESTS:{"test"}, RuntimePhase.MIGRATION:{"migration"}}


class FailureLocalizer:
    def __init__(self, manifest:ApplicationManifest, ownership:GenerationManifest, *,
                 user_owned=(), ownership_overrides:Mapping[str,OwnershipClass]|None=None):
        if not isinstance(manifest,ApplicationManifest) or not isinstance(ownership,GenerationManifest):
            raise ValueError("Localization provenance is invalid.")
        verified=GenerationManifest.from_dict(ownership.canonical_dict())
        for item in verified.files:
            if item.generator not in KNOWN_GENERATORS: raise ValueError("Generator identity is not trusted.")
        self.manifest=manifest; self.ownership=verified
        self.entries={v.path:v for v in verified.files}
        self.user_owned=tuple(sorted(_path(v) for v in user_owned))
        overrides=ownership_overrides or {}
        self.overrides={_path(k):OwnershipClass(v) for k,v in overrides.items()}
        if any(v not in {OwnershipClass.CONFLICTED,OwnershipClass.USER_OWNED} for v in self.overrides.values()):
            raise ValueError("Localization ownership override is invalid.")

    def _validate_report(self, report):
        if not isinstance(report,RuntimeReport) or len(report.phases)>32: raise ValueError("Runtime report is invalid.")
        expected=RuntimeReport.create(report.application_manifest_digest,report.generation_manifest_digest,report.phases)
        if expected.report_identity!=report.report_identity or expected.success!=report.success: raise ValueError("Runtime report identity mismatch.")
        if report.application_manifest_digest!=self.manifest.manifest_identity or report.generation_manifest_digest!=self.ownership.manifest_identity:
            raise ValueError("Runtime report provenance mismatch.")
        if report.success: raise ValueError("A successful runtime report has no failure to localize.")
        failures=[v for v in report.phases if not v.success]
        if len(failures)!=1 or len(failures[0].diagnostic)>MAX_EVIDENCE: raise ValueError("Runtime failure evidence is invalid.")
        return failures[0]

    def localize(self,report):
        failure=self._validate_report(report); evidence=safe_diagnostic(failure.diagnostic).replace("\\","/")
        if "../" in evidence or "..\\" in failure.diagnostic:
            return self._result(failure,(),FailureCategory.UNKNOWN,ReasonCode.HOSTILE_EVIDENCE,ConfidenceClass.UNKNOWN,evidence)
        paths=sorted(self.entries.keys()|set(self.user_owned)|set(self.overrides))
        matched=[]
        for path in paths:
            if re.search(r"(?<![A-Za-z0-9_.-])"+re.escape(path)+r"(?![A-Za-z0-9_.-])",evidence):
                ownership=self.overrides.get(path,OwnershipClass.USER_OWNED if path in self.user_owned else OwnershipClass.GENERATOR_OWNED)
                generator=self.entries[path].generator if path in self.entries and ownership==OwnershipClass.GENERATOR_OWNED else None
                matched.append(SurfaceAttribution(path,generator,ownership))
        boundary=[v for v in matched if v.ownership!=OwnershipClass.GENERATOR_OWNED]
        if boundary:
            reason=ReasonCode.USER_MODIFIED_GENERATED_SURFACE if any(v.ownership==OwnershipClass.CONFLICTED for v in boundary) else ReasonCode.USER_OWNED_SURFACE
            return self._result(failure,boundary,FailureCategory.USER_OWNED_EXTENSION,reason,ConfidenceClass.BOUNDARY,evidence)
        if matched:
            confidence=ConfidenceClass.PROVEN if len(matched)==1 else ConfidenceClass.MULTIPLE_CANDIDATES
            reason=ReasonCode.SURFACE_PATH_MATCH if len(matched)==1 else ReasonCode.AMBIGUOUS_GENERATED_SURFACES
            return self._result(failure,matched,PHASE_CATEGORY.get(failure.phase,FailureCategory.UNKNOWN),reason,confidence,evidence)
        if failure.phase==RuntimePhase.DATABASE:
            return self._result(failure,(),FailureCategory.DATABASE,ReasonCode.EXTERNAL_DATABASE,ConfidenceClass.PROVEN,evidence)
        if failure.category==RuntimeFailure.INFRASTRUCTURE or failure.phase==RuntimePhase.SHUTDOWN:
            return self._result(failure,(),FailureCategory.INFRASTRUCTURE,ReasonCode.EXTERNAL_INFRASTRUCTURE,ConfidenceClass.PROVEN,evidence)
        generators=PHASE_GENERATORS.get(failure.phase,set())
        candidates=[SurfaceAttribution(v.path,v.generator,OwnershipClass.GENERATOR_OWNED) for v in self.ownership.files if v.generator in generators]
        if candidates:
            confidence=ConfidenceClass.PROVEN if len(candidates)==1 else ConfidenceClass.MULTIPLE_CANDIDATES
            reason=ReasonCode.PHASE_PROVENANCE if len(candidates)==1 else ReasonCode.AMBIGUOUS_GENERATED_SURFACES
            return self._result(failure,candidates,PHASE_CATEGORY.get(failure.phase,FailureCategory.UNKNOWN),reason,confidence,evidence)
        return self._result(failure,(),PHASE_CATEGORY.get(failure.phase,FailureCategory.UNKNOWN),ReasonCode.NO_PROVABLE_SURFACE,ConfidenceClass.UNKNOWN,evidence)

    def _result(self,failure,surfaces,category,reason,confidence,evidence):
        return FailureLocalization.create(category=category,phase=failure.phase,surfaces=surfaces,
            reason_code=reason,confidence=confidence,application_manifest_digest=self.manifest.manifest_identity,
            generation_manifest_digest=self.ownership.manifest_identity,evidence=evidence)
