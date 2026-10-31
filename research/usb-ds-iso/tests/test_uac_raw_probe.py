"""Static checks for the raw UAC alt1 ISO host probe."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "host/uac-raw-probe.c"
BINARY = ROOT / "host/uac-raw-probe"


class UacRawProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text() if SOURCE.is_file() else ""

    def test_tries_detach_before_claim(self):
        for token in ("libusb_set_auto_detach_kernel_driver",
                      "libusb_detach_kernel_driver",
                      "libusb_claim_interface",
                      "libusb_set_interface_alt_setting"):
            self.assertIn(token, self.source)
        detach = self.source.index("libusb_detach_kernel_driver")
        claim = self.source.index("libusb_claim_interface")
        self.assertLess(detach, claim)

    def test_submits_iso_before_the_set_cur_trigger(self):
        submit = self.source.index("libusb_submit_transfer")
        trigger = self.source.index("set_cur=")
        self.assertLess(submit, trigger)
        for token in ("libusb_fill_iso_transfer", "libusb_set_iso_packet_lengths",
                      "0x22, 0x01, 0x0100", "done packets=%u"):
            self.assertIn(token, self.source)

    def test_claim_only_and_no_detach_options(self):
        for token in ("--claim-only", "--no-detach", "--no-trigger",
                      "--interface", "--endpoint", "--packets"):
            self.assertIn(token, self.source)

    def test_binary_rejects_bad_packet_count(self):
        if not BINARY.is_file():
            self.skipTest(f"missing {BINARY}; run make -C host uac-raw-probe")
        result = subprocess.run([str(BINARY), "--packets", "0"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("packets must be", result.stderr)


if __name__ == "__main__":
    unittest.main()
