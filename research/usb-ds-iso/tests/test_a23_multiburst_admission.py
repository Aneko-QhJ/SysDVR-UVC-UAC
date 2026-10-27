"""Native injected services and proposed coordinator; no device/receiver calls."""
import copy
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import audit_a23_multiburst_admission as a
w=a.w

class DeviceAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-multiburst-tests-')
        cls.root=Path(cls.temp.name).resolve();cls.report=a.run(cls.root/'audit');cls.rows=cls.report['native_cases']
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_single_matches_observed84_records_and7_identities(self):
        r=self.rows['single'];self.assertEqual((r['records'],r['used'],r['iso_posts'],r['sequence']),(84,7,1,81))
        self.assertTrue(r['normal_export']);self.assertEqual(r['pending'],0)
    def test_full_two_cycles_fit_but_fourth_refuses_before_iso_post(self):
        r=self.rows['full-two'];self.assertEqual((r['records'],r['used'],r['iso_posts']),(150,13,2));self.assertTrue(r['normal_export'])
        r=self.rows['full-four'];self.assertEqual((r['records'],r['iso_posts'],r['sequence']),(242,3,113))
        self.assertEqual(r['trace_refusals'],1);self.assertFalse(r['normal_export'])
    def test_shared_status_two_bursts_have129_records_of_headroom(self):
        r=self.rows['chained-two'];self.assertEqual((r['records'],r['used'],r['iso_posts'],r['sequence']),(127,11,2,97))
        self.assertEqual(r['pending'],0);self.assertTrue(r['normal_export'])
    def test_five_bursts_exact_fit_but_sixth_and_extra_status_refused(self):
        r=self.rows['chained-five'];self.assertEqual((r['records'],r['iso_posts']),(256,5));self.assertTrue(r['normal_export'])
        for case in ('chained-six','five-extra'):
            r=self.rows[case];self.assertEqual((r['records'],r['iso_posts']),(256,5))
            self.assertTrue(r['stop_requested']);self.assertFalse(r['normal_export'])
    def test_all257_prefix_offsets_have_exact147_record_limit(self):
        for n in range(257):
            r=self.rows['prefix-'+str(n)];self.assertEqual(r['normal_export'],n<=147,n)
            self.assertLessEqual(r['records'],256,n);self.assertEqual(r['dropped'],0,n)
    def test_pending_foreign_or_error_report_cannot_retrigger(self):
        for case in ('pending','foreign-terminal','report-error'):
            r=self.rows[case];self.assertEqual(r['iso_posts'],1,case);self.assertEqual(r['sequence'],81,case)
            self.assertGreater(r['pending'],0,case);self.assertFalse(r['normal_export'],case)
    def test_id_reuse_after_terminal_faults_without_rollback(self):
        r=self.rows['duplicate-id'];self.assertEqual(r['iso_posts'],2)
        self.assertEqual(r['fault'],1);self.assertFalse(r['normal_export'])
    def test_terminal_failure_allows_memory_reuse_but_is_not_a_success_gate(self):
        for case in ('terminal4','terminal5'):
            r=self.rows[case];self.assertEqual(r['iso_posts'],2,case);self.assertTrue(r['normal_export'],case)
    def test_disconnect_after_completed_owners_uses_one_trace_slot(self):
        r=self.rows['disconnect'];self.assertEqual(r['records'],128);self.assertTrue(r['normal_export'])
    def test_real_functions_headers_source_and_all_old23_are_bound(self):
        r=self.report;self.assertEqual(len(r['native_binding']['deployed_functions']),5)
        self.assertEqual(r['source_count'],313);self.assertEqual(a.sources(),r['source_hashes'])
        self.assertEqual(r['native_case_count'],273);self.assertEqual(r['coordinator_case_count'],8)
        self.assertEqual(r['native_binding']['deployed_trace_capacity'],256)
        self.assertEqual(r['native_binding']['deployed_owner_slots'],32)
        for key in ('usb_requests','sd_accesses','formal_reservations','formal_records','real_sdk_objects','remaining'):self.assertEqual(r[key],0)
        self.assertFalse((w.LEDGER/'block-00081.json').exists());self.assertFalse(r['firmware_built'])
    def test_function_extraction_ignores_braces_in_strings_and_comments(self):
        text='void example(void) { const char *s="}"; /* { */ if(1) { } }\n'
        start,end=a.function_span(text,'void example(void)');self.assertEqual(text[start:end],text.strip())
        with self.assertRaises(ValueError):a.function_span(text+text,'void example(void)')

