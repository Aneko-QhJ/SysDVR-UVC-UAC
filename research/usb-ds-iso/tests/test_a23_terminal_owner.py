from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import audit_a23_terminal_owner as audit
s = audit.candidate


class TerminalOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved = os.environ.get('A23_TERMINAL_OWNER_REVIEW')
        cls.root = Path(saved) if saved else Path(tempfile.mkdtemp(prefix='a23-owner-tests-', dir='/private/tmp')) / 'review'
        if not saved:
            audit.run(cls.root)
        cls.pin = audit.f.sha(audit.a.read(cls.root / 'SHA256SUMS'))
        cls.result = audit.verify(cls.root, cls.pin)

    def row(self, name):
        return audit.f.load(self.root / 'work/cases' / name / 'observation.json')

    def args(self):
        return audit.args_at(self.root / 'inputs/jobs/normal')[:2]

    def pending(self, *, waited=False):
        owner = s.SamplerOwner()
        owner._slot.child = Mock()
        owner._slot.started = True
        owner._slot.waited = waited
        return owner

    def test_74_cases_73_actual_waits(self):
        self.assertEqual((self.result['model_cases'], self.result['sampler_child_processes'], self.result['directly_waited_sampler_children']), (74,73,73))

    def test_58_historical_caches_and_classifications(self):
        counts = {}
        for d in (self.root / 'work/cases/base').iterdir():
            expected = audit.args_at(self.root / 'inputs/jobs' / d.name)[2]
            self.assertEqual(audit.previous.previous.cache(d / 'captured'), expected)
            result = audit.f.load(d / 'classification.json')
            counts[result['classification']] = counts.get(result['classification'], 0) + 1
            self.assertFalse(result['task_complete'])
        self.assertEqual(counts, dict(commit_associated=6, incomplete=52))

    def test_cancel_before_spawn_creates_no_child(self):
        state = self.row('interrupt/before_spawn')['lifecycle']
        self.assertFalse(state['spawned'])
        self.assertFalse(state['direct_wait_verified'])

    def test_original_exception_preserved_at_seven_capture_points(self):
        for point in audit.INTERRUPT_POINTS:
            row = self.row('interrupt/' + point)
            self.assertTrue(row['primary_exception_preserved'])
            self.assertFalse(row['lifecycle']['accepted'])

    def test_second_cleanup_interrupt_does_not_replace_primary(self):
        row = self.row('interrupt/double')
        self.assertTrue(row['primary_exception_preserved'])
        self.assertEqual(len(row['lifecycle']['interruption_types']), 2)
        self.assertTrue(row['lifecycle']['direct_wait_verified'])

    def test_systemexit_propagates_without_losing_owner(self):
        row = self.row('interrupt/system-exit')
        self.assertTrue(row['primary_exception_preserved'])
        self.assertEqual(row['caught_exception'], 'SystemExit')
        self.assertTrue(row['lifecycle']['direct_wait_verified'])

    def test_timer_interrupts_actual_pipe_exchange(self):
        row = self.row('interrupt/timer')
        self.assertEqual(row['caught_exception'], 'KeyboardInterrupt')
        self.assertEqual(row['lifecycle']['interruption_types'][0]['operation'], 'exchange')
        self.assertTrue(row['lifecycle']['direct_wait_verified'])

    def test_cleanup_signal_and_wait_interruptions_are_distinct(self):
        for name in ('cleanup-terminate','cleanup-wait'):
            state = self.row('interrupt/' + name)['lifecycle']
            self.assertTrue(state['caller_interrupted'])
            self.assertTrue(state['direct_wait_verified'])
            self.assertTrue(state['cleanup_errors'])

    def test_interrupted_close_remains_available_for_finish(self):
        row = self.row('interrupt/cleanup-close')
        self.assertEqual(row['pre_finish']['pending_streams'], 1)
        self.assertEqual(row['lifecycle']['pending_streams'], 0)
        self.assertFalse(row['lifecycle']['accepted'])

    def test_real_handle_transfer_not_reconstructed_from_pid(self):
        for name in ('normal','prepared-interrupt','committed-interrupt'):
            row = self.row('handoff/' + name)
            self.assertTrue(row['same_runtime_handle_transferred'])
            self.assertTrue(row['revoked_owner_rejected'])
            self.assertTrue(row['lifecycle']['direct_wait_verified'])
            self.assertFalse(row['pre_finish']['direct_wait_verified'])

    def test_handoff_interrupted_before_commit_keeps_original_owner(self):
        self.assertTrue(self.row('handoff/prepared-interrupt')['before_commit_owner_kept'])

    def test_handoff_interrupted_after_commit_keeps_successor_reachable(self):
        self.assertTrue(self.row('handoff/committed-interrupt')['after_commit_successor_reachable'])

    def test_all_failed_cases_have_no_cache(self):
        for name in audit.CASES:
            for part in ('captured','report.json','classification.json'):
                self.assertFalse((self.root / 'work/cases' / name / part).exists())

    def test_no_old_history_or_authority_promoted(self):
        for row in self.result['semantic'].values():
            for key in s.prior.intake.recovery.FALSE:
                self.assertIs(row['lifecycle'][key],False)
            self.assertFalse(row['lifecycle']['task_complete'])

    def test_unconfirmed_waits_keep_slot_and_explicit_finish_uses_same_handle(self):
        owner = self.pending()
        child = owner._slot.child
        child.wait.side_effect = subprocess.TimeoutExpired('fixture',0.2)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('relaunch')):
            state = owner.finish()
            self.assertTrue(state['pending_handle_retained'])
            successor = owner.handoff()
            self.assertIs(successor._slot.child,child)
            child.wait.side_effect = None
            child.wait.return_value = -15
            state = successor.finish()
        self.assertTrue(state['direct_wait_verified'])
        self.assertFalse(state['accepted'])
        self.assertFalse(state['pending_handle_retained'])

    def test_revoked_owner_cannot_finish_capture_or_transfer_again(self):
        owner = self.pending()
        successor = owner.handoff()
        for action in (owner.finish, owner.handoff, lambda:owner.capture('/private/tmp/no-open',*self.args())):
            with self.assertRaises(ValueError):action()
        self.assertIs(owner.successor,successor)

    def test_no_pending_resources_means_no_handoff(self):
        with self.assertRaises(ValueError):s.SamplerOwner().handoff()

    def test_reentrant_transfer_blocked(self):
        owner = self.pending()
        observations = []
        def checkpoint(_):
            with self.assertRaises(ValueError):owner.finish()
            observations.append(1)
        successor = owner.handoff(_checkpoint=checkpoint)
        self.assertEqual(len(observations),2)
        self.assertIs(owner._slot.holder,successor)

    def test_after_wait_interrupt_does_not_erase_actual_wait_or_send_kill(self):
        owner = self.pending()
        child = owner._slot.child
        child.wait.return_value = 0
        original = KeyboardInterrupt('after wait')
        def checkpoint(point):
            if point=='after_wait_terminate':raise original
        with self.assertRaises(KeyboardInterrupt) as caught:owner.finish(_checkpoint=checkpoint)
        self.assertIs(caught.exception,original)
        self.assertTrue(owner.observation()['direct_wait_verified'])
        child.kill.assert_not_called()
        self.assertFalse(owner.observation()['pending_handle_retained'])

    def test_stream_only_pending_transfer_never_signals_waited_child(self):
        owner = self.pending(waited=True)
        stream = Mock();stream.closed=False
        def close():stream.closed=True
        stream.close.side_effect=close
        owner._slot.streams=[stream]
        successor=owner.handoff()
        successor.finish()
        owner._slot.child.terminate.assert_not_called()
        owner._slot.child.kill.assert_not_called()
        self.assertEqual(successor.observation()['pending_streams'],0)

    def test_unexpected_exception_preserves_identity_and_waits(self):
        owner=s.SamplerOwner();child=Mock();child.wait.return_value=-15
        child.stdin.closed=child.stdout.closed=False
        child.stdin.close.side_effect=lambda:setattr(child.stdin,'closed',True)
        child.stdout.close.side_effect=lambda:setattr(child.stdout,'closed',True)
        original=RuntimeError('original')
        with patch.object(subprocess,'Popen',return_value=child),patch.object(s.prior,'exchange',side_effect=original):
            with self.assertRaises(RuntimeError) as caught:owner.capture('/private/tmp/no-open',*self.args())
        self.assertIs(caught.exception,original)
        self.assertTrue(owner.observation()['direct_wait_verified'])
        with self.assertRaises(ValueError):owner.capture('/private/tmp/no-open',*self.args())

    def test_pid_or_json_cannot_construct_owner(self):
        with self.assertRaises(TypeError):s.SamplerOwner(pid=123)
        with self.assertRaises(TypeError):s.SamplerOwner({'pid':123})
        self.assertFalse(hasattr(s.SamplerOwner,'from_pid'))
        self.assertFalse(hasattr(s.SamplerOwner,'recover'))

    def test_snapshot_mutation_does_not_change_live_slot(self):
        owner=self.pending();v=owner.observation();v['direct_wait_verified']=True;v['cleanup_errors'].append({'fake':True})
        self.assertFalse(owner.observation()['direct_wait_verified'])
        self.assertEqual(owner.observation()['cleanup_errors'],[])

    def test_invalid_budget_anchor_and_path_fail_before_spawn(self):
        for value in (True,0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):s.SamplerOwner(cleanup_grace=value)
        with patch.object(subprocess,'Popen',side_effect=AssertionError('launch')):
            with self.assertRaises(ValueError):s.SamplerOwner().capture('/Volumes/not-opened',*self.args())
            with self.assertRaises(ValueError):s.SamplerOwner().capture('/private/tmp/no-open',*self.args(),timeout=True)

    def test_readonly_verify_no_launch_or_resample(self):
        with patch.object(subprocess,'Popen',side_effect=AssertionError('launch')),patch.object(s.SamplerOwner,'capture',side_effect=AssertionError('capture')):
            audit.verify(self.root,self.pin)

    def test_external_pin_and_source_count(self):
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
        v=audit.f.load(self.root/'audit.json')
        self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(565,562))


if __name__=='__main__':unittest.main()
