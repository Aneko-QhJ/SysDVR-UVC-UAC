"""Checks the descriptor-only UAC runtime payload against the usb ELF."""
import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build_uac_descriptor_payload import (
    EDITS,
    ISO_ONLY_ADDRESSES,
    USB_BUILD_ID,
    USB_ELF_SHA256,
    load_elf_sections,
    manifest,
    render,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]
ELF = ROOT / "private/module/usb.elf"


class UacDescriptorPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ELF.is_file():
            raise unittest.SkipTest(f"missing {ELF}")
        cls.data = ELF.read_bytes()
        _, cls.sections = load_elf_sections(ELF)

    def test_edit_set_is_descriptor_only(self):
        self.assertEqual(len(EDITS), 18)
        addresses = [address for address, _, _ in EDITS]
        self.assertEqual(len(addresses), len(set(addresses)))
        self.assertFalse(set(addresses) & ISO_ONLY_ADDRESSES)
        self.assertNotIn(0x68D54, addresses)  # ISO cave
        self.assertNotIn(0x30364, addresses)  # iso_enter
        self.assertNotIn(0x30898, addresses)  # iso_event
        self.assertNotIn(0x2CBE0, addresses)  # iso_report

    def test_before_words_match_elf(self):
        validate(self.data, self.sections)
        self.assertEqual(
            hashlib.sha256(self.data).hexdigest(), USB_ELF_SHA256
        )

    def test_after_words_are_u16_forms(self):
        expected = {0x7908AAD5, 0x7948AAC8, 0x7948AAD5, 0x8B3542E0, 0x2A1503E8, 0x78686A68}
        for address, before, after in EDITS:
            self.assertIn(after, expected, hex(address))
            self.assertNotEqual(before, after)
            self.assertEqual(len(struct.pack("<I", after)), 4)

    def test_render_is_a_complete_isoruntimeedit_list(self):
        header = render()
        self.assertEqual(header.count("_before[]={"), 18)
        self.assertEqual(header.count("_after[]={"), 18)
        self.assertEqual(header.count("static const IsoRuntimeEdit uacRuntimeEdits[]"), 1)
        self.assertEqual(header.count("{0x"), 18)
        self.assertIn(
            "uacRuntimeBuildId[32]={" + ",".join(str(b) for b in USB_BUILD_ID) + "}",
            header,
        )

    def test_manifest_records_no_iso_edits(self):
        doc = manifest(render(), ELF)
        self.assertEqual(doc["edit_count"], 18)
        self.assertFalse(doc["includes_iso_edits"])
        self.assertEqual(doc["build_id"], USB_BUILD_ID.hex().upper())
        self.assertEqual(len(doc["edits"]), 18)


if __name__ == "__main__":
    unittest.main()
