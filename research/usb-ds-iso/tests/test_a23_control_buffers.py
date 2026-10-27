"""Actual A23 source under explicit buffer-ownership and cleanup assumptions."""
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_control_buffers as audit

class A23ControlBufferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name)
        cls.result=audit.run(cls.output)
        cls.buffers={r['case']:r['candidate'] for r in cls.result['buffer_cases']}
        cls.exits={r['case']:r for r in cls.result['exit_cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_38_source_replays_preserve_service_results_and_reuse_observations(self):
        self.assertEqual(self.result['source_replay_count'],38)
        self.assertEqual(self.result['buffer_case_count'],19)
        self.assertTrue(all(r['source_behavior_identical'] for r in self.result['buffer_cases']))

    def test_nonzero_pending_in_and_out_are_written_before_original_completion_is_known(self):
        for case in ('in-timeout','in-report-error','in-wrong-id','in-status-1','in-status-2',
                     'in-status-unknown','out-data-timeout','out-data-report-error','disconnect-reconnect'):
            r=self.buffers[case];self.assertEqual(r['pending_nonzero_spans'],1)
            self.assertEqual(r['cpu_write_overlaps'],1);self.assertGreater(r['changed_pending_bytes'],0)
            self.assertEqual(r['same_address_reposts'],2);self.assertFalse(r['ledger_export_allowed'])
        self.assertEqual(self.buffers['in-timeout']['cpu_write_overlap_bytes'],168)
        self.assertEqual(self.buffers['out-data-timeout']['cpu_write_overlap_bytes'],32)

    def test_zero_length_ack_or_status_reuse_does_not_cover_nonzero_dma_bytes(self):
        for case in ('burst-ack-timeout','out-status-timeout'):
            r=self.buffers[case];self.assertEqual(r['pending_zero_spans'],1)
            self.assertEqual(r['pending_nonzero_spans'],0);self.assertEqual(r['cpu_write_overlaps'],0)
            self.assertEqual(r['changed_pending_bytes'],0);self.assertEqual(r['same_address_reposts'],2)
            self.assertEqual(r['ledger_pending'],1);self.assertFalse(r['ledger_export_allowed'])
        self.assertFalse(self.result['zero_length_pointer_reuse_proves_nonzero_dma_corruption'])

    def test_vs_shares_iso_buffer_and_vc_does_not(self):
        r=self.buffers['cross-vs'];self.assertEqual(r['cpu_write_overlap_bytes'],1)
        self.assertEqual(r['changed_pending_bytes'],1);self.assertEqual(r['same_address_reposts'],2)
        r=self.buffers['cross-vc'];self.assertEqual(r['cpu_write_overlaps'],0)
        self.assertEqual(r['same_address_reposts'],0);self.assertEqual(r['ledger_pending'],1)

    def test_raw_terminal_failures_and_success_release_under_explicit_model_assumption(self):
        for case in ('drained','in-terminal-4','in-terminal-5','burst-ack-terminal-4'):
            r=self.buffers[case];self.assertEqual(r['pending_spans'],0)
            self.assertEqual(r['cpu_write_overlaps'],0);self.assertEqual(r['same_address_reposts'],0)
            self.assertTrue(r['ledger_export_allowed'])
        r=self.buffers['cancel-control-pending'];self.assertEqual(r['pending_nonzero_spans'],1)
        self.assertEqual(r['same_address_reposts'],1);self.assertFalse(r['ledger_export_allowed'])

    def test_late_terminal_after_cpu_copy_does_not_erase_history_when_ledger_drains(self):
        r=self.buffers['late-report-after-copy'];self.assertEqual(r['pending_spans'],0)
        self.assertEqual(r['ledger_pending'],0);self.assertTrue(r['ledger_export_allowed'])
        self.assertEqual(r['cpu_write_overlaps'],1);self.assertGreater(r['changed_pending_bytes'],0)
        self.assertFalse(self.result['ledger_drain_proves_no_prior_reuse'])

    def test_unchanged_exit_callback_closes_without_join_or_ownership_gate(self):
        live=self.exits['callback-live'];pending=self.exits['callback-stopped-pending']
        self.assertEqual(live['joins'],0);self.assertEqual(live['live_interface_closes'],3)
        self.assertEqual(pending['joins'],0);self.assertEqual(pending['pending_interface_closes'],3)
        for r in (live,pending):self.assertEqual(r['core_exit'],1);self.assertFalse(r['held'])
        self.assertFalse(self.result['callback_during_live_thread_reachability_verified'])

    def test_original_join_ignores_error_and_join_success_does_not_drain_urbs(self):
        r=self.exits['original-video-join-error'];self.assertEqual(r['live_thread_closes'],1)
        self.assertEqual(r['live_interface_closes'],3)
        r=self.exits['original-pending'];self.assertEqual(r['joins'],2)
        self.assertEqual(r['pending_interface_closes'],3);self.assertEqual(r['pending'],1)

    def test_candidate_normal_exit_holds_on_unknowns_but_drained_exit_is_idempotent(self):
        for case in ('candidate-pending','candidate-video-join-error','candidate-audio-join-error','candidate-sink-error'):
            r=self.exits[case];self.assertTrue(r['held']);self.assertEqual(r['joins'],2)
            for key in ('thread_closes','interface_closes','ds_exit','core_exit','sm_exit'):self.assertEqual(r[key],0)
            self.assertEqual(r['saves'],int(case=='candidate-sink-error'))
        r=self.exits['candidate-drained'];self.assertFalse(r['held']);self.assertEqual(r['saves'],1)
        self.assertEqual(r['interface_closes'],3);self.assertEqual(r['ds_exit'],1);self.assertEqual(r['core_exit'],1)

    def test_drift_rejection_and_offline_limits(self):
        with self.assertRaises(ValueError):audit.extract('anchor anchor end','anchor','end')
        with self.assertRaises(ValueError):audit.extract('end','anchor','end')
        for key in ('usb_accessed','sd_accessed','production_modified','firmware_packaged','hardware_verified',
                    'root_cause_confirmed','dma_executed','threads_executed'):
            self.assertFalse(self.result[key])
        self.assertEqual(list(self.output.rglob('*.nso')),[]);self.assertEqual(list(self.output.rglob('*.elf')),[])

if __name__=='__main__':unittest.main()
