"""Offline packaging and one-use workflow, only disposable modeled deployments."""
import copy,json,shutil,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import prepare_a23_path_span_once as once
pkg=once.package;b=once.build;gate=once.gate


def deployment_model(root,scope):
    root.mkdir()
    b.write(root/'deployment.json',dict(schema='A23-path-span-card-deployment-1',artifact_origin='injected_saved_receipt_model',
        sd_uuid=gate.SD_UUID,whole_disk='disk42',card_write_readback_verified=True,attempt_issued=False,remaining=0,usb_test_invocations=0,
        package_manifest_sha256=scope['package_manifest_sha256'],device_binding_sha256=scope['device_binding_sha256'],source_package=scope['package_directory'],
        after=[dict(path=n,size=row['bytes'],sha256=row['sha256']) for n,row in scope['deployment_files'].items()]))
    b.write(root/'eject.json',dict(device='disk42',ejected=True,mount_absent=True));b.seal(root);return root


class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-life-preparation-');cls.root=Path(cls.temp.name)
        cls.package=cls.root/'package';cls.report=pkg.build(cls.package)
        cls.source,cls.scope=once.materials()
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.work=Path(tempfile.mkdtemp(dir=self.root));self.path=self.work/'A23-path-span-once-model.json'
        self.before=b.plain(once.OFFLINE);self.deployment=deployment_model(self.work/'deployment',self.scope)
    def tearDown(self):self.assertEqual(b.plain(once.OFFLINE),self.before)
    def reseal(self,path):
        for n in ('SHA256SUMS','COMMITTED'):(path/n).unlink()
        b.seal(path)
    def issue(self):return once.prepare(self.path,issue=True,deployment=self.deployment)
    def test_exact_sealed_elf_nso_npdm_and_four_files(self):
        self.assertEqual(pkg.pfs_files(b.plain(self.package/'exefs.nsp')),{'main':b.plain(self.package/'exefs/main'),'main.npdm':b.plain(pkg.DEVICE/'main.npdm')})
        self.assertEqual(self.report['device_binding'],self.source['device_binding']);self.assertTrue(self.report['firmware_packaged'])
        self.assertFalse(self.report['deployed']);self.assertEqual(self.report['remaining'],0)
        self.assertEqual(pkg.verify_review(self.package)['exefs_nsp_sha256'],self.report['exefs_nsp_sha256'])
    def test_rollback_is_last_recovered_lifecycle(self):
        name=pkg.CONTENT+'exefs.nsp';before=b.plain(self.package/'rollback-review'/name)
        self.assertEqual(b.sha(before),'bca717b0db12c0287c5859afc58235d19b83622a6e08a4fc679caf6aaef6d2a5')
        self.assertNotEqual(before,b.plain(self.package/'sd-review'/name))
        self.assertEqual(self.report['card_recovery_manifest_sha256'],b.sha(b.plain(pkg.CARD/'SHA256SUMS')))
    def test_container_corruption_and_wrong_stack_rejected(self):
        raw=b.plain(self.package/'exefs.nsp')
        for mutant in (raw[:63],raw[:-1],raw+b'x'):
            with self.assertRaises((ValueError,struct.error)):pkg.pfs_files(mutant)
        raw=bytearray(b.plain(pkg.DEVICE/'main.npdm'));raw[29]^=1
        with self.assertRaises(ValueError):pkg.verify_npdm(bytes(raw))
        raw=bytearray(b.plain(self.package/'exefs/main'));raw[0xa0]^=1
        with self.assertRaises(ValueError):pkg.verify_nso(b.plain(pkg.DEVICE/'full.elf'),bytes(raw))
    def test_package_output_cannot_target_card_or_extend_seal(self):
        for path in (self.package,once.PACKAGE/'new',Path('/Volumes/offline-review'),Path('/tmp/offline-review')):
            with self.assertRaises(ValueError):pkg.output_path(path)
    def test_preview_no_record_no_process_no_deployment_required(self):
        with patch.object(gate.subprocess,'Popen') as launch:result=once.prepare(self.path)
        self.assertEqual(result['remaining'],0);self.assertFalse(result['record_written']);self.assertFalse(self.path.exists());launch.assert_not_called()
    def test_default_offline_record_rejected_before_lock_or_launch(self):
        with patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(ValueError):gate.capture(once.OFFLINE)
        launch.assert_not_called();self.assertFalse(once.OFFLINE.with_suffix('.lock').exists())
    def test_issue_requires_new_matching_deployment(self):
        with self.assertRaises(ValueError):once.prepare(self.path,issue=True)
        old=b.ROOT/'private/deployments/20261016-015518-quiet-window-30s'
        with self.assertRaises(ValueError):once.prepare(self.path,issue=True,deployment=old)
        self.assertFalse(self.path.exists())
    def test_temporary_model_issue_and_dry_run_never_launch(self):
        with patch.object(gate.subprocess,'Popen') as launch:
            self.issue();row=b.load(self.path);checked=gate.capture(self.path,dry_run=True)
        launch.assert_not_called();self.assertEqual(checked['remaining'],1)
        self.assertEqual(row['issuance']['deployment']['directory'],str(self.deployment))
        self.assertNotEqual(row['preparation_id'],self.source['preparation_id']);self.assertFalse(row['issuance']['automatic_retry'])
    def test_existing_consumed_and_partial_records_never_refill(self):
        self.issue()
        for stage in ('prepared','failed_no_retry','unresolved_no_retry'):
            row=b.load(self.path);row.update(stage=stage,remaining=0,acquisition_enabled=False);self.path.write_bytes(b.canonical(row));before=self.path.read_bytes()
            with self.assertRaises(ValueError):self.issue()
            self.assertEqual(self.path.read_bytes(),before)
        self.path.write_bytes(b'{partial')
        with self.assertRaises(ValueError):self.issue()
        self.assertEqual(self.path.read_bytes(),b'{partial')
    def test_bad_destination_or_nonboolean_issue_rejects_early(self):
        for path in (once.OFFLINE,once.PACKAGE/'A23-path-span-once-new.json',Path('/Volumes/A23-path-span-once-new.json'),self.path.with_name('A23-quiet-once-old.json')):
            with patch.object(once,'materials') as materials,self.assertRaises(ValueError):once.prepare(path,issue=True,deployment=self.deployment)
            materials.assert_not_called()
        with self.assertRaises(ValueError):once.prepare(self.path,issue=1,deployment=self.deployment)
    def test_changed_materials_and_exclusive_race_preserve_others(self):
        changed={**self.scope,'exefs_nsp_sha256':'00'*32}
        with patch.object(once,'materials',side_effect=[(self.source,self.scope),(self.source,changed)]):
            with self.assertRaises(ValueError):self.issue()
        self.assertFalse(self.path.exists())
        original=b.write
        def race(path,value):path.write_bytes(b'other');return original(path,value)
        with patch.object(b,'write',side_effect=race),self.assertRaises(FileExistsError):self.issue()
        self.assertEqual(self.path.read_bytes(),b'other')
    def test_saved_deployment_uuid_readback_and_ejection_are_required(self):
        value=b.load(self.deployment/'deployment.json');eject=b.load(self.deployment/'eject.json')
        for fault in ('uuid','package','duplicate','stack-type','eject','wrong-disk','malformed-disk'):
            row=copy.deepcopy(value);out=dict(eject)
            if fault=='uuid':row['sd_uuid']='wrong'
            if fault=='package':row['package_manifest_sha256']='00'*32
            if fault=='duplicate':row['after'][1]=row['after'][0]
            if fault=='stack-type':row['after'][0]['size']=True
            if fault=='eject':out['mount_absent']=False
            if fault=='wrong-disk':out['device']='disk43'
            if fault=='malformed-disk':row['whole_disk']='../disk42'
            (self.deployment/'deployment.json').write_bytes(b.canonical(row));(self.deployment/'eject.json').write_bytes(b.canonical(out));self.reseal(self.deployment)
            with self.assertRaises(ValueError):self.issue()
        self.assertFalse(self.path.exists())
    def test_deployment_changed_after_issuance_rejected_before_lock(self):
        self.issue();path=self.deployment/'deployment.json';value=b.load(path);value['sd_uuid']='wrong';path.write_bytes(b.canonical(value));self.reseal(self.deployment)
        with patch.object(gate.subprocess,'Popen') as launch,self.assertRaises(ValueError):gate.capture(self.path)
        launch.assert_not_called();self.assertEqual(b.load(self.path)['remaining'],1);self.assertFalse(self.path.with_suffix('.lock').exists())
    def test_scope_workflow_and_package_mismatch_reject_before_launch(self):
        self.issue();original=b.load(self.path)
        for fault in ('workflow','package','retry','stack'):
            row=copy.deepcopy(original)
            if fault=='workflow':row['issuance']['scope']['workflow_source_hashes'][gate.WORKFLOW_FILES[0]]='00'*32
            if fault=='package':row['issuance']['scope']['exefs_nsp_sha256']='00'*32
            if fault=='retry':row['issuance']['automatic_retry']=True
            if fault=='stack':row['device_binding']['main_thread_stack_request_bytes']=True
            self.path.write_bytes(b.canonical(row))
            with patch.object(gate.subprocess,'Popen') as launch,self.assertRaises(ValueError):gate.capture(self.path)
            launch.assert_not_called();self.assertEqual(b.load(self.path)['remaining'],1)
    def simulate_capture(self,process=None,failure=None):
        repo=self.work/'repo';(repo/'research/usb-ds-iso/private/runs').mkdir(parents=True)
        with patch.object(gate,'prepared',return_value=Path(self.source['build'])),patch.object(gate.subprocess,'Popen',return_value=process,side_effect=failure) as launch:
            result=gate.capture(self.path,repo=repo)
        return result,launch
    def test_consume_before_mock_launch_error_and_no_retry(self):
        self.issue();row,launch=self.simulate_capture(failure=OSError('injected launch failure'))
        self.assertEqual(launch.call_count,1);self.assertEqual(row['remaining'],0)
        self.assertEqual(b.load(self.path)['stage'],'failed_no_retry')
        with patch.object(gate.subprocess,'Popen') as again,self.assertRaises(ValueError):gate.capture(self.path)
        again.assert_not_called()
    def test_receipt_write_error_burns_model_use_before_launch(self):
        self.issue();repo=self.work/'repo';(repo/'research/usb-ds-iso/private/runs').mkdir(parents=True);original=b.write
        def fail(path,value):
            if path.name=='waiting-authorization.json':raise OSError('injected receipt failure')
            return original(path,value)
        with patch.object(gate,'prepared',return_value=Path(self.source['build'])),patch.object(b,'write',side_effect=fail),patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(OSError):gate.capture(self.path,repo=repo)
        launch.assert_not_called();self.assertEqual(b.load(self.path)['remaining'],0);self.assertEqual(b.load(self.path)['stage'],'failed_no_retry')
    def test_watchdog_retains_mock_process_and_does_not_seal_live_output(self):
        self.issue();process=Mock(pid=12345);process.wait.side_effect=subprocess.TimeoutExpired('modeled',130)
        row,_=self.simulate_capture(process=process)
        self.assertEqual(row['stage'],'unresolved_no_retry');self.assertEqual(b.load(self.path)['remaining'],0)
        process.kill.assert_not_called();process.terminate.assert_not_called();self.assertFalse((Path(row['run'])/'COMMITTED').exists())
    def test_process_exit_without_host_evidence_never_passes(self):
        self.issue();row,_=self.simulate_capture(process=Mock(wait=Mock(return_value=0)))
        self.assertFalse(row['host_observation_complete']);self.assertEqual(b.load(self.path)['stage'],'failed_no_retry')
        self.assertFalse(row['hardware_verified']);self.assertEqual(b.load(self.path)['remaining'],0)

if __name__=='__main__':unittest.main()
