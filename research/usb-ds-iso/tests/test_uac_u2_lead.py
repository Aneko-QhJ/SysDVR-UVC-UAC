"""v25 lead-4 cave: the TD frame lead moves from 32 ms to 4 ms.

v24 timing showed wait_ms ~60 ms = 32 ms TD frame lead (frame = MFI/8 + 32)
+ 16 ms burst + ~12 ms event/driver, while the PostBufferAsync re-arm costs
<1 ms.  v25 only changes the cave's `add w9, w9, #32` to `#4`; this test pins
that one-instruction difference and assembles both caves.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_u2_producer import assemble  # noqa: E402

LEAD4 = ROOT / "patches/iso_burst_uac84_dci9_lead4.S"
REARM = ROOT / "patches/iso_burst_uac84_dci9_rearm.S"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")

ADD_LEAD32 = 0x11008129  # add w9, w9, #0x20
ADD_LEAD4 = 0x11001129   # add w9, w9, #0x4
LSR3 = 0x53037D29        # lsr w9, w9, #3


def _words(code):
    return [int.from_bytes(code[i:i + 4], "little")
            for i in range(0, len(code) - 4 + 1, 4)]


class UacU2LeadTests(unittest.TestCase):
    def test_source_lead_constants(self):
        lead4 = LEAD4.read_text()
        self.assertIn("add w9, w9, #4", lead4)
        self.assertNotIn("add w9, w9, #32", lead4)
        self.assertIn("add w9, w9, #32", REARM.read_text())

    def test_caves_differ_only_in_the_lead_instruction(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            code4, symbols4 = assemble(TOOLCHAIN, tmp / "a", LEAD4,
                                       require_report=False)
            code32, symbols32 = assemble(TOOLCHAIN, tmp / "b", REARM,
                                         require_report=False)
        self.assertEqual(len(code4), len(code32))
        self.assertLessEqual(len(code4), 0x69000 - 0x68D54)
        words4, words32 = _words(code4), _words(code32)
        self.assertIn(ADD_LEAD4, words4)
        self.assertNotIn(ADD_LEAD32, words4)
        self.assertIn(ADD_LEAD32, words32)
        lead4 = words4.index(ADD_LEAD4)
        lead32 = words32.index(ADD_LEAD32)
        self.assertEqual(lead4, lead32)
        self.assertEqual(words4[lead4 - 1], LSR3)
        self.assertEqual(words32[lead32 - 1], LSR3)
        diff = [i for i, (a, b) in enumerate(zip(code4, code32)) if a != b]
        self.assertEqual(len(diff), 1, [hex(0x68D54 + i) for i in diff])
        self.assertEqual(symbols4["iso_enter"], symbols32["iso_enter"])


if __name__ == "__main__":
    unittest.main()
