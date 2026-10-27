"""Injected coordinator and independent SDK host format binding checks."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_io_usb_host_burst_sdk import analyze, checkpoint
from analyze_io_usb_host_evidence import analyze as audit_core, unique_object


def load(path):
    return json.loads(path.read_bytes(), object_pairs_hook=unique_object)


def reseal(directory, names):
    sums = ''.join(f'{hashlib.sha256((directory/name).read_bytes()).hexdigest()}  {name}\n' for name in names).encode()
    (directory/'SHA256SUMS').write_bytes(sums)
    (directory/'COMMITTED').write_text(hashlib.sha256(sums).hexdigest()+'\n')


class BurstSDKDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value = os.environ.get('A23_BURST_COORDINATOR_FIXTURES')
        if not value:
            raise unittest.SkipTest('set A23_BURST_COORDINATOR_FIXTURES; injected only')
        cls.root = Path(value)

    def case(self, name):
        root = self.root/name
        rows = [json.loads(s, object_pairs_hook=unique_object) for s in (root/'session.jsonl').read_bytes().splitlines()]
        return root, rows, load(root/'result.json'), load(root/'fixture-calls.json')

    def copy(self, name='iso-first'):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root = Path(temp.name)/'case';shutil.copytree(self.root/name, root)
        return root

    def change_checkpoint(self, root, change):
        p = root/'final/checkpoint.json';v = load(p);change(v);p.write_text(json.dumps(v))
        reseal(p.parent, ['checkpoint.json'])

    def change_rows(self, root, change):
        path = root/'session.jsonl';rows = [json.loads(s) for s in path.read_bytes().splitlines()]
        change(rows)
        path.write_text(''.join(json.dumps(s, separators=(',', ':'))+'\n' for s in rows))

    def test_34_injected_exports_bound_requests_and_leave_policy_closed(self):
        directories = sorted(self.root.iterdir());self.assertEqual(len(directories),34)
        for directory in directories:
            root, rows, result, calls = self.case(directory.name)
            self.assertIn('injection', (root/'MOCK_ONLY.txt').read_text())
            self.assertIs(calls['injected_only'], True)
            for key in ['real_sdk_calls', 'registry_calls', 'usb_requests', 'sd_accesses']:
                self.assertEqual(calls[key],0)
            for key in ['iso_submissions', 'burst_enqueues', 'host_aborts']:
                self.assertLessEqual(calls[key],1)
            self.assertLessEqual(calls['status_reads'],2)
            self.assertEqual([r['index'] for r in rows],list(range(1,len(rows)+1)))
            for key in ['hardware_entry_enabled', 'hardware_verified', 'baseline_accepted', 'allow_next_burst', 'callback_drain_verified', 'usb_strict_pass']:
                self.assertIs(result[key],False)
            if result['transport']['closed']:
                self.assertEqual(calls['destroys'],1);self.assertEqual(calls['releases'],1)
                self.assertFalse(result['transport']['storage_retained']);self.assertFalse(result['transport']['control_pending'])

    def test_independent_audit_accepts_only_five_clean_host_observations(self):
        clean = {'iso-first','control-first','inline-control','queue-delayed-control','queue-delayed-iso'}
        incomplete = {'final-save-failed','retained-save-failed'}
        for root in sorted(self.root.iterdir()):
            if root.name in incomplete:
                with self.assertRaisesRegex(ValueError,'incomplete checkpoint'):analyze(root)
                continue
            result = analyze(root)
            self.assertEqual(result['host_observation_complete'],root.name in clean)
            self.assertTrue(result['injected_fixture']);self.assertFalse(result['hardware_verified'])
            self.assertFalse(result['device_log_bound']);self.assertFalse(result['empty_status_policy_verified'])

    def test_control_pending_commits_iso_without_destroy_or_after_status(self):
        root, rows, result, calls = self.case('control-pending')
        native = audit_core(root/'transfer',burst=True)
        self.assertTrue(native['evidence_integrity_verified']);self.assertTrue(native['host_transaction_candidate'])
        self.assertFalse(native['simulation_logic_pass'])
        self.assertTrue(result['core_saved']);self.assertTrue(result['unresolved']);self.assertFalse(result['finished'])
        self.assertFalse(result['transport']['storage_retained']);self.assertTrue(result['transport']['control_pending'])
        self.assertEqual(calls['status_reads'],1);self.assertEqual(calls['destroys'],0);self.assertEqual(calls['host_aborts'],0)
        self.assertIn('control_deadline',result['failure_reasons']);self.assertTrue(checkpoint(root/'retained')['unresolved'])

    def test_late_completions_save_and_close_without_erasing_failure(self):
        for name, reason in [('control-late','control_deadline'),('iso-late','iso_deadline')]:
            root, rows, result, calls = self.case(name)
            self.assertTrue(checkpoint(root/'retained')['unresolved'])
            final = checkpoint(root/'final');self.assertTrue(final['finished']);self.assertFalse(final['unresolved'])
            self.assertIn(reason,final['failure_reasons']);self.assertEqual(final['exit_code'],1)
            self.assertTrue(result['final_checkpoint_saved']);self.assertEqual(calls['destroys'],1)
            self.assertFalse(analyze(root)['host_observation_complete'])

    def test_deadlines_abort_at_most_once_detach_does_not_abort(self):
        for name in ['iso-pending','abort-refused','iso-late','interrupted-after-iso']:
            _,_,result,calls = self.case(name);self.assertEqual(calls['host_aborts'],1)
            self.assertTrue(result['exit_requested'])
        for name in ['detach-pending','detach-completed']:
            _,_,_,calls = self.case(name);self.assertEqual(calls['host_aborts'],0)
        for name in ['foreign-pointer','save-failed','journal-trigger-failed','journal-save-failed','duplicate-iso']:
            _,_,result,calls = self.case(name);self.assertTrue(result['unresolved'])
            self.assertEqual(calls['destroys'],0);self.assertEqual(calls['releases'],0)

    def test_failure_reply_bytes_and_original_errors_are_not_rewritten(self):
        import base64
        for name,size,count in [('short-after',167,167),('overflow-after',168,169)]:
            _,rows,result,_ = self.case(name)
            detail = next(r['details']['details'] for r in rows if r['event']=='adapter' and r['details']['event']=='status_after')
            self.assertEqual(len(base64.b64decode(detail['raw_base64'],validate=True)),size)
            self.assertEqual(detail['observation']['bytes_transferred'],count)
            self.assertIn('invalid_after_observation',result['transport']['failure_reasons'])
        _,rows,_,_ = self.case('trigger-rejected')
        detail = next(r['details']['details'] for r in rows if r['event']=='adapter' and r['details']['event']=='trigger_return')
        self.assertEqual(detail['error']['code_u32'],0xe00002e2)

    def test_new_core_is_rejected_by_simulation_and_no_td_readers(self):
        root = self.root/'iso-first/transfer'
        with self.assertRaisesRegex(ValueError,'backend/schema'):audit_core(root)
        with self.assertRaisesRegex(ValueError,'backend/schema'):audit_core(root,hardware=True)
        with self.assertRaises(ValueError):audit_core(root,hardware=True,burst=True)

    def test_swapped_or_rehashed_core_identity_and_callback_are_rejected(self):
        for field,value in [('binding',{'session_id':'wrong'}),('callback_arrival_ticks',1),('first_frame',101),('callback_count_at_save',True)]:
            root=self.copy();p=root/'transfer/metadata.json';meta=load(p);meta[field]=value;p.write_text(json.dumps(meta))
            reseal(p.parent,['raw.bin','transactions.bin','metadata.json'])
            with self.assertRaises((ValueError,KeyError)):analyze(root)

    def test_descriptor_and_session_relabeling_are_rejected(self):
        for field,value in [('session_id','different'),('hardware_verified',True),('hardware_entry_enabled',True),('index',False)]:
            root=self.copy();self.change_rows(root,lambda rows:rows[0].__setitem__(field,value))
            with self.assertRaises(ValueError):analyze(root)
        root=self.copy();self.change_rows(root,lambda rows:rows[0]['details']['descriptor_base64'].__setitem__('active_interface','AA=='))
        with self.assertRaises(ValueError):analyze(root)

    def test_rehashed_checkpoint_cannot_grant_policy_erase_failures_or_fake_counts(self):
        for key,value in [('hardware_verified',True),('allow_next_burst',True),('core_saved',False),('finished',1)]:
            root=self.copy();self.change_checkpoint(root,lambda v:v.__setitem__(key,value))
            with self.assertRaises(ValueError):analyze(root)
        root=self.copy('control-late');self.change_checkpoint(root,lambda v:v.__setitem__('failure_reasons',[]))
        with self.assertRaisesRegex(ValueError,'erased failures'):analyze(root)
        root=self.copy();self.change_checkpoint(root,lambda v:v['transport'].__setitem__('iso_callbacks',2))
        with self.assertRaisesRegex(ValueError,'count mismatch'):analyze(root)

    def test_control_tuple_budget_and_queue_delay_are_independently_checked(self):
        for key,value in [('request',85),('timeout_ns',16000001),('gap_ns',8000001),('accepted',1)]:
            root=self.copy()
            def change(rows):
                row=next(r for r in rows if r['event']=='adapter' and r['details']['event']=='trigger_return')
                row['details']['details'][key]=value
            self.change_rows(root,change)
            with self.assertRaises(ValueError):analyze(root)
        self.assertTrue(analyze(self.root/'queue-delayed-control')['host_observation_complete'])
        self.assertIn('control_deadline',load(self.root/'native-control-late/result.json')['failure_reasons'])
        self.assertTrue(analyze(self.root/'queue-delayed-iso')['host_observation_complete'])
        self.assertIn('iso_deadline',load(self.root/'native-iso-late/result.json')['failure_reasons'])

    def test_partial_checkpoint_and_symlink_fail_without_claiming_provenance(self):
        root=self.copy();(root/'final/COMMITTED').write_text('0'*64+'\n')
        with self.assertRaisesRegex(ValueError,'hash/commit'):analyze(root)
        root=self.copy();p=root/'transfer/raw.bin';p.rename(root/'external.bin');p.symlink_to(root/'external.bin')
        with self.assertRaisesRegex(ValueError,'plain file'):analyze(root)

    def test_native_ingress_deadline_cannot_be_erased_with_rehashed_checkpoint(self):
        for name,reason,expected in [('native-control-late','control_deadline','late control'),('native-iso-late','iso_deadline','late ISO')]:
            root=self.copy(name)
            def change(rows):
                rows[:] = [r for r in rows if not (r['event']=='stop' and r['details']['reason']==reason)]
                for index,row in enumerate(rows,1):row['index']=index
            self.change_rows(root,change)
            self.change_checkpoint(root,lambda v:v['failure_reasons'].remove(reason))
            with self.assertRaisesRegex(ValueError,expected):analyze(root)


if __name__ == '__main__':
    unittest.main()
