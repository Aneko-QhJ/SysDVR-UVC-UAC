"""Source-bound integration observations plus raw trace input rejection."""
import copy,os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_a23_live109_short128 as b
import a23_live109_short128_workflow as flow

class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['A23_SHORT128_REVIEW']);b.core.verify_seal(cls.root);cls.r=b.w.load(cls.root/'report.json')
    def test_success_binds_new_range_and_empty_trace(self):
        for n,row in self.r['accepted'].items():
            self.assertEqual(row['sdk']['total_bytes'],9216);self.assertEqual(row['sdk']['epochs'][0]['first_sequence'],273);self.assertEqual(row['interest_trace']['message_values'],[]);self.assertTrue(row['checked_export']['supplied_export_chain_complete'])
    def test_each_interest_stops_before_third_and_survives_after_off(self):
        for n,v in self.r['interest_failures'].items():
            self.assertEqual(self.r['matrix'][n]['calls']['iso_submissions'],0 if n=='interest-open' else 2);self.assertIsNotNone(v['after_operator_off']);self.assertFalse(v['overall_success'])
    def test_preparation_interest_survives_without_driver(self):
        p=self.r['interest_failures']['interest-open'];self.assertEqual(p['failure_stage'],'provider_preparation');self.assertEqual(p['initial_trace']['message_values'],[99]);self.assertEqual(p['after_operator_off']['message_values'],[99])
    def test_failed_supplement_and_changed_prefix_refused(self):
        self.assertIn('after-off-prefix',self.r['rejections'])
    def test_history_and_old_scope_rejected(self):
        for n in ('old225-scope','count32-reservation','frozen-spent225'):self.assertEqual(self.r['matrix'][n]['calls']['opens'],0)
        for n in ('spent225-drift','spent225-extra','spent225-missing'):self.assertEqual(self.r['matrix'][n]['calls']['iso_submissions'],0)
    def test_before_third_source_change_stops(self):self.assertEqual(self.r['matrix']['between-third-source']['calls']['iso_submissions'],2)
    def test_trace_unknown_uint32_is_preserved_and_bool_count_rejected(self):
        trace=copy.deepcopy(self.r['matrix']['interest-close']['entry']['driver']['lease']['interest_trace']);self.assertEqual(flow.validate_trace(trace)['message_values'],[0xe0005003]);trace['claimed']=True
        with self.assertRaises(ValueError):flow.validate_trace(trace)
    def test_incomplete_trace_is_diagnostic_only(self):
        trace=copy.deepcopy(self.r['matrix']['interest-close']['entry']['driver']['lease']['interest_trace']);trace.update(committed=0,pending=1,rows=[],complete=False)
        self.assertFalse(flow.validate_trace(trace)['complete_observed_prefix'])
        with self.assertRaises(ValueError):flow.validate_trace(trace,success=True)
    def test_replay_and_no_hardware(self):
        self.assertEqual(len(self.r['replay_rejections']),7);self.assertEqual(self.r['source_count'],636)
        for k in ('formal_reservations','new_authorizations','real_sdk_objects','usb_requests','sd_accesses','remaining'):self.assertEqual(self.r[k],0)

class Dimensions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['A23_SHORT128_REVIEW']);b.core.verify_seal(cls.root);cls.r=b.w.load(cls.root/'report.json')
    def test_owner_and_lease_reject_dimension_mixing(self):
        for n,row in self.r['matrix'].items():
            if n.startswith(('owner-','lease-count-')):
                self.assertTrue(row['probe_rejected']);self.assertEqual(row['calls']['iso_submissions'],0)
                self.assertEqual(row['calls']['opens'],1 if n.startswith('lease-count-') else 0)
    def test_tail_slot_127_retained_and_960_sizes_rejected(self):
        row=self.r['accepted']['tail128'];self.assertEqual(row['sdk']['epochs'][2]['effective_slots'],list(range(112,128)))
        for n in ('raw960','rows960','old103-build-consumer'):self.assertIn(n,self.r['rejections'])
    def test_malformed_payload_never_starts_next_epoch(self):
        for n in ('packet15','packet17','row-error','duplicate-iso','foreign-pointer'):
            self.assertEqual(self.r['matrix'][n]['calls']['iso_submissions'],1)

if __name__=='__main__':unittest.main()
