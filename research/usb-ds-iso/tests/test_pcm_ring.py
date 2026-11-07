"""Compile and run the host-side PCM ring test.

The ring is plain C (source/uvc/pcm_ring.c) so the same code runs in the
sysmodule and here: overflow drops the oldest bytes, underrun zero-fills and
counts, and the wrap arithmetic must survive 3072/4096-byte chunks.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "source" / "uvc"
C_TEST = Path(__file__).with_suffix(".c")


class PcmRingTests(unittest.TestCase):
    def test_host_build_and_run(self):
        cc = shutil.which("clang") or shutil.which("cc")
        if not cc:
            self.skipTest("no host C compiler")
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "test_pcm_ring"
            cmd = [
                cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I" + str(SRC), str(C_TEST), str(SRC / "pcm_ring.c"),
                "-o", str(exe),
            ]
            build = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stderr[-2000:])
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("pcm_ring: ok", run.stdout)


if __name__ == "__main__":
    unittest.main()
