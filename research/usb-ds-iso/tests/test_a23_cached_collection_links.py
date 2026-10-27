from pathlib import Path
from unittest.mock import patch
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_cached_collection_links as audit


class CachedCollectionLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_COLLECTION_LINKS_REVIEW'):cls.root=Path(os.environ['A23_COLLECTION_LINKS_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-collection-links-tests-',dir='/private/tmp')
            cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        audit.a.sealed(cls.root);cls.results=audit.f.load(cls.root/'results.json')
        cls.builds,cls.journal,cls.roots=audit.factory.load_bundle(cls.root/'bundle')
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.results['cases'][name]['result']
    def test_normal_historical_admission_matches_frozen392(self):
        row=self.row('normal');self.assertEqual(row['errors'],[])
        self.assertEqual(row['observations']['admission']['historical_source_count'],392)
        self.assertIs(row['observations']['admission']['point_in_time_only'],True)
    def test_admission_hashes_counts_and_authority_rejected(self):
        for case in ('admission-source','admission-observed','admission-count-bool','admission-current-count',
                     'admission-match','admission-point','admission-authority'):
            self.assertEqual(self.row(case)['errors'],['admission'])
    def test_expected_scope_and_admission_attempt_are_bound(self):
        for case in ('expected-scope','admission-attempt'):self.assertEqual(self.row(case)['errors'],['admission'])
    def test_verifier_schema_types_and_authority_rejected(self):
        for case in ('verifier-failed','verifier-roots','verifier-checks-bool','verifier-checks-zero','verifier-origin','verifier-extra'):
            self.assertEqual(self.row(case)['errors'],['verifier'])
    def test_verifier_count_is_a_declaration_not_authenticated_execution(self):
        before=self.row('normal');after=self.row('declared-checks-change')
        self.assertEqual(after['errors'],[])
        self.assertEqual(after['observations']['verifier']['declared_checks'],before['observations']['verifier']['declared_checks']+1)
        self.assertFalse(after['verifier_check_count_authenticated'])
        self.assertFalse(after['verifier_execution_authenticated'])
    def test_report_final_calls_and_case_match_related_records(self):
        for case in ('report-final','report-calls','report-case'):self.assertEqual(self.row(case)['errors'],['verifier'])
    def test_inventory_rejects_wrong_hash_bool_size_and_missing_member(self):
        for case in ('inventory-hash','inventory-size-bool','inventory-omission'):
            self.assertEqual(self.row(case)['errors'],['collection'])
    def test_declared_directories_have_exact_scope(self):
        for case in ('directories-duplicate','directories-omission','directories-traversal'):
            self.assertEqual(self.row(case)['errors'],['collection'])
    def test_collection_report_attempt_and_stream_copies_are_bound(self):
        for case in ('collection-report-pin','collection-attempt','stream-copy'):
            self.assertEqual(self.row(case)['errors'],['collection'])
    def test_static_collection_cannot_inherit_supervisor_exit_claim(self):
        row=self.row('normal')['observations']
        self.assertIs(row['envelope']['producer_exit_declared'],True)
        self.assertIs(row['collection']['receiver_exit_observed'],False)
        self.assertEqual(self.row('origin-promotion')['errors'],['collection'])
    def test_collection_authority_and_extra_file_rejected(self):
        for case in ('collection-authority','collection-extra'):self.assertEqual(self.row(case)['errors'],['collection'])
    def test_saved_summary_tracks_packets_bytes_quiet_and_authority(self):
        for case in ('summary-packet','summary-total','summary-quiet','summary-authority'):
            self.assertEqual(self.row(case)['errors'],['saved_summary'])
        row=self.row('normal');self.assertIs(row['observations']['saved_summary']['saved_full_chain_claim'],True)
        self.assertFalse(row['saved_full_analysis_reproduced']);self.assertFalse(row['supplied_model_chain_complete'])
    def test_coherent_changes_update_all_collection_and_summary_references(self):
        for case in ('coherent-quiet-minimum','coherent-queued-delay'):
            row=self.row(case);self.assertEqual(row['errors'],[])
            self.assertEqual(row['observations']['saved_summary']['total_effective_bytes'],6144)
    def test_envelope_declarations_and_top_coverage(self):
        for case in audit.CASES:
            if case.startswith('envelope-'):self.assertEqual(self.row(case)['errors'],['envelope'])
    def test_rehashed_counterexamples_pass_lower_subsets_and_all_verdicts_match(self):
        for case,expected in audit.CASES.items():
            row=self.row(case);self.assertEqual(row['errors'],expected)
            self.assertIs(row['prior_subsets_consistent'],case!='prior-receipt')
            for flag in audit.model.FALSE:self.assertIs(row[flag],False)
    def test_consumer_has_no_file_opens_and_pins_external_bytes(self):
        r=self.builds['receiver'];s=self.builds['supervisor'];j=self.journal
        links=audit.factory.link_bytes(r,s,j,self.roots);profile=audit.f.encode(audit.model.clock.profile(r,j))
        with patch('builtins.open',side_effect=AssertionError('open')),patch('os.open',side_effect=AssertionError('os.open')):
            row=audit.model.consume(r,s,j,links,audit.f.sha(links),profile,audit.f.sha(profile))
        self.assertEqual(row['errors'],[])
        with self.assertRaisesRegex(ValueError,'external clock profile pin'):
            audit.model.consume(r,s,j,links,audit.f.sha(links),profile,'0'*64)
    def test_source434_review_pin_and_production_boundary(self):
        row=audit.f.load(self.root/'audit.json')
        self.assertEqual((row['source_count'],row['prior_sources_unchanged']),(434,431))
        self.assertEqual(row['consumer_filesystem_opens'],0)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.replay(self.root,'0'*64)


if __name__=='__main__':unittest.main()
