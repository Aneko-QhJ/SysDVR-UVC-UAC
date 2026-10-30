"""Coverage check: every installer loop that gates alt endpoints is NOPed.

usb:ds's installer (0x295d0..0x2a04c) walks the configuration descriptors in
eight loops (four interfaces x SS/HS).  Each loop skips a type-5 endpoint when
the tracked alternate setting is non-zero; the U2 payload NOPs exactly those
eight `cbnz w9` instructions.  This test re-finds the eight loops in usb.elf and
compares them with the payload's NOP list.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_descriptor_payload import load_elf_sections
from build_uac_u2_base_payload import NOP_EDITS

ELF = ROOT / "private/module/usb.elf"

START, END = 0x295D0, 0x2A050
CMP_W10_4 = 0x7100115F      # cmp w10, #0x4   (interface descriptor)
CMP_W9_30 = 0x7100C13F      # cmp w9, #0x30   (SS endpoint companion)
CBNZ_W9_MASK = 0xFF00001F
CBNZ_W9 = 0x35000009


def _words(data, sections, start, end):
    for sec in sections.values():
        if sec["type"] != 8 and sec["addr"] <= start and end <= sec["addr"] + sec["size"]:
            off = sec["offset"] + start - sec["addr"]
            return [int.from_bytes(data[off + 4 * i:off + 4 * i + 4], "little")
                    for i in range((end - start) // 4)]
    raise ValueError("installer range outside mapped sections")


class Alt1NopCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ELF.is_file():
            raise unittest.SkipTest(f"missing {ELF}")
        data, sections = load_elf_sections(ELF)
        cls.words = _words(data, sections, START, END)
        cls.expected = sorted(address for address, _b, _a in NOP_EDITS)

    def _loops(self):
        sites = []
        for i, word in enumerate(self.words):
            if word != CMP_W10_4:
                continue
            for j in range(i, min(i + 10, len(self.words))):
                if (self.words[j] & CBNZ_W9_MASK) == CBNZ_W9:
                    sites.append(START + 4 * j)
                    break
        return sites

    def test_every_installer_loop_is_patched(self):
        loops = self._loops()
        self.assertEqual(len(loops), 8)
        self.assertEqual(loops, self.expected)

    def test_loops_split_into_four_ss_and_four_hs(self):
        ss = hs = 0
        for site in self.expected:
            index = (site - START) // 4
            window = self.words[index:index + 12]
            if CMP_W9_30 in window:
                ss += 1
            else:
                hs += 1
        self.assertEqual((ss, hs), (4, 4))

    def test_payload_has_one_nop_per_loop(self):
        self.assertEqual(len(NOP_EDITS), 8)
        self.assertEqual(len({a for a, _b, _a in NOP_EDITS}), 8)
        for _address, before, after in NOP_EDITS:
            self.assertEqual(before, 0x35FFFF09)  # cbnz w9, -8
            self.assertEqual(after, 0xD503201F)   # nop


if __name__ == "__main__":
    unittest.main()
