#!/usr/bin/env python3
"""Decode a guest xhci-hcd ftrace capture around an isochronous IN run.

The v29v long run showed the device side is steady but loses two frames to a
code-23 (Missed Service) event roughly every 1.5 s.  The device cannot see why
the host controller did not service those frames, so the next step is to look
at the guest kernel's own xHCI trace (item b of the host-side plan).

What this tool reads is the `trace` text produced by

    /sys/kernel/tracing/events/xhci-hcd/{xhci_urb_enqueue,xhci_urb_giveback,
                                        xhci_handle_transfer}

Sample lines (Debian 13, kernel 6.12, arm64 guest):

    lsusb-5836 [001] ..... 887.902784: xhci_urb_enqueue: 3-1 ep0out-control: urb
      000000004e4284be pipe 2147489920 slot 1 length 0/4 sgs 0/0 stream 0 flags 00110200
    <idle>-0  [000] d.h.. 872.570547: xhci_handle_transfer: CTRL: Buffer
      00000000414e2d00 length 254 TD size 0 intr 0 type 'Data Stage' flags i:i:c:s:I:e:C

The device under test is on the guest's EHCI bus 1 (``ehci-pci``); the
xhci-hcd tracepoints only cover buses 2 and 3 and never see it.  Usbmon is
the tool that does: ``/sys/kernel/debug/usb/usbmon/1u`` prints one line per
URB event, including isochronous ones, e.g. ``S Ii:1:004:4 -115:3072 4`` for
a submit and ``C Ii:1:004:4 -71:2 2688 4`` for a completion that lost two
packets (two missed frames = 384 B).  Pass ``--format usbmon`` for that.

The tool reports, for the isochronous endpoint only:

* URB givebacks: how many, how many came back short (actual != requested) and
  the worst shortfall, so a lost URB is visible from the host side;
* transfer events per ring type, and the "length 0" events that correspond to
  serviced-with-no-data frames;
* a timeline of the short URBs so it can be matched with the device-side
  code-23 offsets (the device log has no timestamps, so the shape matters more
  than exact alignment: short URBs should appear at the same ~1.5 s cadence).

No USB, no hardware, no root: plain text in, report out.
"""
import argparse
import json
import re
from pathlib import Path

HEADER = re.compile(r"^\s*\S+-\d+\s+\[\d+\]\s+\S+\s+(\d+\.\d+):\s+(\S+):\s+(.*)$")
URB = re.compile(
    r"^(?P<dev>\S+)\s+(?P<ep>\S+):\s+urb\s+(?P<urb>\w+)\s+pipe\s+(?P<pipe>\d+)\s+"
    r"slot\s+(?P<slot>\d+)\s+length\s+(?P<actual>\d+)/(?P<len>\d+)")
LENGTH = re.compile(r"length\s+(\d+)")


USBMON = re.compile(
    r"^(?P<tag>[0-9a-f]+)\s+(?P<t>\d+)\s+(?P<event>[SCE])\s+"
    r"(?P<kind>[A-Za-z])(?P<dir>[io]):(?P<bus>\d+):(?P<dev>\d+):(?P<ep>\d+)\s+"
    r"(?P<rest>.*)$")


def parse_usbmon(path, bus=None):
    """Parse a usbmon text capture (one line per URB submit/complete).

    Field layout (kernel 6.12, see Documentation/usb/usbmon.rst):

      <tag> <usec> S <T><dir>:<bus>:<dev>:<ep> <status>:<length> <interval> ...
      <tag> <usec> C <T><dir>:<bus>:<dev>:<ep> <status>[:<iso_err>] <length> ...

    Submits carry the requested length after the status colon; completions
    carry the transferred length as the next token, and for isochronous URBs
    the colon suffix is the number of packets that were not transferred.
    Requests are paired by URB tag so a completion knows what was asked for.
    """
    urbs = []
    pending = {}
    for line in Path(path).read_text(errors="replace").splitlines():
        match = USBMON.match(line.strip())
        if not match:
            continue
        if bus is not None and int(match.group("bus")) != bus:
            continue
        rest = match.group("rest").split()
        if not rest or rest[0] == "s":
            continue  # control submit: the setup packet is not a status
        status_text, _, suffix = rest[0].partition(":")
        status = int(status_text) if status_text.lstrip("-").isdigit() else None
        tag = match.group("tag")
        entry = {
            "t": int(match.group("t")) / 1e6,
            "urb": tag,
            "kind": match.group("kind"),
            "dir": match.group("dir"),
            "bus": int(match.group("bus")),
            "dev": int(match.group("dev")),
            "ep": f"{match.group('kind')}{match.group('dir')}"
                  f":{match.group('bus')}:{match.group('dev')}:{match.group('ep')}",
            "status": status,
            "iso_errors": int(suffix) if suffix.isdigit() else None,
        }
        if match.group("event") == "S":
            requested = (int(suffix) if suffix.isdigit() else
                         int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 0)
            pending[tag] = requested
            entry.update(event="xhci_urb_enqueue", actual=0, length=requested)
        else:
            actual = int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else 0
            entry.update(event="xhci_urb_giveback", actual=actual,
                         length=pending.get(tag, actual))
        urbs.append(entry)
    return urbs, []


