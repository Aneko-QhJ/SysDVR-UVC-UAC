from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_status_capture_revision as audit


class StatusCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_STATUS_CAPTURE_REVIEW');cls.temp=None
        if saved:cls.root=Path(saved)
        else:
            cls.temp=tempfile.TemporaryDirectory(prefix='a23-status-capture-',dir='/private/tmp')
            cls.root=Path(cls.temp.name)/'review';audit.run(cls.root)
        cls.report=audit.verify(cls.root)
    @classmethod
    def tearDownClass(cls):
        if cls.temp:cls.temp.cleanup()
    def test_historical_originals_replay_without_modification(self):
        self.assertEqual(len(self.report['historical_status']),3)
        for row in self.report['historical_status'].values():
            self.assertTrue(row['new_status_passed']);self.assertEqual(row['report_count'],0);self.assertIsNotNone(row['old_rejection'])
        self.assertTrue(self.report['historical_native_status65_passed'])
    def test_count_zero_one_and_both_transitions_complete_two_epochs(self):
        self.assertEqual(set(self.report['accepted']),audit.SUCCESS)
        for name,row in self.report['accepted'].items():
            self.assertEqual(row['total_bytes'],6144);self.assertFalse(row['physical_run_authenticated'])
            self.assertEqual(self.report['native_matrix']['cases'][name]['iso_submissions'],2)
    def test_all_original_gates_still_reject_named_faults(self):
        for name,field in audit.FIELDS.items():self.assertIn(field,self.report['native_failures'][name])
        self.assertEqual(len(self.report['historical_negatives']),6)
    def test_failed_status_and_observation_are_durable(self):
        for name in ('bad-state','bad-transferred','bad-count','bad-terminal','short-after','bad-observation'):
            raw,observed,verdict=audit.snapshot(self.root/'models'/name/'status-after-epoch-0')
            self.assertTrue(verdict['raw_retained']);self.assertTrue(verdict['observation_json_retained'])
            self.assertEqual(len(raw['raw.bin']),167 if name=='short-after' else 168)
            self.assertEqual(observed['bytes_transferred'],len(raw['raw.bin']))
    def test_failed_capture_cannot_submit_next_epoch(self):
        cases=self.report['native_matrix']['cases']
        self.assertEqual(cases['status-before-collision']['iso_submissions'],0)
        for name,row in cases.items():
            if name not in audit.SUCCESS and name!='same-urb':self.assertLessEqual(row['iso_submissions'],1)
            self.assertEqual(row['sdk_destroys'],0)
    def test_second_urb_must_be_new(self):
        row=self.report['native_matrix']['cases']['same-urb']
        self.assertEqual(row['iso_submissions'],2);self.assertFalse(row['loop']['success']);self.assertTrue(row['loop']['unresolved_keep_alive'])
    def test_durable_status_cannot_be_missing_corrupt_or_rebound(self):
        self.assertEqual(len(self.report['archive_negatives']),4)
        self.assertTrue(all(x['rejected'] for x in self.report['archive_negatives'].values()))
    def test_original_sources_and_hardware_boundary_preserved(self):
        self.assertEqual(self.report['source_count'],592);self.assertEqual(self.report['prior_sources_unchanged'],587)
        for key in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations','authorization_consumptions','remaining'):
            self.assertEqual(self.report[key],0)
        self.assertFalse(self.report['formal_candidate_built']);self.assertFalse(self.report['new_scope_bound'])


if __name__=='__main__':unittest.main()
