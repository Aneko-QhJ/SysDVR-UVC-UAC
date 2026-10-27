import json,shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import lifecycle_card_companion_deploy as v
import lifecycle_card_workflow as w
from test_lifecycle_card_workflow import model_card


class CompanionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-companion-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.card=model_card(self.root/'card');self.snap=self.root/'snapshot';self.out=self.root/'deployment'
        w.snapshot(self.card,self.snap);self.before=w.selected(self.card.root)
        self.template=w.read_file(v.EVIDENCE/'observed-card'/v.TEMPLATE_NAME,4096)
    def run_deploy(self,kind='valid',rename_companion=False):
        original=v.b.old.durable_write;replace=v.os.replace;created=[]
        def create(path,data):
            result=original(path,data)
            if self.card.root in path.parents and path.name.startswith('.a23-lifecycle-'):
                companion=self.card.root/v.companion_name(path.relative_to(self.card.root).as_posix());created.append(companion)
                if kind!='none':original(companion,self.template if kind!='invalid' else b'wrong metadata')
                if kind=='unrelated':original(self.card.root/'ep0-unrelated.bin',b'unexpected')
                if kind=='modified-original':(self.card.root/'logfile.txt').write_bytes(b'changed')
            return result
        def publish(source,target):
            result=replace(source,target)
            if rename_companion:
                companion=created[0]
                if companion.exists():companion.unlink() # Injected OS rename behavior, never used by deploy code.
            return result
        with patch.object(v.b.old,'durable_write',side_effect=create),patch.object(v.os,'replace',side_effect=publish):
            return v.deploy(self.card,self.snap,self.out)
    def test_observed_sidecar_is_bound_to_actual_sealed_template(self):
        self.assertEqual(len(self.template),4096);self.assertEqual(w.b.sha(self.template),v.COMPANION_SHA256)
        self.assertEqual(v.check_companion({'owned':self.template},'owned'),self.template)
    def test_only_exact_owned_name_is_exempted(self):
        row=self.run_deploy();self.assertTrue(row['companion_observed']);self.assertEqual(len(row['allowed_added_metadata_files']),1)
        added=row['allowed_added_metadata_files'][0];after=w.selected(self.card.root)
        self.assertEqual({n:r for n,r in after.items() if n!=added},{**self.before,w.pkg.PATHS[0]:w.b.plain(w.once.PACKAGE/'exefs.nsp')})
        self.assertEqual((self.out/'temporary-companion.bin').read_bytes(),self.template)
    def test_no_companion_remains_compatible(self):
        row=self.run_deploy(kind='none');self.assertFalse(row['companion_observed']);self.assertEqual(row['allowed_added_metadata_files'],[])
    def test_companion_removed_during_modeled_rename_is_still_preserved(self):
        row=self.run_deploy(rename_companion=True);self.assertTrue(row['companion_observed']);self.assertEqual(row['allowed_added_metadata_files'],[])
        self.assertEqual((self.out/'temporary-companion.bin').read_bytes(),self.template)
    def test_unknown_companion_stops_before_replacement(self):
        with self.assertRaises(ValueError):self.run_deploy(kind='invalid')
        self.assertEqual((self.card.root/w.pkg.PATHS[0]).read_bytes(),self.before[w.pkg.PATHS[0]])
        self.assertFalse((self.out/'deployment.json').exists())
    def test_unrelated_new_file_is_not_ignored(self):
        with self.assertRaises(ValueError):self.run_deploy(kind='unrelated')
        self.assertFalse((self.out/'deployment.json').exists());self.assertTrue(self.card.attached)
    def test_modified_original_is_not_ignored(self):
        with self.assertRaises(ValueError):self.run_deploy(kind='modified-original')
        self.assertFalse((self.out/'deployment.json').exists())
    def test_preexisting_sidecars_are_preserved_as_originals(self):
        old_temporary=self.card.root/(w.pkg.CONTENT+'.a23-lifecycle-prior.tmp')
        old_temporary.write_bytes(b'preserved failed temporary')
        old_companion=self.card.root/v.companion_name(old_temporary.relative_to(self.card.root).as_posix())
        old_companion.write_bytes(self.template)
        fresh=self.root/'fresh';w.snapshot(self.card,fresh);self.snap=fresh;self.before=w.selected(self.card.root)
        row=self.run_deploy();self.assertEqual(old_companion.read_bytes(),self.template)
        self.assertEqual(old_temporary.read_bytes(),b'preserved failed temporary')
        self.assertEqual(len(row['allowed_added_metadata_files']),1)
    def test_modeled_success_cannot_issue_real_record(self):
        self.run_deploy();scope=w.once.materials()[1]
        with self.assertRaises(ValueError):w.once.gate.verify_deployment(self.out,scope)
    def test_outputs_and_failed_deployment_never_reused(self):
        with self.assertRaises(ValueError):self.run_deploy(kind='invalid')
        with self.assertRaises(ValueError):v.deploy(self.card,self.snap,self.out)
    def test_same_header_but_different_payload_is_rejected(self):
        raw=bytearray(self.template);raw[-1]^=1
        with self.assertRaises(ValueError):v.check_companion({'owned':bytes(raw)},'owned')
    def test_existing_reports_and_old_deployment_metadata_not_relaxed(self):
        self.assertEqual(v.companion_name('some/path/.a23-lifecycle-x.tmp'),'some/path/._.a23-lifecycle-x.tmp')
        row=self.run_deploy();self.assertEqual((self.card.root/'atmosphere/crash_reports/original.log').read_bytes(),b'report\x00\xff')
        self.assertEqual(row['changed_files'],[w.pkg.PATHS[0]]);self.assertFalse(row['attempt_issued'])

if __name__=='__main__':unittest.main()
