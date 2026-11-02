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
LEAD_MS = 32


def simulate(seconds=10, ring_bytes=RING_BYTES, urb_bytes=URB_BYTES,
             urbs_in_flight=3, lead_ms=LEAD_MS, a23_mode=False,
             timed_mode=False, source_pause=None, poster_stall=None):
    """Return counters for one schedule.

    a23_mode=True reproduces the current producer: each URB starts at
    `now + lead` and only one URB is in flight.  timed_mode=True keeps the
    same `now + lead` start formula but posts two URBs every 16 ms, so the
    32 ms lead makes consecutive starts contiguous.  timed_mode=False uses
    the proposed persistent frame cursor with two URBs in flight.
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
            start = (t + lead_ms) if (a23_mode or timed_mode) else cursor
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


V24_CYCLE_MS = 96  # post 0 + wait 59-61 + report 19-20 + loop 3-14 (v24)


def simulate_gap(seconds=10, cycle_ms=V24_CYCLE_MS, ring_bytes=RING_BYTES,
                 source_ppm=0):
    """Model the v24 single-burst schedule: 16 ms of wire data per cycle.

    The endpoint delivers one 3072 B URB per `cycle_ms` wall time.  The
    48 kHz source keeps filling the ring, so a continuous source overruns by
    ~80 ms of audio per cycle: this is the structural gap measured on v24
    (96 ms cycle, 16 ms of data), not a scheduling bug.  The model counts
    bytes only; which audio to drop (oldest vs newest) is a design choice.

    source_ppm models the audio clock against the USB/microframe clock.
    """
    ring = 0
    carry = 0
    started = False
    overflowed = False
    posts = sent = underrun = dropped = drop_events = 0
    ring_max = 0
    for t in range(seconds * 1000):
        carry += BYTES_PER_MS * (1_000_000 + source_ppm)
        add = carry // 1_000_000
        carry -= add * 1_000_000
        ring += add
        if ring > ring_bytes:
            dropped += ring - ring_bytes
            overflowed = True
            ring = ring_bytes
        ring_max = max(ring_max, ring)
        if not started and ring >= URB_BYTES:
            started = True
        if started and t % cycle_ms == 0:
            posts += 1
            if overflowed:
                drop_events += 1
                overflowed = False
            if ring >= URB_BYTES:
                ring -= URB_BYTES
                sent += URB_BYTES
            else:
                underrun += URB_BYTES - ring
                ring = 0
    wall_ms = seconds * 1000
    wire_ms = sent / BYTES_PER_MS
    return {
        "seconds": seconds,
        "cycle_ms": cycle_ms,
        "posts": posts,
        "sent_bytes": sent,
        "dropped_bytes": dropped,
        "drop_events": drop_events,
        "underrun_bytes": underrun,
        "wire_ms": wire_ms,
        "host_idle_ms": wall_ms - wire_ms,
        "duty": sent / (wall_ms * BYTES_PER_MS),
        "ring_max_bytes": ring_max,
        "ring_final_bytes": ring,
        "ring_bytes": ring_bytes,
        "source_ppm": source_ppm,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=10)
    args = parser.parse_args()
    scenarios = [
        ("cursor nominal", dict()),
        ("timed a23 double-buffer", dict(timed_mode=True)),
        ("a23 one-at-a-time", dict(a23_mode=True)),
        ("cursor, 200ms source pause", dict(source_pause=(3000, 3200))),
        ("cursor, 20ms poster stall", dict(poster_stall=(5000, 5020))),
    ]
    width = max(len(name) for name, _ in scenarios)
    for name, kwargs in scenarios:
        result = simulate(seconds=args.seconds, **kwargs)
        print(f"{name:<{width}}  " + "  ".join(
            f"{key}={value}" for key, value in result.items() if key != "seconds"))
    for name, kwargs in (
        ("v24 gap 96ms", dict()),
        ("v24 gap, source +100ppm", dict(source_ppm=100)),
    ):
        result = simulate_gap(seconds=args.seconds, **kwargs)
        print(f"{name:<{width}}  " + "  ".join(
            f"{key}={value}" for key, value in result.items() if key != "seconds"))


if __name__ == "__main__":
    main()
