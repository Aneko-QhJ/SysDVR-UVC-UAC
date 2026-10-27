from pathlib import Path
import sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_paired_sdk as a


class PairedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='a23-paired-',dir='/private/tmp');cls.out=Path(cls.tmp.name)/'review'
        a.run(cls.out);cls.audit=a.w.load(cls.out/'audit.json');cls.prep=cls.audit['matrix']['preparation'];cls.runtime=cls.audit['matrix']['runtime']
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_old323_unchanged(self):self.assertEqual(len(a.sources()),329)
    def test_one_open_one_pipe_four_allocations(self):
        p=self.prep['clean'];self.assertEqual([p[k] for k in ('opens','copies','allocations','retains','releases','destroys')],[1,1,4,1,1,1])
        x=self.runtime['normal'];self.assertEqual(x['mapped_calls'],4);self.assertEqual(x['pipe_copies'],1);self.assertEqual(x['destroys'],0)
    def test_mode_boundaries_before_service_access(self):
        for n in ('simulation-mode-blocked','sdk-mode-blocked'):
            self.assertEqual(self.prep[n]['retains'],0);self.assertEqual(self.prep[n]['opens'],0)
        self.assertTrue(self.runtime['sdk-core-rejected']['core_rejected_sdk_mode'])
    def test_null_error_pointer_does_not_hide_sdk_error(self):
        x=self.prep['retain-with-error'];self.assertTrue(x['failed_preparation_cleaned']);self.assertEqual(x['releases'],1);self.assertEqual(x['opens'],0)
    def test_partial_maps_retained_on_interest(self):
        for n,count in (('interest-open',0),('interest-allocate',3),('interest-final',4),('mode-change-allocate',2)):
            x=self.prep[n];self.assertEqual(x['live_references'],1);self.assertEqual(x['destroys'],0)
            self.assertEqual(x['retained_failure']['store_count'],count);self.assertTrue(x['failed_preparation_quarantined'])
    def test_real_address_overlap_rejected_packed_alignment_allowed(self):
        self.assertTrue(self.prep['overlap-tables']['failed_preparation_cleaned'])
        self.assertTrue(self.prep['alias-data1']['failed_preparation_cleaned'])
        self.assertEqual(self.prep['packed-table']['stage'],'prepared')
    def test_final_identity_after_allocations(self):
        x=self.prep['identity-after-maps'];self.assertEqual(x['allocations'],4);self.assertEqual(x['destroys'],1);self.assertEqual(x['releases'],1)
    def test_bounded_active_resources_never_destroyed(self):
        for row in self.runtime.values():
            if row.get('core_rejected_sdk_mode'):continue
            self.assertEqual(row['service_retained'],1);self.assertEqual(row['destroys'],0)
            self.assertLessEqual(row['lease']['iso_attempts'],2);self.assertLessEqual(row['lease']['trigger_attempts'],2);self.assertLessEqual(row['lease']['aborts'],1)
    def test_combined_receipt_rejects_post_completion_faults(self):
        for name in ('third-iso','extra-status'):
            self.assertTrue(self.runtime[name]['receiver']['complete']);self.assertTrue(self.runtime[name]['lease']['poisoned']);self.assertIn(name,self.audit['rejected'])
        self.assertEqual(set(self.audit['accepted']),{'normal'})
    def test_negative_receipts_and_sdk_accessors(self):
        self.assertEqual(len(self.audit['negative_receipts']),12);self.assertEqual(len(self.audit['sdk_accessors_bound']),7)
        self.assertTrue(all(r['rejected'] for r in self.audit['negative_receipts'].values()))
    def test_no_hardware_authority(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations','remaining'):self.assertEqual(self.audit[k],0)
        self.assertFalse(self.audit['actual_sdk_mapping_tested'])


if __name__=='__main__':unittest.main()
