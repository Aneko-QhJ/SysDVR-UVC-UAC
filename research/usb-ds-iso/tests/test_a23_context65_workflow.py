import copy
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import context65_workflow as w
import context65_once_reservation as reservations
import prepare_a23_context65_once as once
from workflows import capture_a23_context65_receiver as gate
import context65_recovery as recovery
import collect_a23_context65_once as collection
import a23_execution_context as context

REVIEW=w.A/'A23-context65-receiver-review-20261017-r3'
DEPLOYMENT=w.ROOT/'private/deployments/20261016-191203-path-span-window-30s'
LIFE='ep0-life-'+('03'+'00'*15)+'.bin'


def baseline(root,*,restore=True):
    card_root=root/'card';shutil.copytree(w.ANCHOR/'card',card_root)
    if restore:
        flag=card_root/'atmosphere/contents/00FF0000A53BB666/flags/boot2.flag';flag.write_bytes(b'')
    snapshot=root/'snapshot';w.card.recover(w.card.DirectoryCard(card_root,readonly=True),snapshot,eject_after=True)
    return snapshot


def positive_runner(command,run,record):
    shutil.copytree(REVIEW/'loop-models/normal',run/'host')
    w.write(run/'execution-context.json',context.model(record['receiver_sha256'],Path(record['build'])/'receiver'))
    for mode in ('--claim-process-only','--claim-sdk-only'):
        subprocess.run([str(REVIEW/'injected-loop'),mode,str(run),record['build']],check=True,capture_output=True)
    return Mock(pid=123,wait=Mock(return_value=0))


