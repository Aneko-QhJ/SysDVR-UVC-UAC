"""Reject damaged/relabelled traces and distinguish real-source failure branches."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from analyze_ep0_trace import decode
import probe_a23_ep0_trace as probe


def checksums(data):
    data=bytearray(data)
    struct.pack_into('<I',data,96,zlib.crc32(data[128:]))
    data[100:104]=bytes(4);struct.pack_into('<I',data,100,zlib.crc32(data[:128]))
    return bytes(data)


class Ep0TraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.output=Path(cls.tmp.name)
        cls.result=probe.run_probe(cls.output)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def trace(self,family,case):return (self.output/(family+'-'+case+'.bin')).read_bytes()
    def analysis(self,family,case):return decode(self.trace(family,case))

    def test_source_results_preserved_and_arm_core_compiles(self):
        self.assertEqual(self.result['instrumented_case_count'],25)
        self.assertTrue(all(r['baseline_identical'] for r in self.result['instrumented_cases']))
        self.assertTrue(self.result['aarch64_core_compile_pass'])
        self.assertFalse(self.result['production_trace_integrated'])

    def test_full_status_burst_status_windows_fit_capacity_and_keep_order(self):
        for case,paths in [('session-kept',['iso_status','iso_post_and_ack_returned','iso_status']),
                           ('session-replaced',['iso_status','iso_status'])]:
            with self.subTest(case=case):
                result=self.analysis('session',case)
                self.assertEqual([r['path'] for r in result['requests'] if r['interface']==2],paths)
                self.assertLess(result['record_count'],128)
                self.assertTrue(result['trace_window_complete'])
                self.assertEqual(result['dropped_records'],0)

    def test_shared_replacement_records_actual_setup_and_no_post(self):
        changed=self.analysis('shared','32ms-replaced')
        self.assertTrue(changed['mixed_first_interface_setup'])
        iso=[r for r in changed['requests'] if r['interface']==2]
        self.assertEqual([r['path'] for r in iso],['iso_status'])
        self.assertTrue(iso[0]['setup_hex'].startswith('c151'))
        self.assertFalse(any(r['stage']=='iso_post' for r in changed['records']))
        kept=self.analysis('shared','32ms-delayed-arrival')
        self.assertFalse(kept['mixed_first_interface_setup'])
        self.assertEqual([r['path'] for r in kept['requests'] if r['interface']==2],
                         ['iso_post_and_ack_returned','iso_status'])

    def test_speed_post_and_ack_failures_remain_distinct(self):
        speed=self.analysis('dispatch','speed-error')
        row=next(r for r in speed['records'] if r['stage']=='speed')
        self.assertEqual(row['result_u32'],97);self.assertIsNone(row['arg0'])
        self.assertFalse(any(r['stage']=='sequence' for r in speed['records']))
        post=self.analysis('dispatch','post-failed')
        row=next(r for r in post['records'] if r['stage']=='iso_post')
        self.assertEqual(row['result_u32'],96);self.assertIsNone(row['arg1'])
        ack=self.analysis('dispatch','ack-timeout')
        wait=next(r for r in ack['records'] if r['stage']=='ctrl_wait')
        self.assertEqual(wait['result_u32'],94);self.assertEqual(wait['duration_ms'],1000)
        self.assertEqual([r['path'] for r in ack['requests'] if r['interface']==2],['iso_post_then_ack_failed'])
        self.assertTrue(any(r['stage']=='sequence' and r['arg0']==1 for r in ack['records']))

    def test_failed_setup_has_no_uninitialized_bytes_and_quiet_poll_is_absent(self):
        failed=self.analysis('dispatch','get-setup-failed')
        row=next(r for r in failed['records'] if r['stage']=='setup_read' and r['interface']==2)
        self.assertEqual(row['result_u32'],98);self.assertIsNone(row['setup_hex'])
        quiet=self.analysis('dispatch','no-iso-event')
        self.assertFalse(any(r['interface']==2 for r in quiet['records']))
        self.assertGreater(quiet['poll_snapshots'][2]['poll_count'],0)
        self.assertEqual(quiet['poll_snapshots'][2]['last_result_u32'],1)
        self.assertFalse(quiet['root_cause_confirmed'])

    def test_overflow_preserves_prefix_but_cannot_claim_complete_window(self):
        overflow=decode((self.output/'overflow.bin').read_bytes())
        self.assertEqual(overflow['record_count'],128)
        self.assertEqual(overflow['dropped_records'],0xffffffff)
        self.assertEqual(overflow['invalid_records'],0xffffffff)
        self.assertEqual([r['end_ticks'] for r in overflow['records']],list(range(128)))
        self.assertFalse(overflow['trace_window_complete'])

    def test_all_truncations_extra_bytes_and_crc_corruption_are_rejected(self):
        data=self.trace('dispatch','normal')
        for cut in range(len(data)):
            with self.assertRaises(ValueError):decode(data[:cut])
        with self.assertRaises(ValueError):decode(data+b'\0')
        for offset in (16,64,96,100,128,len(data)-1):
            changed=bytearray(data);changed[offset]^=1
            with self.assertRaises(ValueError):decode(changed)

    def test_recomputed_crc_does_not_allow_relabelling_or_missing_identity(self):
        data=self.trace('dispatch','normal')
        for offset,value in ((16,0),(8,2),(24,1)):
            changed=bytearray(data);struct.pack_into('<I' if offset!=8 else '<H',changed,offset,value)
            if offset==24:self.assertFalse(decode(checksums(changed))['trace_window_complete'])
            else:
                with self.assertRaises(ValueError):decode(checksums(changed))
        for begin,end in ((64,80),(80,96),(36,37)):
            changed=bytearray(data);changed[begin:end]=bytes(end-begin) if begin!=36 else b'\1'
            with self.assertRaises(ValueError):decode(checksums(changed))

    def test_semantic_corruption_with_recomputed_crc_is_rejected(self):
        data=self.trace('dispatch','normal')
        mutations=[(128+16,'I',2),(128+20,'I',0),(128+36,'H',99),(128+38,'B',4),
                   (128+39,'B',128),(128+28,'I',1),(128+40,'B',1),
                   (128+48+20,'I',999),(128+48*3+20,'I',1)]
        for offset,kind,value in mutations:
            with self.subTest(offset=offset):
                changed=bytearray(data);struct.pack_into('<'+kind,changed,offset,value)
                with self.assertRaises(ValueError):decode(checksums(changed))
        changed=bytearray(data);struct.pack_into('<Q',changed,128+8,0xffffffffffffffff)
        with self.assertRaises(ValueError):decode(checksums(changed))
        changed=bytearray(data);struct.pack_into('<H',changed,104,0)
        with self.assertRaises(ValueError):decode(checksums(changed))

    def test_simulation_identity_and_crc_never_authenticate_hardware(self):
        for row in self.result['instrumented_cases']:
            result=decode((self.output/row['trace']).read_bytes())
            self.assertTrue(result['simulation']);self.assertFalse(result['hardware_verified'])
            self.assertFalse(result['identity_and_crc_authenticate_origin'])
            self.assertFalse(result['root_cause_confirmed'])

    def test_source_anchor_drift_fails_closed(self):
        text=probe.ep0.actual_source().replace('g_isoStatus.sequence = setup->wValue;',
                                             'g_isoStatus.sequence = 0;')
        with self.assertRaisesRegex(ValueError,'anchor mismatch'):probe.instrument(text)

    def test_partial_ack_or_status_helper_cannot_claim_complete_window(self):
        for family,case in [('dispatch','normal'),('shared','32ms-replaced')]:
            original=self.trace(family,case);analysis=decode(original)
            if case=='normal':
                cut=next(r['ordinal'] for r in analysis['records'] if r['stage']=='ack')-1
            else:
                cut=next(r['ordinal'] for r in analysis['records'] if r['stage']=='ctrl_post')
            changed=bytearray(original[:128+cut*48]);struct.pack_into('<I',changed,20,cut)
            result=decode(checksums(changed))
            self.assertFalse(result['trace_window_complete'])
        original=self.trace('dispatch','normal');analysis=decode(original)
        index=next(r['ordinal']-1 for r in analysis['records'] if r['stage']=='ctrl_wait')
        changed=bytearray(original);struct.pack_into('<H',changed,128+index*48+36,12)
        with self.assertRaisesRegex(ValueError,'out of order'):decode(checksums(changed))


if __name__=='__main__':unittest.main()
