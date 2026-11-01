#!/usr/bin/env python3
"""Build the U2 probe: the UAC alt1 producer payload with the burst trigger.

Requires the payload from tools/build_uac_u2_producer.py.  The build is
UAC_HOST_PROBE + UAC_U2_PATCH + FILE_LOGGING; the host entry is host/uac-burst.
No USB/SD/hardware access.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from build_uac_u2_producer import CAVE_END, WORK, payload_ready

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--define", action="append", default=[],
                        help="extra compiler define (without -D)")
    args = parser.parse_args()

    args.work = args.work.resolve()
    entry = payload_ready(args.work)
    outputs = (args.output or args.work / "build/outputs").resolve()
    objects = args.work / "build/objects"
    objects.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)

    defines = (
        "-DUAC_HOST_PROBE -DUAC_U2_PATCH -DFILE_LOGGING "
        + "".join(f"-D{d} " for d in args.define)
        + f"-I{args.work}"
    )
    cmd = [
        "make", "-B", f"-j{args.jobs}", "TARGET=exefs",
        f"BUILD={objects.relative_to(REPO)}",
        f"OUTPUT_DIR={outputs.relative_to(REPO)}",
        f"DEFINES={defines}",
    ]
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-2000:])
        print(result.stderr[-2000:], file=sys.stderr)
        raise SystemExit(result.returncode)

    nsp = outputs / "exefs.nsp"
    elf = outputs / "exefs.elf"
    markers = [b"UAC U2 post", b"UAC U2 install"]
    if "UAC_U2_PIPELINE" in args.define:
        markers.append(b"UAC U2 pipe end")
    else:
        markers.append(b"UAC U2 complete")
    for marker in markers:
        if marker not in elf.read_bytes():
            raise SystemExit(f"missing compile-time marker {marker!r}")

    record = {
        "schema": "UAC-u2-probe-build-1",
        "payload": {
            "header": str(args.work / "uac_u2_payload.h"),
            "header_sha256": entry["header_sha256"],
            "edit_count": entry["edit_count"],
            "cave_bytes": entry["cave_bytes"],
            "cave_limit": CAVE_END - 0x68D54,
            "cave_sha256": entry["cave_sha256"],
            "endpoint_word": entry["endpoint"]["word"],
            "burst_bytes": entry["burst_bytes"],
        },
        "defines": defines,
        "output": {
            "nsp": str(nsp),
            "sha256": sha256(nsp),
            "size": nsp.stat().st_size,
            "nso_sha256": sha256(outputs / "exefs.nso"),
        },
        "usb_operations": 0,
        "sd_operations": 0,
        "hardware_runs": 0,
    }
    (args.work / "build-result.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record["output"], indent=2))
    print(f"wrote {args.work / 'build-result.json'}")


if __name__ == "__main__":
    main()
