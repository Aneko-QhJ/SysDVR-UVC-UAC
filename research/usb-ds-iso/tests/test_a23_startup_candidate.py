"""Actual-source startup hooks, one main identity query and isolated ARM link."""
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_a23_startup_candidate as candidate
from analyze_ep0_startup import decode_startup
from workflows.artifacts import verify

class A23StartupCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=candidate.run(cls.output)
        cls.rows={r['case']:r for r in cls.result['cases']};cls.policies={r['case']:r for r in cls.result['policy']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_old_40_results_and_resource_observations_are_preserved(self):
        old=json.loads((candidate.JOURNAL/'audit.json').read_text())
        for row in old['cases']:
            actual={k:v for k,v in self.rows[row['case']].items() if k not in ('startup_status','identity_queries','identity_result','startup_bytes','startup_journal')}
            self.assertEqual(actual,{k:v for k,v in row.items() if k!='startup_journal'})
        self.assertEqual(self.result['case_count'],44)

    def test_one_identity_query_per_startup_without_reset_on_repeat(self):
        for row in self.rows.values():self.assertEqual(row['identity_queries'],1)
        row=self.rows['repeat-begin'];self.assertEqual(row['startup_status'],2)
        self.assertEqual(row['startup_journal']['count'],self.rows['launch-ok']['startup_journal']['count'])

    def test_identity_failure_and_zero_id_disable_journal_without_failing_core(self):
        for case,rc in (('app-identity-error',97),('app-zero-writer',0)):
            row=self.rows[case];self.assertEqual((row['startup_status'],row['identity_result'],row['startup_bytes']),(3,rc,0))
            self.assertTrue(row['core_initialized']);self.assertEqual((row['sm_refs'],row['fs_refs'],row['sd_mounts']),(1,1,1))
            self.assertEqual(row['fatals'],0);self.assertNotIn('startup_journal',row)

    def test_interrupted_identity_query_does_not_fake_ready_or_result(self):
        row=self.rows['app-identity-interrupted'];self.assertEqual((row['startup_status'],row['startup_bytes'],row['exit_reason']),(1,0,3))
        self.assertEqual(row['fs_init'],0);self.assertEqual(row['fatals'],0)
        self.assertEqual(self.policies['interrupted']['status'],1)

    def test_begin_occurs_before_boot_wait_sm_and_core(self):
        main=(self.output/'dormant/source/sysmodule/main.c').read_text()
        body=candidate.function(main,'void __appInit(void)')
        self.assertLess(body.index('Ep0StartupBegin'),body.index('svcSleepThread'))
        self.assertLess(body.index('svcSleepThread'),body.index('smInitialize()'))
        self.assertLess(body.index('smInitialize()'),body.index('CoreInit()'))
        runtime=(self.output/'dormant/source/uvc/ep0_startup_runtime.c').read_text()
        self.assertEqual(runtime.count('svcGetThreadId('),1)

    def test_fatal_result_is_saved_and_sealed_before_original_fatal(self):
        for case,result in (('video-create-error',81),('video-start-error',82),('audio-create-error',81),('audio-start-error',82),('app-core-audio-error',72)):
            d=self.rows[case]['startup_journal'];self.assertEqual(d['fatal']['result'],result);self.assertTrue(d['journal_sealed'])
        core=(self.output/'dormant/source/core.c').read_text();self.assertEqual(core.count('Ep0StartupFatal(rc);\n        R_THROW(rc);'),2)
        main=(self.output/'dormant/source/sysmodule/main.c').read_text();self.assertEqual(main.count('Ep0StartupFatal(rc);\n        fatalThrow(rc);'),2)

    def test_thread_role_mapping_keeps_created_and_started_separate(self):
        d=self.rows['audio-start-error']['startup_journal'];successful=[r['step'] for r in d['successful_api_results']]
        self.assertIn('video_create',successful);self.assertIn('video_start',successful);self.assertIn('audio_create',successful)
        self.assertNotIn('audio_start',successful);self.assertFalse(d['thread_liveness_authenticated'])
        runtime=(self.output/'dormant/source/uvc/ep0_startup_runtime.c').read_text()
        self.assertIn('video!=audio',runtime);self.assertNotIn('->index',runtime)

    def test_partial_core_failure_has_no_invented_cleanup_or_rollback(self):
        row=self.rows['core-audio-error'];self.assertEqual((row['fs_refs'],row['sd_mounts']),(1,1))
        self.assertEqual(row['video_close'],0);self.assertEqual(row['core_exit_body'],0)
        d=row['startup_journal'];self.assertNotIn('fs_exit',[r['step'] for r in d['records']])
        self.assertFalse(self.result['initialization_rollback_implemented'])

    def test_main_seals_after_launch_pair_and_on_uvc_failure_return(self):
        main=(self.output/'dormant/source/sysmodule/main.c').read_text();start=main.index('    Ep0StartupBindThreads(')
        block=main[start:main.index('    LOG("SysDVR-UVC running')]
        self.assertEqual(block.count('LaunchThread('),2);self.assertGreater(block.index('Ep0StartupSeal'),block.index('LaunchThread(&g_audioThread'))
        self.assertIn('(void)Ep0StartupSeal();\n        return 1;',main)
        self.assertTrue(self.rows['launch-ok']['startup_journal']['journal_sealed'])

    def test_callback_video_and_audio_bodies_and_runtime_logger_stay_unchanged(self):
        for label in ('dormant','window-30s'):
            old=candidate.SEALED/label/'source';new=self.output/label/'source'
            for signature in ('void __appExit(void)','static void VideoStreamThread(void* arg)','static void AudioStreamThread(void* arg)'):
                self.assertEqual(candidate.function((old/'sysmodule/main.c').read_text(),signature),candidate.function((new/'sysmodule/main.c').read_text(),signature))
            before=(old/'core.c').read_text();after=(new/'core.c').read_text();sig='void LogFunctionImpl(const char* fmt, ...)'
            a=before.rindex(sig);b=after.rindex(sig)
            self.assertEqual(before[a:before.index('#endif',a)],after[b:after.index('#endif',b)])
            self.assertEqual((old/'core.h').read_bytes(),(new/'core.h').read_bytes())

    def test_runtime_policy_handles_no_init_failures_fatal_seal_and_overflow(self):
        self.assertEqual(len(self.policies),7)
        for row in self.policies.values():self.assertTrue(row['passed']);self.assertEqual((row['owner_reads'],row['payload_reads']),(0,0))
        for case in ('normal','fatal','overflow'):
            d=decode_startup((self.output/('runtime-policy-'+case+'.bin')).read_bytes());self.assertTrue(d['journal_sealed'])
        self.assertTrue(decode_startup((self.output/'runtime-policy-overflow.bin').read_bytes())['overflow'])

    def test_all_actual_hook_replays_fit_coarse_budget_and_remain_independent(self):
        counts=[]
        for row in self.rows.values():
            if 'startup_journal' not in row:continue
            d=row['startup_journal'];self.assertFalse(d['invalid']);self.assertFalse(d['overflow']);counts.append(d['count'])
            self.assertFalse(d['ownership_export_accepted']);self.assertFalse(d['cleanup_authorized'])
        self.assertEqual(max(counts),44);self.assertTrue(self.result['descriptor_interface_iso_hooks_coarse'])

    def test_two_complete_arm_elves_link_eleven_objects_with_new_recipes(self):
        a,b=(self.result['builds'][label] for label in ('dormant','window-30s'))
        self.assertNotEqual(a['runtime_recipe_digest'],b['runtime_recipe_digest'])
        for row in (a,b):self.assertEqual(row['object_count'],11);self.assertTrue(row['linked']);self.assertFalse(row['executed'])
        self.assertTrue(self.result['full_arm_candidate_integrated']);self.assertFalse(self.result['startup_exported_on_device'])

    def test_old_ep0_and_diagnostic_runtime_sources_are_unchanged(self):
        for label in ('dormant','window-30s'):
            old=candidate.SEALED/label/'source/uvc';new=self.output/label/'source/uvc'
            for name in ('ep0_candidate.c','ep0_candidate_guard.c','ep0_request_admission.c','ep0_diagnostic_file.c','ep0_candidate_file.c'):
                self.assertEqual((old/name).read_bytes(),(new/name).read_bytes())
            old_body=candidate.function((old/'uvc_device.c').read_text(),'void UvcDeviceProcessRequests(void)')
            self.assertEqual(old_body,candidate.function((new/'uvc_device.c').read_text(),'void UvcDeviceProcessRequests(void)'))
        self.assertFalse(self.result['diagnostic_wire_modified'])

    def test_sources_tickets_seals_and_offline_boundaries(self):
        self.assertTrue(verify(self.output));self.assertTrue(verify(candidate.SEALED));self.assertTrue(verify(candidate.JOURNAL))
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(candidate.base.ep0.sha(candidate.startup.REPO/n),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(candidate.base.ep0.sha(candidate.base.ep0.PRIVATE/'analysis'/n),h)
        for key in ('production_modified','prior_runtime_modified','usb_accessed','sd_accessed','arm_executed','firmware_packaged',
                    'actual_switch_threads_executed','actual_dma_executed','startup_cost_measured','hardware_verified','root_cause_confirmed'):
            self.assertFalse(self.result[key])
        with self.assertRaises(ValueError):candidate.core_source('source drift')
        self.assertEqual(list(self.output.rglob('*.nso')),[])

if __name__=='__main__':unittest.main()
