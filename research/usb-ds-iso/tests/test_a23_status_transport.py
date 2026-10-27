from pathlib import Path
import ast,copy,errno,importlib.util,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_status_transport as audit
m=audit.model
spec=importlib.util.spec_from_file_location('status_candidate',ROOT/'tests/a23_status_transport_actor.py');candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)


class StatusTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_STATUS_TRANSPORT_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-status-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.args_at(self.root/'work/cases'/name,self.r['plan_pins'][name])
    def test_fifty_three_cases(self):self.assertEqual((self.r['model_cases'],len(self.r['semantic']),len(self.r['mutations'])),(53,13,40))
    def test_only_normal_completes(self):self.assertEqual({n for n,r in self.r['semantic'].items() if r['status_transport_model_complete']},{'normal'})
    def test_eighteen_explicit_transport_failures(self):self.assertEqual(sum(v['status_transport_failures'] for v in self.r['semantic'].values()),18);self.assertEqual(self.r['unhandled_broken_pipe_reports'],0)
    def test_raw_exit91_and_epipe_preserved(self):
        count=0
        for name in m.CASES:
            args=self.args(name)
            for role in m.prior.roles(name):
                terminal=m.parse(args[2][role+'-exit.json'])
                if not m.prior.reaped(name,role):self.assertEqual((terminal['reported_exit_code'],terminal['exception_type']),(91,'StatusTransportFailure'));count+=1
        self.assertEqual(count,18)
    def test_frames_bound_and_no_epipe_retry(self):
        for name in m.CASES:
            files=self.args(name)[2]
            for role in m.prior.roles(name):
                if not m.prior.reaped(name,role):
                    report=m.parse(files[role+'-transport.json']);self.assertEqual((report['errno'],report['write_attempts'],report['bytes_committed']),(errno.EPIPE,1,0));self.assertEqual(report['failed_frame_sha256'],m.sha(files[role+'-failed-status.bin']));self.assertIs(report['delivery_confirmed'],False)
    def test_short_writes_finish_exact_frame(self):
        seen=bytearray()
        def write(fd,data):self.assertEqual(fd,9);count=min(2,len(data));seen.extend(data[:count]);return count
        self.assertEqual(candidate.write_status(9,b'abcdef',write),6);self.assertEqual(seen,b'abcdef')
    def test_eintr_then_success(self):
        calls=[]
        def write(fd,data):
            calls.append(bytes(data))
            if len(calls)==1:raise InterruptedError(errno.EINTR,'interrupted')
            return len(data)
        self.assertEqual(candidate.write_status(9,b'abc',write),3);self.assertEqual(calls,[b'abc',b'abc'])
    def test_epipe_is_not_retried(self):
        calls=[]
        def write(fd,data):calls.append(fd);raise BrokenPipeError(errno.EPIPE,'closed')
        with self.assertRaises(candidate.StatusTransportFailure) as found:candidate.write_status(9,b'abc',write)
        self.assertEqual(calls,[9]);self.assertEqual((found.exception.reason,found.exception.error,found.exception.committed,found.exception.attempts),('epipe',errno.EPIPE,0,1))
    def test_partial_progress_then_epipe_retained(self):
        calls=[]
        def write(fd,data):
            calls.append(bytes(data))
            if len(calls)==1:return 1
            raise BrokenPipeError(errno.EPIPE,'closed')
        with self.assertRaises(candidate.StatusTransportFailure) as found:candidate.write_status(9,b'abc',write)
        self.assertEqual(found.exception.committed,1);self.assertEqual(calls,[b'abc',b'bc'])
    def test_zero_bool_and_oversized_progress_rejected(self):
        for value in (0,False,True,4,-1,None):
            with self.subTest(value=value),self.assertRaises(candidate.StatusTransportFailure):candidate.write_status(9,b'abc',lambda *_:value)
    def test_eintr_budget_is_bounded(self):
        calls=[]
        def write(*_):calls.append(1);raise InterruptedError(errno.EINTR,'interrupted')
        with self.assertRaises(candidate.StatusTransportFailure) as found:candidate.write_status(9,b'abc',write)
        self.assertEqual(len(calls),16);self.assertEqual(found.exception.reason,'attempt_limit')
    def test_other_io_error_preserved(self):
        def write(*_):raise OSError(errno.EIO,'failed')
        with self.assertRaises(candidate.StatusTransportFailure) as found:candidate.write_status(9,b'abc',write)
        self.assertEqual((found.exception.reason,found.exception.error),('io_error',errno.EIO))
    def test_invalid_frame_rejected_before_write(self):
        for fd,data in ((True,b'a'),(-1,b'a'),(9,b''),(9,b'x'*8193),(9,'abc')):
            with self.subTest(fd=fd,size=len(data)),self.assertRaises(ValueError):candidate.write_status(fd,data,lambda *_:self.fail('write called'))
    def test_no_new_wait_qualification(self):
        self.assertEqual((self.r['actor_creator_waits'],self.r['terminated_actors_without_verified_wait'],self.r['witness_actor_waits']),(5,18,0))
        baseline=audit.f.load(self.root/'inputs/baseline-summary.json')
        for name,row in self.r['semantic'].items():
            for key in ('actor_exit_notes_valid','actors_waited_by_creator','terminated_actors_without_verified_wait'):self.assertEqual(row[key],baseline['semantic'][name][key])
    def test_late_actor_success_still_rejects_guardian_death(self):
        row=self.r['semantic']['after-requester-wait'];self.assertEqual(row['actors_waited_by_creator'],2);self.assertEqual(row['status_transport_failures'],0);self.assertFalse(row['status_transport_model_complete'])
    def test_early_guardian_loss_has_no_actor(self):self.assertEqual(self.args('before-requester')[5],[]);self.assertEqual(self.r['semantic']['before-requester']['status_transport_failures'],0)
    def test_four_child_pauses_keep_failed_frames(self):
        for name in m.CASES:
            if name.startswith('child-'):self.assertEqual(self.r['semantic'][name]['failed_status_frames_valid'],2);self.assertEqual(self.args(name)[4][-1]['event'],name)
    def test_forty_mutants_rejected(self):
        for row in self.r['mutations'].values():self.assertFalse(row['status_transport_model_complete']);self.assertTrue(row['errors'])
    def test_runtime_alias_and_original_observer_separate(self):
        self.assertEqual(self.r['instrumentation_sha256']['a23_guardian_failure_actor.py'],m.sha(audit.a.read(self.root/'source'/audit.BASE/'tests/a23_status_transport_actor.py')))
        self.assertNotEqual(self.r['instrumentation_sha256']['a23_guardian_failure_actor.py'],self.r['frozen_observer_sha256'])
    def test_source541_preserves537(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(541,537));self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_pure_consumer_never_opens_or_waits(self):
        saved=[self.args(n) for n in m.CASES]
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')),patch.object(audit.os,'waitpid',side_effect=AssertionError('wait')):
            for args in saved:self.assertEqual(m.assess(*args)['consumer_filesystem_calls'],0)
    def test_readonly_verify_never_launches_and_external_pins_required(self):
        with patch.object(audit.subprocess,'Popen',side_effect=AssertionError('process')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
        args=self.args();args[1]='0'*64
        with self.assertRaises(ValueError):m.assess(*args)
    def test_compatibility_projection_does_not_mutate_evidence(self):
        args=self.args('before-worker-release');before=copy.deepcopy(args);m.assess(*args);self.assertEqual(args,before);self.assertEqual(m.parse(args[2]['worker-exit.json'])['reported_exit_code'],91)
    def test_actor_candidate_does_not_create_wait_or_signal(self):
        tree=ast.parse(audit.a.read(self.root/'source'/audit.BASE/'tests/a23_status_transport_actor.py'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else None
                self.assertNotIn(name,('Popen','fork','waitpid','kill','killpg'))
    def test_all_authority_false_and_retry_refused(self):
        for row in (*self.r['semantic'].values(),*self.r['mutations'].values()):
            for key in m.FALSE:self.assertIs(row[key],False)
        for name in m.CASES:self.assertEqual(audit.f.load(self.root/'work/cases'/name/'recovery.json'),dict(retry_refused=True,recovery_refused=True,evidence_unchanged=True))
    def test_coherent_outer_pid_forgery_still_does_not_authenticate_origin(self):
        args=copy.deepcopy(self.args());args[3]['guardian_pid']+=100000
        for cp in args[4]:cp['guardian_pid']=args[3]['guardian_pid']
        checked=m.assess(*args);self.assertTrue(checked['status_transport_model_complete']);self.assertFalse(checked['process_origin_authenticated']);self.assertFalse(checked['orphan_reaping_verified'])


if __name__=='__main__':unittest.main()
