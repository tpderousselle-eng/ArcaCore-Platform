import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.application_manifest import (ApplicationManifest, EnvironmentCategory,
    EnvironmentRequirement, ExecutionMode, ModuleReference, RuntimeContract,
    TargetPlatform, load_application_manifest, save_application_manifest)
from tools.core.field_parser import parse_fields
from tools.core.module_definition import ModuleDefinition
from tools.minimal_regeneration import GenerationManifest, OwnedFile
from tools.schema_lifecycle import LifecycleState, SchemaRevision


D1 = "1" * 64


def revision(name):
    module = ModuleDefinition(name, name.title(), name, name + "s", parse_fields(name, ["name:str"]))
    return SchemaRevision.create(module)


class ApplicationManifestTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.root = Path(self.temp.name)
        self.item = revision("item")
        self.ownership = GenerationManifest.create([OwnedFile("app/item.py", "model", D1, D1)])

    def tearDown(self): self.temp.cleanup()

    def module(self, name="item", dependencies=(), revision=None, surfaces=("app/item.py",)):
        revision = revision or self.item
        return ModuleReference.create(name=name, dependencies=dependencies,
            accepted_schema_digest=revision.schema_digest,
            schema_revision_identity=revision.revision_identity,
            schema_parent_digest=revision.parent_schema_digest,
            migration_revision=revision.migration_revision,
            generation_manifest_digest=self.ownership.manifest_identity,
            generated_surfaces=surfaces, capabilities=("crud",))

    def manifest(self, modules=None):
        return ApplicationManifest.create(application="catalog", project_name="Catalog",
            modules=modules or [self.module()], runtime=RuntimeContract.create(),
            environment=[EnvironmentRequirement.from_dict({"name":"DATABASE_URL","required":True,"category":"credential","secret":True})])

    def test_minimal_manifest_is_stable_and_validates_references(self):
        manifest = self.manifest()
        self.assertEqual(manifest.canonical_json(), self.manifest().canonical_json())
        self.assertTrue(manifest.validate_references({"item": self.item}, self.ownership))
        self.assertNotIn(str(self.root), manifest.canonical_json())

    def test_multi_module_input_order_and_dependency_graph_are_canonical(self):
        owner = revision("owner")
        a = self.module(); b = self.module("owner", ("item",), owner, ())
        one = self.manifest([b, a]); two = self.manifest([a, b])
        self.assertEqual(one.canonical_json(), two.canonical_json())
        self.assertEqual([v.name for v in one.modules], ["item", "owner"])

    def test_missing_cycle_self_and_duplicate_dependencies_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing"): self.manifest([self.module(dependencies=("absent",))])
        with self.assertRaises(ValueError): self.module(dependencies=("item",))
        with self.assertRaises(ValueError): self.module(dependencies=("other", "other"))
        other = revision("other")
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.manifest([self.module(dependencies=("other",)), self.module("other", ("item",), other, ())])

    def test_duplicate_module_and_invalid_identifiers_rejected(self):
        with self.assertRaises(ValueError): self.manifest([self.module(), self.module()])
        with self.assertRaises(ValueError): self.module("../bad")
        with self.assertRaises(ValueError): ApplicationManifest.create(application="bad-name", project_name="x", modules=[self.module()], runtime=RuntimeContract.create())

    def test_stale_forged_pending_schema_references_rejected(self):
        forged = self.module(); value = forged.canonical_dict(); value["accepted_schema_digest"] = "0" * 64
        bad = ModuleReference.from_dict(value)
        with self.assertRaisesRegex(ValueError, "schema provenance"): self.manifest([bad]).validate_references({"item":self.item}, self.ownership)
        pending = SchemaRevision.create(ModuleDefinition("item","Item","item","items",parse_fields("item",["name:str"])), state=LifecycleState.PENDING_EXECUTION)
        with self.assertRaisesRegex(ValueError, "accepted schema"): self.manifest().validate_references({"item":pending}, self.ownership)

    def test_ownership_digest_and_surface_are_verified(self):
        value=self.module().canonical_dict(); value["generation_manifest_digest"]="0"*64
        with self.assertRaisesRegex(ValueError,"ownership manifest digest"): self.manifest([ModuleReference.from_dict(value)]).validate_references({"item":self.item},self.ownership)
        with self.assertRaisesRegex(ValueError,"unowned"): self.manifest([self.module(surfaces=("app/unknown.py",))]).validate_references({"item":self.item},self.ownership)

    def test_runtime_platform_contract_and_commands_fail_closed(self):
        contract=RuntimeContract.create(platforms=(TargetPlatform.KUBERNETES,TargetPlatform.LOCAL),execution_modes=(ExecutionMode.PRODUCTION,))
        self.assertEqual([v.value for v in contract.platforms],["kubernetes","local"])
        with self.assertRaises(ValueError): RuntimeContract.create(platforms=("shell",))
        value=contract.canonical_dict(); value["command"]="rm -rf /"
        with self.assertRaises(ValueError): RuntimeContract.from_dict(value)
        with self.assertRaises(ValueError): RuntimeContract.create(health_path="/../secret")

    def test_environment_metadata_has_no_secret_values(self):
        self.assertEqual(EnvironmentRequirement.from_dict({"name":"TOKEN","required":True,"category":"credential","secret":True}).category,EnvironmentCategory.CREDENTIAL)
        with self.assertRaises(ValueError): EnvironmentRequirement.from_dict({"name":"TOKEN","required":True,"category":"credential","secret":True,"value":"secret"})
        with self.assertRaises(ValueError): EnvironmentRequirement.from_dict({"name":"bad-name","required":True,"category":"string","secret":False})
        with self.assertRaises(ValueError): EnvironmentRequirement.from_dict({"name":"TOKEN","required":True,"category":"credential","secret":False})

    def test_round_trip_repeated_bytes_and_forgery_rejection(self):
        manifest=self.manifest(); path=save_application_manifest(self.root,".arcacore/application.json",manifest)
        first=path.read_bytes(); save_application_manifest(self.root,".arcacore/application.json",manifest)
        self.assertEqual(first,path.read_bytes()); self.assertEqual(load_application_manifest(path),manifest)
        value=json.loads(path.read_text()); value["project_name"]="Forged"; path.write_text(json.dumps(value))
        with self.assertRaises(ValueError): load_application_manifest(path)

    def test_duplicate_keys_malformed_noncanonical_and_oversized_rejected(self):
        path=self.root/"bad.json"; path.write_text('{"format_version":1,"format_version":1}')
        with self.assertRaisesRegex(ValueError,"duplicate key"): load_application_manifest(path)
        path.write_text("[]")
        with self.assertRaises(ValueError): load_application_manifest(path)
        path.write_bytes(b"x"*2_000_001)
        with self.assertRaisesRegex(ValueError,"safety limit"): load_application_manifest(path)
        path.write_text(json.dumps(self.manifest().canonical_dict(),indent=2))
        with self.assertRaisesRegex(ValueError,"not canonical"): load_application_manifest(path)

    def test_path_traversal_symlink_and_atomic_interruption_preserve_previous(self):
        manifest=self.manifest(); path=save_application_manifest(self.root,"manifest.json",manifest); previous=path.read_bytes()
        with self.assertRaises(ValueError): save_application_manifest(self.root,"../escape.json",manifest)
        original=Path.is_symlink
        with patch.object(Path,"is_symlink",lambda p: p.name=="link" or original(p)):
            with self.assertRaisesRegex(ValueError,"symbolic link"): save_application_manifest(self.root,"link/manifest.json",manifest)
        with patch("tools.application_manifest.write_text_atomic",side_effect=OSError("interrupted")):
            with self.assertRaises(OSError): save_application_manifest(self.root,"manifest.json",manifest)
        self.assertEqual(path.read_bytes(),previous)

    def test_windows_and_posix_aliases_and_executable_metadata_rejected(self):
        with self.assertRaises(ValueError): save_application_manifest(self.root,"dir\\manifest.json",self.manifest())
        with self.assertRaises(ValueError): save_application_manifest(self.root,"./manifest.json",self.manifest())
        value=self.manifest().canonical_dict(); value["exec"]="python payload.py"
        with self.assertRaises(ValueError): ApplicationManifest.from_dict(value)


if __name__ == "__main__": unittest.main()
