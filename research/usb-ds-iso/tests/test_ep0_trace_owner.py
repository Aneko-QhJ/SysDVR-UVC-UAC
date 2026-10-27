"""Owner handoff and DMA evidence gates; injected services, no hardware access."""
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_trace_owner as owner
from analyze_ep0_trace import decode


class Ep0TraceOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name)
        cls.audit=owner.run(cls.output)
        cls.rows={r['case']:r for r in cls.audit['policy_cases']}

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_timeout_cancel_disconnect_and_nonterminal_reports_preserve_ownership(self):
        for case in ('wait-timeout','cancel-only','disconnect','wrong-id','wrong-channel',
                     'state-1','state-2','unknown-status','failed-report'):
            with self.subTest(case=case):
                self.assertEqual(self.rows[case]['pending'],1)
                self.assertEqual(self.rows[case]['exported_bytes'],0)

    def test_uncertain_posts_bad_batches_reuse_and_capacity_remain_fail_closed(self):
        for case in ('count-9','duplicate-report','failed-post','missing-id','reuse','capacity','reentrant'):
            with self.subTest(case=case):
                self.assertEqual(self.rows[case]['fault'],1)
                self.assertEqual(self.rows[case]['exported_bytes'],0)

    def test_no_export_before_successful_join_and_no_freeze_inside_handler(self):
        for case in ('prejoin','failed-join'):
            self.assertFalse(self.rows[case]['joined']);self.assertEqual(self.rows[case]['exported_bytes'],0)
        for case in ('inside-call','wrong-writer','immutable'):
            self.assertEqual(self.rows[case]['exported_bytes'],128)

    def test_identity_channels_and_terminal_failure_are_distinct_from_transfer_success(self):
        for case in ('happy','terminal-4','terminal-5','zero-id','same-id-other-channel'):
            self.assertEqual(self.rows[case]['pending'],0)
            self.assertEqual(self.rows[case]['exported_bytes'],128)
        self.assertEqual(self.audit['libnx_parse_matched_status_results'],
                         {'3':0,'4':0x828c,'5':0x748c,'other':0x108c})
        self.assertEqual(self.rows['wrong-id']['unmatched'],1)
        self.assertEqual(self.rows['wrong-channel']['unmatched'],1)

    def test_late_terminal_updates_ledger_without_mutating_frozen_trace(self):
        self.assertEqual(self.rows['late-terminal']['pending'],0)
        self.assertEqual(self.rows['late-terminal']['exported_bytes'],128)

    def test_exportable_incomplete_trace_never_claims_complete_capture(self):
        row=self.rows['trace-overflow'];self.assertEqual(row['trace_dropped'],1)
        self.assertEqual(row['exported_bytes'],6272)
        for binary in self.output.glob('*.bin'):
            if binary.name=='usbds-parse.bin':continue
            self.assertFalse(decode(binary.read_bytes())['trace_window_complete'])

    def test_libnx_link_is_adapter_fixture_and_existing_exit_has_no_regular_trigger(self):
        self.assertEqual(self.audit['policy_case_count'],28)
        self.assertTrue(self.audit['libnx_adapter_full_elf_link'])
        self.assertFalse(self.audit['complete_instrumented_a23_firmware_link'])
        self.assertFalse(self.audit['actual_handler_owner_hooks_inserted'])
        self.assertFalse(self.audit['filesystem_sink_implemented'])
        self.assertFalse(self.audit['source_audit']['regular_stop_trigger_present'])
        for key in ('hardware_verified','root_cause_confirmed','usb_accessed','sd_accessed','production_modified'):
            self.assertFalse(self.audit[key])

    def test_source_drift_rejected_before_compilation(self):
        with patch.object(owner.ep0,'sha',return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'Production sources differ'):owner.source_audit()


if __name__=='__main__':unittest.main()
