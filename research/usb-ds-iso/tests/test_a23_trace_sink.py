"""Offline one-shot adapter failures and local-window arithmetic."""
import sys
import shutil
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_a23_trace_sink as sink
from analyze_ep0_candidate_capture import decode_capture

class A23TraceSinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name)
        cls.result=sink.run(cls.output)
        cls.rows={r['case']:r['observation'] for r in cls.result['adapter_cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_unknown_ownership_failed_join_or_missing_finish_reaches_no_fs(self):
        for case in ('not-finished','pending','fault','join-error'):
            r=self.rows[case];self.assertFalse(r['ok']);self.assertFalse(r['attempted'])
            for key in ('fs_open','create','write','read','commit','fs_close'):self.assertEqual(r[key],0)
            self.assertFalse((self.output/(case+'.capture.bin')).exists())

    def test_all_io_errors_retain_attempt_and_immutable_memory_without_retry(self):
        for case in sink.CASES:
            r=self.rows[case];self.assertTrue(r['immutable_capture']);self.assertTrue(r['no_retry'])
            self.assertEqual(r['ok'],case in ('ok','short-read'))
            if case not in ('not-finished','pending','fault','join-error'):
                self.assertTrue(r['attempted']);self.assertEqual(r['fs_close'],0 if case=='fs-open-error' else 1)
            if r['write']:self.assertEqual(r['close'],1)
            if case not in ('ok','short-read','commit-error'):self.assertEqual(r['commit'],0)
        r=self.rows['file-open-error'];self.assertTrue(r['file_may_exist']);self.assertEqual(r['close'],0)

    def test_create_failure_never_writes_or_overwrites_existing_contents(self):
        for case in ('collision','create-error'):
            r=self.rows[case];self.assertEqual(r['create'],1);self.assertEqual(r['write'],0)
            self.assertEqual((self.output/(case+'.capture.bin')).read_bytes(),b'z')
            self.assertTrue(r['file_may_exist']);self.assertEqual(r['commit'],0)

    def test_successful_short_write_or_corruption_is_detected_before_commit(self):
        for case in ('silent-short-write','corrupt-write'):
            r=self.rows[case];self.assertEqual(r['result'],0);self.assertEqual(r['phase'],7)
            self.assertFalse(r['content_verified']);self.assertEqual(r['commit'],0)
            with self.assertRaises(ValueError):decode_capture((self.output/(case+'.capture.bin')).read_bytes())
        for case in ('extra-byte','short-size','zero-read','oversize-read'):
            self.assertFalse(self.rows[case]['content_verified']);self.assertEqual(self.rows[case]['commit'],0)

    def test_short_reads_progress_and_commit_error_is_not_durable_success(self):
        self.assertGreater(self.rows['short-read']['read'],1)
        for case in ('ok','short-read','commit-error'):
            r=self.rows[case];self.assertTrue(r['content_verified']);self.assertEqual(r['verified_bytes'],r['capture_size'])
            self.assertEqual(r['commit'],1);decode_capture((self.output/(case+'.capture.bin')).read_bytes())
        r=self.rows['commit-error'];self.assertFalse(r['ok']);self.assertFalse(r['commit_acknowledged'])
        self.assertFalse(self.result['durable_after_power_loss_verified'])

    def test_16_sealed_captures_roundtrip_and_late_read_failure_retains_partial_verification(self):
        rows=self.result['roundtrips'];self.assertEqual(len(rows),80);self.assertEqual(len({r['source'] for r in rows}),16)
        for r in rows:
            o=r['observation'];self.assertTrue(o['no_retry']);self.assertTrue(o['debug_sink_input'])
            if r['case']=='late-read-error':
                self.assertFalse(o['ok']);self.assertEqual(o['verified_bytes'],256)
                self.assertEqual(o['commit'],0);self.assertEqual(o['read'],2)
            elif r['case']=='silent-short-write':self.assertFalse(o['ok']);self.assertEqual(o['commit'],0)
            elif r['case']=='commit-error':self.assertTrue(o['content_verified']);self.assertFalse(o['commit_acknowledged'])

    def test_window_arithmetic_and_unique_configuration(self):
        self.assertTrue(all(r['window_cases']==11 for r in self.rows.values()))
        dormant=self.result['builds']['dormant'];sample=self.result['builds']['window-30s']
        self.assertEqual(dormant['window_ms'],0);self.assertEqual(sample['window_ms'],30000)
        self.assertNotEqual(dormant['runtime_recipe_digest'],sample['runtime_recipe_digest'])
        self.assertFalse(self.result['window_stop_latency_bounded'])
        for label in ('dormant','window-30s'):
            s=(self.output/label/'source/sysmodule/main.c').read_text()
            self.assertEqual(s.count('if(ep0_window_expired(&window,svcGetSystemTick()))'),2)
            self.assertLess(s.index('!Ep0CandidateFinish'),s.index('!Ep0CandidateSaveCapture'))
            self.assertLess(s.index('!Ep0CandidateSaveCapture'),s.index('threadClose(&g_videoThread)'))
        with self.assertRaises(ValueError):sink.main_source('',1)
        with self.assertRaises(ValueError):sink.main_source('',0)

    def test_complete_file_adapter_links_in_both_unexecuted_elfs(self):
        for b in self.result['builds'].values():
            self.assertEqual(b['object_count'],7);self.assertTrue(b['linked']);self.assertFalse(b['executed'])
        for key in ('usb_accessed','sd_accessed','production_modified','firmware_packaged','hardware_verified','root_cause_confirmed'):
            self.assertFalse(self.result[key])
        self.assertEqual(list(self.output.rglob('*.nso')),[]);self.assertEqual(list(self.output.rglob('*.nsp')),[])

    def test_native_runtime_drift_from_sealed_arm_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            for name in sink.base.DEVICE:shutil.copyfile(ROOT/'device'/name,path/name)
            sink.validate_runtime(path)
            file=path/'ep0_candidate.c';file.write_text(file.read_text()+'\n/* drift */\n')
            with self.assertRaisesRegex(ValueError,'runtime differ'):sink.validate_runtime(path)

if __name__=='__main__':unittest.main()
