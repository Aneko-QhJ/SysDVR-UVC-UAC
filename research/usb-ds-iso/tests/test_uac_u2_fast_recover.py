"""v31 driver-side code-23 fast recovery.

The generic error branch at 0x31274 (code 23 = Missed Service lands here)
only sets the endpoint halt bit at regs+0x50 and polls the ack at regs+0x5c
before 0x31118 completes the URB with status 5.  It never resets the ring,
so the cave cannot re-arm: the app has to cancel and repost, which costs the
20-40 ms app round trip plus the 32 ms cave lead.

v31 replaces that halt dance with the driver's own endpoint setup
0x2feb0(manager, endpoint): ring reset, 64-byte context rewrite, commit at
regs+0x58 and the halt clear at regs+0x54/0x50.  The app still cancels on
status=5, but from a ring that is already at base and a halt that is already
clear.  This file decodes both instruction blocks instead of trusting the
constants in the builder.
"""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_descriptor_payload import load_elf_sections
from build_patch import read_mapped, validate_module

from build_uac_u2_producer import (
    FAST_RECOVER_ADDR,
    FAST_RECOVER_AFTER,
    FAST_RECOVER_BEFORE,
)

NOP = 0xD503201F

ELF = ROOT / "private/module/usb.elf"
NSO = ROOT / "private/module/exefs/main"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")

SETUP = 0x2FEB0            # driver endpoint setup: ring reset + commit + unhalt
COMPLETE = 0x31118         # complete the URB with status 5 and return
HALT0 = 0x50
HALT1 = 0x54
COMMIT = 0x58
ACK = 0x5C


def _word(data, sections, address):
    for sec in sections.values():
        if sec["type"] != 8 and sec["addr"] <= address < sec["addr"] + sec["size"]:
            off = sec["offset"] + address - sec["addr"]
            return int.from_bytes(data[off:off + 4], "little")
    raise ValueError(f"{address:#x} outside mapped sections")


def _words(data, sections, start, end):
    return [_word(data, sections, a) for a in range(start, end, 4)]


def _branch(word):
    """Decode B/BL; return (link, byte offset) or None."""
    opcode = word & 0xFC000000
    if opcode not in (0x14000000, 0x94000000):
        return None
    imm = word & 0x03FFFFFF
    if imm & 0x02000000:
        imm -= 0x04000000
    return opcode == 0x94000000, imm * 4


def _store_offset(word):
    if (word & 0xFFC00000) != 0xB9000000:
        return None
    return ((word >> 10) & 0xFFF) * 4


