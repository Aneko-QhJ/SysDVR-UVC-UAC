from pathlib import Path
import sys,tempfile,unittest,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_two_epoch_entry as a
class EntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='a23-entry-',dir='/private/tmp');cls.out=Path(cls.tmp.name)/'review';a.run(cls.out);cls.audit=a.w.load(cls.out/'audit.json');cls.cases=cls.audit['matrix']['cases']
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_source_and_build(self):self.assertEqual(len(a.b.sources()),345);self.assertEqual(a.b.verify_build(self.out/'build'),self.audit['build'])
    def test_context_precedes_wait(self):
        for n in ('context-sandbox','context-framework','context-bool','context-future','context-digest','process-reject','process-collision','exit-before-begin','exit-in-process-permit'):
            self.assertEqual(self.cases[n]['calls']['wait_creates'],0);self.assertEqual(self.cases[n]['calls']['opens'],0)
    def test_claim_collisions_preserve_original(self):
        for name,file in (('process-collision','process-claim.json'),('sdk-claim-collision','sdk-claim.json')):
            self.assertEqual((self.out/'models'/name/file).read_text(),'preserved')
            self.assertEqual(self.cases[name]['calls']['opens'],0)
    def test_wait_rejections_precede_sdk(self):
        for n in ('selection-reject','sdk-claim-collision','existing','ambiguous','wait-timeout','exit-waiting','exit-in-selection-permit'):
            self.assertEqual(self.cases[n]['calls']['opens'],0);self.assertEqual(self.cases[n]['calls']['iso_submissions'],0)
    def test_preparation_separate_from_start(self):
        for n in ('exit-prepared','detach-prepared','wait-release-error'):
            self.assertEqual(self.cases[n]['calls']['opens'],1);self.assertEqual(self.cases[n]['calls']['iso_submissions'],0)
    def test_normal_combined_chain(self):
        self.assertEqual(set(self.audit['accepted']),{'normal','queued-delay'})
        for r in self.audit['accepted'].values():self.assertEqual(r['sdk']['total_bytes'],6144);self.assertFalse(r['production_permit_authenticated'])
    def test_active_resources_not_released(self):
        for r in self.cases.values():
            self.assertLessEqual(r['calls']['iso_submissions'],2);self.assertLessEqual(r['calls']['burst_enqueues'],2);self.assertLessEqual(r['calls']['aborts'],1)
            if r['result']['started']:self.assertEqual(r['calls']['sdk_live_refs'],1);self.assertEqual(r['calls']['sdk_destroys'],0)
    def test_late_after_final_checkpoint(self):
        r=self.cases['old-after-final'];self.assertFalse(r['result']['complete']);self.assertTrue(r['final_status']['stale']);self.assertFalse(r['final_status']['saved'])
    def test_pending_observation_no_finalize(self):self.assertFalse(self.cases['quiet-incomplete']['final_status']['attempted'])
    def test_semantic_negatives(self):
        self.assertEqual(len(self.audit['negative_entries']),18);self.assertTrue(all(x['rejected'] for x in self.audit['negative_entries'].values()))
        for name,row in self.audit['negative_entries'].items():
            if name not in ('duplicate-json','missing-final'):self.assertNotIn('integrity differs',row['reason'],name)
        expected={'sandbox':'sandbox state unknown or active','context-bool':'invalid context number pid','context-digest':'entry context binding differs','process-binding':'entry claim differs','selection-pid':'entry claim differs','selection-id':'adapter selected identity differs','wait-order':'passive wait order differs','wait-existing':'device existed before WAITING','wait-release':'entry failed','start-order':'entry journal invalid','range':'entry range differs','final-stale':'entry final status differs','snapshot':'entry final checkpoint not current','hardware-claim':'entry uncertainty/claim: hardware_verified','released':'entry uncertainty/claim: active_resources_released','missing-final':'entry checkpoint inventory differs','duplicate-json':'duplicate JSON key','partial-journal':'entry partial journal'}
        self.assertEqual({name:row['reason'] for name,row in self.audit['negative_entries'].items()},expected)
    def test_file_only_modes(self):self.assertEqual(self.audit['file_modes'],dict(describe=0,build=0,context=0,acquire=2,empty=2))
    def test_native_build_tamper_rejected(self):
        for name in ('source','manifest','header','record'):
            folder=Path(self.tmp.name)/('tamper-'+name);shutil.copytree(self.out/'build',folder)
            if name=='source':p=folder/'source/research/usb-ds-iso/host/a23_two_epoch_entry.m';p.write_bytes(p.read_bytes()+b'\n')
            elif name=='manifest':p=folder/'manifest.json';p.write_bytes(p.read_bytes()+b'\n')
            elif name=='header':p=folder/'a23_two_epoch_entry_binding.h';p.write_bytes(p.read_bytes()+b'\n')
            else:p=folder/'binary.json';raw=p.read_text();p.write_text('{"schema":"A23-two-epoch-entry-binary-1",'+raw[1:])
            r=subprocess.run([str(folder/'entry-inspector'),'--check-build',str(folder)],capture_output=True)
            self.assertEqual(r.returncode,2,name)
    def test_no_authority(self):
        for n in ('usb_requests','sd_accesses','native_iokit_calls','real_sdk_objects','formal_records','formal_reservations','remaining'):self.assertEqual(self.audit[n],0)
        self.assertFalse(self.audit['acquisition_mode_implemented']);self.assertFalse(self.audit['actual_sdk_mapping_tested'])
if __name__=='__main__':unittest.main()
