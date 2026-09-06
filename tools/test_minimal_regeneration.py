import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.minimal_regeneration import (GenerationManifest, MinimalRegenerator,
    OwnershipClass, RegenerationAction, RegenerationPlan)


D1 = "1" * 64; D2 = "2" * 64


class MinimalRegenerationTest(unittest.TestCase):
    def setUp(self): self.temp = TemporaryDirectory(); self.root = Path(self.temp.name); self.regen = MinimalRegenerator(self.root)
    def tearDown(self): self.temp.cleanup()
    def seed(self, values=None):
        values = values or {"app/a.py": "a1\n", "app/b.py": "b1\n"}
        for path, content in values.items(): target=self.root/path; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(content.encode("utf-8"))
        return self.regen.bootstrap(values, generator="module", input_digest=D1)

    def test_noop_is_deterministic_and_byte_identical(self):
        manifest=self.seed(); plan=self.regen.plan({"app/a.py":"a1\n","app/b.py":"b1\n"},generator="module",input_digest=D1)
        self.assertTrue(all(v.action==RegenerationAction.UNCHANGED for v in plan.operations))
        self.assertEqual(plan.canonical_json(), self.regen.plan({"app/b.py":"b1\n","app/a.py":"a1\n"},generator="module",input_digest=D1).canonical_json())
        self.assertEqual(self.regen.apply(plan,{"app/a.py":"a1\n","app/b.py":"b1\n"},generator="module").canonical_json(),manifest.canonical_json())

    def test_one_module_change_replaces_only_expected_file(self):
        self.seed(); plan=self.regen.plan({"app/a.py":"a2\n","app/b.py":"b1\n"},generator="module",input_digest=D2)
        self.assertEqual([(v.path,v.action.value) for v in plan.operations],[('app/a.py','replace'),('app/b.py','unchanged')])
        self.regen.apply(plan,{"app/a.py":"a2\n","app/b.py":"b1\n"},generator="module"); self.assertEqual((self.root/'app/b.py').read_text(),'b1\n')

    def test_new_file_creation(self):
        self.seed({"app/a.py":"a\n"}); proposed={"app/a.py":"a\n","app/new.py":"n\n"}; plan=self.regen.plan(proposed,generator="module",input_digest=D2)
        self.regen.apply(plan,proposed,generator="module"); self.assertEqual((self.root/'app/new.py').read_text(),'n\n')

    def test_user_owned_and_modified_generated_files_conflict(self):
        self.seed({"app/a.py":"a\n"}); user=self.root/'app/user.py'; user.write_text('mine\n')
        plan=self.regen.plan({"app/a.py":"a\n","app/user.py":"generated\n"},generator="module",input_digest=D2,user_owned=("app/user.py",))
        with self.assertRaisesRegex(ValueError,"conflict"): self.regen.apply(plan,{"app/a.py":"a\n","app/user.py":"generated\n"},generator="module")
        self.assertEqual(user.read_text(),'mine\n')
        (self.root/'app/a.py').write_text('manual\n'); plan=self.regen.plan({"app/a.py":"new\n"},generator="module",input_digest=D2)
        self.assertEqual(plan.operations[0].ownership,OwnershipClass.CONFLICTED)

    def test_stale_safe_removal_and_modified_stale_refusal(self):
        self.seed(); plan=self.regen.plan({"app/a.py":"a1\n"},generator="module",input_digest=D2); self.regen.apply(plan,{"app/a.py":"a1\n"},generator="module")
        self.assertFalse((self.root/'app/b.py').exists())
        # Re-seed another root state and modify the stale file before planning.
        self.temp.cleanup(); self.temp=TemporaryDirectory(); self.root=Path(self.temp.name); self.regen=MinimalRegenerator(self.root); self.seed(); (self.root/'app/b.py').write_text('manual\n')
        plan=self.regen.plan({"app/a.py":"a1\n"},generator="module",input_digest=D2)
        with self.assertRaisesRegex(ValueError,"conflict"): self.regen.apply(plan,{"app/a.py":"a1\n"},generator="module")

    def test_path_traversal_and_digest_mismatch_rejected(self):
        self.seed({"app/a.py":"a\n"})
        with self.assertRaises(ValueError): self.regen.plan({"../escape":"x"},generator="module",input_digest=D2)
        plan=self.regen.plan({"app/a.py":"b\n"},generator="module",input_digest=D2)
        with self.assertRaisesRegex(ValueError,"digest mismatch"): self.regen.apply(plan,{"app/a.py":"c\n"},generator="module")

    def test_forged_manifest_and_plan_rejected(self):
        manifest=self.seed({"app/a.py":"a\n"}); value=manifest.canonical_dict(); value['files'][0]['path']='../escape'
        with self.assertRaises(ValueError): GenerationManifest.from_dict(value)
        plan=self.regen.plan({"app/a.py":"b\n"},generator="module",input_digest=D2)
        forged=RegenerationPlan(plan.operations,plan.input_digest,'0'*64)
        with self.assertRaisesRegex(ValueError,"identity mismatch"): self.regen.apply(forged,{"app/a.py":"b\n"},generator="module")

    def test_interrupted_multi_file_apply_recovers(self):
        self.seed(); proposed={"app/a.py":"a2\n","app/b.py":"b2\n"}; plan=self.regen.plan(proposed,generator="module",input_digest=D2)
        with self.assertRaises(InterruptedError): self.regen.apply(plan,proposed,generator="module",interrupt_after=1)
        self.assertEqual(self.regen.status(),'RECOVERY_REQUIRED'); self.assertEqual(self.regen.recover(),'RESTORED')
        self.assertEqual((self.root/'app/a.py').read_text(),'a1\n'); self.assertEqual((self.root/'app/b.py').read_text(),'b1\n')

    def test_write_failure_rolls_back_every_file_and_manifest(self):
        old=self.seed().canonical_json(); proposed={"app/a.py":"a2\n","app/b.py":"b2\n"}; plan=self.regen.plan(proposed,generator="module",input_digest=D2)
        import tools.minimal_regeneration as target; real=target.write_bytes_atomic; calls=[]
        def fail(path,content):
            calls.append(path)
            if len(calls)==2: raise OSError('disk full')
            return real(path,content)
        with patch.object(target,'write_bytes_atomic',side_effect=fail):
            with self.assertRaises(OSError): self.regen.apply(plan,proposed,generator="module")
        self.assertEqual(self.regen.load_manifest().canonical_json(),old); self.assertEqual((self.root/'app/a.py').read_text(),'a1\n')

    def test_manifest_has_no_absolute_paths_and_uses_schema_input_digest(self):
        manifest=self.seed({"app/a.py":"a\n"}); self.assertNotIn(str(self.root),manifest.canonical_json()); self.assertEqual(manifest.files[0].input_digest,D1)

    def test_forged_recovery_journal_rejected(self):
        self.seed(); proposed={"app/a.py":"a2\n","app/b.py":"b2\n"}; plan=self.regen.plan(proposed,generator="module",input_digest=D2)
        with self.assertRaises(InterruptedError): self.regen.apply(plan,proposed,generator="module",interrupt_after=1)
        value=json.loads(self.regen.journal_path.read_text()); value['backups'][0]['path']='../escape'; self.regen.journal_path.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.regen.recover()

    def test_change_after_plan_is_never_overwritten(self):
        self.seed({"app/a.py":"a\n"}); plan=self.regen.plan({"app/a.py":"new\n"},generator="module",input_digest=D2)
        (self.root/'app/a.py').write_text('user edit\n')
        with self.assertRaisesRegex(ValueError,"changed after planning"):
            self.regen.apply(plan,{"app/a.py":"new\n"},generator="module")
        self.assertEqual((self.root/'app/a.py').read_text(),'user edit\n')

    def test_recovery_refuses_to_overwrite_post_interruption_edit(self):
        self.seed(); proposed={"app/a.py":"a2\n","app/b.py":"b2\n"}; plan=self.regen.plan(proposed,generator="module",input_digest=D2)
        with self.assertRaises(InterruptedError): self.regen.apply(plan,proposed,generator="module",interrupt_after=1)
        (self.root/'app/a.py').write_text('new user work\n')
        with self.assertRaisesRegex(ValueError,"recovery conflict"): self.regen.recover()
        self.assertEqual((self.root/'app/a.py').read_text(),'new user work\n')

    def test_symlink_components_are_rejected_before_deletion(self):
        self.seed({"app/a.py":"a\n"})
        original = Path.is_symlink
        with patch.object(Path, "is_symlink", lambda path: path.name == "a.py" or original(path)):
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                self.regen.plan({}, generator="module", input_digest=D2)

    def test_noncanonical_alias_paths_are_rejected(self):
        self.seed({"app/a.py":"a\n"})
        with self.assertRaisesRegex(ValueError, "canonical"):
            self.regen.plan({"app//a.py":"a\n"}, generator="module", input_digest=D2)


if __name__=='__main__': unittest.main()
