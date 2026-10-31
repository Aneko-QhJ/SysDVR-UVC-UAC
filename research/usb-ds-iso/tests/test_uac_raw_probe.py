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
        self.assertIn("if (trigger_first && !no_trigger)", self.source)
        self.assertIn("if (!no_trigger && !trigger_first)", self.source)
        self.assertIn("libusb_submit_transfer", self.source)
        for token in ("libusb_fill_iso_transfer", "libusb_set_iso_packet_lengths",
                      "0x22, 0x01, 0x0100", "done transfers=%u packets=%u",
                      "on_iso_done", "concurrent transfers=%u",
                      "transfer[%u] status=%d", "packet[%u] status=%d"):
            self.assertIn(token, self.source)

    def test_claim_only_and_no_detach_options(self):
        for token in ("--claim-only", "--no-detach", "--no-trigger",
                      "--interface", "--endpoint", "--packets",
                      "--trigger-first", "--delay-ms", "--transfers",
                      "--timeout-ms"):
            self.assertIn(token, self.source)

    def test_binary_rejects_bad_packet_count(self):
        if not BINARY.is_file():
            self.skipTest(f"missing {BINARY}; run make -C host uac-raw-probe")
        for args, value, text in (
                ("--packets", "0", "packets must be"),
                ("--transfers", "0", "transfers must be"),
                ("--transfers", "33", "transfers must be"),
                ("--timeout-ms", "1", "timeout-ms must be")):
            result = subprocess.run([str(BINARY), args, value],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn(text, result.stderr)


if __name__ == "__main__":
    unittest.main()
