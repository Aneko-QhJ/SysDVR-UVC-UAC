from pathlib import Path
import os,sys,tempfile,threading,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_integrated_fixture as audit
m=audit.model


class IntegratedFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_INTEGRATED_FIXTURE_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-integrated-test-',dir='/private/tmp'))/'review';audit.run(cls.root)
        cls.pin=m.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.r=audit.verify(cls.root,cls.pin)
    def args(self,name='normal'):return audit.args_at(self.root/'work/cases'/name,self.r['plan_pins'][name])
    def stage(self):
        stage=Path(tempfile.mkdtemp(prefix='a23-integrated-unit-',dir='/private/tmp'));script=stage/'a23_integrated_fixture_worker.py'
        audit.a.put(stage,script.name,audit.a.read(self.root/'source'/audit.BASE/'tests'/script.name))
        for n in m.LIBRARIES:audit.a.put(stage,'lib/'+n,audit.a.read(self.root/'source'/audit.BASE/'tools'/n))
        job=stage/'job';pin=audit.prepare(job,script,audit.cache(self.root/'inputs/seed'),{})
        return script,job,pin,m.sha(script.read_bytes())
    def test_fifty_one_cases_and_process_accounting(self):
        self.assertEqual((self.r['model_cases'],len(self.r['semantic']),len(self.r['mutations'])),(51,31,20))
        self.assertEqual((self.r['python_fixture_direct_children'],self.r['candidate_direct_reaps'],self.r['harness_rescue_reaps'],self.r['parent_resource_rescues']),(27,25,2,5))
    def test_only_normal_integrated_completion(self):self.assertEqual({n for n,v in self.r['semantic'].items() if v['integrated_model_complete']},{'normal'})
    def test_all_three_sync_failures_prevent_launch(self):
        for name in audit.SPECS:
            if not name.startswith('pre-'):continue
            r=self.r['semantic'][name];o=self.r['observations'][name]
            self.assertFalse(o['supervisor']['spawned']);self.assertEqual(o['supervisor']['launches'],0);self.assertFalse(r['launch_ready_recorded']);self.assertFalse(r['attempt_sync_recorded']);self.assertEqual(o['prelaunch_error'],'prelaunch_io_error')
    def test_spawn_failure_retains_synchronized_attempt(self):
        r=self.r['semantic']['spawn-error'];self.assertTrue(r['attempt_sync_recorded']);self.assertTrue(r['launch_ready_recorded']);self.assertFalse(self.r['observations']['spawn-error']['supervisor']['spawned'])
    def test_ten_child_cut_points_rejected(self):
        for event in m.io.CHILD_EVENTS:self.assertFalse(self.r['semantic']['cut-'+event]['integrated_model_complete'])
        self.assertTrue(self.r['semantic']['cut-stdout.emit']['receipt_binding_valid'])
    def test_receipt_valid_exit_seven_and_timeout_stay_failures(self):
        for name in ('exit-seven','timeout-after-output'):
            self.assertTrue(self.r['semantic'][name]['receipt_binding_valid']);self.assertFalse(self.r['semantic'][name]['integrated_model_complete'])
    def test_close_failure_cannot_be_upgraded_by_healthy_child(self):
        for name in ('stdout-close-error','selector-close-error'):
            self.assertEqual(self.r['observations'][name]['supervisor']['returncode'],0);self.assertTrue(self.r['semantic'][name]['receipt_binding_valid']);self.assertFalse(self.r['semantic'][name]['integrated_model_complete']);self.assertTrue(self.r['harness'][name]['resource_rescues'])
    def test_harness_reap_does_not_rewrite_candidate(self):
        for name in ('wait-error','timeout-and-wait'):
            self.assertFalse(self.r['observations'][name]['supervisor']['reaped']);self.assertTrue(self.r['harness'][name]['direct_child_reaped']);self.assertTrue(self.r['harness'][name]['rescue_used']);self.assertFalse(self.r['semantic'][name]['integrated_model_complete'])
    def test_all_four_combined_failures_rejected(self):
        for name in ('partial-and-close','sync-and-close','exit-and-close','timeout-and-wait'):
            self.assertFalse(self.r['semantic'][name]['integrated_model_complete']);self.assertTrue(self.r['semantic'][name]['errors'])
    def test_all_retries_and_recovery_refused_without_changes(self):
        for v in self.r['recovery'].values():self.assertTrue(all(v.values()))
    def test_twenty_mutants_rejected(self):
        for v in self.r['mutations'].values():self.assertFalse(v['integrated_model_complete']);self.assertTrue(v['errors'])
    def test_wrong_external_pin_spends_use_without_popen(self):
        script,job,_pin,fp=self.stage()
        with patch.object(audit.launcher.subprocess,'Popen',side_effect=AssertionError('process')):
            with self.assertRaisesRegex(ValueError,'external integrated'):audit.launcher.run(script,job,'0'*64,fp)
        self.assertTrue((job/'launcher-use.json').is_file());self.assertFalse((job/'launch-attempt.json').exists())
    def test_changed_library_refuses_worker(self):
        script,job,pin,fp=self.stage();(script.parent/'lib/a23_integrated_fixture_io.py').write_bytes(b'changed')
        with patch.object(audit.launcher.subprocess,'Popen',side_effect=AssertionError('process')):
            with self.assertRaisesRegex(ValueError,'library pin'):audit.launcher.run(script,job,pin,fp)
        self.assertFalse((job/'launch-attempt.json').exists())
    def test_pure_consumer_opens_no_files(self):
        saved=[self.args(n) for n in audit.SPECS]
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')):
            for args in saved:self.assertEqual(m.assess(*args)['consumer_filesystem_calls'],0)
    def test_readonly_verify_never_launches(self):
        with patch.object(audit.launcher.subprocess,'Popen',side_effect=AssertionError('process')):audit.verify(self.root,self.pin)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_bool_use_counter_rejected(self):self.assertIn('publication_trace',self.r['mutations']['use-bool']['errors'])
    def test_source523_preserves517_and_production_disabled(self):
        v=audit.f.load(self.root/'audit.json');self.assertEqual((v['source_count'],v['prior_sources_unchanged']),(523,517));self.assertFalse(self.r['production_launcher_integrated']);self.assertFalse((ROOT/'private/sequence-reservations32').exists())
        for r in (*self.r['semantic'].values(),*self.r['mutations'].values()):
            for k in m.FALSE:self.assertIs(r[k],False)
    def test_split_protocol_order_has_single_parent_ready_boundary(self):
        rows=[m.parse(x) for x in self.args()[2]['trace.jsonl'].splitlines()]
        self.assertEqual([v['event'] for v in rows],[*m.io.PRE_EVENTS,'launch.ready',*m.io.CHILD_EVENTS])
    def test_two_callers_do_not_pollute_trace_or_spawn_twice(self):
        script,job,pin,fp=self.stage();barrier=threading.Barrier(2);results=[]
        def call():
            barrier.wait()
            try:audit.launcher.run(script,job,pin,fp);results.append('spent')
            except FileExistsError:results.append('refused')
        with patch.object(audit.launcher.subprocess,'Popen',side_effect=OSError('fixed no-child race')) as popen:
            threads=[threading.Thread(target=call) for _ in range(2)]
            for t in threads:t.start()
            for t in threads:t.join(timeout=3);self.assertFalse(t.is_alive())
            self.assertEqual(popen.call_count,1)
        self.assertCountEqual(results,['spent','refused']);rows=[m.parse(x) for x in (job/'trace.jsonl').read_bytes().splitlines()]
        self.assertEqual([v['event'] for v in rows],[*m.io.PRE_EVENTS,'launch.ready'])
    def test_empty_use_marker_blocks_all_trace_and_process(self):
        script,job,pin,fp=self.stage();(job/'launcher-use.json').write_bytes(b'')
        with patch.object(audit.launcher.subprocess,'Popen',side_effect=AssertionError('process')):
            with self.assertRaises(FileExistsError):audit.launcher.run(script,job,pin,fp)
        self.assertFalse((job/'trace.jsonl').exists());self.assertEqual((job/'launcher-use.json').read_bytes(),b'')
    def test_coherent_outer_cleanup_forgery_is_only_model_evidence(self):
        args=self.args('stdout-close-error');v=m.parse(args[0]);v['parent_fault']=None;args[0]=m.encode(v);args[1]=m.sha(args[0]);args[2]['integrated-plan.json']=args[0]
        raw=args[2]['launch.json'];args[2]['launcher-use.json']=m.encode(m.use_record(raw,args[0]));args[5]['plan_sha256']=m.sha(args[0]);args[5]['supervisor'].update(close_errors=[],close_completed=m.supervisor.CLOSE_ORDER.copy())
        r=m.assess(*args);self.assertTrue(r['integrated_model_complete']);self.assertFalse(r['process_origin_authenticated']);self.assertFalse(r['power_loss_recovery_verified'])
    def test_historical_sdk_material_bytes_unchanged(self):
        files=self.args()[2];actual={n.removeprefix('result/materials/'):v for n,v in files.items() if n.startswith('result/materials/')}
        self.assertEqual(actual,audit.cache(self.root/'inputs/seed'));self.assertFalse(self.r['semantic']['normal']['cached_sdk_materials_generated_this_launch'])


if __name__=='__main__':unittest.main()
