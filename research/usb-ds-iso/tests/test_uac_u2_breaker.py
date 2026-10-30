"""Breaker candidate: 0x302c0 error-completion NOP + completion-resubmit decode.

The 2026-10-30 precheck2 round showed the cave accepting our 3072-byte submit
and usb crashing afterwards.  The completion routine (0x2c690) re-submits the
request through vtable[+136] with the entry's own buffer/size, which the
3072-only cave rejects; the caller then calls complete_original (0x302c0) and
recurses.  This test validates the breaker payload and decodes that resubmit.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_patch import read_mapped, validate_module
from build_uac_descriptor_payload import load_elf_sections
from build_uac_u2_producer import (
    BREAKER_AFTER,
    BREAKER_BEFORE,
    BREAKER_HOOK,
    EDITS_COUNT_BREAKER,
    build_edits,
    payload_ready,
    render,
)

NSO = ROOT / "private/module/exefs/main"
ELF = ROOT / "private/module/usb.elf"
WORK = ROOT / "private/analysis/UAC-u2-breaker-20261030"


class UacU2BreakerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK / "manifest.json").is_file():
            raise unittest.SkipTest(f"missing {WORK}")
        if not NSO.is_file():
            raise unittest.SkipTest(f"missing {NSO}")
        cls.doc = payload_ready(WORK)
        cls.nso = validate_module(NSO.read_bytes())
        cls.cave = bytes.fromhex(
            next(e["after"] for e in cls.doc["edits"]
                 if int(e["address"], 16) == 0x68D54)
        )
        cls.symbols = {k: int(v, 16) for k, v in cls.doc["symbols"].items()}

    def test_breaker_payload_has_31_edits(self):
        self.assertTrue(self.doc["breaker"])
        self.assertEqual(self.doc["edit_count"], EDITS_COUNT_BREAKER)
        self.assertEqual(self.doc["edit_count"], 31)
        self.assertEqual(self.doc["counts"]["branch"], 4)
        entry = next(e for e in self.doc["edits"]
                     if int(e["address"], 16) == BREAKER_HOOK)
        self.assertEqual(entry["before"], BREAKER_BEFORE.hex())
        self.assertEqual(entry["after"], BREAKER_AFTER.hex())

    def test_edits_match_the_elf_and_render(self):
        edits = build_edits(self.nso, self.cave, self.symbols, breaker=True)
        self.assertEqual(render(edits), (WORK / "uac_u2_payload.h").read_text())
        self.assertEqual(len(edits), EDITS_COUNT_BREAKER)

    def test_breaker_nops_only_the_error_completion(self):
        # Apply the edits to a copy of the module image and inspect the call site.
        image = bytearray(self.nso.sections[0]["content"])
        for address, before, after, _reason in build_edits(
                self.nso, self.cave, self.symbols, breaker=True):
            image[address:address + len(after)] = after
        self.assertEqual(int.from_bytes(image[0x302C0:0x302C4], "little"), 0xD503201F)
        # The rest of the error path is untouched.
        for address, word in ((0x302C4, 0x2A1403E0),   # mov w0, w20
                              (0x302C8, 0xA9424FF4),   # ldp x20, x19, [sp, #32]
                              (0x302D4, 0xD65F03C0)):  # ret
            self.assertEqual(int.from_bytes(image[address:address + 4], "little"), word,
                             hex(address))


class CompletionResubmitDecodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ELF.is_file():
            raise unittest.SkipTest(f"missing {ELF}")
        cls.data, cls.sections = load_elf_sections(ELF)

    def word(self, address):
        for sec in self.sections.values():
            if sec["type"] != 8 and sec["addr"] <= address < sec["addr"] + sec["size"]:
                off = sec["offset"] + address - sec["addr"]
                return int.from_bytes(self.data[off:off + 4], "little")
        raise ValueError(hex(address))

    def test_completion_resubmits_with_the_entry_size(self):
        # 0x2c81c..0x2c848: submit(x0 = [x20+96] (controller),
        # w1 = u8 [x20+112] (endpoint address, 0x84),
        # x2 = [entry+16] (buffer), w3 = min([entry+32] (size), [x20+116])).
        expected = {
            0x2C81C: 0xF9403280,  # ldr x0, [x20, #96]
            0x2C824: 0xB940768A,  # ldr w10, [x20, #116]
            0x2C828: 0x3941C281,  # ldrb w1, [x20, #112]
            0x2C830: 0xB9402109,  # ldr w9, [x8, #32]
            0x2C834: 0xF9400902,  # ldr x2, [x8, #16]
            0x2C840: 0xF9404508,  # ldr x8, [x8, #136]
            0x2C844: 0x1A8A3123,  # csel w3, w9, w10, cc
            0x2C848: 0xD63F0100,  # blr x8
        }
        for address, word in expected.items():
            self.assertEqual(self.word(address), word, hex(address))

    def test_resubmit_size_is_not_pinned_to_3072(self):
        # The size comes from the completed request entry ([x8+32]) clamped by
        # the endpoint limit; only the first submit from the app carries 3072.
        # The cave's `cmp w3, #3072` therefore rejects a follow-up submit whose
        # entry size differs, which is what the breaker at 0x302c0 contains.
        self.assertEqual(self.word(0x2C830), 0xB9402109)  # ldr w9, [x8, #32]
        self.assertEqual(self.word(0x2C844), 0x1A8A3123)  # csel w3, w9, w10, cc


if __name__ == "__main__":
    unittest.main()
