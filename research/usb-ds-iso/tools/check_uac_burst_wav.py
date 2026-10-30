#!/usr/bin/env python3
"""Find the U2 diagnostic 1 kHz square burst in a captured WAV.

The v4 U2 build fills the one-shot 3072-byte buffer with 16 ms of 1 kHz
square wave at -12 dBFS.  If the host captures the UAC stream to WAV, a
non-silent ~16 ms segment with a ~2 kHz zero-crossing rate is evidence that
the burst actually reached EP 0x84.

Usage:
  ffmpeg -f avfoundation -i ":2" -c:a pcm_s16le -t 3 capture.wav
  python3 tools/check_uac_burst_wav.py capture.wav

No USB/SD/hardware access.
"""
import argparse
import json
import struct
import sys
import wave
from pathlib import Path


def read_wav(path):
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        raise SystemExit(f"expected 16-bit PCM, got {width * 8}-bit")
    values = struct.unpack("<%dh" % (len(raw) // 2), raw)
    if channels == 1:
        return rate, list(values)
    frames = [
        sum(values[i:i + channels]) // channels
        for i in range(0, len(values) - channels + 1, channels)
    ]
    return rate, frames


def detect(rate, frames, min_ms=8, threshold=500, zc_lo=1500, zc_hi=2500):
    """Return the first non-silent run with a 1 kHz square-like ZC rate."""
    window = max(1, rate // 1000)
    runs = []
    start = None
    peak = 0
    for offset in range(0, len(frames) - window + 1, window):
        chunk = frames[offset:offset + window]
        level = max(abs(x) for x in chunk)
        if level >= threshold:
            if start is None:
                start = offset
            peak = max(peak, level)
        elif start is not None:
            runs.append((start, offset, peak))
            start, peak = None, 0
    if start is not None:
        runs.append((start, len(frames), peak))

    results = []
    for begin, end, peak in runs:
        duration_ms = (end - begin) * 1000.0 / rate
        if duration_ms < min_ms:
            continue
        segment = frames[begin:end]
        crossings = sum(
            1 for a, b in zip(segment, segment[1:]) if (a < 0) != (b < 0)
        )
        zc_rate = crossings * rate / max(1, len(segment))
        result = {
            "start_ms": round(begin * 1000.0 / rate, 3),
            "duration_ms": round(duration_ms, 3),
            "peak": peak,
            "zero_crossings_per_s": round(zc_rate, 1),
            "square_1khz": zc_lo <= zc_rate <= zc_hi,
        }
        results.append(result)
        if result["square_1khz"]:
            return result, results
    return None, results


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("wav", type=Path, help="16-bit PCM WAV capture")
    parser.add_argument("--min-ms", type=float, default=8.0,
                        help="minimum non-silent segment in ms (default 8)")
    parser.add_argument("--threshold", type=int, default=500,
                        help="absolute 16-bit level considered non-silent")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()

    if not args.wav.is_file():
        raise SystemExit(f"missing {args.wav}")
    rate, frames = read_wav(args.wav)
    found, runs = detect(rate, frames, min_ms=args.min_ms,
                         threshold=args.threshold)
    report = {
        "wav": str(args.wav),
        "sample_rate": rate,
        "frames": len(frames),
        "candidate_runs": runs,
        "burst": found,
        "passed": bool(found),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"wav={args.wav} rate={rate} frames={len(frames)}")
        for run in runs:
            print(f"  run start={run['start_ms']}ms dur={run['duration_ms']}ms "
                  f"peak={run['peak']} zc={run['zero_crossings_per_s']}/s "
                  f"square={run['square_1khz']}")
        print("PASS" if found else "FAIL: no 1 kHz square burst found")
    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
