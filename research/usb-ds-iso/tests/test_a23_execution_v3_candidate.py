"""Isolated execution checks; no receiver invocation, USB or SD access."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_a23_execution_v3_candidate as candidate
from analyze_ep0_execution_v3 import decode_execution
from analyze_ep0_session_v2 import decode_session
from workflows.artifacts import verify


class ExecutionV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name)/'candidate'
        cls.result=candidate.run(cls.output,arm=False)
        cls.rows={(r['kind'],r['primary_fault'],r['execution_fault']):r for r in cls.result['lifecycle_cases']}

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def envelope(self,kind='normal',primary='ok',execution='ok'):
        return self.output/f'{kind}-primary-{primary}-execution-{execution}.execution.bin'

    def test_expired_idle_and_capture_never_start_another_process(self):
        rows=self.result['window_cases']
        for row in rows.values():self.assertEqual(row['process_calls_started_after_expiry'],0)
        self.assertEqual(rows['idle_sleep_crosses_deadline']['process_calls'],1)
        self.assertEqual(rows['idle_sleep_crosses_deadline']['elapsed_ms'],30041)
        self.assertEqual(rows['capture_returns_late']['process_calls'],1)
        self.assertEqual(rows['capture_returns_late']['elapsed_ms'],46017)

    def test_inflight_synchronous_wait_still_has_no_interrupt(self):
        self.assertEqual(self.result['window_cases']['process_returns_late']['elapsed_ms'],46000)
        self.assertEqual(self.result['window_cases']['ready_returns_late']['elapsed_ms'],45000)
        self.assertEqual(self.result['dormant_window_cases']['explicit_stop']['process_calls'],3)

    def test_normal_and_diagnostic_both_save_association(self):
        for kind in ('normal','diagnostic'):
            row=self.rows[kind,'ok','ok']
            self.assertTrue(row['execution_save_acknowledged'])
            decoded=decode_execution(self.envelope(kind).read_bytes(),'03'+'00'*31)
            self.assertEqual(decoded['primary_kind'],'ownership' if kind=='normal' else 'diagnostic')
            self.assertIsNotNone(decoded['startup'])
            self.assertEqual(decoded['window']['start_tick'],2)
            self.assertEqual(decoded['window']['ready_tick'],4)
            self.assertEqual(decoded['window']['stop_tick'],10)
            self.assertFalse(decoded['cleanup_authorized'])

    def test_all_primary_file_failures_keep_failed_receipt_and_bytes(self):
        for kind in ('normal','diagnostic'):
            for fault in candidate.capacity.FILE_CASES:
                row=self.rows[kind,fault,'ok']
                self.assertTrue(row['execution_save_acknowledged'],(kind,fault))
                decoded=decode_execution(self.envelope(kind,fault).read_bytes(),'03'+'00'*31)
                good=fault in ('ok','short-read')
                self.assertEqual(decoded['primary_receipt']['save_return_value'],good)
                if not good:self.assertTrue(row['retained'])
                self.assertTrue(decoded['primary_receipt']['save_returned'])

    def test_commit_failure_is_not_relabelled_success(self):
        for kind in ('normal','diagnostic'):
            decoded=decode_execution(self.envelope(kind,'commit-error').read_bytes(),'03'+'00'*31)
            self.assertTrue(decoded['primary_receipt']['content_verified'])
            self.assertFalse(decoded['primary_receipt']['commit_acknowledged'])
            self.assertEqual(decoded['primary_receipt']['result'],98)

    def test_sidecar_failure_prevents_normal_cleanup(self):
        for kind in ('normal','diagnostic'):
            for fault in candidate.capacity.FILE_CASES:
                row=self.rows[kind,'ok',fault]
                good=fault in ('ok','short-read')
                self.assertEqual(row['execution_save_acknowledged'],good)
                self.assertEqual(row['thread_closes'],2 if kind=='normal' and good else 0)
            row=self.rows[kind,'ok','commit-error']
            self.assertTrue(row['execution_content_verified'])
            self.assertFalse(row['execution_save_acknowledged'])

    def test_failed_joins_and_identity_never_open_files(self):
        for kind in ('normal','diagnostic'):
            for fault in ('video-join-error','audio-join-error','identity-error'):
                row=self.rows[kind,fault,'ok']
                self.assertEqual((row['fs_open'],row['execution_bytes'],row['thread_closes']),(0,0,0))
                self.assertTrue(row['retained'])

    def test_crc_recipe_and_reserved_corruption_rejected(self):
        data=self.envelope().read_bytes()
        for offset in (0,184,255,len(data)-1):
            changed=bytearray(data);changed[offset]^=1
            with self.assertRaises(ValueError):decode_execution(changed,'03'+'00'*31)
        with self.assertRaises(ValueError):decode_execution(data,'04'+'00'*31)
        changed=bytearray(data);struct.pack_into('<Q',changed,64,0)
        struct.pack_into('<I',changed,184,0);struct.pack_into('<I',changed,184,zlib.crc32(changed[:256]))
        # Trace starts at tick 0, so a different non-negative start is permitted;
        # move it beyond the frozen boundary to test a real clock contradiction.
        struct.pack_into('<Q',changed,64,11);struct.pack_into('<I',changed,184,0)
        struct.pack_into('<I',changed,184,zlib.crc32(changed[:256]))
        with self.assertRaises(ValueError):decode_execution(changed,'03'+'00'*31)

    def test_repaired_outer_crc_cannot_hide_receipt_or_expiry_contradictions(self):
        data=self.envelope().read_bytes()
        for offset,value in ((44,0),(92,1),(20,2),(192,3)):
            changed=bytearray(data);struct.pack_into('<I',changed,offset,value)
            struct.pack_into('<I',changed,184,0);struct.pack_into('<I',changed,184,zlib.crc32(changed[:256]))
            with self.assertRaises(ValueError):decode_execution(changed,'03'+'00'*31)

    def test_partial_disks_rejected_but_complete_failed_commit_stays_unacknowledged(self):
        for kind in ('normal','diagnostic'):
            for fault in ('write-error','silent-short-write','corrupt-write'):
                p=self.output/f'{kind}-primary-ok-execution-{fault}.execution.disk.bin'
                with self.assertRaises(ValueError):decode_execution(p.read_bytes(),'03'+'00'*31)
            p=self.output/f'{kind}-primary-ok-execution-commit-error.execution.disk.bin'
            decoded=decode_execution(p.read_bytes(),'03'+'00'*31)
            self.assertFalse(decoded['envelope_own_commit_authenticated'])
            self.assertFalse(self.rows[kind,'ok','commit-error']['execution_save_acknowledged'])

    def test_formats_do_not_fall_back_to_old_session_parser(self):
        with self.assertRaises(ValueError):decode_session(self.envelope().read_bytes(),'03'+'00'*31)
        with self.assertRaises(ValueError):decode_execution((candidate.SEALED/'maximum.session.bin').read_bytes())

    def test_sealed_inputs_production_and_tickets_preserved(self):
        self.assertTrue(verify(self.output)['sha256_verified'])
        for group,base in ((self.result['production_sources_sha256'],candidate.REPO),
                           (self.result['tickets_sha256'],candidate.SEALED.parent)):
            for name,expected in group.items():self.assertEqual(candidate.capacity.ready.sha(base/name),expected)
        self.assertEqual(len(self.rows),76)
        self.assertEqual(self.result['native_execution_count'],87)
        with self.assertRaises(ValueError):candidate.run(self.output,arm=False)

    def test_passive_wait_core_is_compiled_and_single_handoff(self):
        wait=self.result['passive_wait_policy']
        self.assertEqual(wait['policy_cases'],447)
        self.assertEqual(wait['maximum_handoffs'],1)
        self.assertFalse(wait['native_iokit_adapter_implemented'])
        self.assertEqual((wait['usb_requests'],wait['ticket_mutations']),(0,0))


if __name__=='__main__':unittest.main()
