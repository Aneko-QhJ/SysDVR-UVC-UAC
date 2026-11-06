#!/usr/bin/env python3
"""Put the device log and the macOS `log stream` on one timeline.

The device stamps its alt0/alt1 transitions, the miss ring and the host-connected
line with `t_ms` (ms since boot, -DUAC_U2_TICK_LOG).  macOS stamps the isoch
transaction error, `performStopIO`/`performStartIO` and the pipe abort with wall
clock.  The SET_INTERFACE(0/1) that follows each stop/start pairs the clocks, so
every miss record (ring `at_ms - ago_ms`) can be placed next to the host error.

Read the result: if a burst's first miss lies more than ~20 ms before the host
error, the miss came first (device side is the cause); if the burst starts at or
after the error, the host stop produced it.
"""
import argparse
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

ALT0_RE = re.compile(r"UAC U2 alt diag alt0 n=(\d+) .*t_ms=(\d+)")
ALT1_RE = re.compile(r"UAC U2 alt diag alt1 n=(\d+) since_alt0_ms=(\d+) t_ms=(\d+)")
RING_RE = re.compile(r"UAC U2 miss ring total=(\d+) n=(\d+) t_ms=(\d+)")
REC_RE = re.compile(
    r"UAC U2 miss rec i=(\d+) idx=(\d+) ago_ms=(\d+) dprev_ms=(\d+) "
    r"since_cancel_ms=(\d+) post=(\d+) comp=(\d+) infl=(\d+) "
    r"slot=(\d+) urb=(\d+) st=(\d+)")
CONNECT_RE = re.compile(r"USB host connected t_ms=(\d+)")
TEARDOWN_RE = re.compile(r"UAC U2 teardown cancel rc=0x([0-9a-f]+) "
                         r"wait=0x([0-9a-f]+)(?: t_ms=(\d+))?")

TS_FORMATS = ("%Y-%m-%d %H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S%z")


def parse_ts(text):
    for fmt in TS_FORMATS:
        try:
            return datetime.strptime(text, fmt).timestamp()
        except (TypeError, ValueError):
            continue
    return None


def parse_device(text):
    events, records = [], []
    ring = None
    for raw in text.splitlines():
        line = raw.strip()
        m = ALT0_RE.search(line)
        if m:
            events.append({"kind": "alt0", "n": int(m.group(1)),
                           "t": int(m.group(2)) / 1000.0})
            ring = None
            continue
        m = ALT1_RE.search(line)
        if m:
            events.append({"kind": "alt1", "n": int(m.group(1)),
                           "since_alt0_ms": int(m.group(2)),
                           "t": int(m.group(3)) / 1000.0})
            continue
        m = RING_RE.search(line)
        if m:
            ring = {"total": int(m.group(1)), "n": int(m.group(2)),
                    "at_ms": int(m.group(3))}
            events.append({"kind": "ring", **ring})
            continue
        m = REC_RE.search(line)
        if m and ring is not None:
            ago = int(m.group(3))
            if ago <= ring["at_ms"]:
                records.append({
                    "idx": int(m.group(2)), "ago_ms": ago,
                    "dprev_ms": int(m.group(4)),
                    "since_cancel_ms": int(m.group(5)),
                    "post": int(m.group(6)), "comp": int(m.group(7)),
                    "infl": int(m.group(8)), "slot": int(m.group(9)),
                    "urb": int(m.group(10)), "st": int(m.group(11)),
                    "t": (ring["at_ms"] - ago) / 1000.0,
                })
            continue
        m = CONNECT_RE.search(line)
        if m:
            events.append({"kind": "dev_connect", "t": int(m.group(1)) / 1000.0})
            continue
        m = TEARDOWN_RE.search(line)
        if m and m.group(3):
            events.append({"kind": "teardown", "t": int(m.group(3)) / 1000.0,
                           "rc": m.group(1), "wait": m.group(2)})
    return events, records


HOST_RULES = (
    ("iso_error", lambda msg: "IsochronousRequest" in msg
     and "transaction error" in msg),
    ("iso_error_user", lambda msg: "completeBlock block frame" in msg
     and "transaction status error" in msg),
    ("abort", lambda msg: "abortGated" in msg),
    ("stop_io", lambda msg: "performStopIO stopIO" in msg),
    ("start_io", lambda msg: "performStartIO startIO" in msg),
    ("lock_delay", lambda msg: "performStartIO lockDelayMS" in msg),
    ("underflow", lambda msg: "USB underflow" in msg),
    ("zlp", lambda msg: "zero length transfers" in msg),
    ("enumerate", lambda msg: "enumerated 0x1209/ca57" in msg),
)


def parse_host(text):
    events = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        msg = rec.get("eventMessage") or ""
        when = parse_ts(rec.get("timestamp") or "")
        if when is None:
            continue
        for kind, rule in HOST_RULES:
            if rule(msg):
                event = {"kind": kind, "t": when, "msg": msg}
                if kind == "lock_delay":
                    m = re.search(r"lockDelayMS (\d+)", msg)
                    if m:
                        event["lock_delay_ms"] = int(m.group(1))
                events.append(event)
                break
    events.sort(key=lambda e: e["t"])
    return events


