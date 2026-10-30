"""Safe-cave candidate: a rejected ISO submit returns 0 instead of 0x1908c."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_patch import CAVE, CAVE_END, validate_module
from build_uac_u2_producer import build_edits, payload_ready, render

NSO = ROOT / "private/module/exefs/main"
WORK = ROOT / "private/analysis/UAC-u2-safecave-20261030"
ASM = ROOT / "patches/iso_burst_uac84_safe.S"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")


class UacU2SafeCaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK / "manifest.json").is_file() or not ASM.is_file():
            raise unittest.SkipTest(f"missing {WORK}")
        if not NSO.is_file():
            raise unittest.SkipTest(f"missing {NSO}")
        cls.doc = payload_ready(WORK)
        cls.nso = validate_module(NSO.read_bytes())
        cls.cave = bytes.fromhex(
            next(e["after"] for e in cls.doc["edits"]
                 if int(e["address"], 16) == CAVE)
        )
        cls.symbols = {k: int(v, 16) for k, v in cls.doc["symbols"].items()}

    def test_payload_uses_the_safe_assembly(self):
        self.assertEqual(self.doc["assembly"], "patches/iso_burst_uac84_safe.S")
        self.assertEqual(self.doc["edit_count"], 30)
        self.assertEqual(len(self.cave), 668)
        self.assertLess(len(self.cave), CAVE_END - CAVE)
        addresses = {int(e["address"], 16) for e in self.doc["edits"]}
        self.assertNotIn(0x302C0, addresses)  # the global breaker stays out

    def test_safe_assembly_has_no_driver_reject_path(self):
        text = ASM.read_text()
        self.assertIn("fail_accept:", text)
        self.assertIn("mov w0, #0", text)
        self.assertNotIn("reject_original", text)
        self.assertNotIn("error:", text)

    def test_edits_match_the_elf_and_render(self):
        edits = build_edits(self.nso, self.cave, self.symbols)
        self.assertEqual(render(edits), (WORK / "uac_u2_payload.h").read_text())


class SafeCaveReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("unicorn not installed")
        if not (TOOLCHAIN / "aarch64-none-elf-gcc").is_file():
            raise unittest.SkipTest(f"missing toolchain {TOOLCHAIN}")
        from replay_uac_u2_cave import replay_safe

        cls.report = replay_safe(TOOLCHAIN)

    def test_rejected_submits_return_zero(self):
        self.assertEqual(self.report["problems"], [])
        self.assertTrue(self.report["check_passed"])
        rejects = [name for name in self.report["cases"] if "/reject-" in name]
        self.assertEqual(len(rejects), 5)
        for name in rejects:
            self.assertEqual(self.report["cases"][name]["w0"], 0, name)
            self.assertEqual(self.report["cases"][name]["pc"], 0x50000000, name)

    def test_accept_still_builds_the_a23_ring(self):
        self.assertTrue(self.report["ring_identical"])
        self.assertEqual(self.report["ring_sha256"][:16], "d50a387208d83975")


if __name__ == "__main__":
    unittest.main()
