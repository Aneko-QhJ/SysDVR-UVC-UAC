import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_io_usb_host_session import analyze
from analyze_io_usb_host_no_td import analyze as no_td
from io_usb_host_probe_plan import NO_TD_PLAN, RUNTIME_PLAN, validate_plan
from io_usb_host_runtime_policy import duration_ns


class RuntimePolicyTests(unittest.TestCase):
    def test_exact_integer_conversion_boundaries(self):
        self.assertEqual(duration_ns(0,1,125,3),42)
        self.assertEqual(duration_ns(0,2,125,3),84)
        self.assertEqual(duration_ns(0,2**64-1,2**32-1,2**32-1),2**64-1)
        for args in ((0,2**64-1,2,1),(2,1,1,1),(0,1,0,1),(0,1,1,0),
                     (False,1,1,1),(0,1,True,1),(0,1,1.0,1),(0,2**64,1,1)):
            self.assertIsNone(duration_ns(*args))

    def test_new_plan_is_fixed_and_old_plan_remains_readable(self):
        validate_plan(NO_TD_PLAN); validate_plan(RUNTIME_PLAN)
        for field,value in (('max_frame_age_ns',16000001),('max_frame_query_ns',True),
                            ('max_enqueue_call_ns',8000000.0),('exit_grace_ns',0),
                            ('hardware_timing_verified',True),('reserve_ns',0)):
            plan=copy.deepcopy(RUNTIME_PLAN); plan['runtime_budget'][field]=value
            with self.assertRaises(ValueError): validate_plan(plan)


class RuntimeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=os.environ.get('A23_RUNTIME_FIXTURES')
        if not root: raise unittest.SkipTest('set A23_RUNTIME_FIXTURES for native runtime integration')
        cls.fixture=Path(root); cls.sessions=cls.fixture/'runtime-final'

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.journal=Path(self.temp.name)/'session.jsonl'
        self.bundle=Path(self.temp.name)/'transfer'
        self.journal.write_bytes((self.sessions/'clean.jsonl').read_bytes())
        shutil.copytree(self.sessions/'clean',self.bundle)

    def rows(self,name='clean'):
        return [json.loads(line) for line in (self.sessions/(name+'.jsonl')).read_bytes().splitlines()]

    def write(self,rows):
        for i,row in enumerate(rows,1): row['index']=i
        self.journal.write_text(''.join(json.dumps(row)+'\n' for row in rows))

    def detail(self,rows,event):
        return next(r['details'] for r in rows if r['event']==event)

    def result(self,name):
        bundle=self.sessions/name
        return analyze(self.sessions/(name+'.jsonl'),bundle if bundle.is_dir() else None)

    def test_all_eleven_native_journals_bind_exact_runtime_plan(self):
        journals=list(self.sessions.glob('*.jsonl')); self.assertEqual(len(journals),11)
        for path in journals:
            self.assertEqual(self.rows(path.stem)[0]['details']['probe_plan'],RUNTIME_PLAN)
            r=self.result(path.stem)
            self.assertTrue(r['runtime_budget_bound'])
            self.assertEqual(r['simulation_session_pass'],path.stem in {'clean','exit-after-save'})
            self.assertFalse(r['hardware_verified']); self.assertFalse(r['callback_drain_verified'])

    def test_c_timebase_vectors_match_independent_python(self):
        rows=json.loads((self.sessions/'math-vectors.json').read_text()); self.assertEqual(len(rows),9)
        for r in rows:
            value=duration_ns(0,r['ticks'],r['numerator'],r['denominator'])
            self.assertEqual(r['converted'],value is not None)
            self.assertEqual(r['ns'],value or 0)

    def test_stale_journal_and_slow_query_never_forward_or_fabricate_callback(self):
        for name in ('stale-after-journal','slow-frame-query'):
            r=self.result(name); a=r['admission']
            self.assertFalse(a['forwarded']); self.assertFalse(a['accepted'])
            self.assertEqual(r['callbacks'],0); self.assertTrue(r['resources_closed'])
            meta=json.loads((self.sessions/name/'metadata.json').read_text())
            self.assertEqual(meta['owner_state'],5); self.assertNotIn('overall_u32',meta)
            self.assertEqual(meta['callback_arrival_ticks'],0)
        self.assertGreater(self.result('stale-after-journal')['admission']['age_ns'],16000000)
        self.assertGreater(self.result('slow-frame-query')['admission']['query_ns'],2000000)

    def test_slow_sdk_call_is_accepted_but_stops_and_aborts_once(self):
        r=self.result('slow-enqueue'); a=r['admission']
        self.assertTrue(a['accepted']); self.assertTrue(a['forwarded']); self.assertFalse(a['budget_pass'])
        self.assertGreater(a['call_ns'],8000000); self.assertEqual(r['abort_requests'],1)
        self.assertIn('enqueue_budget_exceeded',r['stop_reasons']); self.assertFalse(r['simulation_session_pass'])

    def test_pending_exit_keeps_resources_and_has_at_most_one_abort(self):
        for name in ('exit-pending','exit-abort-refused','exit-after-deadline','exit-detached'):
            rows=self.rows(name); r=self.result(name); expiry=self.detail(rows,'exit_wait_expired')
            self.assertTrue(expiry['storage_retained']); self.assertTrue(expiry['resources_retained'])
            self.assertEqual(r['abort_requests'],int(name!='exit-detached'))
            self.assertFalse(r['resources_closed']); self.assertEqual(r['callbacks'],0)
            self.assertEqual(len([x for x in rows if x['event']=='exit_requested']),1)
            if name!='exit-abort-refused': self.assertGreaterEqual(expiry['elapsed_ns'],1000000000)

    def test_unsubmitted_exit_closes_without_abort(self):
        r=self.result('exit-ready')
        self.assertTrue(r['resources_closed']); self.assertTrue(r['exit_requested'])
        self.assertFalse(r['exit_wait_expired']); self.assertEqual(r['submissions'],0); self.assertEqual(r['abort_requests'],0)

    def test_saved_exit_remains_clean_and_late_recovery_remains_failed(self):
        r=self.result('exit-after-save')
        self.assertTrue(r['simulation_session_pass']); self.assertEqual(r['stop_reasons'],[])
        r=self.result('late-after-expiry')
        self.assertTrue(r['resources_closed']); self.assertEqual(r['callbacks'],1)
        self.assertTrue(r['exit_wait_expired']); self.assertFalse(r['simulation_session_pass'])

    def test_four_collections_convert_timebase_without_accepting_native_baseline(self):
        roots=list((self.fixture/'runtime-collections-final').iterdir()); self.assertEqual(len(roots),4)
        for root in roots:
            r=no_td(root); self.assertTrue(r['frame_timebase_converted'])
            self.assertEqual(r['observation_complete'],root.name in {'clean','exit-after-save'})
            for key in ('software_frame_freshness_verified','hardware_verified','hardware_entry_enabled',
                        'baseline_accepted','allow_next_burst','usb_strict_pass','empty_status_policy_verified'):
                self.assertIs(r[key],False)

    def test_recomputed_admission_values_and_types_rejected(self):
        for field,value in (('age_ns',0),('query_ns',999),('call_ns',999),('budget_pass',False),
                            ('forwarded',False),('admitted',False),('accepted',False),('source','sdk_runtime_budget'),
                            ('age_ns',False),('converted',1),('duration_valid',False)):
            rows=self.rows(); self.detail(rows,'admission_checked')[field]=value; self.write(rows)
            with self.assertRaises(ValueError): analyze(self.journal,self.bundle)

    def test_frame_and_admission_timebase_mismatch_rejected(self):
        for event,field,value in (('frame_sample','timebase_numerator',0),
                                  ('admission_checked','timebase_denominator',True),
                                  ('admission_checked','timebase_numerator',1),
                                  ('admission_checked','check_ticks',1)):
            rows=self.rows(); self.detail(rows,event)[field]=value; self.write(rows)
            with self.assertRaises(ValueError): analyze(self.journal,self.bundle)

    def test_missing_or_repeated_admission_rejected(self):
        rows=self.rows(); self.write([r for r in rows if r['event']!='admission_checked'])
        with self.assertRaises(ValueError): analyze(self.journal,self.bundle)
        rows=self.rows(); i=next(i for i,r in enumerate(rows) if r['event']=='admission_checked')
        rows.insert(i,copy.deepcopy(rows[i])); self.write(rows)
        with self.assertRaises(ValueError): analyze(self.journal,self.bundle)

    def test_early_exit_expiry_or_false_retention_rejected(self):
        for field,value in (('storage_retained',False),('resources_retained',False),('converted',False),('elapsed_ns',0)):
            rows=self.rows('exit-pending'); self.detail(rows,'exit_wait_expired')[field]=value; self.write(rows)
            with self.assertRaises(ValueError): analyze(self.journal)
        rows=self.rows('exit-pending'); begin=self.detail(rows,'exit_requested')['begin_ticks']
        self.detail(rows,'exit_wait_expired').update(check_ticks=begin,elapsed_ns=0); self.write(rows)
        with self.assertRaises(ValueError): analyze(self.journal)

    def test_exit_requires_one_request_and_original_clock(self):
        rows=self.rows('exit-pending'); self.write([r for r in rows if r['event']!='exit_requested'])
        with self.assertRaises(ValueError): analyze(self.journal)
        rows=self.rows('exit-pending'); i=next(i for i,r in enumerate(rows) if r['event']=='exit_requested')
        rows.insert(i,copy.deepcopy(rows[i])); self.write(rows)
        with self.assertRaises(ValueError): analyze(self.journal)
        rows=self.rows('exit-pending'); self.detail(rows,'exit_requested')['timebase_numerator']=1; self.write(rows)
        with self.assertRaises(ValueError): analyze(self.journal)

    def test_pending_cannot_be_rehashed_as_closed(self):
        rows=self.rows('exit-pending')
        for event in ('resources_closing','resources_closed'):
            row=copy.deepcopy(rows[-1]); row.update(event=event,details={}); rows.append(row)
        self.write(rows)
        with self.assertRaisesRegex(ValueError,'pending'): analyze(self.journal)

    def test_native_time_binding_survives_rehashed_bundle(self):
        path=self.bundle/'metadata.json'; meta=json.loads(path.read_text())
        meta['submit_begin_ticks']=self.detail(self.rows(),'admission_checked')['check_ticks']+1
        path.write_text(json.dumps(meta)+'\n')
        raw=''.join(f'{hashlib.sha256((self.bundle/k).read_bytes()).hexdigest()}  {k}\n' for k in
                    ('raw.bin','transactions.bin','metadata.json')).encode()
        (self.bundle/'SHA256SUMS').write_bytes(raw); (self.bundle/'COMMITTED').write_text(hashlib.sha256(raw).hexdigest()+'\n')
        rows=self.rows(); self.detail(rows,'bundle_committed')['manifest_sha256']=hashlib.sha256(raw).hexdigest(); self.write(rows)
        with self.assertRaisesRegex(ValueError,'time mismatch'): analyze(self.journal,self.bundle)


if __name__=='__main__': unittest.main()
