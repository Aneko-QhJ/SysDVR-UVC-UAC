from pathlib import Path
import copy,os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_driver_fault_model as audit


class DriverFaultModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_DRIVER_FAULT_REVIEW'):cls.root=Path(os.environ['A23_DRIVER_FAULT_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-driver-fault-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.report['semantic'][name]
    def test_arrival_equal_allowed_and_poll_equal_times_out(self):
        for target in ('control','iso'):
            self.assertTrue(self.row(target+'-arrival-1to1-equal')['complete']);self.assertFalse(self.row(target+'-poll-1to1-equal')['complete'])
    def test_fractional_poll_can_expire_before_exact_limit(self):
        row=self.row('control-poll-2to3-before');self.assertFalse(row['complete']);self.assertEqual(row['deadline']['exact_ns'],[47999998,3]);self.assertEqual(row['deadline']['rounded_up_ns'],16000000)
    def test_fractional_arrival_before_limit_remains_accepted(self):
        for target in ('control','iso'):self.assertTrue(self.row(target+'-arrival-2to3-before')['complete'])
    def test_all_24_deadline_edges_follow_independent_fraction_oracle(self):
        self.assertEqual(len(audit.DEADLINES),24)
        for name in audit.DEADLINES:self.assertEqual(self.row(name)['deadline'],audit.deadline_oracle(name))
    def test_missing_iso_aborts_once_and_retains_owner_storage(self):
        row=self.row('iso-poll-1to1-equal');self.assertEqual(row['aborts'],1);self.assertTrue(row['facts']['owners'][0]['retained']);self.assertEqual(row['facts']['owners'][0]['callbacks'],0)
    def test_missing_control_does_not_abort_completed_iso(self):
        self.assertEqual(self.row('control-poll-1to1-equal')['aborts'],0)
    def test_late_callback_after_abort_stays_terminal_and_retained(self):
        row=self.row('iso-abort-late');self.assertFalse(row['complete']);self.assertEqual(row['aborts'],1);owner=row['facts']['owners'][0];self.assertEqual(owner['state'],4);self.assertTrue(owner['retained']);self.assertTrue(owner['timed_out'])
    def test_queued_callback_uses_arrival_instead_of_processing_time(self):
        row=self.row('callback-queued-delay');self.assertTrue(row['complete']);self.assertEqual(row['facts']['target_end_ticks'],25000100)
    def test_duplicate_callbacks_are_terminal_without_second_epoch(self):
        for name in ('duplicate-iso','duplicate-control'):self.assertFalse(self.row(name)['complete']);self.assertEqual(self.row(name)['saved_epochs'],0)
    def test_foreign_pointer_keeps_original_storage(self):
        row=self.row('foreign-pointer');self.assertEqual(row['facts']['owners'][0]['state'],3);self.assertTrue(row['facts']['owners'][0]['retained'])
    def test_control_error_bytes_and_iso_error_stop_before_save(self):
        for name in ('control-error','control-bytes','iso-error'):self.assertEqual(self.row(name)['saved_epochs'],0)
    def test_old_control_between_epochs_prevents_second_arm(self):
        row=self.row('old-control-between-epochs');self.assertEqual(row['saved_epochs'],1);self.assertFalse(row['complete']);self.assertNotIn('epochs_saved',row['events'])
    def test_early_iso_and_rejected_submissions_do_not_retry(self):
        for name in ('early-iso','iso-reject','trigger-reject'):self.assertEqual(self.row(name)['saved_epochs'],0)
        self.assertEqual(self.row('trigger-reject')['aborts'],1)
    def test_visible_start_profile_mutations_prevent_start_commit(self):
        for field in ('numerator','denominator','domain','instance'):
            row=self.row('profile-start-'+field);self.assertEqual(row['facts']['quiet_start_ticks'],0);self.assertIn('observation_clock',row['failure_reasons'])
    def test_visible_end_profile_mutations_prevent_settlement(self):
        for field in ('numerator','denominator','domain','instance'):
            row=self.row('profile-end-'+field);self.assertEqual(row['facts']['quiet_start_ticks'],100);self.assertFalse(row['complete'])
    def test_aba_changes_are_observed_by_fixture_but_not_rejected(self):
        for stage in ('start','end'):
            row=self.row('profile-'+stage+'-aba');self.assertEqual(row['facts']['mutations'],1);self.assertTrue(row['complete']);self.assertFalse(row['facts']['profile_reads_atomic'])
    def test_sidecar_rejects_untyped_fields_unknown_keys_and_authority_claims(self):
        original=self.row('callback-queued-delay')['facts']
        mutations=[('target_end_ticks',1.0),('initial_ticks',True),('extra',0),('actual_clock_authenticated',True),('profile_reads_atomic',True)]
        for key,value in mutations:
            changed=copy.deepcopy(original);changed[key]=value
            with self.assertRaises(ValueError):audit.facts_valid(changed,'callback-queued-delay')
        changed=copy.deepcopy(original);changed['owners'][0]['retained']=0
        with self.assertRaises(ValueError):audit.facts_valid(changed,'callback-queued-delay')
    def test_same_driver_candidate_and_unchanged_protected_methods(self):
        raw=audit.a.read(self.root/'source'/audit.previous.previous.DRIVER);candidate=audit.a.read(self.root/'work/generated'/audit.previous.previous.DRIVER)
        patch=audit.previous.previous.patch;self.assertEqual(patch.render(raw),candidate);self.assertEqual(patch.protected_slices(raw),patch.protected_slices(candidate))
    def test_link_scope_and_readonly_external_pin(self):
        for mode,row in self.report['builds'].items():
            self.assertEqual(row['command'].count('-framework'),1)
            for label in row['link_scope']:
                raw=audit.a.read(self.root/'work'/('scope-'+mode)/(label+'.txt'));self.assertFalse(any(token in raw for token in audit.DENY))
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.verify(self.root,'0'*64)
    def test_source462_and_limits(self):
        report=audit.f.load(self.root/'audit.json');self.assertEqual((report['source_count'],report['prior_sources_unchanged']),(462,457));self.assertEqual(self.report['model_cases'],46)
        for flag in audit.FALSE:self.assertIs(self.report[flag],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())


if __name__=='__main__':unittest.main()
