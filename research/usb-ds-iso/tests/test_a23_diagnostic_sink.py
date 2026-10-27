"""Joined failure snapshots save once without granting cleanup; modeled FS only."""
import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build_a23_diagnostic_sink as sink
from workflows.artifacts import verify

class A23DiagnosticSinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=sink.run(cls.output)
        cls.rows={(r['mode'],r['case']):r for r in cls.result['cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def row(self,case,mode='adapter'):return self.rows[mode,case]

    def test_pending_snapshot_is_immutable_and_diagnostic_only(self):
        r=self.row('ok');self.assertTrue(r['ok']);self.assertEqual(r['pending'],1)
        self.assertFalse(r['diagnostic']['ownership_export_accepted']);self.assertFalse(r['diagnostic']['cleanup_authorized'])
        self.assertEqual(r['cleanup_phase'],0);self.assertEqual(r['uvc_closes'],0)

    def test_fault_snapshot_retains_permanent_denial(self):
        r=self.row('fault');self.assertTrue(r['ok']);self.assertEqual(r['fault'],1)
        self.assertTrue(r['diagnostic']['fault']);self.assertEqual(r['pending'],1)

    def test_both_join_failures_reject_before_any_storage_read_or_fs(self):
        for case in ('video-join-error','audio-join-error'):
            r=self.row(case);self.assertEqual(r['owner_reads'],0);self.assertEqual(r['fs_open'],0)
            self.assertEqual(r['diagnostic_bytes'],0);self.assertFalse(r['attempted'])

    def test_live_unstarted_unhanded_and_wrong_exporter_reject_without_fs(self):
        for case in ('live','unstarted','not-finished','wrong-exporter'):
            r=self.row(case);self.assertEqual(r['fs_open'],0);self.assertFalse(r['attempted'])
            self.assertEqual(r['diagnostic_bytes'],0)

    def test_healthy_normal_capture_is_not_saved_as_diagnostic(self):
        r=self.row('healthy');self.assertEqual(r['fs_open'],0);self.assertFalse(r['attempted'])
        r=self.row('healthy','shutdown');self.assertFalse(r['held']);self.assertEqual(r['joins'],2)
        self.assertEqual((r['thread_closes'],r['uvc_closes'],r['core_closes'],r['sm_closes']),(2,1,1,1))
        self.assertEqual(r['cleanup_phase'],4);self.assertEqual(r['create'],1)
        self.assertTrue(r['path'].endswith('.capture.bin'))

    def test_actual_shutdown_saves_then_retains_without_authorizing_cleanup(self):
        r=self.row('ok','shutdown');self.assertTrue(r['held']);self.assertTrue(r['commit_acknowledged'])
        self.assertEqual(r['joins'],2);self.assertEqual(r['cleanup_phase'],1);self.assertEqual(r['pending'],1)
        for key in ('thread_closes','uvc_closes','core_closes','sm_closes'):self.assertEqual(r[key],0)

    def test_failed_joins_exporter_and_unstarted_shutdown_never_save(self):
        for case in ('video-join-error','audio-join-error','exporter-error','unstarted','live'):
            r=self.row(case,'shutdown');self.assertTrue(r['held']);self.assertEqual(r['fs_open'],0)
            self.assertEqual(r['thread_closes'],0);self.assertEqual(r['diagnostic_bytes'],0)

    def test_unstarted_and_live_callbacks_cannot_claim_cleanup(self):
        for case in ('callback-live','callback-unstarted'):
            r=self.row(case,'shutdown');self.assertTrue(r['held']);self.assertEqual(r['cleanup_phase'],0)
            self.assertEqual((r['joins'],r['fs_open'],r['thread_closes'],r['uvc_closes']),(0,0,0,0))

    def test_full_6656_snapshot_passes_and_old_6640_limit_is_unchanged(self):
        r=self.row('maximum');self.assertTrue(r['ok']);self.assertEqual(r['diagnostic_bytes'],6656)
        self.assertEqual(len(r['diagnostic']['urbs']),16);self.assertEqual(r['diagnostic']['trace']['record_count'],128)
        self.assertTrue(self.result['limit_policy']['passed']);self.assertEqual(self.result['limit_policy']['cases'],4)
        self.assertTrue(self.result['limit_policy']['normal_limit_unchanged'])

    def test_create_open_and_collision_failures_do_not_retry_or_overwrite(self):
        for case in ('fs-open-error','create-error','collision','file-open-error'):
            r=self.row(case);self.assertFalse(r['ok']);self.assertTrue(r['attempted']);self.assertTrue(r['no_retry'])
            self.assertEqual(r['commit'],0)
        r=self.row('collision');path=self.output/'adapter-collision.diagnostic.bin.disk'
        self.assertEqual(path.read_bytes(),b'\x7a')
        self.assertEqual(r['create'],1);self.assertEqual(r['file_close'],0)

    def test_size_write_flush_and_read_failures_never_acknowledge_content(self):
        for case in ('write-error','silent-short-write','corrupt-write','flush-error','size-error','extra-byte',
                     'short-size','read-error','late-read-error','zero-read','oversize-read'):
            r=self.row(case);self.assertFalse(r['ok']);self.assertFalse(r['content_verified'])
            self.assertEqual((r['file_close'],r['fs_close'],r['commit']),(1,1,0))
        r=self.row('short-read');self.assertTrue(r['ok']);self.assertGreater(r['read'],3)

    def test_commit_failure_distinguishes_verified_bytes_and_acknowledgement(self):
        r=self.row('commit-error');self.assertFalse(r['ok']);self.assertTrue(r['content_verified'])
        self.assertFalse(r['commit_acknowledged']);self.assertEqual(r['phase'],8)
        self.assertEqual((self.output/'adapter-commit-error.diagnostic.bin.disk').read_bytes(),
                         (self.output/'adapter-commit-error.diagnostic.bin').read_bytes())
        r=self.row('commit-error','shutdown');self.assertTrue(r['held']);self.assertEqual(r['cleanup_phase'],1)

    def test_failure_of_normal_save_retains_without_diagnostic_fallback(self):
        r=self.row('normal-sink-error','shutdown');self.assertTrue(r['held']);self.assertFalse(r['attempted'])
        self.assertEqual(r['create'],1);self.assertTrue(r['path'].endswith('.capture.bin'));self.assertEqual(r['cleanup_phase'],1)

    def test_all_19_prior_diagnostics_roundtrip_with_their_original_recipe(self):
        self.assertEqual(self.result['roundtrip_count'],95)
        for r in self.result['roundtrips']:
            self.assertEqual(r['observation']['ok'],r['case'] in ('ok','short-read'))
            self.assertTrue(r['observation']['no_retry'])
        self.assertFalse(self.result['diagnostic_wire_modified']);self.assertFalse(self.result['admission_counters_in_diagnostic_wire'])

    def test_both_full_arm_elves_link_ten_objects_and_main_retains_after_save(self):
        a,b=(self.result['builds'][k] for k in ('dormant','window-30s'))
        self.assertNotEqual(a['runtime_recipe_digest'],b['runtime_recipe_digest'])
        for label,r in self.result['builds'].items():
            self.assertEqual(r['object_count'],10);self.assertTrue(r['linked']);self.assertFalse(r['executed'])
            main=(self.output/label/'source/sysmodule/main.c').read_text()
            block=main[main.index('    if(!Ep0CandidateFinish'):main.index('    // One save attempt')]
            self.assertIn('Ep0CandidateSaveDiagnostic',block);self.assertIn('for(;;)svcSleepThread',block)
            self.assertNotIn('ep0_cleanup_authorize',block)
            self.assertEqual((self.output/label/'source/uvc/uvc_device.c').read_bytes(),
                             (sink.SEALED/label/'source/uvc/uvc_device.c').read_bytes())

    def test_sealed_evidence_tickets_sources_and_offline_limits(self):
        self.assertTrue(verify(self.output));self.assertTrue(verify(sink.SEALED))
        self.assertEqual(self.result['source_audit'],sink.base.owner.source_audit())
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(sink.base.ep0.sha(sink.base.ep0.PRIVATE/'analysis'/n),h)
        self.assertEqual((self.result['adapter_case_count'],self.result['shutdown_case_count']),(27,14))
        self.assertTrue(self.result['diagnostic_sink_in_candidate']);self.assertFalse(self.result['diagnostic_authorizes_cleanup'])
        for key in ('production_modified','prior_runtime_modified','usb_accessed','sd_accessed','firmware_packaged',
                    'arm_executed','hardware_verified','root_cause_confirmed','actual_threads_executed','initialization_rollback_implemented'):
            self.assertFalse(self.result[key])
        with self.assertRaises(ValueError):sink.main_source('missing anchor')

if __name__=='__main__':unittest.main()
