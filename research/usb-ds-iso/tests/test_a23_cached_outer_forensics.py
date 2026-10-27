from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_cached_outer_forensics as audit


class CachedOuterForensicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_OUTER_FORENSICS_REVIEW'):cls.root=Path(os.environ['A23_OUTER_FORENSICS_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-outer-forensics-tests-',dir='/private/tmp')
            cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        audit.a.sealed(cls.root);cls.results=audit.f.load(cls.root/'results.json')
        cls.builds,cls.journal,cls.roots,cls.outer=audit.load_bundle(cls.root/'bundle')
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.results['cases'][name]['result']
    def test_normal_exact96_member_coverage(self):
        row=self.row('normal');self.assertEqual(row['errors'],[])
        self.assertTrue(row['complete_manifest_byte_coverage'])
        self.assertEqual(row['observations']['byte_scope'],dict(raw_files=92,outer_files=4,manifest_members=96))
    def test_extra_or_missing_manifest_member_is_rejected(self):
        for case in ('scope-extra-manifest','scope-missing-manifest'):
            self.assertEqual(self.row(case)['errors'],['outer_scope'])
            self.assertFalse(self.row(case)['complete_manifest_byte_coverage'])
    def test_outer_cache_pin_commit_and_members_are_bound(self):
        for case in ('scope-cache-pin','scope-commit','scope-missing-file','scope-extra-file','scope-job-copy'):
            self.assertEqual(self.row(case)['errors'],['outer_scope'])
    def test_outer_attempt_authority_and_byte_limit(self):
        for case in ('scope-attempt','scope-authority','scope-size'):self.assertEqual(self.row(case)['errors'],['outer_scope'])
    def test_capture_shape_references_duplicate_fields_and_authority(self):
        for case in audit.CASES:
            if case.startswith('capture-'):self.assertEqual(self.row(case)['errors'],['capture_shape'])
    def test_capture_inventory_types_hashes_and_coverage(self):
        for case in ('inventory-hash','inventory-size-bool','inventory-omission'):
            self.assertEqual(self.row(case)['errors'],['capture_inventory'])
    def test_historical_scratch_and_detached_empty_are_distinct(self):
        row=self.row('normal')['observations']['capture_inventory']
        self.assertEqual(row['historical_empty_directories'],[audit.model.SCRATCH])
        self.assertEqual(row['detached_only_directories'],['empty'])
        for case in ('directories-duplicate','directories-cache-empty','directories-traversal'):
            self.assertEqual(self.row(case)['errors'],['capture_inventory'])
    def test_stat_tuples_reject_types_modes_size_and_aliases(self):
        for case in ('stat-bool','stat-short','stat-mode','stat-marker-size','stat-alias','stat-time-bool'):
            self.assertEqual(self.row(case)['errors'],['capture_identities'])
    def test_unstable_or_skipped_capture_cannot_claim_success(self):
        for case in ('stat-unstable','stat-skipped'):self.assertEqual(self.row(case)['errors'],['capture_identities'])
    def test_shifted_stat_inodes_are_only_self_consistent_declarations(self):
        row=self.row('stat-inodes-shift');self.assertEqual(row['errors'],[])
        self.assertFalse(row['historical_stat_identity_authenticated'])
        self.assertEqual(row['observations']['capture_identities']['live_stat_queries'],0)
        self.assertFalse(row['observations']['capture_identities']['stat_times_compared_to_driver'])
    def test_collector_pid_is_separate_from_supervised_model_child(self):
        a=self.row('normal')['observations']['worker_observation']
        b=self.row('worker-pid-shift')['observations']['worker_observation']
        self.assertNotEqual(a['declared_worker_pid'],a['model_child_pid'])
        self.assertEqual(b['model_child_pid'],a['model_child_pid'])
        self.assertEqual(b['declared_worker_pid']-a['declared_worker_pid'],100)
        self.assertFalse(self.row('worker-pid-shift')['bootstrap_worker_exit_authenticated'])
    def test_static_bootstrap_does_not_claim_worker_exit(self):
        row=self.row('static-bootstrap');self.assertEqual(row['errors'],[])
        observed=row['observations']['worker_observation']
        self.assertFalse(observed['worker_exit_declared']);self.assertIsNone(observed['declared_worker_pid'])
        self.assertEqual(self.row('worker-static-exit')['errors'],['worker_observation'])
    def test_worker_success_profile_requires_zero_typed_returncode(self):
        self.assertEqual(self.row('worker-nonzero')['errors'],['worker_observation'])
        # The old schema's signed-exit range alone admits 7. That does not
        # establish a successfully completed bootstrap worker.
        self.assertTrue(-255<=7<=255)
        for case in ('worker-job-pin','worker-pid-bool','worker-exit-bool','worker-mode','worker-pid-zero'):
            self.assertEqual(self.row(case)['errors'],['worker_observation'])
    def test_saved_summary_matches_journal_but_remains_a_claim(self):
        for case in audit.CASES:
            if case.startswith('summary-'):self.assertEqual(self.row(case)['errors'],['saved_summary'])
        row=self.row('normal');self.assertTrue(row['observations']['saved_summary']['saved_full_chain_claim'])
        self.assertFalse(row['supplied_model_chain_complete']);self.assertFalse(row['whole_archive_runtime_semantics_verified'])
    def test_semantic_counterexamples_have_valid_byte_coverage_and_lower_subsets(self):
        for case,expected in audit.CASES.items():
            row=self.row(case);self.assertEqual(row['errors'],expected)
            if expected not in (['outer_scope'],['prior_subset']):
                self.assertTrue(row['complete_manifest_byte_coverage']);self.assertTrue(row['prior_subsets_consistent'])
            for flag in audit.model.FALSE:self.assertIs(row[flag],False)
    def test_consumer_performs_no_file_opens(self):
        r=self.builds['receiver'];s=self.builds['supervisor'];j=self.journal
        links=audit.factory.link_bytes(r,s,j,self.roots)
        profile=audit.f.encode(audit.model.collection.clock.profile(r,j))
        with patch('builtins.open',side_effect=AssertionError('open')),patch('os.open',side_effect=AssertionError('os.open')):
            row=audit.model.consume(r,s,j,links,audit.f.sha(links),profile,audit.f.sha(profile),self.outer)
        self.assertEqual(row['errors'],[])
    def test_input_cache_rejects_mutable_bytes_and_wrong_contract(self):
        m=audit.model;cache,c,commit=self.outer
        changed={n:cache.read(n) for n in cache.files};changed['FORENSIC_ATTEMPT']=bytearray(changed['FORENSIC_ATTEMPT'])
        bad=m.view.PinnedBytes(MappingProxyType(changed),cache.contract_sha256)
        with self.assertRaisesRegex(ValueError,'byte budget'):m.outer_scope((bad,c,commit),self.journal)
        c=audit.f.parse(audit.f.encode(c));c['raw_contract_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'outer contract'):m.outer_scope((cache,c,commit),self.journal)
    def test_source437_pin_and_production_boundary(self):
        row=audit.f.load(self.root/'audit.json')
        self.assertEqual((row['source_count'],row['prior_sources_unchanged']),(437,434))
        self.assertEqual(row['consumer_filesystem_opens'],0)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.replay(self.root,'0'*64)


if __name__=='__main__':unittest.main()
