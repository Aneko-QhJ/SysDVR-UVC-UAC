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
SETS = ROOT / "patches/iso_burst_uac84_dci9_pipe_sets.S"
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


class QueuePatchTests(unittest.TestCase):
    """v29a: submit the appended request immediately, skip the auto-submit."""

    def test_stub_submits_the_appended_entry(self):
        from build_uac_u2_producer import (QUEUE_GATE_AFTER, QUEUE_SKIP_AFTER,
                                           QUEUE_STUB_AFTER)
        words = [int.from_bytes(QUEUE_STUB_AFTER[i:i + 4], "little")
                 for i in range(0, 12, 4)]
        self.assertEqual(words[0], 0x51000589)   # sub w9, w12, #1
        self.assertEqual(words[1], 0x12000929)   # and w9, w9, #7
        # b 0x2c62c, pc 0x0cc
        self.assertEqual(words[2] & 0xFC000000, 0x14000000)
        target = 0x0CC + ((words[2] & 0x3FFFFFF) << 2)
        self.assertEqual(target, 0x2C62C)

    def test_gate_branches_to_the_stub(self):
        from build_uac_u2_producer import QUEUE_GATE_AFTER
        word = int.from_bytes(QUEUE_GATE_AFTER, "little")
        self.assertEqual(word & 0xFC000000, 0x14000000)
        imm = word & 0x3FFFFFF
        if imm & (1 << 25):
            imm -= 1 << 26
        self.assertEqual(0x2C628 + (imm << 2), 0x0C4)

    def test_skip_branch_jumps_over_the_auto_submit(self):
        from build_uac_u2_producer import QUEUE_SKIP_AFTER
        word = int.from_bytes(QUEUE_SKIP_AFTER, "little")
        imm = word & 0x3FFFFFF
        if imm & (1 << 25):
            imm -= 1 << 26
        self.assertEqual(0x2C80C + (imm << 2), 0x2C84C)

    def test_builder_counts_the_three_extra_edits(self):
        text = PRODUCER.read_text()
        self.assertIn('"--driver-queue"', text)
        self.assertIn("QUEUE_EDITS if driver_queue else 0", text)
        self.assertIn("driver_queue=args.driver_queue", text)

    def test_work_dir_manifest_matches_when_present(self):
        import json
        work = ROOT / "private/analysis/UAC-u2-v29a-queue-20261102"
        if not (work / "manifest.json").is_file():
            self.skipTest("v29a payload not built here")
        doc = json.loads((work / "manifest.json").read_text())
        self.assertTrue(doc["driver_queue"])
        self.assertEqual(doc["edit_count"], 32)
        addrs = {entry["address"] for entry in doc["edits"]}
        self.assertTrue({"0xc4", "0x2c628", "0x2c80c"} <= addrs)


class SetMailboxCaveTests(unittest.TestCase):
    """v29b: one mailbox per in-flight TD set (A at 0xf80, B at 0xfc0)."""

    @classmethod
    def setUpClass(cls):
        cls.text = SETS.read_text()

    def test_enter_selects_the_mailbox_from_prod(self):
        self.assertIn("sub x9, x8, x10", self.text)
        self.assertIn("ubfx w9, w9, #9, #1", self.text)
        self.assertIn("add x5, x5, x9, lsl #6", self.text)
        self.assertIn("add x17, x10, #0xfb8", self.text)

    def test_cursor_is_global_not_per_set(self):
        self.assertIn("ldrh w10, [x17]", self.text)
        self.assertIn("strh w10, [x17]", self.text)
        self.assertNotIn("[x5, #0x38]", self.text)

    def test_event_picks_the_set_from_the_ed_offset(self):
        self.assertIn("ubfx w3, w7, #9, #1", self.text)
        self.assertIn("add x5, x5, x3, lsl #6", self.text)

    def test_no_write_into_the_driver_link_slot(self):
        # set B occupies 0xfc0..0xfdf; ring+0xff0 is the driver's link TRB.
        self.assertNotIn("[x5, #60]", self.text)

    def test_mailbox_fields_end_before_the_link(self):
        self.assertLess(0xFC0 + 0x20, 0xFF0)

    def test_assembled_cave_fits_the_padding(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            code, symbols = assemble(TOOLCHAIN, Path(tmp) / "s", SETS,
                                     require_report=False)
        self.assertLessEqual(len(code), 0x69000 - 0x68D54)
        self.assertGreater(len(code), 0x69000 - 0x68D54 - 8)  # tight budget
        self.assertEqual(symbols["iso_enter"], 0x68D54)


class AppStatusFilterTests(unittest.TestCase):
    def test_status_2_is_not_a_completion(self):
        text = SOURCE.read_text()
        self.assertIn("if (report.report[i].urb_status == 2) continue;", text)


class StreamPipelineTests(unittest.TestCase):
    """v29c: the pipeline keeps posting until STREAM_POSTS, reusing slots."""

    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text()

    def test_stream_length_is_separate_from_the_buffer_pool(self):
        self.assertIn("#ifndef UAC_U2_STREAM_POSTS", self.text)
        self.assertIn("#define UAC_U2_STREAM_POSTS UAC_U2_TRAIN_POSTS", self.text)
        self.assertIn("UAC_U2_STREAM_POSTS must be >= UAC_U2_TRAIN_POSTS",
                      self.text)

    def test_slots_are_reused_only_after_a_completion(self):
        self.assertIn("u8 free_slot[8]", self.text)
        self.assertIn("free_slot[next] = 0;", self.text)
        self.assertIn("free_slot[b] = 1;", self.text)
        self.assertIn("posted < stream_posts && posted - completed < 4 &&",
                      self.text)

    def test_train_breaks_only_after_stream_posts(self):
        self.assertIn("if (posted == stream_posts && completed == posted) break;",
                      self.text)
        self.assertNotIn("posted == UAC_U2_TRAIN_POSTS && completed == posted",
                         self.text)


if __name__ == "__main__":
    unittest.main()
