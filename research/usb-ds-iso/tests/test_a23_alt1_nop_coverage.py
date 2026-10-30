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
BL_MASK = 0xFC000000
BL = 0x94000000
CONFIG_FETCH = 0x2B520
MOV_W1_ZR = 0x2A1F03E1
MOVZ_W1 = 0x52800001
MOV_W2_W20 = 0x2A1403E2
MOVZ_W2_4 = 0x52800082


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

    def _bl_target(self, index):
        word = self.words[index]
        assert (word & BL_MASK) == BL, hex(word)
        imm = word & 0x3FFFFFF
        if imm & (1 << 25):
            imm -= 1 << 26
        return START + 4 * index + (imm << 2)

    def _fetches(self):
        fetches = []
        for i in range(len(self.words)):
            if (self.words[i] & BL_MASK) == BL and self._bl_target(i) == CONFIG_FETCH:
                fetches.append(START + 4 * i)
        return fetches

    def _fetch_args(self, fetch):
        index = (fetch - START) // 4
        w1 = w2 = None
        for j in range(index - 1, max(index - 20, 0), -1):
            word = self.words[j]
            if w1 is None:
                if word == MOV_W1_ZR:
                    w1 = 0
                elif (word & 0xFFE0001F) == MOVZ_W1:
                    w1 = (word >> 5) & 0xFFFF
            if w2 is None:
                if word == MOV_W2_W20:
                    w2 = "requested"
                elif word == MOVZ_W2_4:
                    w2 = "ss"
            if w1 is not None and w2 is not None:
                break
        return w1, w2

    def test_as_interface_loops_are_patched(self):
        # Each install loop follows one config fetch.  Fetches carry the
        # interface index in w1 and the speed in w2 (4 = SS, w20 = requested).
        # Interface 3 (AS) must map to 0x29F04 (SS) and 0x29FE8 (HS), both in
        # the NOP list, so EP 0x84 is installed at the requested (HS) speed.
        fetches = self._fetches()
        mapping = {}
        for site in self.expected:
            preceding = [f for f in fetches if f < site]
            self.assertTrue(preceding, hex(site))
            mapping[site] = self._fetch_args(preceding[-1])
        self.assertEqual(mapping[0x29F04], (3, "ss"))
        self.assertEqual(mapping[0x29FE8], (3, "requested"))
        known = {iface for iface, _variant in mapping.values() if iface is not None}
        self.assertEqual(known, {0, 1, 2, 3})
        # The HS branch at 0x29a84 reuses the caller's w1 = 0 (set at 0x29620).
        self.assertIsNone(mapping[0x29AD4][0])
        self.assertEqual(mapping[0x29AD4][1], "requested")

    def test_payload_has_one_nop_per_loop(self):
        self.assertEqual(len(NOP_EDITS), 8)
        self.assertEqual(len({a for a, _b, _a in NOP_EDITS}), 8)
        for _address, before, after in NOP_EDITS:
            self.assertEqual(before, 0x35FFFF09)  # cbnz w9, -8
            self.assertEqual(after, 0xD503201F)   # nop


if __name__ == "__main__":
    unittest.main()
