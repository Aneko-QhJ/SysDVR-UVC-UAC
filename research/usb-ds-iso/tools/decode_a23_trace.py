#!/usr/bin/env python3
"""Decode the A23 endpoint trace carried in the ISO report diagnostics.

Three layouts are accepted:

v3 (magic 0x314f5349):
    +0   magic
    +8   endpoint object pointer (u64)
    +16  producer index           (u32)
    +20  consumer index           (u32)
    +24  in-flight URB count      (u32)

v4 (magic 0x384f5349, "ISO8"):
    +0   magic
    +8   consumer index           (u32)
    +12  last completed URB IOVA  (u32)
    +16  last completed URB size  (u32)

v5 (magic 0x394f5349, "ISO9"):
    +0   magic
    +8   eight pairs of {IOVA low32 (u32), size (u32)}

The v4 last entry is ``(consumer - 1) & 7``.  A zero size means
``FUN_0002c690`` skipped the unmap; a zero IOVA means it looked up the wrong
address.  Both leave the endpoint producer/consumer/count consistent.  v5
exposes every entry so a leak in an earlier slot is visible.

`iso-probe --status` prints the 112 diagnostic bytes as diagnostics_hex.
"""
import argparse
import json
import sys

MAGIC_V3 = 0x314F5349
MAGIC_V4 = 0x384F5349
MAGIC_V5 = 0x394F5349


def decode(data):
    if isinstance(data, str):
        data = bytes.fromhex(data)
    if len(data) < 28:
        raise ValueError(f"trace buffer too short: {len(data)}")
    magic = int.from_bytes(data[0:4], "little")
    if magic == MAGIC_V4:
        consumer = int.from_bytes(data[8:12], "little")
        last_iova = int.from_bytes(data[12:16], "little")
        last_size = int.from_bytes(data[16:20], "little")
        if last_size == 0:
            gate = "size_zero"
        elif last_iova == 0:
            gate = "iova_zero"
        else:
            gate = "last_entry_present"
        return {
            "layout": "urb-v4",
            "magic": f"0x{magic:08x}",
            "consumer": consumer,
            "last_index": (consumer - 1) & 7,
            "last_iova": last_iova,
            "last_size": last_size,
            "unmap_gate": gate,
        }
    if magic == MAGIC_V5:
        entries = []
        for index in range(8):
            off = 8 + index * 8
            entries.append({
                "index": index,
                "iova": int.from_bytes(data[off:off + 4], "little"),
                "size": int.from_bytes(data[off + 4:off + 8], "little"),
            })
        nonzero = [entry for entry in entries if entry["size"] != 0]
        zero_iova = [entry["index"] for entry in nonzero if entry["iova"] == 0]
        return {
            "layout": "urb-v5",
            "magic": f"0x{magic:08x}",
            "entries": entries,
            "nonzero_sizes": len(nonzero),
            "distinct_iovas": len({entry["iova"] for entry in nonzero}),
            "zero_iova_indices": zero_iova,
            "last_nonzero": nonzero[-1]["index"] if nonzero else None,
        }
    if magic not in (0, MAGIC_V3):
        raise ValueError(f"unknown trace magic: 0x{magic:08x}")
    return {
        "layout": "v3",
        "magic": f"0x{magic:08x}",
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
