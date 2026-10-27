"""Bound candidate builds, file-only native claims and supplied EXE3 models."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_a23_bound_receiver as b
import audit_a23_bound_receiver as audit
import collect_a23_bound_execution as c
from workflows import capture_a23_bound_receiver as gate


class BoundReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.base=Path(cls.tmp.name).resolve();cls.repo=cls.base/'repo';cls.repo.mkdir()
        for n in b.source_hashes():
            p=cls.repo/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(b.REPO/n,p)
        (cls.repo/'research/usb-ds-iso/private/runs').mkdir(parents=True)
        cls.device=cls.base/'device'
        for n in b.device.FILES:
            p=cls.device/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(b.DEVICE/'window-30s'/n,p)
        cls.review=cls.base/'review';cls.audit=audit.run(cls.review,cls.repo,cls.device)
        cls.record=cls.audit['offline_record'];cls.build=Path(cls.record['build'])

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def setUp(self):
        self.work=Path(tempfile.mkdtemp(dir=self.base));self.path=self.work/'record.json';self.ticket=copy.deepcopy(self.record);b.write(self.path,self.ticket)

    def native(self,*args,binary=None):
        return subprocess.run([str(binary or self.build/'receiver'),*map(str,args)],capture_output=True,text=True,timeout=15)

    def row(self,name='matching'):return self.audit['collection_cases'][name]['analysis']

    def mock_issue(self):
        v=self.work/'validation';v.mkdir()
        b.write(v/'validation.json',dict(schema='A23-waiting-receiver-validation-2',passed=True,skipped=0,
            native_iokit_calls=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,
            build_manifest_sha256=self.ticket['build_manifest_sha256'],receiver_sha256=self.ticket['receiver_sha256'],
            device_binding_sha256=self.ticket['device_binding_sha256'],runtime_recipe_sha256=self.ticket['recipe_sha256']))
        b.seal(v);self.ticket.update(stage='prepared',remaining=1,acquisition_enabled=True,
            validation_directory=str(v),validation_manifest_sha256=b.sha(b.plain(v/'SHA256SUMS')))
        self.path.write_bytes(b.canonical(self.ticket))

    def receipt_run(self):
        run=self.work/'run';run.mkdir();b.write(run/'waiting-authorization.json',b.device.receipt(self.ticket));return run

    def fixture(self,mode,run,*extra):
        return self.native(mode,run,self.build,*extra,binary=self.review/'injected-loop')

    def packet(self,name='matching'):
        target=self.work/'packet';shutil.copytree(self.review/'collections'/name,target);return target

    def reseal(self,path):
        for n in ('SHA256SUMS','COMMITTED'):(path/n).unlink()
        b.seal(path)

    def test_record_description_and_native_guard_use_runtime_recipe(self):
        bound=self.record['device_binding'];self.assertNotEqual(bound['parent_input_digest'],bound['runtime_recipe_sha256'])
        self.assertEqual(self.record['recipe_sha256'],bound['runtime_recipe_sha256'])
        self.assertEqual(self.record['device_binding_sha256'],b.device.binding_hash(bound))
        self.assertTrue(b.device.supplied_material(bound,self.build/'device'))
        self.assertEqual(json.loads(self.native('--describe').stdout),b.description(bound))
        p=self.native('--check-build',self.build);self.assertEqual(p.returncode,0,p.stderr)
        checked=json.loads(p.stdout)
        for n in ('recipe_sha256','device_binding_sha256'):self.assertEqual(checked[n],self.record[n])
        self.assertEqual(checked['parent_input_digest'],bound['parent_input_digest'])
        self.assertEqual(checked['device_elf_sha256'],bound['device_elf_sha256'])

    def test_zero_use_record_is_rejected_before_lock_run_or_launch(self):
        before=self.path.read_bytes();runs=self.repo/'research/usb-ds-iso/private/runs';count=len(list(runs.iterdir()))
        with patch.object(gate.subprocess,'Popen') as launch:
            self.assertEqual(gate.capture(self.path,repo=self.repo,dry_run=True)['remaining'],0)
            with self.assertRaises(ValueError):gate.capture(self.path,repo=self.repo)
        launch.assert_not_called();self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(len(list(runs.iterdir())),count);self.assertFalse(self.path.with_suffix('.lock').exists())

    def test_old_record_and_parent_as_runtime_are_rejected(self):
        for fault in ('old-schema','parent','elf','binding'):
            row=copy.deepcopy(self.record)
            if fault=='old-schema':row['schema']='A23-waiting-receiver-record-1'
            elif fault=='parent':row['recipe_sha256']=row['device_binding']['parent_input_digest']
            elif fault=='elf':row['device_binding']['device_elf_sha256']='00'*32
            else:row['device_binding_sha256']='00'*32
            with self.subTest(fault=fault),self.assertRaises(ValueError):b.verify_build(row,self.repo)

    def test_native_wrong_receipt_layers_are_rejected_without_claim(self):
        run=self.receipt_run();original=b.device.receipt(self.ticket)
        for name in ('recipe_sha256','parent_input_digest','device_elf_sha256','device_binding_sha256','schema'):
            changed={**original,name:'00'*32};(run/'waiting-authorization.json').write_bytes(b.canonical(changed))
            p=self.native('--check-consumed',run,self.build);self.assertEqual(p.returncode,2,name)
            self.assertFalse((run/'WAIT_PROCESS_CLAIMED').exists());self.assertFalse((run/'host').exists())
        (run/'waiting-authorization.json').write_bytes(b.canonical(original))
        p=self.native('--check-consumed',run,self.build);self.assertEqual(p.returncode,0,p.stderr)

    def test_native_duplicate_and_partial_receipts_reject(self):
        run=self.receipt_run();raw=(run/'waiting-authorization.json').read_bytes()
        for bad in (raw[:100],b'[]\n',raw.replace(b'{',b'{"attempt_consumed":true,',1)):
            (run/'waiting-authorization.json').write_bytes(bad);self.assertEqual(self.native('--check-consumed',run,self.build).returncode,2)

    def test_native_live_source_and_device_drift_reject(self):
        for path in (self.repo/'research/usb-ds-iso/host/a23_device_binding_guard.inc',self.device/'full.elf',self.device/'recipe.json'):
            original=path.read_bytes()
            try:
                path.write_bytes(original+b' ')
                with self.assertRaises(ValueError):b.verify_build(self.record,self.repo)
                self.assertEqual(self.native('--check-build',self.build).returncode,2)
            finally:path.write_bytes(original)

    def test_resealed_generated_or_frozen_device_drift_cannot_pass_native_binding(self):
        for fault in ('generated/a23_waiting_burst_entry.m','device/full.elf','device-binding.json'):
            target=self.work/fault.replace('/','-');shutil.copytree(self.build,target)
            p=target/fault;p.write_bytes(p.read_bytes()+b' ');self.reseal(target)
            self.assertEqual(self.native('--check-build',target,binary=target/'receiver').returncode,2)

    def test_file_only_process_and_sdk_claims_are_single_use(self):
        run=self.receipt_run();self.assertEqual(self.fixture('--claim-sdk-only',run).returncode,2)
        self.assertEqual(self.fixture('--claim-process-only',run).returncode,0)
        marker=(run/'WAIT_PROCESS_CLAIMED').read_bytes();self.assertEqual(self.fixture('--claim-process-only',run).returncode,2)
        self.assertEqual((run/'WAIT_PROCESS_CLAIMED').read_bytes(),marker)
        self.assertEqual(self.fixture('--claim-sdk-only',run).returncode,0)
        claim=b.load(run/'WAIT_RECEIVER_CLAIMED');self.assertEqual(claim['recipe_sha256'],self.record['recipe_sha256'])
        self.assertEqual(claim['device_binding_sha256'],self.record['device_binding_sha256'])
        self.assertEqual(self.fixture('--claim-sdk-only',run).returncode,2);self.assertFalse((run/'host').exists())

    def test_handoff_rechecks_receipt_and_device_after_process_claim(self):
        run=self.receipt_run();p=self.native('--check-consumed',run,self.build);self.assertEqual(p.returncode,0,p.stderr)
        checked=self.work/'checked.json';checked.write_text(p.stdout)
        self.assertEqual(self.fixture('--claim-process-only',run).returncode,0)
        path=self.device/'full.elf';original=path.read_bytes()
        try:
            path.write_bytes(original+b' ');self.assertEqual(self.fixture('--claim-sdk-checked',run,checked).returncode,2)
        finally:path.write_bytes(original)
        receipt=b.load(run/'waiting-authorization.json');receipt['parent_input_digest']='00'*32
        (run/'waiting-authorization.json').write_bytes(b.canonical(receipt))
        self.assertEqual(self.fixture('--claim-sdk-checked',run,checked).returncode,2)
        self.assertFalse((run/'WAIT_RECEIVER_CLAIMED').exists())

    def test_matching_models_have_complete_software_chain_only(self):
        for name in ('matching','large-clock'):
            row=self.row(name);self.assertTrue(row['binding']['supplied_binding_consistent'])
            self.assertTrue(row['supplied_chain_complete'])
            self.assertEqual(row['waiting']['analysis']['expected_recipe'],self.record['recipe_sha256'])
        self.assertEqual(self.audit['collection_count'],16);self.assertEqual(self.audit['serializer_execution_count'],5)
        for packet in self.audit['collection_cases'].values():
            for flag in c.POLICY:self.assertIs(packet[flag],False);self.assertIs(packet['analysis'][flag],False)

    def test_bad_binding_cannot_inherit_inner_waiting_match(self):
        for name in ('parent-as-runtime','wrong-device-elf','wrong-binding','old-receipt','partial-receipt',
                     'duplicate-receipt','missing-process','process-mismatch','sdk-identity','missing-sdk-claim'):
            row=self.row(name);self.assertTrue(row['waiting']['analysis']['supplied_chain_complete'])
            self.assertFalse(row['binding']['supplied_binding_consistent']);self.assertFalse(row['supplied_chain_consistent'])

    def test_bad_execution_and_missing_primary_remain_distinct(self):
        for name in ('sequence-mismatch','shape-mismatch'):
            row=self.row(name);self.assertTrue(row['binding']['supplied_binding_consistent']);self.assertFalse(row['supplied_chain_consistent'])
        for name in ('primary-receipt-failure','missing-primary'):
            self.assertTrue(self.row(name)['supplied_chain_consistent']);self.assertFalse(self.row(name)['supplied_chain_complete'])

    def test_failed_receipt_bytes_are_preserved(self):
        for name in ('partial-receipt','duplicate-receipt'):
            self.assertEqual((self.review/'mock-runs'/name/'waiting-authorization.json').read_bytes(),
                (self.review/'collections'/name/'binding/waiting-authorization.json').read_bytes())

    def test_reanalysis_uses_frozen_files_and_packet_can_move(self):
        packet=self.packet();self.assertTrue(c.analyze(packet)['analysis']['supplied_chain_complete'])
        path=self.device/'full.elf';original=path.read_bytes()
        try:
            path.write_bytes(original+b' ');self.assertTrue(c.analyze(packet)['analysis']['supplied_chain_complete'])
        finally:path.write_bytes(original)

    def test_resealed_fake_analysis_and_recipe_are_rejected(self):
        packet=self.packet();p=packet/'analysis.json';value=b.load(p);value['same_physical_run_verified']=True
        p.write_bytes(b.canonical(value));self.reseal(packet)
        with self.assertRaises(ValueError):c.analyze(packet)

    def test_extra_or_symlinked_packet_files_cannot_be_resealed_into_acceptance(self):
        packet=self.packet();(packet/'binding/extra.json').write_text('{}\n');self.reseal(packet)
        with self.assertRaises(ValueError):c.analyze(packet)
        (packet/'binding/extra.json').unlink();(packet/'binding/link').symlink_to(self.build/'receiver')
        with self.assertRaises(ValueError):c.analyze(packet)

    def test_prepared_validation_must_bind_device_and_runtime(self):
        self.mock_issue();v=Path(self.ticket['validation_directory']);value=b.load(v/'validation.json');value['runtime_recipe_sha256']=self.ticket['device_binding']['parent_input_digest']
        (v/'validation.json').write_bytes(b.canonical(value));self.reseal(v)
        self.ticket['validation_manifest_sha256']=b.sha(b.plain(v/'SHA256SUMS'));self.path.write_bytes(b.canonical(self.ticket))
        with patch.object(gate.subprocess,'Popen') as launch,self.assertRaises(ValueError):gate.capture(self.path,repo=self.repo)
        launch.assert_not_called()

    def test_workflow_consumes_before_launch_failure_without_retry(self):
        self.mock_issue()
        def launch(command,**kwargs):
            self.assertEqual(b.load(self.path)['stage'],'consumed');run=Path(command[2]);receipt=b.load(run/'waiting-authorization.json')
            self.assertEqual(receipt,b.device.receipt(self.ticket));self.assertTrue(kwargs['start_new_session'])
            raise OSError('injected launch failure, receiver not launched')
        with patch.object(gate.subprocess,'Popen',side_effect=launch) as process:
            result=gate.capture(self.path,repo=self.repo)
            with self.assertRaises(ValueError):gate.capture(self.path,repo=self.repo)
        self.assertEqual(process.call_count,1);self.assertFalse(result['receiver_launched']);self.assertEqual(b.load(self.path)['remaining'],0)

    def test_receipt_write_failure_burns_mock_use_without_launch(self):
        self.mock_issue();original=b.write
        def write(path,value):
            if Path(path).name=='waiting-authorization.json':raise OSError('injected write failure')
            return original(path,value)
        with patch.object(gate.build,'write',side_effect=write),patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(OSError):gate.capture(self.path,repo=self.repo)
        launch.assert_not_called();self.assertEqual(b.load(self.path)['stage'],'consumed')

    def test_watchdog_preserves_pending_process(self):
        self.mock_issue();process=Mock(pid=700,wait=Mock(side_effect=subprocess.TimeoutExpired('mock',130)))
        with patch.object(gate.subprocess,'Popen',return_value=process):result=gate.capture(self.path,repo=self.repo)
        process.kill.assert_not_called();process.terminate.assert_not_called();process.send_signal.assert_not_called()
        self.assertTrue(result['receiver_left_running']);self.assertFalse((Path(result['run'])/'COMMITTED').exists())

    def test_mock_workflow_result_collects_with_the_same_runtime_identity(self):
        self.mock_issue()
        def launch(command,**kwargs):
            run=Path(command[2]);shutil.copytree(self.review/'native-fixtures/normal',run/'host')
            for name in ('WAIT_PROCESS_CLAIMED','WAIT_RECEIVER_CLAIMED'):
                shutil.copyfile(self.review/'mock-runs/matching'/name,run/name)
            (run/'MOCK_ONLY.txt').write_text('Launcher injected; copied file-only claim models. No receiver acquired.')
            return Mock(pid=701,wait=Mock(return_value=0))
        with patch.object(gate.subprocess,'Popen',side_effect=launch):result=gate.capture(self.path,repo=self.repo)
        self.assertTrue(result['host_observation_complete']);self.assertEqual(b.load(self.path)['stage'],'captured_logs_pending')
        run=Path(result['run']);packet=c.freeze(run/'host',self.review/'models/matching.execution.bin',self.work/'collected',
            self.path,run,self.review/'models/matching.primary.bin',self.repo)
        self.assertTrue(packet['analysis']['supplied_chain_complete'])
        for flag in c.POLICY:self.assertIs(packet[flag],False)

    def test_prior_sources_tickets_seals_and_zero_record_preserved(self):
        for n,h in self.audit['source_hashes'].items():self.assertEqual(b.sha(b.plain(self.repo/n)),h)
        for n,h in self.audit['tickets_sha256'].items():self.assertEqual(b.sha(b.plain(b.PARENT.parent/n)),h)
        self.assertEqual((self.record['remaining'],self.record['acquisition_enabled']),(0,False))
        for name in ('native_iokit_calls','real_sdk_objects','usb_requests','sd_accesses'):self.assertEqual(self.audit[name],0)
        self.assertFalse(self.audit['receiver_capture_invoked']);self.assertFalse(self.audit['attempt_issued'])
        self.assertEqual(self.audit['native_loop_case_count'],12)


if __name__=='__main__':unittest.main()
