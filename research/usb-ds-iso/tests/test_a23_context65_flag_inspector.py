"""Read-only inspection of saved job fixtures, never a card or running PID."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import inspect_a23_context65_flag_card as inspector
a=inspector.adapter;w=inspector.w
REVIEW=w.A/'A23-context65-flag-card-review-20261018-r3'
READY=inspector.PARENT/'prepared-job'


class InspectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-card-inspector-');cls.root=Path(cls.temp.name).resolve()
        cls.sources=a.source_hashes();cls.protected=w.load(inspector.PARENT/'closeout.json')['protected_sha256']
        cls.owner=w.A/'A23-context65-flag-card-volume-owner.json'
        cls.owner_before=cls.owner.read_bytes() if cls.owner.exists() else None
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.work=self.root/str(len(list(self.root.iterdir())));self.work.mkdir()
    def tearDown(self):
        self.assertEqual(a.source_hashes(),self.sources)
        for name,h in self.protected.items():self.assertEqual(w.sha(w.plain(Path(name))),h,name)
        self.assertFalse((w.LEDGER/'block-00065.json').exists())
        self.assertEqual(self.owner.read_bytes() if self.owner.exists() else None,self.owner_before)
    def clone(self,name):
        job=self.work/name;shutil.copytree(READY if name=='planned' else REVIEW/name/'job',job);return job
    def change(self,job,**updates):
        value=w.load(job/'state.json');value.update(updates);(job/'state.json').write_bytes(w.b.canonical(value))
        if (job/'COMMITTED').exists():
            for name in ('COMMITTED','SHA256SUMS'):(job/name).unlink()
            w.b.seal(job)
    def test_prepared_job_unmodified_and_no_disk_or_pid_probe(self):
        before=inspector.snapshot(READY)
        with patch.object(a.MacBackend,'command',side_effect=AssertionError('disk')),patch.object(a.subprocess,'Popen',side_effect=AssertionError('process')),patch.object(os,'kill',side_effect=AssertionError('PID')):
            result=inspector.inspect(READY,self.work/'absent-owner.json')
        self.assertEqual(result['classification'],'prepared_no_disk_phase_claimed');self.assertEqual(result['volume_owner'],'absent')
        self.assertEqual(inspector.snapshot(READY),before);self.assertEqual(result['command_count'],0)
        self.assertFalse(result['test_authorized']);self.assertFalse(result['automatic_unlock_authorized'])
    def test_eight_saved_cases_classified_without_mutation(self):
        expected={'success-renumbered':'supplied_complete_model','postcreate-corruption':'flag_created_not_accepted',
            'timeout-before':'interrupted_or_unresolved_no_retry','timeout-after':'interrupted_or_unresolved_no_retry'}
        for folder in sorted(REVIEW.iterdir()):
            if not (folder/'job').is_dir():continue
            owner=folder/'volume-owner.json' if (folder/'volume-owner.json').exists() else None
            before=inspector.snapshot(folder/'job');result=inspector.inspect(folder/'job',owner)
            self.assertEqual(result['classification'],expected.get(folder.name,'failed_no_retry'),folder.name)
            self.assertEqual(result['issues'],[]);self.assertEqual(inspector.snapshot(folder/'job'),before)
            self.assertFalse(result['process_liveness_checked']);self.assertFalse(result['retry_authorized'])
    def test_timeout_after_create_is_not_completed_or_known_dead(self):
        result=inspector.inspect(REVIEW/'timeout-after/job',REVIEW/'timeout-after/volume-owner.json')
        self.assertTrue(result['flag_create_recorded']);self.assertGreater(result['commands_without_exit'],0)
        self.assertFalse(result['complete_supplied_chain_verified']);self.assertEqual(result['seal'],'absent')
        self.assertEqual(result['volume_owner'],'matches_saved_job');self.assertFalse(result['process_liveness_checked'])
    def test_failed_closed_job_can_record_nonzero_exit(self):
        result=inspector.inspect(REVIEW/'writable-mount-failure/job',REVIEW/'writable-mount-failure/volume-owner.json')
        self.assertEqual(result['seal'],'verified');self.assertGreater(result['commands_with_nonzero_exit'],0)
        self.assertFalse(result['flag_create_recorded']);self.assertFalse(result['media_state_checked'])
    def test_awaiting_reinsert_requires_saved_readonly_backup(self):
        job=self.clone('success-renumbered')
        for name in ('after','repair-commands'):shutil.rmtree(job/name)
        for name in ('.repair.lock','create-intent.json','flag-created.json','SHA256SUMS','COMMITTED'):(job/name).unlink()
        value=w.load(job/'state.json')
        for name in ('post_recovery','post_ejected','flag_create_returned_fd'):value.pop(name,None)
        value.update(stage='awaiting_reinsert',repair_remaining=1);(job/'state.json').write_bytes(w.b.canonical(value))
        result=inspector.inspect(job);self.assertEqual(result['classification'],'backup_saved_awaiting_reinsert');self.assertTrue(result['before_saved_and_ejected'])
        shutil.rmtree(job/'before');result=inspector.inspect(job);self.assertEqual(result['classification'],'invalid_or_incomplete_input')
    def test_interrupted_consumption_does_not_imply_a_process_exists(self):
        job=self.clone('planned');(job/'.backup.lock').write_bytes(b'');self.change(job,stage='backup_consumed',backup_remaining=0)
        result=inspector.inspect(job);self.assertEqual(result['classification'],'interrupted_or_unresolved_no_retry')
        self.assertEqual(result['command_count'],0);self.assertFalse(result['process_liveness_checked'])
    def test_planned_job_with_unexpected_claim_is_not_clean(self):
        job=self.clone('planned');(job/'.backup.lock').write_bytes(b'')
        result=inspector.inspect(job);self.assertEqual(result['classification'],'invalid_or_incomplete_input')
    def test_partial_or_corrupt_closed_seal_is_not_accepted(self):
        job=self.clone('postcreate-corruption');(job/'COMMITTED').unlink()
        result=inspector.inspect(job);self.assertEqual(result['classification'],'invalid_or_incomplete_input')
        self.assertFalse(result['complete_supplied_chain_verified'])
    def test_foreign_owner_never_authorizes_unlock(self):
        job=self.clone('timeout-before');owner=self.work/'owner.json';value=w.load(REVIEW/'timeout-before/volume-owner.json')
        value['preparation_id']='00000000-0000-0000-0000-000000000000';owner.write_bytes(w.b.canonical(value))
        result=inspector.inspect(job,owner);self.assertEqual(result['volume_owner'],'foreign_or_invalid')
        self.assertEqual(result['classification'],'invalid_or_incomplete_input');self.assertFalse(result['automatic_unlock_authorized'])
    def test_source_drift_and_boolean_counter_rejected(self):
        job=self.clone('planned');self.change(job,backup_remaining=True)
        with self.assertRaises(ValueError):inspector.inspect(job)
        self.change(job,backup_remaining=1);plan=w.load(job/'plan.json');plan['scope']['maximum_creates']=2
        (job/'plan.json').write_bytes(w.b.canonical(plan));self.change(job,plan_sha256=w.sha(w.plain(job/'plan.json')))
        with self.assertRaises(ValueError):inspector.inspect(job)
    def test_unresolved_pid_is_checked_as_data_only(self):
        job=self.clone('timeout-before');self.change(job,command_pid=True)
        result=inspector.inspect(job);self.assertEqual(result['classification'],'invalid_or_incomplete_input');self.assertFalse(result['process_liveness_checked'])
    def test_create_marker_and_state_disagreement_preserved(self):
        job=self.clone('postcreate-corruption');self.change(job,flag_create_returned_fd=False)
        result=inspector.inspect(job);self.assertEqual(result['classification'],'invalid_or_incomplete_input');self.assertTrue(result['flag_create_recorded'])
    def test_complete_model_forged_as_real_is_rejected(self):
        job=self.clone('success-renumbered');self.change(job,actual_card_repaired=True)
        result=inspector.inspect(job);self.assertEqual(result['classification'],'invalid_or_incomplete_input');self.assertFalse(result['complete_supplied_chain_verified'])
    def test_outside_analysis_and_symlinks_rejected(self):
        with self.assertRaises(ValueError):inspector.inspect(Path('/Volumes/SDCARD'))
        job=self.clone('planned');(job/'link').symlink_to(job/'state.json')
        with self.assertRaises(ValueError):inspector.inspect(job)
    def test_changing_command_log_is_not_reported_stable(self):
        job=self.clone('timeout-before');original=inspector.snapshot;calls=0
        def changing(folder):
            nonlocal calls
            calls+=1
            if calls==2:(job/'backup-commands/001.stderr').write_bytes(b'child output changed')
            return original(folder)
        with patch.object(inspector,'snapshot',side_effect=changing):result=inspector.inspect(job)
        self.assertFalse(result['stable_during_inspection']);self.assertEqual(result['classification'],'invalid_or_incomplete_input')
    def test_cli_saved_report_does_not_execute_a_backend(self):
        result=subprocess.run([sys.executable,str(w.ROOT/'tools/inspect_a23_context65_flag_card.py'),str(REVIEW/'timeout-after/job'),
            '--owner',str(REVIEW/'timeout-after/volume-owner.json')],check=True,capture_output=True)
        value=json.loads(result.stdout);self.assertEqual(value['classification'],'interrupted_or_unresolved_no_retry');self.assertFalse(value['retry_authorized'])


if __name__=='__main__':unittest.main()
