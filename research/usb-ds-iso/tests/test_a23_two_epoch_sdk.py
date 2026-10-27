from pathlib import Path
import sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_two_epoch_sdk as a

class SDKDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='a23-sdk-driver-',dir='/private/tmp');cls.out=Path(cls.tmp.name)/'review'
        a.run(cls.out);cls.audit=a.w.load(cls.out/'audit.json');cls.cases=cls.audit['matrix']['cases']
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_frozen_sources_and_derivations(self):
        self.assertEqual(len(a.sources()),336);self.assertEqual(len(a.derivations(self.out/'source')),2)
    def test_native_mode_and_unused_gates(self):
        for name in ('mock-provider','reused-status','poisoned-before-init'):self.assertTrue(self.cases[name]['init_rejected'])
        self.assertEqual(self.cases['reused-status']['lease']['iso_attempts'],0)
    def test_two_clean_sdk_shaped_models(self):
        self.assertEqual(set(self.audit['accepted']),{'normal','queued-delay'})
        for row in self.audit['accepted'].values():
            self.assertEqual(row['input_origin'],'injected_sdk_model');self.assertEqual(row['total_bytes'],6144)
            self.assertGreaterEqual(row['observation_window_ns'],250000000);self.assertFalse(row['physical_run_authenticated'])
    def test_queue_delay_uses_native_ingress(self):
        self.assertTrue(self.cases['queued-delay']['result']['complete']);self.assertEqual(self.cases['queued-delay']['result']['aborts'],0)
    def test_quiet_window_not_complete_and_does_not_consume_receipt(self):
        x=self.cases['quiet-incomplete'];self.assertEqual(x['result']['saved_epochs'],2)
        self.assertFalse(x['result']['complete']);self.assertFalse(x['result']['stopped']);self.assertFalse(x['receipt_status']['attempted'])
    def test_late_callbacks_invalidate_even_after_receipt(self):
        for n in ('old-during-quiet','old-after-observation','old-after-receipt'):
            self.assertFalse(self.cases[n]['result']['complete']);self.assertTrue(self.cases[n]['result']['stopped'])
        self.assertTrue(self.cases['old-after-receipt']['receipt_status']['stale']);self.assertFalse(self.cases['old-after-receipt']['receipt_status']['saved'])
    def test_resource_fault_invalidates_upper_driver(self):
        for n in ('extra-status-after-observation','third-iso-after-observation'):
            self.assertTrue(self.cases[n]['result']['lease']['poisoned']);self.assertTrue(self.cases[n]['result']['stopped'])
    def test_commit_without_journal_ack_does_not_advance(self):
        x=self.cases['journal-after-commit']['result'];self.assertEqual(x['saved_epochs'],0)
        self.assertTrue((self.out/'models/journal-after-commit/epoch-0/COMMITTED').is_file());self.assertEqual(x['iso_attempts'],1)
    def test_lifetime_and_limits(self):
        for x in self.cases.values():
            if x.get('init_rejected'):continue
            self.assertEqual(x['live_references'],1);self.assertEqual(x['destroys'],0)
            r=x['result'];self.assertLessEqual(r['iso_attempts'],2);self.assertLessEqual(r['trigger_attempts'],2);self.assertLessEqual(r['aborts'],1)
            self.assertTrue(r['all_stores_retained']);self.assertFalse(r['callback_drain_verified'])
    def test_twenty_semantic_and_integrity_negatives(self):
        self.assertEqual(len(self.audit['negative_archives']),20)
        self.assertTrue(all(x['rejected'] and x['integrity_rebound'] for x in self.audit['negative_archives'].values()))
        for n in ('mock-status','mock-frame','mock-budget','short-quiet','poisoned-lease','mixed-origin'):
            self.assertNotIn('hash differs',self.audit['negative_archives'][n]['reason'])
    def test_receipt_failure_and_partial_checkpoint_never_clean(self):
        self.assertIn('receipt-collision',self.audit['rejected']);self.assertIn('quiet-journal-failure',self.audit['rejected'])
        self.assertFalse(self.cases['receipt-collision']['receipt_status']['saved'])
    def test_no_hardware_or_issuance_authority(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations','remaining'):self.assertEqual(self.audit[k],0)
        self.assertFalse(self.audit['actual_sdk_mapping_tested']);self.assertFalse(self.audit['firmware_built'])

if __name__=='__main__':unittest.main()
