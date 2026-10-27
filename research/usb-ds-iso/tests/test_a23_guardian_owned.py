from pathlib import Path
import ast,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_guardian_owned as audit
m=audit.model


class GuardianOwnedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_GUARDIAN_OWNED_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-guardian-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.args_at(self.root/'work/cases'/name,self.r['plan_pins'][name])
    def test_thirty_six_cases(self):self.assertEqual((self.r['model_cases'],len(self.r['semantic']),len(self.r['mutations'])),(36,16,20))
    def test_only_normal_completion(self):self.assertEqual({n for n,v in self.r['semantic'].items() if v['guardian_owned_model_complete']},{'normal'})
    def test_dead_requester_before_launch_creates_no_worker(self):
        for name in m.NO_WORKER:
            args=self.args(name);self.assertFalse(args[3]['worker_seen']);self.assertFalse(args[3]['worker_waited']);self.assertFalse(self.r['semantic'][name]['guardian_worker_wait_model_valid'])
    def test_missing_owner_does_not_prevent_direct_wait(self):
        r=self.r['semantic']['worker-unrecorded'];self.assertFalse(r['owner_record_valid']);self.assertTrue(r['missing_or_partial_owner_with_wait']);self.assertTrue(r['guardian_worker_wait_model_valid'])
    def test_partial_owner_does_not_prevent_direct_wait(self):
        with self.assertRaises(ValueError):m.parse(self.args('owner-partial')[2]['guardian-owner.json'])
        self.assertTrue(self.r['semantic']['owner-partial']['missing_or_partial_owner_with_wait'])
    def test_owner_sync_then_requester_kill_still_waits_worker(self):
        args=self.args('owner-synced');self.assertEqual(args[3]['requester_returncode'],-9);self.assertTrue(args[3]['worker_waited']);self.assertTrue(self.r['semantic']['owner-synced']['owner_record_valid'])
    def test_accepted_handoff_does_not_override_requester_exit(self):
        r=self.r['semantic']['after-handoff'];self.assertTrue(r['handoff_accepted']);self.assertTrue(r['guardian_worker_wait_model_valid']);self.assertFalse(r['guardian_owned_model_complete'])
    def test_four_requester_kill_windows_have_direct_worker_wait(self):
        for name in m.CASES:
            if name.startswith('child-'):
                args=self.args(name);self.assertEqual(args[3]['requester_returncode'],-9);self.assertEqual(args[3]['worker_returncode'],86);self.assertTrue(args[3]['worker_waited'])
    def test_good_worker_report_cannot_override_outer_failure(self):
        r=self.r['semantic']['after-parent-report'];self.assertTrue(r['worker_publication_model_complete']);self.assertFalse(r['guardian_owned_model_complete']);self.assertEqual(self.args('after-parent-report')[3]['requester_returncode'],79)
    def test_wrong_job_and_nonce_handoffs_rejected(self):
        for name in ('handoff-job-mismatch','handoff-nonce-mismatch'):
            args=self.args(name);self.assertEqual(args[3]['requester_returncode'],82);self.assertEqual(args[4][-1]['reason'],'handoff_binding');self.assertFalse(self.r['semantic'][name]['handoff_accepted'])
    def test_duplicate_handoff_rejected_after_one_acceptance(self):
        args=self.args('handoff-repeat');self.assertEqual(sum(x['kind']=='accepted' for x in args[4]),1);self.assertEqual(args[4][-1]['reason'],'handoff_repeat');self.assertEqual(args[3]['requester_returncode'],82);self.assertTrue(args[3]['worker_waited'])
    def test_closed_guardian_gate_aborts_and_reaps_worker(self):
        args=self.args('guardian-gate-closed');self.assertEqual(args[3]['worker_returncode'],87);self.assertTrue(args[3]['worker_waited']);self.assertFalse((self.root/'work/cases/guardian-gate-closed/result').exists())
    def test_all_created_workers_waited_by_creator(self):
        self.assertEqual((self.r['python_fixture_requester_processes'],self.r['python_fixture_worker_processes'],self.r['guardian_requester_waits'],self.r['guardian_worker_waits']),(16,14,16,14))
        for name in m.CASES:
            o=self.args(name)[3]
            if o['worker_seen']:self.assertEqual(o['worker_creator_pid'],o['guardian_pid']);self.assertTrue(o['worker_waited'])
    def test_twenty_mutants_rejected(self):
        for r in self.r['mutations'].values():self.assertFalse(r['guardian_owned_model_complete']);self.assertTrue(r['errors'])
    def test_source532_preserves528_and_frozen_worker(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(532,528))
        self.assertEqual(self.r['code_sha256']['a23_parent_crash_worker.py'],m.sha(audit.a.read(self.root/'source'/audit.BASE/'tests/a23_parent_crash_worker.py')))
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_pure_consumer_has_no_filesystem_or_wait_api(self):
        saved=[self.args(n) for n in m.CASES]
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')),patch.object(audit.os,'waitpid',side_effect=AssertionError('wait')):
            for args in saved:self.assertEqual(m.assess(*args)['consumer_filesystem_calls'],0)
    def test_readonly_verify_never_launches(self):
        with patch.object(audit.subprocess,'Popen',side_effect=AssertionError('process')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_external_owned_plan_pin_required(self):
        args=self.args();args[1]='0'*64
        with self.assertRaisesRegex(ValueError,'external guardian owned'):m.assess(*args)
    def test_requester_source_has_no_worker_creation_wait_or_signal(self):
        tree=ast.parse(audit.a.read(self.root/'source'/audit.BASE/'tests/a23_guardian_owned_parent.py'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else None
                self.assertNotIn(name,('Popen','fork','waitpid','kill','killpg','run_path'))
    def test_all_production_authority_false_and_no_journal_pid_signals(self):
        self.assertEqual(self.r['journal_pid_signals'],0)
        for r in (*self.r['semantic'].values(),*self.r['mutations'].values()):
            for key in m.FALSE:self.assertIs(r[key],False)
    def test_historical_sdk_bytes_and_raw_sync_prefix_preserved(self):
        files=self.args()[2];actual={n.removeprefix('result/materials/'):v for n,v in files.items() if n.startswith('result/materials/')}
        self.assertEqual(actual,audit.cache(self.root/'inputs/seed'));self.assertIn('worker_binding',self.r['mutations']['trace-sync-missing']['errors'])
    def test_coherent_outer_forgery_remains_only_model_evidence(self):
        args=self.args('after-parent-report');v=m.parse(args[0]);v['scenario']='normal';args[0]=m.encode(v);args[1]=m.sha(args[0]);files=args[2]
        files['owned-plan.json']=files['crash-plan.json']=args[0];files['guardian-use.json']=m.encode(m.use_record(args[0],v));args[3]['requester_returncode']=0
        for name in ('guardian-owner.json','handoff-sent.json','parent-accept.json'):
            h=m.parse(files[name]);h['owned_plan_sha256']=args[1];files[name]=m.encode(h)
        h=m.parse(files['guardian-owner.json']);r=m.result(h,args[3]['worker_returncode']);files['parent-result.json']=m.encode(r)
        for msg in args[4]:
            msg['owned_plan_sha256']=args[1]
            if msg['kind']=='accepted':msg['handoff_sha256']=m.sha(m.encode(h))
            if msg['kind']=='reported':msg['result_sha256']=m.sha(m.encode(r))
        for msg in args[5]:msg['crash_plan_sha256']=args[1]
        checked=m.assess(*args);self.assertTrue(checked['guardian_owned_model_complete']);self.assertFalse(checked['process_origin_authenticated']);self.assertFalse(checked['orphan_reaping_verified'])


if __name__=='__main__':unittest.main()
