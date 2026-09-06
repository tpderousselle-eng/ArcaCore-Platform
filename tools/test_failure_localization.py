from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.application_manifest import ApplicationManifest,ModuleReference,RuntimeContract
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.failure_localization import (ConfidenceClass,FailureCategory,FailureLocalizer,
    ReasonCode)
from tools.minimal_regeneration import GenerationManifest,OwnedFile,OwnershipClass
from tools.runtime_harness import PhaseResult,RuntimeFailure,RuntimePhase,RuntimeReport
from tools.schema_lifecycle import SchemaRevision


D="1"*64


class FailureLocalizationTest(unittest.TestCase):
    def fixture(self,entries=None,**kwargs):
        entries=entries or [("app/models/item.py","model"),("app/schemas/item.py","schema"),("app/routers/item.py","router"),("app/services/item.py","service"),("app/main.py","runtime"),("tests/test_item.py","test"),("migrations/item.py","migration")]
        ownership=GenerationManifest.create([OwnedFile(p,g,sha256(p.encode()).hexdigest(),D) for p,g in entries])
        definition=ModuleDefinition("item","Item","item","items",parse_fields("item",["name:str"])); revision=SchemaRevision.create(definition)
        module=ModuleReference.create(name="item",accepted_schema_digest=revision.schema_digest,schema_revision_identity=revision.revision_identity,
            generation_manifest_digest=ownership.manifest_identity,generated_surfaces=tuple(p for p,_ in entries))
        manifest=ApplicationManifest.create(application="app",project_name="App",modules=(module,),runtime=RuntimeContract.create(database="none",required_services=("api",)))
        return FailureLocalizer(manifest,ownership,**kwargs),manifest,ownership

    def report(self,manifest,ownership,phase,diagnostic="failure",category=RuntimeFailure.PROCESS):
        return RuntimeReport.create(manifest.manifest_identity,ownership.manifest_identity,(PhaseResult(phase,False,category,diagnostic),))

    def test_model_schema_router_service_health_test_and_migration_localize(self):
        localizer,m,o=self.fixture()
        cases=[(RuntimePhase.IMPORT,"app/models/item.py",FailureCategory.IMPORT,"model"),(RuntimePhase.IMPORT,"app/schemas/item.py",FailureCategory.IMPORT,"schema"),
            (RuntimePhase.API_SMOKE,"app/routers/item.py",FailureCategory.API,"router"),(RuntimePhase.API_SMOKE,"app/services/item.py",FailureCategory.API,"service"),
            (RuntimePhase.HEALTH,"app/main.py",FailureCategory.HEALTH,"runtime"),(RuntimePhase.GENERATED_TESTS,"tests/test_item.py",FailureCategory.TEST,"test"),
            (RuntimePhase.MIGRATION,"migrations/item.py",FailureCategory.MIGRATION,"migration")]
        for phase,path,category,generator in cases:
            result=localizer.localize(self.report(m,o,phase,f"trace: {path}:12")); self.assertEqual((result.category,result.surfaces[0].generator),(category,generator))

    def test_database_and_infrastructure_are_not_blame_assigned(self):
        localizer,m,o=self.fixture()
        db=localizer.localize(self.report(m,o,RuntimePhase.DATABASE,category=RuntimeFailure.DATABASE)); self.assertEqual((db.category,db.surfaces),(FailureCategory.DATABASE,()))
        infra=localizer.localize(self.report(m,o,RuntimePhase.SHUTDOWN,category=RuntimeFailure.INFRASTRUCTURE)); self.assertEqual(infra.category,FailureCategory.INFRASTRUCTURE)

    def test_user_owned_and_modified_generated_boundaries(self):
        localizer,m,o=self.fixture(user_owned=("extensions/hook.py",)); result=localizer.localize(self.report(m,o,RuntimePhase.IMPORT,"extensions/hook.py"))
        self.assertEqual((result.category,result.reason_code),(FailureCategory.USER_OWNED_EXTENSION,ReasonCode.USER_OWNED_SURFACE))
        localizer,m,o=self.fixture(ownership_overrides={"app/models/item.py":OwnershipClass.CONFLICTED}); result=localizer.localize(self.report(m,o,RuntimePhase.IMPORT,"app/models/item.py"))
        self.assertEqual(result.reason_code,ReasonCode.USER_MODIFIED_GENERATED_SURFACE); self.assertIsNone(result.surfaces[0].generator)

    def test_ambiguous_multiple_and_unknown_fail_honestly(self):
        localizer,m,o=self.fixture(); result=localizer.localize(self.report(m,o,RuntimePhase.IMPORT,"app/models/item.py and app/schemas/item.py"))
        self.assertEqual(result.confidence,ConfidenceClass.MULTIPLE_CANDIDATES)
        unknown=localizer.localize(self.report(m,o,RuntimePhase.IMPORT,"missing dependency")); self.assertEqual((unknown.confidence,unknown.surfaces),(ConfidenceClass.UNKNOWN,()))

    def test_phase_provenance_is_used_only_when_unique(self):
        localizer,m,o=self.fixture(entries=[("app/main.py","runtime")]); result=localizer.localize(self.report(m,o,RuntimePhase.HEALTH,"bad payload"))
        self.assertEqual((result.reason_code,result.surfaces[0].generator),(ReasonCode.PHASE_PROVENANCE,"runtime"))

    def test_deterministic_input_order_and_byte_identity(self):
        entries=[("app/routers/item.py","router"),("app/services/item.py","service")]
        a,m,o=self.fixture(entries); b,_,_=self.fixture(list(reversed(entries)))
        report=self.report(m,o,RuntimePhase.API_SMOKE,"app/services/item.py app/routers/item.py")
        self.assertEqual(a.localize(report).canonical_json(),b.localize(report).canonical_json())

    def test_forged_report_ownership_and_generator_identity_rejected(self):
        localizer,m,o=self.fixture(); report=self.report(m,o,RuntimePhase.IMPORT)
        with self.assertRaisesRegex(ValueError,"identity mismatch"): localizer.localize(replace(report,report_identity="0"*64))
        value=o.canonical_dict(); value["manifest_identity"]="0"*64
        with self.assertRaises(ValueError): FailureLocalizer(m,GenerationManifest.from_dict(value))
        with self.assertRaisesRegex(ValueError,"not trusted"): self.fixture(entries=[("app/main.py","evil.import")])

    def test_traversal_ansi_controls_oversize_and_no_file_reads(self):
        localizer,m,o=self.fixture(); hostile=localizer.localize(self.report(m,o,RuntimePhase.IMPORT,"\x1b[31m../../app/models/item.py\x00"))
        self.assertEqual((hostile.reason_code,hostile.surfaces),(ReasonCode.HOSTILE_EVIDENCE,()))
        with self.assertRaisesRegex(ValueError,"evidence"):
            localizer.localize(self.report(m,o,RuntimePhase.IMPORT,"x"*4097))
        with patch.object(Path,"read_text",side_effect=AssertionError("must not read")):
            localizer.localize(self.report(m,o,RuntimePhase.IMPORT,"app/models/item.py"))

    def test_symlink_strings_and_arbitrary_import_text_are_never_followed(self):
        localizer,m,o=self.fixture(user_owned=("extensions/link.py",))
        with patch.object(Path,"resolve",side_effect=AssertionError("must not resolve")):
            result=localizer.localize(self.report(m,o,RuntimePhase.IMPORT,"extensions/link.py import os; os.system('x')"))
        self.assertEqual(result.category,FailureCategory.USER_OWNED_EXTENSION)

    def test_runtime_harness_returns_report_and_localization_on_failure(self):
        localizer,m,o=self.fixture(entries=[("app/main.py","runtime")])
        class HarnessResult:
            def run(self): return RuntimeReport.create(m.manifest_identity,o.manifest_identity,(PhaseResult(RuntimePhase.HEALTH,False,RuntimeFailure.HEALTH,"bad health"),))
        from tools.runtime_harness import RuntimeHarness
        report,localization=RuntimeHarness.run_with_localization(HarnessResult(),localizer)
        self.assertFalse(report.success); self.assertEqual(localization.category,FailureCategory.HEALTH)


if __name__=="__main__": unittest.main()