def align(device_events, host_events):
    alt0 = [e for e in device_events if e["kind"] == "alt0"]
    stops = [e for e in host_events if e["kind"] == "stop_io"]
    anchors = []
    dev_connect = next((e for e in device_events
                        if e["kind"] == "dev_connect"), None)
    host_enum = next((e for e in host_events
                      if e["kind"] == "enumerate"), None)
    if dev_connect and host_enum:
        anchors.append(host_enum["t"] - dev_connect["t"])
    base = anchors[0] if anchors else None
    pairs = []
    if base is not None and alt0:
        for stop in stops:
            best = min(alt0, key=lambda e: abs(e["t"] + base - stop["t"]))
            if abs(best["t"] + base - stop["t"]) <= 2.0:
                pairs.append(stop["t"] - best["t"])
    if pairs:
        offset = statistics.median(pairs)
        residual = [abs(p - offset) * 1000 for p in pairs]
        stats_ = {"offset_s": offset, "pairs": len(pairs),
                  "residual_ms_median": round(statistics.median(residual), 2),
                  "residual_ms_max": round(max(residual), 2)}
    elif base is not None:
        stats_ = {"offset_s": base, "pairs": 0,
                  "residual_ms_median": None, "residual_ms_max": None}
    else:
        stats_ = {"offset_s": None, "pairs": 0,
                  "residual_ms_median": None, "residual_ms_max": None}
    return stats_


def correlate(device_events, records, host_events, offset):
    errors = [e for e in host_events if e["kind"] == "iso_error"]
    unique = []
    for err in errors:
        if not unique or err["t"] - unique[-1]["t"] > 0.005:
            unique.append(err)
    alt0 = [e for e in device_events if e["kind"] == "alt0"]
    alt1 = [e for e in device_events if e["kind"] == "alt1"]
    rows = []
    for err in unique:
        wall = err["t"]
        after = [e for e in alt0 if wall <= e["t"] + offset <= wall + 1.5]
        alt0_hit = after[0] if after else None
        burst = []
        if alt0_hit:
            end = alt0_hit["t"] + offset
            burst = [r for r in records
                     if end - 0.6 <= r["t"] + offset <= end + 0.01]
            burst.sort(key=lambda r: r["t"])
        next_alt1 = None
        if alt0_hit:
            cands = [e for e in alt1
                     if e["t"] + offset >= alt0_hit["t"] + offset]
            next_alt1 = cands[0] if cands else None
        rows.append({
            "error_at": wall,
            "alt0": alt0_hit["t"] + offset if alt0_hit else None,
            "alt1": next_alt1["t"] + offset if next_alt1 else None,
            "burst": [{"t": r["t"] + offset, "idx": r["idx"],
                       "dprev_ms": r["dprev_ms"],
                       "since_cancel_ms": r["since_cancel_ms"],
                       "infl": r["infl"], "st": r["st"]} for r in burst],
            "first_miss_ms_before_error":
                round((wall - (burst[0]["t"] + offset)) * 1000, 2) if burst else None,
            "last_miss_ms_before_error":
                round((wall - (burst[-1]["t"] + offset)) * 1000, 2) if burst else None,
            "burst_span_ms":
                round((burst[-1]["t"] - burst[0]["t"]) * 1000, 2) if burst else None,
        })
    leads = [r["first_miss_ms_before_error"] for r in rows
             if r["first_miss_ms_before_error"] is not None]
    if not rows:
        verdict = "no-host-errors"
    elif not leads:
        verdict = "no-ring-data"
    elif all(v > 20 for v in leads):
        verdict = "miss-leads"
    elif all(v < 2 for v in leads):
        verdict = "host-error-leads"
    else:
        verdict = "ambiguous"
    return rows, verdict


def summarize(device_events, records, host_events, offset, rows, verdict):
    def count(kind):
        return sum(1 for e in host_events if e["kind"] == kind)
    return {
        "device": {
            "alt0": sum(1 for e in device_events if e["kind"] == "alt0"),
            "alt1": sum(1 for e in device_events if e["kind"] == "alt1"),
            "miss_records": len(records),
            "dev_connect_t_ms": next((round(e["t"] * 1000) for e in device_events
                                      if e["kind"] == "dev_connect"), None),
        },
        "host": {
            "iso_errors": count("iso_error"),
            "aborts": count("abort"),
            "stop_io": count("stop_io"),
            "start_io": count("start_io"),
            "underflows": count("underflow"),
            "zlp_blocks": count("zlp"),
            "lock_delays": sorted({e.get("lock_delay_ms") for e in host_events
                                   if e["kind"] == "lock_delay"
                                   and e.get("lock_delay_ms") is not None}),
        },
        "clock": {"offset_s": offset},
        "errors": rows,
        "verdict": verdict,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-log", type=Path, required=True,
                        help="device log read back from the SD card")
    parser.add_argument("--host-log", type=Path, required=True,
                        help="host-log.ndjson from uac_host_capture.py")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the JSON summary here (default: stdout)")
    args = parser.parse_args()

    device_events, records = parse_device(args.device_log.read_text(errors="replace"))
    host_events = parse_host(args.host_log.read_text(errors="replace"))
    clock = align(device_events, host_events)
    offset = clock["offset_s"]
    if offset is None:
        print(json.dumps({"error": "no clock anchor (enumerate/dev_connect)"},
                         indent=2))
        return 2
    rows, verdict = correlate(device_events, records, host_events, offset)
    summary = summarize(device_events, records, host_events, offset, rows, verdict)
    summary["clock"].update({k: v for k, v in clock.items() if k != "offset_s"})
    text = json.dumps(summary, indent=2)
    if args.out:
        args.out.write_text(text + "\n")
        print(f"{verdict}: {len(rows)} error(s), clock {offset:+.3f} s, "
              f"residual {clock['residual_ms_median']} ms -> {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
