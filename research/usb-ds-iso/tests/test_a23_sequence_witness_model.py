import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import a23_sequence_witness_model as m


class SequenceWitnessTests(unittest.TestCase):
    def test_old_sequence_one_is_distinct_from_proposed_block(self):
        self.assertEqual(m.propose_block([1,1]),17)
        r=m.compare_model(17,1,1,1,m.expected_payload(1))
        self.assertFalse(r['supplied_sequence_agreement'])

    def test_matching_model_never_authenticates_or_issues(self):
        r=m.compare_model(17,17,17,17,m.expected_payload(17))
        self.assertTrue(r['supplied_sequence_agreement'])
        for key in ('physical_run_authenticated','source_authenticated','root_cause_confirmed','usb_strict_pass','acquisition_enabled','unique_historical_allocation_verified'):
            self.assertIs(r[key],False)
        self.assertEqual(r['remaining'],0)

    def test_each_mixed_field_and_payload_is_rejected(self):
        for i in range(4):
            args=[17,17,17,m.expected_payload(17)];args[i]=1 if i<3 else m.expected_payload(1)
            with self.subTest(i=i):self.assertFalse(m.compare_model(17,*args)['supplied_sequence_agreement'])

    def test_partial_corrupt_and_reordered_payloads_fail(self):
        p=m.expected_payload(17)
        for value in (p[:-1],p+b'\0',bytes([p[0]^1])+p[1:],p[192:384]+p[:192]+p[384:]):
            self.assertFalse(m.compare_model(17,17,17,17,value)['supplied_sequence_agreement'])

    def test_boolean_and_out_of_range_sequences_fail(self):
        for value in (True,False,-1,65536,1.0,'17',None):
            with self.subTest(value=value),self.assertRaises(ValueError):m.packet_sequences(value)
            with self.subTest(value=value),self.assertRaises(ValueError):m.propose_block([value])

    def test_wraparound_history_blocks_intersecting_new_ranges(self):
        self.assertEqual(m.packet_sequences(65535)[:3],(65535,0,1))
        self.assertEqual(m.propose_block([65535]),17)
        self.assertEqual(m.propose_block([2]),33)

    def test_exhaustion_is_not_recycling(self):
        with self.assertRaisesRegex(ValueError,'exhausted'):m.propose_block(list(range(1,65521,16)))

    def test_proposals_do_not_mutate_or_reserve(self):
        used=[1];self.assertEqual(m.propose_block(used),m.propose_block(used));self.assertEqual(used,[1])
        with self.assertRaises(ValueError):m.propose_block({1})


if __name__=='__main__':unittest.main()
