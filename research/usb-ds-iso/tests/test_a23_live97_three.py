"""Review saved native integration evidence without launching hardware."""
import json,os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_a23_live97_three as b

class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['A23_LIVE97_REVIEW']);b.core.verify_seal(cls.root);cls.r=b.w.load(cls.root/'report.json')
    def test_normal_three_strict_checked_export(self):
        for n in ('normal','queued-delay'):
            r=self.r['accepted'][n];self.assertEqual(r['sdk']['total_bytes'],9216);self.assertTrue(r['checked_export']['supplied_export_chain_complete']);self.assertTrue(self.r['synthetic_clock_rejected'][n])
    def test_old32_and_bad_archive_never_open(self):
        for n in ('old32-permit','range32-permit','count32-reservation','frozen-source','frozen-spent145','generated','binary'):self.assertEqual(self.r['matrix'][n]['calls']['opens'],0)
    def test_source_change_before_third_stops_at_two(self):self.assertEqual(self.r['matrix']['between-third-source']['calls']['iso_submissions'],2)
    def test_third_failure_preserves_all_owner_snapshots(self):
        for n in ('third-bad-status','third-status-collision'):
            host=self.root/'cases'/n/'host';self.assertTrue((host/'live-evidence-epoch-2/COMMITTED').is_file());self.assertTrue((host/'live-failure/COMMITTED').is_file());self.assertFalse((host/'live-acceptance').exists())
    def test_boundaries_and_prior_sources(self):
        self.assertEqual(self.r['source_count'],623)
        for k in ('formal_reservations','new_authorizations','usb_requests','sd_accesses','real_sdk_objects','remaining'):self.assertEqual(self.r[k],0)
    def test_post_receipt_payload_change_rejected_by_collector(self):
        self.assertTrue(self.r['matrix']['after-receipt-bytes']['loop']['success']);self.assertIn('after-receipt-bytes',self.r['collector_rejections'])
    def test_replay_and_unauthorized_issue_refused(self):self.assertEqual(len(self.r['replay_rejections']),5)

if __name__=='__main__':unittest.main()
