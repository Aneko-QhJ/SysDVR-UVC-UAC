from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_quiet_driver_copy as audit


class QuietDriverCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_QUIET_DRIVER_COPY_REVIEW'):cls.root=Path(os.environ['A23_QUIET_DRIVER_COPY_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-quiet-driver-copy-tests-',dir='/private/tmp')
            cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
        cls.original=audit.a.read(cls.root/'source'/audit.DRIVER)
        cls.candidate=audit.a.read(cls.root/'work/candidate/source'/audit.DRIVER)
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.report['bridge']['cases'][name]
    def test_pinned_driver_derivation_and_reviewable_diff(self):
        self.assertEqual(audit.patch.render(self.original),self.candidate)
        self.assertNotEqual(self.original,self.candidate)
        diff=audit.a.read(self.root/'work/driver-copy.diff').decode()
        self.assertTrue(diff.startswith('--- frozen/host/a23_two_epoch_sdk_driver.m\n'))
        self.assertIn('+',diff);self.assertIn('duration.minimum_met',diff)
    def test_unrelated_driver_methods_are_byte_identical(self):
        self.assertEqual(audit.patch.protected_slices(self.original),audit.patch.protected_slices(self.candidate))
        self.assertEqual(set(self.report['protected_slice_sha256']),{'deadline','emit-stop-guard','receipt-and-result'})
    def test_constructor_preflights_labels_before_owner_creation(self):
        text=self.candidate.decode()
        self.assertLess(text.index('A23QuietDriverReadProfile(clock'),text.index('if((self=[super init]))'))
        self.assertEqual(self.row('normal')['preflight_tick_reads'],0)
    def test_start_snapshot_follows_saved_event_and_keeps_sentinel(self):
        text=self.candidate.decode();section=text[text.index('if(_epoch==2)'):text.index('// Do not arm here.')]
        self.assertLess(section.index('emit:@"epochs_saved"'),section.index('A23QuietDriverCapture(_clock,&start)'))
        self.assertIn('!start.stamp.ticks',section);self.assertIn('_quietClockStart=start;_quietSince=start.stamp.ticks;',section)
    def test_end_snapshot_preserves_append_then_guard_settlement(self):
        text=self.candidate.decode();section=text[text.index('if(_complete){'):text.index('if(!_pending){')]
        self.assertLess(section.index('A23QuietDriverCapture'),section.index('A23QuietDriverEvaluate'))
        self.assertIn('duration.minimum_met && [self emit:@"observation_complete"',section)
        self.assertIn('&& [self guard]){_settled=YES;',section)
        self.assertNotIn('ns>=250000000',section)
    def test_changed_or_ambiguous_patch_inputs_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'frozen driver pin'):audit.patch.render(self.original+b'\n')
        with self.assertRaisesRegex(ValueError,'anchor'):audit.patch.replace_once('aa','a','b')
        with self.assertRaisesRegex(ValueError,'anchor'):audit.patch.replace_once('x','a','b')
    def test_full_driver_is_compile_only_not_linked_into_bridge(self):
        self.assertEqual(self.report['driver_translation_units_compiled'],2)
        for row in self.report['compile_only_jobs'].values():self.assertIn('-c',row['command'])
        for row in self.report['bridge_builds'].values():
            self.assertFalse(any('driver.o' in arg or 'a23_two_epoch_sdk_driver.m' in arg for arg in row['command']))
    def test_bridge_links_only_foundation_and_helper(self):
        for row in self.report['bridge_builds'].values():
            command=row['command'];self.assertEqual(command[command.index('-framework')+1],'Foundation')
            self.assertEqual(command.count('-framework'),1)
            self.assertNotIn('IOKit',command);self.assertNotIn('IOUSBHost',command)
        self.assertEqual(self.report['foundation_fixture_executions'],4)
    def test_fractional_bridge_does_not_promote_shortfall(self):
        row=self.row('fractional-short');self.assertEqual(row['rounded_up_ns'],250000000);self.assertFalse(row['minimum_met'])
        self.assertTrue(self.row('fractional-equal')['minimum_met']);self.assertTrue(self.row('fractional-after')['minimum_met'])
    def test_unlabeled_and_non_driver_clocks_are_rejected_without_tick_query(self):
        for case in ('plain-clock','pretend-clock','nil-clock','owner-role','supervisor-role','unknown-role'):
            row=self.row(case);self.assertFalse(row['profile_ok']);self.assertEqual(row['tick_reads'],0)
    def test_missing_selector_and_invalid_profiles_reset_output(self):
        for case in ('missing-selector','zero-instance','zero-numerator','zero-denominator'):
            row=self.row(case);self.assertFalse(row['begin_ok']);self.assertTrue(row['begin_zeroed']);self.assertTrue(row['end_zeroed'])
    def test_mutation_during_tick_read_invalidates_the_capture(self):
        for case in ('numerator-during','denominator-during','instance-during','domain-during'):
            row=self.row(case);self.assertTrue(row['begin_ok']);self.assertFalse(row['end_ok'])
            self.assertTrue(row['end_zeroed']);self.assertEqual(row['tick_reads'],2)
    def test_timebase_or_instance_change_between_samples_is_rejected(self):
        for case in ('numerator-between','denominator-between','instance-between'):
            row=self.row(case);self.assertTrue(row['end_ok']);self.assertEqual(row['status'],4)
        self.assertFalse(self.row('domain-between')['end_ok']);self.assertEqual(self.row('domain-between')['tick_reads'],1)
    def test_object_replacement_cannot_reuse_the_same_logical_label(self):
        row=self.row('object-replaced');self.assertTrue(row['begin_ok']);self.assertTrue(row['end_ok'])
        self.assertFalse(row['same_object']);self.assertEqual(row['status'],4)
    def test_bridge_zero_tick_is_separate_from_driver_lifecycle_sentinel(self):
        row=self.row('zero-tick');self.assertTrue(row['begin_ok']);self.assertTrue(row['minimum_met'])
        self.assertIn('!start.stamp.ticks',self.candidate.decode())
    def test_reversed_or_overflowing_bridge_interval_is_invalid(self):
        self.assertEqual(self.row('backwards')['status'],5);self.assertEqual(self.row('overflow')['status'],6)
        for case in ('backwards','overflow'):self.assertFalse(self.row(case)['minimum_met'])
    def test_double_profile_read_does_not_claim_atomicity(self):
        row=self.row('aba-during');self.assertTrue(row['aba_performed']);self.assertTrue(row['end_ok'])
        self.assertFalse(self.report['clock_profile_reads_atomic'])
    def test_bridge_pointer_checks_and_every_reference_case(self):
        self.assertTrue(self.report['bridge']['pointer_checks_passed']);self.assertEqual(len(self.report['bridge']['cases']),27)
        for name in audit.NAMES:self.assertEqual(self.row(name),audit.bridge_oracle(name),name)
    def test_replay_plan_explicitly_excludes_legacy_context_and_clock_execution(self):
        plan=self.report['replay_plan'];self.assertTrue(plan['legacy_two_clock_uses_actual_mach_clock'])
        self.assertTrue(plan['broker_reads_actual_context_and_scope']);self.assertFalse(plan['full_sdk_fixture_executed'])
        self.assertEqual(len(plan['blockers']),4)
    def test_source452_pin_and_production_boundaries(self):
        row=audit.f.load(self.root/'audit.json');self.assertEqual((row['source_count'],row['prior_sources_unchanged']),(452,447))
        for flag in audit.FALSE:self.assertIs(self.report[flag],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.verify(self.root,'0'*64)


if __name__=='__main__':unittest.main()
