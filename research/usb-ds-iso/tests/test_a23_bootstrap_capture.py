from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_bootstrap_capture as a
class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_BOOTSTRAP_REVIEW'):cls.root=Path(os.environ['A23_BOOTSTRAP_REVIEW'])
        else:cls.tmp=tempfile.TemporaryDirectory(prefix='a23-bootstrap-tests-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';a.run(cls.root)
        a.w.card.seal_verify(cls.root);cls.audit=a.f.load(cls.root/'audit.json');cls.rows={n:v['result']['analysis'] for n,v in cls.audit['matrix'].items()}
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def test_source402_preserves397_and_native392(self):self.assertEqual(len(a.sources()),402);self.assertEqual(self.audit['native_build_source_count'],392);self.assertFalse(self.audit['new_sdk_model_execution'])
    def test_only_consistent_complete_bootstrap_is_complete(self):self.assertEqual({n for n,r in self.rows.items() if r['journal_committed']},{'normal'})
    def test_empty_and_partial_source_marker_bytes(self):self.assertEqual(a.a.read(self.root/'models/marker-empty/raw/source-marker'),b'');self.assertEqual(a.a.read(self.root/'models/marker-partial/raw/source-marker'),b'{')
    def test_full_marker_without_journal_is_preserved(self):self.assertTrue(self.rows['marker-full']['source_attempt_valid']);self.assertIn('journal not established',self.rows['marker-full']['errors']);self.assertFalse((self.root/'models/marker-full/raw/journal').exists())
    def test_empty_journal_directory_preserved(self):self.assertTrue((self.root/'models/journal-directory/raw/journal').is_dir());self.assertFalse((self.root/'models/journal-directory/raw/journal/attempt.json').exists())
    def test_partial_attempt_and_copy_not_repaired(self):
        for name,leaf in (('attempt-partial','attempt.json'),('copy-partial','SOURCE_ATTEMPT')):self.assertEqual(a.a.read(self.root/'models'/name/'raw/journal'/leaf),b'{');self.assertFalse(self.rows[name]['journal_committed'])
    def test_partial_event_bytes_preserved(self):self.assertEqual(a.a.read(self.root/'models/event-partial/raw/journal/events/00.json'),b'{')
    def test_actual_process_exits_at_bootstrap_points(self):
        for name in ('marker-empty','marker-partial','marker-full','journal-directory','attempt-empty','attempt-partial','attempt-full','copy-empty','copy-partial','copy-full','event-partial','event-full','hold-marker'):self.assertEqual(self.audit['matrix'][name]['exit']['returncode'],74)
    def test_float_pid_is_not_a_valid_source_attempt(self):self.assertFalse(self.rows['float-marker']['source_attempt_valid']);self.assertFalse(self.rows['float-marker']['journal_committed'])
    def test_malformed_source_marker_cannot_promote_complete_journal(self):self.assertFalse(self.rows['malformed-marker-complete']['source_attempt_valid']);self.assertFalse(self.rows['malformed-marker-complete']['journal_committed']);self.assertTrue((self.root/'models/malformed-marker-complete/raw/journal/COMMITTED').exists())
    def test_wrong_source_pid_cannot_promote_complete_journal(self):self.assertFalse(self.rows['mismatched-marker-complete']['source_attempt_valid']);self.assertFalse(self.rows['mismatched-marker-complete']['journal_committed'])
    def test_fifo_symlink_and_huge_marker_metadata_only(self):
        for name in ('marker-symlink','marker-fifo','marker-oversized'):self.assertFalse((self.root/'models'/name/'raw/source-marker').exists());self.assertFalse(self.rows[name]['capture_safe'])
    def test_blocked_journal_never_followed(self):self.assertFalse(self.rows['journal-symlink']['capture_safe']);self.assertFalse((self.root/'models/journal-symlink/raw/journal/SECRET').exists())
    def test_three_descriptor_replacement_models_refuse_completion(self):
        for name in ('source-renamed','marker-replaced','journal-renamed'):self.assertFalse(self.rows[name]['capture_stable']);self.assertFalse(self.rows[name]['journal_committed']);self.assertEqual(len(self.audit['matrix'][name]['replacement_checkpoints']),1)
    def test_pinned_marker_keeps_original_bytes(self):self.assertTrue(self.rows['marker-replaced']['source_attempt_valid']);self.assertNotEqual(a.a.read(self.root/'models/marker-replaced/raw/source-marker'),b'FORBIDDEN_OUTSIDE_BYTES\n')
    def test_unsafe_or_large_nested_files_are_skipped(self):
        for name in ('journal-unsafe-nested','journal-oversized'):self.assertFalse(self.rows[name]['capture_safe']);self.assertTrue(a.f.load(self.root/'models'/name/'capture.json')['capture']['journal']['skipped'])
    def test_all_26_retries_refused_without_original_writes(self):self.assertEqual(len(self.audit['retained_attempts']),26);self.assertTrue(all(v['retry_refused'] and v['originals_unchanged'] for v in self.audit['retained_attempts'].values()))
    def test_running_unknown_and_other_worker_refused(self):
        for key in ('running_refused','unknown_refused','other_worker_refused'):self.assertTrue(self.audit['lifecycle'][key])
    def test_static_mode_never_claims_exit(self):self.assertFalse(self.audit['lifecycle']['static_exit_claimed'])
    def test_seven_forged_archives_rejected(self):self.assertEqual(len(self.audit['negative_archives']),7);self.assertEqual(self.audit['negative_archives']['forged-early-success'],'saved bootstrap analysis differs')
    def test_no_hardware_or_formal_namespace(self):
        for key in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations'):self.assertEqual(self.audit[key],0)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
if __name__=='__main__':unittest.main()
