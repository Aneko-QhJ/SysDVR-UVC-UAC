"""Check saved observations of the bounded trace and unchanged stop policy."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import audit_a23_interest_trace as a

class InterestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['A23_INTEREST_REVIEW']);a.b.core.verify_seal(cls.root);cls.r=a.w.load(cls.root/'report.json');cls.rows=cls.r['matrix']
    def test_every_message_stops_including_unknown_and_zero(self):
        for n in self.r['message_values']:self.assertEqual(self.rows[n]['iso_submissions'],2);self.assertTrue(self.rows[n]['result']['stopped'])
    def test_raw_values_are_not_relabelled_as_termination(self):
        for n,v in self.r['message_values'].items():self.assertEqual(self.rows[n]['result']['lease']['interest_trace']['rows'][0]['message_u32'],v)
    def test_pending_is_not_exposed_as_committed(self):
        d=self.rows['contracts']['pending'];self.assertFalse(d['complete']);self.assertEqual(d['pending'],1);self.assertEqual(d['rows'],[])
    def test_poison_before_slot_is_not_a_complete_empty_trace(self):
        d=self.rows['contracts']['latch_gap'];self.assertTrue(d['latch_without_slot']);self.assertFalse(d['complete']);self.assertEqual(d['rows'],[])
    def test_concurrency_is_bounded_and_overflow_explicit(self):
        d=self.rows['contracts'];self.assertEqual(d['native_threads_joined'],9);self.assertLessEqual(d['overflow']['claimed'],8);self.assertTrue(d['overflow']['overflow']);self.assertFalse(d['overflow']['complete'])
    def test_normal_and_authority_boundary(self):
        self.assertTrue(self.rows['normal']['result']['complete']);self.assertFalse(self.r['hardware_ready']);self.assertFalse(self.r['sdk_argument_captured'])
        for k in ('usb_requests','sd_accesses','real_sdk_objects','new_authorizations','formal_reservations','remaining'):self.assertEqual(self.r[k],0)

if __name__=='__main__':unittest.main()
