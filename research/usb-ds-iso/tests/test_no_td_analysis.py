"""Independent no-TD analysis must reject damaged or native-error evidence."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('no_td_analysis',ROOT/'tools/analyze_no_td_window.py')
analysis=importlib.util.module_from_spec(spec);spec.loader.exec_module(analysis)

class NoTdAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.run=Path(self.temp.name)
        source=ROOT/'private/host-A23-no-td-window/validation/0'
        if not source.exists():self.skipTest('build/validate no-TD receiver first')
        for name in ['host.jsonl','host.jsonl.seq0.buffer.bin']:shutil.copyfile(source/name,self.run/name)
        extra=[dict(kind='darwin_iso_schedule',configured_lead_frames=64,packets=960,interval=1,speed=3),
            dict(kind='darwin_iso_queue_timing',clock='CLOCK_MONOTONIC',queue_result=0,
                 frame_before_ns=1,frame_after_ns=2,queue_before_ns=3,queue_after_ns=4,callback_entry_ns=5)]
        self.native=''.join(json.dumps(r)+'\n' for r in extra)+(source/'native.txt').read_text()
        (self.run/'native-stderr.txt').write_text(self.native)
    def tearDown(self):self.temp.cleanup()
    def test_host_baseline_does_not_certify_full_log_or_stability(self):
        value=analysis.analyze(self.run);self.assertTrue(value['host_baseline_passed'])
        self.assertTrue(value['switch_log_pending']);self.assertFalse(value['strict_no_td_acceptance_passed'])
        self.assertFalse(value['stability_verified'])
    def test_native_error_retained(self):
        native=analysis.rows(self.run/'native-stderr.txt')
        for row in native:
            if row['kind']=='darwin_iso_native':row['overall']=0xe000400e
            if row.get('index')==0:row['status']=0xe000400e
        (self.run/'native-stderr.txt').write_text(''.join(json.dumps(r)+'\n' for r in native))
        value=analysis.analyze(self.run);self.assertFalse(value['host_baseline_passed'])
        self.assertTrue(value['native_anomaly']);self.assertEqual(value['initial_empty_not_sent_slots'],1)
    def test_missing_native_rejected(self):
        (self.run/'native-stderr.txt').write_text('\n'.join(self.native.splitlines()[:-1])+'\n')
        self.assertFalse(analysis.analyze(self.run)['host_baseline_passed'])
    def test_missing_timing_rejected(self):
        (self.run/'native-stderr.txt').write_text('\n'.join(self.native.splitlines()[2:])+'\n')
        self.assertFalse(analysis.analyze(self.run)['host_baseline_passed'])
    def test_nonzero_raw_rejected(self):
        (self.run/'host.jsonl.seq0.buffer.bin').write_bytes(b'X'+bytes(184319))
        self.assertFalse(analysis.analyze(self.run)['host_baseline_passed'])
    def test_device_change_rejected(self):
        host=analysis.rows(self.run/'host.jsonl')
        [r.update(sequence=1) for r in host if r['kind']=='device_status']
        (self.run/'host.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in host))
        self.assertFalse(analysis.analyze(self.run)['host_baseline_passed'])

if __name__=='__main__':unittest.main()
