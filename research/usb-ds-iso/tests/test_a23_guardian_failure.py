from pathlib import Path
import ast,copy,errno,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_guardian_failure as audit
m=audit.model


class GuardianFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_GUARDIAN_FAILURE_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-guardian-failure-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.args_at(self.root/'work/cases'/name,self.r['plan_pins'][name])
    def test_thirty_three_cases(self):self.assertEqual((self.r['model_cases'],len(self.r['semantic']),len(self.r['mutations'])),(33,13,20))
    def test_only_normal_completion(self):self.assertEqual({n for n,v in self.r['semantic'].items() if v['guardian_failure_model_complete']},{'normal'})
    def test_witness_waits_only_its_direct_guardians(self):
        self.assertEqual((self.r['witness_guardian_waits'],self.r['witness_actor_waits']),(13,0))
        for name in m.CASES:self.assertIs(self.args(name)[3]['guardian_waited'],True);self.assertEqual(self.args(name)[3]['guardian_returncode'],0 if name=='normal' else -9)
    def test_before_requester_has_no_actor(self):self.assertEqual(self.args('before-requester')[5],[]);self.assertEqual(self.r['semantic']['before-requester']['actor_exit_notes_valid'],0)
    def test_after_requester_has_no_worker(self):self.assertEqual([n['role'] for n in self.args('after-requester')[5]],['requester'])
    def test_unrecorded_worker_exits_without_claiming_wait(self):
        args=self.args('after-worker-unrecorded');self.assertNotIn('guardian-owner.json',args[2]);self.assertEqual(self.r['semantic']['after-worker-unrecorded']['terminated_actors_without_verified_wait'],2)
    def test_partial_owner_preserved(self):
        with self.assertRaises(ValueError):m.parse(self.args('owner-partial')[2]['guardian-owner.json'])
    def test_synced_owner_does_not_grant_wait(self):self.assertEqual(self.r['semantic']['owner-synced']['actors_waited_by_creator'],0)
    def test_gate_before_release_observes_pipe_failure(self):
        args=self.args('before-worker-release');self.assertNotIn('result/payload.bin',args[2]);self.assertEqual(m.parse(args[2]['worker-exit.json'])['exception_type'],'BrokenPipeError')
    def test_four_child_checkpoints_reject_completion(self):
        for name in m.CASES:
            if name.startswith('child-'):self.assertEqual(self.args(name)[4][-1]['event'],name);self.assertEqual(self.r['semantic'][name]['terminated_actors_without_verified_wait'],2);self.assertFalse(self.r['semantic'][name]['guardian_failure_model_complete'])
    def test_after_worker_wait_preserves_one_direct_wait(self):
        r=self.r['semantic']['after-worker-wait'];self.assertEqual((r['actors_waited_by_creator'],r['terminated_actors_without_verified_wait']),(1,1));self.assertEqual(m.parse(self.args('after-worker-wait')[2]['worker-exit.json'])['reported_exit_code'],0)
    def test_after_both_waits_still_rejects_dead_guardian(self):
        r=self.r['semantic']['after-requester-wait'];self.assertEqual(r['actors_waited_by_creator'],2);self.assertFalse(r['guardian_failure_model_complete']);self.assertNotIn('inner-observation.json',self.args('after-requester-wait')[2])
    def test_note_exit_is_not_actor_wait(self):
        for name in m.CASES:
            for note in self.args(name)[5]:self.assertIs(note['proc_exit_observed'],True);self.assertIs(note['witness_waited_actor'],False);self.assertEqual(note['waitpid_errno'],errno.ECHILD)
    def test_aggregate_creator_waits_and_unverified_waits(self):
        rows=self.r['semantic'].values();self.assertEqual(sum(r['actors_waited_by_creator'] for r in rows),5);self.assertEqual(sum(r['terminated_actors_without_verified_wait'] for r in rows),18)
    def test_broken_pipe_terminal_reports_match_wait_boundary(self):
        count=0
        for name in m.CASES:
            for role in m.roles(name):
                r=m.parse(self.args(name)[2][role+'-exit.json'])
                if not m.reaped(name,role):self.assertEqual((r['reported_exit_code'],r['exception_type']),(1,'BrokenPipeError'));count+=1
        self.assertEqual(count,18)
    def test_twenty_mutants_rejected(self):
        for r in self.r['mutations'].values():self.assertFalse(r['guardian_failure_model_complete']);self.assertTrue(r['errors'])
    def test_source537_preserves532_and_frozen_worker(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(537,532))
        self.assertEqual(self.r['code_sha256']['a23_parent_crash_worker.py'],m.sha(audit.a.read(self.root/'source'/audit.BASE/'tests/a23_parent_crash_worker.py')))
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_pure_consumer_has_no_filesystem_or_wait_api(self):
        saved=[self.args(n) for n in m.CASES]
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')),patch.object(audit.os,'waitpid',side_effect=AssertionError('wait')):
            for args in saved:self.assertEqual(m.assess(*args)['consumer_filesystem_calls'],0)
    def test_readonly_verify_never_launches_and_pin_required(self):
        with patch.object(audit.subprocess,'Popen',side_effect=AssertionError('process')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
        args=self.args();args[1]='0'*64
        with self.assertRaises(ValueError):m.assess(*args)
    def test_actor_wrapper_has_no_process_creation_wait_or_signal(self):
        tree=ast.parse(audit.a.read(self.root/'source'/audit.BASE/'tests/a23_guardian_failure_actor.py'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else None
                self.assertNotIn(name,('Popen','fork','waitpid','kill','killpg'))
    def test_all_authority_false_and_retries_preserve_evidence(self):
        self.assertEqual(self.r['actor_pid_signals'],0)
        for r in (*self.r['semantic'].values(),*self.r['mutations'].values()):
            for key in m.FALSE:self.assertIs(r[key],False)
        for name in m.CASES:self.assertEqual(audit.f.load(self.root/'work/cases'/name/'recovery.json'),dict(retry_refused=True,recovery_refused=True,evidence_unchanged=True))
    def test_coherent_forged_witness_pid_does_not_authenticate_origin(self):
        args=copy.deepcopy(self.args());args[3]['guardian_pid']+=100000
        for checkpoint in args[4]:checkpoint['guardian_pid']=args[3]['guardian_pid']
        checked=m.assess(*args);self.assertTrue(checked['guardian_failure_model_complete']);self.assertFalse(checked['process_origin_authenticated']);self.assertFalse(checked['orphan_reaping_verified'])


if __name__=='__main__':unittest.main()
