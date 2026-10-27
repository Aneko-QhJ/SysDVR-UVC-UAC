"""Actual startup failure paths, modeled handles and forced callback boundaries."""
from pathlib import Path
import sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_startup as audit
from workflows.artifacts import verify

class A23StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=audit.run(cls.output)
        cls.rows={r['case']:r for r in cls.result['cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_second_capture_open_failure_retains_first_session_without_close(self):
        for case in ('capture-audio-error','core-audio-error'):
            r=self.rows[case];self.assertEqual(r['result'],72);self.assertTrue(r['video_active'])
            self.assertFalse(r['audio_active']);self.assertEqual(r['video_close'],0)
        r=self.rows['core-audio-error'];self.assertFalse(r['core_initialized'])
        self.assertEqual((r['fs_refs'],r['sd_mounts'],r['fs_exit'],r['core_exit_body']),(1,1,0,0))

    def test_first_capture_open_failure_does_not_open_audio_but_core_keeps_fs(self):
        r=self.rows['capture-video-error'];self.assertEqual((r['video_open'],r['audio_open']),(1,0))
        self.assertFalse(r['video_active']);self.assertFalse(r['audio_active'])
        r=self.rows['core-video-error'];self.assertEqual(r['result'],71);self.assertEqual((r['fs_refs'],r['sd_mounts']),(1,1))
        self.assertEqual(r['fs_exit'],0)

    def test_successful_core_reentry_and_repeated_exit_do_not_duplicate_resources(self):
        for case in ('core-ok','core-reentry'):
            r=self.rows[case];self.assertEqual((r['fs_init'],r['fs_exit'],r['fs_refs'],r['sd_mounts']),(1,1,0,0))
            self.assertEqual((r['video_open'],r['audio_open'],r['video_close'],r['audio_close']),(1,1,1,1))
            self.assertEqual(r['core_exit_body'],1)

    def test_hypothetical_partial_retry_duplicates_fs_acquisition(self):
        r=self.rows['retry-partial'];self.assertEqual(r['result'],0)
        self.assertEqual((r['fs_init'],r['fs_exit'],r['fs_refs'],r['sd_mounts']),(2,1,1,1))
        self.assertEqual((r['video_open'],r['audio_open']),(1,2))
        self.assertEqual((r['log_delete'],r['log_create']),(2,2))
        self.assertFalse(r['video_active']);self.assertFalse(r['audio_active'])

    def test_logging_failures_are_nonfatal_and_log_create_results_are_ignored(self):
        for case in ('core-fs-error','core-sd-error','log-delete-error','log-create-error'):
            r=self.rows[case];self.assertEqual(r['result'],0);self.assertEqual(r['fatals'],0)
        for case in ('log-delete-error','log-create-error'):
            r=self.rows[case];self.assertEqual((r['log_delete'],r['log_create']),(1,1))
        self.assertEqual(self.rows['core-fs-error']['fs_exit'],1)
        self.assertEqual(self.rows['core-sd-audio-error']['fs_refs'],1)
        self.assertEqual(self.rows['core-fs-audio-error']['fs_refs'],0)

    def test_serial_failure_is_nonfatal_and_only_successful_initialize_is_exited(self):
        r=self.rows['serial-init-error'];self.assertEqual((r['result'],r['serial_exit']),(0,0))
        r=self.rows['serial-get-error'];self.assertEqual((r['result'],r['serial_exit']),(0,1))
        for case in ('app-setsys-error','app-fw-error'):
            self.assertEqual(self.rows[case]['fatals'],0);self.assertTrue(self.rows[case]['core_initialized'])

    def test_usb_top_level_failure_calls_exit_without_cleanup_authorization(self):
        for case in audit.CASES:
            if not case.startswith('usb-') or case in ('usb-ok','usb-reentry','usb-init-error'):continue
            r=self.rows[case];self.assertNotEqual(r['result'],0);self.assertEqual(r['usb_exit'],1)
            self.assertFalse(r['usb_initialized']);self.assertEqual(r['cleanup_phase'],0)
            self.assertTrue(r['usb_exit_auto_close_is_model'])
        self.assertEqual(self.rows['usb-iso-enable-error']['registered'],3)

    def test_usb_init_failure_and_successful_reentry_have_no_extra_exit(self):
        self.assertEqual(self.rows['usb-init-error']['usb_exit'],0)
        for case in ('usb-ok','usb-reentry'):
            r=self.rows[case];self.assertEqual(r['result'],0);self.assertTrue(r['usb_initialized'])
            self.assertTrue(r['usb_active']);self.assertEqual((r['registered'],r['usb_exit']),(3,0))

    def test_app_init_fatal_keeps_previously_acquired_core_resources_in_model(self):
        r=self.rows['app-sm-error'];self.assertEqual((r['fatals'],r['fatal_result'],r['fs_init']),(1,80,0))
        r=self.rows['app-core-audio-error'];self.assertEqual((r['fatals'],r['fatal_result']),(1,72))
        self.assertEqual((r['sm_refs'],r['fs_refs'],r['sd_mounts']),(1,1,1));self.assertTrue(r['video_active'])
        self.assertFalse(r['core_initialized'])

    def test_video_start_failure_has_created_handle_but_no_successful_start(self):
        r=self.rows['video-create-error'];self.assertFalse(r['video_created']);self.assertEqual(r['thread_starts'],0)
        r=self.rows['video-start-error'];self.assertTrue(r['video_created']);self.assertFalse(r['video_live'])
        self.assertEqual((r['thread_creates'],r['thread_starts'],r['fatal_result']),(1,1,82))

    def test_audio_launch_failure_follows_successful_video_launch(self):
        for case in ('audio-create-error','audio-start-error'):
            r=self.rows[case];self.assertTrue(r['video_created']);self.assertTrue(r['video_live'])
            self.assertFalse(r['audio_live']);self.assertEqual(r['thread_creates'],2)
            self.assertTrue(r['core_initialized']);self.assertTrue(r['usb_active'])
        self.assertTrue(self.rows['audio-start-error']['audio_created'])
        self.assertFalse(self.rows['audio-create-error']['audio_created'])

    def test_forced_fatal_callback_rejects_without_join_close_or_owner_access(self):
        for case in ('video-create-error','video-start-error','audio-create-error','audio-start-error'):
            r=self.rows[case];self.assertEqual((r['fatals'],r['exit_reason'],r['cleanup_phase']),(1,2,0))
            self.assertEqual((r['thread_closes'],r['joins'],r['callback_uvc'],r['core_exit_body']),(0,0,0,0))
            self.assertFalse(r['fatal_callback_reachability_verified'])
        r=self.rows['launch-ok'];self.assertEqual(r['fatals'],0);self.assertTrue(r['video_live']);self.assertTrue(r['audio_live'])

    def test_evidence_binding_models_and_offline_scope(self):
        self.assertEqual(self.result['case_count'],40);self.assertTrue(verify(self.output));self.assertTrue(verify(audit.SEALED))
        for n,h in self.result['production_sources_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.REPO/n),h)
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(audit.base.ep0.sha(audit.base.ep0.PRIVATE/'analysis'/n),h)
        for key in ('production_modified','prior_runtime_modified','new_arm_build','firmware_packaged','usb_accessed','sd_accessed',
                    'arm_executed','actual_threads_executed','actual_dma_executed','fatal_callback_reachability_verified',
                    'initialization_rollback_implemented','hardware_verified','root_cause_confirmed'):
            self.assertFalse(self.result[key])
        self.assertTrue(self.result['usb_descriptor_interface_iso_helpers_modeled'])
        self.assertEqual(list(self.output.rglob('*.elf')),[])

if __name__=='__main__':unittest.main()
