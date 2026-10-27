from pathlib import Path
import sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_two_epoch as a


class TwoEpochTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='a23-two-epoch-',dir='/private/tmp');cls.out=Path(cls.tmp.name)/'review'
        a.run(cls.out);cls.audit=a.w.load(cls.out/'audit.json');cls.cases=cls.audit['native_matrix']['cases']
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_frozen_prior317(self):self.assertEqual(len(a.sources()),323)
    def test_two_full_snapshots_reanalyzed(self):
        x=self.audit['accepted']['normal'];self.assertEqual(x['total_bytes'],6144)
        self.assertEqual([r['first_sequence'] for r in x['epochs']],[81,97])
        self.assertEqual(x['epochs'][1]['effective_slots'],list(range(120,136)))
    def test_finite_limits_and_retention(self):
        self.assertEqual(len(self.cases),47)
        for row in self.cases.values():
            if row.get('init_rejected'):continue
            self.assertLessEqual(row['iso_attempts'],2);self.assertLessEqual(row['trigger_attempts'],2);self.assertLessEqual(row['aborts'],1)
            self.assertTrue(row['all_stores_retained']);self.assertTrue(row['shared_resources_retained'])
    def test_first_save_failure_blocks_second(self):
        for key in ('save-collision','journal-failure'):
            self.assertEqual(self.cases[key]['iso_attempts'],1);self.assertEqual(self.cases[key]['saved_epochs'],0)
    def test_post_commit_failure_never_acknowledges_or_continues(self):
        for key in ('journal-after-commit','old-after-commit'):
            self.assertTrue((self.out/'models'/key/'epoch-0/COMMITTED').is_file())
            self.assertEqual(self.cases[key]['saved_epochs'],0);self.assertEqual(self.cases[key]['iso_attempts'],1)
    def test_callback_ingress_fences(self):
        self.assertEqual(self.cases['old-during-iso-intent']['iso_attempts'],1)
        self.assertEqual(self.cases['old-control-trigger-intent']['iso_attempts'],2)
        self.assertEqual(self.cases['old-control-trigger-intent']['trigger_attempts'],1)
        self.assertFalse(self.cases['old-after-complete']['complete'])
        self.assertEqual(self.cases['old-after-complete']['saved_epochs'],2)
    def test_urb_identity_and_save_order(self):
        self.assertEqual(self.cases['same-urb']['saved_epochs'],1)
        self.assertEqual(self.cases['stale-before-second']['iso_attempts'],1)
    def test_deadlines_are_terminal(self):
        for key in ('iso-timeout','control-timeout','late-control'):
            self.assertTrue(self.cases[key]['stopped']);self.assertEqual(self.cases[key]['saved_epochs'],0)
    def test_all_semantic_negative_archives(self):
        x=self.audit['negative_archives'];self.assertEqual(len(x),20)
        self.assertTrue(all(r['rejected'] for r in x.values()));self.assertGreaterEqual(sum(r['integrity_rebound'] for r in x.values()),10)
    def test_no_sdk_or_formal_authority(self):
        self.assertTrue(self.cases['real-blocked']['init_rejected'])
        for name in ('usb_requests','sd_accesses','real_sdk_objects','formal_reservations','formal_records','remaining'):self.assertEqual(self.audit[name],0)
        plan=a.w.load(self.out/'offline-plan.json');self.assertFalse(plan['sequence_ranges_allocated']);self.assertFalse(plan['sdk_provider_implemented'])


if __name__=='__main__':unittest.main()
