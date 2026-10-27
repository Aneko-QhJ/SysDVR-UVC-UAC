from pathlib import Path
import copy,shutil,sys,tempfile,unittest,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_shared_sequence32 as a
s=a.s;f=a.f
class SharedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='a23-shared-tests-',dir='/private/tmp');cls.out=Path(cls.tmp.name)/'review';a.run(cls.out);cls.audit=a.w.load(cls.out/'audit.json');cls.inputs=a.w.load(cls.out/'materials.json');cls.scope=cls.inputs['scope']
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_351_frozen_sources(self):self.assertEqual(len(a.material.sources()),359)
    def test_distinct_jobs_compete_in_one_namespace(self):
        r=self.audit['shared_cases']['cross-job-and-native-race'];self.assertNotEqual(r['winner'],r['loser']);self.assertEqual(sum(v['won'] for v in r['job_results']),1);self.assertEqual(r['shared_burn_files'],1)
    def test_native_instances_compete_durably(self):
        r=self.audit['shared_cases']['cross-job-and-native-race'];self.assertEqual(sum(v['process_returned'] for v in r['native_results']),1);self.assertEqual(sum(v['selection_returned'] for v in r['native_results']),1)
    def test_empty_and_failed_issue_keep_entire_range(self):
        for name in ('empty-burn','issue-failure','scope-after-burn'):self.assertTrue(self.audit['shared_cases'][name]['burn_retained'])
    def test_scope_history_overlap_and_clone_reject(self):
        for name in ('scope-before-issue','history-drift','overlap','stolen-owner','clone'):self.assertTrue(self.audit['shared_cases'][name]['rejected'])
    def test_uncommitted_files_never_resume(self):
        for name in ('issue-not-committed','consume-not-committed'):self.assertTrue(self.audit['shared_cases'][name]['burn_retained'])
        for name in ('missing-issue-commit','missing-consume-commit'):self.assertFalse(self.audit['matrix'][name]['native']['init_accepted'])
    def test_two_complete_native_chains(self):self.assertEqual(set(self.audit['accepted']),{'normal','cross-instance-replay'});self.assertEqual(len(self.audit['rejected']),21)
    def test_model_cannot_enter_production_permit(self):self.assertFalse(self.audit['matrix']['production-rejects-model']['native']['init_accepted'])
    def test_context_and_binding_reject(self):
        for name in ('bad-binding','sandbox-context','bool-pid'):self.assertFalse(self.audit['matrix'][name]['native']['process_returned'])
        for name in ('changed-context','bad-identity'):self.assertFalse(self.audit['matrix'][name]['native']['selection_returned'])
    def test_post_claim_changes_invalidate_result(self):
        for name in ('scope-after-selection','scope-restored-after-read','selection-file-tamper','core-after-selection','process-file-tamper','context-file-tamper'):
            r=self.audit['matrix'][name]['native']['permit'];self.assertTrue(r['stale']);self.assertFalse(r['selection_claimed'])
    def test_native_save_then_verifier_failure_never_claims_success(self):
        r=self.audit['matrix']['fail-after-process-save'];folder=self.out/'native/fail-after-process-save/jobs'/r['job_id'];self.assertTrue((folder/'native-process-claim.json').exists());self.assertFalse(r['native']['process_returned'])
        r=self.audit['matrix']['fail-after-selection-save'];folder=self.out/'native/fail-after-selection-save/jobs'/r['job_id'];self.assertTrue((folder/'native-sdk-claim.json').exists());self.assertFalse(r['native']['selection_returned'])
    def test_native_attempt_collisions(self):
        self.assertFalse(self.audit['matrix']['process-collision']['native']['process_returned']);self.assertFalse(self.audit['matrix']['selection-collision']['native']['selection_returned'])
    def test_real_namespace_not_created(self):
        existed=s.FORMAL_ROOT.exists();store=s.SharedSequence32(s.FORMAL_ROOT,simulation=False,fresh_scope=lambda:self.scope)
        with self.assertRaisesRegex(ValueError,'not ready'):store.initialize(self.inputs['history'])
        self.assertEqual(s.FORMAL_ROOT.exists(),existed)
    def test_authorization_must_match_mode_and_scope(self):
        st=a.namespace(Path(self.tmp.name)/'bad-authorization',self.scope,self.inputs['history']);ident=str(uuid.uuid4());ns=f.load(st.root/'namespace.json')
        receipt=dict(schema='A23-shared32-authorization-1',job_id=ident,scope_sha256=ns['scope_sha256'],maximum_invocations=1,simulation=True,hardware_test_authorized=True)
        with self.assertRaises(ValueError):st.prepare(ident,receipt)
        self.assertFalse((st.root/'jobs'/ident).exists())
    def test_cross_mode_constructor_rejected(self):
        with self.assertRaises(ValueError):s.SharedSequence32(Path(self.tmp.name)/'fake-formal',simulation=False,fresh_scope=lambda:self.scope)
    def test_consume_does_not_launch_or_refill(self):
        st=a.namespace(Path(self.tmp.name)/'consume-once',self.scope,self.inputs['history']);job=a.job(st);st.issue(job);v=st.consume(job);before=a.tree(st.root)
        with self.assertRaises(OSError):st.consume(job)
        self.assertEqual(a.tree(st.root),before);self.assertEqual(v['remaining'],0);self.assertFalse(v['receiver_launched'])
    def test_twelve_negative_archives(self):
        self.assertEqual(len(self.audit['negative_archives']),12);self.assertTrue(all(r['rejected'] for r in self.audit['negative_archives'].values()))
        for name in ('bool-count','split16','owner-job'):self.assertEqual(self.audit['negative_archives'][name]['reason'],'shared reservation owner/range differs')
        self.assertEqual(self.audit['negative_archives']['selection-pid']['reason'],'native selection snapshot differs')
        self.assertEqual(self.audit['negative_archives']['baseline-scope']['reason'],'supplied shared scope differs')
    def test_no_live_authority(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations','remaining'):self.assertEqual(self.audit[k],0)
        self.assertFalse(self.audit['production_fresh_scope_binding_wired']);self.assertFalse(self.audit['acquisition_mode_implemented'])
if __name__=='__main__':unittest.main()
