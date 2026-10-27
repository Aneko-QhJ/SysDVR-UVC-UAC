from pathlib import Path
import copy,os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_versioned_clock_candidate as audit


class VersionedClockCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_VERSIONED_CLOCK_REVIEW'):cls.root=Path(os.environ['A23_VERSIONED_CLOCK_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-versioned-clock-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.report['fixture']['cases'][name]
    def test_stable_snapshots_keep_exact_fractional_minimum(self):
        self.assertTrue(self.row('normal')['minimum_met']);self.assertFalse(self.row('fractional-short')['minimum_met']);self.assertEqual(self.row('fractional-short')['rounded_ns'],250000000);self.assertTrue(self.row('fractional-equal')['minimum_met'])
    def test_during_start_and_end_aba_is_rejected(self):
        self.assertEqual(self.row('start-aba')['begin'],4);self.assertEqual(self.row('end-aba')['end'],4)
        for name in ('start-aba','end-aba'):self.assertEqual(self.row(name)['mutations'],2);self.assertEqual(self.row(name)['generation'],6)
    def test_between_capture_aba_is_rejected_despite_restored_profile(self):
        row=self.row('between-aba');self.assertEqual(row['begin'],0);self.assertEqual(row['end'],0);self.assertEqual(row['evaluate'],4);self.assertNotEqual(row['begin_generation'],row['end_generation'])
    def test_noop_and_aborted_writes_advance_version(self):
        for name in ('between-noop','between-abort'):self.assertEqual(self.row(name)['generation'],4);self.assertEqual(self.row(name)['evaluate'],4)
    def test_single_writer_busy_returns_without_spinning_or_reading_ticks(self):
        self.assertEqual(self.row('busy-before')['begin'],3);self.assertEqual(self.row('busy-before')['reads'],1);self.assertEqual(self.row('nested-writer')['writer_status'],3)
    def test_busy_during_capture_invalidates_output_without_retry(self):
        row=self.row('busy-during');self.assertEqual(row['end'],4);self.assertTrue(row['end_zeroed']);self.assertEqual(row['reads'],2)
    def test_threaded_aba_and_contender_use_same_contract(self):
        self.assertEqual(self.report['fixture']['threads_created'],3)
        for name in ('thread-start-aba','thread-end-aba','thread-contender'):self.assertEqual(self.row(name)['threads'],1);self.assertFalse(self.row(name)['minimum_met'])
    def test_all_visible_cooperative_profile_changes_are_rejected(self):
        for name in ('during-numerator','during-denominator','during-domain','during-instance'):self.assertNotEqual(self.row(name)['end'],0);self.assertFalse(self.row(name)['minimum_met'])
    def test_invalid_profiles_are_poisoned_before_tick_reader(self):
        for name in ('invalid-domain','invalid-instance','invalid-numerator','invalid-denominator','invalid-incarnation'):self.assertEqual(self.row(name)['init'],2);self.assertEqual(self.row(name)['reads'],0);self.assertTrue(self.row(name)['poisoned'])
    def test_invalid_finish_poison_is_sticky(self):
        row=self.row('invalid-finish');self.assertEqual(row['writer_status'],2);self.assertEqual(row['end'],5);self.assertTrue(row['poisoned'])
    def test_generation_exhaustion_fails_instead_of_wrapping(self):
        self.assertEqual(self.row('last-write')['generation'],audit.U64-1);row=self.row('exhaustion');self.assertEqual(row['writer_status'],6);self.assertTrue(row['poisoned']);self.assertEqual(row['generation'],audit.U64-1)
    def test_wrong_and_reused_writer_ticket_do_not_rewrite_generation(self):
        for name in ('wrong-ticket','stale-ticket'):self.assertEqual(self.row(name)['writer_status'],4);self.assertEqual(self.row(name)['generation'],4)
    def test_store_object_and_incarnation_bind_endpoints(self):
        self.assertEqual(self.row('other-store')['evaluate'],4);self.assertEqual(self.row('other-incarnation')['evaluate'],4)
    def test_unreported_bypass_aba_is_an_explicit_negative_control(self):
        for name in ('bypass-aba','bypass-between'):self.assertEqual(self.row(name)['mutations'],2);self.assertEqual(self.row(name)['generation'],2);self.assertTrue(self.row(name)['minimum_met'])
        self.assertFalse(self.report['writer_contract_enforced'])
    def test_samples_describe_past_interval_not_live_store_authorization(self):
        row=self.row('after-end-publish');self.assertEqual(row['generation'],4);self.assertEqual(row['end_generation'],2);self.assertTrue(row['minimum_met'])
    def test_reader_failure_null_and_zero_state_reset_output(self):
        for name in ('reader-failure','nil-reader','nil-store','poisoned','zero-generation'):self.assertNotEqual(self.row(name)['end'],0);self.assertTrue(self.row(name)['end_zeroed'])
        self.assertTrue(self.report['fixture']['pointer_checks_passed'])
    def test_reversal_overflow_and_zero_tick_keep_arithmetic_policy(self):
        self.assertEqual(self.row('backwards')['evaluate'],5);self.assertEqual(self.row('overflow')['evaluate'],6);self.assertTrue(self.row('zero-tick')['minimum_met'])
    def test_every_reference_case_and_strict_result_mutation_rejection(self):
        self.assertEqual(len(audit.NAMES),43)
        for name in audit.NAMES:self.assertEqual(self.row(name),audit.oracle(name))
        forged=copy.deepcopy(self.report['fixture']);forged['cases']['end-aba']['end']=0
        with self.assertRaisesRegex(ValueError,'versioned oracle'):audit.validate(forged)
    def test_standalone_build_does_not_compile_or_execute_driver(self):
        for mode,row in self.report['builds'].items():
            self.assertFalse(any(arg.endswith('.m') or arg=='-framework' for arg in row['command']))
            for label in row['link_scope']:
                raw=audit.a.read(self.root/'work'/('scope-'+mode)/(label+'.txt'));self.assertFalse(any(token in raw for token in audit.previous.DENY))
        self.assertEqual(self.report['full_sdk_model_executions'],0);self.assertFalse(self.report['versioned_driver_integrated'])
    def test_source467_and_external_pin_authority_limits(self):
        report=audit.f.load(self.root/'audit.json');self.assertEqual((report['source_count'],report['prior_sources_unchanged']),(467,462))
        for flag in audit.FALSE:self.assertIs(self.report[flag],False)
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.verify(self.root,'0'*64)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())


if __name__=='__main__':unittest.main()
