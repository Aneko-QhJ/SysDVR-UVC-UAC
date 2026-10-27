from pathlib import Path
import ast,copy,errno,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_terminal_commit as audit
m=audit.model;io=m.publication


class TerminalCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_TERMINAL_COMMIT_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-commit-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.args_at(self.root/'work/cases'/name,self.r['plan_pins'][name])
    def unit_job(self):return Path(tempfile.mkdtemp(prefix='a23-commit-unit-',dir='/private/tmp'))
    def test_eighty_two_cases(self):self.assertEqual((self.r['model_cases'],len(self.r['semantic']),len(self.r['mutations'])),(82,58,24))
    def test_only_normal_completes(self):self.assertEqual({n for n,r in self.r['semantic'].items() if r['terminal_commit_model_complete']},{'normal'})
    def test_fifty_six_interruption_windows(self):self.assertEqual(sum(r['publication_interrupted'] for r in self.r['semantic'].values()),56);self.assertTrue(all(r['publication_evidence_valid'] for r in self.r['semantic'].values()))
    def test_final_files_are_complete_or_absent(self):
        for name in m.CASES:
            args=self.args(name);v=m.parse(args[0]);role=v['role']
            for kind in ('frame','transport','exit','commit'):
                path=m.filename(role,kind)
                if path in args[2]:self.assertEqual(args[2][path],args[2][path+'.part']);self.assertTrue(args[2][path])
    def test_commit_link_visibility_is_distinct_from_directory_sync(self):
        for role in ('requester','worker'):
            linked=self.r['semantic'][role+'-commit-link'];synced=self.r['semantic'][role+'-commit-dir_sync'];self.assertTrue(linked['local_commit_file_valid']);self.assertFalse(linked['commit_directory_sync_observed']);self.assertTrue(synced['commit_directory_sync_observed'])
    def test_synced_commit_then_interruption_never_completes(self):
        for role in ('requester','worker'):
            r=self.r['semantic'][role+'-commit-dir_sync'];self.assertTrue(r['committed_then_interrupted']);self.assertFalse(r['terminal_commit_model_complete']);self.assertEqual(r['actors_waited_by_creator'],0)
    def test_every_runtime_cut_retains_local_use(self):
        for name in m.CASES:
            files=self.args(name)[2]
            for role in ('requester','worker'):self.assertIn(role+'-terminal-use.json',files)
    def test_commit_binds_artifact_bytes_without_wait_claim(self):
        files=self.args('guardian-loss')[2]
        for role in ('requester','worker'):
            c=m.parse(files[role+'-terminal-commit.json']);self.assertFalse(c['process_wait_verified'])
            for name,v in c['records'].items():self.assertEqual((v['sha256'],v['size']),(m.sha(files[name]),len(files[name])))
    def test_guardian_death_never_gains_actor_wait(self):
        self.assertEqual((self.r['actor_creator_waits'],self.r['terminated_actors_without_verified_wait']),(2,114))
        for name,r in self.r['semantic'].items():self.assertEqual(r['actors_waited_by_creator'],2 if name=='normal' else 0)
    def test_exit_notes_are_not_witness_actor_wait(self):
        self.assertEqual(self.r['actor_exit_notes'],116)
        for name in m.CASES:
            for note in self.args(name)[5]:self.assertEqual(note['waitpid_errno'],errno.ECHILD);self.assertIs(note['witness_waited_actor'],False)
    def test_event_frames_are_bounded_json(self):
        for name in m.CASES:
            events=self.args(name)[6];self.assertLessEqual(len(events),30);self.assertEqual(m.parse(m.encode(events)),events)
        self.assertEqual(len(self.args('guardian-loss')[6]),30)
    def test_pure_consumer_never_opens_or_waits(self):
        saved=[self.args(n) for n in m.CASES]
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')),patch.object(audit.os,'waitpid',side_effect=AssertionError('wait')):
            for args in saved:self.assertEqual(m.assess(*args)['consumer_filesystem_calls'],0)
    def test_readonly_verify_never_launches(self):
        with patch.object(audit.subprocess,'Popen',side_effect=AssertionError('process')):audit.verify(self.root,self.pin)
    def test_external_pins_required(self):
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
        args=self.args();args[1]='0'*64
        with self.assertRaises(ValueError):m.assess(*args)
    def test_source551_preserves546(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(551,546));self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_status_writer_ast_is_unchanged(self):
        def function(name):
            tree=ast.parse(audit.a.read(self.root/'source'/audit.BASE/'tests'/name));return ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='write_status'))
        self.assertEqual(function('a23_terminal_commit_actor.py'),function('a23_status_transport_actor.py'))
    def test_twenty_four_mutants_rejected(self):
        for r in self.r['mutations'].values():self.assertFalse(r['publication_evidence_valid']);self.assertTrue(r['errors'])
    def test_consumer_does_not_fill_or_change_files(self):
        args=self.args('worker-use-created');before=copy.deepcopy(args);m.assess(*args);self.assertEqual(args,before);self.assertNotIn('worker-terminal-commit.json',args[2])
    def test_guardian_and_both_local_retries_refused(self):
        for name in m.CASES:self.assertEqual(audit.f.load(self.root/'work/cases'/name/'recovery.json'),dict(guardian_retry_refused=True,guardian_recovery_refused=True,local_retry_refusals=2,local_recovery_refusals=2,evidence_unchanged=True))
    def test_all_authority_false(self):
        for r in (*self.r['semantic'].values(),*self.r['mutations'].values()):
            for key in m.FALSE:self.assertIs(r[key],False)
    def test_coherent_outer_pid_forgery_does_not_authenticate_origin(self):
        args=copy.deepcopy(self.args());args[3]['guardian_pid']+=100000
        for checkpoint in args[4]:checkpoint['guardian_pid']=args[3]['guardian_pid']
        r=m.assess(*args);self.assertTrue(r['terminal_commit_model_complete']);self.assertFalse(r['process_origin_authenticated']);self.assertFalse(r['orphan_reaping_verified'])
    def test_use_marker_refuses_second_publication_without_overwrite(self):
        job=self.unit_job();records={'worker-exit.json':b'original'};io.publish(job,'worker',records,dict(role='worker'),lambda *_:None);before=audit.cache(job)
        with self.assertRaises(FileExistsError):io.publish(job,'worker',{'worker-exit.json':b'other'},dict(role='worker'),lambda *_:None)
        self.assertEqual(audit.cache(job),before)
    def test_existing_final_is_never_overwritten(self):
        job=self.unit_job();(job/'worker-exit.json').write_bytes(b'preserved')
        with self.assertRaises(FileExistsError):io.publish(job,'worker',{'worker-exit.json':b'new'},dict(role='worker'),lambda *_:None)
        self.assertEqual((job/'worker-exit.json').read_bytes(),b'preserved');self.assertFalse((job/'worker-terminal-commit.json').exists())
    def test_artifact_directory_sync_error_stops_before_commit(self):
        job=self.unit_job();events=[];original=io.sync_directory;calls=[]
        def sync(path):
            calls.append(path)
            if len(calls)==2:raise OSError(errno.EIO,'mock directory sync failure')
            return original(path)
        with patch.object(io,'sync_directory',side_effect=sync),self.assertRaises(OSError):io.publish(job,'worker',{'worker-exit.json':b'data'},dict(role='worker'),lambda *row:events.append(row[:2]))
        self.assertTrue((job/'worker-exit.json').exists());self.assertFalse((job/'worker-terminal-commit.json').exists());self.assertNotIn(('exit','dir_sync'),events)
    def test_commit_directory_sync_error_has_no_complete_event(self):
        job=self.unit_job();events=[];original=io.sync_directory;calls=[]
        def sync(path):
            calls.append(path)
            if len(calls)==3:raise OSError(errno.EIO,'mock commit directory sync failure')
            return original(path)
        with patch.object(io,'sync_directory',side_effect=sync),self.assertRaises(OSError):io.publish(job,'worker',{'worker-exit.json':b'data'},dict(role='worker'),lambda *row:events.append(row[:2]))
        self.assertTrue((job/'worker-terminal-commit.json').exists());self.assertNotIn(('commit','dir_sync'),events);self.assertNotIn(('complete','complete'),events)
    def test_artifact_file_sync_error_stops_before_link(self):
        job=self.unit_job();original=io.os.fsync;calls=[]
        def sync(fd):
            calls.append(fd)
            if len(calls)==3:raise OSError(errno.EIO,'mock artifact sync failure')
            return original(fd)
        with patch.object(io.os,'fsync',side_effect=sync),self.assertRaises(OSError):io.publish(job,'worker',{'worker-exit.json':b'data'},dict(role='worker'),lambda *_:None)
        self.assertFalse((job/'worker-exit.json').exists());self.assertFalse((job/'worker-terminal-commit.json').exists());self.assertEqual((job/'worker-exit.json.part').read_bytes(),b'data')
    def test_short_writes_are_completed(self):
        captured=bytearray()
        def write(fd,data):count=min(2,len(data));captured.extend(data[:count]);return count
        with patch.object(io.os,'write',side_effect=write):io.write_all(9,b'abcdef')
        self.assertEqual(captured,b'abcdef')
    def test_zero_bool_or_invalid_write_progress_fails(self):
        for value in (0,True,False,-1,4,None):
            with patch.object(io.os,'write',return_value=value),self.assertRaises(OSError):io.write_all(9,b'abc')
    def test_recover_refuses_without_filesystem_access(self):
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')):
            with self.assertRaises(ValueError):io.recover(Path('/private/tmp/no-recovery'),'worker')
    def test_actor_candidate_has_no_process_creation_wait_or_signal(self):
        tree=ast.parse(audit.a.read(self.root/'source'/audit.BASE/'tests/a23_terminal_commit_actor.py'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else None
                self.assertNotIn(name,('Popen','fork','waitpid','kill','killpg'))


if __name__=='__main__':unittest.main()
