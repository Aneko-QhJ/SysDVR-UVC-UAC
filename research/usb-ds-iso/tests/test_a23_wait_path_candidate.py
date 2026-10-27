"""Fixed path behavior, final-ELF save stack and injected SDK handle waits."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_a23_wait_path_candidate as candidate
from model_a23_wait_machine import HandleWaitMachine,Unsupported
from workflows.artifacts import verify

class A23WaitPathCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=candidate.run(cls.output)
        cls.shutdown={r['case']:r for r in cls.result['shutdown_cases']};cls.files={r['case']:r for r in cls.result['file_cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def model(self):return self.result['wait_audit']['dormant']['model']
    def assembly(self):return (self.output/'dormant/disassembly.txt').read_text()

    def test_old_91_startup_shutdown_file_and_limit_observations_are_preserved(self):
        old=json.loads((candidate.SEALED/'audit.json').read_text())
        for key in ('startup_cases','shutdown_cases','file_cases'):
            a={r['case']:{k:v for k,v in r.items() if k not in ('session','disk_session','startup_journal')} for r in old[key]}
            b={r['case']:{k:v for k,v in r.items() if k not in ('session','disk_session','startup_journal')} for r in self.result[key]}
            self.assertEqual(a,b)
        self.assertEqual(self.result['native_legacy_cases'],91);self.assertEqual(self.result['limit_policy'],old['limit_policy'])

    def test_path_byte_values_cap_alias_and_zero_nonce_checks(self):
        p=self.result['path_policy'];self.assertTrue(p['passed']);self.assertEqual(p['cases'],262)
        self.assertEqual(p['path_bytes'],82);self.assertTrue(p['same_legacy_path']);self.assertTrue(p['output_unchanged_on_rejection'])
        for row in (*self.shutdown.values(),*self.files.values()):
            if row['session_attempted'] and row['fs_close']==2 and row['path']:self.assertTrue(row['path'].endswith('.session.bin'))

    def test_only_generated_file_adapter_and_recipe_change(self):
        for label in ('dormant','window-30s'):
            before=candidate.SEALED/label/'source';after=self.output/label/'source'
            for path in before.rglob('*'):
                if path.is_file() and str(path.relative_to(before)) not in ('uvc/ep0_session_file.c','uvc/ep0_candidate_recipe.h'):
                    self.assertEqual(path.read_bytes(),(after/path.relative_to(before)).read_bytes())
            text=(after/'uvc/ep0_session_file.c').read_text();self.assertNotIn('snprintf',text);self.assertNotIn('<stdio.h>',text)
            self.assertIn('ep0_session_path(',text)

    def test_save_direct_graph_closes_at_768_bytes_and_local_frame_is_480(self):
        for label,r in self.result['stack_analysis'].items():
            row=r['roots']['Ep0SessionSaveJoined'];self.assertTrue(row['closed_direct_graph']);self.assertEqual(row['stack_bound_bytes'],768)
            self.assertEqual(row['unresolved'],[]);self.assertNotIn('snprintf',row['reachable_functions']);self.assertNotIn('_svfprintf_r',row['reachable_functions'])
            stack=json.loads((self.output/label/'stack-usage.json').read_text());self.assertEqual(next(p['bytes'] for p in stack if p['function']=='Ep0SessionSaveJoined'),480)
            self.assertEqual(r['roots']['session_capture']['stack_bound_bytes'],352);self.assertFalse(r['whole_thread_stack_verified'])

    def test_two_full_arm_elves_preserve_13_objects_and_bss_while_text_increases(self):
        for row in self.result['builds'].values():
            self.assertEqual(row['object_count'],13);self.assertTrue(row['linked']);self.assertFalse(row['executed'])
            self.assertEqual(row['delta_from_session_candidate'],dict(text=240,data=0,bss=0))
        self.assertNotEqual(self.result['builds']['dormant']['runtime_recipe_digest'],self.result['builds']['window-30s']['runtime_recipe_digest'])

    def test_failure_join_and_old_diagnostic_failure_still_make_no_extra_fs_attempt(self):
        for name in ('video-join-error','audio-join-error'):
            row=self.shutdown[name];self.assertEqual(row['fs_open'],0);self.assertEqual(row['session_owner_reads'],0)
        for name in ('commit-error','collision','fs-open-error'):
            row=self.shutdown[name];self.assertEqual(row['fs_open'],1);self.assertFalse(row['session_attempted'])
        for name in ('healthy','normal-sink-error'):self.assertFalse(self.shutdown[name]['session_attempted'])

    def test_new_file_failure_remains_held_and_own_commit_is_not_embedded(self):
        for name in ('ok','maximum','session-write-error','session-commit-error','session-collision'):
            row=self.shutdown[name];self.assertTrue(row['held']);self.assertEqual(row['thread_closes'],0)
        row=self.shutdown['session-commit-error'];self.assertTrue(row['session_verified']);self.assertFalse(row['session_ack'])
        self.assertTrue(row['session']['sink']['commit_acknowledged']);self.assertFalse(row['session']['envelope_own_save_result_recorded'])

    def test_event_wait_has_one_object_two_handle_types_and_bound_shape(self):
        for r in self.result['wait_audit'].values():
            m=r['model'];self.assertEqual(m['profile_count'],156);self.assertEqual(m['event_wait_objects'],1)
            self.assertEqual((m['wait_objects_one_handle_frame'],m['wait_objects_one_handle_with_svc'],m['event_wait_with_svc']),(288,304,352))
            self.assertTrue(r['scalar_count_proven_at_event_wait']);self.assertTrue(r['event_validity_assumed'])
            self.assertGreater(len(r['event_wait_sites']),0);self.assertEqual([v['local_frame'] for v in r['join_wait']],[32,80])

    def test_all_64_handle_counts_and_clear_types_restore_sp_without_callbacks(self):
        rows=[r for r in self.model()['profiles'] if r['name'].startswith('count-')];self.assertEqual(len(rows),128)
        for row in rows:
            n=row['count'];self.assertEqual(row['peak_user_stack_bytes'],224+((4*n+15)//16)*16+48*n+16)
            self.assertTrue(row['stack_restored']);self.assertFalse(row['indirect_callbacks_reached'])
            self.assertEqual(row['result'],0);self.assertEqual(row['svc_calls'][0]['handles'],list(range(100,100+n)))

    def test_count_above_64_rejected_before_dynamic_allocation_or_svc(self):
        row=next(r for r in self.model()['profiles'] if r['name']=='bad-count-65')
        self.assertEqual((row['result'],row['peak_user_stack_bytes']),(0xee01,224));self.assertEqual(row['svc_calls'],[])

    def test_timeout_cancel_and_reset_results_are_preserved_without_stack_growth(self):
        rows=[r for r in self.model()['profiles'] if not r['name'].startswith('count-') and r['count']==1]
        for row in rows:self.assertLessEqual(row['peak_user_stack_bytes'],304)
        for row in rows:
            if row['name'].startswith('many-cancels'):
                waits=[c for c in row['svc_calls'] if c['svc']==0x18];self.assertEqual(len(waits),101);self.assertEqual(waits[0]['result'],0xec01)
            if row['name'].startswith('timeout'):self.assertEqual(row['result'],0xea01)
        self.assertFalse(self.model()['termination_bound_verified'])

    def test_unsupported_generic_waitable_and_unending_sequence_never_claim_success(self):
        with self.assertRaises(Unsupported):HandleWaitMachine(self.assembly(),count=1,types=(2,)).run()
        with self.assertRaises(Unsupported):HandleWaitMachine(self.assembly(),results=(0xec01,)).run()
        with self.assertRaises(Unsupported):HandleWaitMachine(self.assembly()).run(budget=1)
        self.assertFalse(self.model()['full_symbolic_proof']);self.assertTrue(self.model()['conditional_handle_profile_only'])

    def test_sdk_inputs_bound_and_whole_thread_stack_still_unresolved(self):
        self.assertEqual(set(self.result['sdk_headers_sha256']),set(candidate.SDK_HEADERS))
        for n,h in self.result['sdk_headers_sha256'].items():self.assertEqual(candidate.base.ep0.sha(self.output/'sdk-headers'/n),h)
        for r in self.result['stack_analysis'].values():
            self.assertIsNone(r['roots']['VideoStreamThread']['stack_bound_bytes']);self.assertFalse(r['whole_thread_stack_verified'])
        self.assertFalse(self.result['real_wait_or_stop_time_bound'])

    def test_seals_tickets_sources_and_offline_limits(self):
        for p in (self.output,candidate.SEALED,candidate.CONCURRENT):self.assertTrue(verify(p))
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(candidate.base.ep0.sha(candidate.candidate.startup.startup.REPO/n),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(candidate.base.ep0.sha(candidate.base.ep0.PRIVATE/'analysis'/n),h)
        for key in ('old_source_modified','old_runtime_modified','old_wire_modified','normal_sink_modified','main_worker_callback_modified',
                    'cleanup_authorized_by_path','wait_implementation_modified','arm_executed','firmware_packaged','usb_accessed','sd_accessed',
                    'actual_switch_threads_executed','actual_dma_executed','full_symbolic_proof','whole_thread_stack_verified','real_wait_or_stop_time_bound',
                    'hardware_verified','root_cause_confirmed','source_authenticated'):self.assertFalse(self.result[key])
        self.assertEqual(list(self.output.rglob('*.nso')),[]);self.assertEqual(list(self.output.rglob('*.nsp')),[])

if __name__=='__main__':unittest.main()
