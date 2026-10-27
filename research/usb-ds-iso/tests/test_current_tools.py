"""Smoke tests for the tools listed as current in tools/README.md.

These do not prove the tools' results; they only catch syntax/import/CLI
regressions before a hardware round.
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = [
    "build_a23_short24_path_span_candidate.py",
    "audit_a23_short24_path_span.py",
    "build_a23_short24_candidate.py",
    "audit_a23_short24_entry.py",
    "build_a23_short24_entry.py",
    "package_a23_short24.py",
    "analyze_a23_short24_session.py",
    "audit_a23_short24_sdk.py",
    "analyze_a23_audio_cadence.py",
]


class CurrentToolSmoke(unittest.TestCase):
    def test_tools_are_listed(self):
        index = (ROOT / "tools" / "README.md").read_text()
        for name in CURRENT:
            self.assertIn(name, index, f"{name} missing from tools/README.md")

    def test_help(self):
        for name in CURRENT:
            with self.subTest(tool=name):
                path = ROOT / "tools" / name
                self.assertTrue(path.is_file(), f"missing {name}")
                result = subprocess.run(
                    [sys.executable, str(path), "--help"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr[-800:])


if __name__ == "__main__":
    unittest.main()