class Context65WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-context65-flow-');cls.root=Path(cls.temp.name).resolve()
        cls.source,cls.scope=w.materials();cls.base=baseline(cls.root/'baseline')
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.work=Path(tempfile.mkdtemp(dir=self.root));self.path=self.work/'A23-context65-once-model.json';self.ledger=self.work/'ledger'
        self.protected=w.load(w.A/'A23-context65-receiver-closeout-20261017/closeout.json')['protected_sha256']
    def tearDown(self):
        for n,h in self.protected.items():self.assertEqual(w.sha(w.plain(Path(n))),h,n)
        self.assertFalse((w.LEDGER/'block-00065.json').exists())
    def issue(self):return once.prepare(self.path,issue=True,deployment=DEPLOYMENT,recovery=self.base,ledger=self.ledger)
    def consume(self,runner=positive_runner):
        runs=self.work/'runs';runs.mkdir(exist_ok=True);return gate.capture(self.path,_model_runner=runner,_model_runs=runs)
    def failed(self):return self.consume(lambda *args:Mock(pid=123,wait=Mock(return_value=0)))
    def test_preview_is_read_only(self):
        value=once.prepare(self.path,ledger=self.ledger);self.assertEqual(value['remaining'],0)
        self.assertFalse(self.path.exists());self.assertFalse(self.ledger.exists());self.assertFalse(value['issuance_available'])
    def test_formal_preview_blocked_by_missing_flag(self):
        path=w.A/'A23-context65-once-preview-test.json'
        value=once.prepare(path,deployment=DEPLOYMENT,recovery=w.ANCHOR)
        self.assertFalse(value['issuance_available']);self.assertFalse(path.exists());self.assertTrue(value['blockers'])
    def test_old_success_not_a_fresh_baseline(self):
        old=w.ROOT/'private/card-cycles/20261017-133944-lead32-repeat1-live-read'
        with self.assertRaises(ValueError):w.verify_recovery(old,self.scope)
    def test_missing_flag_refused_before_burn(self):
        bad=baseline(self.work/'bad',restore=False)
        with self.assertRaises(ValueError):once.prepare(self.path,issue=True,deployment=DEPLOYMENT,recovery=bad,ledger=self.ledger)
        self.assertFalse(self.ledger.exists())
    def test_model_cannot_use_formal_ledger(self):
        with self.assertRaises(ValueError):once.prepare(self.path,ledger=w.LEDGER)
    def test_new_record_issued_only_in_model(self):
        result=self.issue();self.assertEqual(result['remaining'],1);record=w.load(self.path)
        self.assertTrue(record['issuance']['reservation']['simulation']);self.assertEqual(record['issuance']['scope']['first_sequence'],65)
        gate.capture(self.path,dry_run=True);self.assertEqual(w.load(self.path)['remaining'],1)
    def test_dry_run_does_not_probe_environment_or_launch(self):
        self.issue()
        with patch.object(gate,'environment',side_effect=AssertionError('probe')),patch.object(gate.subprocess,'Popen') as launch:
            gate.capture(self.path,dry_run=True)
        launch.assert_not_called()
    def test_offline_dry_run_never_issues(self):
        with patch.object(gate.subprocess,'Popen') as launch:result=gate.capture(w.OFFLINE,dry_run=True)
        self.assertEqual(result['remaining'],0);launch.assert_not_called()
    def test_offline_capture_and_old49_rejected(self):
        for path in (w.OFFLINE,w.A/'A23-sequence-once-20261017-interface2.json'):
            with self.assertRaises(ValueError):gate.capture(path)
    def test_model_cannot_launch_real_receiver(self):
        self.issue()
        with patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(ValueError):gate.capture(self.path)
        launch.assert_not_called();self.assertEqual(w.load(self.path)['remaining'],1)
    def test_existing_partial_target_never_refilled(self):
        self.path.write_bytes(b'partial')
        with self.assertRaises(ValueError):self.issue()
        self.assertFalse(self.ledger.exists());self.assertEqual(self.path.read_bytes(),b'partial')
    def test_burn_prevents_second_record(self):
        self.issue();other=self.work/'A23-context65-once-other.json'
        with self.assertRaises(ValueError):once.prepare(other,issue=True,deployment=DEPLOYMENT,recovery=self.base,ledger=self.ledger)
        self.assertFalse(other.exists())
    def test_failed_record_write_keeps_burn(self):
        original=w.write
        def fault(path,value):
            if path==self.path:raise OSError('injected record write')
            return original(path,value)
        with patch.object(w,'write',side_effect=fault):
            with self.assertRaises(OSError):self.issue()
        self.assertTrue((self.ledger/'block-00065.json').exists());self.assertFalse(self.path.exists())
        with self.assertRaises(ValueError):self.issue()
    def test_truncated_burn_refused(self):
        self.issue();(self.ledger/'block-00065.json').write_bytes(b'{')
        with self.assertRaises(ValueError):gate.capture(self.path,dry_run=True)
    def test_unknown_ledger_artifact_refused(self):
        self.ledger.mkdir();(self.ledger/'unknown').write_bytes(b'x')
        with self.assertRaises(ValueError):self.issue()
    def test_lock_contention_refused(self):
        self.ledger.mkdir()
        with (self.ledger/'.lock').open('w') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.issue()
        self.assertFalse((self.ledger/'block-00065.json').exists())
    def test_copied_record_and_changed_preparation_refused(self):
        self.issue();other=self.work/'A23-context65-once-copy.json';shutil.copyfile(self.path,other)
        with self.assertRaises(ValueError):gate.capture(other,dry_run=True)
        value=w.load(self.path);value['preparation_id']='11111111-1111-4111-8111-111111111111';w.replace(self.path,value)
        with self.assertRaises(ValueError):gate.capture(self.path,dry_run=True)
    def test_scope_or_budget_drift_refused(self):
        self.issue();original=w.load(self.path)
        for key in ('source','budget','baseline'):
            value=copy.deepcopy(original)
            if key=='source':value['issuance']['scope']['source_hashes'][next(iter(value['issuance']['scope']['source_hashes']))]='00'*32
            if key=='budget':value['plan']['sdk_plan']['first_frame_lead']=64
            if key=='baseline':value['issuance']['recovery']['manifest_sha256']='00'*32
            w.replace(self.path,value)
            with self.assertRaises(ValueError):gate.capture(self.path,dry_run=True)
    def test_launch_failure_consumes_and_keeps_lock(self):
        self.issue()
        def fail(*args):raise OSError('injected launch failure')
        result=self.consume(fail);self.assertEqual(result['remaining'],0);self.assertEqual(w.load(self.path)['stage'],'failed_no_retry')
        self.assertTrue(self.path.with_suffix('.lock').exists())
        with self.assertRaises(ValueError):self.consume(fail)
    def test_receipt_write_failure_consumes_before_launch(self):
        self.issue();original=w.write
        def fault(path,value):
            if path.name=='waiting-authorization.json':raise OSError('receipt write')
            return original(path,value)
        runner=Mock()
        with patch.object(w,'write',side_effect=fault):
            with self.assertRaises(OSError):self.consume(runner)
        runner.assert_not_called();self.assertEqual(w.load(self.path)['remaining'],0)
    def test_timeout_keeps_live_process_unsealed(self):
        self.issue();process=Mock(pid=123);process.wait.side_effect=subprocess.TimeoutExpired('injected',130)
        result=self.consume(lambda *args:process);self.assertEqual(result['stage'],'unresolved_no_retry')
        process.kill.assert_not_called();process.terminate.assert_not_called();self.assertFalse((Path(result['run'])/'COMMITTED').exists())
        with self.assertRaises(ValueError):recovery.ready(self.path)
    def test_exit_zero_without_material_is_not_success(self):
        self.issue();result=self.failed();self.assertFalse(result['host_observation_complete']);self.assertEqual(w.load(self.path)['remaining'],0)
    def test_positive_model_preserves_claims_and_environment(self):
        self.issue();result=self.consume();self.assertTrue(result['host_observation_complete'])
        record=w.load(self.path);self.assertEqual(record['launch_environment']['requested_execution_mode'],'injected_model');w.verify_scope(record,self.path)
    def test_only_owned_mutation_is_admitted(self):
        self.issue();record=w.load(self.path);reservations.verify(record['issuance']['reservation'],self.path,record)
        changed=copy.deepcopy(record);changed['issuance']['scope']['first_sequence']=81
        with self.assertRaises(ValueError):reservations.verify(record['issuance']['reservation'],self.path,changed)
        self.assertTrue(w.transition(record,self.path)['unrelated_history_unchanged'])
    def test_fresh_baseline_preserves_all59_originals(self):
        fresh=self.work/'fresh';shutil.copytree(self.base/'card',fresh/'card');(fresh/'card/logfile.txt').write_bytes(b'changed')
        snap=fresh/'snapshot';w.card.recover(w.card.DirectoryCard(fresh/'card',readonly=True),snap,eject_after=True)
        with self.assertRaises(ValueError):w.verify_recovery(snap,self.scope,simulation=True)
    def test_writable_recovery_refused_without_pending_clear(self):
        self.issue();self.failed();root=self.work/'postcard';shutil.copytree(self.base/'card',root)
        with self.assertRaises(ValueError):recovery.recover(self.path,w.card.DirectoryCard(root),self.work/'postread')
        self.assertTrue(w.load(self.path)['device_log_pending'])
    def test_readonly_model_recovery_ejects_and_closes(self):
        self.issue();self.failed();root=self.work/'postcard';shutil.copytree(self.base/'card',root)
        result=recovery.recover(self.path,w.card.DirectoryCard(root,readonly=True),self.work/'postread')
        self.assertTrue(result['recovery_receipt_accepted']);self.assertTrue(w.load(self.path)['recovered'])
        with self.assertRaises(ValueError):recovery.ready(self.path)
    def test_mismatch_snapshot_saved_without_acceptance(self):
        self.issue();self.failed();root=self.work/'postcard';shutil.copytree(self.base/'card',root)
        (root/'atmosphere/contents/00FF0000A53BB666/flags/boot2.flag').unlink()
        result=recovery.recover(self.path,w.card.DirectoryCard(root,readonly=True),self.work/'postread')
        value=w.load(self.path);self.assertFalse(result['recovery_receipt_accepted']);self.assertTrue(value['card_snapshot_saved'])
        self.assertFalse(value['device_log_pending']);self.assertFalse(value['recovered']);self.assertEqual(value['remaining'],0)
    def test_attached_model_rejected_before_disk_access(self):
        self.issue();self.failed()
        with patch.object(recovery.subprocess,'check_output') as disk:
            with self.assertRaises(ValueError):recovery.attached(self.path,self.work/'job',shutdown_card_connected=True)
        disk.assert_not_called()
    def test_attached_requires_confirmation_before_any_access(self):
        with patch.object(recovery.subprocess,'check_output') as disk:
            with self.assertRaises(ValueError):recovery.attached(self.path,self.work/'job')
        disk.assert_not_called()

    def test_parent_sandbox_rejected_before_consumption(self):
        self.issue();record=w.load(self.path);record['issuance']['reservation']['simulation']=False
        # Inject only the formal branch result; no formal record is created.
        with patch.object(gate,'prepared',return_value=(record,Path(record['build']))),patch.object(gate,'environment',return_value=dict(sandbox_query_result=1,sandbox_query_errno=0)),patch.object(gate.subprocess,'Popen') as launch:
            with self.assertRaises(ValueError):gate.capture(self.path,execution_mode='require_escalated')
        launch.assert_not_called();self.assertEqual(w.load(self.path)['remaining'],1);self.assertFalse(self.path.with_suffix('.lock').exists())
    def test_recovery_job_preparation_does_not_access_disk(self):
        self.issue();self.failed()
        with patch.object(recovery.subprocess,'check_output') as disk:
            value=recovery.prepare_job(self.path,self.work/'job',self.work/'future-snapshot')
        self.assertTrue(value['scripts_prepared_only']);self.assertFalse((self.work/'future-snapshot').exists());disk.assert_not_called()
    def test_record_changes_not_silently_accepted(self):
        self.issue();record=w.load(self.path);changed=copy.deepcopy(record);changed['extra']='changed';w.replace(self.path,changed)
        with self.assertRaises(ValueError):w.transition(record,self.path)
    def test_collection_checks_portable_reservation_and_launch(self):
        self.issue();result=self.consume();run=Path(result['run']);target=self.work/'collection'
        life=self.work/LIFE;shutil.copyfile(REVIEW/'models/joined.bin',life)
        value=collection.freeze(run/'host',target,self.path,run,[life],REVIEW/'models/matching.execution.bin',REVIEW/'models/matching.primary.bin')
        self.assertTrue(value['analysis']['supplied_chain_complete']);shutil.rmtree(self.ledger)
        self.assertTrue(collection.analyze(target)['analysis']['reservation_commitment_consistent'])
        cli=subprocess.run([sys.executable,str(w.ROOT/'tools/collect_a23_context65_once.py'),'analyze',str(target)],check=True,capture_output=True)
        self.assertTrue(json.loads(cli.stdout)['analysis']['supplied_chain_complete'])
        (target/'binding/reservation.json').unlink()
        value=collection.analyze_inputs(target,self.source['recipe_sha256'])
        self.assertFalse(value['reservation_commitment_consistent']);self.assertFalse(value['supplied_chain_complete'])
    def test_collection_rejects_altered_commitment_and_issuance(self):
        self.issue();result=self.consume();run=Path(result['run']);target=self.work/'collection'
        collection.freeze(run/'host',target,self.path,run)
        original=w.load(target/'binding/record.json')
        for key in ('recovery','maximum_invocations'):
            changed=copy.deepcopy(original)
            if key=='recovery':changed['issuance'][key]['manifest_sha256']='0'*64
            else:changed['issuance'][key]=2
            (target/'binding/record.json').write_bytes(w.b.canonical(changed))
            value=collection.analyze_inputs(target,self.source['recipe_sha256'])
            self.assertFalse(value['reservation_commitment_consistent']);self.assertFalse(value['supplied_chain_complete'])
    def test_boolean_invocation_limit_is_not_an_integer_limit(self):
        self.issue();record=w.load(self.path);record['issuance']['maximum_invocations']=True;w.replace(self.path,record)
        with self.assertRaises(ValueError):w.verify_scope(record,self.path)
    def test_owned_formal_transition_on_disposable_history_clone(self):
        self.issue();record=w.load(self.path);root=self.work/'history';runs=root/'runs'
        shutil.copytree(w.b.device.history.SCOPE/'runs',runs);ledger=root/'ledger';shutil.copytree(self.ledger,ledger)
        shutil.copyfile(w.LEDGER/'block-00049.json',ledger/'block-00049.json')
        burn=ledger/'block-00065.json';value=w.load(burn);value['simulation']=False;burn.write_bytes(w.b.canonical(value))
        receipt=record['issuance']['reservation'];receipt.update(directory=str(ledger),path=str(burn),sha256=w.sha(w.plain(burn)),simulation=False)
        w.replace(self.path,record)
        with patch.object(w,'LEDGER',ledger),patch.object(reservations,'location',return_value=(self.path,ledger,False)):
            self.assertTrue(w.transition(record,self.path,runs_root=runs,ledger=ledger)['owned_reservation_excluded'])
            own=runs/('A-context65-waiting-'+record['preparation_id']);own.mkdir();(own/'partial.json').write_bytes(b'{')
            record['run']=str(own);w.replace(self.path,record)
            with self.assertRaises(ValueError):w.transition(record,self.path,runs_root=runs,ledger=ledger)
            record.update(stage='consumed',remaining=0,acquisition_enabled=False);w.replace(self.path,record)
            self.assertTrue(w.transition(record,self.path,runs_root=runs,ledger=ledger)['owned_run_excluded'])
            foreign=runs/'A-context81-waiting-foreign';foreign.mkdir();(foreign/'x').write_bytes(b'x')
            with self.assertRaises(ValueError):w.transition(record,self.path,runs_root=runs,ledger=ledger)
            shutil.rmtree(foreign);historical=next(p for p in runs.rglob('*') if p.is_file() and not p.is_relative_to(own));historical.write_bytes(b'changed')
            with self.assertRaises(ValueError):w.transition(record,self.path,runs_root=runs,ledger=ledger)

if __name__=='__main__':unittest.main()
