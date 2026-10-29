"""Unicorn check of the usb:ds configuration assembler with UAC sizes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

try:
    import unicorn  # noqa: F401
except ImportError:  # pragma: no cover - optional dependency
    unicorn = None

from emulate_uac_config_assembly import (
    BLOCKS_HS,
    BLOCKS_SS,
    EXPECTED,
    emulate,
    load_elf,
)

ROOT = Path(__file__).resolve().parents[1]
ELF = ROOT / "private/module/usb.elf"


@unittest.skipUnless(unicorn, "unicorn is not installed")
class UacConfigAssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ELF.is_file():
            raise unittest.SkipTest(f"missing {ELF}")
        cls.data, cls.sections = load_elf(ELF)
        from build_uac_descriptor_payload import EDITS

        cls.edits = EDITS

    def _run(self, config, speed, sizes, patched):
        return emulate(self.data, self.sections, self.edits, speed, sizes, patched)

    def test_hs_u8_truncation_and_patched_length(self):
        before = self._run("hs", 2, BLOCKS_HS, False)
        after = self._run("hs", 2, BLOCKS_HS, True)
        self.assertEqual(before["wTotalLength"], EXPECTED["hs"]["unpatched_u8"])
        self.assertEqual(before["getter_9"], 1)
        self.assertEqual(after["wTotalLength"], EXPECTED["hs"]["patched"])
        self.assertEqual(after["getter_9"], 9)
        self.assertEqual(after["getter_257"], 257)
        self.assertEqual(before["bNumInterfaces"], 4)
        self.assertEqual(after["bNumInterfaces"], 4)

    def test_ss_u8_truncation_and_patched_length(self):
        before = self._run("ss", 3, BLOCKS_SS, False)
        after = self._run("ss", 3, BLOCKS_SS, True)
        self.assertEqual(before["wTotalLength"], EXPECTED["ss"]["unpatched_u8"])
        self.assertEqual(before["getter_257"], EXPECTED["ss"]["unpatched_u8"])
        self.assertEqual(after["wTotalLength"], EXPECTED["ss"]["patched"])
        self.assertEqual(after["getter_257"], 257)  # request clamp
        self.assertEqual(before["bNumInterfaces"], 4)

    def test_payload_preserves_header(self):
        row = self._run("hs", 2, BLOCKS_HS, True)
        self.assertEqual(row["bLength"], 9)
        self.assertEqual(row["bDescriptorType"], 2)


if __name__ == "__main__":
    unittest.main()
