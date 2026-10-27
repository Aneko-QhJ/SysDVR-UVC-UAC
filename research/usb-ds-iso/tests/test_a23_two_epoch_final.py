from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_two_epoch_final as a
class FinalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_FINAL_REVIEW'):cls.root=Path(os.environ['A23_FINAL_REVIEW'])
        else:cls.tmp=tempfile.TemporaryDirectory(prefix='a23-final-tests-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';a.run(cls.root)
        a.w.card.seal_verify(cls.root);cls.audit=a.f.load(cls.root/'audit.json')
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def test_sources(self):self.assertEqual(len(a.sources()),372);self.assertEqual(self.audit['prior_sources_unchanged'],367)
    def test_two_complete_26_incomplete(self):
        complete={n for n,r in self.audit['collections'].items() if r['analysis']['supplied_model_chain_complete']};self.assertEqual(complete,{'normal','queued-delay'});self.assertEqual(len(self.audit['collections']),28)
    def test_failed_bytes_and_empty_host_preserved(self):
        for name in ('binary','frozen-source'):self.assertTrue((self.root/'collections'/name/'inputs/host').is_dir());self.assertFalse(self.audit['collections'][name]['analysis']['supplied_model_chain_complete'])
    def test_uncertain_request_archived_incomplete(self):
        r=self.audit['collections']['stopped-pending-source'];self.assertTrue(r['archive_integrity_valid']);self.assertFalse(r['analysis']['callback_drain_verified']);self.assertFalse(r['analysis']['supplied_model_chain_complete'])
    def test_running_producer_refused_before_output(self):self.assertTrue(self.audit['lifecycle']['running']['rejected']);self.assertFalse(self.audit['lifecycle']['running']['output_created'])
    def test_unknown_producer_rejected(self):self.assertIn('explicit',self.audit['lifecycle']['unknown'])
    def test_failed_write_burn_preserved(self):self.assertTrue(self.audit['lifecycle']['failed-write']['attempt_retained']);self.assertFalse(self.audit['lifecycle']['failed-write']['committed'])
    def test_source_change_and_empty_directory_refuse_commit(self):
        for n in ('source-drift','new-empty-directory'):self.assertTrue(self.audit['lifecycle'][n]['attempt_retained']);self.assertFalse(self.audit['lifecycle'][n]['committed'])
    def test_mixed_chains_remain_incomplete(self):
        self.assertEqual(len(self.audit['combined_mixes']),3)
        for r in self.audit['combined_mixes'].values():self.assertFalse(r['analysis']['supplied_model_chain_complete']);self.assertFalse(r['producer_exit_reported'])
    def test_thirteen_bad_archives(self):self.assertEqual(len(self.audit['negative_archives']),13)
    def test_recomputed_seal_cannot_grant_cleanup_or_exit(self):
        self.assertEqual(self.audit['negative_archives']['bool-exit'],'model exit observation differs');self.assertEqual(self.audit['negative_archives']['claims-cleanup'],'collection authority differs')
    def test_forensic_success_does_not_authorize_next(self):
        for r in self.audit['collections'].values():
            for k in a.a.FLAGS:self.assertIs(r[k],False)
    def test_exited_failed_process_raw_preserved(self):
        r=self.audit['lifecycle']['exited-failed'];self.assertTrue(r['archive_integrity_valid']);self.assertFalse(r['analysis']['supplied_model_chain_complete']);self.assertEqual(a.a.read(self.root/'lifecycle/exited-failed/process.stdout'),b'partial bytes')
    def test_concurrent_collectors_have_one_winner(self):self.assertEqual(sorted(self.audit['lifecycle']['race_exitcodes']),[0,2])
    def test_static_exit_uses_bool_type(self):self.assertEqual(self.audit['negative_archives']['numeric-static-exit'],'static observation claims process exit')
    def test_rehashed_report_cannot_keep_success(self):self.assertEqual(self.audit['negative_archives']['rehashed-false-report'],'saved analysis differs')
    def test_real_namespace_absent(self):self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_no_hardware(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations'):self.assertEqual(self.audit[k],0)
if __name__=='__main__':unittest.main()
