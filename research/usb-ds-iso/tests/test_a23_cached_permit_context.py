from pathlib import Path
from unittest.mock import patch
import os
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_cached_permit_context as audit

class CachedPermitContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_PERMIT_CONTEXT_REVIEW'):cls.root=Path(os.environ['A23_PERMIT_CONTEXT_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-permit-context-tests-',dir='/private/tmp')
            cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        audit.a.sealed(cls.root);cls.results=audit.f.load(cls.root/'results.json')
        cls.builds,cls.journal,cls.roots=audit.factory.load_bundle(cls.root/'bundle')
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.results['cases'][name]['result']
    def test_normal_simulated_chain(self):
        row=self.row('normal');self.assertEqual(row['errors'],[])
        for key in ('session_subset_consistent','shared_model_records_consistent','native_claim_links_consistent','supervision_context_links_consistent'):
            self.assertTrue(row[key])
        self.assertEqual(row['model_sequences_declared'],32)
    def test_actual_context_is_not_accepted_as_injected_policy(self):
        row=self.row('normal')['context_observation']
        self.assertFalse(row['actual_context_policy_accepted']);self.assertTrue(row['injected_policy_declared'])
        self.assertEqual((row['actual_sandbox_query_result'],row['supplied_execution_sandbox_query_result']),(1,0))
    def test_shared_authorization_reservation_and_durable_markers(self):
        for case,expected in audit.CASES.items():
            if expected==['shared_records']:self.assertEqual(self.row(case)['errors'],expected)
    def test_native_context_pid_and_sandbox_types(self):
        for case in ('context-pid-bool','context-sandbox'):
            self.assertEqual(self.row(case)['errors'],['native_claims'])
    def test_context_legacy_slash_encoding_preserves_original_hashes(self):
        raw={n:self.journal[0].read(n) for n in self.journal[0].files}
        host=audit.model.HOST+'context.json'
        job=audit.f.parse(raw[audit.model.INPUTS+'case-info.json'])['job_id']
        native=audit.model.INPUTS+'namespace/jobs/'+job+'/native-context.json'
        self.assertEqual(audit.model.obj(raw,host),audit.model.obj(raw,native))
        self.assertNotEqual(audit.f.sha(raw[host]),audit.f.sha(raw[native]))
        changed=dict(raw);changed[host]=b' '+raw[host]
        with self.assertRaises(ValueError):audit.model.obj(changed,host)
    def test_native_process_selection_and_result_links(self):
        for case in ('native-receipt','native-speed-bool','native-marker','native-stale','native-hardware-count','native-identity'):
            self.assertEqual(self.row(case)['errors'],['native_claims'])
    def test_entry_consumption_digest_and_pid_are_joined(self):
        for case in ('entry-receipt','entry-pid'):
            self.assertTrue(self.row(case)['session_subset_consistent']);self.assertEqual(self.row(case)['errors'],['native_claims'])
    def test_internally_consistent_pid_splice_is_rejected_by_outer_context(self):
        row=self.row('coherent-pid-splice');self.assertTrue(row['native_claim_links_consistent'])
        self.assertEqual(row['errors'],['supervision_context'])
    def test_injection_changes_only_three_sandbox_fields(self):
        for case in ('injection-declaration','extra-context-substitution'):
            self.assertTrue(self.row(case)['native_claim_links_consistent']);self.assertEqual(self.row(case)['errors'],['supervision_context'])
    def test_supervision_owner_nonce_job_and_pid_links(self):
        for case in ('control-nonce','supervised-pid','actual-context-copy','supervision-owner','control-job','envelope-pid'):
            self.assertEqual(self.row(case)['errors'],['supervision_context'])
    def test_supervisor_saved_policy_and_deadline_records(self):
        for case in ('saved-policy','hello-budget','late-hello'):
            self.assertEqual(self.row(case)['errors'],['supervision_context'])
    def test_independent_clock_values_do_not_grant_timing_authority(self):
        for case in ('owner-clock-shift','hello-observation-shift'):
            self.assertEqual(self.row(case)['errors'],[])
            self.assertFalse(self.row(case)['callback_deadlines_verified'])
    def test_prior_session_failure_cannot_be_promoted(self):
        self.assertEqual(self.row('session-receipt')['errors'],['session_subset'])
    def test_rehashed_case_scope_and_no_live_authority(self):
        for case,expected in audit.CASES.items():
            self.assertEqual(self.row(case)['errors'],expected)
            self.assertIs(self.results['cases'][case]['constructed_model'],case!='normal')
            for key in audit.model.FALSE:self.assertIs(self.row(case)[key],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_consumer_file_opens_and_external_pin(self):
        r=self.builds['receiver'];s=self.builds['supervisor'];j=self.journal
        links=audit.factory.link_bytes(r,s,j,self.roots)
        with patch('builtins.open',side_effect=AssertionError('open')),patch('os.open',side_effect=AssertionError('os.open')):
            row=audit.model.consume(r,s,j,links,audit.f.sha(links))
        self.assertEqual(row['errors'],[])
        with self.assertRaisesRegex(ValueError,'external link pin'):audit.model.consume(r,s,j,links,'0'*64)
    def test_source428_and_external_review_anchor(self):
        row=audit.f.load(self.root/'audit.json')
        self.assertEqual((row['source_count'],row['prior_sources_unchanged']),(428,425))
        self.assertEqual(row['consumer_filesystem_opens'],0)
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.replay(self.root,'0'*64)

if __name__=='__main__':unittest.main()
