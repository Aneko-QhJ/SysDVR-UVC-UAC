#!/usr/bin/env python3
"""Build the UAC enumeration probe with the descriptor-only runtime patch.

Generates uac_descriptor_payload.h, compiles source/ with
-DUAC_HOST_PROBE -DUAC_DESCRIPTOR_PATCH -DFILE_LOGGING, and records the NSP
hash.  The patch is applied by the app at boot, via dmnt, before usbDsEnable();
it contains only the 18 configuration-length edits.  No USB/SD/hardware access.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from build_uac_descriptor_payload import (
    DEFAULT_ELF,
    EDITS,
    USB_ELF_SHA256,
    load_elf_sections,
    manifest,
    render,
    validate,
)

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
WORK = ROOT / "private/analysis/UAC-descriptor-patch-20261029"
DEFINES = (
    "-DUAC_HOST_PROBE -DUAC_DESCRIPTOR_PATCH -DFILE_LOGGING "
    f"-I{WORK}"
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()

    data = args.elf.read_bytes()
    _raw, sections = load_elf_sections(args.elf)
    validate(data, sections)
    header = render()
    args.work.mkdir(parents=True, exist_ok=True)
    (args.work / "uac_descriptor_payload.h").write_text(header)
    (args.work / "manifest.json").write_text(json.dumps(manifest(header, args.elf), indent=2) + "\n")

    objects = args.work / "build/objects"
    outputs = args.work / "build/outputs"
    objects.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    cmd = [
        "make", "-B", f"-j{args.jobs}", "TARGET=exefs",
        f"BUILD={objects.relative_to(REPO)}",
        f"OUTPUT_DIR={outputs.relative_to(REPO)}",
        f"DEFINES={DEFINES}",
    ]
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout[-2000:])
        print(result.stderr[-2000:], file=sys.stderr)
        raise SystemExit(result.returncode)

    nsp = outputs / "exefs.nsp"
    elf = outputs / "exefs.elf"
    if not nsp.is_file() or not elf.is_file():
        raise SystemExit("build did not produce exefs.nsp/exefs.elf")
    if b"UAC descriptor patch failed; refusing to enable the device" not in elf.read_bytes():
        raise SystemExit("patch code is missing from exefs.elf")

    record = {
        "schema": "UAC-descriptor-probe-build-1",
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "defines": DEFINES,
        "build_command": " ".join(cmd),
        "elf": {
            "path": str(args.elf),
            "sha256": USB_ELF_SHA256,
            "size": len(data),
        },
        "payload": {
            "edits": len(EDITS),
            "includes_iso_edits": False,
            "header_sha256": sha256(args.work / "uac_descriptor_payload.h"),
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