class UacU2FastRecoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ELF.is_file():
            raise unittest.SkipTest(f"missing {ELF}")
        cls.data, cls.sections = load_elf_sections(ELF)

    def test_setup_target_is_the_committing_endpoint_setup(self):
        # 0x2feb0 starts the driver endpoint setup: descriptor-type check then
        # the state byte clear.  It is the only reset path that commits and
        # clears both halt bits (see test_uac_u2_endpoint_context).
        self.assertEqual(_word(self.data, self.sections, SETUP), 0x39400428)
        self.assertEqual(_word(self.data, self.sections, SETUP + 4), 0x39010C3F)
        self.assertTrue(any(_store_offset(w) == COMMIT
                            for w in _words(self.data, self.sections,
                                            SETUP, 0x300AC)))
        self.assertTrue(any(_store_offset(w) == HALT1
                            for w in _words(self.data, self.sections,
                                            SETUP, 0x300AC)))
        self.assertTrue(any(_store_offset(w) == HALT0
                            for w in _words(self.data, self.sections,
                                            SETUP, 0x300AC)))

    def test_original_branch_only_sets_halt_and_never_rearms(self):
        words = _words(self.data, self.sections,
                       FAST_RECOVER_ADDR, FAST_RECOVER_ADDR + 0x50)
        # ldr x8,[x21,#8] / mov w11,#1 / lsl w20,w11,w9 / ldr w10,[x8,#0x50]
        self.assertEqual(words[0], 0xF94006A8)
        self.assertEqual(words[3], 0xB940510A)
        self.assertEqual(_store_offset(words[8]), HALT0)  # str w9,[x8,#0x50]
        # poll loop: ldr w9,[x8,#0x5c]! / tst w9,w20 / b.ne 0x312c0
        self.assertEqual(words[10], 0xB845CD09)
        targets = [(i * 4 + FAST_RECOVER_ADDR, _branch(w))
                   for i, w in enumerate(words) if _branch(w)]
        self.assertNotIn(SETUP, [t + off for t, (_, off) in targets])
        # The only unconditional branch in the block is the 50 us delay call;
        # the fall-through continues to the unchanged `b 0x31118` at 0x312c4.
        end_targets = [t + off for t, (_, off) in targets]
        self.assertEqual(end_targets, [0xBE80])

    def test_before_matches_the_module(self):
        if not NSO.is_file():
            self.skipTest(f"missing {NSO}")
        nso = validate_module(NSO.read_bytes())
        self.assertEqual(read_mapped(nso, FAST_RECOVER_ADDR, 0x50),
                         FAST_RECOVER_BEFORE)
        self.assertEqual(len(FAST_RECOVER_BEFORE), 0x50)
        self.assertEqual(len(FAST_RECOVER_AFTER), 0x50)

    def test_after_calls_setup_then_completes(self):
        words = struct.unpack("<20I", FAST_RECOVER_AFTER)
        self.assertEqual(words[0], 0xD1408AA0)  # sub x0,x21,#0x22,lsl#12
        self.assertEqual(words[1], 0xAA1303E1)  # mov x1,x19
        link, offset = _branch(words[2])
        self.assertTrue(link)
        self.assertEqual(FAST_RECOVER_ADDR + 8 + offset, SETUP)
        link, offset = _branch(words[3])
        self.assertFalse(link)
        self.assertEqual(FAST_RECOVER_ADDR + 12 + offset, COMPLETE)
        self.assertEqual(list(words[4:]), [NOP] * 16)

    def test_builder_adds_exactly_one_edit_behind_the_flag(self):
        if not NSO.is_file():
            self.skipTest(f"missing {NSO}")
        sys.path.insert(0, str(ROOT / "tools"))
        import build_uac_u2_producer as builder

        nso = validate_module(NSO.read_bytes())
        code = bytes.fromhex("1f2003d5") * 8
        symbols = {"iso_enter": 0x68D54, "iso_event": 0x68D5C}
        common = dict(report=False, driver_queue=True, driver_link=True,
                      driver_map_soft=True, driver_map_soft2=True)
        without = builder.build_edits(nso, code, symbols, **common)
        with_it = builder.build_edits(nso, code, symbols,
                                      driver_fast_recover=True, **common)
        self.assertEqual(len(with_it), len(without) + 1)
        added = [e for e in with_it if e[0] not in {x[0] for x in without}]
        self.assertEqual(len(added), 1)
        address, before, after, _reason = added[0]
        self.assertEqual(address, FAST_RECOVER_ADDR)
        self.assertEqual((before, after),
                         (FAST_RECOVER_BEFORE, FAST_RECOVER_AFTER))

    def test_assembly_encoding_matches_the_toolchain(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        import subprocess
        import tempfile

        source = (
            ".text\n"
            ".global entry\n"
            "entry:\n"
            "sub x0, x21, #0x22, lsl #12\n"
            "mov x1, x19\n"
            "bl rearm_endpoint\n"
            "b complete_original\n"
            + "nop\n" * 16
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "enc.S").write_text(source)
            # The snippet sits at 0x31274 so the two branches keep their
            # absolute targets; both destinations are within branch range.
            (tmp / "enc.ld").write_text(
                "SECTIONS { . = 0x31274; .text : { *(.text) } }\n"
                "rearm_endpoint = 0x2feb0;\n"
                "complete_original = 0x31118;\n")
            subprocess.run([str(TOOLCHAIN / "aarch64-none-elf-gcc"), "-c",
                            str(tmp / "enc.S"), "-o", str(tmp / "enc.o")],
                           check=True)
            subprocess.run([str(TOOLCHAIN / "aarch64-none-elf-ld"), "-T",
                            str(tmp / "enc.ld"), str(tmp / "enc.o"),
                            "-o", str(tmp / "enc.elf")], check=True)
            subprocess.run([str(TOOLCHAIN / "aarch64-none-elf-objcopy"),
                            "-O", "binary", "--only-section=.text",
                            str(tmp / "enc.elf"), str(tmp / "enc.bin")],
                           check=True)
            self.assertEqual((tmp / "enc.bin").read_bytes(), FAST_RECOVER_AFTER)


if __name__ == "__main__":
    unittest.main()
