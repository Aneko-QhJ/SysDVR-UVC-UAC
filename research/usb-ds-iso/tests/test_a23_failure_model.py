from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_failure_model as a
class FailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_FAILURE_REVIEW'):cls.root=Path(os.environ['A23_FAILURE_REVIEW'])
        else:cls.tmp=tempfile.TemporaryDirectory(prefix='a23-failure-tests-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';a.run(cls.root)
        a.w.card.seal_verify(cls.root);cls.audit=a.w.load(cls.root/'audit.json');cls.matrix=cls.audit['matrix']
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def test_frozen_sources(self):self.assertEqual(len(a.b.sources()),392);self.assertEqual(self.audit['prior_sources_unchanged'],385)
    def test_single_explicit_model_complete(self):self.assertEqual({n for n,r in self.matrix.items() if r['complete_injected_model_chain']},{'injected-normal'})
    def test_actual_policy_still_refused(self):self.assertFalse(self.matrix['actual-policy-denied']['actual_environment_accepted']);self.assertFalse((self.root/'models/actual-policy-denied/final/inputs/namespace').exists())
    def test_missing_report_after_native_exit_collected(self):
        for case in ('exit-before-hello','partial-hello','exit-after-command'):self.assertEqual(self.matrix[case]['report_state'],'missing');self.assertFalse(self.matrix[case]['complete_injected_model_chain']);self.assertEqual(a.a.read(self.root/'models'/case/'final/report.json'),b'')
    def test_partial_report_preserved(self):self.assertEqual(a.a.read(self.root/'models/partial-report/final/report.json'),b'{"schema":');self.assertEqual(self.matrix['partial-report']['report_state'],'malformed')
    def test_non_object_and_empty_are_distinct(self):self.assertEqual(self.matrix['non-object-report']['report_state'],'non_object');self.assertEqual(self.matrix['empty-report']['report_state'],'empty')
    def test_partial_hello_preserved(self):self.assertEqual(a.a.read(self.root/'models/partial-hello/supervision/stdout.bin'),b'{"schema":')
    def test_abrupt_post_command_exit_retains_consumption(self):self.assertTrue((self.root/'models/exit-after-command/final/inputs/namespace/block-00081.json').exists())
    def test_prehello_exit_has_no_model_consumption(self):self.assertFalse((self.root/'models/exit-before-hello/final/inputs/namespace').exists())
    def test_native_nonzero_exit_preserved(self):
        for case,code in (('exit-before-hello',71),('exit-after-command',72),('partial-report',72)):self.assertEqual(a.f.load(self.root/'models'/case/'supervision/result.json')['returncode'],code)
    def test_pid_substitution_still_rejected(self):self.assertIn('execution context substitution',self.matrix['context-substitution']['errors']);self.assertTrue(self.matrix['context-substitution']['collection']['analysis']['supplied_model_chain_complete'])
    def test_running_producer_retained(self):self.assertTrue(self.audit['pending_before_release']['handle_retained']);self.assertFalse(self.audit['pending_before_release']['final_before_release']);self.assertFalse(self.audit['pending_before_release']['attempt_marker_before_release'])
    def test_source_and_build_drift_refused_before_spawn(self):self.assertEqual(set(self.audit['prelaunch_rejected']),{'source-drift','build-drift'})
    def test_spawn_failure_remains_uncommitted(self):self.assertTrue(self.audit['spawn_failure_retained']);self.assertFalse((self.root/'models/spawn-error-partial/supervision/COMMITTED').exists())
    def test_forged_incomplete_success_rejected(self):self.assertEqual(self.audit['negative_archives']['forged-missing-success'],'saved failure verdict differs');self.assertEqual(len(self.audit['negative_archives']),7)
    def test_collector_api_has_no_process_or_issuer(self):self.assertEqual(set(a.collector.ExitedModelFiles.__dataclass_fields__),{'root','receiver','supervisor','child_pid','control_delivery'})
    def test_no_hardware_or_formal_namespace(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations'):self.assertEqual(self.audit[k],0)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
if __name__=='__main__':unittest.main()
