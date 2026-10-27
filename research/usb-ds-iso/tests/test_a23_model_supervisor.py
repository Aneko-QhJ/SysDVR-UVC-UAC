from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_model_supervisor as a
class SupervisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_SUPERVISOR_REVIEW'):cls.root=Path(os.environ['A23_SUPERVISOR_REVIEW'])
        else:cls.tmp=tempfile.TemporaryDirectory(prefix='a23-supervisor-tests-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';a.run(cls.root)
        a.w.card.seal_verify(cls.root);cls.audit=a.w.load(cls.root/'audit.json');cls.rows=cls.audit['matrix']
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def test_sources_preserved(self):self.assertEqual(len(a.b.sources()),378);self.assertEqual(self.audit['prior_sources_unchanged'],372)
    def test_only_normal_and_sanitized_environment_complete(self):self.assertEqual({n for n,r in self.rows.items() if r['supervision_complete']},{'normal','ambient-environment'})
    def test_actual_context_policy_never_grants_acquisition(self):
        for r in self.rows.values():self.assertIs(r['acquisition_permitted'],False);self.assertIs(r['parent_sandbox_evaluated'],False)
    def test_context_and_nonce_reject(self):
        for n in ('nonce','pid','ppid','uid','bool-pid','binary','path','environment'):self.assertFalse(self.rows[n]['hello_consistent'])
    def test_owner_parent_and_handoff_changes_latch(self):
        for n in ('owner-change','parent-change','handoff'):self.assertFalse(self.rows[n]['supervision_complete'])
    def test_timeout_retains_child_and_late_hello_stays_failed(self):
        for n in ('hold-before','hold-after'):self.assertTrue(self.rows[n]['timed_out']);self.assertFalse(self.rows[n]['supervision_complete']);self.assertTrue(self.audit['retained_unresolved'][n])
        self.assertFalse(self.rows['hold-before']['hello_consistent'])
    def test_bounded_raw_streams(self):
        for n in ('stdout-limit','stderr-limit'):self.assertTrue(self.rows[n]['truncated']);self.assertFalse(self.rows[n]['supervision_complete'])
        for n in self.rows:self.assertLessEqual(len(a.a.read(self.root/'models'/n/'stdout.bin')),4096);self.assertLessEqual(len(a.a.read(self.root/'models'/n/'stderr.bin')),256)
    def test_duplicate_trailing_partial_and_nonzero_reject(self):
        for n in ('duplicate','trailing','partial','exit3','no-hello'):self.assertFalse(self.rows[n]['supervision_complete'])
    def test_nine_bad_archives_reject(self):self.assertEqual(len(self.audit['negative_archives']),9)
    def test_rehashed_timeout_cannot_be_restored(self):self.assertEqual(self.audit['negative_archives']['deadline-restored'],'deadline verdict differs')
    def test_poll_has_bounded_wait(self):self.assertLess(self.audit['maximum_poll_seconds'],0.25)
    def test_prelaunch_changes_prevent_process(self):
        for n in ('handoff-before-launch','binary-before-launch'):self.assertFalse(self.audit['admission'][n]['process_created']);self.assertTrue(self.audit['admission'][n]['attempt_retained'])
    def test_spawn_failure_is_not_retryable(self):self.assertFalse(self.audit['admission']['spawn-error']['committed']);self.assertTrue(self.audit['admission']['spawn-error']['attempt_retained'])
    def test_unsupported_mode_and_bool_budget_make_no_output(self):
        for n in ('bad-mode','bool-budget'):self.assertFalse(self.audit['admission'][n]['output_created'])
    def test_no_hardware_or_formal_namespace(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations'):self.assertEqual(self.audit[k],0)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
if __name__=='__main__':unittest.main()
