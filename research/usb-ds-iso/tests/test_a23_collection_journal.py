from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_collection_journal as a
class JournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_JOURNAL_REVIEW'):cls.root=Path(os.environ['A23_JOURNAL_REVIEW'])
        else:cls.tmp=tempfile.TemporaryDirectory(prefix='a23-journal-tests-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';a.run(cls.root)
        a.w.card.seal_verify(cls.root);cls.audit=a.f.load(cls.root/'audit.json');cls.rows={n:r['result']['analysis'] for n,r in cls.audit['matrix'].items()}
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def test_sources_397_and_frozen_native_392(self):self.assertEqual(len(a.sources()),397);self.assertEqual(self.audit['native_build_source_count'],392);self.assertFalse(self.audit['new_sdk_model_execution'])
    def test_only_completed_transactions_admitted(self):self.assertEqual({n for n,r in self.rows.items() if r['journal_committed']},{'normal-complete','normal-missing','hold-reserved'})
    def test_missing_report_remains_incomplete_chain(self):self.assertTrue(self.rows['normal-missing']['journal_committed']);self.assertFalse(self.rows['normal-missing']['complete_injected_model_chain'])
    def test_five_actual_process_interruptions(self):
        for name in ('crash-reserved','crash-final_started','crash-final_frozen','crash-revalidated','crash-completed'):self.assertEqual(self.audit['matrix'][name]['exit']['returncode'],73);self.assertFalse(self.rows[name]['journal_committed'])
    def test_completed_inner_does_not_promote_outer(self):self.assertTrue(self.rows['crash-completed']['inner_envelope_sealed']);self.assertFalse(self.rows['crash-completed']['complete_injected_model_chain'])
    def test_half_inner_output_preserved(self):self.assertTrue((self.root/'models/crash-final_started/journal/envelope/final/ATTEMPT').exists());self.assertFalse((self.root/'models/crash-final_started/journal/envelope/final/COMMITTED').exists())
    def test_source_drift_after_inner_freeze_keeps_failure(self):self.assertTrue(self.rows['source-drift']['failure_recorded']);self.assertEqual(self.rows['source-drift']['last_event'],'envelope_prepared');self.assertFalse(self.rows['source-drift']['journal_committed'])
    def test_unsafe_tree_has_durable_pre_scan_marker(self):
        for name in ('symlink-input','fifo-input','oversize-report','excess-nodes'):self.assertEqual(self.rows[name]['last_event'],'reserved');self.assertTrue(self.rows[name]['failure_recorded']);self.assertTrue(self.audit['retained_attempts'][name]['marker_retained'])
    def test_all_retries_refused_without_changing_journal(self):self.assertEqual(len(self.audit['retained_attempts']),14);self.assertTrue(all(v['retry_refused'] and v['journal_unchanged'] for v in self.audit['retained_attempts'].values()))
    def test_running_and_unknown_workers_refused(self):self.assertTrue(self.audit['lifecycle']['running_refused']);self.assertTrue(self.audit['lifecycle']['unknown_refused'])
    def test_partial_source_attempt_remains_spent(self):self.assertEqual(a.a.read(self.root/'models/partial-marker/SOURCE_ATTEMPT'),b'{');self.assertTrue(self.audit['lifecycle']['partial_marker_retained'])
    def test_two_process_race_only_one_winner(self):self.assertEqual(sorted(self.audit['lifecycle']['race_exitcodes']),[0,2])
    def test_eight_forged_archives_rejected(self):self.assertEqual(len(self.audit['negative_archives']),8);self.assertEqual(self.audit['negative_archives']['forged-partial-success'],'saved journal analysis differs')
    def test_forensic_seal_does_not_commit_partial_journal(self):self.assertTrue((self.root/'models/crash-completed/COMMITTED').exists());self.assertFalse((self.root/'models/crash-completed/journal/COMMITTED').exists())
    def test_other_worker_exit_cannot_be_joined(self):self.assertTrue(self.audit['lifecycle']['unrelated_worker_refused']);self.assertEqual(self.audit['negative_archives']['worker-job-binding'],'worker job does not own journal')
    def test_static_copy_never_claims_worker_exit(self):self.assertFalse(self.audit['lifecycle']['static_worker_exit_claimed']);self.assertTrue(self.audit['lifecycle']['static_journal_committed'])
    def test_no_hardware_or_formal_namespace(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations'):self.assertEqual(self.audit[k],0)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
if __name__=='__main__':unittest.main()
