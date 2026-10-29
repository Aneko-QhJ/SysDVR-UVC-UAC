#!/usr/bin/env python3
"""Build the U2 base probe: 18 descriptor edits + 8 alt0-filter NOPs.

No ISO producer is included yet, so this build is for payload/build validation
only; posting data still needs the producer port.  No USB/SD/hardware access.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from build_uac_u2_base_payload import (
    DEFAULT_ELF,
    EDITS,
    load_elf_sections,
    render,
    validate_all,
)

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
WORK = ROOT / "private/analysis/UAC-u2-base-20261030"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()

    args.work = args.work.resolve()
    defines = (
        "-DUAC_HOST_PROBE -DUAC_U2_BASE_PATCH -DFILE_LOGGING "
        f"-I{args.work}"
    )
    data = args.elf.read_bytes()
    _raw, sections = load_elf_sections(args.elf)
    validate_all(data, sections)
    header = render()
    args.work.mkdir(parents=True, exist_ok=True)
    (args.work / "uac_u2_base_payload.h").write_text(header)

    objects = args.work / "build/objects"
    outputs = args.work / "build/outputs"
    objects.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
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
    if b"u2-base" not in elf.read_bytes():
        raise SystemExit("u2-base patch log is missing from exefs.elf")

    record = {
        "schema": "UAC-u2-base-probe-build-1",
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "defines": defines,
        "build_command": " ".join(cmd),
        "payload": {
            "descriptor_edits": 18,
            "nop_edits": 8,
            "edit_count": len(EDITS),
            "includes_producer": False,
            "header_sha256": sha256(args.work / "uac_u2_base_payload.h"),
        },
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
