"""Compile and run the host-side UAC descriptor/state-machine test.

No Switch, USB, SD or libnx: uac_standard.c is built with -DUAC_STANDALONE
against the same source file the sysmodule uses.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "source" / "uvc"
C_TEST = Path(__file__).with_suffix(".c")


class UacStandardTests(unittest.TestCase):
    def test_host_build_and_run(self):
        cc = shutil.which("clang") or shutil.which("cc")
        if not cc:
            self.skipTest("no host C compiler")
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "test_uac_standard"
            cmd = [
                cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-DUAC_STANDALONE",
                f"-I{SRC}", str(C_TEST), str(SRC / "uac_standard.c"), "-o", str(exe),
            ]
            build = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stderr[-2000:])
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("uac_standard: ok", run.stdout)


if __name__ == "__main__":
    unittest.main()
