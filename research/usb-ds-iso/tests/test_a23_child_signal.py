from pathlib import Path
import copy
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_child_signal as audit
s=audit.candidate


class ChildSignalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_CHILD_SIGNAL_REVIEW')
        cls.root=Path(saved) if saved else Path(tempfile.mkdtemp(prefix='a23-child-signal-tests-',dir='/private/tmp'))/'review'
        if not saved:audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def row(self,n):return audit.f.load(self.root/'work/cases'/n/'observation.json')
    def report(self,n):return audit.f.load(self.root/'work/cases'/n/'ready.json')
    def test_twenty_actual_children_directly_waited(self):self.assertEqual((self.r['model_cases'],self.r['actual_child_processes'],self.r['candidate_direct_waits']),(20,20,20))
    def test_original_bytes_survive_normal_and_preblocked_int(self):
        args=audit.recovery_audit.args_at(self.root/'inputs/normal')
        for n in audit.ACCEPTED:self.assertEqual(audit.intake_audit.cache(self.root/'work/cases'/n/'captured'),args[2])
    def test_initial_extra_sigint_mask_removed_before_sampling(self):
        v=self.report('normal');self.assertEqual(v['mask_before'],[int(signal.SIGINT)]);self.assertEqual(v['mask_after'],[])
    def test_original_blocked_sigint_preserved(self):self.assertEqual(self.report('preblocked-int')['mask_after'],[int(signal.SIGINT)])
    def test_pending_child_sigint_preserved_when_originally_blocked(self):self.assertTrue(self.report('preblocked-int-pending')['pending_sigint_before_reset']);self.assertTrue(self.row('preblocked-int-pending')['accepted'])
    def test_before_reset_pending_int_delivered_on_restore(self):self.assertEqual(self.row('before-reset-int')['actual_exitcode'],130);self.assertFalse(self.row('before-reset-int')['lifecycle']['child_policy_confirmed'])
    def test_before_reset_default_term_kills(self):self.assertEqual(self.row('before-reset-term')['actual_exitcode'],-int(signal.SIGTERM))
    def test_after_reset_int_terminates_without_ready(self):self.assertEqual(self.row('after-reset-int')['actual_exitcode'],130)
    def test_after_reset_term_terminates_without_ready(self):self.assertEqual(self.row('after-reset-term')['actual_exitcode'],-int(signal.SIGTERM))
    def test_after_ready_int_failure_rejects_sample(self):self.assertEqual(self.row('ready-int')['actual_exitcode'],130);self.assertFalse(self.row('ready-int')['accepted'])
    def test_after_ready_term_failure_rejects_sample(self):self.assertEqual(self.row('ready-term')['actual_exitcode'],-int(signal.SIGTERM));self.assertFalse(self.row('ready-term')['accepted'])
    def test_inherited_ignored_term_reset_before_ready(self):
        v=self.report('ignored-term-then-ready-term');self.assertEqual((v['sigterm_before'],v['sigterm_after']),('SIG_IGN','SIG_DFL'));self.assertEqual(self.row('ignored-term-then-ready-term')['actual_exitcode'],-int(signal.SIGTERM))
    def test_default_term_timeout_needs_no_kill(self):self.assertEqual(self.row('timeout-default-term')['lifecycle'].get('kill_attempts',0),0)
    def test_originally_blocked_term_timeout_escalates_to_kill(self):self.assertEqual(self.row('timeout-blocked-term')['actual_exitcode'],-int(signal.SIGKILL));self.assertEqual(self.report('timeout-blocked-term')['mask_after'],[int(signal.SIGTERM)])
    def test_corrupt_reports_cannot_confirm_or_sample(self):
        for n in ('bad-token','bad-mask','bad-handler','partial-ready','oversized-ready'):self.assertFalse(self.row(n)['lifecycle']['child_policy_confirmed']);self.assertFalse(self.row(n)['accepted'])
    def test_missing_ready_deadline_is_distinct_from_total_deadline(self):
        self.assertTrue(self.row('stall-before-ready')['lifecycle']['child_ready_deadline_expired']);self.assertFalse(self.row('timeout-default-term')['lifecycle']['child_ready_deadline_expired'])
    def test_reset_failure_and_early_exit_do_not_confirm(self):
        for n in ('reset-error','exit-before-ready'):self.assertFalse(self.row(n)['lifecycle']['child_policy_confirmed']);self.assertNotEqual(self.row(n)['actual_exitcode'],0)
    def test_parent_masks_handlers_and_pending_state_preserved(self):
        for n in audit.CASES:
            v=self.row(n);self.assertTrue(v['parent_mask_restored']);self.assertTrue(v['parent_term_handler_preserved']);self.assertEqual(v['parent_pending_signals'],[])
    def test_all_pipes_closed_and_every_failed_sample_artifact_absent(self):
        for n in audit.CASES:
            v=self.row(n);self.assertEqual((v['actual_open_streams'],v['lifecycle']['policy_fd_count'],v['lifecycle']['policy_fd_close_uncertain']),(0,0,0))
            if n not in audit.ACCEPTED:
                for part in ('captured','report.json','classification.json'):self.assertFalse((self.root/'work/cases'/n/part).exists())
    def test_ready_binding_mask_and_handler_tampering_rejected(self):
        policy=audit.f.load(self.root/'work/cases/normal/policy.json');good=self.report('normal')
        for key,val in (('launch_token','0'*32),('policy_sha256','0'*64),('mask_after',[True]),('mask_after',[int(signal.SIGINT)]),('sigterm_after','SIG_IGN')):
            v=copy.deepcopy(good);v[key]=val
            with self.assertRaises(ValueError):s.validate_report(policy,v)
    def test_uncertain_fd_close_is_recorded_and_never_retried(self):
        owner=s.SamplerOwner();owner._policy_fds=[12345]
        with patch.object(os,'close',side_effect=OSError('close')) as close:
            with self.assertRaises(OSError):owner._close_fd(12345)
            owner._close_fd(12345);self.assertEqual(close.call_count,1)
        self.assertEqual(owner.observation()['policy_fd_close_uncertain'],1);self.assertTrue(owner.observation()['cleanup_errors'])
    def test_primary_creation_interrupt_survives_close_failure(self):
        owner=s.SamplerOwner();primary=KeyboardInterrupt('primary')
        command=[sys.executable,'-B',str(Path(s.prior.__file__).with_name('a23_terminal_deadline_worker.py'))]
        with patch.object(os,'pipe',return_value=(12344,12345)),patch.object(s.PreviousOwner,'_create',side_effect=primary),patch.object(os,'close',side_effect=OSError('close')):
            with self.assertRaises(KeyboardInterrupt) as caught:owner._create(command)
        self.assertIs(caught.exception,primary);self.assertEqual(owner._policy_fd_uncertain,1);owner._policy_fds=[]
    def test_pure_validation_has_no_launch_mask_wait_or_file_io(self):
        rows=[self.row(n) for n in audit.CASES]
        with patch('builtins.open',side_effect=AssertionError('open')),patch.object(subprocess,'Popen',side_effect=AssertionError('spawn')),patch.object(signal,'pthread_sigmask',side_effect=AssertionError('mask')),patch.object(os,'waitpid',side_effect=AssertionError('wait')):
            for row in rows:audit.validate(row)
    def test_task_and_hardware_authority_never_promoted(self):
        for n in audit.CASES:
            v=self.row(n);self.assertFalse(v['task_complete'])
            for key in audit.FALSE:self.assertIs(v[key],False);self.assertIs(v['lifecycle'][key],False)
        v=copy.deepcopy(self.row('bad-token'));v['accepted']=True
        with self.assertRaises(ValueError):audit.validate(v)
    def test_readonly_verify_no_launch_trace_mask_wait(self):
        with patch.object(subprocess,'Popen',side_effect=AssertionError('spawn')),patch.object(sys,'settrace',side_effect=AssertionError('trace')),patch.object(signal,'pthread_sigmask',side_effect=AssertionError('mask')),patch.object(os,'waitpid',side_effect=AssertionError('wait')):audit.verify(self.root,self.pin)
    def test_external_pin_and_579_sources(self):
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(579,575))


if __name__=='__main__':unittest.main()
