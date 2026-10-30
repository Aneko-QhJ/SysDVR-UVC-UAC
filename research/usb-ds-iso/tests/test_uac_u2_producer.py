"""Static checks for the U2 AS alt1 producer payload and its wiring.

The cave itself is assembled by tools/build_uac_u2_producer.py; these tests
re-derive the 30-edit plan from the generated cave and validate every before
word against the usb NSO, without an assembler or a Switch.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build_patch import CAVE, CAVE_END, validate_module
from build_uac_descriptor_payload import EDITS as DESCRIPTOR_EDITS
from build_uac_u2_base_payload import NOP_EDITS
from build_uac_u2_producer import (
    ASM,
    EDITS_COUNT,
    ENDPOINT_WORD,
    build_edits,
    endpoint_constants_ok,
    payload_ready,
    render,
)

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
NSO = ROOT / "private/module/exefs/main"
WORK = ROOT / "private/analysis/UAC-u2-producer-20261030"
HOST = ROOT / "host/uac-burst.c"
SOURCE = REPO / "source/uvc/uvc_device.c"


class UacU2ProducerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NSO.is_file():
            raise unittest.SkipTest(f"missing {NSO}")
        cls.nso = validate_module(NSO.read_bytes())
        cls.doc = payload_ready(WORK)
        cls.cave = bytes.fromhex(
            next(e["after"] for e in cls.doc["edits"]
                 if int(e["address"], 16) == CAVE)
        )
        cls.symbols = {k: int(v, 16) for k, v in cls.doc["symbols"].items()}

    def test_payload_is_complete(self):
        self.assertEqual(self.doc["edit_count"], EDITS_COUNT)
        self.assertEqual(EDITS_COUNT, 30)
        self.assertEqual(self.doc["counts"],
                         {"cave": 1, "branch": 3,
                          "descriptor": len(DESCRIPTOR_EDITS), "nop": len(NOP_EDITS)})

    def test_cave_fills_the_rx_padding_page(self):
        self.assertEqual(len(self.cave), CAVE_END - CAVE)
        self.assertEqual(len(self.cave), 684)
        self.assertTrue(endpoint_constants_ok(self.cave))

    def test_endpoint_is_uac_alt1_not_the_vendor_endpoint(self):
        self.assertEqual(ENDPOINT_WORD, 0x00C00584)
        self.assertEqual(self.doc["endpoint"]["attributes"], "0x05")
        self.assertEqual(self.doc["endpoint"]["max_packet"], 192)
        self.assertEqual(self.doc["burst_bytes"], 16 * 192)

    def test_edits_match_the_elf_and_render_is_stable(self):
        edits = build_edits(self.nso, self.cave, self.symbols)
        header = render(edits)
        self.assertEqual(
            header, (WORK / "uac_u2_payload.h").read_text()
        )
        self.assertEqual(
            [(e["address"], e["before"], e["after"]) for e in self.doc["edits"]],
            [(hex(a), b.hex(), c.hex()) for a, b, c, _r in edits],
        )
        self.assertEqual(header.count("static const IsoRuntimeEdit uacU2Edits[]"), 1)
        self.assertEqual(header.count("_before[]={"), 30)

    def test_assembly_targets_only_the_uac_endpoint(self):
        text = ASM.read_text()
        self.assertIn("mov w10, #0x584", text)
        self.assertIn("movk w10, #0x00c0, lsl #16", text)
        self.assertIn("mov w1, #0x84", text)
        self.assertIn("cmp w8, #0x84", text)
        self.assertNotIn("#0x183", text)
        self.assertNotIn("mov w1, #0x83", text)
        self.assertNotIn("cmp w8, #0x83", text)

    def test_host_submits_before_the_set_cur_trigger(self):
        text = HOST.read_text()
        submit = text.index("libusb_submit_transfer(transfer)")
        trigger = text.index("libusb_control_transfer(device, 0x22")
        self.assertLess(submit, trigger)
        self.assertIn("--trigger-delay-ms", text)

    def test_source_wires_the_payload_and_one_shot_trigger(self):
        text = SOURCE.read_text()
        self.assertIn('#include "uac_u2_payload.h"', text)
        self.assertIn("static bool _applyUacU2Patch(void)", text)
        self.assertIn("patch_ok = _applyUacU2Patch();", text)
        self.assertIn("_postUacBurst();", text)
        self.assertIn("if (g_uacCtx.burstPosted) return;", text)
        self.assertIn("g_uacStd.alt_setting != 1", text)
        # The applier body must stay generic: no per-payload edit lists.
        start = text.index("static bool _applyUacPatch(")
        body = text[start:text.index("\n}\n", start)]
        self.assertNotIn("uacU2Edits", body)
        self.assertIn("0x369000", body)


if __name__ == "__main__":
    unittest.main()
