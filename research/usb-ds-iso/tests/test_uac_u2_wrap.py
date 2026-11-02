"""v29d: move the ring link after six aligned 0x200 TD sets.

v29c wrapped at ring+0xf70, which is inside the 8th 0x200 TD set (0xe00..0xfff).
A set split at the link, and every wrap shifted the write cursor by 0x90; once a
set straddled a 0x200 boundary its EDs were counted in both mailbox blocks,
neither mailbox reached 3072 B, and the controller reported status=5.

v29d puts the link at ring+0xc00 (six aligned sets; six is even so mailbox A/B
still alternates across the wrap) and patches the driver's link constant at its
four setup/error sites.  These tests pin the cave, the assembled size, the 12
driver edits and a small ring model; no hardware is needed.
"""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_uac_u2_producer as builder  # noqa: E402
from build_uac_u2_producer import assemble  # noqa: E402

WRAP = ROOT / "patches/iso_burst_uac84_dci9_pipe_wrap.S"
SETS = ROOT / "patches/iso_burst_uac84_dci9_pipe_sets.S"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")
RING = 0x1000
SET = 0x200          # 16 Isoch+ED pairs x 32 B
LINK = 0xC00         # six aligned sets
MAILBOX = 0xF80      # A at +0xf80, B at +0xfc0


def add_imm(word):
    """Return the imm12 of an ADD (immediate, 64-bit) instruction."""
    assert word & 0xFF800000 == 0x91000000, hex(word)
    return (word >> 10) & 0xFFF


def str_offset(word):
    """Return the unsigned byte offset of a `str xzr, [x8, #imm]` instruction."""
    assert word & 0xFFC00000 == 0xF9000000, hex(word)
    return ((word >> 10) & 0xFFF) * 8


class WrapCaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WRAP.read_text()

    def test_link_follows_six_aligned_sets(self):
        self.assertEqual(self.text.count("add x13, x10, #0xc00"), 2)
        self.assertIn("cmp x7, #0xc00", self.text)
        self.assertIn("add x6, x6, #0xc00", self.text)
        self.assertNotIn("add x13, x10, #0xf70", self.text)
        self.assertNotIn("cmp x7, #0xf70", self.text)
        self.assertNotIn("add x6, x6, #0xf70", self.text)
        self.assertEqual(LINK % SET, 0)
        self.assertEqual(LINK // SET, 6)

    def test_even_set_count_keeps_the_mailbox_phase(self):
        # Mailbox = (offset >> 9) & 1; an odd set count would repeat A.
        self.assertEqual((LINK // SET) % 2, 0)
        starts = list(range(0, LINK, SET))
        self.assertEqual([(s >> 9) & 1 for s in starts], [0, 1, 0, 1, 0, 1])
        self.assertNotEqual((starts[-1] >> 9) & 1, (0 >> 9) & 1)

    def test_old_slot_would_split_the_eighth_set(self):
        eighth = LINK + SET
        self.assertEqual(eighth, 0xE00)
        self.assertGreater(eighth + SET, 0xF70)  # 0xe00..0xfff covers 0xf70
        self.assertLess(LINK, 0xF70)

    def test_mailboxes_stay_outside_the_fetched_ring(self):
        self.assertGreater(MAILBOX, LINK + SET)
        self.assertEqual(MAILBOX, LINK + 0x380)

    def test_cave_still_fits_the_padding(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        with tempfile.TemporaryDirectory() as tmp:
            wrap, symbols = assemble(TOOLCHAIN, Path(tmp), WRAP, require_report=False)
            sets, _ = assemble(TOOLCHAIN, Path(tmp) / "sets", SETS, require_report=False)
        self.assertLessEqual(len(wrap), 0x69000 - 0x68D54)
        self.assertEqual(len(wrap), len(sets))  # immediates are size-neutral
        self.assertEqual(symbols["iso_enter"], 0x68D54)


class LinkEditTests(unittest.TestCase):
    def test_twelve_edits_at_four_sites(self):
        self.assertEqual(builder.LINK_EDIT_COUNT, 12)
        addresses = [address for address, _b, _a, _r in builder.LINK_EDITS]
        self.assertEqual(len(addresses), len(set(addresses)))
        self.assertEqual(sorted(addresses), addresses)
        words = [struct.unpack("<I", after)[0]
                 for _a, _b, after, _r in builder.LINK_EDITS]
        adds = [word for word in words if word & 0xFF800000 == 0x91000000]
        self.assertEqual([add_imm(word) for word in adds], [0xC00] * 4)

    def test_each_site_moves_the_link_to_c00(self):
        expected = {
            "add": 0xC00,
            "clear_high": 0xC08,
            "clear_low": 0xC00,
        }
        # Four identical triples: add, clear high half, clear low half.
        for index in range(4):
            add, high, low = builder.LINK_EDITS[index * 3:index * 3 + 3]
            self.assertEqual(add_imm(struct.unpack("<I", add[1])[0]), 0xFF0)
            self.assertEqual(add_imm(struct.unpack("<I", add[2])[0]), expected["add"])
            self.assertEqual(str_offset(struct.unpack("<I", high[1])[0]), 0xFF8)
            self.assertEqual(str_offset(struct.unpack("<I", high[2])[0]), expected["clear_high"])
            self.assertEqual(str_offset(struct.unpack("<I", low[1])[0]), 0xFF0)
            self.assertEqual(str_offset(struct.unpack("<I", low[2])[0]), expected["clear_low"])


class RingModelTests(unittest.TestCase):
    def test_sixty_four_posts_stay_aligned(self):
        prod = 0
        seen = []
        for _ in range(64):
            self.assertEqual(prod % SET, 0)
            self.assertLess(prod, LINK)
            seen.append(prod)
            prod = 0 if prod + SET == LINK else prod + SET
        self.assertEqual(seen[:7], [0, 0x200, 0x400, 0x600, 0x800, 0xA00, 0])

    def test_two_in_flight_sets_always_use_different_mailboxes(self):
        prod = 0
        in_flight = []
        for _ in range(64):
            in_flight.append(prod)
            if len(in_flight) > 2:
                in_flight.pop(0)
            boxes = [(start >> 9) & 1 for start in in_flight]
            self.assertEqual(len(boxes), len(set(boxes)))
            prod = 0 if prod + SET == LINK else prod + SET

    def test_mailbox_block_holds_one_set(self):
        self.assertEqual(SET >> 9, 1)
        self.assertGreaterEqual(MAILBOX, LINK + SET)


if __name__ == "__main__":
    unittest.main()
