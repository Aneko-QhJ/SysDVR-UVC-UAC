import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_io_usb_host_session import analyze as session
from analyze_io_usb_host_evidence import analyze as transfer
from analyze_io_usb_host_no_td import analyze as observation
from analyze_io_usb_host_collection import analyze as collection, freeze
from io_usb_host_probe_plan import HARDWARE_PLAN,validate_hardware_plan
from workflows import capture_io_usb_host_no_td as gate


class HardwareFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('A23_HARDWARE_MOCK_FIXTURES')
        if not value:raise unittest.SkipTest('set A23_HARDWARE_MOCK_FIXTURES; SDK-shaped fixtures are mocks only')
        cls.root=Path(value)

    def test_eighteen_injected_driver_journals_use_exact_hardware_plan(self):
        directories=list((self.root/'driver-final').iterdir());self.assertEqual(len(directories),18)
        for d in directories:
            self.assertIn('injected', (d/'MOCK_ONLY.txt').read_text().lower())
            rows=[json.loads(x) for x in (d/'session.jsonl').read_text().splitlines()]
            validate_hardware_plan(rows[0]['details']['probe_plan'])
            b=d/'transfer';r=session(d/'session.jsonl',b if (b/'COMMITTED').is_file() else None,hardware=True)
            self.assertEqual(r['simulation_session_pass'],d.name=='clean')
            self.assertFalse(r['hardware_verified']);self.assertFalse(r['callback_drain_verified'])

    def test_simulation_analyzers_reject_sdk_mode_without_relabeling(self):
        d=self.root/'driver-final/clean'
        with self.assertRaises(ValueError):session(d/'session.jsonl',d/'transfer')
        with self.assertRaises(ValueError):transfer(d/'transfer')
        with self.assertRaises(ValueError):collection(self.root/'hardware-collections/clean')

    def test_four_collections_keep_native_policy_unknown(self):
        dirs=list((self.root/'hardware-collections').iterdir());self.assertEqual(len(dirs),4)
        for d in dirs:
            # Older injected logs used request sequence labels, unlike A23.
            # Keep those frozen inputs and reject them in hardware mode.
            self.assertFalse(observation(d,hardware=True)['observation_complete'])
            with tempfile.TemporaryDirectory() as tmp:
                tmp=Path(tmp);log=tmp/'device-log.txt'
                lines=[]
                for line in (d/'device-log.txt').read_text().splitlines():
                    if line.startswith('EP0['):
                        suffix=line.split(': ',1)[1]
                        for interface in (0,1):
                            lines.extend([f'EP0[{interface}]: {suffix}',
                                          f'EP0[{interface}]: wIndex mismatch, ignoring'])
                    else: lines.append(line)
                log.write_text('\n'.join(lines)+'\n')
                freeze(d/'session.jsonl',d/'transfer',log,tmp/'collection',hardware=True)
                r=observation(tmp/'collection',hardware=True)
            self.assertEqual(r['observation_complete'],d.name=='clean')
            for k in ('hardware_verified','usb_strict_pass','baseline_accepted','allow_next_burst',
                      'empty_status_policy_verified','callback_drain_verified','software_frame_freshness_verified'):
                self.assertIs(r[k],False)

    def test_rejected_submit_has_one_status_and_no_callback(self):
        for name in ('stale-frame','slow-query'):
            d=self.root/'driver-final'/name;r=session(d/'session.jsonl',d/'transfer',hardware=True)
            self.assertEqual(r['status_replies'],1);self.assertEqual(r['callbacks'],0)
            self.assertFalse(r['admission']['forwarded']);self.assertTrue(r['resources_closed'])

    def test_timeout_detach_foreign_and_write_failure_never_close(self):
        for name in ('pending-timeout','abort-refused','detach-pending','foreign-pointer','save-failed'):
            d=self.root/'driver-final'/name;r=session(d/'session.jsonl',hardware=True)
            self.assertFalse(r['resources_closed']);self.assertTrue(r['exit_wait_expired'])
            self.assertEqual(r['abort_requests'],int(name not in {'detach-pending','foreign-pointer','save-failed'}))

    def test_fixed_hardware_plan_rejects_numeric_and_policy_changes(self):
        for k,v in (('max_submissions',True),('repeat',1),('max_device_triggers',1),
                    ('completion_deadline_ns',0),('post_close_monitor_ns',1),('hardware_verified',True)):
            plan=copy.deepcopy(HARDWARE_PLAN);plan[k]=v
            with self.assertRaises(ValueError):validate_hardware_plan(plan)

    def test_sdk_reply_cannot_be_replaced_with_mock_source(self):
        d=self.root/'driver-final/clean'
        rows=[json.loads(x) for x in (d/'session.jsonl').read_text().splitlines()]
        next(r for r in rows if r['event']=='status_observed')['details']['observation']['source']='mock_control_reply'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'journal';p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaises(ValueError):session(p,d/'transfer',hardware=True)


class OneUseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'project/research/usb-ds-iso'
        (self.root/'private/analysis').mkdir(parents=True);(self.root/'private/runs').mkdir()
        (self.root/'host').mkdir();self.source=self.root/'host/driver.m';self.source.write_text('mock source')
        protocol=self.root.parents[1]/'source/uvc/iso_probe_protocol.h';protocol.parent.mkdir(parents=True);protocol.write_text('mock protocol')
        self.build=self.base/'build';self.build.mkdir();(self.build/'receiver').write_text('mock program: never execute')
        self.meta=dict(schema='A23-IOUSBHost-build-1',backend='iousbhost-no-td-1',validation_passed=True,usb_requests_during_preparation=0,plan=HARDWARE_PLAN,
                       source_hashes={'host/driver.m':gate.digest(self.source)},protocol_header_sha256=gate.digest(protocol))
        self.ticket=dict(schema='A23-IOUSBHost-preparation-1',backend='iousbhost-no-td-1',stage='prepared',remaining=1,
                         preparation_id='injected-mock',plan=copy.deepcopy(HARDWARE_PLAN),build=str(self.build))
        self.ticket_path=self.root/'private/analysis/ticket.json';self.seal()

    def seal(self):
        (self.build/'manifest.json').write_text(json.dumps(self.meta))
        manifest=''.join(f'{gate.digest(p)}  {p.name}\n' for p in sorted(self.build.iterdir()) if p.name!='SHA256SUMS')
        (self.build/'SHA256SUMS').write_text(manifest)
        self.ticket.update(build_manifest_sha256=gate.digest(self.build/'SHA256SUMS'),receiver_sha256=gate.digest(self.build/'receiver'))
        self.ticket_path.write_text(json.dumps(self.ticket))

    def test_dry_run_reads_only_and_never_consumes_or_launches(self):
        with patch.object(gate.subprocess,'Popen') as launch:
            result=gate.capture(self.ticket_path,dry_run=True,root=self.root)
        launch.assert_not_called();self.assertFalse(result['usb_accessed'])
        self.assertEqual(gate.load(self.ticket_path)['remaining'],1);self.assertFalse(list((self.root/'private/runs').iterdir()))

    def test_consumption_is_durable_before_the_only_launch(self):
        def launch(argv,**kwargs):
            self.assertEqual(gate.load(self.ticket_path)['remaining'],0)
            self.assertEqual(gate.load(self.ticket_path)['stage'],'consumed')
            self.assertEqual(argv[1],'--acquire-once')
            receipt=gate.load(Path(argv[2])/'authorization.json');self.assertIs(receipt['attempt_consumed'],True)
            return Mock(wait=Mock(return_value=1))
        with patch.object(gate.subprocess,'Popen',side_effect=launch) as start:
            result=gate.capture(self.ticket_path,root=self.root)
            with self.assertRaises(ValueError):gate.capture(self.ticket_path,root=self.root)
        self.assertEqual(start.call_count,1);self.assertFalse(result['host_observation_complete'])
        self.assertEqual(gate.load(self.ticket_path)['stage'],'failed_no_retry')

    def test_failed_launch_still_consumes_and_cannot_retry(self):
        with patch.object(gate.subprocess,'Popen',side_effect=OSError('injected launch failure')) as start:
            with self.assertRaises(OSError):gate.capture(self.ticket_path,root=self.root)
            with self.assertRaises(ValueError):gate.capture(self.ticket_path,root=self.root)
        self.assertEqual(start.call_count,1);self.assertEqual(gate.load(self.ticket_path)['remaining'],0)

    def test_watchdog_leaves_receiver_resident_and_never_sends_signal(self):
        process=Mock(pid=12345);process.wait.side_effect=subprocess.TimeoutExpired('injected mock',20)
        with patch.object(gate.subprocess,'Popen',return_value=process) as launch:
            result=gate.capture(self.ticket_path,root=self.root)
        self.assertIs(launch.call_args.kwargs['start_new_session'],True)
        process.terminate.assert_not_called();process.kill.assert_not_called();process.send_signal.assert_not_called()
        self.assertTrue(result['receiver_left_running']);self.assertFalse(result['forced_exit'])
        self.assertEqual(gate.load(self.ticket_path)['stage'],'unresolved_no_retry')

    def test_duplicate_or_concurrent_entry_refused_before_launch(self):
        self.ticket_path.with_suffix('.lock').write_text('injected held lock')
        with patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(FileExistsError):gate.capture(self.ticket_path,root=self.root)
        launch.assert_not_called();self.assertEqual(gate.load(self.ticket_path)['remaining'],1)

    def test_wrong_stage_count_or_boolean_count_refused(self):
        for key,value in (('stage','consumed'),('remaining',0),('remaining',True),('remaining',1.0),('backend','legacy')):
            ticket=copy.deepcopy(self.ticket);ticket[key]=value
            with self.assertRaises(ValueError):gate.verify_prepared(ticket,self.root)

    def test_binary_or_source_change_refused_before_claim(self):
        for path in (self.build/'receiver',self.source):
            original=path.read_bytes();path.write_bytes(original+b'changed')
            with patch.object(gate.subprocess,'Popen') as launch:
                with self.assertRaises(ValueError):gate.capture(self.ticket_path,root=self.root)
            launch.assert_not_called();self.assertEqual(gate.load(self.ticket_path)['remaining'],1);path.write_bytes(original)

    def test_extra_file_and_manifest_traversal_refused(self):
        p=self.build/'extra';p.write_text('extra')
        with self.assertRaises(ValueError):gate.verify_prepared(self.ticket,self.root)
        p.unlink();(self.build/'SHA256SUMS').write_text('0'*64+'  ../outside\n')
        self.ticket['build_manifest_sha256']=gate.digest(self.build/'SHA256SUMS')
        with self.assertRaises(ValueError):gate.verify_prepared(self.ticket,self.root)

    def test_rehashed_validation_false_and_plan_change_refused(self):
        self.meta['validation_passed']=False;self.seal()
        with self.assertRaises(ValueError):gate.verify_prepared(self.ticket,self.root)
        self.meta['validation_passed']=True;self.seal();self.ticket['plan']['max_device_triggers']=1
        with self.assertRaises(ValueError):gate.verify_prepared(self.ticket,self.root)

    def test_duplicate_json_fields_and_symlink_ticket_refused(self):
        self.ticket_path.write_text('{"remaining":1,"remaining":0}')
        with self.assertRaises(ValueError):gate.load(self.ticket_path)
        self.ticket_path.unlink();self.ticket_path.symlink_to(self.build/'manifest.json')
        with self.assertRaises(ValueError):gate.load(self.ticket_path)

    def test_failure_to_commit_consumption_never_launches(self):
        with patch.object(gate.os,'replace',side_effect=OSError('injected fsync/rename failure')):
            with patch.object(gate.subprocess,'Popen') as launch:
                with self.assertRaises(OSError):gate.capture(self.ticket_path,root=self.root)
        launch.assert_not_called();self.assertEqual(gate.load(self.ticket_path)['remaining'],1)


class ReceiverArgumentGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('A23_TEST_RECEIVER')
        if not value:raise unittest.SkipTest('set A23_TEST_RECEIVER for offline native argument guards')
        cls.receiver=Path(value)

    def run_receiver(self,*args):
        return subprocess.run([str(self.receiver),*map(str,args)],capture_output=True,timeout=10)

    def test_describe_is_pure_and_matches_fixed_plan(self):
        r=self.run_receiver('--describe');self.assertEqual(r.returncode,0)
        self.assertEqual(json.loads(r.stdout),HARDWARE_PLAN)

    def test_unknown_options_cannot_override_count_or_trigger(self):
        for args in (('--repeat','2'),('--trigger',),('--first-frame','100'),('--acquire-once',),('--describe','extra')):
            r=self.run_receiver(*args);self.assertEqual(r.returncode,2)

    def test_missing_consumed_receipt_refuses_before_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=self.run_receiver('--acquire-once',tmp);self.assertEqual(r.returncode,2)
            self.assertFalse((Path(tmp)/'RECEIVER_CLAIMED').exists())

    def test_changed_plan_or_false_consumption_refuses_without_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            original=dict(schema='A23-IOUSBHost-consumed-receipt-1',attempt_consumed=True,
                          receiver_sha256=gate.digest(self.receiver),plan=HARDWARE_PLAN)
            for change in ('plan','consumption'):
                receipt=copy.deepcopy(original)
                if change=='plan':receipt['plan']['max_device_triggers']=1
                else:receipt['attempt_consumed']=1
                (root/'authorization.json').write_text(json.dumps(receipt))
                r=self.run_receiver('--acquire-once',root);self.assertEqual(r.returncode,2)
                self.assertFalse((root/'RECEIVER_CLAIMED').exists())

    def test_already_claimed_receipt_refuses_before_sdk_instantiation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'RECEIVER_CLAIMED').write_text('injected existing claim')
            receipt=dict(schema='A23-IOUSBHost-consumed-receipt-1',attempt_consumed=True,
                         receiver_sha256=gate.digest(self.receiver),plan=HARDWARE_PLAN)
            (root/'authorization.json').write_text(json.dumps(receipt))
            r=self.run_receiver('--acquire-once',root);self.assertEqual(r.returncode,2)
            self.assertIn(b'already claimed',r.stderr)
            self.assertFalse((root/'session.jsonl').exists())


if __name__=='__main__':unittest.main()
