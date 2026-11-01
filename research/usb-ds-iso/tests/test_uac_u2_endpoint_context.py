"""Derive the U2 endpoint context/commit model from usb.elf.

v23 finding: the installer 0x295d0 only walks descriptors; the controller is
armed by the endpoint setup path 0x2fd30 -> 0x2fd80 + 0x2feb0, which writes a
64-byte endpoint context (state + TR dequeue pointer) and then commits it by
writing regs+0x58.  The completion error path 0x30ff4 rewrites the same ring
and context after a burst but never commits and never clears the halt bits,
so the controller keeps its stale state.

These tests decode the instructions instead of trusting constants, and they
check the v23 re-arm cave against the same model.  No assembler, Switch or
hardware is needed except for the optional assembly test.
"""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_descriptor_payload import load_elf_sections

ELF = ROOT / "private/module/usb.elf"
REARM = ROOT / "patches/iso_burst_uac84_dci9_rearm.S"
DCI9_CAVE = ROOT / "patches/iso_burst_uac84_dci9_noreport.S"
A23_CAVE = ROOT / "patches/iso_burst_uac84_noreport.S"
BUILDER = ROOT / "tools/build_uac_u2_producer.py"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")

# 0x302e0: endpoint object = controller + 0x22000 + dci * 0x48 + 0x78.
ENDPOINT_AREA = 0x22000
ENDPOINT_STRIDE = 0x48
ENDPOINT_OBJECT = 0x78

# Register offsets used by the endpoint setup/commit path.
REG_COMMIT = 0x58
REG_HALT0 = 0x50
REG_HALT1 = 0x54
REG_ACK = 0x5C


def _word(data, sections, address):
    for sec in sections.values():
        if sec["type"] != 8 and sec["addr"] <= address < sec["addr"] + sec["size"]:
            off = sec["offset"] + address - sec["addr"]
            return int.from_bytes(data[off:off + 4], "little")
    raise ValueError(f"{address:#x} outside mapped sections")


def _words(data, sections, start, end):
    return [_word(data, sections, a) for a in range(start, end, 4)]


def _str_imm_offset(word):
    """Return the byte offset of a 32-bit `str w?, [x?, #imm]`, else None."""
    if (word & 0xFFC00000) != 0xB9000000:
        return None
    return ((word >> 10) & 0xFFF) * 4


def _ldr64_imm_offset(word):
    if (word & 0xFFC00000) != 0xF9400000:
        return None
    return ((word >> 10) & 0xFFF) * 8


def _ldrb_imm_offset(word):
    if (word & 0xFFC00000) != 0x39400000:
        return None
    return (word >> 10) & 0xFFF


def _add_imm(word):
    assert (word & 0xFF800000) == 0x91000000, hex(word)
    return ((word >> 10) & 0xFFF) << (12 * ((word >> 22) & 0x3))


def _movz(word):
    assert (word & 0xFFE00000) == 0x52800000, hex(word)
    return (word >> 5) & 0xFFFF


def _ep_index(address):
    return ((address & 0xF) << 1) | ((address >> 7) & 1)


def _endpoint_object(dci):
    return ENDPOINT_AREA + dci * ENDPOINT_STRIDE + ENDPOINT_OBJECT


