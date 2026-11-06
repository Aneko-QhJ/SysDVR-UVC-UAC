#!/usr/bin/env python3
"""Capture one macOS host-side UAC round: unified log + WAV + snapshots.

The device log (SD card) has no wall clock, but macOS logs the isochronous
transaction error, `performStopIO`/`performStartIO` and the pipe abort with
timestamps.  This tool records that stream next to the audio capture and the
USB/audio snapshots, so tools/uac_host_timeline.py can align the two clocks.
No USB, SD or hardware access beyond the requested capture.
"""
import argparse
import hashlib
import json
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# kernel USB messages for our endpoint plus the audio daemon that owns it
PREDICATE = (
    '(process == "kernel" AND (eventMessage CONTAINS "endpoint 0x84" '
    'OR eventMessage CONTAINS "SysDVR" '
    'OR eventMessage CONTAINS "IOUSBHostDevice")) '
    'OR process == "usbaudiod"'
)

SNAPSHOTS = (
    ("usb.txt", ["ioreg", "-p", "IOUSB", "-l", "-w0"]),
    ("audio-engine.txt", ["ioreg", "-r", "-c", "AppleUSBAudioEngine", "-l", "-w0"]),
    ("audio.json", ["system_profiler", "SPAudioDataType", "-json"]),
)


def _iso(epoch):
    local = datetime.fromtimestamp(epoch, timezone.utc).astimezone()
    return {"epoch": round(epoch, 6), "local": local.isoformat(),
            "utc": datetime.fromtimestamp(epoch, timezone.utc).isoformat()}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run_snapshot(path, cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        path.write_text(result.stdout)
        return result.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        path.write_text(f"snapshot failed: {exc}\n")
        return None


def capture(out, seconds, audio_index, dry_run=False):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    log_cmd = ["log", "stream", "--style", "ndjson", "--level", "debug",
               "--predicate", PREDICATE]
    wav = out / "capture.wav"
    ffmpeg_cmd = ["ffmpeg", "-hide_banner", "-y", "-f", "avfoundation",
                  "-i", f":{audio_index}", "-t", str(seconds),
                  "-c:a", "pcm_s16le", str(wav)]
    if dry_run:
        print("log stream ->", out / "host-log.ndjson")
        print(" ".join(log_cmd))
        print(" ".join(ffmpeg_cmd))
        return {"dry_run": True}

    log_file = open(out / "host-log.ndjson", "wb")
    log_err = open(out / "host-log.stderr.txt", "wb")
    started = time.time()
    log_proc = subprocess.Popen(log_cmd, stdout=log_file, stderr=log_err)
    try:
        time.sleep(1.0)  # let the stream attach before the audio starts
        ff_started = time.time()
        ff = subprocess.run(ffmpeg_cmd, capture_output=True, text=True,
                            timeout=seconds + 45)
        ff_wall = time.time() - ff_started
        (out / "capture.log").write_text(ff.stdout + ff.stderr)
    finally:
        stopped = time.time()
        log_proc.send_signal(signal.SIGTERM)
        try:
            log_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            log_proc.kill()
            log_proc.wait(timeout=10)
        log_file.close()
        log_err.close()

    for name, cmd in SNAPSHOTS:
        _run_snapshot(out / name, cmd)

    meta = {
        "schema": "UAC-u2-host-capture-1",
        "started": _iso(started),
        "stopped": _iso(stopped),
        "ffmpeg": {"command": ffmpeg_cmd, "rc": ff.returncode,
                   "wall_seconds": round(ff_wall, 3)},
        "log_stream": {"command": log_cmd, "predicate": PREDICATE},
        "audio_index": audio_index,
        "seconds": seconds,
        "files": {},
    }
    for name in ("host-log.ndjson", "capture.wav"):
        path = out / name
        if path.is_file():
            meta["files"][name] = {"bytes": path.stat().st_size,
                                   "sha256": _sha256(path)}
    (out / "capture-meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True,
                        help="directory for host-log.ndjson, capture.wav, meta")
    parser.add_argument("--seconds", type=int, default=20,
                        help="audio capture length (default 20)")
    parser.add_argument("--audio-index", type=int, default=2,
                        help="avfoundation audio device index (default 2; "
                             "run ffmpeg -f avfoundation -list_devices true "
                             "-i '' to enumerate)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the commands without running anything")
    args = parser.parse_args()
    meta = capture(args.out, args.seconds, args.audio_index, args.dry_run)
    if not args.dry_run:
        ff = meta["ffmpeg"]
        print(f"wav {meta['files'].get('capture.wav', {}).get('bytes', 0)} B, "
              f"ffmpeg rc={ff['rc']}, {ff['wall_seconds']:.1f} s wall")
        print(f"log {meta['files'].get('host-log.ndjson', {}).get('bytes', 0)} B"
              f" -> {Path(args.out).resolve()}")
    return 0 if args.dry_run or meta["ffmpeg"]["rc"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
