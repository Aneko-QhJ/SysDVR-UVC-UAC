"""Actual A23 handler hooks, source-result parity and isolated full ELF builds."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_a23_trace_candidate as candidate
from analyze_ep0_candidate_capture import decode_capture
from analyze_ep0_trace import decode


def checksums(data):
    data=bytearray(data);count=struct.unpack_from('<I',data,20)[0];offset=112+count*16
    struct.pack_into('<I',data,84,zlib.crc32(data[112:offset]))
    struct.pack_into('<I',data,88,zlib.crc32(data[offset:]))
    data[92:96]=bytes(4);struct.pack_into('<I',data,92,zlib.crc32(data[:112]))
    return bytes(data)


class A23TraceCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name)
        cls.result=candidate.run(cls.output)
        cls.rows={(r['family'],r['case']):r for r in cls.result['source_replays']}

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def row(self,case,family='owner'):return self.rows[(family,case)]
    def capture(self,case):return Path(str(self.output/self.row(case)['trace'])+'.capture.bin').read_bytes()
    def analysis(self,case):return decode_capture(self.capture(case),self.result['recipe_digest'])

    def test_all_48_actual_source_replays_preserve_usb_results_and_service_counts(self):
        self.assertEqual(len(self.rows),48)
        self.assertTrue(all(r['baseline_identical'] for r in self.rows.values()))
        for r in self.rows.values():
            path=self.output/r['trace'];baseline=Path(str(path).replace('-candidate-','-baseline-')+'.owner.json')
            self.assertEqual(r['owner']['services'],json.loads(baseline.read_text())['services'])

    def test_full_original_and_candidate_link_include_runtime_patch_without_execution(self):
        self.assertEqual(self.result['builds']['baseline']['object_count'],5)
        self.assertEqual(self.result['builds']['candidate']['object_count'],6)
        self.assertEqual(self.result['runtime_payload_records'],22)
        for r in self.result['builds'].values():self.assertTrue(r['linked']);self.assertFalse(r['executed'])
        for key in ('production_modified','firmware_packaged','usb_accessed','sd_accessed','hardware_verified','root_cause_confirmed'):
            self.assertFalse(self.result[key])

    def test_complete_status_burst_status_does_not_imply_iso_drained(self):
        kept=self.row('session-kept','session')['owner'];covered=self.row('session-replaced','session')['owner']
        self.assertEqual(kept['used'],6);self.assertEqual(kept['pending'],1);self.assertFalse(kept['export_allowed'])
        self.assertEqual(covered['used'],4);self.assertEqual(covered['pending'],0);self.assertTrue(covered['export_allowed'])

    def test_unobserved_pending_or_retained_iso_is_fail_closed(self):
        for case in ('pending','retained'):
            r=self.row(case,'dispatch')['owner'];self.assertEqual(r['fault'],1)
            self.assertFalse(r['export_allowed'])

    def test_terminal_failure_releases_own_id_but_does_not_claim_transfer_success(self):
        for case in ('iso-terminal-4','iso-terminal-5','ctrl-terminal-4','ctrl-terminal-5'):
            r=self.row(case)['owner'];self.assertEqual(r['pending'],0);self.assertTrue(r['export_allowed'])
            a=self.analysis(case);self.assertTrue(any(u['status'] in (4,5) for u in a['urbs']))
            self.assertFalse(a['hardware_verified']);self.assertFalse(a['runtime_ownership_authenticated'])
        # A later EXISTING IN report can contain both the timed-out ACK's ID
        # and the current STATUS's ID. No extra GetReportData call is injected.
        r=self.row('ctrl-late-terminal')['owner'];self.assertEqual(r['pending'],0)
        self.assertTrue(r['export_allowed'])
        self.assertTrue(any(x['stage']=='ctrl_wait' and x['result_u32']==94
                            for x in self.analysis('ctrl-late-terminal')['trace']['records']))

    def test_bad_batches_and_uncertain_posts_cannot_be_blessed_by_idle_status(self):
        for case in ('iso-count-9','iso-duplicate','ctrl-duplicate','failed-post'):
            r=self.row(case)['owner'];self.assertEqual(r['fault'],1);self.assertFalse(r['export_allowed'])
        self.assertEqual(self.row('failed-post')['owner']['pending'],0) # Sticky fault still blocks.

    def test_timeouts_failed_reports_wrong_ids_and_nonterminal_statuses_keep_buffers(self):
        for case in ('iso-pending','iso-wrong-id','iso-state-1','iso-state-2','iso-report-error',
                     'ctrl-timeout','ctrl-report-error','ctrl-wrong-id','ctrl-unknown-status'):
            r=self.row(case)['owner'];self.assertGreater(r['pending'],0);self.assertFalse(r['export_allowed'])

    def test_stop_inside_actual_helper_wait_cannot_freeze_and_failed_join_cannot_export(self):
        r=self.row('stop-inside-wait')['owner']
        self.assertTrue(r['early_stop_attempted']);self.assertFalse(r['early_stop_accepted'])
        self.assertFalse(r['export_allowed'])
        r=self.row('join-error')['owner'];self.assertEqual(r['pending'],0)
        self.assertFalse(r['injected_join_success']);self.assertFalse(r['export_allowed'])
        main=(self.output/'candidate/source/sysmodule/main.c').read_text()
        self.assertIn('static atomic_bool g_running',main)
        self.assertLess(main.index('!Ep0CandidateFinish'),main.index('threadClose(&g_videoThread)'))

    def test_trace_overflow_remains_exportable_only_with_independent_drained_ledger(self):
        self.assertTrue(self.row('trace-overflow')['owner']['export_allowed'])
        trace=self.analysis('trace-overflow')['trace'];self.assertGreater(trace['dropped_records'],0)
        self.assertFalse(trace['trace_window_complete'])
        r=self.row('capacity-storm')['owner'];self.assertEqual(r['used'],16)
        self.assertEqual(r['fault'],1);self.assertFalse(r['export_allowed'])

    def test_capture_all_truncations_extra_bytes_crcs_and_recipe_mismatch_are_rejected(self):
        data=self.capture('drained')
        for n in range(len(data)):
            with self.assertRaises(ValueError):decode_capture(data[:n])
        with self.assertRaises(ValueError):decode_capture(data+b'\0')
        with self.assertRaisesRegex(ValueError,'recipe digest mismatch'):decode_capture(data,'0'*64)
        for n in (16,48,84,92,112,len(data)-1):
            b=bytearray(data);b[n]^=1
            with self.assertRaises(ValueError):decode_capture(b)

    def test_recomputed_crc_cannot_relabel_or_forge_inconsistent_ledger(self):
        data=self.capture('drained')
        for offset,fmt,value in ((16,'I',0),(24,'I',1),(28,'I',1),(40,'Q',11),
                                 (100,'I',1),(112,'B',9),(113,'B',1),(114,'H',1),
                                 (116,'I',999),(120,'I',1),(124,'I',1)):
            with self.subTest(offset=offset):
                b=bytearray(data);struct.pack_into('<'+fmt,b,offset,value)
                with self.assertRaises(ValueError):decode_capture(checksums(b))
        # Repeat the first IN post ID on the later IN helper, keeping every CRC
        # valid. A set-only comparison would silently hide this impossible reuse.
        count=struct.unpack_from('<I',data,20)[0];offset=112+count*16
        trace=decode(data[offset:]);posts=[r for r in trace['records'] if r['stage']=='ctrl_post' and r['direction']=='in']
        b=bytearray(data);position=offset+128+(posts[1]['ordinal']-1)*48+32
        struct.pack_into('<I',b,position,posts[0]['arg1'])
        inner=bytearray(b[offset:]);struct.pack_into('<I',inner,96,zlib.crc32(inner[128:]))
        inner[100:104]=bytes(4);struct.pack_into('<I',inner,100,zlib.crc32(inner[:128]));b[offset:]=inner
        with self.assertRaisesRegex(ValueError,'reused observed post identity'):decode_capture(checksums(b))
        a=self.analysis('drained');self.assertTrue(a['recipe_correlated'])
        self.assertFalse(a['source_authenticated']);self.assertFalse(a['runtime_ownership_authenticated'])

    def test_unique_source_anchors_fail_on_drift_and_payload_has_no_firmware_packaging(self):
        source=candidate.poll_source()+'\n'+candidate.ep0.actual_source()
        with self.assertRaises(ValueError):candidate.integrate(source.replace('GetCtrlInReportData','MissingReport',1))
        self.assertEqual(list(self.output.rglob('*.nso')),[])
        self.assertEqual(list(self.output.rglob('*.nsp')),[])
        for r in self.rows.values():
            p=self.output/r['trace'];self.assertFalse(decode(p.read_bytes())['trace_window_complete'])


if __name__=='__main__':unittest.main()
