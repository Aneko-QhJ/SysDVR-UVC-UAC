"""Joint preflight, per-ready-request trace budget and linked isolated ARM candidate."""
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_a23_bounded_candidate as bounded
from workflows.artifacts import verify

class A23BoundedCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=bounded.run(cls.output)
        cls.rows={r['case']:r for r in cls.result['cases']}
        cls.policies={r['case']:r for r in cls.result['policy_cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_prestatus_timeout_blocks_iso_payload_sequence_and_post(self):
        r=self.rows['prestatus-timeout']
        self.assertEqual((r['used'],r['pending'],r['iso_posts'],r['sequence']),(1,1,0,0))
        self.assertEqual(r['guard_reason'],6);self.assertFalse(r['normal_export'])
        self.assertEqual(r['diagnostic']['pending'],1)

    def test_complete_three_step_path_and_two_extra_statuses_remain_lossless(self):
        for case,count in (('complete',66),('session-extra-2',112)):
            r=self.rows[case];self.assertTrue(r['normal_export']);self.assertEqual(r['records'],count)
            self.assertEqual(r['dropped'],0);self.assertEqual(r['invalid'],0)
        r=self.rows['complete'];self.assertEqual(r['used'],6);self.assertEqual(r['largest_request'],17)
        paths=[g['path'] for g in r['ownership']['trace']['requests'] if g['interface']==2]
        self.assertEqual(paths,['iso_status','iso_post_and_ack_returned','iso_status'])

    def test_sixth_status_stops_before_copy_or_new_post_without_losing_trace(self):
        for case in ('statuses-6','statuses-8','statuses-9'):
            r=self.rows[case]
            self.assertEqual((r['dispatches'],r['used'],r['records'],r['dropped']),(6,10,115,0))
            self.assertEqual((r['in_posts'],r['out_posts']),(5,5))
            self.assertEqual((r['trace_refusals'],r['guard_reason']),(1,4))
            self.assertFalse(r['normal_export']);self.assertGreater(r['diagnostic_bytes'],0)

    def test_third_extra_status_stops_before_overflow_and_remaining_planned_requests(self):
        for case in ('session-extra-3','session-extra-5','session-extra-6'):
            r=self.rows[case]
            self.assertEqual((r['dispatches'],r['used'],r['records'],r['dropped']),(6,10,112,0))
            self.assertEqual(r['trace_refusals'],1);self.assertFalse(r['normal_export'])

    def test_all_129_capacity_offsets_accept_exact_fit_and_reject_one_short(self):
        self.assertEqual(self.result['policy_case_count'],138)
        for n in range(129):
            r=self.policies['limit-'+str(n)]
            self.assertTrue(r['passed']);self.assertTrue(r['iso_payload_untouched'])
            self.assertEqual(r['records'],n+17 if n<=111 else n)
            self.assertEqual(r['admitted'],int(n<=111))
            self.assertEqual(r['trace_refusals'],int(n>111))

    def test_followup_flood_within_one_process_call_stops_after_five_statuses(self):
        r=self.policies['followup-flood'];self.assertTrue(r['passed'])
        self.assertEqual((r['records'],r['admitted'],r['trace_refusals']),(115,15,1))
        s=(self.output/'admission-policy.c').read_text()
        self.assertIn('while (serviced && !Ep0CandidateStopRequested() &&',s)

    def test_joint_preflight_handles_iso_out_zero_and_proposed_range_overlap(self):
        for case in ('iso-borrowed','ack-out-borrowed','ack-zero-borrowed','proposed-alias','proposed-adjacent'):
            r=self.policies[case];self.assertTrue(r['passed']);self.assertTrue(r['iso_payload_untouched'])

    def test_two_identity_slots_are_required_before_iso_mutation(self):
        self.assertTrue(self.policies['slot-one-left']['passed'])
        self.assertTrue(self.policies['slot-one-left']['iso_payload_untouched'])

    def test_bound_violation_and_external_overflow_cannot_export_as_normal(self):
        self.assertEqual(self.policies['bound-violation']['bound_violations'],1)
        r=self.rows['trace-overflow'];self.assertEqual(r['dropped'],138)
        self.assertEqual(r['fault'],1);self.assertFalse(r['normal_export'])
        self.assertTrue(r['diagnostic']['diagnostic_only'])

    def test_duplicate_control_report_requests_stop_before_another_dispatch(self):
        r=self.rows['ctrl-duplicate'];self.assertEqual((r['dispatches'],r['pending']),(2,2))
        self.assertTrue(r['stopped']);self.assertFalse(r['normal_export'])
        self.assertEqual(r['guard_reason'],2)

    def test_stop_inside_wait_is_deferred_but_future_calls_are_skipped(self):
        r=self.rows['stop-inside-wait'];self.assertTrue(r['early_stop_attempted']);self.assertFalse(r['early_stop_accepted'])
        self.assertEqual(r['dispatches'],2);self.assertEqual(r['pending'],1)
        self.assertTrue(self.policies['stop-before-followup']['passed'])

    def test_all_19_control_reuse_regressions_still_have_no_overlap_or_repost(self):
        self.assertEqual(self.result['buffer_case_count'],19)
        for r in self.result['buffer_cases']:
            self.assertEqual(r['cpu_write_overlaps'],0);self.assertEqual(r['same_address_reposts'],0)
        for r in self.rows.values():
            self.assertEqual(r['bound_violations'],0);self.assertLessEqual(r['largest_request'],17)
            if r['case']!='trace-overflow':self.assertEqual(r['dropped'],0)

    def test_diagnostics_keep_faults_and_join_failures_do_not_take_over(self):
        self.assertEqual(self.result['diagnostic_count'],19);self.assertEqual(self.result['normal_capture_count'],5)
        for r in self.rows.values():
            if 'diagnostic' in r:
                self.assertFalse(r['diagnostic']['cleanup_authorized']);self.assertFalse(r['diagnostic']['ownership_export_accepted'])
        for case in ('video-join-error','audio-join-error','identity-error','zero-nonce'):
            r=self.rows[case];self.assertFalse(r['normal_export']);self.assertEqual(r['diagnostic_bytes'],0)

    def test_two_full_arm_configurations_link_nine_objects_with_distinct_recipes(self):
        a,b=(self.result['builds'][k] for k in ('dormant','window-30s'))
        self.assertNotEqual(a['runtime_recipe_digest'],b['runtime_recipe_digest'])
        for r in (a,b):self.assertEqual(r['object_count'],9);self.assertTrue(r['linked']);self.assertFalse(r['executed'])
        self.assertEqual((a['window_ms'],b['window_ms']),(0,30000))

    def test_frozen_sources_tickets_and_offline_limits(self):
        self.assertTrue(verify(self.output));self.assertTrue(verify(bounded.SEALED));self.assertTrue(verify(bounded.SESSION))
        self.assertEqual(self.result['source_audit'],bounded.base.owner.source_audit())
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(h,bounded.base.ep0.sha(bounded.base.ep0.PRIVATE/'analysis'/n))
        for key in ('production_modified','prior_runtime_modified','usb_accessed','sd_accessed','firmware_packaged',
                    'arm_executed','hardware_verified','root_cause_confirmed','actual_threads_executed','diagnostic_sink_in_candidate'):
            self.assertFalse(self.result[key])
        self.assertEqual(list(self.output.rglob('*.nso')),[])
        with self.assertRaises(ValueError):bounded.handler('bad anchor')

if __name__=='__main__':unittest.main()
