import os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_checked_export as a


class CheckedExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['A23_CHECKED_EXPORT_REVIEW']);cls.report=a.verify(cls.root);cls.matrix=cls.report['native_matrix']

    def test_two_boundaries_bind_source_and_timing(self):
        for name in ('normal','queued-delay'):
            r=self.report['accepted'][name]
            self.assertEqual(r['post_full_checks'],r['pre_full_checks']+1)
            self.assertTrue(r['supplied_export_chain_complete'])
            self.assertEqual(r['candidate_binding'],self.report['candidate_binding'])

    def test_mutations_during_export_cannot_get_accepted(self):
        for n in ('before-pre-source','mid-payload-source','after-payload-source','after-payload-baseline','after-payload-context','after-payload-bytes'):
            self.assertIn(n,self.report['rejected']);self.assertFalse(self.matrix[n]['loop']['success'])

    def test_pure_getters_are_not_used_as_freshness_proof(self):
        r=self.matrix['stale-getters'];self.assertTrue(r['stale_getter_seen']);self.assertTrue(r['getters_had_no_checks'])
        self.assertIn('stale-getters',self.report['rejected'])

    def test_payload_without_acceptance_is_incomplete(self):
        for n in ('payload-collision','acceptance-collision'):
            self.assertFalse(self.matrix[n]['loop']['success']);self.assertIn(n,self.report['rejected'])
        self.assertTrue(self.matrix['acceptance-collision']['loop']['export_saved'])

    def test_pending_failure_keeps_owner_without_hashing_or_copying(self):
        r=self.matrix['exit-running'];self.assertTrue(r['pending_full_checks_skipped']);self.assertTrue(r['loop']['unresolved_keep_alive'])
        self.assertEqual(r['calls']['iso_submissions'],1)
        self.assertEqual(r['loop']['owner_evidence_snapshots_saved'],0)

    def test_bad_status_still_keeps_raw_before_rejection(self):
        r=self.matrix['bad-status'];self.assertEqual(r['calls']['iso_submissions'],1)
        files=a.w.card.seal_verify(self.root/'cases/bad-status/host/status-after-epoch-0')
        self.assertEqual(len(files['raw.bin']),168);self.assertIn('transferred',a.json.loads(files['verdict.json'])['failed_checks'])

    def test_consumer_detects_changed_payload_even_after_controller_success(self):
        self.assertTrue(self.matrix['after-receipt-bytes']['loop']['success'])
        self.assertIn('after-receipt-bytes',self.report['rejected'])

    def test_later_source_change_is_not_falsely_promoted_to_current_freshness(self):
        r=self.report['accepted']['after-post-source']
        self.assertFalse(r['current_disk_freshness_verified']);self.assertFalse(r['physical_run_authenticated'])
        self.assertFalse(r['creator_wait_verified']);self.assertFalse(r['atomic_directory_snapshot_verified'])

    def test_resealed_or_incomplete_negative_archives_rejected(self):
        self.assertEqual(set(self.report['negative_archives']),set(a.NEGATIVES))
        self.assertTrue(all(v['rejected'] for v in self.report['negative_archives'].values()))

    def test_hardware_state_and_old_sources_preserved(self):
        self.assertEqual(self.report['source_count'],607);self.assertEqual(self.report['prior_sources_unchanged'],601)
        self.assertEqual(self.report['native_fixture_waits'],15)
        self.assertFalse(self.report['hardware_candidate_ready']);self.assertFalse(self.report['live_acquisition_entry_adopted'])
        for k in ('usb_requests','sd_accesses','real_sdk_objects','actual_acquisition_invocations','formal_records','formal_reservations','remaining'):
            self.assertEqual(self.report[k],0)


if __name__=='__main__':unittest.main()
