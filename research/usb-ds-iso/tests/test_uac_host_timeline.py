"""v42 host clock: device log and macOS log stream on one timeline.

The device log has no wall clock, so v42 stamps the transition lines with
`t_ms` (ms since boot).  macOS logs the isoch transaction error, the audio
daemon stop/start and the pipe abort with wall clock time.  This test pins the
parser, the clock alignment and the decisive reading: did the burst's first
miss come before the host error (device side is the cause) or at/after it
(the host stop produced the burst)?
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE = REPO / "source/uvc/uvc_device.c"
TOOL = ROOT / "tools/uac_host_timeline.py"
CAPTURE = ROOT / "tools/uac_host_capture.py"

DEVICE = """\
SysDVR-UVC 1.0.0 initializing...
USB host connected t_ms=5000
UAC U2 alt diag alt1 n=1 since_alt0_ms=0 t_ms=8000
UAC U2 alt diag alt0 n=1 active=1 inflight=2 posted=9 completed=7 misses=3 last_status=5 dt_done_ms=4 dt_post_ms=4 since_alt1_ms=12000 t_ms=20010
UAC U2 miss ring total=3 n=3 t_ms=20000
UAC U2 miss rec i=0 idx=0 ago_ms=150 dprev_ms=0 since_cancel_ms=4294967295 post=3 comp=1 infl=2 slot=0 urb=388 st=5
UAC U2 miss rec i=1 idx=1 ago_ms=100 dprev_ms=50 since_cancel_ms=21 post=6 comp=4 infl=2 slot=3 urb=436 st=5
UAC U2 miss rec i=2 idx=2 ago_ms=0 dprev_ms=100 since_cancel_ms=21 post=9 comp=7 infl=2 slot=6 urb=484 st=5
UAC U2 alt diag alt1 n=2 since_alt0_ms=190 t_ms=20200
"""

HOST = [
    ("2026-11-06 12:00:00.000000+0000",
     "AppleUSBHostPort::enumerateDeviceComplete_block_invoke: enumerated "
     "0x1209/ca57/0100 (SysDVR-UVC Capture / 1) at 480 Mbps"),
    ("2026-11-06 12:00:14.900000+0000",
     "AppleUSBXHCIIsochronousRequest: AppleUSBIORequest::complete: device 1 "
     "(SysDVR-UVC Capture@00100000) endpoint 0x84: status 0xe00002ed "
     "(transaction error)"),
    ("2026-11-06 12:00:15.010000+0000",
     "performStopIO stopIO"),
    ("2026-11-06 12:00:15.010000+0000",
     "AppleUSBXHCIPipe: IOUSBHostPipe::abortGated: device 1 "
     "(SysDVR-UVC Capture@00100000) endpoint 0x84: aborting 30 requests"),
]


def host_ndjson(rows):
    return "\n".join(json.dumps({"timestamp": ts, "eventMessage": msg})
                     for ts, msg in rows) + "\n"


def run(device_text, host_text):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "device.log").write_text(device_text)
        (tmp / "host.ndjson").write_text(host_text)
        out = tmp / "summary.json"
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--device-log", str(tmp / "device.log"),
             "--host-log", str(tmp / "host.ndjson"), "--out", str(out)],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        return json.loads(out.read_text())


class UacHostTimelineTests(unittest.TestCase):
    def test_device_parser_puts_records_on_the_ring_anchor(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import uac_host_timeline as timeline  # noqa: E402
        events, records = timeline.parse_device(DEVICE)
        self.assertEqual(len(records), 3)
        # at 20000 ms, ago 150 -> 19.850 s
        self.assertAlmostEqual(records[0]["t"], 19.850, places=3)
        self.assertEqual([e["kind"] for e in events].count("alt0"), 1)
        self.assertTrue(any(e["kind"] == "dev_connect" for e in events))

    def test_miss_leads_when_the_burst_starts_before_the_error(self):
        summary = run(DEVICE, host_ndjson(HOST))
        self.assertEqual(summary["verdict"], "miss-leads")
        err = summary["errors"][0]
        # first burst miss at 19.850 -> wall 14.850, error at 14.900
        self.assertAlmostEqual(err["first_miss_ms_before_error"], 50.0, places=1)
        self.assertEqual(summary["clock"]["pairs"], 1)
        self.assertLess(summary["clock"]["residual_ms_max"], 5)

    def test_host_error_leads_when_the_burst_starts_after_it(self):
        late = [row for row in HOST]
        late[1] = ("2026-11-06 12:00:14.800000+0000", late[1][1])
        summary = run(DEVICE, host_ndjson(late))
        self.assertEqual(summary["verdict"], "host-error-leads")
        self.assertLess(summary["errors"][0]["first_miss_ms_before_error"], 2)

    def test_capture_tool_has_a_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(CAPTURE), "--out", tmp, "--seconds", "5",
                 "--audio-index", "2", "--dry-run"],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("log stream", proc.stdout)
            self.assertIn("avfoundation", proc.stdout)
            self.assertFalse((Path(tmp) / "capture.wav").exists())

    def test_capture_can_start_the_log_before_the_device_exists(self):
        # the enumeration anchor needs log stream running before power-on,
        # while ffmpeg can only open an audio device that already exists
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, str(CAPTURE), "--out", tmp, "--seconds", "5",
                 "--wait-audio", "30", "--dry-run"],
                capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("wait up to 30 s", proc.stdout)
            self.assertLess(proc.stdout.index("log stream --style"),
                            proc.stdout.index("wait up to"))

    def test_audio_device_list_parser(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import uac_host_capture as capture  # noqa: E402
        sample = (
            "[AVFoundation indev @ 0x1] AVFoundation video devices:\n"
            "[AVFoundation indev @ 0x1] [0] FaceTime HD Camera\n"
            "[AVFoundation indev @ 0x1] AVFoundation audio devices:\n"
            "[AVFoundation indev @ 0x1] [2] SysDVR-UVC Capture\n"
            "[AVFoundation indev @ 0x1] [3] MacBook Pro Microphone\n")
        self.assertEqual(capture.parse_audio_devices(sample),
                         {2: "SysDVR-UVC Capture",
                          3: "MacBook Pro Microphone"})

    def test_tick_stamp_is_opt_in_and_needs_the_alt_diag_clock(self):
        self.assertIn("#if defined(UAC_U2_TICK_LOG)", SOURCE.read_text())
        self.assertIn('#error "UAC_U2_TICK_LOG needs the ALT_DIAG clock conversion"',
                      SOURCE.read_text())
        # off by default: empty format and empty argument
        self.assertIn('#define UAC_TICK_FMT ""', SOURCE.read_text())
        self.assertIn("#define UAC_TICK_ARG(tick)", SOURCE.read_text())

    def test_every_transition_line_carries_the_stamp(self):
        text = SOURCE.read_text()
        for marker in ("UAC U2 alt diag alt0", "UAC U2 alt diag alt1",
                       "UAC U2 miss ring total", "UAC U2 teardown cancel",
                       "USB host connected"):
            start = text.index(marker)
            line = text[start:text.index("\n", start)]
            self.assertIn("UAC_TICK_FMT", line,
                          f"{marker} lost the tick stamp")


if __name__ == "__main__":
    unittest.main()
