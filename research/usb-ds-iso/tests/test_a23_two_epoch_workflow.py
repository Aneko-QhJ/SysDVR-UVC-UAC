from pathlib import Path
import copy,shutil,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_two_epoch_workflow as a
m=a.m
class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='a23-workflow32-',dir='/private/tmp');cls.out=Path(cls.tmp.name)/'review';a.run(cls.out);cls.audit=a.w.load(cls.out/'audit.json');cls.scope=a.w.load(cls.out/'preview.json')
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def new(self,name,history=None,material=None):
        return m.create(Path(self.tmp.name)/name,material or self.scope['model_materials'],history if history is not None else self.scope['baseline']['history'])
    def test_345_frozen_sources(self):self.assertEqual(len(a.baseline.sources()),351)
    def test_saved69_preview_is_readonly_and_blocked(self):
        self.assertEqual(self.scope['baseline']['raw_files'],69);self.assertEqual(self.scope['baseline']['preserved_old_files'],62)
        self.assertFalse(self.scope['record_written']);self.assertFalse(self.scope['sequence_reserved']);self.assertFalse(self.scope['formal_issuance_available'])
        self.assertEqual(self.audit['real_ledger_before'],self.audit['real_ledger_after']);self.assertEqual(self.audit['actual_history'],[[49,64],[65,80]])
    def test_five_complete_model_chains(self):self.assertEqual(self.audit['accepted'],['normal','race-consume','race-issue','race-process','race-selection'])
    def test_partial_files_keep_entire32(self):
        for name in ('partial-reservation','empty-reservation','issue-write-failed','consume-write-failed','context-write-failed','process-write-failed','selection-write-failed'):
            row=self.audit['models'][name];self.assertFalse(row['complete']);self.assertTrue(row['entire32_burn_kept'])
    def test_four_cross_process_races(self):
        for name in ('race-issue','race-consume','race-process','race-selection'):
            self.assertEqual(sum(r['won'] for r in self.audit['models'][name]['race']),1)
    def test_single_record_holds_all32(self):
        folder=self.out/'models/normal';r=m.load(folder/'reservation.json');self.assertEqual([r[k] for k in ('first','last','count')],[81,112,32])
        self.assertEqual(len(list(folder.glob('*reservation*'))),1)
    def test_model_clone_cannot_be_consumed(self):self.assertTrue(self.audit['cloned_writer_rejected'])
    def test_formal_destination_rejected(self):
        with self.assertRaises(ValueError):m.create(a.w.A/'must-not-create-sequence32-model',self.scope['model_materials'],[])
        self.assertFalse((a.w.A/'must-not-create-sequence32-model').exists())
    def test_historical_overlap_blocks_both_halves(self):
        for first in (81,97):
            h=copy.deepcopy(self.scope['baseline']['history']);h.append(dict(first=first,last=first+15,reservation_sha256='1'*64,record_sha256='2'*64));root=self.new('overlap-'+str(first),h)
            with self.assertRaises(ValueError):m.issue(root)
            self.assertFalse((root/'reservation.json').exists());self.assertEqual(len(m.preview(root)['historical_overlap']),16)
    def test_boolean_material_and_overlapping_history_rejected(self):
        v=copy.deepcopy(self.scope['model_materials']);v['first_sequence']=True
        with self.assertRaises(ValueError):self.new('bad-bool',material=v)
        h=copy.deepcopy(self.scope['baseline']['history']);h.append(copy.deepcopy(h[0]))
        with self.assertRaises(ValueError):self.new('bad-history',h)
    def test_failed_process_attempt_cannot_be_retried(self):
        root=self.new('bad-process-retry');m.issue(root);m.consume(root);c=a.context(self.scope);c['sandbox_query_result']=1
        with self.assertRaises(ValueError):m.process_claim(root,c)
        before=a.digest_tree(root)
        with self.assertRaises(FileExistsError):m.process_claim(root,a.context(self.scope))
        self.assertEqual(a.digest_tree(root),before)
    def test_phase_order_and_successful_replay(self):
        root=self.new('phase-order')
        with self.assertRaises((ValueError,FileNotFoundError)):m.consume(root)
        m.issue(root);m.consume(root);c=a.context(self.scope);m.process_claim(root,c);m.selection_claim(root,a.identity(),c)
        before=a.digest_tree(root)
        for op in (m.issue,m.consume,lambda r:m.process_claim(r,c),lambda r:m.selection_claim(r,a.identity(),c)):
            with self.assertRaises((ValueError,OSError)):op(root)
        self.assertEqual(a.digest_tree(root),before)
    def test_saved69_semantic_rejections(self):
        original={n:a.w.plain(self.out/'saved69'/n) for n in a.w.card.seal_verify(a.baseline.ANCHOR)}
        for name in ('mode','eject','uuid','writable','flag','count','claim'):
            files=dict(original);meta=m.parse(files['snapshot.json']);eject=m.parse(files['eject.json'])
            if name=='mode':meta['simulation']=True
            elif name=='eject':eject['ejected']=False
            elif name=='uuid':meta['identity']['VolumeUUID']='wrong'
            elif name=='writable':meta['identity']['WritableVolume']=True
            elif name=='flag':
                flag=next(n for n in files if n.endswith('/flags/boot2.flag'));files[flag]=b'x';meta['raw_files']=a.baseline.inventory(files)
            elif name=='count':
                key=next(n for n in files if n.startswith('card/ep0-'));del files[key];meta['raw_files']=a.baseline.inventory(files)
            elif name=='claim':meta['physical_run_authenticated']=True
            files['snapshot.json']=m.encode(meta);files['eject.json']=m.encode(eject)
            with self.assertRaises(ValueError,msg=name):a.baseline.validate_saved69(files)
    def test_symlink_refused_without_following_target(self):
        root=self.new('symlink');target=Path(self.tmp.name)/'do-not-touch';target.write_bytes(b'unchanged');(root/'context.json').symlink_to(target)
        with self.assertRaises(ValueError):m.issue(root)
        self.assertEqual(target.read_bytes(),b'unchanged');self.assertFalse((root/'reservation.json').exists())
    def test_negative_archives_have_real_reasons(self):
        self.assertEqual(len(self.audit['negative_archives']),15)
        expected={'split16':'reservation binding/overlap differs','bool-count':'reservation binding/overlap differs','old-baseline':'model scope differs','source-scope':'model scope differs','history-scope':'model scope differs','remaining':'consumption binding differs','wrong-pid':'selection claim differs','wrong-identity':'invalid selected HS identity','context-digest':'process claim differs','hardware-claim':'model authority differs','duplicate-json':'duplicate JSON key','wrong-lock':'lock content differs'}
        for name,reason in expected.items():self.assertEqual(self.audit['negative_archives'][name]['reason'],reason,name)
    def test_cli_cannot_issue_or_acquire(self):
        r=subprocess.run([sys.executable,'-B',str(ROOT/'tools/prepare_a23_two_epoch.py'),'--issue'],capture_output=True);self.assertEqual(r.returncode,2)
    def test_no_hardware_or_formal_authority(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations','remaining'):self.assertEqual(self.audit[k],0)
        self.assertFalse(self.audit['receiver_launched']);self.assertFalse(self.audit['production_permit_implemented'])
if __name__=='__main__':unittest.main()
