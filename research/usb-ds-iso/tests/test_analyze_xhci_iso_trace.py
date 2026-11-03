"""v29w host-side plan (b): decode a guest xhci-hcd trace of the ISO run.

The v29v long run is steady but loses two frames to a code-23 (Missed
Service) event about every 1.5 s.  The device cannot see why the host
controller skipped those frames, so the next round captures the guest's own
xHCI trace.  These tests pin the decoder against the real formats the guest
printed (Debian 13, kernel 6.12, arm64) and against a synthetic ISO run.
"""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import analyze_xhci_iso_trace as analyzer  # noqa: E402

# real lines captured from the guest while it enumerated a hub
URB_LINES = """\
           lsusb-5836    [001] .....   887.902784: xhci_urb_enqueue: 3-1 ep0out-control: urb 000000004e4284be pipe 2147489920 slot 1 length 0/4 sgs 0/0 stream 0 flags 00110200
          <idle>-0       [000] d.h..   887.902835: xhci_urb_giveback: 3-1 ep0out-control: urb 000000004e4284be pipe 2147489920 slot 1 length 4/4 sgs 0/0 stream 0 flags 00110200
"""

TRANSFER_LINES = """\
          <idle>-0       [000] d.h..   872.570547: xhci_handle_transfer: CTRL: Buffer 00000000414e2d00 length 254 TD size 0 intr 0 type 'Data Stage' flags i:i:c:s:I:e:C
          <idle>-0       [000] d.h..   872.570548: xhci_handle_transfer: CTRL: Buffer 0000000000000000 length 0 TD size 0 intr 0 type 'Status Stage' flags I:c:e:C
"""


def iso_line(i, actual, length=3072, t=None):
    t = 500.0 + i * 0.0167 if t is None else t
    return (f"          <idle>-0       [000] d.h..   {t:.6f}: xhci_urb_giveback: "
            f"1-1 ep84in-isoc: urb 00000000{i:08x} pipe 0 slot 2 "
            f"length {actual}/{length} sgs 0/0 stream 0 flags 00110200")


# real usbmon text lines captured in the guest (bus 1, EHCI)
USBMON_LINES = """\
ffff000003565300 1085935229 S Ci:1:001:0 s a3 00 0000 0001 0004 4 <
ffff000003565300 1085935273 C Ci:1:001:0 0 4 = 07050000
ffff0000744e8cc0 1085935422 S Ii:1:001:1 -115:2048 4 <
"""


def usbmon_iso(i, actual, iso_err=0, status=-71):
    t = 1085935000 + i * 16700
    return (f"ffff0000744e8cc{i:02x} {t} S Ii:1:004:4 -115:3072 4 <\n"
            f"ffff0000744e8cc{i:02x} {t + 16000} C Ii:1:004:4 "
            f"{status}:{iso_err} {actual} 4")


class XhciIsoTraceTests(unittest.TestCase):
    def _write(self, text):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "trace.txt"
        path.write_text(text)
        return path

    def test_parses_the_real_control_format(self):
        urbs, transfers = analyzer.parse(self._write(URB_LINES + TRANSFER_LINES))
        self.assertEqual(len(urbs), 2)
        self.assertEqual(urbs[0]["ep"], "ep0out-control")
        self.assertEqual(urbs[0]["length"], 4)
        self.assertEqual(urbs[1]["actual"], 4)
        self.assertEqual(len(transfers), 2)
        self.assertEqual(transfers[0]["ring"], "CTRL")
        self.assertEqual(transfers[0]["length"], 254)
        self.assertEqual(transfers[1]["length"], 0)

    def test_reports_short_isoc_urbs(self):
        lines = [iso_line(i, 3072) for i in range(10)]
        # one URB loses the two frames the device reported as code 23
        lines[5] = iso_line(5, 3072 - 2 * 192)
        path = self._write("\n".join(lines) + "\n")
        urbs, transfers = analyzer.parse(path)
        report = analyzer.summarize(urbs, transfers, "isoc")
        self.assertEqual(report["urb_givebacks"], 10)
        self.assertEqual(report["urb_short"], 1)
        self.assertEqual(report["worst_shortfall"], 384)
        self.assertEqual(report["short_urbs"][0]["missing"], 384)
        # span_s is rounded to milliseconds by the report
        self.assertEqual(report["span_s"], 0.15)

    def test_control_urbs_are_filtered_out(self):
        path = self._write(URB_LINES + "\n".join(
            iso_line(i, 3072) for i in range(3)) + "\n")
        urbs, transfers = analyzer.parse(path)
        report = analyzer.summarize(urbs, transfers, "isoc")
        self.assertEqual(report["urb_givebacks"], 3)
        self.assertEqual(report["urb_short"], 0)

    def test_usbmon_parser_keeps_isoc_dev4(self):
        lines = [usbmon_iso(i, 3072) for i in range(3)]
        path = self._write("\n".join(lines) + "\n")
        urbs, _ = analyzer.parse_usbmon(path, bus=1)
        self.assertEqual(len(urbs), 6)  # 3 submits + 3 completions
        self.assertEqual(urbs[1]["ep"], "Ii:1:004:4")
        self.assertEqual(urbs[1]["event"], "xhci_urb_giveback")
        self.assertEqual(urbs[1]["actual"], 3072)

    def test_usbmon_reports_short_urbs(self):
        lines = [usbmon_iso(i, 3072) for i in range(5)]
        lines[2] = usbmon_iso(2, 3072 - 2 * 192, iso_err=2)
        path = self._write("\n".join(lines) + "\n")
        urbs, _ = analyzer.parse_usbmon(path, bus=1)
        report = analyzer.summarize(urbs, [], "Ii:1:004")
        self.assertEqual(report["urb_givebacks"], 5)
        self.assertEqual(report["urb_short"], 1)
        self.assertEqual(report["worst_shortfall"], 384)

    def test_cli_prints_json(self):
        path = self._write("\n".join(iso_line(i, 3072) for i in range(4)) + "\n")
        out = io.StringIO()
        sys.argv = ["analyze_xhci_iso_trace.py", str(path), "--json"]
        with redirect_stdout(out):
            analyzer.main()
        report = json.loads(out.getvalue())
        self.assertEqual(report["urb_givebacks"], 4)
        self.assertEqual(report["urb_bytes"], 4 * 3072)


if __name__ == "__main__":
    unittest.main()
