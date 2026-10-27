import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_io_usb_host_burst_executor import analyze,PLAN


class BurstExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('A23_BURST_EXECUTOR_FIXTURES')
        if not value:raise unittest.SkipTest('set A23_BURST_EXECUTOR_FIXTURES; injected native cases only')
        cls.fixtures=Path(value)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'case'

    def use(self,name='iso-first'):
        if self.root.exists():shutil.rmtree(self.root)
        shutil.copytree(self.fixtures/name,self.root)
        self.rows=[json.loads(s) for s in (self.root/'journal.jsonl').read_text().splitlines()]
        self.result=json.loads((self.root/'result.json').read_text())

    def save(self):
        (self.root/'journal.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in self.rows))
        (self.root/'result.json').write_text(json.dumps(self.result))

    def detail(self,event):return next(r['details'] for r in self.rows if r['event']==event)

    def test_all_22_transcripts_bind_only_three_clean_model_executions(self):
        dirs=sorted(p for p in self.fixtures.iterdir() if p.is_dir());self.assertEqual(len(dirs),22)
        completed=[]
        for path in dirs:
            r=analyze(path)
            if r['simulation_execution_complete']:completed.append(path.name)
            for key in ['hardware_verified','usb_strict_pass','baseline_accepted','allow_next_burst',
                        'device_log_bound','hardware_trigger_binding_verified','callback_drain_verified']:
                self.assertIs(r[key],False)
            for key in ['trigger_attempts','host_aborts']:self.assertLessEqual(r['result'][key],1)
        self.assertEqual(completed,['control-first','inline-control','iso-first'])

    def test_ingress_arrival_blocks_trigger_before_owner_handler_runs(self):
        for name in ['inline-iso','arrival-during-intent']:
            r=analyze(self.fixtures/name)
            self.assertEqual(r['result']['trigger_attempts'],0);self.assertEqual(r['result']['host_aborts'],0)
            self.assertEqual(r['result']['iso_callbacks'],1)
            self.assertFalse(r['simulation_execution_complete'])

    def test_control_deadline_is_sticky_even_after_successful_late_callback(self):
        for name in ['control-pending','control-late']:
            r=analyze(self.fixtures/name)
            self.assertTrue(r['result']['saved']);self.assertTrue(r['result']['closed'])
            self.assertIn('control_deadline_observed',r['result']['failure_reasons'])
            self.assertFalse(r['simulation_execution_complete'])
        self.use('control-late');self.result['failure_reasons']=[];self.save()
        with self.assertRaisesRegex(ValueError,'failures'):analyze(self.root)

    def test_foreign_pointer_and_failed_save_retain_owner(self):
        for name in ['foreign-pointer','save-failed','iso-pending','abort-refused','detach-pending']:
            r=analyze(self.fixtures/name)
            self.assertFalse(r['result']['closed']);self.assertTrue(r['result']['storage_retained'])
            self.assertFalse(r['simulation_execution_complete'])
        self.assertEqual(analyze(self.fixtures/'detach-pending')['result']['host_aborts'],0)

    def test_trigger_tuple_and_budget_are_not_reporter_assertions(self):
        for key,value in [('request',0x50),('value',2),('timeout_ns',17000000),('gap_ns',8000001),('age_ns',32000001)]:
            self.use();self.detail('trigger_return')[key]=value;self.save()
            with self.assertRaises(ValueError):analyze(self.root)

    def test_snapshot_and_native_callback_bind_saved_bytes(self):
        for event,key,value in [('iso_snapshot','raw_sha256','0'*64),('iso_snapshot','transactions_sha256','0'*64),
                                ('bundle_committed','manifest_sha256','0'*64),('iso_begin','first_frame',101),
                                ('iso_callback','arrival_ticks',1),('iso_callback','status_u32',0xe00002e7)]:
            self.use();self.detail(event)[key]=value;self.save()
            with self.assertRaises(ValueError):analyze(self.root)
        self.use();p=self.root/'transfer/raw.bin';raw=bytearray(p.read_bytes());raw[512*192]^=1;p.write_bytes(raw)
        with self.assertRaises(ValueError):analyze(self.root)

    def test_close_requires_control_completion_and_commit(self):
        self.use();close=next(r for r in self.rows if r['event']=='close_begin');self.rows.remove(close)
        index=next(i for i,r in enumerate(self.rows) if r['event']=='control_callback')
        self.rows.insert(index,close)
        for i,r in enumerate(self.rows,1):r['index']=i;r['ticks']=self.rows[0]['ticks']+i*100000
        # Preserve all pre-trigger timestamps so the relevant rejection is close ordering.
        original=[json.loads(s) for s in (self.fixtures/'iso-first/journal.jsonl').read_text().splitlines()]
        for i in range(6):self.rows[i]=copy.deepcopy(original[i])
        for i in range(6,len(self.rows)):self.rows[i]['ticks']=self.rows[5]['ticks']+(i-5)*100000
        self.save()
        with self.assertRaisesRegex(ValueError,'control pending'):analyze(self.root)
        self.use();self.detail('close_begin')['prepared']=1;self.save()
        with self.assertRaisesRegex(ValueError,'invalid close'):analyze(self.root)

    def test_model_cannot_be_relabelled_hardware_or_grant_policy(self):
        for key,value in [('execution_mode','hardware'),('hardware_verified',True),('allow_next_burst',True),
                          ('trigger_attempts',True),('started',False),('control_pending',True)]:
            self.use();self.result[key]=value;self.save()
            with self.assertRaises(ValueError):analyze(self.root)
        self.use();self.detail('begin')['plan']['repeat']=1;self.save()
        with self.assertRaisesRegex(ValueError,'plan'):analyze(self.root)

    def test_partial_and_duplicate_journal_not_certified(self):
        self.use();p=self.root/'journal.jsonl';p.write_bytes(p.read_bytes().rstrip(b'\n'))
        with self.assertRaisesRegex(ValueError,'partial'):analyze(self.root)
        self.use();self.rows.append(copy.deepcopy(self.rows[-1]));self.rows[-1]['index']=len(self.rows);self.save()
        with self.assertRaisesRegex(ValueError,'repeated'):analyze(self.root)
        r=analyze(self.fixtures/'journal-trigger-failed');self.assertTrue(r['result']['journal_failed'])
        self.assertFalse(r['simulation_execution_complete']);self.assertFalse(r['result']['closed'])

    def test_plan_is_fixed_and_trigger_intent_delay_rechecked(self):
        self.use();self.assertEqual(self.detail('begin')['plan'],PLAN)
        r=analyze(self.fixtures/'gap-after-intent');self.assertEqual(r['result']['trigger_attempts'],0)
        self.assertIn('trigger_final_check_failed',r['result']['failure_reasons'])


if __name__=='__main__':unittest.main()
