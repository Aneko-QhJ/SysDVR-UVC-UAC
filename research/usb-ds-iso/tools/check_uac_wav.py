#!/usr/bin/env python3
"""Validate a 10 s UAC capture WAV for the standard-host experiment.

Checks the container format, duration/frame count and simple continuity
statistics.  It does not decide whether the audio content is musically correct;
it only reports what the host captured.
"""
import argparse
import array
import json
import sys
import wave
from pathlib import Path


def check(path, seconds, rate, channels, width):
    with wave.open(str(path), "rb") as wav:
        got_rate = wav.getframerate()
        got_channels = wav.getnchannels()
        got_width = wav.getsampwidth()
        frames = wav.getnframes()
        raw = wav.readframes(frames)
    expected_frames = int(round(seconds * rate))
    data_bytes = frames * channels * width
    result = {
        "file": str(path),
        "rate": got_rate,
        "channels": got_channels,
        "sample_width": got_width,
        "frames": frames,
        "expected_frames": expected_frames,
        "duration_s": frames / got_rate if got_rate else 0.0,
        "data_bytes": len(raw),
        "expected_data_bytes": data_bytes,
        "format_ok": (got_rate == rate and got_channels == channels and got_width == width),
        "duration_ok": abs(frames - expected_frames) <= rate * 0.05,
        "complete": len(raw) == data_bytes,
    }
    warnings = []
    if not result["format_ok"]:
        warnings.append("format_mismatch")
    if not result["duration_ok"]:
        warnings.append("duration_mismatch")
    if not result["complete"]:
        warnings.append("truncated_data")

    if got_width == 2 and got_channels == 2 and raw:
        samples = array.array("h")
        samples.frombytes(raw)
        if sys.byteorder != "little":
            samples.byteswap()
        peak = max(abs(v) for v in samples) if samples else 0
        zero = sum(1 for v in samples if v == 0)
        result["peak"] = peak
        result["zero_fraction"] = zero / len(samples)
        result["distinct_samples"] = len(set(samples))
        # Per-channel largest adjacent step, a cheap discontinuity indicator.
        max_step = 0
        left = samples[0::2]
        right = samples[1::2]
        for channel in (left, right):
            for i in range(1, len(channel)):
                step = abs(channel[i] - channel[i - 1])
                if step > max_step:
                    max_step = step
        result["max_step"] = max_step
        if peak == 0:
            warnings.append("all_silence")
        elif result["zero_fraction"] > 0.99:
            warnings.append("mostly_silence")
        if max_step > 30000:
            warnings.append("large_step")
    result["warnings"] = warnings
    result["ok"] = result["format_ok"] and result["duration_ok"] and result["complete"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--rate", type=int, default=48000)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--width", type=int, default=2)
    args = parser.parse_args(argv)
    if not args.wav.is_file():
        parser.error(f"missing {args.wav}")
    result = check(args.wav, args.seconds, args.rate, args.channels, args.width)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
