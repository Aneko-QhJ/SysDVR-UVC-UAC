#!/usr/bin/env python3
"""Decode the A23 endpoint trace carried in the ISO report diagnostics.

The trace build replaces the report's mailbox copy with four fields:

    +16  endpoint object pointer (u64)
    +24  producer index           (u32)
    +28  consumer index           (u32)
    +32  in-flight URB count      (u32)

`iso-probe --status` prints those 112 diagnostic bytes as diagnostics_hex.
"""
import argparse
import json
import sys

TRACE_OFFSET = 8


def decode(data):
    if isinstance(data, str):
        data = bytes.fromhex(data)
    if len(data) < TRACE_OFFSET + 20:
        raise ValueError(f"trace buffer too short: {len(data)}")
    return {
        "endpoint": int.from_bytes(data[8:16], "little"),
        "producer": int.from_bytes(data[16:20], "little"),
        "consumer": int.from_bytes(data[20:24], "little"),
        "count": int.from_bytes(data[24:28], "little"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", help="iso-probe JSON line, or raw hex")
    args = parser.parse_args(argv)
    if args.input:
        text = open(args.input).read() if args.input != "-" else sys.stdin.read()
    else:
        text = sys.stdin.read()
    text = text.strip()
    hexstr = None
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            hexstr = obj.get("diagnostics_hex") or obj.get("diagnostics")
            if hexstr:
                break
    if not hexstr:
        hexstr = text
    result = decode(hexstr)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
