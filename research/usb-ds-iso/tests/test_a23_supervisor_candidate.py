from pathlib import Path
import copy,os,sys,tempfile,unittest
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_supervisor_candidate as audit
m=audit.materials


class SupervisorCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_SUPERVISOR_CANDIDATE_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-supervisor-test-'))/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
    def material(self,n):
        p=self.root/'work'/n
        return copy.deepcopy(self.report['observations'][n]),audit.a.read(p/'stdout.bin'),audit.a.read(p/'stderr.bin'),audit.cache(p/'materials')
    def test_eighteen_cases_only_normal_admitted(self):
        self.assertEqual(len(self.report['semantic']),18);self.assertEqual([n for n,r in self.report['semantic'].items() if r['completion_admitted']],['normal'])
    def test_seventeen_created_children_reaped_without_retry(self):
        o=self.report['observations'];self.assertEqual(sum(v['launches'] for v in o.values()),17)
        for n,v in o.items():self.assertEqual(v['reaped'],n!='spawn-error');self.assertEqual(v['retries'],0)
    def test_nonzero_and_signal_exit_recorded(self):
        self.assertEqual(self.report['observations']['abnormal-exit']['returncode'],7);self.assertEqual(self.report['observations']['signal-exit']['returncode'],-15)
    def test_timeout_before_and_after_valid_output_rejected(self):
        for n in ('timeout-before-output','timeout-after-output'):
            o=self.report['observations'][n];self.assertTrue(o['timed_out']);self.assertTrue(o['group_kill_sent']);self.assertEqual(o['returncode'],-9)
        self.assertFalse(self.report['semantic']['timeout-before-output']['materials_valid']);self.assertTrue(self.report['semantic']['timeout-after-output']['materials_valid'])
    def test_output_caps_and_stderr_policy(self):
        self.assertEqual(self.report['observations']['oversize-stdout']['stdout_bytes'],65537);self.assertEqual(self.report['observations']['oversize-stderr']['stderr_bytes'],8193)
        for n in ('oversize-stdout','oversize-stderr','stderr-output'):self.assertFalse(self.report['semantic'][n]['completion_admitted'])
    def test_no_stdout_is_not_success(self):self.assertEqual(self.report['semantic']['no-stdout']['reasons'],['missing_stdout'])
    def test_malformed_and_partial_stdout_rejected(self):
        for n in ('malformed-stdout','partial-stdout'):self.assertIn('malformed_stdout',self.report['semantic'][n]['reasons'])
    def test_empty_and_missing_materials_rejected(self):
        for n in ('empty-materials','missing-material'):self.assertFalse(self.report['semantic'][n]['materials_valid'])
    def test_stdout_case_and_digest_binding(self):
        for n in ('wrong-case','wrong-digest'):self.assertIn('stdout_binding',self.report['semantic'][n]['reasons'])
    def test_nested_worker_failure_survives_process_exit_zero(self):
        r=self.report['semantic']['worker-failure'];self.assertTrue(r['process_healthy']);self.assertTrue(r['driver_complete']);self.assertFalse(r['worker_healthy']);self.assertFalse(r['completion_admitted'])
        self.assertIn('driver_incomplete',self.report['semantic']['driver-failure']['reasons'])
    def test_spawn_error_never_creates_child(self):
        r=self.report['observations']['spawn-error'];self.assertFalse(r['spawned']);self.assertTrue(r['spawn_error']);self.assertIsNone(r['returncode'])
    def test_pure_consumer_opens_no_files(self):
        saved={n:self.material(n) for n in m.CASES}
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')):
            for n,args in saved.items():self.assertEqual(m.assess(n,*args)['consumer_filesystem_calls'],0)
    def test_every_observation_field_rejects_wrong_type(self):
        o,out,err,c=self.material('normal')
        for k,v in o.items():
            mutated=copy.deepcopy(o);mutated[k]=1 if type(v) is bool else False if type(v) is int else 0
            with self.assertRaises(ValueError):m.assess('normal',mutated,out,err,c)
    def test_every_normal_and_nested_member_required(self):
        count=0
        for n in ('normal','worker-failure'):
            o,out,err,c=self.material(n)
            for path in c:
                bad=dict(c);del bad[path];self.assertIn('invalid_materials',m.assess(n,o,out,err,bad)['reasons']);count+=1
        self.assertEqual(count,48)
    def test_every_normal_truncated_member_rejected(self):
        o,out,err,c=self.material('normal')
        for path in c:
            bad=dict(c);bad[path]=bad[path][:-1];self.assertFalse(m.assess('normal',o,out,err,bad)['completion_admitted'])
    def test_nested_health_forgery_after_recomputed_manifests_rejected(self):
        o,out,err,c=self.material('worker-failure');trace=m.parse(c['worker-failure.json']);trace['exit_code']=0;c['worker-failure.json']=m.encode(trace)
        c['worker-materials.json']=m.worker.contract('capture-worker-error',c)
        out=m.encode(m.stdout_report('worker-failure','capture-worker-error',c));o['stdout_bytes']=len(out)
        self.assertIn('invalid_materials',m.assess('worker-failure',o,out,err,c)['reasons'])
    def test_exit_observation_is_not_provenance_negative_control(self):
        o,out,err,c=self.material('abnormal-exit');o['returncode']=0
        result=m.assess('abnormal-exit',o,out,err,c);self.assertTrue(result['completion_admitted']);self.assertFalse(result['provenance_authenticated'])
    def test_launcher_checks_pin_before_spawn(self):
        fixture=self.root/'source'/audit.BASE/'tests/a23_supervised_worker_fixture.py';spawn=Mock(side_effect=AssertionError('spawned'))
        with self.assertRaises(ValueError):audit.supervisor.run_fixture(fixture,'0'*64,'normal',self.root/'inputs/normal',Path('/private/tmp')/'a23-supervisor-pin-mismatch-output',popen=spawn)
        spawn.assert_not_called()
    def test_readonly_verify_does_not_launch(self):
        with patch.object(audit.supervisor,'run_fixture',side_effect=AssertionError('launch')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_sources493_scope_and_no_formal_namespace(self):
        r=audit.f.load(self.root/'audit.json');self.assertEqual((r['source_count'],r['prior_sources_unchanged']),(493,488))
        for k in audit.FALSE:self.assertIs(self.report[k],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists());self.assertEqual(self.report['native_compiler_jobs'],0)


if __name__=='__main__':unittest.main()
