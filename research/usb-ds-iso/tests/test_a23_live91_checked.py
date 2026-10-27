import os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_live91_checked as a


class Live91Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['A23_LIVE91_CHECKED_REVIEW']);cls.r=a.verify(cls.root);cls.m=cls.r['matrix']
    def test_current91_full611_and_spent_intervals_bound(self):
        self.assertTrue(self.r['current91_bound']);self.assertEqual(self.r['source_count'],611)
        self.assertEqual([(r['first'],r['last']) for r in self.r['history']],[(49,64),(65,80),(81,96),(97,112),(113,128),(129,144)])
    def test_both_models_strict_payload_status_and_acceptance(self):
        for n,result in self.r['accepted'].items():
            self.assertEqual(result['sdk']['total_bytes'],6144);self.assertEqual(result['sdk']['epochs'][0]['first_sequence'],145)
            self.assertTrue(result['sdk']['status_captures_verified']);self.assertTrue(result['checked_export']['supplied_export_chain_complete'])
            self.assertFalse(result['checked_export']['candidate_binding']['model_only'])
    def test_fake_clock_cannot_pass_real_clock_consumer(self):
        self.assertEqual(self.r['clock_domain_rejections'],dict(normal=True,**{'queued-delay':True}))
    def test_spent113_missing_extra_drift_block_first_iso(self):
        for n in ('spent113-drift','spent113-extra','spent113-missing'):self.assertEqual(self.m[n]['calls']['iso_submissions'],0)
    def test_new_sources_baseline_and_recovery_block_first_iso(self):
        for n in ('source611-pre','baseline91-pre','new-recovery'):self.assertEqual(self.m[n]['calls']['iso_submissions'],0)
        self.assertEqual(self.m['between-source611']['calls']['iso_submissions'],1)
    def test_bad_archives_cannot_open_sdk(self):
        for n in a.ARCHIVES:self.assertFalse(self.m[n]['initial_core']);self.assertEqual(self.m[n]['calls']['opens'],0)
    def test_pending_and_bad_status_stop_after_first(self):
        for n in ('bad-status','exit-running'):self.assertEqual(self.m[n]['calls']['iso_submissions'],1)
        self.assertTrue(self.m['exit-running']['pending_full_checks_skipped'])
        files=a.w.card.seal_verify(self.root/'cases/bad-status/host/status-after-epoch-0')
        self.assertEqual(len(files['raw.bin']),168);self.assertIn('transferred',a.json.loads(files['verdict.json'])['failed_checks'])
    def test_export_and_unchanged_getters_cannot_promote_failure(self):
        for n in ('stale-getters','after-payload-bytes','acceptance-collision'):self.assertFalse(self.m[n]['loop']['success'])
        self.assertTrue(self.m['stale-getters']['stale_getter_seen'])
    def test_consumption_replay_and_old_scope_range_rejected(self):
        self.assertEqual(len(self.r['replay_rejections']),4);self.assertTrue(all(self.r['replay_rejections'].values()))
        engine=a.flow.engine_module(self.root/'build')
        for first,last,schema in ((113,144,a.builder.base.SCOPE_SCHEMA),(145,176,a.builder.base.SCOPE_SCHEMA),(129,160,a.builder.SCOPE_SCHEMA)):
            wrong=dict(self.r['scope'],first_sequence=first,last_sequence=last,schema=schema)
            with self.assertRaises(ValueError):engine.scope(wrong)
    def test_readonly_modes_and_no_formal_authority_used(self):
        self.assertEqual(self.r['file_modes']['current']['returncode'],0);self.assertEqual(self.r['file_modes']['missing-job']['returncode'],2)
        for k in ('formal_records','formal_reservations','actual_acquisition_invocations','usb_requests','sd_accesses','real_sdk_objects','remaining'):self.assertEqual(self.r[k],0)
        self.assertFalse(a.builder.FORMAL_ROOT.exists())
        with self.assertRaises(ValueError):a.flow.issue(self.root/'build',authorized=False)


if __name__=='__main__':unittest.main()
