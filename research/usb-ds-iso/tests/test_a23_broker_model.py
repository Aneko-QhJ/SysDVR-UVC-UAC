from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_broker_model as a
class BrokerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_BROKER_REVIEW'):cls.root=Path(os.environ['A23_BROKER_REVIEW'])
        else:cls.tmp=tempfile.TemporaryDirectory(prefix='a23-broker-tests-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';a.run(cls.root)
        a.w.card.seal_verify(cls.root);cls.audit=a.w.load(cls.root/'audit.json');cls.matrix=cls.audit['matrix']
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def test_sources_frozen(self):self.assertEqual(len(a.b.sources()),385);self.assertEqual(self.audit['prior_sources_unchanged'],378)
    def test_two_explicit_injected_models_complete(self):self.assertEqual({n for n,r in self.matrix.items() if r['complete_injected_model_chain']},{'injected-normal','injected-queued-delay'})
    def test_actual_environment_blocks_before_model_issue(self):
        root=self.root/'models/actual-policy-denied';self.assertFalse((root/'final/inputs/namespace').exists());self.assertFalse(self.matrix['actual-policy-denied']['actual_environment_accepted'])
    def test_actual_context_reused_and_only_policy_fields_injected(self):
        r=self.matrix['injected-normal'];self.assertTrue(r['injected_policy_used']);self.assertFalse(r['actual_environment_accepted']);self.assertFalse(r['production_execution_authorized'])
    def test_context_substitution_breaks_join_but_not_inner_model(self):
        r=self.matrix['context-substitution'];self.assertTrue(r['collection']['analysis']['supplied_model_chain_complete']);self.assertIn('execution context substitution',r['errors']);self.assertFalse(r['complete_injected_model_chain'])
    def test_consumed_tamper_stays_spent(self):
        folder=next((self.root/'models/consumed-tamper/final/inputs/namespace/jobs').glob('*/consumed.json'));self.assertEqual(a.a.read(folder),b'{');self.assertFalse(self.matrix['consumed-tamper']['complete_injected_model_chain'])
    def test_scope_drift_never_burns(self):self.assertFalse((self.root/'models/scope-before-consume/final/inputs/namespace/block-00081.json').exists())
    def test_unresolved_producer_does_not_collect(self):
        for row in self.audit['pending_before_release'].values():self.assertTrue(row['handle_retained']);self.assertFalse(row['final_before_release'])
    def test_late_command_after_stop_cannot_open_sdk(self):
        r=a.f.parse(a.a.read(self.root/'models/timeout-after-command/final/report.json'));self.assertFalse(r['model_execute_admitted']);self.assertEqual(r['calls']['opens'],0)
    def test_partial_control_keeps_consumed_model(self):self.assertTrue((self.root/'models/partial-control/final/inputs/namespace/block-00081.json').exists());self.assertFalse(self.matrix['partial-control']['complete_injected_model_chain'])
    def test_spawn_failure_retains_uncommitted_ownership(self):self.assertTrue(self.audit['spawn_failure_retained']);self.assertFalse((self.root/'models/spawn-error-partial/supervision/COMMITTED').exists())
    def test_seven_bad_joined_archives(self):self.assertEqual(len(self.audit['negative_archives']),7)
    def test_rehashed_substitution_cannot_claim_success(self):self.assertEqual(self.audit['negative_archives']['forged-substitution-success'],'saved broker verdict differs')
    def test_context_and_execution_have_independent_fixed_bounds(self):
        h=a.f.parse(a.a.read(self.root/'models/injected-normal/supervision/handoff-original.json'));self.assertEqual(h['hello_budget_ns'],5000000000);self.assertEqual(h['execution_budget_ns'],30000000000)
    def test_late_hello_cannot_use_remaining_execution_budget(self):
        r=self.matrix['hello-timeout-before-hello']['supervision'];self.assertTrue(r['hello_timed_out']);self.assertFalse(r['timed_out']);self.assertFalse(r['hello_consistent'])
    def test_no_hardware_or_formal_namespace(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations'):self.assertEqual(self.audit[k],0)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
if __name__=='__main__':unittest.main()
