import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_io_usb_host_evidence import analyze as audit_core,unique_object
from analyze_io_usb_host_session import analyze as audit_no_td
from analyze_io_usb_host_burst_executor import analyze as audit_model


class BurstSDKTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('A23_BURST_SDK_FIXTURES')
        if not value:raise unittest.SkipTest('set A23_BURST_SDK_FIXTURES; injected SDK capabilities only')
        cls.root=Path(value)

    def case(self,name):
        root=self.root/name
        load=lambda p:json.loads(p.read_bytes(),object_pairs_hook=unique_object)
        rows=[json.loads(line,object_pairs_hook=unique_object) for line in (root/'adapter.jsonl').read_bytes().splitlines()]
        return root,rows,load(root/'result.json'),load(root/'fixture-calls.json')

    def test_all_33_exports_keep_requests_bounded_and_policy_closed(self):
        dirs=sorted(p for p in self.root.iterdir() if p.is_dir());self.assertEqual(len(dirs),33)
        for directory in dirs:
            root,rows,result,calls=self.case(directory.name)
            self.assertIn('injection',(root/'MOCK_ONLY.txt').read_text())
            self.assertEqual(calls['execution_mode'],'simulation');self.assertIs(calls['injected_only'],True)
            for key in ['real_sdk_calls','registry_calls','usb_requests']:self.assertEqual(calls[key],0)
            for key in ['iso_submissions','burst_enqueues','host_aborts']:self.assertLessEqual(calls[key],1)
            self.assertLessEqual(calls['status_reads'],2)
            for key in ['iso_attempts','trigger_attempts','after_reads','host_aborts']:
                self.assertIs(type(result[key]),int);self.assertLessEqual(result[key],1)
            self.assertEqual(result['trigger_attempts'],calls['burst_enqueues']);self.assertEqual(result['host_aborts'],calls['host_aborts'])
            self.assertEqual([r['index'] for r in rows],list(range(1,len(rows)+1)))
            for row in rows:
                self.assertEqual(row['schema'],'A23-burst-sdk-adapter-event-1')
                self.assertEqual(row['backend_role'],'sdk_capability_adapter')
                self.assertIs(row['hardware_entry_enabled'],False);self.assertIs(row['hardware_verified'],False)
            for key in ['hardware_entry_enabled','hardware_verified','baseline_accepted','allow_next_burst','callback_drain_verified']:
                self.assertIs(result[key],False)
            if result['closed']:
                self.assertEqual(calls['destroys'],1);self.assertEqual(calls['releases'],1)
                self.assertFalse(result['storage_retained']);self.assertFalse(result['control_pending'])

    def test_after_status_waits_for_both_callbacks_and_raw_data_survives(self):
        for name in ['iso-first','control-first','inline-control','control-pending']:
            _,rows,result,calls=self.case(name);self.assertTrue(result['closed']);self.assertFalse(result['failure_reasons'])
            index=lambda event:next(r['index'] for r in rows if r['event']==event)
            self.assertLess(index('iso_callback'),index('after_intent'))
            self.assertLess(index('control_callback'),index('after_intent'))
            self.assertLess(index('status_after'),index('close_intent'));self.assertEqual(calls['status_reads'],2)
            close=next(r['details'] for r in rows if r['event']=='close_intent')
            self.assertIs(close['owner_acknowledged'],True);self.assertIs(close['prepared'],False)
        for name,length,count in [('short-after',167,167),('overflow-after',168,169)]:
            _,rows,result,_=self.case(name)
            d=next(r['details'] for r in rows if r['event']=='status_after')
            raw=base64.b64decode(d['raw_base64'],validate=True)
            self.assertEqual(len(raw),length);self.assertEqual(d['observation']['bytes_transferred'],count)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),d['sha256'])
            self.assertIn('invalid_after_observation',result['failure_reasons'])

    def test_control_error_and_success_with_error_never_erase_native_identity(self):
        for name in ['trigger-rejected','accepted-control-error','control-error','control-bytes']:
            _,rows,result,_=self.case(name);self.assertTrue(result['failure_reasons'])
            trigger=next(r['details'] for r in rows if r['event']=='trigger_return')
            self.assertEqual([trigger[k] for k in ['request_type','request','value','index','length','timeout_ns']],
                             [0x41,0x54,1,2,0,16000000])
            if name=='trigger-rejected':
                self.assertEqual(trigger['error']['domain'],'fixture-control')
                self.assertEqual(trigger['error']['code_u32'],0xe00002e2)
            if name=='accepted-control-error':
                self.assertIs(trigger['accepted'],True);self.assertEqual(trigger['error']['code'],19)
                self.assertIn('trigger_accepted_with_error',result['failure_reasons'])

    def test_foreign_missing_callback_abort_rejection_and_failed_save_hold_resources(self):
        for name in ['foreign-pointer','iso-pending','abort-refused','detach-pending','save-failed','journal-trigger-failed','duplicate-iso']:
            _,_,result,calls=self.case(name);self.assertFalse(result['closed'])
            self.assertEqual(calls['destroys'],0);self.assertEqual(calls['releases'],0)
        self.assertEqual(self.case('detach-pending')[3]['host_aborts'],0)
        self.assertEqual(self.case('iso-pending')[3]['host_aborts'],1)
        self.assertEqual(self.case('abort-refused')[3]['host_aborts'],1)

    def test_invalid_source_time_or_type_cannot_submit_iso(self):
        for name in ['short-before','stale-before','mock-before','error-before','overflow-before','integer-accepted','boolean-count',
                     'old-before-time','future-before-time','mock-frame','old-frame-time','stale-frame']:
            _,_,result,calls=self.case(name)
            self.assertEqual(calls['iso_submissions'],0);self.assertEqual(calls['burst_enqueues'],0)
            self.assertTrue(result['failure_reasons']);self.assertTrue(result['closed'])
        for name in ['gap-after-intent','arrival-during-intent','journal-trigger-failed']:
            _,_,result,calls=self.case(name);self.assertEqual(calls['burst_enqueues'],0)
            self.assertEqual(calls['host_aborts'],0)
            self.assertTrue(result['failure_reasons'])

    def test_saved_mock_cores_do_not_override_errors_or_become_sdk_capture(self):
        for directory in sorted(self.root.iterdir()):
            if not (directory/'transfer/COMMITTED').is_file():continue
            core=audit_core(directory/'transfer');self.assertFalse(core['hardware_verified'])
            self.assertEqual(core['execution_mode'],'simulation')
        root,_,result,_=self.case('control-error');core=audit_core(root/'transfer')
        self.assertTrue(core['simulation_logic_pass']);self.assertTrue(result['failure_reasons'])
        root=self.root/'iso-first'
        with self.assertRaises(ValueError):audit_no_td(root/'adapter.jsonl',root/'transfer',hardware=True)
        with self.assertRaises((OSError,ValueError)):audit_model(root)


if __name__=='__main__':unittest.main()
