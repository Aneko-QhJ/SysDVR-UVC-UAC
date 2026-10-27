"""Full ARM association hooks, returned receipts and independent REL1 adapter."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_a23_session_candidate as candidate
from analyze_ep0_session import decode_session
from workflows.artifacts import verify

class A23SessionCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=candidate.run(cls.output)
        cls.startup={r['case']:r for r in cls.result['startup_cases']};cls.shutdown={r['case']:r for r in cls.result['shutdown_cases']}
        cls.files={r['case']:r for r in cls.result['file_cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_original_44_actual_startup_results_and_journals_are_preserved(self):
        old=json.loads((candidate.SEALED/'audit.json').read_text())
        for row in old['cases']:
            new=self.startup[row['case']]
            self.assertEqual({k:v for k,v in row.items() if k!='startup_journal'},
                             {k:v for k,v in new.items() if k not in ('session','startup_journal')})
            if 'startup_journal' in row:
                self.assertEqual(row['startup_journal']['records'],new['startup_journal']['records'])
        self.assertEqual(self.result['startup_case_count'],45)

    def test_combined_actual_startup_hooks_fit_64_record_budget(self):
        d=self.startup['full-launch']['startup_journal'];self.assertEqual(d['count'],44)
        self.assertTrue(d['complete_journal']);self.assertFalse(d['overflow']);self.assertFalse(d['invalid'])
        steps=[r['step'] for r in d['successful_api_results']]
        for step in ('sm_initialize','core_initialize','usb_device_initialize','video_start','audio_start'):self.assertIn(step,steps)

    def test_startup_fatal_and_partial_thread_failure_only_copy_startup(self):
        for name in ('app-sm-error','app-core-audio-error','audio-start-error','video-create-error'):
            row=self.startup[name];d=row['session'];self.assertEqual(d['mode'],'startup_only')
            self.assertIsNotNone(d['startup']['fatal']);self.assertIsNone(d['diagnostic']);self.assertIsNone(d['sink'])
            self.assertEqual(d['startup']['records'],row['startup_journal']['records'])
        self.assertFalse(self.result['initialization_failure_filesystem_export'])

    def test_startup_identity_failure_and_interruption_do_not_invent_records(self):
        for name,status in (('app-identity-error',3),('app-zero-writer',3),('app-identity-interrupted',1)):
            d=self.startup[name]['session'];self.assertEqual((d['mode'],d['startup_status']),('metadata_only',status))
            self.assertIsNone(d['startup']);self.assertEqual(d['starter'],0)
        self.assertEqual(self.startup['app-identity-interrupted']['session']['startup_identity_result'],0)
        for name in ('startup-identity-error','startup-zero-writer'):
            row=self.shutdown[name];self.assertEqual(row['session']['mode'],'ep0_only');self.assertTrue(row['session_ack'])

    def test_binding_reuses_existing_nonce_without_new_random_or_usb_calls(self):
        for label in ('dormant','window-30s'):
            old=(candidate.SEALED/label/'source/sysmodule/main.c').read_text();new=(self.output/label/'source/sysmodule/main.c').read_text()
            signature='static void VideoStreamThread(void* arg)'
            body=candidate.startup.function(new,signature)
            self.assertEqual(body.replace('    (void)Ep0SessionBind(writer,boot_nonce,session_nonce,ep0CandidateRecipe);\n',''),candidate.startup.function(old,signature))
            self.assertEqual(body.count('randomGet('),2);self.assertEqual(body.count('svcGetThreadId('),1)
        self.assertEqual(self.shutdown['bind-skipped']['session']['fallback_reason'],2)
        self.assertEqual(self.shutdown['bind-skipped']['fs_open'],1);self.assertFalse(self.shutdown['bind-skipped']['session_attempted'])

    def test_failed_join_has_no_ep0_receipt_or_filesystem_reads(self):
        for name,rc in (('video-join-error',78),('audio-join-error',79)):
            row=self.shutdown[name];self.assertEqual((row['fs_open'],row['session_owner_reads'],row['receipt_reads']),(0,0,0))
            self.assertEqual(row['session']['fallback_reason'],1);self.assertIsNone(row['session']['diagnostic'])
            self.assertIn(rc,(row['session']['video_join'],row['session']['audio_join']))
            self.assertEqual(row['thread_closes'],0);self.assertTrue(row['held'])

    def test_joined_diagnostic_return_publishes_receipt_for_exact_input(self):
        row=self.shutdown['ok'];d=row['session'];self.assertEqual(d['mode'],'startup_and_ep0')
        self.assertEqual((d['starter'],d['ep0_writer']),(22,11));self.assertEqual(d['startup']['count'],44)
        self.assertEqual(row['receipt_reads'],1);self.assertTrue(d['sink']['input_crc_matched']);self.assertTrue(d['sink']['commit_acknowledged'])
        self.assertEqual(row['fs_open'],2);self.assertTrue(row['session_ack']);self.assertEqual(d,row['disk_session'])
        self.assertFalse(self.result['save_outcome_injected'])

    def test_failed_old_diagnostic_save_does_not_start_session_file_or_retry(self):
        for name in ('commit-error','collision','fs-open-error'):
            row=self.shutdown[name];self.assertEqual(row['fs_open'],1);self.assertFalse(row['session_attempted']);self.assertFalse(row['session_ack'])
            self.assertFalse(row['session']['sink']['commit_acknowledged']);self.assertTrue(row['held'])
        s=self.shutdown['commit-error']['session']['sink'];self.assertTrue(s['content_verified']);self.assertEqual(s['result'],98)

    def test_session_save_failure_and_success_never_authorize_teardown(self):
        for name in ('ok','maximum','session-write-error','session-collision','session-commit-error'):
            row=self.shutdown[name];self.assertTrue(row['held'])
            self.assertEqual((row['thread_closes'],row['uvc_closes'],row['core_closes'],row['sm_closes']),(0,0,0,0))
        row=self.shutdown['session-commit-error'];self.assertTrue(row['session_verified']);self.assertFalse(row['session_ack'])
        self.assertTrue(row['session']['sink']['commit_acknowledged']);self.assertFalse(row['session']['envelope_own_save_result_recorded'])

    def test_normal_sink_and_authorization_flow_is_preserved(self):
        row=self.shutdown['healthy'];self.assertFalse(row['held']);self.assertEqual(row['fs_open'],1)
        self.assertEqual((row['thread_closes'],row['uvc_closes'],row['core_closes'],row['sm_closes']),(2,1,1,1))
        self.assertEqual(row['session']['fallback_reason'],3);self.assertFalse(row['session_attempted'])
        row=self.shutdown['normal-sink-error'];self.assertTrue(row['held']);self.assertFalse(row['session_attempted']);self.assertEqual(row['fs_open'],1)

    def test_all_new_file_errors_readback_corruption_and_full_capacity(self):
        good={'session-ok','session-short-read','session-maximum','session-maximum-short-read'}
        self.assertEqual(self.result['file_case_count'],20)
        for name,row in self.files.items():
            self.assertEqual(row['session_ack'],name in good);self.assertEqual(row['fs_open'],2)
            self.assertTrue(row['session_attempted']);self.assertTrue(row['no_retry'])
            if row['session_verified']:self.assertEqual(row['session'],row['disk_session'])
        for name in ('session-maximum','session-maximum-short-read'):
            row=self.files[name];self.assertEqual(row['session_bytes'],7968);self.assertEqual(row['session']['startup']['count'],64)
        self.assertEqual(self.result['limit_policy'],dict(passed=True,cases=6,maximum=7968,legacy_caps_unchanged=True))

    def test_callbacks_audio_handlers_and_legacy_sinks_are_unchanged(self):
        for label in ('dormant','window-30s'):
            before=candidate.SEALED/label/'source';after=self.output/label/'source'
            for name in ('capture.c','grcd.c','core.h','uvc/uvc_device.c','uvc/ep0_candidate.c','uvc/ep0_diagnostic_file.c','uvc/ep0_candidate_file.c','uvc/ep0_request_admission.c'):
                self.assertEqual((before/name).read_bytes(),(after/name).read_bytes())
            for signature in ('void __appExit(void)','static void AudioStreamThread(void* arg)'):
                self.assertEqual(candidate.startup.function((before/'sysmodule/main.c').read_text(),signature),candidate.startup.function((after/'sysmodule/main.c').read_text(),signature))
        for name in ('callback-live','callback-unstarted'):self.assertEqual(self.shutdown[name]['session_bytes'],0)

    def test_two_full_arm_elves_link_13_objects_and_report_static_costs(self):
        a,b=(self.result['builds'][n] for n in ('dormant','window-30s'));self.assertNotEqual(a['runtime_recipe_digest'],b['runtime_recipe_digest'])
        for name,row in self.result['builds'].items():
            self.assertEqual(row['object_count'],13);self.assertTrue(row['linked']);self.assertFalse(row['executed'])
            self.assertEqual(row['delta_from_startup_candidate']['bss'],16384);self.assertFalse(row['whole_call_graph_stack_verified'])
            stack={r['function']:r for r in json.loads((self.output/name/'stack-usage.json').read_text())}
            self.assertEqual(stack['session_capture']['bytes'],352);self.assertEqual(stack['Ep0SessionSaveJoined']['bytes'],560)
        self.assertFalse(self.result['startup_cost_measured'])

    def test_main_orders_return_capture_and_separate_save_without_cleanup(self):
        main=(self.output/'dormant/source/sysmodule/main.c').read_text();start=main.index('    if(!Ep0CandidateFinish');end=main.index('    // One save attempt',start);body=main[start:end]
        self.assertLess(body.index('Ep0CandidateSaveDiagnostic'),body.index('Ep0SessionJoined'))
        self.assertLess(body.index('Ep0SessionJoined'),body.index('Ep0SessionSaveJoined'))
        self.assertIn('if(diagnostic_saved)',body);self.assertNotIn('ep0_cleanup_authorize',body)
        self.assertIn('for(;;)svcSleepThread',body)

    def test_seals_sources_tickets_offline_and_authentication_boundaries(self):
        for p in (self.output,candidate.SEALED,candidate.PROTOTYPE):self.assertTrue(verify(p))
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(candidate.base.ep0.sha(candidate.startup.startup.REPO/n),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(candidate.base.ep0.sha(candidate.base.ep0.PRIVATE/'analysis'/n),h)
        for key in ('production_modified','prior_runtime_modified','usb_accessed','sd_accessed','firmware_packaged','arm_executed',
                    'actual_switch_threads_executed','actual_dma_executed','whole_call_graph_stack_verified','hardware_verified','root_cause_confirmed','source_authenticated',
                    'session_save_after_diagnostic_failure','initialization_failure_filesystem_export','callback_modified','old_wire_modified','normal_sink_modified','cleanup_authorized_by_session'):self.assertFalse(self.result[key])
        self.assertEqual(list(self.output.rglob('*.nso')),[]);self.assertEqual(list(self.output.rglob('*.nsp')),[])
        for row in (*self.startup.values(),*self.shutdown.values(),*self.files.values()):
            if 'session' not in row:continue
            for key in ('source_authenticated','cleanup_authorized','hardware_verified','root_cause_confirmed','envelope_own_save_result_recorded'):self.assertFalse(row['session'][key])

if __name__=='__main__':unittest.main()
