"""v40 halt-gated 32 ms lead: 20 ms normally, 32 ms for the first set after a miss.

v39's miss ring showed the host never reacts to a single miss: every alt0
arrives 1-16 ms after the LAST miss of a burst, and a burst is 2-10 misses at
20-25 ms spacing.  So the lever is to break the burst: give the first re-armed
set (the one right after a cancel) the v30h-safe 32 ms lead and keep 20 ms
everywhere else.

The marker is the endpoint halt bit at regs+0x50 - the driver sets it on a
code-23 miss, the app's cancel does not clear it, a fresh 0x2feb0 does.  Same
mechanism as v35, which used 16 ms and failed; this is the mirror.

This test pins the selection (32 only when the halt bit is set), the two
normal-20 paths, and that the cave still assembles into the 684 B cave.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_u2_producer import assemble  # noqa: E402

CAVE = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_slead32.S"
PREV = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_lead20.S"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")

MOV_W14_20 = 0x5280028E  # mov w14, #0x14
MOV_W14_32 = 0x5280040E  # mov w14, #0x20
ADD_LEAD_W14 = 0x0B0E0129  # add w9, w9, w14
LDR_HALT = 0xB940512A     # ldr w10, [x9, #0x50]


def _words(code):
    return [int.from_bytes(code[i:i + 4], "little")
            for i in range(0, len(code) - 4 + 1, 4)]


class UacU2Slead32Tests(unittest.TestCase):
    def test_source_selects_32_only_from_the_halt_bit(self):
        text = CAVE.read_text()
        self.assertIn("mov w14, #32", text)
        self.assertEqual(text.count("mov w14, #20"), 2)
        self.assertIn("add w9, w9, w14", text)
        self.assertNotIn("add w9, w9, #20", text)
        self.assertNotIn("add w9, w9, #32", text)
        self.assertIn("[x9, #0x50]", text)
        self.assertIn("tst w10, w11", text)
        # the empty-ring path must test the halt bit before rearm_endpoint
        empty = text.index("bl rearm_endpoint")
        self.assertLess(text.index("tst w10, w11"), empty)
        # ... and the non-empty path must set the normal lead before writing
        nonempty = text.index("pipe_nonempty:")
        self.assertIn("mov w14, #20", text[nonempty:nonempty + 120])

    def test_assembles_into_the_cave(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            code, symbols = assemble(TOOLCHAIN, Path(tmp), CAVE,
                                     require_report=False)
        self.assertEqual(symbols["iso_enter"], 0x68D54)
        self.assertEqual(len(code), 600)
        self.assertLessEqual(len(code), 0x69000 - 0x68D54)

    def test_word_counts(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = assemble(TOOLCHAIN, Path(tmp), CAVE,
                               require_report=False)
        words = _words(code)
        self.assertEqual(words.count(MOV_W14_20), 2)  # empty-ring default + non-empty
        self.assertEqual(words.count(MOV_W14_32), 1)  # halt set
        self.assertEqual(words.count(ADD_LEAD_W14), 1)
        self.assertEqual(words.count(LDR_HALT), 1)
        # the packet counter still uses 16 and must not be confused with a lead
        self.assertEqual(words.count(0x5280020E), 1)  # mov w14, #0x10

    def test_v38_cave_is_untouched(self):
        self.assertIn("add w9, w9, #20", PREV.read_text())


if __name__ == "__main__":
    unittest.main()
