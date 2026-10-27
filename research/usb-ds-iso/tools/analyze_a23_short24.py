#!/usr/bin/env python3
"""Narrow file-only short24 payload/STATUS consumer, not a strict USB verdict."""
import argparse
import json
from pathlib import Path
import struct


PACKET_BYTES = 24
PACKETS = 16
TRANSACTIONS = 128
MAGIC = 0x34325349


def require(value, message):
    if not value:
        raise ValueError(message)


def analyze(raw, transactions, after, first, overall):
    require(type(first) is int and 1 <= first <= 65520, "sequence range would wrap")
    require(type(overall) is int and overall == 0, "overall native result")
    require(len(raw) == TRANSACTIONS * PACKET_BYTES and len(transactions) == TRANSACTIONS * 28,
            "fixed128 short24 snapshot sizes")
    require(len(after) == 168, "STATUS size")
    status = struct.unpack_from("<14I", after)
    require(status[:5] == (0x31505349, 1, first, 2, 0) and status[5] == status[6] > 0 and
            status[7:12] == (384, 384, 3, 3, 0x83) and status[12] in (0, 1) and status[13] == 0,
            "completed short24 STATUS")
    diagnostic = struct.unpack_from("<6IQ", after, 56)
    require(diagnostic[0] == MAGIC and diagnostic[1] == 0 and diagnostic[3:6] == (1, 65535, 384)
            and diagnostic[6] != 0 and diagnostic[6] % 16 == 0, "IS24 terminal identity")
    mfi, valid = struct.unpack_from("<2I", after, 56 + 72)
    control = diagnostic[2]
    require(valid == 1 and mfi < 16384 and (control >> 10 & 63) == 5 and
            not control >> 31 and (control >> 20 & 2047) == (((mfi >> 3) + 32) & 2047),
            "IS24 scheduling/context snapshot")
    for offset in (56 + 32, 56 + 52):
        pointer, counts, flags, stamp = struct.unpack_from("<QIII", after, offset)
        require(pointer and counts == (1 << 24 | 24) and flags >> 16 & 31 == 7 and
                flags >> 10 & 63 == 32 and flags & 4 and stamp < 16384,
                "first-two ED snapshot")
    slots = []
    for i in range(TRANSACTIONS):
        rc, requested, offset, count, timestamp, options = struct.unpack_from("<iIIIQI", transactions, i * 28)
        require(rc == 0 and requested == 24 and offset == i * 24 and options == 0 and count in (0, 24),
                "native short24 transaction")
        if count:
            require(len(slots) < 16, "extra packet")
            seq = first + len(slots)
            expected = b"IS24" + struct.pack("<H", seq) + bytes(
                (j ^ seq ^ (seq >> 8)) & 255 for j in range(6, 24))
            require(raw[offset:offset + count] == expected, "short24 payload sequence/body")
            slots.append(i)
    require(len(slots) == 16 and slots == list(range(slots[0], slots[0] + 16)),
            "16 consecutive short packets")
    return dict(schema="A23-short24-file-analysis-1", effective_slots=slots, payload_bytes=384,
                first_sequence=first, urb_id=status[5], diagnostic="IS24",
                supplied_payload_and_status_valid=True, physical_provenance_verified=False,
                device_log_relation_verified=False, control_path_verified=False,
                callback_drain_verified=False, buffer_reuse_verified=False,
                hardware_verified=False, continuous_audio_verified=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("raw", "transactions", "after"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--first", type=int, required=True)
    parser.add_argument("--overall", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(analyze(args.raw.read_bytes(), args.transactions.read_bytes(), args.after.read_bytes(),
                             args.first, args.overall), sort_keys=True))
