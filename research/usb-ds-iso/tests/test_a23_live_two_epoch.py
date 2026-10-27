from pathlib import Path
import os,signal,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_live_two_epoch as audit
b=audit.builder
f=audit.flow


class LiveTwoEpochTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_LIVE_TWO_EPOCH_REVIEW')
        cls.root=Path(saved) if saved else Path(tempfile.mkdtemp(prefix='a23-live-tests-',dir='/private/tmp'))/'review'
        if not saved:audit.run(cls.root)
        cls.r=audit.verify(cls.root)
    def row(self,name):return b.w.load(self.root/'loop-cases'/name/'controller-observation.json')
    def test_real_cli_capabilities_and_file_build_checks(self):
        modes=self.r['file_modes'];self.assertEqual(modes['describe']['result'],b.DESCRIPTION);self.assertEqual(modes['check-build']['returncode'],0);self.assertEqual(modes['check-archive']['returncode'],0)
    def test_missing_job_or_arguments_cannot_reach_sdk(self):
        for name in ('missing-args','missing-job'):self.assertEqual(self.r['file_modes'][name]['returncode'],2)
    def test_preview_writes_no_job_reservation_or_invocation(self):
        v=b.w.load(self.root/'preview.json');self.assertFalse(v['record_written']);self.assertFalse(v['sequence_reserved']);self.assertFalse(v['receiver_launched']);self.assertEqual(v['remaining'],0)
    def test_issue_requires_explicit_new_authorization_before_any_engine_use(self):
        with patch.object(f,'engine_module',side_effect=AssertionError('engine')):
            with self.assertRaises(ValueError):f.issue(self.root/'build')
    def test_capture_requires_explicit_execution_mode(self):
        with patch.object(f,'engine_module',side_effect=AssertionError('engine')):
            with self.assertRaises(ValueError):f.capture(self.root/'build',Path('/nonexistent'))
    def test_controller_normal_two_epochs_are_strictly_analyzable(self):
        v=self.row('normal');self.assertTrue(v['loop']['finished']);self.assertTrue(v['loop']['success']);self.assertEqual((v['iso_submissions'],v['burst_triggers']),(2,2));self.assertTrue(self.r['strict_controller_entry_analysis']['supplied_entry_chain_complete'])
    def test_bad_first_payload_prevents_second_submission(self):self.assertEqual(self.row('bad-payload')['iso_submissions'],1);self.assertTrue(self.row('bad-payload')['loop']['unresolved_keep_alive'])
    def test_control_timeout_retains_sdk_process_and_does_not_force_exit(self):
        v=self.row('control-timeout');self.assertTrue(v['loop']['unresolved_keep_alive']);self.assertFalse(v['loop']['finished']);self.assertFalse(v['loop']['forced_exit'])
    def test_exit_waiting_finishes_without_sdk_open(self):
        v=self.row('exit-waiting');self.assertEqual(v['opens'],0);self.assertEqual(v['iso_submissions'],0);self.assertTrue(v['loop']['finished']);self.assertFalse(v['loop']['success'])
    def test_exit_running_stops_one_epoch_and_keeps_resources(self):
        v=self.row('exit-running');self.assertEqual(v['iso_submissions'],1);self.assertTrue(v['loop']['unresolved_keep_alive']);self.assertEqual(v['sdk_destroys'],0)
    def test_incomplete_observation_does_not_finalize(self):
        v=self.row('quiet-incomplete');self.assertFalse(v['loop']['finished']);self.assertFalse(v['loop']['export_attempted'])
    def test_export_or_receipt_collision_cannot_report_success(self):
        for n in ('export-collision','receipt-collision'):self.assertFalse(self.row(n)['loop']['success']);self.assertTrue(self.row(n)['loop']['unresolved_keep_alive'])
    def test_old_callback_before_final_prevents_success(self):self.assertFalse(self.row('old-before-final')['loop']['success']);self.assertTrue(self.row('old-before-final')['loop']['unresolved_keep_alive'])
    def test_failure_exports_do_not_copy_buffers_with_pending_writes(self):
        for n in ('bad-payload','control-timeout','exit-running','receipt-collision','old-before-final'):
            v=b.w.load(self.root/'loop-cases'/n/'live-failure/live.json');self.assertFalse(v['raw_inflight_buffers_copied']);self.assertFalse(v['callback_drain_verified'])
    def test_failed_completed_payload_preserves_owner_snapshot_without_sdk_buffer_read(self):
        directory=self.root/'loop-cases/bad-payload/live-evidence-epoch-0';b.w.card.seal_verify(directory)
        meta=b.w.load(directory/'owner.json');self.assertEqual(meta['source'],'retained_owner_snapshot');self.assertFalse(meta['active_sdk_buffers_read'])
        self.assertEqual((directory/'raw.bin').stat().st_size,184320);self.assertEqual((directory/'transactions.bin').stat().st_size,26880)
    def test_new_scope_and_native_permit_complete_one_model_and_reject_replay(self):
        rows=self.r['scope_results'];self.assertTrue(rows['normal']['entry']['complete'])
        for row in rows.values():self.assertTrue(row['native']['replay_blocked'])
    def test_source_change_and_pending_failure_block_second_epoch(self):
        rows=self.r['scope_results']
        for n in ('live-source-afterprepare','between-epochs-source','stopped-pending-source'):self.assertFalse(rows[n]['entry']['complete']);self.assertLessEqual(rows[n]['calls']['iso_submissions'],1)
        self.assertTrue(rows['stopped-pending-source']['full_checks_skipped_while_pending'])
    def test_old_scope_schema_cannot_be_used_as_live_permission(self):
        scope=b.runtime_scope(self.root/'build');module=f.engine_module(self.root/'build');self.assertEqual(scope['schema'],'A23-live-shared32-scope-1')
        bad=dict(scope,schema='A23-shared32-scope-1')
        with self.assertRaises(ValueError):module.scope(bad)
    def test_scope_capabilities_do_not_claim_physical_verification(self):
        scope=b.runtime_scope(self.root/'build');self.assertTrue(scope['acquisition_mode_implemented']);self.assertTrue(scope['hardware_entry_enabled']);self.assertFalse(self.r['hardware_verified']);self.assertEqual(self.r['actual_acquisition_invocations'],0)
    def test_creator_keeps_child_after_interrupt_and_forwards_stop(self):
        class Child:
            calls=0
            signals=[]
            def wait(self,timeout=None):
                self.calls+=1
                if self.calls==1:raise KeyboardInterrupt()
                return 1
            def send_signal(self,n):self.signals.append(n)
        child=Child();before={n:signal.getsignal(n) for n in (signal.SIGINT,signal.SIGTERM)}
        code,stops,errors=f.wait_retained(child)
        self.assertEqual((code,stops,errors),(1,[int(signal.SIGINT)],[]));self.assertEqual(child.signals,[signal.SIGINT])
        self.assertEqual(before,{n:signal.getsignal(n) for n in before})
    def test_creator_stop_forward_failure_still_waits(self):
        class Child:
            calls=0
            def wait(self,timeout=None):
                self.calls+=1
                if self.calls==1:raise KeyboardInterrupt()
                return 1
            def send_signal(self,n):raise ProcessLookupError()
        code,stops,errors=f.wait_retained(Child());self.assertEqual(code,1);self.assertEqual(errors,['ProcessLookupError'])
    def test_operator_power_off_ends_retained_failure_without_claiming_drain(self):
        v=self.row('operator-off-after-timeout');s=v['loop'];self.assertTrue(s['finished']);self.assertFalse(s['success']);self.assertTrue(s['operator_power_off_acknowledged']);self.assertTrue(s['pending_sdk_work_unverified']);self.assertFalse(s['callback_drain_verified']);self.assertEqual(v['sdk_destroys'],0)
    def test_operator_power_off_requires_explicit_confirmation_before_file_read(self):
        with patch.object(b.w,'load',side_effect=AssertionError('read')):
            with self.assertRaises(ValueError):f.acknowledge_power_off(Path('/nonexistent'))
    def test_archive_verify_needs_no_process_launch(self):
        with patch.object(audit.subprocess,'Popen',side_effect=AssertionError('launch')):audit.verify(self.root)
    def test_579_existing_sources_and_three_native_compiles(self):self.assertEqual((self.r['source_count'],self.r['prior_sources_unchanged'],self.r['new_native_compiler_jobs']),(587,579,3))


if __name__=='__main__':unittest.main()
