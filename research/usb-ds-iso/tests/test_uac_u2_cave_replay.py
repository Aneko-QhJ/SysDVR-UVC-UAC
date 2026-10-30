"""Replay the A23 and U2 producer caves with Unicorn (optional dependency).

Skips when unicorn or the devkitA64 toolchain is unavailable; the replay only
compares instructions and memory, and never touches USB or SD.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")


class UacU2CaveReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("unicorn not installed (see UAC_U2_BURST.md)")
        if not (TOOLCHAIN / "aarch64-none-elf-gcc").is_file():
            raise unittest.SkipTest(f"missing toolchain {TOOLCHAIN}")
        from replay_uac_u2_cave import replay

        cls.report = replay(TOOLCHAIN)

    def test_ported_cave_builds_the_same_ring_as_a23(self):
        self.assertEqual(self.report["problems"], [])
        self.assertTrue(self.report["check_passed"])
        self.assertTrue(self.report["ring_identical"])

    def test_rejection_matrix_matches_the_precheck(self):
        cases = self.report["cases"]
        self.assertEqual(cases["u2/accept"]["outcome"], "accept")
        self.assertEqual(cases["a23/accept"]["outcome"], "accept")
        rejects = [name for name in cases if "/reject-" in name]
        self.assertEqual(len(rejects), 5)  # word, size, interval, speed, ring
        for name in rejects:
            self.assertEqual(cases[name]["outcome"], "reject", name)
            self.assertEqual(cases[name]["w0"], 0x1908C, name)

    def test_endpoint_ownership_is_exact(self):
        cases = self.report["cases"]
        self.assertEqual(cases["u2/accept"]["descriptor"], "8405c000")
        self.assertEqual(cases["u2/reject-word"]["descriptor"], "83010001")

    def test_replay_records_no_hardware_access(self):
        self.assertEqual(
            (self.report["usb_operations"], self.report["sd_accesses"]), (0, 0)
        )
        self.assertFalse(self.report["hardware_verified"])


if __name__ == "__main__":
    unittest.main()
