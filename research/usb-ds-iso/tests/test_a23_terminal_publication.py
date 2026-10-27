from pathlib import Path
import ast,copy,errno,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_terminal_publication as audit
m=audit.model


class TerminalPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_TERMINAL_PUBLICATION_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-terminal-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.args_at(self.root/'work/cases'/name,self.r['plan_pins'][name])
    def test_fifty_cases(self):self.assertEqual((self.r['model_cases'],len(self.r['semantic']),len(self.r['mutations'])),(50,26,24))
    def test_only_normal_completes(self):self.assertEqual({n for n,r in self.r['semantic'].items() if r['terminal_publication_model_complete']},{'normal'})
    def test_twenty_four_interruption_windows_valid(self):self.assertEqual(sum(r['publication_interrupted'] for r in self.r['semantic'].values()),24);self.assertTrue(all(r['publication_evidence_valid'] for r in self.r['semantic'].values()))
    def test_before_create_file_missing(self):
        for role in ('requester','worker'):
            for artifact,suffix in m.ARTIFACTS.items():self.assertNotIn(role+'-'+suffix,self.args(role+'-'+artifact+'-before')[2])
    def test_created_file_empty(self):
        for role in ('requester','worker'):
            for artifact,suffix in m.ARTIFACTS.items():self.assertEqual(self.args(role+'-'+artifact+'-created')[2][role+'-'+suffix],b'')
    def test_half_written_prefix_exact(self):
        for role in ('requester','worker'):
            for artifact,suffix in m.ARTIFACTS.items():
                args=self.args(role+'-'+artifact+'-half');event=next(e for e in args[6] if e['filename']==role+'-'+suffix and e['phase']=='before');data=bytes.fromhex(event['content_hex']);self.assertEqual(args[2][role+'-'+suffix],data[:len(data)//2])
    def test_synced_file_complete(self):
        for role in ('requester','worker'):
            for artifact,suffix in m.ARTIFACTS.items():
                args=self.args(role+'-'+artifact+'-synced');event=next(e for e in args[6] if e['filename']==role+'-'+suffix and e['phase']=='before');self.assertEqual(args[2][role+'-'+suffix],bytes.fromhex(event['content_hex']))
    def test_complete_exit_then_interrupted_never_completes(self):
        for role in ('requester','worker'):
            name=role+'-exit-synced';row=self.r['semantic'][name];self.assertTrue(row['complete_terminal_then_interrupted']);self.assertTrue(row['prior_actor_metadata_accepted']);self.assertFalse(row['terminal_publication_model_complete']);self.assertEqual(m.parse(self.args(name)[2][role+'-exit.json'])['reported_exit_code'],91)
    def test_no_invented_wait_for_requested_exit73(self):
        for name in m.CASES:
            if name not in ('normal','guardian-loss'):
                args=self.args(name);self.assertEqual(args[6][-1]['exit_requested'],73);self.assertEqual(self.r['semantic'][name]['actors_waited_by_creator'],0)
    def test_fifty_two_actor_notes_do_not_become_wait(self):
        self.assertEqual((self.r['actor_exit_notes'],self.r['actor_creator_waits'],self.r['terminated_actors_without_verified_wait']),(52,2,50))
        for name in m.CASES:
            for note in self.args(name)[5]:self.assertEqual(note['waitpid_errno'],errno.ECHILD);self.assertIs(note['witness_waited_actor'],False)
    def test_witness_directly_waits_twenty_six_guardians(self):
        for name in m.CASES:self.assertTrue(self.args(name)[3]['guardian_waited']);self.assertEqual(self.args(name)[3]['guardian_returncode'],0 if name=='normal' else -9)
    def test_nonselected_actor_has_complete_terminal(self):
        for name in m.CASES:
            args=self.args(name);selected=m.parse(args[0])['role'];other='requester' if selected=='worker' else 'worker';self.assertEqual(m.parse(args[2][other+'-exit.json'])['reported_exit_code'],0 if name=='normal' else 91)
    def test_ordered_event_trace_bounded(self):
        for name in m.CASES:
            events=self.args(name)[6];self.assertLessEqual(len(events),12);self.assertEqual(events[0]['phase'],'before');self.assertTrue(all(e['model_only'] for e in events))
    def test_normal_has_no_transport_failure_files(self):
        files=self.args()[2]
        for role in ('requester','worker'):self.assertNotIn(role+'-failed-status.bin',files);self.assertNotIn(role+'-transport.json',files)
    def test_guardian_loss_without_local_interruption_keeps_explicit_failure(self):
        row=self.r['semantic']['guardian-loss'];self.assertFalse(row['publication_interrupted']);self.assertTrue(row['selected_terminal_file_complete']);self.assertTrue(row['prior_actor_metadata_accepted']);self.assertFalse(row['terminal_publication_model_complete'])
    def test_twenty_four_mutants_rejected(self):
        for row in self.r['mutations'].values():self.assertFalse(row['publication_evidence_valid']);self.assertTrue(row['errors'])
    def test_source546_preserves541(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(546,541))
    def test_frozen_status_writer_algorithm_unchanged(self):
        def function(name):
            tree=ast.parse(audit.a.read(self.root/'source'/audit.BASE/'tests'/name));return ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='write_status'))
        self.assertEqual(function('a23_terminal_publication_actor.py'),function('a23_status_transport_actor.py'))
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
    def test_consumer_does_not_modify_or_fill_missing_files(self):
        args=self.args('worker-frame-before');before=copy.deepcopy(args);m.assess(*args);self.assertEqual(args,before);self.assertNotIn('worker-exit.json',args[2])
    def test_actor_instrument_has_no_process_creation_wait_or_signal(self):
        tree=ast.parse(audit.a.read(self.root/'source'/audit.BASE/'tests/a23_terminal_publication_actor.py'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                name=node.func.attr if isinstance(node.func,ast.Attribute) else node.func.id if isinstance(node.func,ast.Name) else None
                self.assertNotIn(name,('Popen','fork','waitpid','kill','killpg'))
    def test_all_retry_and_recovery_refused(self):
        for name in m.CASES:self.assertEqual(audit.f.load(self.root/'work/cases'/name/'recovery.json'),dict(retry_refused=True,recovery_refused=True,evidence_unchanged=True))
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_all_authority_false(self):
        for row in (*self.r['semantic'].values(),*self.r['mutations'].values()):
            for key in m.FALSE:self.assertIs(row[key],False)
    def test_complete_outer_pid_forgery_still_not_origin_authentication(self):
        args=copy.deepcopy(self.args());args[3]['guardian_pid']+=100000
        for checkpoint in args[4]:checkpoint['guardian_pid']=args[3]['guardian_pid']
        checked=m.assess(*args);self.assertTrue(checked['terminal_publication_model_complete']);self.assertFalse(checked['process_origin_authenticated']);self.assertFalse(checked['orphan_reaping_verified'])


if __name__=='__main__':unittest.main()
