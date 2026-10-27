import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import prepare_a23_lead32_once as once
import collect_a23_lead32_execution as collection
import analyze_io_usb_host_lead32 as sdk
from io_usb_host_lead32_policy import audit_admission

b=once.build;gate=once.gate


class Lead32WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-lead32-workflow-')
        cls.root=Path(cls.temp.name).resolve();cls.review=once.READINESS
        cls.result=b.load(cls.review/'audit.json');cls.source,cls.scope=once.materials()
        cls.deployment=b.ROOT/'private/deployments/20261016-191203-path-span-window-30s'
        cls.recovery=b.ROOT/'private/card-cycles/20261016-232422-path-span-first-live-read'

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.work=Path(tempfile.mkdtemp(dir=self.root));self.path=self.work/'A23-lead32-once-model.json'
        self.before=b.plain(once.OFFLINE)

    def tearDown(self):self.assertEqual(b.plain(once.OFFLINE),self.before)

    def row(self,name='matching'):return self.result['collection_cases'][name]['analysis']

    def issue(self):return once.prepare(self.path,issue=True,deployment=self.deployment,recovery=self.recovery)

    def test_preview_and_dry_run_are_zero_use(self):
        with patch.object(gate.subprocess,'Popen') as launch:
            r=once.prepare(self.path);d=gate.capture(once.OFFLINE,dry_run=True)
        self.assertEqual(r['remaining'],0);self.assertFalse(self.path.exists());self.assertEqual(d['remaining'],0);launch.assert_not_called()

    def test_offline_or_old_record_rejected_before_lock(self):
        with patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(ValueError):gate.capture(once.OFFLINE)
            old=b.ROOT/'private/analysis/A23-path-span-once-20261016-interface2.json'
            with self.assertRaises(ValueError):gate.capture(old)
        launch.assert_not_called();self.assertFalse(once.OFFLINE.with_suffix('.lock').exists())

    def test_issue_requires_both_saved_receipts(self):
        for kwargs in ({},{'deployment':self.deployment},{'recovery':self.recovery}):
            with self.assertRaises(ValueError):once.prepare(self.path,issue=True,**kwargs)
        self.assertFalse(self.path.exists())

    def test_old_device_deployment_rejected(self):
        old=b.ROOT/'private/deployments/20261016-015518-quiet-window-30s'
        with self.assertRaises(ValueError):once.prepare(self.path,issue=True,deployment=old,recovery=self.recovery)

    def test_saved_recovery_and_package_match_without_card_access(self):
        self.assertEqual(gate.verify_recovery(self.recovery,self.scope)['directory'],str(self.recovery))
        self.assertEqual(gate.verify_deployment(self.deployment,self.scope)['directory'],str(self.deployment))
        self.assertTrue(self.scope['device_package_reused'])

    def test_temporary_model_issue_and_dry_run_do_not_launch(self):
        with patch.object(gate.subprocess,'Popen') as launch:
            r=self.issue();d=gate.capture(self.path,dry_run=True)
        launch.assert_not_called();self.assertEqual(r['remaining'],1);self.assertEqual(d['remaining'],1)
        record=b.load(self.path);self.assertEqual(record['issuance']['recovery']['directory'],str(self.recovery))
        self.assertFalse(record['issuance']['automatic_retry'])

    def test_existing_or_partial_record_never_refilled(self):
        self.path.write_bytes(b'partial')
        with patch.object(once,'materials') as materials:
            with self.assertRaises(ValueError):self.issue()
        materials.assert_not_called();self.assertEqual(self.path.read_bytes(),b'partial')

    def test_project_seal_or_volume_cannot_be_record_target(self):
        for p in (self.review/'A23-lead32-once-x.json',Path('/Volumes/A23-lead32-once-x.json'),self.work/'wrong.json'):
            with self.assertRaises(ValueError):once.prepare(p)

    def test_old_plan_or_budget_tampering_refused_before_launch(self):
        self.issue();saved=b.load(self.path)
        for part in ('lead','reserve','workflow','recovery'):
            value=copy.deepcopy(saved)
            if part=='lead':value['plan']['sdk_plan']['first_frame_lead']=64
            if part=='reserve':value['plan']['sdk_plan']['runtime_budget']['reserve_ns']=16000000
            if part=='workflow':value['issuance']['scope']['workflow_source_hashes'][gate.WORKFLOW_FILES[0]]='00'*32
            if part=='recovery':value['issuance']['recovery']['manifest_sha256']='00'*32
            gate.replace(self.path,value)
            with patch.object(gate.subprocess,'Popen') as launch:
                with self.assertRaises(ValueError):gate.capture(self.path)
            launch.assert_not_called();self.assertEqual(b.load(self.path)['remaining'],1)

    def simulate(self,process=None,failure=None):
        repo=self.work/'repo';(repo/'research/usb-ds-iso/private/runs').mkdir(parents=True)
        with patch.object(gate,'prepared',return_value=Path(self.source['build'])),patch.object(gate.subprocess,'Popen',return_value=process,side_effect=failure) as launch:
            result=gate.capture(self.path,repo=repo)
        return result,launch

    def test_consumed_before_mock_launch_failure_and_no_retry(self):
        self.issue();r,launch=self.simulate(failure=OSError('injected launch failure'))
        self.assertEqual(launch.call_count,1);self.assertEqual(r['remaining'],0)
        self.assertEqual(b.load(self.path)['stage'],'failed_no_retry')
        with patch.object(gate.subprocess,'Popen') as again:
            with self.assertRaises(ValueError):gate.capture(self.path)
        again.assert_not_called()

    def test_receipt_write_failure_burns_use_before_launch(self):
        self.issue();repo=self.work/'repo';(repo/'research/usb-ds-iso/private/runs').mkdir(parents=True)
        original=b.write
        def fail(path,value):
            if path.name=='waiting-authorization.json':raise OSError('injected receipt failure')
            return original(path,value)
        with patch.object(gate,'prepared',return_value=Path(self.source['build'])),patch.object(b,'write',side_effect=fail),patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(OSError):gate.capture(self.path,repo=repo)
        launch.assert_not_called();self.assertEqual(b.load(self.path)['remaining'],0)

    def test_watchdog_keeps_unresolved_mock_process(self):
        self.issue();process=Mock(pid=12345);process.wait.side_effect=subprocess.TimeoutExpired('injected',130)
        r,_=self.simulate(process=process)
        self.assertEqual(r['stage'],'unresolved_no_retry');self.assertEqual(b.load(self.path)['remaining'],0)
        process.kill.assert_not_called();process.terminate.assert_not_called();self.assertFalse((Path(r['run'])/'COMMITTED').exists())

    def test_exit_zero_without_host_material_cannot_pass(self):
        self.issue();r,_=self.simulate(process=Mock(wait=Mock(return_value=0)))
        self.assertFalse(r['host_observation_complete']);self.assertEqual(b.load(self.path)['stage'],'failed_no_retry')

    def test_complete_supplied_chain_is_only_content_agreement(self):
        row=self.row();self.assertTrue(row['supplied_chain_complete'])
        for flag in collection.POLICY:self.assertIs(row[flag],False)

    def test_missing_and_partial_materials_remain_incomplete(self):
        for name in ('missing-execution','missing-primary','missing-both','truncated-header','partial-after-context','bad-tail-crc','bad-header-crc'):
            self.assertFalse(self.row(name)['supplied_chain_complete'],name)

    def test_lifecycle_context_and_ambiguity_not_automatically_resolved(self):
        row=self.row('multiple-lifecycle');self.assertTrue(row['lifecycle']['selection_ambiguous'])
        self.assertFalse(row['lifecycle']['supplied_context_associated'])
        for name in ('prepared','quiet','before-context','wrong-recipe','wrong-writer','wrong-frequency','different-nonce'):
            self.assertFalse(self.row(name)['supplied_chain_complete'],name)

    def test_failed_binding_and_primary_mismatch_never_complete(self):
        for name in ('old-receipt','wrong-lead','wrong-npdm','missing-process','sdk-mismatch','duplicate-receipt'):
            self.assertFalse(self.row(name)['binding']['supplied_binding_consistent'],name)
        for name in ('sequence-mismatch','shape-mismatch','primary-receipt-failure','primary-mismatch'):
            self.assertFalse(self.row(name)['supplied_chain_complete'],name)

    def test_collection_can_move_without_live_build_lookup(self):
        folder=self.work/'packet';shutil.copytree(self.review/'collections/matching',folder)
        with patch.object(b,'verify_build',side_effect=AssertionError('live build read')):
            self.assertTrue(collection.analyze(folder)['analysis']['supplied_chain_complete'])
        (folder/'extra').write_bytes(b'x')
        with self.assertRaises(ValueError):collection.analyze(folder)

    def test_new_sdk_analysis_rejects_original64_journal(self):
        old=b.ROOT/'private/runs/A-A23-path-span-waiting-20261016-152211-7e95b3a8/host'
        with self.assertRaises(ValueError):sdk.analyze(old)

    def test_budget_equal_boundary_and_first_overrun(self):
        frame=dict(begin_ticks=100,end_ticks=200,timebase_numerator=1,timebase_denominator=1)
        for age,call,passed in ((4000000,2000000,True),(4000001,0,False),(4000000,2000001,False)):
            admitted=age<=4000000;ret=100+age+(call if admitted else 0)
            d=dict(source='sdk_runtime_budget',check_ticks=100+age,return_ticks=ret,query_ns=100,age_ns=age,
                call_ns=call if admitted else 0,timebase_numerator=1,timebase_denominator=1,converted=True,duration_valid=True,
                admitted=admitted,forwarded=admitted,accepted=admitted,budget_pass=passed)
            self.assertEqual(audit_admission(d,frame,hardware=True),passed)

    def test_independent_modules_do_not_change_old_inputs(self):
        self.assertEqual(len(self.result['source_hashes']),251)
        self.assertEqual(self.result['collection_count'],28)
        self.assertEqual(len(self.result['native_cases']['driver-models']),34)
        self.assertEqual(len(self.result['native_cases']['loop-models']),12)


if __name__=='__main__':unittest.main()
