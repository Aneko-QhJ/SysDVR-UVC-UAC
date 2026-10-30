"""Static checks for the U2 retrigger round: device skip log and host loop."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE = REPO / "source/uvc/uvc_device.c"
HOST = ROOT / "host/uac-control.c"
BINARY = ROOT / "host/uac-control"
DOC = ROOT / "docs/UAC_U2_BURST.md"


class UacU2RetriggerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for path in (SOURCE, HOST, DOC):
            if not path.is_file():
                raise unittest.SkipTest(f"missing {path}")
        cls.source = SOURCE.read_text()
        cls.host = HOST.read_text()
        cls.doc = DOC.read_text()

    def test_device_logs_every_alt_miss_before_the_post(self):
        start = self.source.index("static void _postUacBurst(void)")
        body = self.source[start:self.source.index("\n}\n", start)]
        self.assertIn('LOG("UAC U2 skip alt=%u ep=%u\\n"', body)
        skip = body.index("UAC U2 skip")
        posted = body.index("burstPosted")
        self.assertLess(skip, posted)  # the skip precedes the one-shot guard
        self.assertIn("usbDsEndpoint_PostBufferAsync", body)

    def test_host_can_repeat_the_set_cur_trigger(self):
        for token in ("--repeat=", "--interval-ms=", "repeat < 1 || repeat > 1000",
                      "interval_ms < 5 || interval_ms > 1000"):
            self.assertIn(token, self.host)
        self.assertIn("for (int n = 0; n < repeat; ++n)", self.host)
        self.assertIn("SET_CUR retrigger (ep)", self.host)
        self.assertIn("usleep((useconds_t)interval_ms * 1000)", self.host)

    def test_host_can_require_alt1_before_set_cur(self):
        for token in ("--require-alt1", "require_alt1",
                      "alt1 required but GET_INTERFACE=%u; not sending SET_CUR",
                      "--require-alt1 cannot be combined with --alt-only"):
            self.assertIn(token, self.host)
        # The abort must come before the SET_CUR loop.
        abort = self.host.index("not sending SET_CUR")
        set_cur = self.host.index("SET_CUR rate 48k (ep)")
        self.assertLess(abort, set_cur)

    def test_host_can_force_alt1_before_set_cur(self):
        for token in ("--force-alt1", "SET_INTERFACE(1) force",
                      "GET_INTERFACE forced", "SET_INTERFACE(0) restore force",
                      "--force-alt1 cannot be combined with --alt-only"):
            self.assertIn(token, self.host)
        force = self.host.index("SET_INTERFACE(1) force")
        set_cur = self.host.index("SET_CUR rate 48k (ep)")
        self.assertLess(force, set_cur)

    def test_binary_rejects_force_alt1_with_alt_only(self):
        if not BINARY.is_file():
            self.skipTest(f"missing {BINARY}; run make -C host")
        result = subprocess.run([str(BINARY), "--force-alt1", "--alt-only"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be combined", result.stderr)

    def test_binary_rejects_require_alt1_with_alt_only(self):
        if not BINARY.is_file():
            self.skipTest(f"missing {BINARY}; run make -C host")
        result = subprocess.run([str(BINARY), "--require-alt1", "--alt-only"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be combined", result.stderr)

    def test_binary_rejects_out_of_range_repeat(self):
        if not BINARY.is_file():
            self.skipTest(f"missing {BINARY}; run make -C host")
        result = subprocess.run([str(BINARY), "--repeat=0"], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("repeat", result.stderr)
        result = subprocess.run([str(BINARY), "--interval-ms=1"], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 2)

    def test_doc_records_the_retrigger_plan(self):
        self.assertIn("--repeat=", self.doc)
        self.assertIn("UAC U2 skip", self.doc)
        self.assertIn("burstPosted", self.doc)


if __name__ == "__main__":
    unittest.main()
