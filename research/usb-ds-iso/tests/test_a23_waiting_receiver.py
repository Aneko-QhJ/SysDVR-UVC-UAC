"""Native build/receipt guards and injected lifecycle/workflow. No acquisition."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_a23_waiting_receiver as b
import audit_a23_waiting_receiver as audit
from workflows import capture_a23_waiting_receiver as gate


class WaitingReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.base=Path(cls.tmp.name).resolve();cls.repo=cls.base/'repo';cls.repo.mkdir()
        for n in b.source_hashes():
            dst=cls.repo/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(b.REPO/n,dst)
        (cls.repo/'research/usb-ds-iso/private/runs').mkdir(parents=True)
        cls.review=cls.base/'review';cls.audit=audit.run(cls.review,cls.repo);cls.record=cls.audit['offline_record'];cls.build=Path(cls.record['build'])

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def setUp(self):
        self.work=Path(tempfile.mkdtemp(dir=self.base));self.path=self.work/'record.json';self.ticket=copy.deepcopy(self.record);b.write(self.path,self.ticket)

    def case(self,name):return self.review/'native-fixtures'/name
    def calls(self,name):return b.load(self.case(name)/'injected-calls.json')
    def native(self,*args,binary=None):
        return subprocess.run([str(binary or self.build/'receiver'),*map(str,args)],capture_output=True,text=True,timeout=10)

    def mock_issue(self):
        validation=self.work/'validation';validation.mkdir()
        b.write(validation/'validation.json',dict(schema='A23-waiting-receiver-validation-1',passed=True,skipped=0,
            native_iokit_calls=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,build_manifest_sha256=self.ticket['build_manifest_sha256'],receiver_sha256=self.ticket['receiver_sha256']))
        b.seal(validation)
        self.ticket.update(stage='prepared',remaining=1,acquisition_enabled=True,validation_directory=str(validation),validation_manifest_sha256=b.sha(b.plain(validation/'SHA256SUMS')))
        self.path.unlink();b.write(self.path,self.ticket)

    def receipt(self,run):
        r=dict(schema='A23-waiting-burst-consumed-receipt-1',backend='a23-waiting-burst-1',attempt_consumed=True,
            receiver_sha256=self.ticket['receiver_sha256'],build_manifest_sha256=self.ticket['build_manifest_sha256'],
            recipe_sha256=self.ticket['recipe_sha256'],plan=b.WAIT_PLAN,preparation_id=self.ticket['preparation_id'])
        b.write(run/'waiting-authorization.json',r);return r

    def reseal_clone(self,build):
        for n in ('SHA256SUMS','COMMITTED'):(build/n).unlink()
        b.seal(build)

    def test_offline_record_has_zero_and_rejects_before_lock_run_or_launch(self):
        runs=list((self.repo/'research/usb-ds-iso/private/runs').iterdir());before=self.path.read_bytes()
        with patch.object(gate.subprocess,'Popen') as launch:
            self.assertEqual(gate.capture(self.path,repo=self.repo,dry_run=True)['remaining'],0)
            with self.assertRaisesRegex(ValueError,'no new waiting invocation'):gate.capture(self.path,repo=self.repo)
        launch.assert_not_called();self.assertEqual(self.path.read_bytes(),before);self.assertFalse(self.path.with_suffix('.lock').exists())
        self.assertEqual(list((self.repo/'research/usb-ds-iso/private/runs').iterdir()),runs)

    def test_native_description_and_build_check_are_file_only(self):
        self.assertEqual(json.loads(self.native('--describe').stdout),b.DESCRIPTION)
        p=self.native('--check-build',self.build);self.assertEqual(p.returncode,0,p.stderr);self.assertTrue(json.loads(p.stdout)['source_closure_checked'])
        for args in ([],['--acquire-once'],['--repeat','1'],['--capture']):self.assertEqual(self.native(*args).returncode,2)

    def test_native_consumed_check_is_read_only_and_process_claim_is_single_use(self):
        run=self.work/'run';run.mkdir();self.receipt(run);before={p.name:p.read_bytes() for p in run.iterdir()}
        p=self.native('--check-consumed',run,self.build);self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual({p.name:p.read_bytes() for p in run.iterdir()},before)
        command=[str(self.review/'injected-loop'),'--claim-process-only',str(run),str(self.build)]
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
        marker=(run/'WAIT_PROCESS_CLAIMED').read_bytes();self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)
        self.assertEqual((run/'WAIT_PROCESS_CLAIMED').read_bytes(),marker);self.assertFalse((run/'host').exists())

    def test_sdk_claim_requires_the_same_process_receipt_and_is_single_use(self):
        run=self.work/'run';run.mkdir();self.receipt(run)
        command=[str(self.review/'injected-loop'),'--claim-sdk-only',str(run),str(self.build)]
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)
        self.assertFalse((run/'WAIT_RECEIVER_CLAIMED').exists())
        self.assertEqual(subprocess.run([str(self.review/'injected-loop'),'--claim-process-only',str(run),str(self.build)],capture_output=True).returncode,0)
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)
        marker=(run/'WAIT_RECEIVER_CLAIMED').read_bytes();self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)
        self.assertEqual((run/'WAIT_RECEIVER_CLAIMED').read_bytes(),marker);self.assertFalse((run/'host').exists())

    def test_waiting_handoff_rechecks_sources_and_the_original_consumed_receipt(self):
        for fault in ('source','receipt'):
            with self.subTest(fault=fault):
                run=self.work/fault;run.mkdir();r=self.receipt(run)
                p=self.native('--check-consumed',run,self.build);self.assertEqual(p.returncode,0,p.stderr)
                checked=self.work/(fault+'.json');checked.write_text(p.stdout)
                self.assertEqual(subprocess.run([str(self.review/'injected-loop'),'--claim-process-only',str(run),str(self.build)],capture_output=True).returncode,0)
                source=self.repo/'research/usb-ds-iso/host/a23_waiting_receiver.m';raw=source.read_bytes()
                try:
                    if fault=='source':source.write_bytes(raw+b'\n/* changed during passive wait */\n')
                    else:r['preparation_id']=str(uuid.uuid4());(run/'waiting-authorization.json').write_bytes(b.canonical(r))
                    p=subprocess.run([str(self.review/'injected-loop'),'--claim-sdk-checked',str(run),str(self.build),str(checked)],capture_output=True)
                    self.assertEqual(p.returncode,2);self.assertFalse((run/'WAIT_RECEIVER_CLAIMED').exists())
                finally:source.write_bytes(raw)

    def test_invalid_acquire_receipts_reject_before_any_claim_or_device_setup(self):
        for fault in ('missing','old','binary','build','recipe','integer-flag','float-count','duplicate','symlink'):
            with self.subTest(fault=fault):
                run=self.work/str(uuid.uuid4());run.mkdir();r=self.receipt(run);p=run/'waiting-authorization.json'
                if fault=='old':r['schema']='A23-burst-sdk-consumed-receipt-1'
                elif fault in ('binary','build','recipe'):r[{'binary':'receiver_sha256','build':'build_manifest_sha256','recipe':'recipe_sha256'}[fault]]='0'*64
                elif fault=='integer-flag':r['attempt_consumed']=1
                elif fault=='float-count':r=copy.deepcopy(r);r['plan']['max_handoffs']=1.0
                p.unlink()
                if fault=='symlink':b.write(run/'other',r);p.symlink_to(run/'other')
                elif fault!='missing':p.write_bytes(b.canonical(r) if fault!='duplicate' else b.canonical(r).replace(b'{',b'{"attempt_consumed":false,',1))
                result=self.native('--acquire-once',run,self.build);self.assertEqual(result.returncode,2,result.stderr)
                self.assertFalse((run/'WAIT_PROCESS_CLAIMED').exists());self.assertFalse((run/'host').exists())

    def test_current_source_change_is_rejected_by_both_guards_without_side_effects(self):
        name='research/usb-ds-iso/host/a23_waiting_receiver.m';p=self.repo/name;raw=p.read_bytes()
        try:
            p.write_bytes(raw+b'\n/* injected drift */\n')
            with self.assertRaises(ValueError):b.verify_build(self.ticket,self.repo)
            self.assertEqual(self.native('--check-build',self.build).returncode,2)
        finally:p.write_bytes(raw)

    def test_tampered_frozen_builds_fail_even_after_outer_rehash(self):
        for fault in ('frozen-source','embedded-meta','extra','symlink','partial-manifest','receiver'):
            with self.subTest(fault=fault):
                clone=self.work/fault;shutil.copytree(self.build,clone)
                if fault=='frozen-source':(clone/'source/research/usb-ds-iso/host/a23_passive_wait_adapter.c').write_text('changed')
                elif fault=='embedded-meta':
                    meta=b.load(clone/'manifest.json');meta['acquisition_enabled']=True;(clone/'manifest.json').write_bytes(b.canonical(meta))
                elif fault=='extra':(clone/'extra').write_text('unlisted')
                elif fault=='symlink':(clone/'alias').symlink_to(clone/'manifest.json')
                elif fault=='receiver':
                    p=clone/'receiver';raw=bytearray(p.read_bytes());raw[-1]^=1;p.write_bytes(raw)
                if fault!='symlink':self.reseal_clone(clone)
                if fault=='partial-manifest':(clone/'SHA256SUMS').write_bytes((clone/'SHA256SUMS').read_bytes()[:-10])
                record=copy.deepcopy(self.ticket);record.update(build=str(clone),build_manifest_sha256=b.sha(b.plain(clone/'SHA256SUMS')))
                with self.assertRaises(ValueError):b.verify_build(record,self.repo)
                # A changed binary must never be executed, even in a check mode.
                if fault!='receiver':self.assertEqual(self.native('--check-build',clone,binary=clone/'receiver').returncode,2)

    def test_loop_separates_prepare_start_and_allows_queued_detach(self):
        self.assertEqual(self.audit['native_loop_case_count'],12)
        for name in ('signal-before-begin','signal-waiting','signal-between-turns','detach-between-turns','wait-timeout','existing','ambiguous'):
            calls=self.calls(name);self.assertEqual((calls['status_reads'],calls['iso_submissions'],calls['burst_enqueues']),(0,0,0),name)
        self.assertEqual(self.calls('detach-between-turns')['sdk_opens'],1)
        self.assertEqual(self.calls('detach-between-turns')['sdk_destroys'],1)
        self.assertTrue(self.audit['native_loop_cases']['normal']['sdk_analysis']['host_observation_complete'])
        self.assertTrue(self.audit['native_loop_cases']['signal-before-begin']['pre_wait_signal_prefix_preserved'])

    def test_unresolved_signal_and_detach_keep_resources_without_more_wait_pumps(self):
        for name in ('iso-pending','control-pending','signal-running','detach-running'):
            r=b.load(self.case(name)/'waiting-entry-result.json');calls=self.calls(name)
            self.assertTrue(r['unresolved']);self.assertFalse(r['finished']);self.assertEqual((calls['sdk_destroys'],calls['sdk_releases']),(0,0))
            self.assertLessEqual(calls['aborts'],1)
        for case in self.audit['native_loop_cases']:
            for k in ('native_iokit_calls','real_sdk_objects','usb_requests','sd_accesses'):self.assertEqual(self.calls(case)[k],0)

    def test_prepared_validation_is_bound_and_dry_run_changes_nothing(self):
        self.mock_issue();before=self.path.read_bytes()
        with patch.object(gate.subprocess,'Popen') as launch:gate.capture(self.path,repo=self.repo,dry_run=True)
        launch.assert_not_called();self.assertEqual(before,self.path.read_bytes())
        validation=Path(self.ticket['validation_directory']);value=b.load(validation/'validation.json');value['receiver_sha256']='0'*64
        (validation/'validation.json').write_bytes(b.canonical(value))
        with self.assertRaises(ValueError):gate.prepared(b.load(self.path),self.repo)

    def test_consumes_before_launch_failure_and_never_retries(self):
        self.mock_issue()
        def launch(command,**kwargs):
            current=b.load(self.path);self.assertEqual((current['stage'],current['remaining'],current['acquisition_enabled']),('consumed',0,False))
            r=b.load(Path(command[2])/'waiting-authorization.json');self.assertEqual(r['recipe_sha256'],self.ticket['recipe_sha256']);self.assertTrue(kwargs['start_new_session'])
            raise OSError('injected launch failure')
        with patch.object(gate.subprocess,'Popen',side_effect=launch) as p:
            result=gate.capture(self.path,repo=self.repo)
            with self.assertRaises(ValueError):gate.capture(self.path,repo=self.repo)
        self.assertEqual(p.call_count,1);self.assertEqual(b.load(self.path)['stage'],'failed_no_retry');self.assertFalse(result['receiver_launched'])

    def test_failure_writing_consumed_receipt_still_burns_use_without_launch(self):
        self.mock_issue();original=b.write
        def write(path,value):
            if Path(path).name=='waiting-authorization.json':raise OSError('injected receipt persistence failure')
            return original(path,value)
        with patch.object(gate.build,'write',side_effect=write),patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(OSError):gate.capture(self.path,repo=self.repo)
        launch.assert_not_called();ticket=b.load(self.path)
        self.assertEqual((ticket['stage'],ticket['remaining'],ticket['acquisition_enabled']),('consumed',0,False))
        with self.assertRaises(ValueError):gate.capture(self.path,repo=self.repo)

    def test_watchdog_and_wait_error_preserve_process_and_leave_host_unsealed(self):
        for i,error in enumerate((subprocess.TimeoutExpired('injected',130),OSError('injected wait error'))):
            if i:
                self.path.unlink();self.ticket=copy.deepcopy(self.record);b.write(self.path,self.ticket)
                self.work=self.work/'second';self.work.mkdir();self.path=self.work/'record.json';b.write(self.path,self.ticket)
            self.mock_issue();process=Mock(pid=731);process.wait.side_effect=error
            with patch.object(gate.subprocess,'Popen',return_value=process):result=gate.capture(self.path,repo=self.repo)
            process.kill.assert_not_called();process.terminate.assert_not_called();process.send_signal.assert_not_called()
            self.assertTrue(result['receiver_left_running']);self.assertFalse(result['forced_exit'])
            self.assertFalse((Path(result['run'])/'COMMITTED').exists());self.assertEqual(b.load(self.path)['stage'],'unresolved_no_retry')

    def test_closed_injected_observation_is_audited_and_sealed(self):
        self.mock_issue()
        def launch(command,**kwargs):
            (Path(command[2])/'MOCK_ONLY.txt').write_text('Workflow launcher replaced; receiver never invoked.')
            shutil.copytree(self.case('normal'),Path(command[2])/'host');return Mock(pid=732,wait=Mock(return_value=0))
        with patch.object(gate.subprocess,'Popen',side_effect=launch):result=gate.capture(self.path,repo=self.repo)
        self.assertTrue(result['host_observation_complete']);self.assertIs(result['hardware_verified'],False)
        self.assertEqual(b.load(self.path)['stage'],'captured_logs_pending');self.assertTrue((Path(result['run'])/'COMMITTED').is_file())

    def test_bad_or_partial_receiver_results_are_preserved_and_cannot_pass(self):
        self.mock_issue()
        for fault in ('not-finished','exit-code','boolean-ticks','binding','partial-journal'):
            with self.subTest(fault=fault):
                self.path.write_bytes(b.canonical(self.ticket)) # isolated mock record only
                def launch(command,**kwargs):
                    host=Path(command[2])/'host';shutil.copytree(self.case('normal'),host)
                    r=b.load(host/'waiting-entry-result.json')
                    if fault=='not-finished':r['finished']=False
                    elif fault=='exit-code':r['host_result']['exit_code']=1
                    elif fault=='boolean-ticks':r['host_result']['ticks']=True
                    elif fault=='binding':r['host_result']['binding']['session_id']=str(uuid.uuid4())
                    elif fault=='partial-journal':(host/'wait.jsonl').write_bytes((host/'wait.jsonl').read_bytes()[:90])
                    (host/'waiting-entry-result.json').write_bytes(b.canonical(r));return Mock(pid=733,wait=Mock(return_value=0))
                with patch.object(gate.subprocess,'Popen',side_effect=launch):result=gate.capture(self.path,repo=self.repo)
                self.assertFalse(result['host_observation_complete']);self.assertEqual(b.load(self.path)['stage'],'failed_no_retry')
                run=Path(result['run']);self.assertTrue((run/'COMMITTED').is_file())
                if fault=='partial-journal':self.assertEqual((run/'host/wait.jsonl').stat().st_size,90)

    def test_boolean_count_wrong_scope_and_old_record_reject_without_launch(self):
        self.mock_issue()
        for key,value in [('remaining',True),('remaining',1.0),('acquisition_enabled',1),('backend','iousbhost-single-burst-1'),('stage','failed_no_retry'),('hardware_verified',True)]:
            record=copy.deepcopy(self.ticket);record[key]=value
            with self.assertRaises(ValueError):gate.prepared(record,self.repo)


if __name__=='__main__':unittest.main()
