from pathlib import Path
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_scope_verifier as a
class VerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_VERIFIER_REVIEW'):cls.root=Path(os.environ['A23_VERIFIER_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-verifier-tests-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';a.run(cls.root)
        a.w.card.seal_verify(cls.root);cls.audit=a.f.load(cls.root/'audit.json');cls.matrix=cls.audit['matrix']
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def test_two_complete_chains(self):self.assertEqual(set(self.audit['accepted']),{'normal','queued-delay'});self.assertEqual(len(self.audit['rejected']),26)
    def test_sources_frozen(self):self.assertEqual(len(a.builder.authority.sources()),367);self.assertEqual(self.audit['prior_sources_unchanged'],359)
    def test_current_and_archive_checks(self):
        for n in ('archive','current'):self.assertEqual(self.audit['file_modes'][n]['returncode'],0)
        self.assertTrue(self.audit['file_modes']['current']['result']['live_sources_checked'])
    def test_archive_faults_stop_before_wait(self):
        for n in a.ARCHIVE_CASES:
            r=self.matrix[n];self.assertFalse(r['initial_core']);self.assertEqual(r['calls']['wait_creates'],0);self.assertEqual(r['calls']['opens'],0)
    def test_current_source_and_recovery_changes(self):
        for n in ('live-source-afterprepare','new-recovery','baseline-drift','legacy-drift'):self.assertTrue(self.matrix[n]['verifier']['failed']);self.assertEqual(self.matrix[n]['calls']['iso_submissions'],0)
    def test_foreign_and_empty_jobs_witnessed(self):
        for n in ('foreign-job','new-empty-job','unknown-shared-file'):self.assertTrue(self.matrix[n]['verifier']['failed']);self.assertEqual(self.matrix[n]['calls']['iso_submissions'],0)
    def test_native_claim_tamper_rejects(self):self.assertTrue(self.matrix['own-native-context']['native']['permit']['stale']);self.assertEqual(self.matrix['own-native-context']['calls']['iso_submissions'],0)
    def test_observed_failure_latches_after_restore(self):self.assertTrue(self.matrix['restored-after-observed']['verifier']['failed']);self.assertFalse(self.matrix['restored-after-observed']['entry']['complete'])
    def test_no_full_hashes_pending(self):self.assertTrue(self.matrix['during-pending-source']['full_checks_skipped_while_pending']);self.assertEqual(self.matrix['during-pending-source']['calls']['iso_submissions'],1)
    def test_stopped_request_still_skips_full_hashes(self):self.assertTrue(self.matrix['stopped-pending-source']['full_checks_skipped_while_pending']);self.assertEqual(self.matrix['stopped-pending-source']['calls']['iso_submissions'],1)
    def test_resealed_source_and_header_reject(self):
        for n in ('resealed-source','resealed-header'):self.assertFalse(self.matrix[n]['initial_core'])
    def test_epoch_boundary_stops_second(self):self.assertEqual(self.matrix['between-epochs-source']['calls']['iso_submissions'],1)
    def test_final_boundary_and_postcommit_stale(self):
        self.assertFalse(self.matrix['before-final-source']['final']['saved']);self.assertTrue(self.matrix['after-final-source']['final']['stale']);self.assertFalse(self.matrix['after-final-source']['final']['saved'])
    def test_limits_and_retention(self):
        for r in self.matrix.values():self.assertLessEqual(r['calls']['iso_submissions'],2);self.assertLessEqual(r['calls']['burst_triggers'],2);self.assertLessEqual(r['calls']['aborts'],1);self.assertEqual(r['calls']['sdk_destroys'],0)
    def test_acquisition_unavailable(self):self.assertEqual(self.audit['file_modes']['acquire']['returncode'],2);self.assertFalse(self.audit['formal_issuance_available'])
    def test_individually_valid_context_mix_rejects(self):self.assertEqual(self.audit['combined_negative_archives']['context-mix'],'native/entry context differs')
    def test_individually_valid_identity_mix_rejects(self):self.assertEqual(self.audit['combined_negative_archives']['identity-mix'],'native/entry selected identity differs')
    def test_individually_valid_binding_mix_rejects(self):self.assertEqual(self.audit['combined_negative_archives']['binding-mix'],'entry/consumption binding differs')
    def test_no_hardware_or_formal_records(self):
        for k in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations'):self.assertEqual(self.audit[k],0)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
if __name__=='__main__':unittest.main()
