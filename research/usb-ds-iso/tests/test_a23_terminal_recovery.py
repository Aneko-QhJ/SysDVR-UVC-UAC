from pathlib import Path
import copy,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_terminal_recovery as audit
m=audit.model


class TerminalRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_TERMINAL_RECOVERY_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-recovery-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.args_at(self.root/'inputs/jobs'/name)
    def test_eighty_seven_cases(self):self.assertEqual((self.r['model_cases'],len(self.r['semantic']),len(self.r['variants'])),(87,58,29))
    def test_classification_counts(self):self.assertEqual(self.r['classification_counts'],dict(absent=1,incomplete=56,commit_associated=6,conflict=24))
    def test_base_roles_have_sixty_four_associated_and_fifty_two_incomplete(self):
        counts={label:sum(v['classification']==label for r in self.r['semantic'].values() for v in r['roles'].values()) for label in ('commit_associated','incomplete')};self.assertEqual(counts,dict(commit_associated=64,incomplete=52))
    def test_all_task_completion_remains_false(self):
        for r in (*self.r['semantic'].values(),*self.r['variants'].values()):self.assertIs(r['task_complete'],False)
    def test_sync_wait_exit_and_inode_status_always_unknown(self):
        for r in (*self.r['semantic'].values(),*self.r['variants'].values()):
            for key in ('directory_sync_status','actor_wait_status','actual_process_exit_status','hardlink_identity_status'):self.assertEqual(r[key],'unknown')
    def test_normal_saved_wait_is_not_recovered_from_disk(self):
        r=self.r['semantic']['normal'];self.assertEqual(r['classification'],'commit_associated');self.assertEqual(r['actor_wait_status'],'unknown');self.assertFalse(r['task_complete'])
    def test_linked_and_synced_commit_snapshots_share_unknown_history(self):
        for role in m.ROLES:
            for phase in ('link','dir_sync'):
                r=self.r['semantic'][role+'-commit-'+phase];self.assertEqual(r['classification'],'commit_associated');self.assertEqual(r['directory_sync_status'],'unknown')
    def test_blank_use_blocks_association_without_claiming_corruption(self):
        r=self.r['semantic']['worker-use-created'];self.assertEqual(r['roles']['worker']['classification'],'incomplete');self.assertEqual(r['roles']['worker']['errors'],[])
    def test_opaque_part_is_explicitly_unvalidated(self):
        r=self.r['variants']['opaque-frame-part'];self.assertEqual(r['classification'],'incomplete');self.assertIn('worker-failed-status.bin.part',r['roles']['worker']['opaque_partial_files']);self.assertFalse(r['record_source_authenticated'])
    def test_unlinked_complete_commit_part_is_incomplete(self):self.assertEqual(self.r['variants']['worker-commit-not-linked']['classification'],'incomplete')
    def test_missing_retained_parts_conflict_with_final_commit(self):
        for name in ('record-part-missing','commit-part-missing'):self.assertEqual(self.r['variants'][name]['classification'],'conflict')
    def test_empty_and_one_role_absent_controls(self):self.assertEqual(self.r['variants']['absent']['classification'],'absent');self.assertEqual(self.r['variants']['requester-absent']['roles']['requester']['classification'],'absent');self.assertEqual(self.r['variants']['requester-absent']['classification'],'incomplete')
    def test_twenty_four_conflicts_rejected(self):
        for name in audit.MUTANTS:self.assertEqual(self.r['variants'][name]['classification'],'conflict');self.assertTrue(self.r['variants'][name]['roles']['worker']['errors'])
    def test_anchor_and_cache_exclude_scenarios_and_witness(self):
        for name in audit.previous.model.CASES:
            raw,_,files=self.args(name);v=m.parse(raw);self.assertNotIn('scenario',v);self.assertNotIn('guardian_case',v);self.assertLessEqual(set(files),m.ALLOWED);self.assertNotIn('publication-events.json',files)
    def test_pure_consumer_never_calls_filesystem_or_process_apis(self):
        import subprocess
        saved=[self.args(n) for n in audit.previous.model.CASES]
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')),patch.object(os,'open',side_effect=AssertionError('filesystem')),patch.object(os,'stat',side_effect=AssertionError('filesystem')),patch.object(os,'waitpid',side_effect=AssertionError('wait')),patch.object(os,'kill',side_effect=AssertionError('signal')),patch.object(subprocess,'Popen',side_effect=AssertionError('process')):
            for args in saved:self.assertEqual(m.classify(*args)['consumer_filesystem_calls'],0);self.assertEqual(m.classify(*args)['consumer_process_calls'],0)
    def test_readonly_verify_never_launches(self):
        import subprocess
        with patch.object(subprocess,'Popen',side_effect=AssertionError('process')):audit.verify(self.root,self.pin)
    def test_external_anchor_and_review_pins_required(self):
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
        args=self.args();args[1]='0'*64
        with self.assertRaises(ValueError):m.classify(*args)
    def test_unsupported_paths_and_witness_files_are_rejected(self):
        for name in ('../outside','/private/tmp/x','publication-events.json','outer.json'):
            args=self.args();args[2][name]=b'{}'
            with self.assertRaises(ValueError):m.classify(*args)
    def test_nonbyte_and_oversized_entries_are_rejected(self):
        for value in ('text',bytearray(b'{}'),b'x'*8193):
            args=self.args();args[2]['worker-exit.json']=value
            with self.assertRaises(ValueError):m.classify(*args)
    def test_anchor_repin_does_not_allow_bool_pid(self):
        args=self.args();v=m.parse(args[0]);v['actors']['worker']=True;args[0]=m.encode(v);args[1]=m.sha(args[0])
        with self.assertRaises(ValueError):m.classify(*args)
    def test_classifier_does_not_modify_or_fill_cache(self):
        args=self.args('worker-use-created');before=copy.deepcopy(args);m.classify(*args);self.assertEqual(args,before);self.assertNotIn('worker-terminal-commit.json',args[2])
    def test_partial_declared_exit_never_becomes_actual_status(self):
        r=self.r['semantic']['worker-exit-file_sync'];self.assertEqual(r['roles']['worker']['declared_exit_code'],91);self.assertEqual(r['actual_process_exit_status'],'unknown');self.assertFalse(r['roles']['worker']['commit_associated'])
    def test_no_new_fixture_jobs_processes_or_queries(self):self.assertEqual((self.r['new_fixture_jobs'],self.r['new_fixture_processes'],self.r['process_queries']),(0,0,0));self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_source554_preserves551(self):v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(554,551))
    def test_all_authority_and_source_authentication_false(self):
        for r in (*self.r['semantic'].values(),*self.r['variants'].values()):
            self.assertFalse(r['record_source_authenticated'])
            for key in m.FALSE:self.assertIs(r[key],False)
    def test_coherent_repinned_declared_pid_forgery_only_associates_bytes(self):
        args=audit.coherent_declared_pid_forgery(self.args());r=m.classify(*args);self.assertEqual(r['classification'],'commit_associated');self.assertFalse(r['task_complete']);self.assertFalse(r['record_source_authenticated']);self.assertEqual(r['actor_wait_status'],'unknown')


if __name__=='__main__':unittest.main()
