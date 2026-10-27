import struct
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_a23_iso_retention import geometry, retained_error


def packet(selected=8177):
    raw=bytearray(112);frame=((selected>>3)+32)&2047
    struct.pack_into('<6IQ',raw,0,0x374f5349,0,(frame<<20)|0x1411,0x80000017,0,0,0x135897d000)
    struct.pack_into('<5I',raw,52,0x80023000,0,0x170000c0,0x78001,((frame+1)*8)&16383)
    struct.pack_into('<2I',raw,72,selected,1)
    struct.pack_into('<8I',raw,80,0x10001,0x100002e,0x80023001,0,0x1000c00,0,0xc0000,0)
    return raw


class RetentionTests(unittest.TestCase):
    def test_error_count_is_not_192_transferred_bytes(self):
        result=retained_error(bytes(packet()))
        self.assertTrue(result['error_slot_consistent'])
        self.assertEqual(result['error']['td_index'],0)
        self.assertEqual(result['error']['raw_count'],192)
        self.assertEqual(result['accepted_success_bytes'],0)
        self.assertFalse(result['raw_count_is_transferred_bytes'])
        self.assertFalse(result['device_cc_semantics_confirmed'])

    def test_stale_cleared_slot_does_not_supply_error(self):
        raw=packet();struct.pack_into('<I',raw,64,0)
        self.assertIsNone(retained_error(bytes(raw))['error'])

    def test_nonatomic_terminal_and_event_mismatch_not_used(self):
        raw=packet();struct.pack_into('<I',raw,60,0x010000c0)
        self.assertIsNone(retained_error(bytes(raw))['error'])

    def test_zero_completion_code_or_reserved_terminal_bits_not_used(self):
        for terminal,status in ((0x80000000,192),(0xc0000017,0x170000c0)):
            raw=packet();struct.pack_into('<I',raw,12,terminal);struct.pack_into('<I',raw,60,status)
            self.assertIsNone(retained_error(bytes(raw))['error'])

    def test_wrong_endpoint_or_event_type_not_used(self):
        for flags in (0x68001,0x78401):
            raw=packet();struct.pack_into('<I',raw,64,flags)
            self.assertIsNone(retained_error(bytes(raw))['error'])

    def test_parity_and_burst_boundary_not_used(self):
        for offset in (16,512,0xffffffff):
            raw=packet();struct.pack_into('<I',raw,4,offset)
            self.assertIsNone(retained_error(bytes(raw))['error'])

    def test_invalid_context_not_used_for_target_arithmetic(self):
        raw=packet();struct.pack_into('<I',raw,76,0)
        result=retained_error(bytes(raw));self.assertIsNone(result['target_frame'])
        self.assertIsNone(result['error']['handler_mfi_minus_target_microframes'])

    def test_frame_wrap_keeps_event_delta_eight(self):
        result=retained_error(bytes(packet(16380)))
        self.assertTrue(result['header_consistent'])
        self.assertEqual(result['target_frame'],31)
        self.assertEqual(result['error']['handler_mfi_minus_target_microframes'],8)

    def test_malformed_length_magic_bitmap_rejected(self):
        for raw in (b'',bytes(112),bytes(packet())+b'x'):
            with self.assertRaises(ValueError):retained_error(raw)
        raw=packet();struct.pack_into('<I',raw,16,65536)
        with self.assertRaises(ValueError):retained_error(bytes(raw))

    def test_geometry_preserves_conditional_limits(self):
        result=geometry(1054,33721405)
        self.assertEqual(result['host_first_after_device_target_frames'],31)
        self.assertEqual(result['reference_slot_at_current_lead'],-248)
        self.assertFalse(result['frame_domain_alignment_verified'])
        self.assertFalse(result['root_cause_confirmed'])
        positions={r['modeled_lead_frames']:r['first_target_slot'] for r in result['modeled_windows']}
        self.assertEqual(positions,{16:136,24:72,32:8,64:-248})

    def test_geometry_wrap(self):
        result=geometry(20,2035+64)
        self.assertEqual(result['device_target_after_host_sample_frames'],33)

    def test_ambiguous_backward_geometry_rejected(self):
        with self.assertRaises(ValueError):geometry(1900,100+64)

    def test_geometry_extent(self):
        result=geometry(136,100+64,leads=(16,64))
        self.assertTrue(result['modeled_windows'][0]['sixteen_reference_slots_fit'])
        self.assertFalse(result['modeled_windows'][1]['sixteen_reference_slots_fit'])


if __name__=='__main__':unittest.main()
