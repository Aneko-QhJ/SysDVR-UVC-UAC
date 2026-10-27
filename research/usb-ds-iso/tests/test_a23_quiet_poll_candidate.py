from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_quiet_poll_candidate as audit


class NativeQuietPollCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_QUIET_POLL_REVIEW'):cls.root=Path(os.environ['A23_QUIET_POLL_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-quiet-poll-tests-',dir='/private/tmp')
            cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def rows(self,name):return self.report['results']['quiet'][name]['steps']
    def deadline(self,name):return self.report['results']['deadlines'][name]
    def test_exact_and_fractional_wait_then_settle_once(self):
        for case in ('one-to-one','fractional-short-equal'):
            rows=self.rows(case);self.assertEqual([r['poll_status'] for r in rows],[1,2,2])
            self.assertEqual([r['complete_attempts'] for r in rows],[0,1,1])
            self.assertEqual([r['complete_successes'] for r in rows],[0,1,1])
    def test_not_started_or_epochs_not_saved_cannot_complete(self):
        for case in ('unstarted','epochs-not-saved'):
            for row in self.rows(case):
                self.assertEqual(row['poll_status'],0);self.assertEqual(row['complete_attempts'],0)
        self.assertEqual(self.rows('unstarted')[-1]['guard_calls'],0)
        self.assertEqual(self.rows('epochs-not-saved')[-1]['guard_calls'],2)
    def test_zero_is_preserved_as_unstarted_quiet_sentinel(self):
        row=self.rows('zero-sentinel')[0]
        self.assertEqual((row['poll_status'],row['reason'],row['clock_status']),(3,1,1))
        self.assertEqual(row['complete_attempts'],0)
    def test_existing_stop_and_journal_failure_never_retry(self):
        for case,status in (('already-stopped',3),('already-journal-failed',4)):
            rows=self.rows(case);self.assertEqual([r['poll_status'] for r in rows],[status,status])
            self.assertEqual(rows[-1]['guard_calls'],0);self.assertEqual(rows[-1]['complete_attempts'],0)
            self.assertFalse(rows[-1]['flags']&16)
    def test_preguard_failure_prevents_completion_event(self):
        row=self.rows('preguard-failure')[-1]
        self.assertEqual(row['complete_attempts'],0);self.assertEqual(row['stop_attempts'],1)
        self.assertEqual(row['guard_calls'],1);self.assertEqual(row['trace'],int('25',8))
    def test_completion_event_precedes_postguard_and_settlement(self):
        rows=self.rows('one-to-one')
        self.assertEqual(rows[1]['trace'],int('1131',8))
        self.assertEqual(rows[1]['settled_at'],250000100)
        self.assertEqual(rows[1]['complete_successes'],1)
    def test_postguard_failure_retains_event_but_denies_settlement(self):
        row=self.rows('postguard-failure')[-1]
        self.assertEqual(row['trace'],int('1325',8))
        self.assertEqual(row['complete_successes'],1);self.assertEqual(row['stop_successes'],1)
        self.assertEqual(row['poll_status'],3);self.assertFalse(row['flags']&16)
        self.assertEqual(row['settled_at'],0)
    def test_append_failure_sets_journal_failure_and_blocks_retry(self):
        row=self.rows('completion-append-failure')[-1]
        self.assertEqual(row['trace'],int('14',8));self.assertEqual(row['poll_status'],4)
        self.assertEqual(row['guard_calls'],1);self.assertEqual(row['complete_attempts'],1)
        self.assertEqual(row['complete_successes'],0);self.assertEqual(row['stop_attempts'],0)
    def test_stop_append_failure_is_also_terminal(self):
        for case,trace in (('stop-append-failure','26'),('postguard-stop-append-failure','1326')):
            row=self.rows(case)[-1];self.assertEqual(row['poll_status'],4)
            self.assertEqual(row['trace'],int(trace,8));self.assertEqual(row['stop_successes'],0)
    def test_settlement_can_be_revoked_without_erasing_diagnostic_ticks(self):
        rows=self.rows('settled-then-guard-failure')
        self.assertEqual([r['poll_status'] for r in rows],[2,3,3])
        self.assertTrue(rows[0]['flags']&16);self.assertFalse(rows[-1]['flags']&16)
        self.assertEqual([r['settled_at'] for r in rows],[250000100]*3)
        self.assertEqual(rows[-1]['complete_attempts'],1)
    def test_postguard_is_not_evaluated_before_minimum(self):
        rows=self.rows('short-does-not-call-postguard')
        self.assertEqual(rows[0]['poll_status'],1);self.assertEqual(rows[0]['guard_calls'],1)
        self.assertEqual(rows[1]['poll_status'],2)
    def test_clock_errors_and_non_driver_roles_fail_closed(self):
        for case in ('reversed','cross-domain','clock-instance-changed','timebase-changed','unknown-timebase',
                     'owner-role-refused','supervisor-role-refused','overflow'):
            row=self.rows(case)[0];self.assertEqual(row['poll_status'],3,case)
            self.assertEqual(row['reason'],1,case);self.assertEqual(row['complete_attempts'],0,case)
    def test_corrupt_attempted_state_cannot_repeat_completion(self):
        row=self.rows('attempted-without-settlement')[0]
        self.assertEqual((row['poll_status'],row['reason']),(3,4));self.assertEqual(row['complete_attempts'],0)
    def test_every_initial_flag_combination_requires_observed_success_before_settlement(self):
        for flags in range(64):
            for row in self.rows(f'initial-flags-{flags:02d}'):
                if row['flags']&16:
                    self.assertEqual(row['poll_status'],2);self.assertEqual(row['complete_successes'],1)
                    self.assertEqual(row['flags']&35,35);self.assertGreater(row['settled_at'],0)
    def test_arrival_equality_is_allowed_but_poll_equality_expires(self):
        self.assertFalse(self.deadline('arrival-exact')['expired'])
        self.assertTrue(self.deadline('poll-exact')['expired'])
    def test_fractional_poll_conservatism_is_preserved(self):
        self.assertTrue(self.deadline('fractional-poll-conservative')['expired'])
        self.assertFalse(self.deadline('fractional-arrival-before')['expired'])
    def test_invalid_deadline_clocks_expire_including_zero_start(self):
        for case in ('zero-start','reversed','cross-domain','instance','unknown-timebase','overflow'):
            row=self.deadline(case);self.assertNotEqual(row['clock_status'],0);self.assertTrue(row['expired'])
    def test_all_native_transitions_and_deadlines_match_reference(self):
        self.assertGreater(self.report['quiet_scenarios'],600);self.assertEqual(self.report['deadline_cases'],166)
        for name,v in self.report['cases']['quiet'].items():self.assertEqual({'steps':self.rows(name)},audit.quiet_oracle(v),name)
        for name,v in self.report['cases']['deadlines'].items():self.assertEqual(self.deadline(name),audit.deadline_oracle(v),name)
    def test_both_builds_and_malformed_protocol_are_clean(self):
        self.assertEqual(set(self.report['builds']),{'optimized','ubsan'})
        for row in self.report['builds'].values():self.assertEqual(row['compiler_stderr'],'');self.assertEqual(row['returncode'],0)
        for rows in self.report['malformed_protocol'].values():self.assertEqual(len(rows),12);self.assertEqual(set(rows.values()),{2})
        self.assertEqual(self.report['native_fixture_executions'],30)
    def test_source447_pin_and_no_production_authority(self):
        row=audit.f.load(self.root/'audit.json')
        self.assertEqual((row['source_count'],row['prior_sources_unchanged']),(447,442))
        for flag in audit.FALSE:self.assertIs(self.report[flag],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.verify(self.root,'0'*64)


if __name__=='__main__':unittest.main()
