from pathlib import Path
import os
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import audit_a23_cached_journal_epochs as audit

class CachedJournalEpochTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = None
        if os.environ.get('A23_CACHED_EPOCH_REVIEW'):
            cls.root = Path(os.environ['A23_CACHED_EPOCH_REVIEW'])
        else:
            cls.tmp = tempfile.TemporaryDirectory(prefix='a23-cached-epoch-tests-', dir='/private/tmp')
            cls.root = Path(cls.tmp.name)/'review'; audit.run(cls.root)
        audit.a.sealed(cls.root)
        cls.report = audit.f.load(cls.root/'audit.json')
        cls.catalog = audit.f.load(cls.root/'scope-catalog.json')
    @classmethod
    def tearDownClass(cls):
        if cls.tmp: cls.tmp.cleanup()
    def result(self, case): return audit.f.load(self.root/'models'/case/'analysis.json')
    def test_source416_preserves413(self):
        self.assertEqual(len(audit.sources()),416)
        self.assertEqual(self.report['prior_sources_unchanged'],413)
    def test_exact_raw_scope_fits_without_raising_limits(self):
        self.assertEqual(self.catalog['raw_file_count'],92)
        self.assertEqual(self.catalog['raw_total_bytes'],516080)
        self.assertEqual(self.catalog['existing_limits']['files'],128)
        self.assertTrue(self.catalog['full_raw_fits_existing_view'])
    def test_external_builds_remain_outside_cached_scope(self):
        self.assertFalse(self.catalog['external_build_materials_cached'])
        for row in self.catalog['external_builds'].values():
            self.assertGreater(row['files'],128)
            self.assertFalse(row['fits_single_existing_view'])
    def test_normal_all_eight_seals_and_journal_pass(self):
        row=self.result('normal')
        self.assertTrue(row['nested_seals_verified']); self.assertTrue(row['journal_commit_verified'])
        self.assertEqual(row['errors'],[])
    def test_worker_declaration_is_byte_bound_and_type_checked(self):
        self.assertTrue(self.result('normal')['declared_worker_job_matches_attempt'])
        self.assertEqual(self.result('worker-pid-bool')['errors'],['worker_declaration'])
    def test_namespace_job_relation_checked(self):
        self.assertTrue(self.result('normal')['namespace_job_id_consistent'])
        self.assertEqual(self.result('namespace-job')['errors'],['namespace_job'])
    def test_late_journal_link_bool_index_and_copy_rejected(self):
        for case in ('late-event-link','event-bool-index','copy-mismatch'):
            self.assertEqual(self.result(case)['errors'],['journal'])
            self.assertTrue(self.result(case)['nested_seals_verified'])
    def test_two_epochs_packet_and_status_match(self):
        row=self.result('normal')
        self.assertTrue(row['epoch_packet_relations_consistent'])
        self.assertEqual(row['total_effective_bytes'],6144)
        self.assertEqual([r['first_sequence'] for r in row['epochs']],[81,97])
        self.assertTrue(all(len(r['effective_slots'])==16 for r in row['epochs']))
    def test_payload_and_transactions_rejected_after_resealing(self):
        for case in ('payload','transaction-count','transaction-offset','transaction-return'):
            self.assertEqual(self.result(case)['errors'],['epoch_packets'])
            self.assertTrue(self.result(case)['nested_seals_verified'])
    def test_status_continuity_urb_and_binding_rejected(self):
        for case in ('iso7','before-continuity','urb-reuse','binding-mismatch','bool-epoch'):
            self.assertEqual(self.result(case)['errors'],['epoch_packets'])
    def test_untransferred_padding_is_not_effective_payload(self):
        row=self.result('padding')
        self.assertEqual(row['errors'],[]); self.assertEqual(row['total_effective_bytes'],6144)
        self.assertNotEqual((self.root/'models/normal/view/data'/audit.model.HOST/'epoch-0/raw.bin').read_bytes(),
                            (self.root/'models/padding/view/data'/audit.model.HOST/'epoch-0/raw.bin').read_bytes())
    def test_missing_or_bad_commits_cannot_promote_success(self):
        self.assertEqual(self.result('missing-epoch-commit')['errors'],['nested_seals','epoch_packets'])
        self.assertEqual(self.result('journal-commit')['errors'],['nested_seals','journal'])
    def test_no_complete_chain_or_physical_claims(self):
        for case in audit.CASES:
            row=self.result(case)
            for name in audit.model.FALSE: self.assertIs(row[name],False)
        self.assertEqual(sum(not r['errors'] for r in self.report['cases'].values()),2)
    def test_cache_consumption_and_later_disk_changes(self):
        self.assertEqual(self.report['consumer_filesystem_opens'],[])
        self.assertGreater(self.report['consumer_read_calls'],1800)
        self.assertEqual(len(self.report['storage_mutations']),3)
        self.assertTrue(all(r['cached_analysis_unchanged'] and r['fresh_load_refused']
                            for r in self.report['storage_mutations'].values()))
    def test_four_scope_refusals_and_no_hardware(self):
        self.assertEqual(len(self.report['scope_rejections']),4)
        for name in ('usb_requests','sd_accesses','real_sdk_objects','formal_records','formal_reservations'):
            self.assertEqual(self.report[name],0)
        self.assertFalse(self.report['native_build_used'])
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())

if __name__=='__main__': unittest.main()
