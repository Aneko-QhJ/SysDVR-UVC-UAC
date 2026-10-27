from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_capture_window as a
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_WINDOW_REVIEW'):cls.root=Path(os.environ['A23_WINDOW_REVIEW'])
        else:cls.tmp=tempfile.TemporaryDirectory(prefix='a23-window-tests-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';a.run(cls.root)
        a.w.card.seal_verify(cls.root);cls.audit=a.f.load(cls.root/'audit.json');cls.rows={n:v['result']['analysis'] for n,v in cls.audit['matrix'].items()}
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def test_406_preserves402_with_native392(self):self.assertEqual(len(a.sources()),406);self.assertEqual(self.audit['native_build_source_count'],392);self.assertFalse(self.audit['new_sdk_model_execution'])
    def test_normal_three_observations_agree(self):self.assertTrue(self.rows['normal']['observations_agree']);self.assertTrue(self.rows['normal']['accepted_model_evidence'])
    def test_three_legacy_false_freshness_counterexamples(self):
        for n in ('marker-partial-before-journal','marker-unlink-before-journal','source-rename-before-journal'):self.assertTrue(self.audit['matrix'][n]['result']['first_capture']['analysis']['journal_committed']);self.assertFalse(self.rows[n]['accepted_model_evidence'])
    def test_late_marker_and_journal_changes_rejected(self):
        for n in ('marker-change-after-first','marker-symlink-after-first','journal-modify-after-first','journal-rename-after-first'):self.assertFalse(self.rows[n]['recheck_matches_first']);self.assertFalse(self.rows[n]['accepted_model_evidence'])
    def test_second_to_third_observation_changes_rejected(self):
        for n in ('marker-change-after-recheck','journal-change-after-recheck'):self.assertTrue(self.rows[n]['recheck_matches_first']);self.assertFalse(self.rows[n]['final_matches_first'])
    def test_restored_bytes_do_not_restore_metadata_identity(self):
        for n in ('marker-restore-after-first','marker-recreate-after-first'):self.assertFalse(self.audit['matrix'][n]['marker_bytes_differ_after_capture']);self.assertFalse(self.rows[n]['observations_agree'])
    def test_empty_directory_is_part_of_comparison(self):self.assertFalse(self.rows['new-empty-directory-after-first']['observations_agree'])
    def test_blocked_path_reobservation_retained(self):self.assertEqual(a.f.load(self.root/'models/source-rename-before-journal/recheck.json')['status'],'blocked');self.assertFalse(self.rows['source-rename-before-journal']['accepted_model_evidence'])
    def test_incomplete_first_capture_never_promoted(self):self.assertTrue(self.rows['first-incomplete']['observations_agree']);self.assertFalse(self.rows['first-incomplete']['accepted_model_evidence'])
    def test_final_observation_residual_window_is_explicit(self):self.assertTrue(self.rows['after-final-observation']['observations_agree']);self.assertTrue(self.audit['matrix']['after-final-observation']['marker_bytes_differ_after_capture']);self.assertFalse(self.rows['after-final-observation']['source_unchanged_through_commit_proven']);self.assertFalse(self.rows['after-final-observation']['post_final_changes_excluded'])
    def test_no_model_claims_an_atomic_snapshot(self):self.assertTrue(all(r['atomic_snapshot_verified'] is False for r in self.rows.values()))
    def test_only_two_observation_sets_accepted(self):self.assertEqual({n for n,r in self.rows.items() if r['accepted_model_evidence']},{'normal','after-final-observation'})
    def test_fifteen_retries_keep_originals(self):self.assertEqual(len(self.audit['retained_attempts']),15);self.assertTrue(all(v['retry_refused'] and v['physical_originals_unchanged'] for v in self.audit['retained_attempts'].values()))
    def test_static_and_unknown_observation_modes(self):self.assertFalse(self.audit['lifecycle']['static_exit_claimed']);self.assertTrue(self.audit['lifecycle']['unknown_refused'])
    def test_seven_negative_archives(self):self.assertEqual(len(self.audit['negative_archives']),7);self.assertEqual(self.audit['negative_archives']['forged-late-success'],'saved window analysis differs')
    def test_no_hardware_or_formal_namespace(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations'):self.assertEqual(self.audit[k],0)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
if __name__=='__main__':unittest.main()
