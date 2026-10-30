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

    def test_precheck_reads_the_fields_the_cave_checks(self):
        start = self.source.index("static void _postUacBurst(void)")
        body = self.source[start:self.source.index("\n}\n", start)]
        precheck = body.index("_uacReadUsbState")
        post = body.index("usbDsEndpoint_PostBufferAsync")
        self.assertLess(precheck, post)  # never post before the state read
        for token in ("word != 0x00C00584u", "state[6] != 4", "speed != 3",
                      "ring == 0", "prod != cons",
                      "UAC U2 post skipped: endpoint not ready for the cave"):
            self.assertIn(token, body)
        self.assertIn("#define UAC_U2_SPEED_OFFSET 0x22A58ULL", self.source)

    def test_reader_attaches_only_briefly(self):
        start = self.source.index("static bool _uacReadUsbState")
        body = self.source[start:self.source.index("\n}\n", start)]
        self.assertIn("svcDebugActiveProcess(&h, g_uacUsbPid)", body)
        self.assertIn("svcReadDebugProcessMemory(state, h,", body)
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
