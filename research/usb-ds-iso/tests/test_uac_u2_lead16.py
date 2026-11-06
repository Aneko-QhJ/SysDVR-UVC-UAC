"""v33 lead-16 cave: the re-arm first-set lead drops from 32 ms to 16.

The lead only applies to the first TD set after an empty-ring re-arm: the
cave schedules frame 0 at MFI/8 + lead and the cursor keeps the following
sets contiguous.  v30h measured 28-67 ms holes after a recovery; 16 ms of
that is this lead.  v33 is the v29s log cave with `#32` -> `#16`, nothing
else.  This test pins that one-instruction difference and assembles both.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_u2_producer import assemble  # noqa: E402

LOG16 = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_log16.S"
LOG32 = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_log.S"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")

ADD_LEAD32 = 0x11008129  # add w9, w9, #0x20
ADD_LEAD16 = 0x11004129  # add w9, w9, #0x10
LSR3 = 0x53037D29        # lsr w9, w9, #3


def _words(code):
    return [int.from_bytes(code[i:i + 4], "little")
            for i in range(0, len(code) - 4 + 1, 4)]


class UacU2Lead16Tests(unittest.TestCase):
    def test_source_has_the_16ms_lead_only(self):
        text = LOG16.read_text()
        self.assertIn("add w9, w9, #16", text)
        self.assertNotIn("add w9, w9, #32", text)
        self.assertNotIn("add w9, w9, #40", text)
        # the rest of the v29s log cave is untouched
        self.assertIn(".equ ISO_ENTRY, 0x300", text)
        self.assertIn("bl rearm_endpoint", text)

    def test_variants_differ_only_in_the_lead_instruction(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            code16, _ = assemble(TOOLCHAIN, tmp / "a", LOG16, require_report=False)
            code32, _ = assemble(TOOLCHAIN, tmp / "b", LOG32, require_report=False)
        self.assertEqual(len(code16), len(code32))
        self.assertLessEqual(len(code16), 0x69000 - 0x68D54)
        words16, words32 = _words(code16), _words(code32)
        self.assertIn(ADD_LEAD16, words16)
        self.assertNotIn(ADD_LEAD32, words16)
        self.assertIn(ADD_LEAD32, words32)
        lead16 = words16.index(ADD_LEAD16)
        lead32 = words32.index(ADD_LEAD32)
        self.assertEqual(lead16, lead32)
        self.assertEqual(words16[lead16 - 1], LSR3)
        self.assertEqual(words32[lead32 - 1], LSR3)
        diff = [i for i, (a, b) in enumerate(zip(code16, code32)) if a != b]
        self.assertEqual(diff, [4 * lead16 + 1])
        self.assertEqual(words16[lead16] ^ words32[lead32], 0xC000)


if __name__ == "__main__":
    unittest.main()
