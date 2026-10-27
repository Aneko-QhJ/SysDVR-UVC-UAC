from pathlib import Path
import copy,os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_versioned_driver_model as audit


class VersionedDriverModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_VERSIONED_DRIVER_REVIEW'):cls.root=Path(os.environ['A23_VERSIONED_DRIVER_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-versioned-driver-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.report['semantic'][name]
    def test_full_driver_rejects_cooperating_start_and_end_aba(self):
        for name in ('profile-start-aba','profile-end-aba'):
            row=self.row(name);self.assertFalse(row['complete']);self.assertIn('observation_clock',row['failure_reasons'])
    def test_changes_between_capture_and_commit_are_rejected(self):
        for name in ('between-captures-aba','after-capture-aba'):
            row=self.row(name);self.assertFalse(row['complete']);self.assertIn('observation_version',row['failure_reasons']);self.assertNotIn('observation_complete',row['events'])
    def test_event_append_runs_with_odd_ticket_and_releases_to_next_even(self):
        v=self.row('normal')['version'];self.assertEqual((v['start_generation'],v['end_generation'],v['append_generation'],v['released_generation']),(2,2,3,4))
    def test_cooperating_aba_writes_during_append_are_busy(self):
        row=self.row('append-aba-attempt');self.assertTrue(row['complete']);self.assertEqual(row['version']['busy_writes'],2);self.assertEqual(row['version']['write_successes'],0)
    def test_visible_write_during_append_is_busy(self):
        row=self.row('append-visible-attempt');self.assertTrue(row['complete']);self.assertEqual(row['version']['busy_writes'],1)
    def test_append_failure_releases_ticket_without_settlement(self):
        row=self.row('append-journal-failure');self.assertFalse(row['complete']);self.assertEqual(row['version']['released_generation'],4);self.assertIn('journal_failed',row['failure_reasons'])
    def test_callback_during_append_prevents_settlement(self):
        row=self.row('append-callback');self.assertFalse(row['complete']);self.assertIn('observation_complete',row['events']);self.assertEqual(row['version']['released_generation'],4)
    def test_clock_replacement_during_append_releases_acquired_owner(self):
        row=self.row('append-object-replaced');self.assertFalse(row['complete']);self.assertEqual(row['version']['released_generation'],4);self.assertEqual(row['version']['current_generation'],4);self.assertIn('observation_clock',row['failure_reasons'])
    def test_post_release_change_revokes_saved_receipt(self):
        row=self.row('post-receipt-aba');self.assertFalse(row['complete']);self.assertTrue(row['receipt']['stale']);self.assertFalse(row['receipt']['saved']);self.assertEqual(row['version']['current_generation'],8)
    def test_zero_start_and_object_replacement_are_rejected(self):
        for name in ('zero-quiet-start','object-replaced'):self.assertIn('observation_clock',self.row(name)['failure_reasons'])
    def test_fractional_shortfall_stays_pending_until_exact_threshold(self):
        row=self.row('fractional-short-equal');self.assertTrue(row['complete']);self.assertTrue(row['version']['short_poll_observed']);self.assertFalse(row['version']['short_poll_complete'])
    def test_deadline_matrix_still_uses_original_arrival_poll_policy(self):
        for name in audit.DEADLINES:self.assertEqual(self.row(name)['deadline'],audit.deadline_oracle(name))
    def test_queued_delay_and_abort_late_callback_behaviors_remain(self):
        self.assertTrue(self.row('callback-queued-delay')['complete']);row=self.row('iso-abort-late');self.assertEqual(row['aborts'],1);self.assertTrue(row['facts']['owners'][0]['retained'])
    def test_unreported_bypass_remains_an_explicit_negative_control(self):
        row=self.row('profile-end-bypass');self.assertTrue(row['complete']);self.assertEqual(row['facts']['mutations'],1);self.assertEqual(row['version']['write_attempts'],0)
    def test_bridge_lifetime_contract_pointer_checks_and_preflight(self):
        self.assertTrue(audit.f.load(self.root/'work/stdout-optimized.json')['bridge_checks_passed'])
        for name in audit.NAMES:self.assertTrue(self.row(name)['version']['object_bound'])
    def test_critical_methods_stay_identical_and_guard_delta_is_explicit(self):
        raw=audit.a.read(self.root/'source'/audit.model.DRIVER);candidate=audit.a.read(self.root/'work/generated'/audit.model.DRIVER)
        self.assertEqual(audit.model.protected(raw),audit.model.protected(candidate));self.assertIn(b'A23VersionedDriverMatches',candidate)
        self.assertIn('versioned-isolated',audit.a.read(self.root/'work/driver-versioned.diff').decode())
    def test_gate_order_is_capture_begin_append_guard_settle_release(self):
        text=audit.a.read(self.root/'work/generated'/audit.model.DRIVER).decode();section=text[text.index('if(_complete){'):text.index('if(!_pending){')]
        self.assertLess(section.index('A23VersionedDriverBeginCommit'),section.index('emit:@"observation_complete"'));self.assertLess(section.index('if(accepted){_settled=YES'),section.index('A23VersionedDriverEndCommit'))
    def test_version_sidecar_rejects_extra_keys_and_untyped_generations(self):
        row=self.row('normal');v=row['version']
        for key,value in (('extra',0),('start_generation',True),('actual_clock_authenticated',True)):
            changed=copy.deepcopy(v);changed[key]=value
            with self.assertRaises(ValueError):audit.validate_version(changed,'normal',True,2,{'failure_reasons':[]})
    def test_pure_c_helper_unchanged_and_foundation_only_link(self):
        for path in ('host/a23_versioned_clock_candidate.c','host/a23_versioned_clock_candidate.h'):
            self.assertEqual(audit.a.read(self.root/'source'/audit.BASE/path),audit.a.read(self.root/'work/generated'/audit.BASE/path))
        for row in self.report['builds'].values():self.assertEqual(row['command'].count('-framework'),1);self.assertIn('Foundation',row['command']);self.assertIn('versioned_helper_command',row)
    def test_frozen474_and_expected_model_scope(self):
        report=audit.f.load(self.root/'audit.json');self.assertEqual((report['source_count'],report['prior_sources_unchanged']),(474,467));self.assertEqual(self.report['model_cases'],59);self.assertTrue(self.report['versioned_driver_model_integrated'])
        for flag in audit.FALSE:self.assertIs(self.report[flag],False)
    def test_readonly_external_pin_and_formal_namespace_absence(self):
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.verify(self.root,'0'*64)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())


if __name__=='__main__':unittest.main()
