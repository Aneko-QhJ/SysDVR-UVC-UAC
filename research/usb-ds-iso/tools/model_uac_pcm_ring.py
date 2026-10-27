#!/usr/bin/env python3
"""Model the UAC PCM ring / URB schedule and the A23 frame-cursor gap.

This is a design model, not a USB or thread implementation.  It uses 1 ms
steps, 192 bytes per millisecond (48 kHz, 16-bit stereo), 3072-byte URBs
(16 ms), and a 64 KiB ring.  See docs/UAC_PCM_PRODUCER.md.
"""
import argparse

BYTES_PER_MS = 192
URB_BYTES = 3072
URB_MS = 16
RING_BYTES = 64 * 1024
LEAD_MS = 4


def simulate(seconds=10, ring_bytes=RING_BYTES, urb_bytes=URB_BYTES,
             urbs_in_flight=2, lead_ms=LEAD_MS, a23_mode=False,
             source_pause=None, poster_stall=None):
    """Return counters for one schedule.

    a23_mode=True reproduces the current producer: each URB starts at
    `now + lead` and only one URB is in flight.  a23_mode=False uses the
    proposed persistent frame cursor with two URBs in flight.
    """
    ring = 0
    cursor = None
    inflight = []
    prev_end = None
    underrun = overrun = late = gap_max = 0
    posts = completions = 0
    ring_max = 0
    paused = source_pause or (0, 0)
    stalled = poster_stall or (0, 0)

    for t in range(0, seconds * 1000):
        # grc:d supplies 48 kHz stereo continuously in this model.
        if not (paused[0] <= t < paused[1]):
            ring += BYTES_PER_MS
        if ring > ring_bytes:
            overrun += ring - ring_bytes
            ring = ring_bytes
        ring_max = max(ring_max, ring)

        inflight = [(start, end) for start, end in inflight if end > t]
        completions = posts - len(inflight)

        if cursor is None:
            if ring < urb_bytes:
                continue
            cursor = t + lead_ms

        if stalled[0] <= t < stalled[1]:
            continue

        limit = 1 if a23_mode else urbs_in_flight
        while len(inflight) < limit and cursor <= t + lead_ms:
            start = (t + lead_ms) if a23_mode else cursor
            if start < t + lead_ms:
                late += (t + lead_ms) - start
            if ring < urb_bytes:
                underrun += urb_bytes - ring
                ring = 0
            else:
                ring -= urb_bytes
            end = start + URB_MS
            if prev_end is not None:
                gap_max = max(gap_max, start - prev_end)
            prev_end = end
            inflight.append((start, end))
            cursor = start + URB_MS
            posts += 1
            if a23_mode:
                break

    return {
        "seconds": seconds,
        "posts": posts,
        "completions": completions,
        "underrun_bytes": underrun,
        "overrun_bytes": overrun,
        "late_ms": late,
        "max_gap_ms": gap_max,
        "ring_max_bytes": ring_max,
        "ring_bytes": ring_bytes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=10)
    args = parser.parse_args()
    scenarios = [
        ("cursor nominal", dict()),
        ("a23 one-at-a-time", dict(a23_mode=True)),
        ("cursor, 200ms source pause", dict(source_pause=(3000, 3200))),
        ("cursor, 20ms poster stall", dict(poster_stall=(5000, 5020))),
    ]
    width = max(len(name) for name, _ in scenarios)
    for name, kwargs in scenarios:
        result = simulate(seconds=args.seconds, **kwargs)
        print(f"{name:<{width}}  " + "  ".join(
            f"{key}={value}" for key, value in result.items() if key != "seconds"))


if __name__ == "__main__":
    main()
