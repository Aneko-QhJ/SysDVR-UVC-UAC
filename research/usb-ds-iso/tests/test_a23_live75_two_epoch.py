import os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_live75_two_epoch as a


class Live75Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_LIVE75_REVIEW');cls.tmp=None
        if saved:cls.root=Path(saved)
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-live75-unit-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';a.run(cls.root)
        cls.report=a.verify(cls.root);cls.matrix=cls.report['native_matrix']
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def test_current75_and_all_spent_intervals_bound(self):
        self.assertEqual(self.report['baseline_files'],75)
        self.assertEqual([(r['first'],r['last']) for r in self.report['historical_intervals']],[(49,64),(65,80),(81,96),(97,112)])
        self.assertEqual((self.report['scope']['first_sequence'],self.report['scope']['last_sequence']),(113,144))
    def test_two_successes_use_new_payload_range_and_status_capture(self):
        for name,result in self.report['accepted'].items():
            self.assertEqual(result['sdk']['epochs'][0]['first_sequence'],113);self.assertEqual(result['sdk']['epochs'][1]['first_sequence'],129)
            self.assertTrue(result['sdk']['status_captures_verified']);self.assertEqual(result['sdk']['total_bytes'],6144)
            self.assertEqual(self.matrix[name]['calls']['iso_submissions'],2)
    def test_spent_predecessor_missing_extra_and_drift_block_iso(self):
        for name in ('predecessor-drift','predecessor-extra','predecessor-missing'):
            self.assertEqual(self.matrix[name]['calls']['iso_submissions'],0);self.assertTrue(self.matrix[name]['verifier']['failed'])
    def test_baseline_source_and_recovery_changes_block_iso(self):
        for name in ('new-recovery','baseline-drift','legacy-drift','live-source-afterprepare'):
            self.assertEqual(self.matrix[name]['calls']['iso_submissions'],0)
    def test_first_failure_blocks_second_and_keeps_status_original(self):
        self.assertEqual(self.matrix['bad-status']['calls']['iso_submissions'],1)
        files=a.w.card.seal_verify(self.root/'cases/bad-status/host/status-after-epoch-0')
        self.assertIn('transferred',a.json.loads(files['verdict.json'])['failed_checks']);self.assertEqual(len(files['raw.bin']),168)
    def test_no_full_hashing_while_pending_and_next_round_guarded(self):
        for name in ('during-pending-source','stopped-pending-source'):
            self.assertTrue(self.matrix[name]['full_checks_skipped_while_pending']);self.assertEqual(self.matrix[name]['calls']['iso_submissions'],1)
        self.assertEqual(self.matrix['between-epochs-source']['calls']['iso_submissions'],1)
    def test_frozen_and_resealed_generated_tampering_cannot_open_sdk(self):
        for name in a.ARCHIVES:
            self.assertFalse(self.matrix[name]['initial_core']);self.assertEqual(self.matrix[name]['calls']['opens'],0)
    def test_once_consume_and_foreign_job_replay_rejected(self):
        self.assertEqual(len(self.report['replay_rejections']),4);self.assertTrue(all(self.report['replay_rejections'].values()))
    def test_preview_and_unauthorized_issue_leave_formal_namespace_absent(self):
        self.assertFalse(a.builder.FORMAL_ROOT.exists());self.assertFalse(self.report['preview']['sequence_reserved'])
        with self.assertRaises(ValueError):a.flow.issue(self.root/'build',authorized=False)
        self.assertFalse(a.builder.FORMAL_ROOT.exists())
    def test_file_modes_and_no_real_hardware_authority_used(self):
        self.assertEqual(self.report['file_modes']['current']['returncode'],0);self.assertEqual(self.report['file_modes']['missing-job']['returncode'],2)
        for key in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations','authorization_consumptions','remaining'):
            self.assertEqual(self.report[key],0)
        self.assertEqual(self.report['source_count'],597);self.assertEqual(self.report['prior_sources_unchanged'],592)


if __name__=='__main__':unittest.main()
