from pathlib import Path
import base64
import copy
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import audit_a23_terminal_deadline as audit
s = audit.candidate


class TerminalDeadlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved = os.environ.get('A23_TERMINAL_DEADLINE_REVIEW')
        cls.root = Path(saved) if saved else Path(tempfile.mkdtemp(prefix='a23-deadline-tests-', dir='/private/tmp')) / 'review'
        if not saved:
            audit.run(cls.root)
        cls.pin = audit.f.sha(audit.a.read(cls.root / 'SHA256SUMS'))
        cls.result = audit.verify(cls.root, cls.pin)

    def args(self):
        return audit.previous.previous.args_at(self.root / 'inputs/jobs/normal')

    def row(self, name):
        return self.result['semantic'][name]

    def wire(self):
        path = self.root / 'work/cases/base/normal'
        files = audit.previous.cache(path / 'captured')
        return dict(schema='A23-terminal-deadline-wire-1', files={n: base64.b64encode(v).decode() for n, v in files.items()}, report=audit.f.load(path / 'report.json'))

    def test_all_67_cases_and_direct_waits(self):
        self.assertEqual((self.result['model_cases'], self.result['sampler_child_processes'], self.result['directly_waited_sampler_children']), (67, 67, 67))

    def test_58_historical_caches_unchanged(self):
        for name, row in self.result['semantic'].items():
            if name.startswith('base/'):
                self.assertTrue(row['accepted'])
                expected = audit.previous.previous.args_at(self.root / 'inputs/jobs' / name.removeprefix('base/'))[2]
                self.assertEqual(audit.previous.cache(self.root / 'work/cases' / name / 'captured'), expected)

    def test_blocked_read_deadline_is_failure_even_after_wait(self):
        row = self.row('fault/blocked-read')
        self.assertTrue(row['deadline_expired'])
        self.assertTrue(row['direct_wait_verified'])
        self.assertEqual(row['returncode'], -signal.SIGTERM)
        self.assertFalse(row['accepted'])

    def test_ignored_sigterm_escalates_then_waits(self):
        row = self.row('fault/ignore-term')
        self.assertTrue(row['terminate_call_returned'])
        self.assertTrue(row['kill_call_returned'])
        self.assertEqual(row['cleanup_wait_timeouts'], 1)
        self.assertEqual(row['returncode'], -signal.SIGKILL)

    def test_child_not_reading_input_still_times_out(self):
        self.assertEqual(self.row('fault/no-input')['reason'], 'deadline')

    def test_partial_response_is_discarded(self):
        self.assertFalse(self.row('fault/partial')['accepted'])
        self.assertFalse((self.root / 'work/cases/fault/partial/captured').exists())

    def test_full_response_and_eof_do_not_replace_wait(self):
        row = self.row('fault/after-eof')
        self.assertEqual(row['reason'], 'deadline')
        self.assertTrue(row['direct_wait_verified'])
        self.assertFalse(row['accepted'])

    def test_oversized_response_rejected(self):
        self.assertEqual(self.row('fault/oversized')['reason'], 'response_limit')
        state = audit.f.load(self.root / 'work/cases/fault/oversized/lifecycle.json')
        self.assertEqual(state['response_size'], s.MAX_RESPONSE + 1)

    def test_malformed_response_rejected_after_wait(self):
        self.assertFalse(self.row('fault/malformed')['accepted'])
        self.assertTrue(self.row('fault/malformed')['direct_wait_verified'])

    def test_nonzero_exit_with_complete_cache_rejected(self):
        self.assertEqual(self.row('fault/exit7')['reason'], 'child_exit')
        self.assertEqual(self.row('fault/exit7')['returncode'], 7)

    def test_forged_history_report_rejected(self):
        self.assertEqual(self.row('fault/forged-report')['reason'], 'response_report_claim')

    def test_no_failed_case_has_artifacts(self):
        for name in audit.FAULTS:
            directory = self.root / 'work/cases/fault' / name
            for part in ('captured', 'report.json', 'classification.json'):
                self.assertFalse((directory / part).exists())

    def test_no_history_or_authority_promotion(self):
        for row in self.result['semantic'].values():
            self.assertFalse(row['task_complete'])
            for key in s.intake.recovery.FALSE:
                self.assertIs(row[key], False)
        for directory in (self.root / 'work/cases/base').iterdir():
            result = audit.f.load(directory / 'classification.json')
            for key in ('directory_sync_status', 'actor_wait_status', 'actual_process_exit_status', 'hardlink_identity_status'):
                self.assertEqual(result[key], 'unknown')

    def test_budgets_reject_bool_nan_infinity_zero_before_launch(self):
        anchor, pin, _ = self.args()
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('spawn')):
            for value in (True, 0, -1, float('nan'), float('inf'), 31):
                for key in ('timeout', 'cleanup_grace'):
                    with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                        s.capture('/private/tmp/not-opened', anchor, pin, **{key: value})

    def test_anchor_and_path_rejected_before_launch(self):
        anchor, pin, _ = self.args()
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('spawn')):
            with self.assertRaises(ValueError):
                s.capture('/private/tmp/not-opened', anchor, '0' * 64)
            with self.assertRaises(ValueError):
                s.capture('/Volumes/not-opened', anchor, pin)

    def test_spawn_error_has_no_fictitious_wait(self):
        anchor, pin, _ = self.args()
        with patch.object(subprocess, 'Popen', side_effect=OSError('spawn')):
            result = s.capture('/private/tmp/not-opened', anchor, pin)
        self.assertFalse(result.lifecycle['spawned'])
        self.assertFalse(result.lifecycle['direct_wait_verified'])
        self.assertIsNone(result.pending_process)
        self.assertIsNone(result.cache)

    def test_wait_failure_keeps_actual_handle(self):
        child = Mock()
        child.wait.side_effect = subprocess.TimeoutExpired('fixture', 0.01)
        state = dict(cleanup_wait_timeouts=0, direct_wait_verified=False, pending_handle_retained=False)
        with patch.object(os, 'kill', side_effect=AssertionError('journal PID signal')), patch.object(os, 'waitpid', side_effect=AssertionError('PID wait')):
            pending = s.reap(child, state, 0.01)
        self.assertIs(pending, child)
        self.assertTrue(state['pending_handle_retained'])
        self.assertFalse(state['direct_wait_verified'])
        self.assertEqual(state['cleanup_wait_timeouts'], 2)
        child.terminate.assert_called_once_with()
        child.kill.assert_called_once_with()

    def test_signal_return_does_not_prove_wait(self):
        child = Mock()
        child.wait.side_effect = OSError('wait failed')
        state = dict(cleanup_wait_timeouts=0, direct_wait_verified=False, pending_handle_retained=False)
        self.assertIs(s.reap(child, state, 0.01), child)
        self.assertTrue(state['terminate_call_returned'])
        self.assertFalse(state['direct_wait_verified'])

    def test_signal_error_does_not_prevent_direct_wait(self):
        child = Mock()
        child.terminate.side_effect = ProcessLookupError('exited')
        child.wait.return_value = 7
        state = dict(cleanup_wait_timeouts=0, direct_wait_verified=False, pending_handle_retained=False)
        self.assertIsNone(s.reap(child, state, 0.01))
        self.assertTrue(state['direct_wait_verified'])
        self.assertEqual(state['returncode'], 7)
        child.kill.assert_not_called()

    def test_transport_error_still_waits_owned_child(self):
        anchor, pin, _ = self.args()
        child = Mock()
        child.wait.return_value = -15
        child.stdin.closed = child.stdout.closed = False
        with patch.object(subprocess, 'Popen', return_value=child), patch.object(s, 'exchange', side_effect=OSError('pipe')):
            result = s.capture('/private/tmp/not-opened', anchor, pin)
        self.assertFalse(result.lifecycle['accepted'])
        self.assertTrue(result.lifecycle['direct_wait_verified'])
        self.assertIsNone(result.cache)
        child.stdin.close.assert_called_once()
        child.stdout.close.assert_called_once()

    def test_close_failure_discards_accepted_cache(self):
        anchor, pin, _ = self.args()
        child = Mock()
        child.wait.return_value = 0
        child.stdin.closed = child.stdout.closed = False
        child.stdout.close.side_effect = OSError('close')
        with patch.object(subprocess, 'Popen', return_value=child), patch.object(s, 'exchange', return_value=('received', s.encode(self.wire()))):
            result = s.capture('/private/tmp/not-opened', anchor, pin)
        self.assertFalse(result.lifecycle['accepted'])
        self.assertEqual(result.lifecycle['reason'], 'stream_close')
        self.assertIsNone(result.cache)
        self.assertTrue(result.lifecycle['direct_wait_verified'])

    def test_invalid_response_variants_reject(self):
        anchor, pin, _ = self.args()
        variants = []
        def add(edit):
            value = copy.deepcopy(self.wire())
            edit(value)
            variants.append(s.encode(value))
        add(lambda v: v.update(schema='other'))
        add(lambda v: v['files'].update({'../outside': ''}))
        add(lambda v: v['files'].update({'worker-exit.json': '!invalid'}))
        add(lambda v: v['report'].update(file_count=True))
        add(lambda v: v['report'].update(equal_views=True))
        add(lambda v: v['report'].update(model_only=False))
        add(lambda v: v['report'].update(directory_identity_chain=[]))
        add(lambda v: v['report'].update(total_bytes=0))
        add(lambda v: v['report'].update(file_metadata={}))
        add(lambda v: v.update(extra=True))
        variants.extend([b'[]', b'null', b'{}', b'{', s.encode(self.wire()) + b'\n'])
        for raw in variants:
            with self.subTest(raw=raw[:40]), self.assertRaises((ValueError, TypeError, KeyError)):
                s.decode_response(raw, anchor, pin)

    def test_parent_recomputes_classification(self):
        anchor, pin, _ = self.args()
        value = self.wire()
        _, report, classification = s.decode_response(s.encode(value), anchor, pin)
        self.assertFalse(report['historical_sync_or_wait_inferred'])
        self.assertEqual(classification['classification'], 'commit_associated')
        self.assertFalse(classification['task_complete'])

    def test_readonly_verify_never_launches_or_resamples(self):
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('launch')), patch.object(s, 'capture', side_effect=AssertionError('capture')):
            audit.verify(self.root, self.pin)

    def test_review_pin_required(self):
        with self.assertRaises(ValueError):
            audit.verify(self.root, '0' * 64)

    def test_source562_preserves557(self):
        value = audit.f.load(self.root / 'audit.json')
        self.assertEqual((value['source_count'], value['prior_sources_unchanged']), (562, 557))


if __name__ == '__main__':
    unittest.main()
