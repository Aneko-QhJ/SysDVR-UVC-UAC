from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_io_usb_host_timestamps import timestamp_summary


class AbsoluteTimeTests(unittest.TestCase):
    def test_exact_fractional_timebase_is_not_raw_nanoseconds(self):
        r=timestamp_summary([101,104,107],125,3,100,110,99)
        self.assertEqual(r['span_ns'],dict(numerator=250,denominator=1,floor=250))
        self.assertEqual(r['first_from_frame_ns'],dict(numerator=250,denominator=3,floor=83))
        self.assertFalse(r['bus_phase_verified']);self.assertFalse(r['baseline_accepted'])
        self.assertFalse(r['allow_next_burst']);self.assertFalse(r['callback_drain_verified'])

    def test_shared_timestamps_are_preserved(self):
        r=timestamp_summary([102,102,105],1,1,100,110,99)
        self.assertEqual(r['duplicate_nonzero_count'],1)
        self.assertEqual(r['nonzero_run_length_counts'],{1:1,2:1})
        self.assertEqual(r['adjacent_min_ns']['floor'],0)
        self.assertFalse(r['timestamps_required_unique'])

    def test_missing_times_do_not_become_elapsed_times(self):
        r=timestamp_summary([0,102,0],1,1,100,110,99)
        self.assertEqual(r['zero_count'],2);self.assertEqual(r['adjacent_comparable_count'],0)
        self.assertIsNone(r['adjacent_mean_ns'])
        self.assertEqual(timestamp_summary([102,0,102],1,1,100,110,99)['nonzero_run_length_counts'],{1:2})
        r=timestamp_summary([0,0],1,1,100,110,99)
        self.assertIsNone(r['span_ns']);self.assertIsNone(r['callback_from_last_ns'])

    def test_regression_and_boundary_anomalies_are_not_hidden_by_sorting(self):
        r=timestamp_summary([98,115,102],1,1,100,110,99)
        self.assertEqual(r['backward_pairs'],1)
        self.assertEqual(r['before_submit_count'],1);self.assertEqual(r['after_callback_count'],1)
        self.assertEqual(r['adjacent_min_ns']['floor'],-13)
        self.assertEqual(r['first_from_frame_ns']['floor'],-1)

    def test_invalid_units_types_and_boundaries_rejected(self):
        for args in [([True],1,1,100,110,99),([2**64],1,1,100,110,99),
                     ([],1,1,100,110,99),([102],0,1,100,110,99),([102],1,0,100,110,99),
                     ([102],1,True,100,110,99),([102],1,1,110,100,99)]:
            with self.assertRaises(ValueError):timestamp_summary(*args)


if __name__=='__main__':unittest.main()
