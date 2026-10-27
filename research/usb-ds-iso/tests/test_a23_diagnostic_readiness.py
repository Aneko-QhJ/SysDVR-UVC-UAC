"""Actual-source prelude boundaries and conservative evidence interpretation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import audit_a23_diagnostic_readiness as audit
from workflows.artifacts import verify


class DiagnosticReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.tmp.name) / 'review'
        cls.result = audit.run(cls.output)
        cls.rows = {(r['configuration'], r['candidate'], r['prelude'], r['mode']): r
                    for r in cls.result['cases']}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def row(self, n=0, mode='healthy', candidate=True, label='dormant'):
        return self.rows[label, candidate, n, mode]

    def test_two_queries_fit_but_third_prevents_after_status(self):
        for label in audit.LABELS:
            for n, expected in ((0, 66), (1, 89), (2, 112)):
                row = self.row(n, label=label)
                self.assertEqual((row['records'], row['slots']), (expected, 6 + n * 2))
                self.assertTrue(row['normal_export'])
                self.assertEqual((row['iso_posts'], row['status_writes']), (1, 2))
            row = self.row(3, label=label)
            self.assertEqual((row['records'], row['slots'], row['status_writes']), (112, 10, 1))
            self.assertEqual((row['iso_posts'], row['sequence'], row['trace_refusals']), (1, 1, 1))
            self.assertEqual(row['events_left_signaled'], 3)
            self.assertFalse(row['normal_export'])

    def test_four_queries_block_burst_before_sequence_and_keep_events(self):
        row = self.row(4)
        self.assertEqual((row['records'], row['sequence'], row['iso_posts']), (115, 0, 0))
        self.assertEqual((row['trace_refusals'], row['guard_reason']), (1, 4))
        self.assertEqual(row['events_left_signaled'], 3)
        self.assertGreater(row['diagnostic_bytes'], 0)
        self.assertFalse(row['diagnostic_cleanup_authorized'])
        self.assertEqual(row['evidence_assessment']['observation'], 'candidate_capacity_denial')

    def test_original_client_handles_all_eight_queries_under_same_services(self):
        for n in range(9):
            row = self.row(n, candidate=False)
            self.assertEqual((row['prelude_dispatched'], row['target_setup_deliveries']), (n, 3))
            self.assertEqual((row['iso_posts'], row['status_writes'], row['sequence']), (1, 2, 1))
        for n in range(3):
            baseline, candidate = self.row(n, candidate=False), self.row(n)
            for key in ('iso_posts', 'in_posts', 'out_posts', 'stalls', 'sequence', 'status_writes'):
                self.assertEqual(candidate[key], baseline[key], (n, key))

    def test_reconnect_cost_persists_and_is_not_an_ownership_reset(self):
        for n in range(4):
            row = self.row(n, mode='reconnect')
            self.assertEqual(row['records'], 66 + 19 * n)
            self.assertEqual(row['slots'], 6 + n)
            self.assertTrue(row['normal_export'])
        row = self.row(4, mode='reconnect')
        self.assertEqual((row['records'], row['sequence'], row['status_writes']), (119, 1, 1))
        row = self.row(5, mode='reconnect')
        self.assertEqual((row['records'], row['slots'], row['sequence'], row['iso_posts']), (118, 7, 0, 0))
        for n in range(9):
            self.assertEqual(self.row(n, mode='reconnect', candidate=False)['iso_posts'], 1)

    def test_replacement_uses_only_three_host_setups_and_preserves_read_difference(self):
        row = self.row(mode='replaced')
        self.assertEqual((row['target_setup_deliveries'], row['target_dispatches']), (3, 2))
        self.assertEqual((row['records'], row['iso_posts'], row['sequence']), (52, 0, 0))
        self.assertTrue(row['replacement_delivered'])
        self.assertTrue(row['normal_export'])
        evidence = row['evidence_assessment']
        self.assertEqual(evidence['observation'], 'different_setup_at_interface2')
        self.assertFalse(evidence['shared_setup_overwrite_proven'])

    def test_speed_and_ack_paths_remain_distinguishable(self):
        expected = {'speed-error': 'speed_query_failed', 'full-speed': 'speed_rejection_observed',
                    'super-speed': 'non_hs_observed', 'post-failed': 'iso_post_failed',
                    'ack-timeout': 'ack_failed', 'setup-failed': 'interface2_setup_read_failed'}
        for mode, observation in expected.items():
            row = self.row(mode=mode)
            self.assertEqual(row['evidence_assessment']['observation'], observation)
        self.assertEqual(self.row(mode='ack-timeout')['sequence'], 1)
        self.assertEqual(self.row(mode='speed-error')['sequence'], 0)

    def test_candidate_rejection_is_not_labelled_an_original_guard(self):
        row = self.row(mode='prestatus-timeout')
        self.assertEqual((row['pending'], row['iso_posts'], row['sequence']), (1, 0, 0))
        self.assertEqual(row['evidence_assessment']['observation'], 'candidate_rejection_before_sequence')
        self.assertFalse(any(q['guards'] for q in row['requests'] if q['interface'] == 2))

    def test_missing_burst_event_does_not_prove_absence(self):
        evidence = self.row(mode='no-iso-event')['evidence_assessment']
        self.assertEqual(evidence['observation'], 'interface2_burst_unobserved')
        self.assertFalse(evidence['interface2_event_absence_proven'])

    def test_envelope_acceptance_never_becomes_usb_acceptance(self):
        for mode in ('healthy', 'speed-error', 'replaced', 'iso-pending'):
            row = self.row(mode=mode)
            self.assertFalse(row['evidence_assessment']['usb_strict_pass'])
            self.assertFalse(row['evidence_assessment']['root_cause_confirmed'])
        self.assertTrue(self.row(mode='speed-error')['normal_export'])
        self.assertEqual(self.row(mode='iso-pending')['pending'], 1)
        self.assertFalse(self.row(mode='iso-pending')['normal_export'])

    def test_join_failure_has_no_capture_or_diagnostic(self):
        for mode in ('video-join-error', 'audio-join-error'):
            row = self.row(mode=mode)
            self.assertFalse(row['normal_export'])
            self.assertEqual(row['diagnostic_bytes'], 0)
            self.assertEqual(row['evidence_assessment']['observation'], 'capture_unavailable')

    def test_window_starts_before_readiness_and_is_not_exercised_by_request_fixture(self):
        for label, ms in (('dormant', 0), ('window-30s', 30000)):
            binding = self.result['bindings'][label]
            self.assertEqual(binding['window_boundary']['window_ms'], ms)
            self.assertTrue(binding['window_boundary']['start_precedes_usb_ready'])
            self.assertFalse(binding['window_boundary']['expiry_interrupts_process'])
            self.assertFalse(binding['window_checked_in_native_request_replay'])

    def test_history_is_log_labels_and_not_a_reconstructed_bus_trace(self):
        history = self.result['historical_log_prelude']
        self.assertEqual(history['set_interface0_labels'], {'0': 9, '1': 9})
        self.assertEqual((history['connected_notices'], history['disconnected_notices']), (9, 8))
        self.assertFalse(history['exact_bus_request_count_proven'])
        candidate = self.row(9, mode='log-prefix')
        baseline = self.row(9, mode='log-prefix', candidate=False)
        self.assertEqual((baseline['prelude_dispatched'], baseline['target_setup_deliveries']), (9, 3))
        self.assertEqual(baseline['iso_posts'], 1)
        self.assertEqual(candidate['target_dispatches'], 0)
        self.assertEqual(candidate['trace_refusals'], 1)

    def test_corrupted_capture_rejected_and_missing_stage_stays_unknown(self):
        path = next(self.output.glob('dormant-candidate-prelude0-healthy.ownership.bin'))
        raw = path.read_bytes();corrupt = bytearray(raw);corrupt[-1] ^= 1
        recipe = self.row()['recipe_digest']
        with self.assertRaises(ValueError):
            audit.decode_capture(bytes(corrupt), recipe)
        with self.assertRaises(ValueError):
            audit.decode_capture(raw, '0' * 64)
        decoded = audit.decode_capture(raw, recipe)
        incomplete = copy.deepcopy(decoded);incomplete['trace']['dropped_records'] = 1
        self.assertEqual(audit.assess_evidence(incomplete)['observation'], 'trace_incomplete')

    def test_output_preservation_source_binding_and_limits(self):
        self.assertEqual(self.result['case_count'], 124)
        self.assertTrue(verify(self.output))
        with self.assertRaises(ValueError):
            audit.run(self.output)
        for row in self.result['cases']:
            self.assertEqual((row['dropped'], row['invalid'], row['bound_violations']), (0, 0, 0))
        for key in ('usb_accessed', 'sd_accessed', 'new_arm_build', 'arm_executed',
                    'firmware_packaged', 'production_modified', 'prior_runtime_modified',
                    'hardware_verified', 'root_cause_confirmed', 'actual_class_handlers_executed'):
            self.assertFalse(self.result[key])
        for name, expected in self.result['production_sources_sha256'].items():
            self.assertEqual(audit.sha(audit.REPO / name), expected)
        for name, expected in self.result['tickets_sha256'].items():
            self.assertEqual(audit.sha(audit.base.ep0.PRIVATE / 'analysis' / name), expected)


if __name__ == '__main__':
    unittest.main()
