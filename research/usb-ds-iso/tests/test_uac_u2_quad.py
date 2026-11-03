"""v29e: four per-set mailboxes so three requests can stay in flight.

v29d aligned the ring link and the wrap became clean, but two in-flight sets
still drained while the app posted about every 30 ms.  v29e keeps three sets
in flight and gives each a mailbox at ring+0xf00/+0xf40/+0xf80/+0xfc0; the
set index is (offset >> 9) & 3, so three consecutive sets never share one.
The app also cancels the remaining requests after a status=5 so the next post
takes the cave's empty re-arm path.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_u2_producer import assemble  # noqa: E402

QUAD = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad.S"
WRAP = ROOT / "patches/iso_burst_uac84_dci9_pipe_wrap.S"
SOURCE = REPO / "source/uvc/uvc_device.c"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")
RING = 0x1000
SET = 0x200
LINK = 0xC00
MAILBOXES = 4


class QuadCaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = QUAD.read_text()

    def test_four_mailboxes_start_after_the_link(self):
        self.assertIn("add x5, x10, #0xf00", self.text)
        self.assertIn("add x5, x5, #0xf00", self.text)
        self.assertIn("ubfx w9, w9, #9, #2", self.text)
        self.assertIn("ubfx w3, w7, #9, #2", self.text)
        self.assertGreater(0xF00, LINK)
        self.assertEqual(0xF00 + 4 * 0x40, 0x1000)

    def test_done_gate_is_per_selected_mailbox(self):
        select = self.text.index("add x5, x5, x3, lsl #6")
        gate = self.text.index("ldr w6, [x5, #12]")
        self.assertLess(select, gate)

    def test_three_consecutive_sets_have_distinct_mailboxes(self):
        blocks = [offset // SET for offset in range(0, LINK, SET)]
        self.assertEqual(blocks, [0, 1, 2, 3, 4, 5])
        boxes = [block & 3 for block in blocks]
        for start in range(len(boxes) - 2):
            self.assertEqual(len(set(boxes[start:start + 3])), 3)
        self.assertEqual(boxes[5], 1)
        self.assertNotEqual(boxes[5], boxes[0])

    def test_cave_still_fits(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            quad, symbols = assemble(TOOLCHAIN, Path(tmp), QUAD, require_report=False)
            wrap, _ = assemble(TOOLCHAIN, Path(tmp) / "w", WRAP, require_report=False)
        self.assertLessEqual(len(quad), 0x69000 - 0x68D54)
        self.assertEqual(len(quad), len(wrap))
        self.assertEqual(symbols["iso_enter"], 0x68D54)


class PipelineAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def test_three_requests_in_flight(self):
        self.assertIn("posted - completed < 3", self.text)
        self.assertNotIn("posted - completed < 4", self.text)

    def test_status5_only_counts_a_miss(self):
        self.assertIn('UAC U2 pipe miss buf=%u status=%u', self.text)
        self.assertIn("++misses;", self.text)
        self.assertNotIn("pipe recover cancelled=%u", self.text)

    def test_stall_cancels_and_reposts(self):
        self.assertIn("UAC U2 pipe stall recover cancelled=%u", self.text)
        self.assertIn("recoveries < 8", self.text)
        self.assertIn("usbDsEndpoint_Cancel(", self.text)
        self.assertIn("++recoveries;", self.text)


class TeardownTests(unittest.TestCase):
    """v29g: alt0 must see a quiet endpoint before the status stage."""

    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.text = SOURCE.read_text()

    def test_alt0_cancels_and_reaps_before_ack(self):
        start = self.text.index("case UAC_ACT_STOP:")
        end = self.text.index("case UAC_ACT_ACK:", start)
        block = self.text[start:end]
        cancel = block.index("usbDsEndpoint_Cancel(")
        ack = block.index("_ctrlAck(iface);")
        self.assertLess(cancel, ack)
        self.assertIn("UAC U2 teardown cancel", block)
        self.assertIn("GetReportData", block)


class MapSoftTests(unittest.TestCase):
    """v29h: node exhaustion must return an error, not reach the 0x40d0 panic."""

    def test_edit_retargets_the_panic_branch(self):
        import build_uac_u2_producer as builder
        address, before, after, reason = builder.MAP_SOFT_EDITS[0]
        self.assertEqual(address, 0x3FE0)
        self.assertEqual(before, bytes.fromhex("800700b4"))  # cbz x0, 0x40d0
        self.assertEqual(after, bytes.fromhex("e00500b4"))   # cbz x0, 0x409c
        self.assertEqual(builder.MAP_SOFT_EDIT_COUNT, 1)
        self.assertIn("panic", reason)

    def test_target_is_the_failure_epilogue(self):
        before = int.from_bytes(bytes.fromhex("800700b4"), "little")
        after = int.from_bytes(bytes.fromhex("e00500b4"), "little")
        def target(word, pc):
            imm = (word >> 5) & 0x7FFFF
            return pc + (imm << 2)
        self.assertEqual(target(before, 0x3FE0), 0x40D0)
        self.assertEqual(target(after, 0x3FE0), 0x409C)


QUAD4 = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad4.S"


class FourSetRingTests(unittest.TestCase):
    """v29i: four sets per ring so four in-flight sets keep distinct mailboxes."""

    @classmethod
    def setUpClass(cls):
        cls.text = QUAD4.read_text()

    def test_link_after_four_aligned_sets(self):
        self.assertEqual(self.text.count("add x13, x10, #0x800"), 2)
        self.assertIn("cmp x7, #0x800", self.text)
        self.assertIn("add x6, x6, #0x800", self.text)
        self.assertNotIn("add x13, x10, #0xc00", self.text)
        self.assertEqual(0x800 // SET, 4)

    def test_four_consecutive_sets_are_unique_across_the_wrap(self):
        boxes = [(offset // SET) & 3 for offset in range(0, 0x800, SET)]
        self.assertEqual(boxes, [0, 1, 2, 3])
        self.assertNotEqual(boxes[3], boxes[0])

    def test_cave_size_is_unchanged(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            quad4, symbols = assemble(TOOLCHAIN, Path(tmp), QUAD4,
                                      require_report=False)
        self.assertEqual(len(quad4), 680)
        self.assertEqual(symbols["iso_enter"], 0x68D54)


class LinkSlotTests(unittest.TestCase):
    def test_edits_follow_the_slot(self):
        import build_uac_u2_producer as builder
        edits = builder.link_edits(0x800)
        self.assertEqual(len(edits), 12)
        add = int.from_bytes(edits[0][2], "little")
        self.assertEqual((add >> 10) & 0xFFF, 0x800)
        high = int.from_bytes(edits[1][2], "little")
        low = int.from_bytes(edits[2][2], "little")
        self.assertEqual(((high >> 10) & 0xFFF) * 8, 0x808)
        self.assertEqual(((low >> 10) & 0xFFF) * 8, 0x800)


QUAD16 = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad16.S"


class Lead16Tests(unittest.TestCase):
    """v29j: the v29h ring with frame lead 16 instead of 32."""

    @classmethod
    def setUpClass(cls):
        cls.text = QUAD16.read_text()

    def test_lead_is_sixteen(self):
        self.assertIn("add w9, w9, #16", self.text)
        self.assertNotIn("add w9, w9, #32", self.text)

    def test_ring_and_mailboxes_are_v29h(self):
        self.assertIn("add x13, x10, #0xc00", self.text)
        self.assertIn("add x5, x10, #0xf00", self.text)

    def test_size_is_unchanged(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            quad16, symbols = assemble(TOOLCHAIN, Path(tmp), QUAD16,
                                       require_report=False)
        self.assertEqual(len(quad16), 680)
        self.assertEqual(symbols["iso_enter"], 0x68D54)


QUAD40 = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad40.S"
ADD_LEAD32 = 0x11008129  # add w9, w9, #0x20
ADD_LEAD40 = 0x1100A129  # add w9, w9, #0x28
LSR3 = 0x53037D29        # lsr w9, w9, #3


def _words(code):
    return [int.from_bytes(code[i:i + 4], "little")
            for i in range(0, len(code) - 4 + 1, 4)]


class Lead40Tests(unittest.TestCase):
    """v29k: the v29h ring with frame lead 40 instead of 32."""

    @classmethod
    def setUpClass(cls):
        cls.text = QUAD40.read_text()

    def test_lead_is_forty(self):
        self.assertIn("add w9, w9, #40", self.text)
        self.assertNotIn("add w9, w9, #32", self.text)

    def test_ring_and_mailboxes_are_v29h(self):
        self.assertIn("add x13, x10, #0xc00", self.text)
        self.assertIn("add x5, x10, #0xf00", self.text)
        self.assertNotIn("ring+0x800", self.text)

    def test_cave_differs_from_lead32_only_in_the_lead(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            quad40, symbols = assemble(TOOLCHAIN, tmp / "a", QUAD40,
                                       require_report=False)
            quad32, _ = assemble(TOOLCHAIN, tmp / "b", QUAD,
                                 require_report=False)
        self.assertEqual(len(quad40), 680)
        self.assertEqual(len(quad40), len(quad32))
        self.assertEqual(symbols["iso_enter"], 0x68D54)
        words40, words32 = _words(quad40), _words(quad32)
        self.assertIn(ADD_LEAD40, words40)
        self.assertNotIn(ADD_LEAD32, words40)
        self.assertIn(ADD_LEAD32, words32)
        lead40 = words40.index(ADD_LEAD40)
        lead32 = words32.index(ADD_LEAD32)
        self.assertEqual(lead40, lead32)
        self.assertEqual(words40[lead40 - 1], LSR3)
        diff = [i for i, (a, b) in enumerate(zip(quad40, quad32)) if a != b]
        self.assertEqual(len(diff), 1, [hex(0x68D54 + i) for i in diff])


class MapSoft2Tests(unittest.TestCase):
    """v29l: the second alt0/IOVA panic entry at 0x3dac."""

    def test_edit_retargets_the_second_panic(self):
        import build_uac_u2_producer as builder
        address, before, after, reason = builder.MAP_SOFT2_EDITS[0]
        self.assertEqual(address, 0x3DAC)
        self.assertEqual(before, bytes.fromhex("00190034"))  # cbz w0, 0x40cc
        self.assertEqual(after, bytes.fromhex("80170034"))   # cbz w0, 0x409c
        self.assertNotEqual(before, after)

    def test_branch_targets(self):
        def target(insn, pc):
            imm = (insn >> 5) & 0x7FFFF
            if imm & 0x40000:
                imm -= 0x80000
            return pc + (imm << 2)
        before = int.from_bytes(bytes.fromhex("00190034"), "little")
        after = int.from_bytes(bytes.fromhex("80170034"), "little")
        self.assertEqual(target(before, 0x3DAC), 0x40CC)
        self.assertEqual(target(after, 0x3DAC), 0x409C)


if __name__ == "__main__":
    unittest.main()
