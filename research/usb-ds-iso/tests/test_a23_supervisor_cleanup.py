from pathlib import Path
import copy,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_supervisor_cleanup as audit
m=audit.materials


class SupervisorCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_SUPERVISOR_CLEANUP_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-cleanup-test-'))/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
    def args(self,n):
        p=self.root/'work'/n;return copy.deepcopy(self.report['observations'][n]),audit.a.read(p/'stdout.bin'),audit.a.read(p/'stderr.bin'),audit.cache(p/'materials')
    def test_fifteen_cases_two_positive(self):
        self.assertEqual(len(self.report['semantic']),15);self.assertEqual({n for n,r in self.report['semantic'].items() if r['completion_admitted']},audit.GOOD)
    def test_direct_leader_exit_not_pipe_eof(self):
        for n in ('leader-both-held','leader-stdout-held','leader-stderr-held'):
            o=self.report['observations'][n];self.assertEqual(o['returncode'],0);self.assertTrue(o['timed_out']);self.assertEqual(o['group_kill_outcome'],'sent');self.assertFalse(o['leader_reaped_before_signal']);self.assertFalse(self.report['semantic'][n]['completion_admitted'])
    def test_both_pipe_eof_not_worker_exit(self):
        o=self.report['observations']['eof-worker-alive'];self.assertTrue(o['stdout_eof'] and o['stderr_eof']);self.assertTrue(o['timed_out']);self.assertEqual(o['returncode'],-9)
    def test_one_pipe_eof_still_bounded(self):
        for n in ('stdout-eof-worker-alive','stderr-eof-worker-alive'):self.assertTrue(self.report['observations'][n]['timed_out']);self.assertEqual(self.report['observations'][n]['returncode'],-9)
    def test_interrupted_read_continues_same_child(self):
        o=self.report['observations']['read-interrupted'];self.assertEqual((o['read_interrupts'],o['launches'],o['retries']),(1,1,0));self.assertFalse(o['group_kill_attempted']);self.assertTrue(self.report['semantic']['read-interrupted']['completion_admitted'])
    def test_read_and_selector_failures_rejected(self):
        for n in ('read-error','selector-error'):self.assertFalse(self.report['semantic'][n]['completion_admitted']);self.assertEqual(self.report['observations'][n]['returncode'],-9)
    def test_group_failure_has_explicit_direct_fallback(self):
        o=self.report['observations']['group-kill-error'];self.assertEqual((o['group_kill_outcome'],o['fallback_kill_outcome']),('error','sent'));self.assertTrue(o['reaped'])
    def test_group_missing_is_not_signal_sent(self):
        o=self.report['observations']['group-kill-not-found'];self.assertEqual((o['group_kill_outcome'],o['fallback_kill_outcome']),('not_found','sent'));self.assertFalse(self.report['semantic']['group-kill-not-found']['completion_admitted'])
    def test_wait_failure_retains_unreaped_status(self):
        for n in audit.WAIT_FAILURES:
            o=self.report['observations'][n];self.assertFalse(o['reaped']);self.assertIsNone(o['returncode']);self.assertTrue(o['wait_error'])
    def test_harness_rescue_cannot_upgrade_admission(self):
        for n in audit.WAIT_FAILURES:
            r=self.report['semantic'][n];self.assertTrue(r['harness']['rescue_used']);self.assertTrue(r['harness']['direct_child_reaped']);self.assertFalse(r['harness']['admission_upgraded']);self.assertFalse(r['completion_admitted'])
    def test_combined_cleanup_failure_is_recorded(self):
        o=self.report['observations']['cleanup-multiple-errors'];self.assertEqual((o['group_kill_outcome'],o['fallback_kill_outcome']),('error','error'));self.assertTrue(o['wait_timed_out'])
    def test_all_observation_fields_reject_wrong_types(self):
        o,out,err,c=self.args('normal')
        for k,v in o.items():
            bad=copy.deepcopy(o);bad[k]=1 if type(v) is bool else False if type(v) is int else 0
            with self.assertRaises(ValueError):m.assess('normal',bad,out,err,c)
    def test_signal_attempt_and_outcome_relation(self):
        o,out,err,c=self.args('group-kill-error');o['group_kill_attempted']=False
        with self.assertRaisesRegex(ValueError,'attempt/outcome'):m.assess('group-kill-error',o,out,err,c)
    def test_missing_normal_members_rejected(self):
        o,out,err,c=self.args('normal');self.assertEqual(len(c),23)
        for path in c:
            bad=dict(c);del bad[path];self.assertIn('invalid_materials',m.assess('normal',o,out,err,bad)['reasons'])
    def test_all_normal_truncated_members_rejected(self):
        o,out,err,c=self.args('normal')
        for path in c:
            bad=dict(c);bad[path]=bad[path][:-1];self.assertFalse(m.assess('normal',o,out,err,bad)['completion_admitted'])
    def test_consumers_open_no_files(self):
        saved={n:self.args(n) for n in m.CASES}
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')):
            for n,args in saved.items():self.assertEqual(m.assess(n,*args)['consumer_filesystem_calls'],0)
    def test_clear_failure_observation_can_be_forged_negative_control(self):
        o,out,err,c=self.args('eof-worker-alive');o.update(timed_out=False,returncode=0,group_kill_attempted=False,group_kill_outcome='none')
        self.assertTrue(m.assess('eof-worker-alive',o,out,err,c)['completion_admitted'])
    def test_readonly_verify_never_launches(self):
        with patch.object(audit.supervisor,'run_fixture',side_effect=AssertionError('launch')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_wrong_fixture_pin_rejected_before_launch(self):
        p=self.root/'source'/audit.BASE/'tests/a23_supervisor_cleanup_fixture.py'
        with patch.object(audit.supervisor.subprocess,'Popen',side_effect=AssertionError('launch')):
            with self.assertRaises(ValueError):audit.supervisor.run_fixture(p,'0'*64,'normal',self.root/'inputs/normal',Path('/private/tmp/a23-cleanup-wrong-pin-output'))
    def test_sources498_scope_and_no_formal_reservation(self):
        r=audit.f.load(self.root/'audit.json');self.assertEqual((r['source_count'],r['prior_sources_unchanged']),(498,493))
        for k in audit.FALSE:self.assertIs(self.report[k],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())


if __name__=='__main__':unittest.main()
