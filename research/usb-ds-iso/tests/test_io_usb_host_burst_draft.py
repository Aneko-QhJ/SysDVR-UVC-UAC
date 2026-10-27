import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from io_usb_host_burst_draft import PLAN,validate_plan,trigger_decision,lifecycle_disposition,assess_candidate


class BurstDraftTests(unittest.TestCase):
    def decision(self,**changes):
        args=dict(query_ns=2000000,age_ns=16000000,enqueue_ns=8000000,gap_ns=8000000,
                  before_valid=True,enqueue_accepted=True,owner_pending=True,journal_ok=True,
                  interrupted=False,detached=False,previous_triggers=0)
        args.update(changes);return trigger_decision(**args)

    def test_budget_boundary_leaves_only_assumed_reserve(self):
        r=self.decision();self.assertTrue(r['model_trigger_allowed'])
        self.assertEqual(r['projected_trigger_end_age_ns'],48000000)
        self.assertFalse(r['hardware_entry_enabled']);self.assertFalse(r['allow_next_burst'])
        self.assertFalse(self.decision(age_ns=1999999)['model_trigger_allowed'])
        for key in ['query_ns','age_ns','enqueue_ns','gap_ns']:
            value={'query_ns':2000000,'age_ns':16000000,'enqueue_ns':8000000,'gap_ns':8000000}[key]
            self.assertFalse(self.decision(**{key:value+1})['model_trigger_allowed'])

    def test_inline_completion_failed_enqueue_and_ambiguous_previous_attempt_stop_trigger(self):
        for changes in [dict(owner_pending=False),dict(enqueue_accepted=False),dict(previous_triggers=1),
                        dict(before_valid=False),dict(journal_ok=False),dict(interrupted=True),dict(detached=True)]:
            self.assertFalse(self.decision(**changes)['model_trigger_allowed'])
        for changes in [dict(gap_ns=True),dict(query_ns=-1),dict(previous_triggers=2),dict(owner_pending=1)]:
            with self.assertRaises(ValueError):self.decision(**changes)

    def life(self,state,**changes):
        args=dict(committed=False,pointer_matches=True,detached=False,abort_attempts=0,journal_ok=True)
        args.update(changes);return lifecycle_disposition(state,**args)

    def test_pending_abort_once_is_not_release_or_retry(self):
        self.assertEqual(self.life('pending')['model_action'],'abort_once_then_wait')
        for changes in [dict(abort_attempts=1),dict(detached=True),dict(pointer_matches=False),dict(journal_ok=False)]:
            r=self.life('pending',**changes);self.assertFalse(r['may_close_host']);self.assertFalse(r['may_request_host_abort'])
            self.assertFalse(r['may_cancel_device']);self.assertFalse(r['may_resubmit'])

    def test_own_completion_requires_commit_and_never_cancels_completed_request(self):
        self.assertFalse(self.life('completed')['may_close_host'])
        for state in ['completed','rejected']:
            r=self.life(state,committed=True);self.assertTrue(r['may_close_host'])
            self.assertFalse(r['may_request_host_abort']);self.assertFalse(r['callback_drain_verified'])
        self.assertFalse(self.life('completed',committed=True,pointer_matches=False)['may_close_host'])
        self.assertFalse(self.life('retained',committed=True)['may_close_host'])

    def test_iso_completion_cannot_close_an_interface_with_control_completion_pending(self):
        r=self.life('completed',committed=True,control_pending=True)
        self.assertFalse(r['may_close_host']);self.assertFalse(r['may_request_host_abort'])
        self.assertEqual(r['model_action'],'retain_wait')
        self.assertFalse(self.life('prepared',control_pending=True)['may_close_host'])

    def test_plan_cannot_enable_hardware_repeat_or_normalize_empty_errors(self):
        validate_plan(PLAN)
        for key,value in [('hardware_entry_enabled',True),('execution_mode','hardware'),('max_submissions',2),
                          ('max_device_triggers',True),('repeat',1),('allow_next_burst',True)]:
            plan=copy.deepcopy(PLAN);plan[key]=value
            with self.assertRaises(ValueError):validate_plan(plan)
        plan=copy.deepcopy(PLAN);plan['empty_rule']['expected_status_u32']=0xe00002e7
        with self.assertRaises(ValueError):validate_plan(plan)


class BurstCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('A23_SIMULATION_BUNDLES')
        if not value:raise unittest.SkipTest('set A23_SIMULATION_BUNDLES; candidates are mocks only')
        cls.fixture=Path(value)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'bundle';shutil.copytree(self.fixture/'clean',self.root)
        self.original=(self.root/'transactions.bin').read_bytes()
        self.rows=[list(r) for r in struct.iter_unpack('<IIIIQI',self.original)]
        for row in self.rows:
            if row[3]==0:row[0]=0
        # Generate a new sequence-1 mock payload; do not relabel the old bytes.
        raw=bytearray(len((self.root/'raw.bin').read_bytes()))
        active=[i for i,r in enumerate(self.rows) if r[3]]
        for ordinal,i in enumerate(active,1):
            packet=b'ISO1'+struct.pack('<H',ordinal)+bytes(
                (j ^ ordinal ^ (ordinal>>8)) & 255 for j in range(6,192))
            raw[i*192:(i+1)*192]=packet
        (self.root/'raw.bin').write_bytes(raw)
        meta=json.loads((self.root/'metadata.json').read_text());meta['scenario']=copy.deepcopy(PLAN['scenario'])
        (self.root/'metadata.json').write_text(json.dumps(meta))
        self.save()

    def save(self):
        (self.root/'transactions.bin').write_bytes(b''.join(struct.pack('<IIIIQI',*r) for r in self.rows))
        sums=''.join(f'{hashlib.sha256((self.root/name).read_bytes()).hexdigest()}  {name}\n'
                     for name in ['raw.bin','transactions.bin','metadata.json'])
        (self.root/'SHA256SUMS').write_text(sums);(self.root/'COMMITTED').write_text(hashlib.sha256(sums.encode()).hexdigest()+'\n')

    def test_correct_mock_payload_and_zero_empty_slots_do_not_grant_hardware(self):
        r=assess_candidate(self.root);self.assertTrue(r['candidate_rule_matches'])
        self.assertEqual(len(r['active_indices']),16);self.assertEqual(r['empty_status_counts'],{'0x00000000':944})
        for key in ['hardware_verified','usb_strict_pass','baseline_accepted','allow_next_burst','device_relation_verified',
                    'empty_status_policy_verified','trigger_journal_binding_verified']:self.assertIs(r[key],False)

    def test_empty_error_is_preserved_separately_from_correct_payload(self):
        i=next(i for i,r in enumerate(self.rows) if r[3]==0)
        for status in [0xe00002e7,0xe000400e,0xe0000001,0xdeadbeef]:
            self.rows[i][0]=status;self.save();r=assess_candidate(self.root)
            self.assertTrue(r['payload_matches']);self.assertFalse(r['candidate_rule_matches'])
            self.assertIn(f'0x{status:08x}',r['empty_status_counts'])

    def test_correct_bytes_cannot_override_active_status_or_overall_error(self):
        i=next(i for i,r in enumerate(self.rows) if r[3]);self.rows[i][0]=0xe00002bd;self.save()
        r=assess_candidate(self.root);self.assertTrue(r['payload_matches']);self.assertIn('active_native_error',r['failure_reasons'])
        self.rows[i][0]=0;meta=json.loads((self.root/'metadata.json').read_text());meta['overall_u32']=0xe00002bd
        (self.root/'metadata.json').write_text(json.dumps(meta));self.save();r=assess_candidate(self.root)
        self.assertTrue(r['payload_matches']);self.assertIn('callback_or_overall_error',r['failure_reasons'])

    def test_extra_packet_and_raw_outside_actual_slots_do_not_match(self):
        empty=next(i for i,r in enumerate(self.rows) if r[3]==0);self.rows[empty][3]=1;self.save()
        self.assertFalse(assess_candidate(self.root)['payload_matches'])
        self.rows[empty][3]=0;raw=bytearray((self.root/'raw.bin').read_bytes());raw[empty*192]=1
        (self.root/'raw.bin').write_bytes(raw);self.save();self.assertFalse(assess_candidate(self.root)['payload_matches'])

    def test_wrong_scenario_and_hardware_relabeling_are_rejected(self):
        path=self.root/'metadata.json';original=json.loads(path.read_text())
        for changed in [dict(original,scenario={'kind':'no_td'}),dict(original,execution_mode='hardware'),
                        dict(original,scenario={'kind':'single_burst','first_sequence':2})]:
            path.write_text(json.dumps(changed));self.save()
            with self.assertRaises(ValueError):assess_candidate(self.root)


if __name__=='__main__':unittest.main()
