"""v28: widen one transfer instead of keeping a second one in flight.

v27 proved the usb:ds AS endpoint is single-transfer: a second post while one
request is in flight never reaches the cave and completes xfer=0/status=5.
v28 therefore keeps one post and makes the request larger.  The cave builds
one Isoch+ED TD pair per 192 B of the request (the loop ends at buffer +
request length, not a fixed counter) and completes on the frame count it was
built for.

v28 used 32 frames (6144 B) and hung the console inside PostBufferAsync, so
v28b steps down to 20 frames (3840 B) to find the cliff.  These tests pin
both caves, the app frame macro and the builders; no hardware is needed.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_u2_producer import assemble  # noqa: E402

MULTI = ROOT / "patches/iso_burst_uac84_dci9_pipe_multi.S"
MULTI20 = ROOT / "patches/iso_burst_uac84_dci9_pipe_multi20.S"
CURSOR = ROOT / "patches/iso_burst_uac84_dci9_pipe_cursor.S"
SOURCE = REPO / "source/uvc/uvc_device.c"
PRODUCER = ROOT / "tools/build_uac_u2_producer.py"
PROBE = ROOT / "tools/build_uac_u2_probe.py"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")
FRAME_BYTES = 192


class MultiCaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = MULTI.read_text()

    def test_request_gate_is_the_two_segment_size(self):
        # cmp supports only 12-bit immediates; 6144 needs a register.
        self.assertIn("mov w9, #0x1800", self.text)
        self.assertIn("cmp w3, w9", self.text)
        self.assertNotIn("cmp w3, #3072", self.text)

    def test_td_count_follows_the_request_length(self):
        self.assertIn("add x16, x2, w3, uxtw", self.text)
        self.assertIn("cmp x2, x16", self.text)
        self.assertNotIn("mov w14, #16", self.text)
        self.assertNotIn("subs w14, w14, #1", self.text)

    def test_event_accepts_32_slots_and_needs_the_full_bitmap(self):
        self.assertIn("cmp x6, #1024", self.text)
        self.assertIn("cmn w6, #1", self.text)
        self.assertNotIn("cmp w4, #3072", self.text)

    def test_assembled_cave_fits_and_only_the_gate_costs_bytes(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            multi, symbols = assemble(TOOLCHAIN, tmp / "m", MULTI,
                                      require_report=False)
            cursor, _ = assemble(TOOLCHAIN, tmp / "c", CURSOR,
                                 require_report=False)
        self.assertLessEqual(len(multi), 0x69000 - 0x68D54)
        self.assertEqual(len(multi), len(cursor) + 4)  # mov/cmp instead of cmp
        self.assertEqual(symbols["iso_enter"], 0x68D54)


class Multi20CaveTests(unittest.TestCase):
    """v28b: the same shape with a 20-frame (3840 B) request."""

    @classmethod
    def setUpClass(cls):
        cls.text = MULTI20.read_text()

    def test_size_and_ed_sum_are_3840_bytes(self):
        self.assertIn("cmp w3, #0xf00", self.text)   # 20 x 192 B request
        self.assertIn("cmp w4, #0xf00", self.text)   # 20 distinct EDs
        self.assertIn("cmp x6, #0x280", self.text)   # 20 TD pairs x 32 B

    def test_td_count_still_follows_the_request_length(self):
        self.assertIn("add x16, x2, w3, uxtw", self.text)
        self.assertIn("cmp x2, x16", self.text)
        self.assertNotIn("mov w14, #16", self.text)
        self.assertNotIn("subs w14, w14, #1", self.text)

    def test_assembled_cave_is_byte_neutral(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            multi20, symbols = assemble(TOOLCHAIN, tmp / "m20", MULTI20,
                                        require_report=False)
            cursor, _ = assemble(TOOLCHAIN, tmp / "c", CURSOR,
                                 require_report=False)
        self.assertLessEqual(len(multi20), 0x69000 - 0x68D54)
        self.assertEqual(len(multi20), len(cursor))
        self.assertEqual(symbols["iso_enter"], 0x68D54)

    def test_model_matches_the_request(self):
        frames = 20
        size = frames * FRAME_BYTES
        self.assertEqual(size, 3840)
        self.assertLess(frames * 32, 0xF70)       # TD pairs stay before the link
        self.assertLess(frames, 32)               # bitmap covers 32 slots
        self.assertEqual((1 << frames) - 1, 0xFFFFF)


class MultiAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def test_one_request_carries_all_frames(self):
        self.assertIn("#define UAC_U2_FRAMES (16 * UAC_U2_SEGMENTS)", self.text)
        self.assertIn("#define UAC_U2_BURST_BYTES "
                      "(UAC_ISO_PACKET_SIZE * UAC_U2_FRAMES)", self.text)
        self.assertIn("#define UAC_U2_BUF_BYTES", self.text)
        self.assertIn("g_u2BurstBuffers[UAC_U2_TRAIN_POSTS][UAC_U2_BUF_BYTES]",
                      self.text)

    def test_frame_range_and_pipeline_are_guarded(self):
        self.assertIn("UAC_U2_FRAMES must be 1..32", self.text)
        self.assertIn("a pipeline build keeps two transfers in flight", self.text)

    def test_multi_build_logs_its_shape(self):
        self.assertIn("UAC U2 multi frames=%u size=%u", self.text)


class MultiBuilderTests(unittest.TestCase):
    def test_producer_records_frames_and_burst_bytes(self):
        text = PRODUCER.read_text()
        self.assertIn('"--frames"', text)
        self.assertIn('"burst_bytes": 192 * frames', text)
        self.assertIn('if doc["burst_bytes"] != 192 * frames', text)

    def test_probe_builder_marks_multi_frame_builds(self):
        text = PROBE.read_text()
        self.assertIn('markers.append(b"UAC U2 multi")', text)
        self.assertIn("int(v) > 16", text)


class MultiFrameModelTests(unittest.TestCase):
    """The cave frame/cursor arithmetic for a larger request."""

    @staticmethod
    def pick(mfi_frame, cursor):
        if cursor == 0:
            return mfi_frame
        return cursor if ((cursor - mfi_frame) & 0x7FF) < 0x400 else mfi_frame

    def test_cursor_advances_by_the_whole_request(self):
        start = self.pick(900, 0)
        self.assertEqual(start, 900)
        self.assertEqual((start + 32) & 0x7FF, 932)  # written back as cursor
        self.assertEqual(self.pick(920, 932), 932)   # cursor ahead of MFI

    def test_frame_field_wraps_at_2048(self):
        self.assertEqual((2040 + 32) & 0x7FF, 24)
        self.assertEqual(self.pick(2040, 24), 24)


if __name__ == "__main__":
    unittest.main()
