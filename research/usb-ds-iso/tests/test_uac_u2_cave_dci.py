"""The UAC cave must filter the EP0x84 DCI (9), not A23's EP0x83 DCI (7)."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UAC_CAVE = ROOT / "patches/iso_burst_uac84_dci9_noreport.S"
A23_CAVE = ROOT / "patches/iso_burst_uac84_noreport.S"


class UacCaveDciTests(unittest.TestCase):
    def test_uac_event_filter_uses_dci_9(self):
        source = UAC_CAVE.read_text()
        self.assertIn("cmp w9, #9 /* UAC EP0x84 DCI", source)
        self.assertNotIn("cmp w9, #7", source)
        self.assertIn("mov w10, #0x584", source)

    def test_original_port_still_uses_dci_7(self):
        source = A23_CAVE.read_text()
        self.assertIn("cmp w9, #7", source)


if __name__ == "__main__":
    unittest.main()
