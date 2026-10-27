from pathlib import Path
import copy,os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_isolated_driver_model as audit


class IsolatedDriverModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_ISOLATED_DRIVER_REVIEW'):cls.root=Path(os.environ['A23_ISOLATED_DRIVER_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-isolated-driver-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.report['semantic'][name]
    def test_complete_driver_reaches_settlement_and_receipt(self):
        row=self.row('normal');self.assertTrue(row['complete']);self.assertTrue(row['receipt']['saved']);self.assertEqual(row['events'][-1],'observation_complete')
    def test_fractional_shortfall_does_not_settle_or_attempt_receipt(self):
        row=self.row('fractional-short');self.assertFalse(row['complete']);self.assertFalse(row['stopped']);self.assertFalse(row['receipt']['attempted']);self.assertEqual(row['exact_duration'],[749999998,3])
    def test_same_driver_can_poll_again_at_exact_fractional_minimum(self):
        row=self.row('fractional-short-equal');self.assertTrue(row['complete']);self.assertEqual(row['exact_duration'],[250000000,1]);self.assertEqual(row['events'].count('observation_complete'),1)
    def test_after_fractional_minimum_settles(self):
        self.assertTrue(self.row('fractional-after')['complete']);self.assertEqual(self.row('fractional-after')['exact_duration'],[750000002,3])
    def test_unlabeled_owner_and_zero_instance_fail_before_clock_or_submission(self):
        for name in ('unlabeled','owner-role','zero-instance'):self.assertEqual(self.row(name),dict(init_rejected=True,clock_reads=0,events=[]))
    def test_tick_zero_start_is_rejected_after_saved_epochs(self):
        row=self.row('zero-start');self.assertEqual(row['quiet_start_ticks'],0);self.assertIn('observation_clock',row['failure_reasons'])
    def test_profile_changes_fail_without_completion_event(self):
        for name in ('ratio-change','instance-change','domain-change'):
            row=self.row(name);self.assertTrue(row['stopped']);self.assertNotIn('observation_complete',row['events'])
    def test_reverse_and_overflow_intervals_fail(self):
        for name in ('backwards','overflow'):self.assertIn('observation_clock',self.row(name)['failure_reasons'])
    def test_replacement_with_identical_logical_labels_is_rejected(self):
        row=self.row('object-replaced');self.assertTrue(row['profile']['object_replaced']);self.assertIn('observation_clock',row['failure_reasons'])
    def test_append_failure_is_terminal(self):
        row=self.row('quiet-journal-failure');self.assertIn('journal_failed',row['failure_reasons']);self.assertFalse(row['observation_complete'])
    def test_post_append_guard_must_pass_before_settlement(self):
        row=self.row('postguard-failure');self.assertIn('observation_complete',row['events']);self.assertFalse(row['observation_complete']);self.assertEqual(row['quiet_end_ticks'],0)
    def test_late_callback_revokes_settlement_and_preserves_diagnostic_end(self):
        row=self.row('late-after-settled');self.assertTrue(row['stopped']);self.assertFalse(row['complete']);self.assertGreater(row['quiet_end_ticks'],0)
    def test_late_callback_revokes_saved_receipt(self):
        row=self.row('late-after-receipt');self.assertTrue(row['receipt']['stale']);self.assertFalse(row['receipt']['saved'])
    def test_incomplete_wait_leaves_receipt_unattempted(self):
        row=self.row('incomplete');self.assertFalse(row['stopped']);self.assertFalse(row['receipt']['attempted'])
    def test_full_candidate_is_same_patch_and_protected_methods(self):
        source=self.root/'source';raw=audit.a.read(source/audit.previous.DRIVER);candidate=audit.a.read(self.root/'work/generated'/audit.previous.DRIVER)
        self.assertEqual(candidate,audit.previous.patch.render(raw));self.assertEqual(audit.previous.patch.protected_slices(raw),audit.previous.patch.protected_slices(candidate))
    def test_binary_scope_is_checked_before_execution(self):
        for mode,row in self.report['builds'].items():
            self.assertEqual(row['command'].count('-framework'),1);self.assertEqual(row['command'][-4],'-framework');self.assertIn('Foundation',row['command'])
            for label in row['link_scope']:
                raw=audit.a.read(self.root/'work'/('scope-'+mode)/(label+'.txt'));self.assertFalse(any(token in raw for token in audit.DENY))
    def test_every_implementation_has_no_actual_factory_or_clock(self):
        for name,raw in audit.model.render(self.root/'source').items():
            if name.endswith(('.m','.c')):
                for token in (b'mach_absolute_time',b'mach_timebase_info',b'initWithIOService:',b'A23ReadExecutionContext'):self.assertNotIn(token,raw)
    def test_saved_model_mutations_are_rejected(self):
        original=audit.f.load(self.root/'work/stdout-optimized.json')
        for name in ('normal','fractional-short','postguard-failure','late-after-receipt'):
            mutated=copy.deepcopy(original);mutated['cases'][name]['result']['complete']=not mutated['cases'][name]['result']['complete']
            with self.assertRaises(ValueError):audit.analyze(self.root/'work/models-optimized',mutated)
    def test_readonly_external_pin_and_all_authority_limits(self):
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.verify(self.root,'0'*64)
        for flag in audit.FALSE:self.assertIs(self.report[flag],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists());self.assertEqual(self.report['model_cases'],19)
    def test_source457_preserves_old452(self):
        report=audit.f.load(self.root/'audit.json');self.assertEqual((report['source_count'],report['prior_sources_unchanged']),(457,452))


if __name__=='__main__':unittest.main()
