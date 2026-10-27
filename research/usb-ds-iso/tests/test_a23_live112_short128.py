"""Fresh112 guard integration, source bound to the frozen native result."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_a23_live112_short128 as b
class Rebind(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=Path(os.environ['A23_LIVE112_REVIEW']);b.core.verify_seal(p);cls.r=b.w.load(p/'report.json')
    def test_new_three_epoch_chain(self):
        v=self.r['accepted']['normal'];self.assertEqual([x['first_sequence'] for x in v['sdk']['epochs']],[321,337,353]);self.assertEqual(v['sdk']['total_bytes'],9216);self.assertEqual(v['checked_export']['candidate_binding']['transaction_count'],128)
    def test_spent273_including_zero_submit_range_is_bound(self):
        for n in ('spent273-drift','spent273-extra','spent273-missing'):self.assertEqual(self.r['matrix'][n]['calls']['iso_submissions'],0)
    def test_new_source_baseline_and_old_scope(self):
        for n in ('source640-pre','baseline112-pre'):self.assertEqual(self.r['matrix'][n]['calls']['iso_submissions'],0)
        for n in ('old273-scope','count32-reservation','frozen-spent273'):self.assertEqual(self.r['matrix'][n]['calls']['opens'],0)
    def test_between_epoch_change_and_interest_stop(self):
        for n in ('between-third-source','interest-close'):self.assertEqual(self.r['matrix'][n]['calls']['iso_submissions'],2)
        self.assertEqual(self.r['interest_failures']['interest-close']['after_operator_off']['message_values'],[0xe0005003])
    def test_original_128_transport_and_replay(self):
        self.assertEqual(self.r['source_count'],640);self.assertEqual(len(self.r['replay_rejections']),3)
        for n in ('raw960','rows960','old109-build-consumer','after-off-prefix'):self.assertIn(n,self.r['rejections'])
    def test_file_modes_and_no_hardware(self):
        self.assertEqual(self.r['file_modes']['unissued']['returncode'],2)
        for n in ('new_authorizations','formal_reservations','real_sdk_objects','usb_requests','sd_accesses','remaining'):self.assertEqual(self.r[n],0)
if __name__=='__main__':unittest.main()
