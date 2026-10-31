"""Derive the U2 endpoint-object offset from usb.elf and check the pre-check.

The app reads usb:ds endpoint state before posting; the address must match the
driver (0x2854 device, 0x2914/0xb44 manager construction, 0x302e0 object
indexing).  This test decodes those instructions instead of trusting a magic
constant.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_uac_descriptor_payload import load_elf_sections

ELF = ROOT / "private/module/usb.elf"
SOURCE = REPO / "source/uvc/uvc_device.c"


def _word(data, sections, address):
    for sec in sections.values():
        if sec["type"] != 8 and sec["addr"] <= address < sec["addr"] + sec["size"]:
            off = sec["offset"] + address - sec["addr"]
            return int.from_bytes(data[off:off + 4], "little")
    raise ValueError(f"{address:#x} outside mapped sections")


def _adr(word, pc):
    assert (word & 0x9F000000) == 0x10000000, hex(word)
    imm = (((word >> 5) & 0x7FFFF) << 2) | ((word >> 29) & 0x3)
    if imm & (1 << 20):
        imm -= 1 << 21
    return pc + imm


def _add_imm(word):
    assert (word & 0xFF800000) == 0x91000000, hex(word)
    imm = (word >> 10) & 0xFFF
    shift = (word >> 22) & 0x3
    assert shift in (0, 1), hex(word)
    return imm << (12 * shift)


def _movz_low(word):
    assert (word & 0xFFE00000) == 0x52800000, hex(word)
    return (word >> 5) & 0xFFFF


def _movk_imm(word):
    assert (word & 0xFFE00000) == 0x72A00000, hex(word)
    return (word >> 5) & 0xFFFF


def _bl_target(word, pc):
    assert (word & 0xFC000000) == 0x94000000, hex(word)
    imm = word & 0x3FFFFFF
    if imm & (1 << 25):
        imm -= 1 << 26
    return pc + (imm << 2)


def _ep_index(address):
    """0x3a30: IN endpoints map to 0x10 | number."""
    signed = address - 256 if address >= 128 else address
    return (0x10 | (address & 0xF)) if signed < 0 else (address & 0xF)


def _movz(word):
    assert (word & 0xFFE00000) == 0x52800000, hex(word)
    return (word >> 5) & 0xFFFF


class UacU2PrecheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ELF.is_file() or not SOURCE.is_file():
            raise unittest.SkipTest("missing usb.elf or uvc_device.c")
        cls.data, cls.sections = load_elf_sections(ELF)
        cls.source = SOURCE.read_text()

    def test_endpoint_object_offset_matches_the_driver(self):
        device = _adr(_word(self.data, self.sections, 0x2854), 0x2854)
        self.assertEqual(device, 0xD3000)
        init_arg = device + _add_imm(_word(self.data, self.sections, 0x2900))
        self.assertEqual(init_arg, 0xD9000)
        manager = init_arg + _add_imm(_word(self.data, self.sections, 0xB44))
        self.assertEqual(manager, 0xDA000)  # also x21 in the 2026-10-30 crash
        stride = _movz(_word(self.data, self.sections, 0x302F4))
        self.assertEqual(stride, 0x48)
        index = ((0x84 & 0xF) << 1) | ((0x84 >> 7) & 1)
        self.assertEqual(index, 9)
        offset = (manager + index * stride
                  + _add_imm(_word(self.data, self.sections, 0x30300))
                  + _add_imm(_word(self.data, self.sections, 0x30304)))
        self.assertEqual(offset, 0xFC300)
        self.assertIn("#define UAC_U2_EP_OBJ 0xFC300ULL", self.source)

    def test_install_markers_derive_from_the_installer(self):
        # 0x295d0 marks install_obj + 0x14d0 + index*16; 0x2a980 reads the
        # table pointer at install_obj + 0x14c8 + index*16.  install_obj is
        # not the manager: 0x30294/0x302a8 load it from manager + 0x229b8.
        manager = 0xDA000
        ptr_off = _movz(_word(self.data, self.sections, 0x30294))
        ptr_off |= _movk_imm(_word(self.data, self.sections, 0x30298)) << 16
        self.assertEqual(ptr_off, 0x229B8)
        self.assertEqual(manager + ptr_off, 0xFC9B8)
        # 0x302a8: ldr x0, [x21, x22]; 0x302c0: bl 0x2a980.
        self.assertEqual(_bl_target(_word(self.data, self.sections, 0x302C0),
                                    0x302C0), 0x2A980)
        flag_base = _movz(_word(self.data, self.sections, 0x29600))
        ptr_base = _movz(_word(self.data, self.sections, 0x2A9C4))
        self.assertEqual((flag_base, ptr_base), (0x14D0, 0x14C8))
        index = _ep_index(0x84)
        self.assertEqual(index, 0x14)

        # Both 2026-10-30 crash reports have complete_original's x0 (the
        # install object) and x21 (the manager): x0 - x21 = 0xa1038.
        import re
        reports = [
            ROOT / "private/runs/UAC-u2-precheck2-20261030/crash-usb-2.log",
            ROOT / "private/runs/UAC-u2-burst2-20261030/"
                   "crash-usb-0100000000000006.log",
        ]
        reports = [p for p in reports if p.is_file()]
        if not reports:
            self.skipTest("missing crash reports")
        for path in reports:
            text = path.read_text()
            x0 = int(re.search(r"X\[00\]:\s+([0-9a-fA-F]+)", text).group(1), 16)
            x21 = int(re.search(r"X\[21\]:\s+([0-9a-fA-F]+)", text).group(1), 16)
            self.assertEqual(x0 - x21, 0xA1038, path.name)

        bias = 0xA1038
        self.assertEqual(manager + bias, 0x17B038)
        self.assertEqual(manager + bias + flag_base + index * 16, 0x17C648)
        self.assertEqual(manager + bias + ptr_base + index * 16, 0x17C640)
        self.assertIn("#define UAC_U2_INSTALL_OBJ_PTR_OFFSET 0xFC9B8ULL",
                      self.source)
        self.assertIn("#define UAC_U2_INSTALL_OBJ_OFFSET 0x17B038ULL",
                      self.source)
        self.assertIn("#define UAC_U2_INSTALL_FLAG_OFF 0x1610ULL",
                      self.source)
        self.assertIn("#define UAC_U2_INSTALL_TABLE_OFF 0x1608ULL",
                      self.source)

    def test_speed_offset_derives_from_the_cave(self):
        manifest = ROOT / "private/analysis/UAC-u2-producer-20261030/manifest.json"
        if not manifest.is_file():
            self.skipTest("missing cave manifest")
        import json
        doc = json.loads(manifest.read_text())
        cave = bytes.fromhex(next(e["after"] for e in doc["edits"]
                                  if int(e["address"], 16) == 0x68D54))
        # 0x68d80: add x6, x0, #0x22, lsl #12
        add = int.from_bytes(cave[0x68D80 - 0x68D54:][:4], "little")
        # 0x68d84: ldr w9, [x6, #0xa58]
        ldr = int.from_bytes(cave[0x68D84 - 0x68D54:][:4], "little")
        self.assertEqual((add & 0xFF800000), 0x91000000)
        imm = ((add >> 10) & 0xFFF) << (12 * ((add >> 22) & 3))
        self.assertEqual((ldr & 0xFFC00000), 0xB9400000)
        off = ((ldr >> 10) & 0xFFF) * 4  # LDR W scales the imm12 by 4
        self.assertEqual((imm, off), (0x22000, 0xA58))
        self.assertEqual(0xDA000 + imm + off, 0xFCA58)
        self.assertIn("#define UAC_U2_SPEED_OFFSET 0xFCA58ULL", self.source)
        self.assertIn("_uacLogRingState", self.source)

    def test_precheck_reads_the_fields_the_cave_checks(self):
        start = self.source.index("static void _postUacBurst(void)")
        body = self.source[start:self.source.index("\n}\n", start)]
        precheck = body.index("_uacReadUsbState")
        post = body.index("usbDsEndpoint_PostBufferAsync")
        self.assertLess(precheck, post)  # never post before the state read
        for token in ("word != 0x00C00584u", "ep.state[6] != 4", "ep.speed != 3",
                      "ring == 0", "prod != cons", "installed=%u flag1=%u table=0x%llx",
                      "ep.state[0x42] != 9",
                      "ep.installed != 1 || ep.table_ptr == 0",
                      "UAC U2 post skipped: install object not ready"):
            self.assertIn(token, body)
        self.assertIn("#define UAC_U2_SPEED_OFFSET 0xFCA58ULL", self.source)
        post_rc = body.index("UAC U2 post rc=")
        ring = body.index("_uacLogRingState();", post_rc)
        wait = body.index("eventWait(", post_rc)
        self.assertLess(ring, wait)  # dump before the completion can clear it

    def test_reader_attaches_only_briefly(self):
        start = self.source.index("static bool _uacReadUsbState")
        body = self.source[start:self.source.index("\n}\n", start)]
        self.assertIn("svcDebugActiveProcess(&h, g_uacUsbPid)", body)
        self.assertIn("svcReadDebugProcessMemory(out->state, h,", body)
        self.assertIn("svcCloseHandle(h)", body)
        # The patch applier must not keep the session open.
        patch = self.source[self.source.index("static bool _applyUacPatch("):]
        patch = patch[:patch.index("\n}\n")]
        self.assertIn("svcCloseHandle(debug)", patch)

    def test_reject_path_is_the_fatal_one(self):
        # reject_original returns 0x1908c ...
        lo = _movz_low(_word(self.data, self.sections, 0x30394))
        hi = _movk_imm(_word(self.data, self.sections, 0x30398))
        self.assertEqual(lo, 0x908C)
        self.assertEqual(hi, 1)
        # ... and the submit caller treats any non-zero result as an error and
        # calls complete_original (0x2a980), which is where the 2026-10-30
        # crash recursed.
        cbz = _word(self.data, self.sections, 0x30290)
        self.assertEqual(cbz & 0x7F000000, 0x34000000)  # cbz w0, ...
        self.assertEqual(_bl_target(_word(self.data, self.sections, 0x302C0),
                                    0x302C0), 0x2A980)

    def test_target_is_recorded_by_the_patch_applier(self):
        patch = self.source[self.source.index("static bool _applyUacPatch("):]
        patch = patch[:patch.index("\n}\n")]
        self.assertIn("g_uacUsbPid = pid", patch)
        self.assertIn("g_uacUsbBase = modules[0].base_address", patch)


if __name__ == "__main__":
    unittest.main()
