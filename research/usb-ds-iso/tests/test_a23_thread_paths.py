"""Per-call wait profiles, capture retry limits and a dormant shared-flag hazard."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_thread_paths as audit
from workflows.artifacts import verify

class A23ThreadPathsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=audit.run(cls.output)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def text(self):return (self.output/'dormant/disassembly.txt').read_text()
    def cert(self):return copy.deepcopy(self.result['wait_site_certificates']['dormant'])
    def rows(self):return json.loads((self.output/'dormant/stack-usage.json').read_text())
    def test_exact_two_wait_objects_sites_have_different_counts(self):
        for c in self.result['wait_site_certificates'].values():
            sites={r['caller']:r for r in c['sites']};self.assertEqual(set(sites),{'eventWait','UvcDeviceProcessRequests'})
            self.assertEqual((sites['eventWait']['count'],sites['eventWait']['wait_objects_observed_peak_bytes']),(1,304))
            self.assertEqual((sites['UvcDeviceProcessRequests']['count'],sites['UvcDeviceProcessRequests']['wait_objects_observed_peak_bytes']),(3,400))
    def test_three_event_mixed_types_and_error_retry_profiles(self):
        for c in self.result['wait_site_certificates'].values():
            rows=c['three_event_profiles'];self.assertEqual(len(rows),32)
            self.assertEqual(len({tuple(r['types']) for r in rows}),8)
            self.assertEqual({r['name'] for r in rows},{'ok','timeout','cancel','reset-retry'})
            for r in rows:self.assertTrue(r['stack_restored']);self.assertFalse(r['indirect_callbacks_reached']);self.assertLessEqual(r['peak_user_stack_bytes'],400)
            for r in rows:
                if r['name']=='timeout':self.assertEqual(r['result'],0xea01)
                else:self.assertEqual(r['result'],0)
    def test_site_scoped_substitution_removes_wait_unknowns_and_keeps_others(self):
        for g in self.result['conditional_stacks'].values():
            video=g['roots']['VideoStreamThread'];self.assertEqual(len(video['used_sites']),2)
            self.assertFalse(any('waitObjects:' in v for v in video['unresolved']))
            self.assertTrue(any('CaptureReadVideoFrame: recursive' in v for v in video['unresolved']))
            self.assertTrue(any('_svfprintf_r:' in v and 'indirect' in v for v in video['unresolved']))
            self.assertTrue(any('diagAbortWithResult:' in v for v in video['unresolved']))
            self.assertIsNone(video['stack_bound_bytes'])
    def test_original_strict_save_and_capture_bounds_preserved(self):
        for g in self.result['conditional_stacks'].values():
            self.assertEqual(g['strict_roots']['Ep0SessionSaveJoined']['stack_bound_bytes'],768)
            self.assertEqual(g['strict_roots']['session_capture']['stack_bound_bytes'],352)
            self.assertIsNone(g['strict_roots']['VideoStreamThread']['stack_bound_bytes'])
    def test_certificate_rejects_changed_event_count_instruction(self):
        text=self.text().replace('mov\tw2, #0x1','mov\tw2, #0x2')
        with self.assertRaisesRegex(ValueError,'function drift'):audit.conditional_graph(text,self.rows(),self.cert())
    def test_certificate_rejects_three_event_machine_drift(self):
        text=self.text().replace('mov\tw2, #0x3','mov\tw2, #0x4')
        with self.assertRaisesRegex(ValueError,'function drift'):audit.conditional_graph(text,self.rows(),self.cert())
    def test_certificate_rejects_unbound_sdk_function(self):
        text=self.text().replace('svc\t#0x18','svc\t#0x19')
        with self.assertRaisesRegex(ValueError,'function drift'):audit.conditional_graph(text,self.rows(),self.cert())
    def test_certificate_rejects_relabeling_profiles_as_proof(self):
        c=self.cert();c['full_symbolic_proof']=True
        with self.assertRaisesRegex(ValueError,'assert proof'):audit.conditional_graph(self.text(),self.rows(),c)
    def test_certificate_rejects_wrong_peak_and_call_edge(self):
        for field,value in (('wait_objects_observed_peak_bytes',352),('at',1)):
            c=self.cert();c['sites'][0][field]=value
            with self.assertRaises(ValueError):audit.conditional_graph(self.text(),self.rows(),c)
    def test_sequential_init_failures_never_loop_indefinitely(self):
        rows=[r for r in self.result['capture_audit']['cases'] if not r['control']];self.assertEqual(len(rows),16)
        cases={(r['case'],r['stream']):r for r in rows}
        for s in (0,1):
            key='audio_transfers' if s else 'video_transfers'
            self.assertEqual(cases['init-ok',s][key],2);self.assertTrue(cases['init-ok',s]['ok'])
            for n in ('init-repeated-error','init-retry-error'):self.assertEqual(cases[n,s][key],2);self.assertFalse(cases[n,s]['ok'])
            self.assertEqual(cases['init-error',s][key],1);self.assertFalse(cases['init-error',s]['ok'])
            self.assertEqual(cases['cross-stream',s]['begin_calls'],1)
    def test_native_flag_race_detected_for_both_reader_orders(self):
        rows=[r for r in self.result['capture_audit']['race_cases'] if not r['control']];self.assertEqual(len(rows),2)
        for r in rows:
            self.assertTrue(r['tsan_expected_race']);self.assertEqual(r['exit_code'],66)
            report=(self.output/('actual-race-'+str(r['stream'])+'.stderr')).read_text()
            self.assertIn("global 'g_grcdBeginCalled'",report);self.assertEqual(report.count('WARNING: ThreadSanitizer: data race'),1)
    def test_read_under_lock_control_is_clean_and_preserves_sequential_results(self):
        c=self.result['capture_audit'];rows=c['race_cases'];self.assertEqual(len(rows),4)
        for r in rows:
            if r['control']:self.assertEqual(r['exit_code'],0);self.assertFalse(r['tsan_expected_race'])
        before=[{k:v for k,v in r.items() if k!='control'} for r in c['cases'] if not r['control']]
        after=[{k:v for k,v in r.items() if k!='control'} for r in c['cases'] if r['control']];self.assertEqual(before,after)
        self.assertTrue(c['locked_read_control_test_only'])
    def test_host_source_keeps_actual_flag_logic_and_control_is_explicit(self):
        raw=(audit.REPO/'source/capture.c').read_text();actual=audit.native_source();control=audit.native_source(True)
        helper=raw.split('static bool _ensureGrcdInit',1)[1].split('// ============================================================================',1)[0]
        self.assertIn(helper,actual);self.assertNotIn(helper,control)
        self.assertIn('#define CAPTURE_LOCKED_CONTROL 0',actual);self.assertIn('#define CAPTURE_LOCKED_CONTROL 1',control)
        self.assertIn('alignas(64) atomic_bool second_completed',actual)
    def test_uac_disabled_prerequisite_does_not_prune_or_claim_actual_race(self):
        r=self.result['current_uac_reachability'];self.assertTrue(r['uac_setup_disabled_in_current_candidate']);self.assertTrue(r['uac_positive_initializer_not_linked'])
        self.assertFalse(r['audio_capture_pruned_from_stack_graph']);self.assertTrue(r['host_race_is_not_current_switch_execution_evidence'])
        self.assertFalse(self.result['capture_audit']['actual_switch_concurrent_capture_reachability_verified'])
    def test_seals_elf_sources_and_tickets_preserved(self):
        for p in (self.output,audit.SEALED):self.assertTrue(verify(p))
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.REPO/n),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.base.ep0.PRIVATE/'analysis'/n),h)
    def test_profiles_and_models_cannot_authorize_hardware_or_cleanup(self):
        for key in ('prior_runtime_modified','production_modified','prior_evidence_modified','new_arm_build','arm_executed','firmware_packaged','actual_switch_threads_executed','usb_accessed','sd_accessed','cleanup_authorized','full_symbolic_proof','whole_thread_stack_verified','real_wait_or_stop_time_bound','hardware_verified','root_cause_confirmed'):
            self.assertFalse(self.result[key],key)
        for c in self.result['wait_site_certificates'].values():self.assertFalse(c['full_symbolic_proof']);self.assertTrue(c['observed_profiles_only']);self.assertFalse(c['termination_bound_verified'])
        self.assertEqual(list(self.output.rglob('*.elf')),[])
if __name__=='__main__':unittest.main()