def parse(path):
    """Return (urb_events, transfer_events) parsed from a trace text file."""
    urbs, transfers = [], []
    for line in Path(path).read_text(errors="replace").splitlines():
        head = HEADER.match(line)
        if not head:
            continue
        timestamp, tracepoint, rest = float(head.group(1)), head.group(2), head.group(3)
        if tracepoint in ("xhci_urb_enqueue", "xhci_urb_giveback"):
            match = URB.match(rest)
            if not match:
                continue
            urbs.append({
                "t": timestamp,
                "event": tracepoint,
                "dev": match.group("dev"),
                "ep": match.group("ep"),
                "urb": match.group("urb"),
                "slot": int(match.group("slot")),
                "actual": int(match.group("actual")),
                "length": int(match.group("len")),
            })
        elif tracepoint == "xhci_handle_transfer":
            ring = rest.split(":", 1)[0].strip()
            length = LENGTH.search(rest)
            transfers.append({
                "t": timestamp,
                "ring": ring,
                "length": int(length.group(1)) if length else None,
                "raw": rest,
            })
        elif tracepoint == "xhci_queue_trb":
            ring = rest.split(":", 1)[0].strip()
            transfers.append({
                "t": timestamp,
                "ring": ring,
                "length": None,
                "raw": rest,
                "event": "queue",
            })
    return urbs, transfers


def summarize(urbs, transfers, ep="isoc"):
    """Build the report.  `ep` filters devices/endpoints by substring."""
    picked = [u for u in urbs if ep in u["ep"]]
    givebacks = [u for u in picked if u["event"] == "xhci_urb_giveback"]
    enqueues = [u for u in picked if u["event"] == "xhci_urb_enqueue"]
    short = [u for u in givebacks if u["actual"] != u["length"]]
    known = [t for t in transfers if t.get("event") != "queue"]
    rings = {}
    for t in known:
        entry = rings.setdefault(t["ring"], {"events": 0, "zero_length": 0})
        entry["events"] += 1
        if t["length"] == 0:
            entry["zero_length"] += 1
    report = {
        "endpoint_filter": ep,
        "urb_enqueues": len(enqueues),
        "urb_givebacks": len(givebacks),
        "urb_short": len(short),
        "urb_bytes": sum(u["actual"] for u in givebacks),
        "worst_shortfall": max((u["length"] - u["actual"] for u in short),
                               default=0),
        "transfer_events": len(known),
        "transfer_rings": rings,
        "short_urbs": [
            {"t": u["t"], "ep": u["ep"], "actual": u["actual"],
             "length": u["length"], "missing": u["length"] - u["actual"]}
            for u in short[:64]
        ],
    }
    if givebacks:
        span = givebacks[-1]["t"] - givebacks[0]["t"]
        report["span_s"] = round(span, 3)
        if span > 0:
            report["bytes_per_s"] = round(report["urb_bytes"] / span, 1)
            report["frames_per_s"] = round(len(givebacks) * 16 / span, 2)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("trace", type=Path, help="trace text file")
    parser.add_argument("--format", choices=("xhci", "usbmon"), default="xhci",
                        help="xhci = ftrace text (buses 2/3 only), "
                             "usbmon = /sys/kernel/debug/usb/usbmon/1u text")
    parser.add_argument("--bus", type=int, default=1,
                        help="usbmon bus number (default 1, the EHCI bus)")
    parser.add_argument("--ep", default="isoc",
                        help="substring of the endpoint name to keep (default: isoc)")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()
    if args.format == "usbmon":
        urbs, transfers = parse_usbmon(args.trace, args.bus)
    else:
        urbs, transfers = parse(args.trace)
    report = summarize(urbs, transfers, args.ep)
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f"endpoint filter: {report['endpoint_filter']}")
    print(f"URBs: {report['urb_enqueues']} enqueue / {report['urb_givebacks']} giveback, "
          f"{report['urb_short']} short, {report['urb_bytes']} B, "
          f"worst shortfall {report['worst_shortfall']} B")
    if "span_s" in report:
        print(f"span {report['span_s']} s, {report.get('bytes_per_s')} B/s, "
              f"{report.get('frames_per_s')} frames/s")
    print(f"transfer events: {report['transfer_events']} "
          f"{report['transfer_rings']}")
    for short in report["short_urbs"][:20]:
        print(f"  short t={short['t']:.6f} {short['ep']} "
              f"{short['actual']}/{short['length']} missing {short['missing']} B")


if __name__ == "__main__":
    main()