class CoordinatorModelTests(unittest.TestCase):
    def prepared(self):
        m=a.ContinuationModel();o=m.submit();self.assertTrue(m.trigger());return m,o
    def callback(self,m,ordinal=0):return m.callback(ordinal,sequences=list(range(81+ordinal*16,97+ordinal*16)))
    def finish_first(self,m):
        m.control_callback(0);self.callback(m);self.assertTrue(m.complete(a.witness(81)))
    def test_two_commits_have_distinct_stores_and_bound_sequences(self):
        m,o=self.prepared();self.finish_first(m);second=m.submit();m.trigger();m.control_callback(1);self.callback(m,1)
        self.assertTrue(m.complete(a.witness(97)));self.assertEqual(m.phase,'complete')
        self.assertEqual((o.first,second.first),(81,97));self.assertEqual(len({o.data_id,o.transactions_id,second.data_id,second.transactions_id}),4)
        self.assertTrue(all(o.saved for o in m.owners));self.assertFalse(m.submit());self.assertEqual(len(m.owners),2)
    def test_nonzero_continuation_is_expected_only_after_first_commit(self):
        m,o=self.prepared();m.control_callback(0);self.callback(m)
        self.assertFalse(m.complete(a.witness(97)));self.assertTrue(o.quarantined)
    def test_no_second_submission_before_callback_and_durable_save(self):
        m,o=self.prepared();self.assertFalse(m.submit());self.assertEqual(len(m.owners),1)
        m,o=self.prepared();m.control_callback(0);self.callback(m);self.assertFalse(m.complete(a.witness(81),saved=False))
        self.assertFalse(m.submit());self.assertFalse(o.saved)
    def test_control_callback_can_follow_iso_before_commit(self):
        m,o=self.prepared();self.assertTrue(self.callback(m));self.assertTrue(m.control_callback(0))
        self.assertTrue(m.complete(a.witness(81)))
    def test_missing_or_duplicate_control_callback_stops(self):
        m,o=self.prepared();self.callback(m);self.assertFalse(m.complete(a.witness(81)))
        m,o=self.prepared();m.control_callback(0);self.assertFalse(m.control_callback(0));self.assertTrue(o.quarantined)
    def test_late_old_callback_during_second_burst_quarantines_both(self):
        m,o=self.prepared();self.finish_first(m);second=m.submit();m.trigger()
        self.assertFalse(self.callback(m));self.assertTrue(o.quarantined and second.quarantined)
        self.assertFalse(m.trigger());self.assertFalse(m.submit())
    def test_wrong_pointer_status_size_or_sequence_all_stop(self):
        for changed in (dict(pointer_matches=False),dict(status=1),dict(actual=0),dict(sequences=list(range(65,81))),dict(sequences=[float(n) for n in range(81,97)])):
            m,o=self.prepared();args=dict(sequences=list(range(81,97)));args.update(changed)
            self.assertFalse(m.callback(0,**args));self.assertTrue(o.quarantined)
    def test_bool_is_not_a_numeric_success_or_ordinal(self):
        for changed in (dict(status=False),dict(actual=True)):
            m,o=self.prepared();self.assertFalse(m.callback(0,sequences=list(range(81,97)),**changed))
        m,o=self.prepared();self.assertFalse(m.control_callback(False))
    def test_callback_before_trigger_or_duplicate_never_advances(self):
        m=a.ContinuationModel();m.submit();self.assertFalse(self.callback(m))
        m,o=self.prepared();self.callback(m);self.assertFalse(self.callback(m));self.assertFalse(m.complete(a.witness(81)))
    def test_each_device_witness_field_is_required_and_exact(self):
        for key in a.witness(81):
            m,o=self.prepared();m.control_callback(0);self.callback(m);bad=a.witness(81);bad.pop(key)
            self.assertFalse(m.complete(bad),key)
    def test_pending_retained_failed_short_or_wrong_identity_device_blocks(self):
        for key,value in [('state',1),('state',4),('state',3),('urb_status',4),('urb_status',5),('transferred',0),('report_id',1),('trace_lossless',False),('iso7_bitmap',255)]:
            m,o=self.prepared();m.control_callback(0);self.callback(m);d=a.witness(81);d[key]=value
            self.assertFalse(m.complete(d),(key,value));self.assertFalse(m.submit())
    def test_exit_detach_timeout_never_release_or_retry(self):
        for reason in ('exit','detach','timeout','journal-failure'):
            m,o=self.prepared();m.stop(reason);self.assertTrue(o.quarantined);self.assertFalse(m.submit());self.assertEqual(len(m.owners),1)
    def test_reserved_ranges_unaligned_boolean_and_wrap_are_refused(self):
        for first in (1,49,65,True,82,65505):
            with self.assertRaises(ValueError):a.ContinuationModel(first)
        for count in (True,0,1,3):
            with self.assertRaises(ValueError):a.ContinuationModel(count=count)
    def test_eight_coordinator_scenarios_keep_all_model_stores(self):
        rows=a.model_cases();self.assertEqual(rows['normal']['phase'],'complete')
        for name,row in rows.items():
            self.assertEqual(row['owners'],2);self.assertTrue(row['distinct_storage_identities'])
            if name!='normal':self.assertEqual(row['quarantined'],2)

if __name__=='__main__':unittest.main()
