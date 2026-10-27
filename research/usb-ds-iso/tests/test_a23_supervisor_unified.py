from pathlib import Path
import copy,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_supervisor_unified as audit
m=audit.materials


class SupervisorUnifiedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_SUPERVISOR_UNIFIED_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-unified-test-'))/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
    def args(self,n):
        p=self.root/'work'/n;return copy.deepcopy(self.report['observations'][n]),audit.a.read(p/'stdout.bin'),audit.a.read(p/'stderr.bin'),audit.cache(p/'materials')
    def test_merged_coverage37_two_positive(self):
        expected=set(audit.collection.materials.CASES)|set(audit.previous.materials.CASES)|set(m.CLOSE_CASES)
        self.assertEqual(set(self.report['semantic']),expected);self.assertEqual(len(expected),37)
        self.assertEqual({n for n,r in self.report['semantic'].items() if r['completion_admitted']},m.GOOD)
    def test_one_schema_and_strict_field_inventory(self):
        for o in self.report['observations'].values():self.assertEqual(set(o),m.KEYS);self.assertEqual(o['schema'],'A23-supervisor-unified-observation-1')
        self.assertEqual(len(m.KEYS),33)
    def test_close_errors_deny_even_exit_zero_driver_complete(self):
        for n in m.CLOSE_CASES[:-1]:
            o=self.report['observations'][n];r=self.report['semantic'][n];self.assertEqual(o['returncode'],0);self.assertTrue(r['driver_complete']);self.assertTrue(o['reaped']);self.assertFalse(r['completion_admitted']);self.assertFalse(o['group_kill_attempted'])
    def test_other_close_attempts_continue_after_failure(self):
        for n in m.CLOSE_CASES:
            o=self.report['observations'][n];self.assertEqual(o['close_attempts'],m.CLOSE_ORDER);self.assertEqual(o['close_completed'],[x for x in m.CLOSE_ORDER if x not in o['close_errors']])
    def test_close_and_wait_failure_does_not_bypass_cleanup_wait(self):
        o=self.report['observations']['close-and-wait-error'];self.assertTrue(o['cleanup_wait_attempted']);self.assertTrue(o['wait_error']);self.assertFalse(o['reaped']);self.assertIn('stdout',o['close_errors'])
    def test_harness_resource_and_child_rescue_never_upgrade(self):
        for n in set(m.CLOSE_CASES)|audit.WAIT_FAILURES:
            r=self.report['semantic'][n];self.assertFalse(r['harness']['admission_upgraded']);self.assertFalse(r['completion_admitted']);self.assertEqual(r['harness']['resource_rescues'],m.close_errors(n))
    def test_unified_output_limits(self):
        self.assertEqual(self.report['observations']['oversize-stdout']['stdout_bytes'],65537);self.assertEqual(self.report['observations']['oversize-stderr']['stderr_bytes'],8193)
        for n in ('oversize-stdout','oversize-stderr'):self.assertIn('output_limit',self.report['semantic'][n]['reasons'])
    def test_nested_worker_zero_exit_remains_rejected(self):
        r=self.report['semantic']['worker-failure'];self.assertTrue(r['driver_complete']);self.assertFalse(r['worker_healthy']);self.assertEqual(self.report['observations']['worker-failure']['returncode'],0);self.assertFalse(r['completion_admitted'])
    def test_eof_and_leader_exit_remain_separate(self):
        for n in ('leader-both-held','leader-stdout-held','leader-stderr-held'):self.assertEqual(self.report['observations'][n]['returncode'],0);self.assertTrue(self.report['observations'][n]['timed_out'])
        o=self.report['observations']['eof-worker-alive'];self.assertTrue(o['stdout_eof'] and o['stderr_eof']);self.assertEqual(o['returncode'],-9)
    def test_eintr_continues_without_restart(self):
        o=self.report['observations']['read-interrupted'];self.assertEqual((o['read_interrupts'],o['launches'],o['retries']),(1,1,0));self.assertTrue(self.report['semantic']['read-interrupted']['completion_admitted'])
    def test_signal_failure_fallback_and_candidate_wait_status(self):
        o=self.report['observations']['group-kill-not-found'];self.assertEqual((o['group_kill_outcome'],o['fallback_kill_outcome']),('not_found','sent'))
        for n in audit.WAIT_FAILURES:self.assertFalse(self.report['observations'][n]['reaped']);self.assertIsNone(self.report['observations'][n]['returncode']);self.assertTrue(self.report['semantic'][n]['harness']['rescue_used'])
    def test_spawn_failure_has_no_close_or_wait_claim(self):
        o=self.report['observations']['spawn-error'];self.assertFalse(o['spawned']);self.assertEqual(o['close_attempts'],[]);self.assertFalse(o['cleanup_wait_attempted']);self.assertFalse(o['completion_wait_attempted'])
    def test_pure_consumer_opens_no_files(self):
        saved={n:self.args(n) for n in m.CASES}
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')):
            for n,args in saved.items():self.assertEqual(m.assess(n,*args)['consumer_filesystem_calls'],0)
    def test_all33_fields_reject_wrong_type(self):
        o,out,err,c=self.args('normal')
        for k,v in o.items():
            bad=copy.deepcopy(o);bad[k]=1 if type(v) is bool else False if type(v) is int else 0
            with self.assertRaises(ValueError):m.assess('normal',bad,out,err,c)
    def test_contradictory_close_claims_rejected(self):
        o,out,err,c=self.args('stdout-close-error');o['close_completed'].append('stdout')
        with self.assertRaises(ValueError):m.assess('stdout-close-error',o,out,err,c)
    def test_missing_and_truncated_members_rejected(self):
        count=0
        for n in ('normal','worker-failure'):
            o,out,err,c=self.args(n)
            for path in c:
                bad=dict(c);del bad[path];self.assertIn('invalid_materials',m.assess(n,o,out,err,bad)['reasons']);count+=1
        self.assertEqual(count,48)
        o,out,err,c=self.args('normal')
        for path in c:
            bad=dict(c);bad[path]=bad[path][:-1];self.assertFalse(m.assess('normal',o,out,err,bad)['completion_admitted'])
    def test_nested_forgery_resealed_and_observation_negative_control(self):
        o,out,err,c=self.args('worker-failure');trace=m.parse(c['worker-failure.json']);trace['exit_code']=0;c['worker-failure.json']=m.encode(trace);c['worker-materials.json']=m.old.worker.contract('capture-worker-error',c)
        out=m.encode(m.old.stdout_report('worker-failure','capture-worker-error',c));o['stdout_bytes']=len(out)
        self.assertIn('invalid_materials',m.assess('worker-failure',o,out,err,c)['reasons'])
        o,out,err,c=self.args('stdout-close-error');o['close_errors']=[];o['close_completed']=m.CLOSE_ORDER.copy()
        self.assertTrue(m.assess('stdout-close-error',o,out,err,c)['completion_admitted'])
    def test_readonly_verify_never_launches(self):
        with patch.object(audit.supervisor,'run_fixture',side_effect=AssertionError('launch')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_fixture_pin_before_launch(self):
        p=self.root/'source'/audit.BASE/'tests/a23_supervisor_unified_fixture.py'
        with patch.object(audit.supervisor.subprocess,'Popen',side_effect=AssertionError('launch')):
            with self.assertRaises(ValueError):audit.supervisor.run_fixture(p,'0'*64,'normal',self.root/'inputs/normal',Path('/private/tmp/a23-unified-wrong-pin-output'))
    def test_source_inventory503_scope_and_no_reservation(self):
        r=audit.f.load(self.root/'audit.json');self.assertEqual((r['source_count'],r['prior_sources_unchanged']),(503,498))
        for k in audit.FALSE:self.assertIs(self.report[k],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())


if __name__=='__main__':unittest.main()
