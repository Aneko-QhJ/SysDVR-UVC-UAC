"""Offline actual-source guard behavior, cleanup authorization and ARM link checks."""
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_a23_guard_candidate as guard
from workflows.artifacts import verify

class A23GuardCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name)
        cls.result=guard.run(cls.output)
        cls.buffers={r['case']:r for r in cls.result['buffer_cases']}
        cls.exits={r['case']:r for r in cls.result['exit_cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_all_actual_source_replays_block_overlapping_copy_and_repost(self):
        self.assertEqual(self.result['buffer_case_count'],19)
        for pair in self.buffers.values():
            r=pair['guarded']
            self.assertEqual(r['cpu_write_overlaps'],0)
            self.assertEqual(r['changed_pending_bytes'],0)
            self.assertEqual(r['same_address_reposts'],0)
            if pair['previous']['same_address_reposts']:
                self.assertGreater(r['guard_denials'],0)
                self.assertTrue(r['guard_stop_requested'])
                self.assertEqual(r['ledger_fault'],1)
                self.assertFalse(r['ledger_export_allowed'])

    def test_completed_or_disjoint_requests_keep_original_service_observations(self):
        for case in ('drained','in-terminal-4','in-terminal-5','burst-ack-terminal-4','cross-vc'):
            pair=self.buffers[case];r=pair['guarded']
            self.assertEqual(r['guard_denials'],0)
            self.assertFalse(r['guard_stop_requested'])
            for key,value in pair['previous'].items():self.assertEqual(r[key],value,(case,key))

    def test_zero_length_identity_still_blocks_shared_pointer_reuse(self):
        for case in ('burst-ack-timeout','out-status-timeout'):
            r=self.buffers[case]['guarded']
            self.assertEqual(r['pending_nonzero_spans'],0)
            self.assertEqual(r['pending_zero_spans'],1)
            self.assertEqual(r['guard_reason'],6)
            self.assertEqual(r['same_address_reposts'],0)

    def test_late_report_is_not_polled_by_an_unsafe_new_request(self):
        pair=self.buffers['late-report-after-copy'];r=pair['guarded']
        self.assertTrue(pair['previous']['ledger_export_allowed'])
        self.assertEqual(pair['previous']['cpu_write_overlap_bytes'],168)
        self.assertEqual(r['ctrl_reports'],0)
        self.assertEqual(r['in_posts'],1)
        self.assertEqual(r['ledger_pending'],1)
        self.assertFalse(r['ledger_export_allowed'])
        self.assertFalse(self.result['live_late_report_recovery_implemented'])

    def test_range_identity_reservation_and_atomic_phase_policies(self):
        self.assertEqual(self.result['policy_case_count'],9)
        self.assertEqual({r['case'] for r in self.result['policy_cases']},set(guard.POLICY_CASES))
        self.assertTrue(all(r['passed'] for r in self.result['policy_cases']))

    def test_adapter_post_errors_zero_id_and_missing_or_invalid_binding(self):
        self.assertEqual(self.result['adapter_case_count'],5)
        self.assertEqual({r['case'] for r in self.result['adapter_cases']},set(guard.ADAPTER_CASES))
        for r in self.result['adapter_cases']:
            self.assertTrue(r['passed']);self.assertEqual(r['fault'],1)
            self.assertTrue(r['stop_requested']);self.assertFalse(r['export_allowed'])

    def test_callback_without_authorization_retains_even_when_urbs_drained(self):
        self.assertEqual(self.result['exit_case_count'],10)
        for case in ('callback-live','callback-stopped-pending','callback-drained','callback-claimed','callback-unstarted'):
            r=self.exits[case];self.assertTrue(r['held']);self.assertEqual(r['joins'],0)
            for key in ('thread_closes','interface_closes','ds_exit','core_exit','sm_exit','saves'):
                self.assertEqual(r[key],0,(case,key))

    def test_join_pending_or_save_failure_never_authorizes_cleanup(self):
        for case in ('candidate-pending','candidate-video-join-error','candidate-audio-join-error','candidate-sink-error'):
            r=self.exits[case];self.assertTrue(r['held']);self.assertEqual(r['joins'],2)
            for key in ('thread_closes','interface_closes','ds_exit','core_exit','sm_exit'):
                self.assertEqual(r[key],0,(case,key))
            self.assertEqual(r['saves'],int(case=='candidate-sink-error'))

    def test_authorized_normal_exit_and_repeated_callback_clean_once(self):
        r=self.exits['candidate-drained'];self.assertFalse(r['held'])
        for key,value in dict(joins=2,thread_closes=2,interface_closes=3,ds_exit=1,core_exit=1,sm_exit=1,saves=1).items():
            self.assertEqual(r[key],value)
        self.assertEqual(r['live_interface_closes'],0)
        self.assertEqual(r['pending_interface_closes'],0)

    def test_two_arm_configurations_bind_distinct_recipes_and_link_eight_objects(self):
        a,b=(self.result['builds'][k] for k in ('dormant','window-30s'))
        self.assertEqual((a['window_ms'],b['window_ms']),(0,30000))
        self.assertNotEqual(a['runtime_recipe_digest'],b['runtime_recipe_digest'])
        for r in (a,b):
            self.assertTrue(r['linked']);self.assertFalse(r['executed']);self.assertEqual(r['object_count'],8)
        self.assertTrue(verify(self.output))

    def test_offline_boundaries_and_unchanged_production_and_tickets(self):
        for key in ('usb_accessed','sd_accessed','production_modified','prior_runtime_modified','firmware_packaged',
                    'hardware_verified','root_cause_confirmed','early_unstarted_cleanup_allowed'):
            self.assertFalse(self.result[key])
        self.assertEqual(self.result['source_audit'],guard.base.owner.source_audit())
        for name,digest in self.result['tickets_sha256'].items():
            self.assertEqual(digest,guard.base.ep0.sha(guard.base.ep0.PRIVATE/'analysis'/name))
        self.assertFalse(self.result['original_usb_behavior_preserved_on_guard_denial'])
        self.assertEqual(list(self.output.rglob('*.nso')),[])

if __name__=='__main__':unittest.main()
