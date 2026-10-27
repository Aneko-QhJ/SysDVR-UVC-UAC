"""Bound entry/file guards and injected one-use workflow; never a real capture."""
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
import uuid
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from workflows import capture_io_usb_host_burst as gate
import prepare_io_usb_host_burst as prepare
from io_usb_host_burst_entry_plan import PLAN,SCOPE,canonical,validate_plan,validate_scope

class EntryGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.root=self.base/'project/research/usb-ds-iso'
        for name in ('private/analysis','private/runs','host','tools/workflows'):(self.root/name).mkdir(parents=True)
        (self.root/'host/io_usb_host_mock.m').write_text('injected source, never compile or execute')
        (self.root/'tools/workflows/capture_io_usb_host_burst.py').write_text('injected workflow source')
        protocol=self.root.parents[1]/'source/uvc/iso_probe_protocol.h';protocol.parent.mkdir(parents=True);protocol.write_text('mock ABI')
        self.build=self.base/'build';self.build.mkdir();(self.build/'receiver').write_text('injected executable: never run')
        self.hashes=gate.source_hashes(self.root)
        for name in self.hashes:
            dst=self.build/'source'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(self.root.parents[1]/name,dst)
        self.meta=dict(schema='A23-burst-sdk-build-1',backend='iousbhost-single-burst-1',validation_passed=True,
            acquisition_enabled=False,usb_requests_during_preparation=0,plan=copy.deepcopy(PLAN),diagnostic_scope=copy.deepcopy(SCOPE),source_hashes=self.hashes)
        self.ticket=dict(schema='A23-burst-sdk-preparation-1',backend='iousbhost-single-burst-1',stage='prepared',remaining=1,
            acquisition_enabled=True,preparation_id=str(uuid.uuid4()),build=str(self.build),plan=copy.deepcopy(PLAN),diagnostic_scope=copy.deepcopy(SCOPE),
            receiver_sha256=gate.digest(self.build/'receiver'),**{k:False for k in gate.POLICY})
        self.path=self.root/'private/analysis/ticket.json';self.seal()

    def seal(self):
        (self.build/'manifest.json').write_bytes(canonical(self.meta));(self.build/'describe.json').write_bytes(canonical(PLAN))
        sums=''.join(f'{gate.digest(p)}  {p.relative_to(self.build).as_posix()}\n' for p in sorted(self.build.rglob('*')) if p.is_file() and p.name not in ('SHA256SUMS','COMMITTED')).encode()
        (self.build/'SHA256SUMS').write_bytes(sums);self.ticket['build_manifest_sha256']=hashlib.sha256(sums).hexdigest()
        (self.build/'COMMITTED').write_text(self.ticket['build_manifest_sha256']+'\n');self.path.write_bytes(canonical(self.ticket))

    def test_offline_record_has_zero_and_cannot_lock_launch_or_create_run(self):
        self.ticket.update(stage='offline_build_ready',remaining=0,acquisition_enabled=False);self.seal()
        with patch.object(gate.subprocess,'Popen') as launch:
            result=gate.capture(self.path,dry_run=True,root=self.root)
            with self.assertRaisesRegex(ValueError,'No single SDK burst'):gate.capture(self.path,root=self.root)
        launch.assert_not_called();self.assertEqual(result['remaining'],0);self.assertFalse(result['acquisition_enabled'])
        self.assertFalse(self.path.with_suffix('.lock').exists());self.assertFalse(list((self.root/'private/runs').iterdir()))

    def test_issued_dry_run_is_read_only(self):
        before=self.path.read_bytes()
        with patch.object(gate.subprocess,'Popen') as launch:r=gate.capture(self.path,dry_run=True,root=self.root)
        launch.assert_not_called();self.assertEqual(self.path.read_bytes(),before);self.assertEqual(r['remaining'],1)

    def test_consumed_before_launch_and_failed_launch_cannot_retry(self):
        def launch(command,**kwargs):
            ticket=gate.load(self.path);self.assertEqual(ticket['stage'],'consumed');self.assertEqual(ticket['remaining'],0)
            self.assertIs(ticket['acquisition_enabled'],False);self.assertTrue(kwargs['start_new_session'])
            receipt=gate.load(Path(command[2])/'authorization.json')
            self.assertEqual(receipt['plan'],PLAN);self.assertEqual(receipt['diagnostic_scope'],SCOPE)
            self.assertEqual((Path(command[2])/'authorization.json').read_bytes(),canonical(receipt))
            raise OSError('injected launch failure')
        with patch.object(gate.subprocess,'Popen',side_effect=launch) as start:
            r=gate.capture(self.path,root=self.root)
            with self.assertRaises(ValueError):gate.capture(self.path,root=self.root)
        self.assertEqual(start.call_count,1);self.assertFalse(r['receiver_launched']);self.assertEqual(gate.load(self.path)['stage'],'failed_no_retry')

    def test_watchdog_or_wait_error_leaves_process_and_dma_alive(self):
        for error in (subprocess.TimeoutExpired('injected',20),OSError('injected wait error')):
            self.path.write_bytes(canonical(self.ticket));process=Mock(pid=1234);process.wait.side_effect=error
            with patch.object(gate.subprocess,'Popen',return_value=process):r=gate.capture(self.path,root=self.root)
            process.kill.assert_not_called();process.terminate.assert_not_called();process.send_signal.assert_not_called()
            self.assertTrue(r['receiver_left_running']);self.assertFalse(r['forced_exit']);self.assertEqual(gate.load(self.path)['remaining'],0)

    def test_lock_or_changed_stage_count_plan_policy_rejects_before_launch(self):
        self.path.with_suffix('.lock').write_text('injected held claim')
        with patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(FileExistsError):gate.capture(self.path,root=self.root)
        self.path.with_suffix('.lock').unlink();launch.assert_not_called()
        for key,value in [('backend','iousbhost-no-td-1'),('stage','consumed'),('remaining',0),('remaining',True),('remaining',1.0),('acquisition_enabled',1),('hardware_verified',True)]:
            ticket=copy.deepcopy(self.ticket);ticket[key]=value
            with self.assertRaises(ValueError):gate.verify_prepared(ticket,self.root)
        for key,value in [('max_submissions',True),('repeat',1),('hardware_entry_enabled',True),('control_deadline_ns',0),('first_frame_lead',64.0)]:
            p=copy.deepcopy(PLAN);p[key]=value
            with self.assertRaises(ValueError):validate_plan(p)
        for key,value in [('runtime_record',True),('video_disabled_required',1),('allow_next_burst',True)]:
            p=copy.deepcopy(SCOPE);p[key]=value
            with self.assertRaises(ValueError):validate_scope(p)

    def test_build_tamper_partial_extra_and_symlink_fail_even_after_rehash(self):
        for fault in ('receiver','extra','symlink','source','frozen-source','protocol','duplicate-json','manifest-traversal'):
            with self.subTest(fault=fault):
                temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);b=Path(temp.name).resolve()/'build';shutil.copytree(self.build,b)
                t=copy.deepcopy(self.ticket);t['build']=str(b)
                if fault=='receiver':(b/'receiver').write_text('changed')
                elif fault=='extra':(b/'extra').write_text('extra')
                elif fault=='symlink':(b/'source-link').symlink_to(b/'source',target_is_directory=True)
                elif fault=='source':t['plan']['repeat']=1
                elif fault=='frozen-source':next((b/'source').rglob('io_usb_host_mock.m')).write_text('different frozen source')
                elif fault=='protocol':t['diagnostic_scope']['runtime_record']=22
                elif fault=='duplicate-json':(b/'manifest.json').write_text('{"backend":"x","backend":"y"}')
                else:
                    sums=(b/'SHA256SUMS').read_bytes()+b'0  ../outside\n';(b/'SHA256SUMS').write_bytes(sums)
                    t['build_manifest_sha256']=hashlib.sha256(sums).hexdigest();(b/'COMMITTED').write_text(t['build_manifest_sha256']+'\n')
                with self.assertRaises((ValueError,OSError,KeyError)):gate.verify_prepared(t,self.root)

    def test_source_change_invalidates_preparation(self):
        (self.root/'host/io_usb_host_mock.m').write_text('new source')
        with self.assertRaisesRegex(ValueError,'sources changed'):gate.verify_prepared(self.ticket,self.root)

    def test_durable_consumption_failure_cannot_launch(self):
        with patch.object(gate,'replace_state',side_effect=OSError('injected fsync failure')),patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(OSError):gate.capture(self.path,root=self.root)
        launch.assert_not_called()

    def test_zero_record_and_invalid_validation_never_build_or_issue(self):
        report=self.base/'validation.json';report.write_text('{}');output=self.base/'never-created'
        with patch.object(prepare.subprocess,'run') as run:
            with self.assertRaises(ValueError):prepare.prepare(output,report,ticket_path=self.base/'new-ticket',root=self.root)
        run.assert_not_called();self.assertFalse(output.exists())
        with self.assertRaises(ValueError):prepare.prepare(output,report,ticket_path=self.path,root=self.root)

    def test_receipt_save_failure_after_consumption_cannot_launch_or_retry(self):
        original=gate.write_new
        def write(path,value):
            if path.name=='authorization.json':raise OSError('injected receipt write failure')
            return original(path,value)
        with patch.object(gate,'write_new',side_effect=write),patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(OSError):gate.capture(self.path,root=self.root)
        launch.assert_not_called();self.assertEqual(gate.load(self.path)['remaining'],0)
        with self.assertRaises(ValueError):gate.capture(self.path,root=self.root)

    def fixture_launch(self,case,mutate=None,code=0):
        value=os.environ.get('A23_BURST_COORDINATOR_FIXTURES')
        if not value:self.skipTest('set injected SDK coordinator fixtures')
        fixture=Path(value)/case
        def launch(command,**kwargs):
            run=Path(command[2]);shutil.copytree(fixture,run/'host');host=gate.load(run/'host/result.json')
            entry=dict(schema='A23-burst-sdk-entry-result-1',backend='iousbhost-single-burst-1',attempted=True,
                preflight_failed=False,finished=True,unresolved=False,exit_code=code,host_result=host,**{k:False for k in gate.POLICY})
            if mutate:mutate(entry)
            gate.write_new(run/'entry-result.json',entry);return Mock(wait=Mock(return_value=code))
        return launch

    def test_complete_injected_host_records_logs_pending_without_hardware_promotion(self):
        with patch.object(gate.subprocess,'Popen',side_effect=self.fixture_launch('iso-first')) as launch:r=gate.capture(self.path,root=self.root)
        self.assertEqual(launch.call_count,1);self.assertTrue(r['host_observation_complete']);self.assertEqual(gate.load(self.path)['stage'],'captured_logs_pending')
        self.assertTrue((Path(r['run'])/'COMMITTED').exists())
        for key in gate.POLICY:self.assertIs(r[key],False)

    def test_failed_injected_host_or_wrong_process_code_stays_failed_no_retry(self):
        for case,code in [('control-error',1),('iso-first',1)]:
            self.path.write_bytes(canonical(self.ticket))
            with patch.object(gate.subprocess,'Popen',side_effect=self.fixture_launch(case,code=code)):r=gate.capture(self.path,root=self.root)
            self.assertFalse(r['host_observation_complete']);self.assertEqual(gate.load(self.path)['stage'],'failed_no_retry')

    def test_entry_result_cannot_erase_coordinator_failure_policy_or_clock(self):
        for change in [lambda r:r.update(hardware_verified=True),lambda r:r['host_result'].update(failure_reasons=['erased']),
                       lambda r:r['host_result'].update(final_checkpoint_saved=False),lambda r:r['host_result'].update(ticks=True)]:
            self.path.write_bytes(canonical(self.ticket))
            with patch.object(gate.subprocess,'Popen',side_effect=self.fixture_launch('iso-first',mutate=change)):r=gate.capture(self.path,root=self.root)
            self.assertFalse(r['host_observation_complete']);self.assertEqual(gate.load(self.path)['stage'],'failed_no_retry')

class NativeEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('A23_BURST_ENTRY_REVIEW')
        if not value:raise unittest.SkipTest('set A23_BURST_ENTRY_REVIEW; all native operations injected')
        cls.review=Path(value);cls.receiver=cls.review/'receiver-draft';cls.claim=cls.review/'entry-test'

    def test_twelve_native_preflight_and_pending_scenarios(self):
        dirs=list((self.review/'native-fixtures').iterdir());self.assertEqual(len(dirs),12)
        for d in dirs:
            r=gate.load(d/'entry-result.json');calls=gate.load(d/'injected-calls.json')
            for key in ('attempted','preflight_failed','finished','unresolved',*gate.POLICY):self.assertIs(type(r[key]),bool)
            self.assertIs(calls['injected_only'],True)
            for key in ('usb_requests','registry_calls','real_sdk_objects','sd_accesses'):self.assertEqual(calls[key],0)
            self.assertLessEqual(calls['iso_submissions'],1);self.assertLessEqual(calls['burst_enqueues'],1)
            if r['preflight_failed']:self.assertTrue(r['finished']);self.assertEqual(calls['iso_submissions'],0)
            if r['unresolved']:self.assertFalse(r['finished']);self.assertEqual(calls['destroys'],0)
        self.assertEqual(gate.audit_host(self.review/'native-fixtures/clean')['host_observation_complete'],True)

    def receipt(self):
        return dict(schema='A23-burst-sdk-consumed-receipt-1',backend='iousbhost-single-burst-1',attempt_consumed=True,
            plan=copy.deepcopy(PLAN),diagnostic_scope=copy.deepcopy(SCOPE),receiver_sha256=gate.digest(self.receiver),
            build_manifest_sha256='0'*64,preparation_id=str(uuid.uuid4()))

    def test_native_receipt_valid_claim_and_duplicate_refusal_without_sdk(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);r=self.receipt();(p/'authorization.json').write_bytes(canonical(r))
            command=[str(self.claim),'--claim-only',str(p),str(self.receiver)]
            first=subprocess.run(command,capture_output=True,text=True);self.assertEqual(first.returncode,0,first.stderr)
            second=subprocess.run([str(self.receiver),'--acquire-once',str(p)],capture_output=True,text=True)
            self.assertEqual(second.returncode,2);self.assertIn('already claimed',second.stderr);self.assertFalse((p/'host').exists())

    def test_native_receipt_guards_reject_before_claim_or_sdk(self):
        faults=['missing','old-schema','wrong-binary','wrong-plan','boolean-count','float-count','integer-flag','scope','bad-id','bad-hash','extra','duplicate-json','symlink','oversized']
        for fault in faults:
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);r=self.receipt()
                if fault=='old-schema':r['schema']='A23-IOUSBHost-consumed-receipt-1'
                elif fault=='wrong-binary':r['receiver_sha256']='1'*64
                elif fault=='wrong-plan':r['plan']['repeat']=1
                elif fault=='boolean-count':r['plan']['max_submissions']=True
                elif fault=='float-count':r['plan']['max_submissions']=1.0
                elif fault=='integer-flag':r['attempt_consumed']=1
                elif fault=='scope':r['diagnostic_scope']['runtime_record']=22
                elif fault=='bad-id':r['preparation_id']='bad'
                elif fault=='bad-hash':r['build_manifest_sha256']='Z'*64
                elif fault=='extra':r['repeat']=1
                raw=canonical(r)
                if fault=='duplicate-json':raw=raw.replace(b'{',b'{"attempt_consumed":false,',1)
                elif fault=='oversized':raw=b' '*16385
                if fault=='symlink':
                    other=p/'other';other.write_bytes(raw);(p/'authorization.json').symlink_to(other)
                elif fault!='missing':(p/'authorization.json').write_bytes(raw)
                run=subprocess.run([str(self.receiver),'--acquire-once',str(p)],capture_output=True,text=True,timeout=5)
                self.assertEqual(run.returncode,2,run.stderr);self.assertIn('no USB accessed',run.stderr)
                self.assertFalse((p/'RECEIVER_CLAIMED').exists());self.assertFalse((p/'host').exists())

    def test_offline_description_and_unknown_capture_repeat_commands(self):
        r=subprocess.run([str(self.receiver),'--describe'],capture_output=True,text=True);self.assertEqual(r.returncode,0);validate_plan(json.loads(r.stdout))
        for argv in ([],['--capture'],['--repeat','1'],['--acquire-once']):
            r=subprocess.run([str(self.receiver),*argv],capture_output=True,text=True);self.assertEqual(r.returncode,2);self.assertIn('no USB accessed',r.stderr)

if __name__=='__main__':unittest.main()
