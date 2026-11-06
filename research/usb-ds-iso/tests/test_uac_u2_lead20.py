"""v38 lead-20 cave: v37 with the re-arm first-set lead at 20 ms.

v37 measured every per-train max_gap at <= 40 ms with lead 24 and still saw 8
alt0 teardowns in 20 s (each costs the host's 122-191 ms re-arm).  A miss hole
is the lost 16 ms set plus the lead, so 24 lands exactly on the ~40 ms host
tolerance and 20 lands at 36.  This test pins the one changed immediate and
assembles the cave; the lead-24 and lead-32 caves must stay untouched.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_u2_producer import assemble  # noqa: E402

CAVE = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_lead20.S"
PREV = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_lead24.S"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")

ADD_LEAD32 = 0x11008129  # add w9, w9, #0x20
ADD_LEAD24 = 0x11006129  # add w9, w9, #0x18
ADD_LEAD20 = 0x11005129  # add w9, w9, #0x14
ADD_LEAD16 = 0x11004129  # add w9, w9, #0x10


def _words(code):
    return [int.from_bytes(code[i:i + 4], "little")
            for i in range(0, len(code) - 4 + 1, 4)]


class UacU2Lead20Tests(unittest.TestCase):
    def test_source_has_the_20ms_lead_only(self):
        text = CAVE.read_text()
        self.assertIn("add w9, w9, #20", text)
        for other in ("#16", "#24", "#32", "#40"):
            self.assertNotIn(f"add w9, w9, {other}", text)
        # the rest of the v37 cave is untouched
        self.assertIn(".equ ISO_ENTRY, 0x300", text)
        self.assertIn("b doorbell_tail", text)
        self.assertIn("ubfx w9, w9, #9, #2", text)

    def test_assembles_to_the_same_size_as_v37(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            code, symbols = assemble(TOOLCHAIN, Path(tmp), CAVE,
                                     require_report=False)
        self.assertEqual(symbols["iso_enter"], 0x68D54)
        with tempfile.TemporaryDirectory() as tmp:
            prev, _ = assemble(TOOLCHAIN, Path(tmp), PREV,
                               require_report=False)
        self.assertEqual(len(code), len(prev))
        self.assertEqual(len(code), 548)
        self.assertLessEqual(len(code), 0x69000 - 0x68D54)

    def test_the_lead_word_is_20(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = assemble(TOOLCHAIN, Path(tmp), CAVE,
                               require_report=False)
        words = _words(code)
        self.assertIn(ADD_LEAD20, words)
        for other in (ADD_LEAD16, ADD_LEAD24, ADD_LEAD32):
            self.assertNotIn(other, words)

    def test_the_previous_cave_is_untouched(self):
        self.assertIn("add w9, w9, #24", PREV.read_text())


if __name__ == "__main__":
    unittest.main()
