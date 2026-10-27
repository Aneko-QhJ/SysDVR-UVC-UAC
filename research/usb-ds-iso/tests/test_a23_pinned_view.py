from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_pinned_view as a
class PinnedViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_PINNED_REVIEW'):cls.root=Path(os.environ['A23_PINNED_REVIEW'])
        else:cls.tmp=tempfile.TemporaryDirectory(prefix='a23-view-tests-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';a.run(cls.root)
        a.w.card.seal_verify(cls.root);cls.audit=a.f.load(cls.root/'audit.json');cls.rows=cls.audit['matrix']
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def test_410_preserves406_without_native_execution(self):self.assertEqual(len(a.sources()),410);self.assertFalse(self.audit['native_build_used']);self.assertFalse(self.audit['new_sdk_model_execution'])
    def test_six_files_match_frozen_origin_manifest(self):self.assertEqual(len(a.source_proof(self.root/'bundle')['files']),6)
    def test_normal_detached_and_verified(self):self.assertTrue(self.rows['normal']['published']);self.assertTrue(self.rows['normal']['storage_valid_at_observation']);self.assertFalse(self.rows['normal']['source_and_view_inode_shared'])
    def test_input_hardlinks_rejected_before_commit(self):
        for n in ('source-hardlink','internal-hardlink','during-read-hardlink'):self.assertFalse(self.rows[n]['published']);self.assertFalse((self.root/'models'/n/'view/COMMITTED').exists())
    def test_source_changes_after_capture_do_not_change_contract_bytes(self):
        for n in ('source-write-after-snapshot','source-write-after-publish','source-rename-after-snapshot'):self.assertTrue(self.rows[n]['storage_valid_at_observation']);self.assertTrue(self.rows[n]['cached_bytes_match'])
    def test_output_alias_or_write_before_commit_rejected(self):
        for n in ('output-hardlink-before-commit','output-write-before-commit'):self.assertFalse(self.rows[n]['published']);self.assertFalse((self.root/'models'/n/'view/COMMITTED').exists())
    def test_cached_bytes_survive_later_storage_mutations(self):
        for n in ('cache-then-rewrite-disk','cache-then-hardlink-write','cache-then-replace-path'):self.assertTrue(self.rows[n]['cached_bytes_match']);self.assertFalse(self.rows[n]['storage_valid_at_observation'])
    def test_alias_write_is_recorded(self):self.assertEqual(self.rows['cache-then-hardlink-write']['observed_data_nlink'],2)
    def test_no_successful_view_keeps_source_inode(self):self.assertTrue(all(not r['source_and_view_inode_shared'] for r in self.rows.values()))
    def test_missing_symlink_fifo_and_wrong_contract_refused(self):
        for n in ('missing-source-file','source-symlink','source-fifo','wrong-contract'):self.assertFalse(self.rows[n]['published'])
    def test_three_actual_publication_exit_points(self):self.assertEqual(set(self.audit['interrupted_publications']),{'reserved','copied','before_commit'});self.assertTrue(all(r['returncode']==75 and not r['committed'] and r['retry_refused'] for r in self.audit['interrupted_publications'].values()))
    def test_two_process_race_one_winner(self):self.assertEqual(sorted(self.audit['race_exitcodes']),[0,2])
    def test_all_outputs_refuse_overwrite(self):self.assertTrue(all(r['retry_refused'] for r in self.rows.values()))
    def test_seven_negative_views_rejected(self):self.assertEqual(len(self.audit['negative_archives']),7)
    def test_never_claims_live_authentication_or_os_immutability(self):self.assertTrue(all(r['live_source_authenticated'] is False and r['os_immutability_enforced'] is False and r['atomic_snapshot_verified'] is False for r in self.rows.values()))
    def test_no_hardware_or_formal_namespace(self):
        for n in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations'):self.assertEqual(self.audit[n],0)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
if __name__=='__main__':unittest.main()
