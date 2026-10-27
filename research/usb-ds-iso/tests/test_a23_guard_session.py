"""Actual sealed video-loop replay and independently decoded diagnostic snapshots."""
from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest
import zlib
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_guard_session as audit
from analyze_ep0_diagnostic import decode_diagnostic
from analyze_ep0_candidate_capture import decode_capture
from workflows.artifacts import verify

def repair(data):
    b=bytearray(data);count=struct.unpack_from('<I',b,20)[0];offset=128+16*count
    struct.pack_into('<I',b,84,zlib.crc32(b[128:offset]));struct.pack_into('<I',b,88,zlib.crc32(b[offset:]))
    struct.pack_into('<I',b,92,0);struct.pack_into('<I',b,92,zlib.crc32(b[:128]));return b

class A23GuardSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name);cls.result=audit.run(cls.output)
        cls.rows={r['case']:r for r in cls.result['cases']}
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def diagnostic(self,case):return (self.output/(case+'.diagnostic.bin')).read_bytes()

    def test_all_28_video_function_replays_avoid_control_copy_and_repost(self):
        self.assertEqual(self.result['case_count'],28)
        for r in self.rows.values():
            self.assertEqual(r['copy_overlaps'],0);self.assertEqual(r['reposts'],0)
            self.assertEqual(r['processing'],0);self.assertLessEqual(r['used'],16)

    def test_complete_sequence_has_six_terminal_ids_and_66_records(self):
        r=self.rows['complete'];self.assertEqual((r['used'],r['records'],r['dropped']),(6,66,0))
        self.assertTrue(r['normal_export']);self.assertEqual(r['diagnostic_bytes'],0)
        self.assertEqual([u['channel'] for u in r['ownership']['urbs']],[4,5,8,4,4,5])
        paths=[g['path'] for g in r['ownership']['trace']['requests'] if g['interface']==2]
        self.assertEqual(paths,['iso_status','iso_post_and_ack_returned','iso_status'])

    def test_trace_budget_is_exhausted_at_six_status_requests_before_slots(self):
        a,b=(self.rows[c] for c in ('statuses-5','statuses-6'))
        self.assertEqual((a['used'],a['records'],a['dropped']),(10,115,0))
        self.assertEqual((b['used'],b['records'],b['dropped']),(12,128,10))
        self.assertTrue(b['normal_export']);self.assertTrue(b['diagnostic']['diagnostic_only'])

    def test_ninth_status_is_rejected_before_data_or_status_post(self):
        a,b=(self.rows[c] for c in ('statuses-8','statuses-9'))
        self.assertEqual((a['used'],a['in_posts'],a['out_posts']),(16,8,8))
        self.assertEqual((b['used'],b['in_posts'],b['out_posts']),(16,8,8))
        self.assertEqual((b['guard_reason'],b['pending']),(4,0));self.assertFalse(b['normal_export'])

    def test_complete_session_plus_status_budget_is_two_lossless_extras(self):
        a,b,c,d=(self.rows['session-extra-'+str(n)] for n in (2,3,5,6))
        self.assertEqual((a['used'],a['records'],a['dropped']),(10,112,0))
        self.assertEqual((b['used'],b['dropped']),(12,7))
        self.assertEqual(c['used'],16);self.assertTrue(c['normal_export'])
        self.assertEqual(d['used'],16);self.assertEqual(d['guard_reason'],4);self.assertFalse(d['normal_export'])

    def test_ack_timeout_stops_on_after_status_without_new_control_report(self):
        for case in ('ack-timeout','late-ack-report'):
            r=self.rows[case];self.assertEqual((r['used'],r['pending'],r['fault']),(4,1,1))
            self.assertEqual((r['in_posts'],r['out_posts'],r['ctrl_reports']),(2,1,2))
            self.assertEqual(r['guard_reason'],6);self.assertTrue(r['stopped']);self.assertFalse(r['normal_export'])
        self.assertEqual(self.diagnostic('ack-timeout'),self.diagnostic('late-ack-report'))

    def test_prestatus_timeout_can_post_iso_before_ack_buffer_denial(self):
        r=self.rows['prestatus-timeout'];self.assertEqual((r['iso_posts'],r['sequence']),(1,1))
        self.assertEqual((r['used'],r['pending'],r['in_posts']),(2,2,1))
        self.assertEqual(r['guard_reason'],6);self.assertFalse(r['normal_export'])

    def test_stop_inside_wait_is_deferred_until_owner_returns(self):
        r=self.rows['stop-inside-wait'];self.assertTrue(r['early_stop_attempted']);self.assertFalse(r['early_stop_accepted'])
        self.assertEqual(r['dispatches'],2);self.assertEqual((r['pending'],r['stopped'],r['joined']),(1,1,1))
        self.assertFalse(r['normal_export']);self.assertGreater(r['diagnostic_bytes'],0)

    def test_failed_joins_have_no_takeover_or_diagnostic(self):
        for case in ('video-join-error','audio-join-error'):
            r=self.rows[case];self.assertEqual(r['joined'],0);self.assertFalse(r['normal_export'])
            self.assertEqual(r['diagnostic_bytes'],0)
        self.assertTrue(self.result['diagnostic_policy']['failed_join_rejected_before_read'])

    def test_unstarted_owner_is_distinct_from_empty_stopped_owner(self):
        for case in ('identity-error','zero-nonce'):
            r=self.rows[case];self.assertEqual((r['dispatches'],r['stopped'],r['joined']),(0,0,0))
            self.assertFalse(r['normal_export']);self.assertEqual(r['diagnostic_bytes'],0)
        for case in ('ready-stop','window-wait'):
            r=self.rows[case];self.assertEqual((r['dispatches'],r['stopped'],r['joined']),(0,1,1))
            self.assertTrue(r['normal_export']);self.assertEqual(r['ownership']['trace']['record_count'],0)

    def test_diagnostics_preserve_unknowns_and_never_authorize_cleanup(self):
        self.assertEqual(self.result['diagnostic_count'],19)
        for r in self.rows.values():
            if 'diagnostic' not in r:continue
            d=r['diagnostic'];self.assertTrue(d['simulation']);self.assertTrue(d['diagnostic_only'])
            self.assertEqual((d['pending'],d['fault'],d['guard_denials']),(r['pending'],bool(r['fault']),r['guard_denials']))
            self.assertFalse(d['ownership_export_accepted']);self.assertFalse(d['cleanup_authorized'])
            self.assertFalse(d['join_results_authenticated'])
        self.assertTrue(self.result['diagnostic_policy']['owner_immutable'])
        self.assertTrue(self.result['diagnostic_policy']['output_alias_rejected'])

    def test_diagnostic_crc_protects_header_ledger_and_trace(self):
        data=self.diagnostic('ack-timeout');offset=128+16*self.rows['ack-timeout']['used']
        for index in (100,132,offset+128):
            b=bytearray(data);b[index]^=1
            with self.assertRaises(ValueError):decode_diagnostic(b)
        with self.assertRaises(ValueError):decode_diagnostic(data[:-1])
        with self.assertRaises(ValueError):decode_diagnostic(data,'00'*32)

    def test_diagnostic_semantic_tampering_is_rejected_even_with_new_crcs(self):
        data=self.diagnostic('ack-timeout')
        for offset,value in ((16,1),(24,0),(28,0),(108,1),(112,1),(116,2),(120,1)):
            b=bytearray(data);struct.pack_into('<I',b,offset,value)
            with self.assertRaises(ValueError):decode_diagnostic(repair(b))
        b=bytearray(data);b[128+3*16+1]=0
        with self.assertRaises(ValueError):decode_diagnostic(repair(b))
        b=bytearray(data);b[128+3*16:128+4*16]=b[128:144]
        with self.assertRaises(ValueError):decode_diagnostic(repair(b))

    def test_clean_snapshot_cannot_be_promoted_to_diagnostic_or_safe_capture(self):
        b=bytearray(self.diagnostic('iso-pending'));struct.pack_into('<I',b,28,0)
        for i in range(self.rows['iso-pending']['used']):
            b[128+i*16+1]=0;struct.pack_into('<I',b,128+i*16+8,3)
        with self.assertRaises(ValueError):decode_diagnostic(repair(b))
        for name in ('iso-pending','statuses-6'):
            with self.assertRaises(ValueError):decode_capture(self.diagnostic(name))

    def test_trace_loss_is_reported_even_when_existing_ownership_export_allows(self):
        r=self.rows['trace-overflow'];self.assertTrue(r['normal_export']);self.assertEqual(r['dropped'],138)
        self.assertEqual(r['ownership']['trace']['dropped_records'],138)
        self.assertEqual(r['diagnostic']['trace']['dropped_records'],138)
        self.assertTrue(self.result['diagnostic_policy']['short_output_untouched'])

    def test_sealed_inputs_and_offline_boundaries_remain_unchanged(self):
        self.assertTrue(verify(self.output));self.assertTrue(verify(audit.SEALED))
        self.assertEqual(self.result['source_audit'],audit.base.owner.source_audit())
        for n,h in self.result['tickets_sha256'].items():self.assertEqual(h,audit.base.ep0.sha(audit.base.ep0.PRIVATE/'analysis'/n))
        for key in ('usb_accessed','sd_accessed','production_modified','prior_runtime_modified','firmware_packaged',
                    'new_full_arm_elf_built','arm_executed','hardware_verified','root_cause_confirmed',
                    'actual_threads_executed','diagnostic_sink_in_candidate','diagnostic_authorizes_cleanup'):
            self.assertFalse(self.result[key])
        self.assertEqual(list(self.output.rglob('*.elf')),[]);self.assertEqual(list(self.output.rglob('*.nso')),[])

if __name__=='__main__':unittest.main()