class UacU2EndpointContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ELF.is_file():
            raise unittest.SkipTest(f"missing {ELF}")
        cls.data, cls.sections = load_elf_sections(ELF)

    def _range_has_store(self, start, end, offset):
        return any(_str_imm_offset(w) == offset
                   for w in _words(self.data, self.sections, start, end))

    def test_context_entry_is_dci_indexed_64_byte_record(self):
        # 0x30bf0: ldr x11,[x8,#80]  -> [controller+0x22050] context array
        # 0x30bf4: ldrb w12,[x19,#66] -> dci
        # 0x30bf8: add x22,x11,x12,lsl#6 -> 64-byte entries
        self.assertEqual(_ldr64_imm_offset(
            _word(self.data, self.sections, 0x30BF0)), 0x50)
        self.assertEqual(_word(self.data, self.sections, 0x30BF4), 0x39410A6C)
        self.assertEqual(_word(self.data, self.sections, 0x30BF8), 0x8B0C1976)

    def test_context_install_writes_state_and_tr_dequeue(self):
        # state = (old & ~7) | 1 at context word0
        self.assertEqual(_word(self.data, self.sections, 0x30C10), 0x121D716B)
        self.assertEqual(_word(self.data, self.sections, 0x30C14), 0x3200016B)
        self.assertEqual(_str_imm_offset(
            _word(self.data, self.sections, 0x30C18)), 0)
        # interval is loaded from the endpoint object and placed in bits 16..23
        self.assertEqual(_ldrb_imm_offset(
            _word(self.data, self.sections, 0x30C1C)), 6)
        self.assertEqual(_word(self.data, self.sections, 0x30C24), 0x33101D6C)
        self.assertEqual(_str_imm_offset(
            _word(self.data, self.sections, 0x30C28)), 0)
        # TR dequeue low word + DCS: 0x30d2c loads [ep+0x40] cycle, 0x30d38
        # stores the pointer low word with bit0 replaced by the cycle.
        self.assertEqual(_ldrb_imm_offset(
            _word(self.data, self.sections, 0x30D2C)), 0x40)  # cycle
        self.assertEqual(_str_imm_offset(
            _word(self.data, self.sections, 0x30D38)), 8)
        self.assertEqual(_str_imm_offset(
            _word(self.data, self.sections, 0x30D28)), 12)
        # physical address comes from the driver translation helper.
        self.assertEqual(_word(self.data, self.sections, 0x30D0C) & 0xFC000000,
                         0x94000000)  # bl translation helper

    def test_setup_commits_and_clears_the_halt_bits(self):
        # 0x2feb0 (endpoint setup) is the only ring-reset path that commits.
        self.assertTrue(self._range_has_store(0x2FEB0, 0x300AC, REG_COMMIT))
        self.assertTrue(self._range_has_store(0x2FEB0, 0x300AC, REG_HALT1))
        self.assertTrue(self._range_has_store(0x2FEB0, 0x300AC, REG_HALT0))
        # commit is written and polled before the halt clear (0x2ffa4/0x2ffb4)
        self.assertEqual(_str_imm_offset(
            _word(self.data, self.sections, 0x2FFA4)), REG_COMMIT)
        self.assertEqual(
            (_word(self.data, self.sections, 0x2FFB4) >> 10) & 0xFFF,
            REG_COMMIT // 4)
        # acknowledge each halt clear through regs+0x5c
        self.assertEqual(_add_imm(
            _word(self.data, self.sections, 0x30024)), REG_ACK)
        self.assertEqual(_str_imm_offset(
            _word(self.data, self.sections, 0x30028)), 0)
        self.assertEqual(_add_imm(
            _word(self.data, self.sections, 0x30078)), REG_ACK)
        self.assertEqual(_str_imm_offset(
            _word(self.data, self.sections, 0x30080)), 0)

    def test_completion_error_reset_does_not_commit(self):
        # 0x30ff4..0x31118: ack regs+0x78, set regs+0x50 halt, memset ring,
        # rewrite context, but no regs+0x58 commit and no halt clear.
        self.assertTrue(self._range_has_store(0x30FF4, 0x31118, REG_HALT0))
        self.assertFalse(self._range_has_store(0x30FF4, 0x31118, REG_COMMIT))
        self.assertFalse(self._range_has_store(0x30FF4, 0x31118, REG_HALT1))
        # the same reset sequence zeroes the ring and reinstalls the context
        self.assertEqual(_word(self.data, self.sections, 0x310C0) & 0xFC000000,
                         0x94000000)  # bl 0x30b50 from the reset block

    def test_cancel_style_reset_does_not_commit(self):
        # 0x30470 resets the ring and performs the halt handshake when the
        # context state is 1, but it never commits the new context either.
        self.assertTrue(self._range_has_store(0x30470, 0x30630, REG_HALT1))
        self.assertFalse(self._range_has_store(0x30470, 0x30630, REG_COMMIT))

    def test_endpoint_objects_are_dci_7_and_dci_9_slots(self):
        stride = _movz(_word(self.data, self.sections, 0x302F4))
        self.assertEqual(stride, ENDPOINT_STRIDE)
        area = _add_imm(_word(self.data, self.sections, 0x30300))
        self.assertEqual(area, ENDPOINT_AREA)
        tail = _add_imm(_word(self.data, self.sections, 0x30304))
        self.assertEqual(tail, ENDPOINT_OBJECT)
        self.assertEqual(_ep_index(0x83), 7)
        self.assertEqual(_ep_index(0x84), 9)
        self.assertEqual(_endpoint_object(7), 0x22270)  # ISO_ENTRY 0x270
        self.assertEqual(_endpoint_object(9), 0x22300)  # ISO_ENTRY 0x300

    def test_v23_cave_replays_the_setup_path_once_per_burst(self):
        text = REARM.read_text()
        self.assertIn("bl rearm_endpoint", text)
        self.assertIn("stp x0, x1, [sp, #-16]!", text)
        self.assertIn("ldp x2, x30, [sp], #16", text)
        # the same acceptance gate and the DCI-9 filter stay in place
        self.assertIn("cmp w9, #9", text)
        self.assertIn("cmp x8, x9", text)
        self.assertIn("b.ne fail_accept", text)
        # one variable: ISO_ENTRY stays at the A23 value for this round
        self.assertIn(".equ ISO_ENTRY, 0x270", text)

    def test_builder_links_the_driver_setup_symbol(self):
        text = BUILDER.read_text()
        self.assertIn("rearm_endpoint = 0x2feb0", text)

    def test_rearm_cave_assembles_to_a_call_into_the_driver(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        sys.path.insert(0, str(ROOT / "tools"))
        from build_uac_u2_producer import assemble

        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            code, symbols = assemble(TOOLCHAIN, Path(tmp), REARM,
                                     require_report=False)
        self.assertLessEqual(len(code), 0x69000 - 0x68D54)
        self.assertGreater(len(code), 0)
        # find the bl whose word encodes a call to 0x2feb0
        hits = []
        for pc in range(symbols["iso_enter"], symbols["iso_enter"] + len(code), 4):
            word = code[pc - symbols["iso_enter"]:pc - symbols["iso_enter"] + 4]
            if len(word) < 4:
                break
            w = int.from_bytes(word, "little")
            if (w & 0xFC000000) == 0x94000000:
                imm = w & 0x3FFFFFF
                if imm & (1 << 25):
                    imm -= 1 << 26
                if (pc + (imm << 2)) & 0xFFFFFFFF == 0x2FEB0:
                    hits.append(pc)
        self.assertEqual(len(hits), 1, [hex(h) for h in hits])
        self.assertLess(hits[0], symbols["iso_event"])


class UacU2EndpointContextSourceTests(unittest.TestCase):
    def test_known_iso_entry_mismatch_is_documented(self):
        # The DCI-9 caves compare 9 but still read the DCI-7 object; the v23
        # round deliberately keeps that constant (one variable at a time).
        dci9 = DCI9_CAVE.read_text()
        self.assertIn("cmp w9, #9", dci9)
        self.assertIn(".equ ISO_ENTRY, 0x270", dci9)
        # the A23 original is correct: DCI 7 -> 0x270.
        a23 = A23_CAVE.read_text()
        self.assertIn("cmp w9, #7", a23)
        self.assertIn(".equ ISO_ENTRY, 0x270", a23)


if __name__ == "__main__":
    unittest.main()
