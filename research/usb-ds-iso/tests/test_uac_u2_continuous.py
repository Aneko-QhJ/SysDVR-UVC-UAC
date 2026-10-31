"""Offline checks for the v15 sequential-burst candidate and the host re-arm.

The runtime payload is identical to v14 (only the app-side post count and the
host probe changed), so these checks pin the invariants that make the four
bursts safe: one ISO request pending at a time, a cancel on timeout, a 1..4
bound, and a 1 kHz phase that continues across buffers.  The host checks pin
the rolling re-arm window that keeps URBs queued for every cave TD.

No USB, SD, SDK or hardware access.
"""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE = REPO / "source/uvc/uvc_device.c"
HOST = ROOT / "host/uac-raw-probe.c"
BINARY = ROOT / "host/uac-raw-probe"
WORK15 = ROOT / "private/analysis/UAC-u2-v15-continuous-20261101"
WORK14 = ROOT / "private/analysis/UAC-u2-v14-dci9-20261031"
NM = Path("/opt/devkitpro/devkitA64/bin/aarch64-none-elf-nm")


def post_body(source):
    start = source.index("static void _postUacBurst(void)")
    return source[start:source.index("\n}\n", start)]


def buffer_symbol_size(elf):
    if not NM.is_file():
        return None
    out = subprocess.run([str(NM), "-S", str(elf)], capture_output=True,
                         text=True, check=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[3] == "g_u2BurstBuffers":
            return int(parts[1], 16)
    return None


class UacU2SequentialTrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.source = SOURCE.read_text()
        cls.body = post_body(cls.source)

    def test_burst_count_is_bounded_and_defaults_to_one(self):
        self.assertIn("#elif defined(UAC_U2_BURSTS)\n"
                      "#define UAC_U2_TRAIN_POSTS UAC_U2_BURSTS", self.source)
        self.assertIn("#else\n#define UAC_U2_TRAIN_POSTS 1\n#endif", self.source)
        self.assertIn("#if UAC_U2_TRAIN_POSTS < 1 || UAC_U2_TRAIN_POSTS > 4",
                      self.source)
        self.assertIn('must be 1..4: only one request may be pending', self.source)

    def test_exactly_one_request_is_submitted_at_a_time(self):
        self.assertEqual(self.body.count("usbDsEndpoint_PostBufferAsync("), 1)
        post = self.body.index("usbDsEndpoint_PostBufferAsync(")
        wait = self.body.index("eventWait(&g_uacCtx.audioEndpointIn->CompletionEvent")
        report = self.body.index("usbDsEndpoint_GetReportData(")
        self.assertLess(post, wait)
        self.assertLess(wait, report)
        # The loop only advances after a completion; the single break path
        # cancels before leaving, so no second request can be pending.
        self.assertIn("for (u32 n = 0; n < UAC_U2_TRAIN_POSTS; ++n)", self.body)
        self.assertEqual(self.body.count("usbDsEndpoint_Cancel("), 1)
        cancel = self.body.index("usbDsEndpoint_Cancel(")
        timeout = self.body.index("no completion within 100ms")
        leave = self.body.index("break;", timeout)
        self.assertLess(cancel, timeout)
        self.assertLess(timeout, leave)

    def test_waveform_phase_continues_across_bursts(self):
        self.assertIn("u32 patternFrame;", self.source)
        self.assertIn("const u32 base = g_uacCtx.patternFrame;", self.body)
        self.assertIn("const u32 frame = base + (i / 2);", self.body)
        self.assertIn("g_uacCtx.patternFrame = base + UAC_U2_BURST_BYTES / "
                      "sizeof(s16) / 2;", self.body)

    def test_train_reports_its_outcome(self):
        for token in ('LOG("UAC U2 train begin count=%u pattern=%u',
                      'LOG("UAC U2 train end posted=%u completed=%u pattern=%u',
                      'LOG("UAC U2 short seq=%u requested=%u transferred=%u'):
            self.assertIn(token, self.body)


class UacU2ContinuousBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK15 / "manifest.json").is_file():
            raise unittest.SkipTest(f"missing {WORK15}; run the offline build")
        cls.doc = json.loads((WORK15 / "manifest.json").read_text())

    def test_payload_is_unchanged_from_v14(self):
        if not (WORK14 / "manifest.json").is_file():
            self.skipTest(f"missing {WORK14}")
        old = json.loads((WORK14 / "manifest.json").read_text())
        self.assertEqual(self.doc["cave_sha256"], old["cave_sha256"])
        self.assertEqual(self.doc["cave_bytes"], old["cave_bytes"])
        self.assertEqual([(e["address"], e["after"]) for e in self.doc["edits"]],
                         [(e["address"], e["after"]) for e in old["edits"]])

    def test_build_selects_four_sequential_bursts(self):
        build = json.loads((WORK15 / "build-result.json").read_text())
        self.assertIn("-DUAC_U2_BURSTS=4", build["defines"])
        self.assertEqual(build["payload"]["cave_sha256"],
                         self.doc["cave_sha256"])
        nsp = Path(build["output"]["nsp"])
        if nsp.is_file():
            import hashlib
            self.assertEqual(hashlib.sha256(nsp.read_bytes()).hexdigest(),
                             build["output"]["sha256"])

    def test_four_ring_buffers_are_linked(self):
        build = json.loads((WORK15 / "build-result.json").read_text())
        elf = Path(build["output"]["nsp"]).parent / "exefs.elf"
        if not elf.is_file():
            self.skipTest(f"missing {elf}")
        self.assertEqual(buffer_symbol_size(elf), 4 * 0x1000)
        old_elf = (WORK14 / "build/outputs/exefs.elf")
        if old_elf.is_file():
            self.assertEqual(buffer_symbol_size(old_elf), 1 * 0x1000)


class UacRawProbeRearmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HOST.is_file():
            raise unittest.SkipTest(f"missing {HOST}")
        cls.text = HOST.read_text()

    def test_options_and_bounds(self):
        for token in ("--rearm", "--max-urbs", "max-urbs must be 1..%d",
                      "max-urbs must be >= transfers (window)",
                      "rearm window=%u max_urbs=%u packets=%u timeout_ms=%d",
                      "urb[%u] t=%llums status=%d valid=%u bad=%u bytes=%u",
                      "resubmit[%u]=%d"):
            self.assertIn(token, self.text)

    def test_completions_are_replaced_to_keep_the_window_full(self):
        for token in ("unsigned in_flight = submitted;",
                      "if (!states[i].done) continue;",
                      "submit_iso(t, h, endpoint, bufs[i], packets,",
                      "++in_flight;",
                      "cancel remaining=%u/%u"):
            self.assertIn(token, self.text)

    def test_binary_rejects_bad_rearm_bounds(self):
        if not BINARY.is_file():
            self.skipTest(f"missing {BINARY}")
        for args, text in (
                (("--max-urbs", "0"), "max-urbs must be 1.."),
                (("--rearm", "--transfers", "8", "--max-urbs", "4"),
                 "max-urbs must be >= transfers")):
            result = subprocess.run([str(BINARY), *args], capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn(text, result.stderr)


if __name__ == "__main__":
    unittest.main()
