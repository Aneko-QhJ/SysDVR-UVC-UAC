import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_io_usb_host_no_td import analyze, control_trace
from analyze_io_usb_host_session import analyze as analyze_session
from analyze_io_usb_host_collection import LIMITS
from io_usb_host_probe_plan import NO_TD_PLAN, validate_plan


class NoTDPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.environ.get('A23_NO_TD_FIXTURES')
        if not root: raise unittest.SkipTest('set A23_NO_TD_FIXTURES for fixed-plan integration')
        cls.fixture = Path(root)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'collection'
        shutil.copytree(self.fixture/'collections/clean-underrun',self.root)

    def seal_bundle(self):
        root = self.root/'transfer'
        raw = ''.join(f'{hashlib.sha256((root/k).read_bytes()).hexdigest()}  {k}\n' for k in ('raw.bin','transactions.bin','metadata.json')).encode()
        (root/'SHA256SUMS').write_bytes(raw);(root/'COMMITTED').write_text(hashlib.sha256(raw).hexdigest()+'\n')

    def reseal(self):
        meta_path = self.root/'collection.json'; meta = json.loads(meta_path.read_text())
        for field,name in [('journal_sha256','session.jsonl'),('transfer_manifest_sha256','transfer/SHA256SUMS'),('device_log_sha256','device-log.txt')]:
            meta[field] = hashlib.sha256((self.root/name).read_bytes()).hexdigest()
        meta_path.write_text(json.dumps(meta)+'\n')
        raw = ''.join(f'{hashlib.sha256((self.root/k).read_bytes()).hexdigest()}  {k}\n' for k in sorted(LIMITS)).encode()
        (self.root/'SHA256SUMS').write_bytes(raw); (self.root/'COMMITTED').write_text(hashlib.sha256(raw).hexdigest()+'\n')

    def rows(self):
        return [json.loads(line) for line in (self.root/'session.jsonl').read_text().splitlines()]

    def write_rows(self,rows):
        for index,row in enumerate(rows,1): row['index'] = index
        (self.root/'session.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows)); self.reseal()

    def frame_change(self,field,value):
        rows = self.rows(); next(r['details'] for r in rows if r['event']=='frame_sample')[field]=value; self.write_rows(rows)

    def test_fixed_plan_rejects_changes_and_numeric_substitution(self):
        validate_plan(NO_TD_PLAN)
        for key,value in [('execution_mode','hardware'),('hardware_entry_enabled',True),('repeat',1),('max_submissions',2),
                          ('max_device_triggers',1),('max_async_aborts',2),('first_frame_lead',63),
                          ('transfer_options',False),('hardware_verified',0),('first_frame_lead',64.0)]:
            plan = copy.deepcopy(NO_TD_PLAN); plan[key]=value
            with self.assertRaises(ValueError): validate_plan(plan)
        plan = copy.deepcopy(NO_TD_PLAN); plan['scenario']['first_sequence']=1
        with self.assertRaises(ValueError): validate_plan(plan)

    def test_c_and_python_plans_match_in_all_eighteen_sessions(self):
        journals = sorted((self.fixture/'final-sessions/no-td').glob('*.jsonl')); self.assertEqual(len(journals),18)
        for journal in journals:
            plan = json.loads(journal.read_text().splitlines()[0])['details']['probe_plan']; validate_plan(plan)
            bundle=journal.parent/journal.stem
            result = analyze_session(journal,bundle if bundle.is_dir() else None)
            self.assertTrue(result['probe_plan_bound']); self.assertEqual(result['submissions'],int(journal.stem not in
                {'missing-frame','bad-frame','wrong-frame'}))
            if journal.stem=='missing-callback':
                self.assertEqual(result['callbacks'],0); self.assertFalse(result['resources_closed'])
            if journal.stem=='missing-after': self.assertFalse(result['resources_closed'])
            if journal.stem.startswith('timeout-'): self.assertEqual(result['abort_requests'],1)
            if journal.stem=='detach-pending': self.assertEqual(result['abort_requests'],0)

    def test_all_thirteen_collections_observe_four_distributions_without_accepting(self):
        roots = sorted((self.fixture/'collections').iterdir());self.assertEqual(len(roots),13)
        for root in roots:
            result=analyze(root)
            self.assertEqual(result['observation_complete'],root.name in {'clean-underrun','all-zero','mixed-status','unknown-status'})
            for key in ('baseline_accepted','allow_next_burst','hardware_entry_enabled','hardware_verified','usb_strict_pass',
                        'empty_status_policy_verified','callback_drain_verified','root_cause_confirmed'):
                self.assertIs(result[key],False)
            self.assertIs(result['software_frame_freshness_verified'],False)
            self.assertGreaterEqual(result['frame_end_to_native_submit_ticks'],0)

    def test_mixed_prefix_and_original_unknown_status_preserved(self):
        result=analyze(self.fixture/'collections/mixed-status')
        self.assertEqual(result['empty_status_counts'],{'0xe000400e':271,'0xe00002e7':689})
        self.assertEqual(result['initial_empty_span'],dict(first_index=0,last_index=270,count=271,status_u32_hex='0xe000400e'))
        self.assertEqual(len(result['empty_status_spans']),2)
        unknown=analyze(self.fixture/'collections/unknown-status')
        self.assertEqual(unknown['empty_status_counts'],{'0xdeadbeef':960})
        self.assertEqual(unknown['empty_native_policy'],'unverified')

    def test_raw_active_overall_invalid_and_timeout_do_not_pass_observation(self):
        for name in ('stray-raw','unexpected-data','native-error','invalid-row','timeout-accepted','timeout-rejected',
                     'scenario-mismatch','detach-pending','late-after-close'):
            result=analyze(self.fixture/'collections'/name)
            self.assertFalse(result['observation_complete']); self.assertTrue(result['failure_reasons'])
        self.assertEqual(analyze(self.fixture/'collections/unexpected-data')['active_indices'],[522])

    def test_header_stays_fresh_while_live_diagnostic_changes(self):
        before=(self.root/'status-before.bin').read_bytes(); after=(self.root/'status-after.bin').read_bytes()
        self.assertEqual(before[:56],after[:56]);self.assertNotEqual(before[56:],after[56:])
        self.assertTrue(analyze(self.root)['status_header_unchanged'])

    def test_control_trace_rejects_burst_cancel_frames_unknown_and_wrong_tuple(self):
        raw=(self.root/'device-log.txt').read_bytes()
        self.assertTrue(control_trace(raw)['matches_fixed_plan'])
        for replacement in (b'req=0x50',b'req=0x52',b'req=0x53',b'req=0x54',b'req=0x55',b'req=0x51 wVal=0x0001'):
            value=raw.replace(b'req=0x51',replacement,1)
            self.assertFalse(control_trace(value)['matches_fixed_plan'])
        for old,new in ((b'reqType=0xc1',b'reqType=0x41'),(b'wIdx=0x0002',b'wIdx=0x0003'),(b'wLen=168',b'wLen=167')):
            self.assertFalse(control_trace(raw.replace(old,new,1))['matches_fixed_plan'])

    def test_missing_duplicate_or_malformed_control_trace_is_failure_evidence(self):
        original=(self.root/'device-log.txt').read_bytes()
        line=next(x for x in original.splitlines(keepends=True) if x.startswith(b'EP0[0]'))
        for raw in (original.replace(line,b''),original+line,original.replace(b'req=0x51',b'req=oops',1)):
            (self.root/'device-log.txt').write_bytes(raw); self.reseal()
            result=analyze(self.root);self.assertFalse(result['observation_complete'])
            self.assertFalse(result['allow_next_burst'])

    def test_frame_field_type_identity_overflow_and_lead_rejected(self):
        original=self.rows()
        for field,value in [('current_frame',True),('current_frame',2**64-64),('first_frame',101),('frame_lead',63),
                            ('source','sdk_frame_number'),('begin_ticks',1),('end_ticks',1)]:
            self.write_rows(copy.deepcopy(original));self.frame_change(field,value)
            with self.assertRaises(ValueError): analyze(self.root)

    def test_missing_and_duplicate_frame_events_rejected(self):
        original=self.rows()
        self.write_rows([r for r in original if r['event']!='frame_sample'])
        with self.assertRaisesRegex(ValueError,'planned frame'): analyze(self.root)
        rows=copy.deepcopy(original); index=next(i for i,r in enumerate(rows) if r['event']=='frame_sample')
        rows.insert(index,copy.deepcopy(rows[index]));self.write_rows(rows)
        with self.assertRaisesRegex(ValueError,'repeated frame'): analyze(self.root)

    def test_rehashed_plan_and_scenario_swapping_rejected(self):
        rows=self.rows(); rows[0]['details']['probe_plan']['repeat']=1; self.write_rows(rows)
        with self.assertRaisesRegex(ValueError,'changed no-TD plan'): analyze(self.root)

    def test_native_callback_time_must_match_journal(self):
        path=self.root/'transfer/metadata.json';meta=json.loads(path.read_text());meta['callback_arrival_ticks']+=1
        path.write_text(json.dumps(meta));self.seal_bundle()
        rows=self.rows();next(r['details'] for r in rows if r['event']=='bundle_committed')['manifest_sha256']=hashlib.sha256((self.root/'transfer/SHA256SUMS').read_bytes()).hexdigest()
        self.write_rows(rows)
        with self.assertRaisesRegex(ValueError,'native/journal time'): analyze(self.root)

    def test_submit_cannot_relabel_frame_even_with_hashes_recomputed(self):
        rows=self.rows();next(r['details'] for r in rows if r['event']=='submit_begin')['first_frame']=101;self.write_rows(rows)
        with self.assertRaisesRegex(ValueError,'planned frame'): analyze(self.root)

    def test_prior_frozen_burst_mock_is_not_new_no_td_baseline(self):
        root=Path(__file__).resolve().parents[1]/'private/analysis/A23-IOUSBHost-sdk-binding-review-20261012/collections/clean'
        if not root.exists(): self.skipTest('local frozen previous inputs unavailable')
        with self.assertRaisesRegex(ValueError,'not a no-TD'): analyze(root)


if __name__=='__main__': unittest.main()
