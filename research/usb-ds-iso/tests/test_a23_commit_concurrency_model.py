from pathlib import Path
import copy,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_commit_concurrency_model as audit


class CommitConcurrencyModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_COMMIT_CONCURRENCY_REVIEW'):cls.root=Path(os.environ['A23_COMMIT_CONCURRENCY_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-commit-concurrency-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin);cls.native=audit.f.load(cls.root/'work/stdout-optimized.json')
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.report['semantic'][name]
    def material(self,name):return copy.deepcopy(self.native['cases'][name]),audit.cache(self.root/'work/models-optimized'/name)
    def test_commit_thread_publishers_are_busy_and_cannot_change_profile(self):
        for name in ('gate-publish','gate-aba','gate-noop'):
            row=self.row(name);self.assertTrue(row['complete']);self.assertEqual(row['version']['write_successes'],0);self.assertEqual(row['version']['current_generation'],4)
    def test_two_publishers_are_ready_before_release_and_both_busy(self):
        trace=self.row('gate-two-publishers')['concurrency'];self.assertEqual(trace['worker_count'],2);self.assertEqual(trace['ready_count'],2)
        for worker in trace['workers']:self.assertEqual(worker['statuses'],[3]);self.assertEqual(worker['before_generation'],3);self.assertEqual(worker['after_generation'],3)
    def test_iso_callback_before_and_after_write_revokes_completion(self):
        for name,actions in (('gate-iso-before-write',['iso','publish']),('gate-write-before-iso',['publish','iso'])):
            row=self.row(name);self.assertFalse(row['complete']);self.assertEqual(row['concurrency']['workers'][0]['actions'],actions);self.assertEqual(row['facts']['owners'][0]['callbacks'],2)
    def test_control_callback_before_and_after_write_revokes_completion(self):
        for name,actions in (('gate-control-before-write',['control','publish']),('gate-write-before-control',['publish','control'])):
            row=self.row(name);self.assertFalse(row['complete']);self.assertEqual(row['concurrency']['workers'][0]['actions'],actions)
    def test_callback_schedules_release_original_ticket(self):
        for name in audit.model.CASES:
            if name.startswith('gate-'):self.assertEqual(self.row(name)['version']['released_generation'],4)
    def test_journal_failure_after_concurrent_attempt_remains_terminal(self):
        row=self.row('gate-journal-failure');self.assertFalse(row['complete']);self.assertNotIn('observation_complete',row['events']);self.assertEqual(row['version']['busy_writes'],1)
    def test_aba_worker_after_capture_return_prevents_commit(self):
        row=self.row('capture-return-aba');self.assertFalse(row['complete']);self.assertNotIn('observation_complete',row['events']);self.assertEqual(row['version']['current_generation'],8);self.assertEqual(row['concurrency']['workers'][0]['after_generation'],6)
    def test_after_release_aba_creates_failure_receipt(self):
        row=self.row('after-release-aba');self.assertFalse(row['complete']);self.assertTrue(row['receipt']['saved']);self.assertFalse(row['receipt']['stale'])
    def test_after_receipt_aba_and_noop_revoke_saved_receipt(self):
        for name in ('after-receipt-aba','after-receipt-noop'):
            row=self.row(name);self.assertFalse(row['complete']);self.assertFalse(row['receipt']['saved']);self.assertTrue(row['receipt']['stale'])
    def test_all_72_diagnostic_rows_checked_without_claiming_provenance(self):
        self.assertEqual(len(self.report['semantic']),72);self.assertEqual(sum(self.row(n)['diagnostics']['workers'] for n in audit.model.CASES),14)
        for row in self.report['semantic'].values():self.assertTrue(row['diagnostics']['passed']);self.assertFalse(row['diagnostics']['provenance_authenticated'])
    def test_pure_consumer_does_not_open_files(self):
        row,cache=self.material('gate-publish')
        with patch('builtins.open',side_effect=AssertionError('consumer opened file')) as a,patch('io.open',side_effect=AssertionError('consumer opened path')) as b:
            audit.diagnostics.validate('gate-publish',row,cache);self.assertEqual(a.call_count+b.call_count,0)
    def test_every_version_field_forgery_is_rejected_after_export_is_updated(self):
        row,cache=self.material('normal')
        for key,value in row['version'].items():
            forged=copy.deepcopy(row);changed=dict(cache);forged['version'][key]=not value if type(value) is bool else value+1 if type(value) is int else value+'!';changed['version-profile.json']=audit.diagnostics.encode(forged['version'])
            with self.assertRaises(ValueError):audit.diagnostics.validate('normal',forged,changed)
    def test_every_fact_field_forgery_is_rejected_after_export_is_updated(self):
        row,cache=self.material('normal')
        for key,value in row['facts'].items():
            forged=copy.deepcopy(row);changed=dict(cache)
            if key=='owners':forged['facts'][key][0]['retained']=True
            else:forged['facts'][key]=not value if type(value) is bool else value+1 if type(value) is int else value+'!'
            changed['fault-facts.json']=audit.diagnostics.encode(forged['facts'])
            with self.assertRaises(ValueError):audit.diagnostics.validate('normal',forged,changed)
    def test_each_owner_diagnostic_field_is_linked_to_lease_and_saved_epochs(self):
        row,cache=self.material('normal')
        for key,value in row['facts']['owners'][0].items():
            forged=copy.deepcopy(row);changed=dict(cache);forged['facts']['owners'][0][key]=not value if type(value) is bool else value+1;changed['fault-facts.json']=audit.diagnostics.encode(forged['facts'])
            with self.assertRaises(ValueError):audit.diagnostics.validate('normal',forged,changed)
    def test_trace_mutation_cannot_hide_accepted_write_under_commit(self):
        row,cache=self.material('gate-publish');row['concurrency']['workers'][0]['statuses']=[0];cache['concurrency.json']=audit.diagnostics.encode(row['concurrency'])
        with self.assertRaisesRegex(ValueError,'concurrency trace'):audit.diagnostics.validate('gate-publish',row,cache)
    def test_recomputed_receipt_hashes_cannot_replace_stale_snapshot_with_current_state(self):
        row,cache=self.material('after-receipt-aba');d=audit.diagnostics
        cache['sdk-receipt/snapshot.json']=d.encode(row['result']);receipt=d.parse(cache['sdk-receipt/receipt.json']);receipt['snapshot']=row['result'];receipt['snapshot_sha256']=d.sha(cache['sdk-receipt/snapshot.json']);cache['sdk-receipt/receipt.json']=d.encode(receipt)
        names=('receipt.json','snapshot.json');sums=''.join(d.sha(cache['sdk-receipt/'+n])+'  '+n+'\n' for n in names).encode();cache['sdk-receipt/SHA256SUMS']=sums;cache['sdk-receipt/COMMITTED']=(d.sha(sums)+'\n').encode()
        with self.assertRaisesRegex(ValueError,'snapshot relation'):d.validate('after-receipt-aba',row,cache)
    def test_old_behavior_and_bypass_negative_control_remain(self):
        self.assertFalse(self.row('profile-start-aba')['complete']);self.assertTrue(self.row('profile-end-bypass')['complete']);self.assertTrue(self.row('callback-queued-delay')['complete'])
    def test_driver_bridge_and_c_sources_remain_identical(self):
        parent=self.root/'source'
        for key,value in audit.model.old_model.render(parent).items():
            if key!=audit.BASE+'tests/model_main.m':self.assertEqual(value,audit.a.read(self.root/'work/generated'/key),key)
    def test_sources479_and_frozen_thread_schedule_scope(self):
        report=audit.f.load(self.root/'audit.json');self.assertEqual((report['source_count'],report['prior_sources_unchanged']),(479,474));self.assertEqual(self.report['specified_worker_threads_per_fixture'],14)
        for flag in audit.FALSE:self.assertIs(self.report[flag],False)
    def test_external_pin_and_formal_namespace(self):
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.verify(self.root,'0'*64)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())


if __name__=='__main__':unittest.main()
