from pathlib import Path
import copy,os,sys,tempfile,threading,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_fixture_job_binding as audit
m=audit.model


class FixtureJobBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_FIXTURE_JOB_BINDING_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-bound-job-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.args_at(self.root/'work/cases'/name,self.r['launch_pins'][name])
    def test_thirty_four_cases(self):
        self.assertEqual((self.r['model_cases'],len(self.r['semantic']),len(self.r['preflight_cases']),len(self.r['mutations'])),(34,10,4,20))
    def test_only_normal_fixture_completes(self):
        self.assertEqual({n for n,v in self.r['semantic'].items() if v['fixture_completion']},{'normal'})
    def test_all_fourteen_job_ids_and_nonces_unique(self):
        v=[audit.f.load(p) for p in (self.root/'work').glob('*/**/launch.json')]
        self.assertEqual(len(v),14);self.assertEqual(len({x['fixture_job_id'] for x in v}),14);self.assertEqual(len({x['launch_nonce'] for x in v}),14)
    def test_no_authority_in_any_verdict(self):
        for v in (*self.r['semantic'].values(),*self.r['mutations'].values()):
            for k in m.FALSE:self.assertIs(v[k],False)
    def test_retry_refused_for_all_ten_launches(self):self.assertEqual(set(self.r['retries'].values()),{'refused_spent_fixture_attempt'})
    def test_preflight_failure_retains_spent_marker(self):
        for v in self.r['preflight_cases'].values():self.assertTrue(v['attempt_retained']);self.assertTrue(v['retry_refused'])
    def test_exit_zero_does_not_substitute_for_binding(self):
        for n in ('wrong-nonce','wrong-job','tampered-material'):
            self.assertEqual(self.r['observations'][n]['supervisor']['returncode'],0);self.assertFalse(self.r['semantic'][n]['receipt_binding_valid'])
    def test_valid_receipt_cannot_override_timeout_or_exit_failure(self):
        for n in ('abnormal-exit','timeout-after-output','stderr-output'):
            self.assertTrue(self.r['semantic'][n]['receipt_binding_valid']);self.assertFalse(self.r['semantic'][n]['fixture_completion'])
    def test_missing_and_partial_receipts_fail(self):
        for n in ('missing-receipt','partial-receipt'):self.assertIn('receipt_or_materials',self.r['semantic'][n]['errors'])
    def test_twenty_semantic_mutations_rejected(self):
        for v in self.r['mutations'].values():self.assertTrue(v['errors']);self.assertFalse(v['fixture_completion'])
    def test_external_pin_required_even_if_result_is_valid(self):
        args=self.args();args[1]='0'*64
        with self.assertRaisesRegex(ValueError,'external launch'):m.assess(*args)
    def test_recomputed_links_do_not_admit_bool_attempt_counter(self):
        args=self.args();v=m.parse(args[2]);v['attempt_number']=True;args[2]=m.encode(v)
        args[3]=m.observation(args[0],args[2],args[3]['supervisor']);args[4]=m.encode(m.report(args[0],args[2],args[6]));args[3]['supervisor']['stdout_bytes']=len(args[4]);args[7]=m.encode(m.receipt(args[0],args[2],args[4],args[6]))
        self.assertIn('attempt_or_observation',m.assess(*args)['errors'])
    def test_every_receipt_member_required(self):
        for k in m.parse(self.args()[7]):
            args=self.args();v=m.parse(args[7]);del v[k];args[7]=m.encode(v);self.assertFalse(m.assess(*args)['fixture_completion'],k)
    def test_launch_flags_strict_after_repin(self):
        for key,value in (('maximum_launches',True),('maximum_launches',2),('model_only',False),('production_execution_authorized',True),('cached_materials_origin','fresh_sdk')):
            args=self.args();v=m.parse(args[0]);v[key]=value;args[0]=m.encode(v);args[1]=m.sha(args[0])
            with self.assertRaises(ValueError):m.assess(*args)
    def test_cached_sdk_bytes_are_not_fresh_execution(self):
        seed=audit.cache(self.root/'inputs/seed');self.assertEqual(self.args()[6],seed)
        self.assertFalse(self.r['semantic']['normal']['cached_sdk_materials_generated_this_launch']);self.assertTrue(self.r['semantic']['normal']['cached_materials_valid'])
    def test_pure_consumer_uses_no_filesystem_or_process(self):
        saved=[self.args(n) for n in m.MODES]
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')),patch.object(audit.launcher.subprocess,'Popen',side_effect=AssertionError('process')):
            for args in saved:self.assertEqual(m.assess(*args)['consumer_filesystem_calls'],0)
    def test_readonly_verify_never_launches(self):
        with patch.object(audit.launcher.subprocess,'Popen',side_effect=AssertionError('process')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_exclusive_marker_serializes_two_fixture_callers(self):
        stage=Path(tempfile.mkdtemp(prefix='a23-bound-race-',dir='/private/tmp'));script=stage/'a23_job_launch_fixture.py'
        script.write_bytes(audit.a.read(self.root/'source'/audit.BASE/'tests'/script.name));job=stage/'job'
        pin=audit.prepare(job,script,'normal',audit.cache(self.root/'inputs/seed'));fp=m.sha(script.read_bytes());barrier=threading.Barrier(2);out=[]
        def caller():
            barrier.wait()
            try:audit.launcher.run(script,job,pin,fp);out.append('spent')
            except FileExistsError:out.append('refused')
        with patch.object(audit.launcher.subprocess,'Popen',side_effect=OSError('fixed no-process test')) as popen:
            threads=[threading.Thread(target=caller) for _ in range(2)]
            for t in threads:t.start()
            for t in threads:t.join(timeout=3);self.assertFalse(t.is_alive())
            self.assertEqual(popen.call_count,1)
        self.assertCountEqual(out,['spent','refused'])
    def test_forged_outer_observation_remains_only_model_evidence(self):
        args=self.args('abnormal-exit');args[3]['supervisor']['returncode']=0
        result=m.assess(*args);self.assertTrue(result['fixture_completion']);self.assertFalse(result['process_origin_authenticated']);self.assertFalse(result['job_launch_binding_authenticated'])
    def test_source512_preserves507_and_formal_namespace_absent(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(512,507))
        self.assertFalse((ROOT/'private/sequence-reservations32').exists());self.assertEqual((self.r['authorization_consumptions'],self.r['permit_claim_invocations']),(0,0))


if __name__=='__main__':unittest.main()
