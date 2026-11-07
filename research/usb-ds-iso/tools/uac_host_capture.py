#!/usr/bin/env python3
"""Capture one macOS host-side UAC round: unified log + WAV + snapshots.

The device log (SD card) has no wall clock, but macOS logs the isochronous
transaction error, `performStopIO`/`performStartIO` and the pipe abort with
timestamps.  This tool records that stream next to the audio capture and the
USB/audio snapshots, so tools/uac_host_timeline.py can align the two clocks.
No USB, SD or hardware access beyond the requested capture.

Order matters: the log stream must already run when the Switch enumerates
(that line is the clock anchor), but ffmpeg can only open the audio device
after it exists.  Start the tool first, then power the Switch on:

    uac_host_capture.py --out RUN --seconds 20 --wait-audio 30
"""
import argparse
import hashlib
import json
import re
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


def parse_audio_devices(text):
    """Map avfoundation audio index -> name from `-list_devices` stderr."""
    devices, in_audio = {}, False
    for line in text.splitlines():
        if "AVFoundation audio devices:" in line:
            in_audio = True
            continue
        if "AVFoundation video devices:" in line:
            in_audio = False
            continue
        if in_audio:
            match = re.search(r"\[(\d+)\]\s+(.+?)\s*$", line)
            if match:
                devices[int(match.group(1))] = match.group(2)
    return devices


def list_audio_devices():
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-f", "avfoundation",
             "-list_devices", "true", "-i", ""],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    return parse_audio_devices(proc.stderr)


def wait_for_audio(name, timeout):
    """Poll until an audio device whose name contains `name` shows up."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for index, label in list_audio_devices().items():
            if name.lower() in label.lower():
                return index, label
        time.sleep(1.0)
    return None, None


def capture(out, seconds, audio_index, dry_run=False, wait_audio=0.0,
            audio_name="SysDVR"):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    log_cmd = ["log", "stream", "--style", "ndjson", "--level", "debug",
               "--predicate", PREDICATE]
    if dry_run:
        print("log stream ->", out / "host-log.ndjson")
        print(" ".join(log_cmd))
        if wait_audio:
            print(f"then wait up to {wait_audio:.0f} s for an audio device "
                  f"matching {audio_name!r}, then:")
        print("ffmpeg -f avfoundation -i :<index> -t", seconds, "capture.wav")
        return {"dry_run": True}

    log_file = open(out / "host-log.ndjson", "wb")
    log_err = open(out / "host-log.stderr.txt", "wb")
    started = time.time()
    log_proc = subprocess.Popen(log_cmd, stdout=log_file, stderr=log_err)
    print(f"log stream attached (pid {log_proc.pid}); "
          + (f"waiting up to {wait_audio:.0f} s for audio device "
             f"{audio_name!r} - power the Switch on now"
             if wait_audio else "starting ffmpeg in 1 s"), flush=True)
    waited, matched_label = 0.0, None
    try:
        if wait_audio:
            found, matched_label = wait_for_audio(audio_name, wait_audio)
            waited = time.time() - started
            if found is None:
                raise SystemExit(
                    f"no audio device matching {audio_name!r} after "
                    f"{wait_audio:.0f} s; is the Switch powered on?")
            audio_index = found
            print(f"audio device [{audio_index}] {matched_label} after "
                  f"{waited:.1f} s; recording {seconds} s", flush=True)
        else:
            time.sleep(1.0)  # let the stream attach before the audio starts
        wav = out / "capture.wav"
        ffmpeg_cmd = ["ffmpeg", "-hide_banner", "-y", "-f", "avfoundation",
                      "-i", f":{audio_index}", "-t", str(seconds),
                      "-c:a", "pcm_s16le", str(wav)]
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
        "wait_audio": {"requested_s": wait_audio,
                       "waited_s": round(waited, 1),
                       "matched_device": matched_label,
                       "index": audio_index},
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
                        help="avfoundation audio device index (default 2); "
                             "ignored when --wait-audio finds the device")
    parser.add_argument("--wait-audio", type=float, default=0.0, metavar="SEC",
                        help="start the log stream first, then poll up to SEC "
                             "seconds for the Switch audio device before "
                             "starting ffmpeg (required to catch the "
                             "enumeration anchor: start this before powering "
                             "the Switch on)")
    parser.add_argument("--audio-name", default="SysDVR",
                        help="audio device name to wait for (default SysDVR)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the commands without running anything")
    args = parser.parse_args()
    try:
        meta = capture(args.out, args.seconds, args.audio_index, args.dry_run,
                       wait_audio=args.wait_audio, audio_name=args.audio_name)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    if not args.dry_run:
        ff = meta["ffmpeg"]
        print(f"wav {meta['files'].get('capture.wav', {}).get('bytes', 0)} B, "
              f"ffmpeg rc={ff['rc']}, {ff['wall_seconds']:.1f} s wall")
        print(f"log {meta['files'].get('host-log.ndjson', {}).get('bytes', 0)} B"
              f" -> {Path(args.out).resolve()}")
    return 0 if args.dry_run or meta["ffmpeg"]["rc"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
