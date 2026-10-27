from pathlib import Path
from unittest.mock import patch
import os
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_cached_session_links as audit


class CachedSessionLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_SESSION_LINK_REVIEW'):cls.root=Path(os.environ['A23_SESSION_LINK_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-session-link-tests-',dir='/private/tmp')
            cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        audit.a.sealed(cls.root);cls.results=audit.f.load(cls.root/'results.json')
        cls.builds,cls.journal,cls.roots=audit.previous.load_bundle(cls.root/'bundle')

    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()

    def row(self,name):return self.results['cases'][name]['result']
    def test_normal_entry_to_epoch_links(self):
        row=self.row('normal');self.assertEqual(row['errors'],[])
        for key in ('build_subset_consistent','driver_receipt_links_consistent','session_journal_links_consistent','entry_to_epoch_session_links_consistent'):
            self.assertTrue(row[key])

    def test_driver_checkpoint_and_receipt_copies_refused(self):
        for case in ('driver-copy','snapshot-hash','embedded-snapshot','driver-session'):
            self.assertEqual(self.row(case)['errors'],['driver_receipt'])

    def test_stale_receipts_and_entry_checkpoint_refused(self):
        for case in ('receipt-stale','entry-final-stale'):
            self.assertEqual(self.row(case)['errors'],['driver_receipt'])

    def test_bool_counts_and_numeric_complete_refused(self):
        for case in ('driver-count-bool','lease-callback-bool','entry-complete-int'):
            self.assertEqual(self.row(case)['errors'],['driver_receipt'])

    def test_event_types_duplicates_and_partial_journal_refused(self):
        for case in ('journal-index-bool','journal-tick-bool','journal-duplicate','journal-partial','entry-event'):
            self.assertEqual(self.row(case)['errors'],['session_journals'])

    def test_session_identity_and_claim_splicing_refused(self):
        for case in ('event-session','receipt-binding','claim-binding','identity-bool','context-hash'):
            self.assertEqual(self.row(case)['errors'],['session_journals'])

    def test_epoch_bindings_samples_budgets_and_byte_links_refused(self):
        for case in ('epoch-session','sample-link','budget-link','saved-hash'):
            self.assertEqual(self.row(case)['errors'],['epoch_links'])
            self.assertTrue(self.row(case)['build_subset_consistent'])

    def test_callback_declarations_and_quiet_record_link_refused(self):
        for case in ('owner-count','control-bytes','quiet-record'):
            self.assertEqual(self.row(case)['errors'],['epoch_links'])

    def test_callback_order_is_not_fixed_to_one_delivery_order(self):
        self.assertEqual(self.row('callback-order')['errors'],[])

    def test_owner_clock_is_distinct_and_not_authenticated(self):
        normal=self.row('normal');shifted=self.row('owner-clock-shift')
        self.assertEqual(shifted['errors'],[])
        self.assertEqual(len(normal['clock_observations']),2)
        for before,after in zip(normal['clock_observations'],shifted['clock_observations']):
            self.assertGreater(before['owner_arrival_ticks'],before['journal_ticks'])
            self.assertNotEqual(before['owner_arrival_ticks'],before['driver_arrival_ticks'])
            self.assertEqual(after['owner_arrival_ticks']-before['owner_arrival_ticks'],1000000)
        self.assertFalse(normal['owner_driver_clock_domain_relation_verified'])

    def test_rehashed_cases_have_expected_semantic_results(self):
        self.assertEqual(set(self.results['cases']),set(audit.CASES))
        for case,expected in audit.CASES.items():
            self.assertEqual(self.row(case)['errors'],expected)
            self.assertIs(self.results['cases'][case]['constructed_model'],case!='normal')

    def test_build_failure_cannot_be_promoted(self):
        self.assertEqual(self.row('build-reference')['errors'],['build_subset'])
        self.assertFalse(self.row('build-reference')['entry_to_epoch_session_links_consistent'])

    def test_pure_consumer_never_opens_material_paths(self):
        r=self.builds['receiver'];s=self.builds['supervisor'];j=self.journal
        links=audit.previous.link_bytes(r,s,j,self.roots)
        with patch('builtins.open',side_effect=AssertionError('open')),patch('os.open',side_effect=AssertionError('os.open')):
            row=audit.model.consume(r,s,j,links,audit.f.sha(links))
        self.assertEqual(row['errors'],[])
        with self.assertRaisesRegex(ValueError,'external link pin'):
            audit.model.consume(r,s,j,links,'0'*64)

    def test_no_full_sdk_timing_or_native_permit_claims(self):
        for case in audit.CASES:
            for key in audit.model.FALSE:self.assertIs(self.row(case)[key],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())

    def test_source425_and_external_review_anchor(self):
        row=audit.f.load(self.root/'audit.json')
        self.assertEqual((row['source_count'],row['prior_sources_unchanged']),(425,422))
        self.assertEqual(row['consumer_filesystem_opens'],0)
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.replay(self.root,'0'*64)

if __name__=='__main__':unittest.main()
