"""Specific failure boundaries for the offline cadence calculation."""
import importlib.util
from pathlib import Path
import struct
import unittest


SPEC = importlib.util.spec_from_file_location("cadence", Path(__file__).parents[1] /
    "tools/analyze_a23_audio_cadence.py")
cadence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cadence)


def snapshot(first_slot=9):
    raw = bytearray(128 * 192)
    transactions = bytearray(128 * 28)
    for i in range(128):
        count = 192 if first_slot <= i < first_slot + 16 else 0
        struct.pack_into("<iIIIQI", transactions, i * 28, 0, 192, i * 192, count, 17, 0)
        if count:
            sequence = 465 + i - first_slot
            raw[i * 192:(i + 1) * 192] = b"ISO1" + struct.pack("<H", sequence) + bytes(
                (j ^ sequence ^ (sequence >> 8)) & 255 for j in range(6, 192))
    return raw, transactions


class CadenceTests(unittest.TestCase):
    def test_current_source_facts_remain_readable_after_comment_changes(self):
        facts = {record['path']: record for record in cadence.source_facts()}
        device = facts['source/uvc/uvc_device.c']
        self.assertTrue(device['anchors']['if (!g_uacCtx.initialized || !g_uacCtx.streaming) {'])
        self.assertEqual(len(device['sha256']), 64)

    def test_rate_and_time_are_distinct(self):
        diagnostic = cadence.packet_budget(192, 125)
        self.assertEqual(diagnostic["pcm_rate_multiple"], 8)
        self.assertEqual(diagnostic["pcm_equivalent_ms"], 16)
        self.assertEqual(diagnostic["service_slots_ms"], 2)
        self.assertEqual(diagnostic["first_to_last_slot_ms"], 1.875)
        for size, period in [(24, 125), (192, 1000)]:
            self.assertEqual(cadence.packet_budget(size, period)["pcm_rate_multiple"], 1)

    def test_chunk_boundaries_carry_samples(self):
        for size, remainder, packets in [(192, [64, 128, 0], [21, 21, 22]),
                                         (24, [16, 8, 0], [170, 171, 171])]:
            rows = cadence.chunk_residues(size)
            self.assertEqual([r["carried_bytes"] for r in rows], remainder)
            self.assertEqual([r["emitted_packets"] for r in rows], packets)
            self.assertEqual(sum(r["emitted_packets"] for r in rows) * size, 3 * 4096)
        with self.assertRaises(ValueError):
            cadence.packet_budget(25, 125)

    def test_full_window_and_last_slot_are_parsed(self):
        for first in (0, 9, 112):
            raw, transactions = snapshot(first)
            self.assertEqual(cadence.decode_payload(raw, transactions, 465), list(range(first, first + 16)))

    def test_dormant_padding_changes_sample_count(self):
        padded = cadence.legacy_padding_budget()
        self.assertEqual(padded["emitted_bytes"], 4224)
        self.assertEqual(padded["inserted_stereo_sample_frames"], 32)
        self.assertEqual(padded["sample_count_increase_percent"], 3.125)
        self.assertEqual(cadence.legacy_padding_budget(3072)["inserted_silence_bytes"], 0)

    def test_native_error_in_empty_slot_is_preserved(self):
        raw, transactions = snapshot()
        struct.pack_into("<i", transactions, 127 * 28, -1)
        with self.assertRaisesRegex(ValueError, "invalid transaction"):
            cadence.decode_payload(raw, transactions, 465)

    def test_corrupt_body_and_partial_packet_are_rejected(self):
        raw, transactions = snapshot()
        raw[9 * 192 + 180] ^= 1
        with self.assertRaisesRegex(ValueError, "payload mismatch"):
            cadence.decode_payload(raw, transactions, 465)
        raw, transactions = snapshot()
        struct.pack_into("<I", transactions, 9 * 28 + 12, 188)
        with self.assertRaisesRegex(ValueError, "invalid transaction"):
            cadence.decode_payload(raw, transactions, 465)


if __name__ == "__main__":
    unittest.main()
