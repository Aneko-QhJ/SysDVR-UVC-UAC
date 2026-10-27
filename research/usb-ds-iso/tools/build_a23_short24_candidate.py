#!/usr/bin/env python3
"""Build an isolated fixed16/24-byte ARM candidate; no deployment or receiver.

The old patch builder is used with a private generated source root. Existing
source, packages, runtime payload headers and consumed permits stay untouched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import build_patch as old


ROOT = Path(__file__).resolve().parents[1]
DEVICE = ROOT / "private/analysis/A23-lifecycle-device-review-20261016"
BASELINE = ROOT / "private/packages-A23-interval1/A"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")
MAGIC = 0x34325349  # IS24, distinct from ISO7 and the legacy payload marker.


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def replace(text, before, after, count=1):
    require(text.count(before) == count, "source anchor changed: " + before)
    return text.replace(before, after)


def verify_tree(root):
    sums = (root / "SHA256SUMS").read_bytes()
    require((root / "COMMITTED").read_text().strip() == sha(sums), "parent seal differs")
    for line in sums.decode().splitlines():
        digest, name = line.split("  ", 1)
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "invalid sealed path")
        require(sha((root / name).read_bytes()) == digest, "parent changed: " + name)
    return sha(sums)


def runtime_header(manifest, nso):
    lines = ["/* Isolated short24 runtime payload, not installed. */",
             "static const unsigned char isoRuntimeBuildId[32] = {" +
             ",".join(str(n) for n in bytes.fromhex(old.BUILD_ID)) + "};"]
    entries = []
    for i, edit in enumerate(manifest["edits"]):
        address = int(edit["address"], 16)
        before, after = bytes.fromhex(edit["before"]), bytes.fromhex(edit["after"])
        require(before == old.read_mapped(nso, address, len(before)) and
                len(before) == len(after) <= 1024, "runtime edit mismatch")
        for label, raw in (("before", before), ("after", after)):
            lines.append(f"static const unsigned char isoRuntime_{i}_{label}[] = {{" +
                         ",".join(str(n) for n in raw) + "};")
        entries.append(f"{{{address},{len(before)},isoRuntime_{i}_before,isoRuntime_{i}_after}}")
    lines.append("static const IsoRuntimeEdit isoRuntimeEdits[] = {" + ",".join(entries) + "};")
    return "\n".join(lines) + "\n"


def build(output):
    output = output.resolve()
    require(not output.exists(), "fresh output required")
    parent_seal = verify_tree(DEVICE)
    baseline = json.loads((BASELINE / "manifest.json").read_text())
    require(baseline["diagnostics_magic"] == "ISO7" and baseline["interval"] == 1 and
            baseline["burst_packets"] == 16 and baseline["mps"] == 256, "baseline shape differs")
    raw = (ROOT / "private/module/exefs/main").read_bytes()
    nso = old.validate_module(raw)
    source = (ROOT / "patches/iso_burst_context.S").read_text()
    for before, after, count in [
        ("#3072", "#384", 2), ("#192", "#24", 5),
        ("#0x374f, lsl #16 /* ISO7: bInterval1 */",
         "#0x3432, lsl #16 /* IS24: fixed16 short packets */", 1)]:
        source = replace(source, before, after, count)
    output.mkdir(parents=True)
    generated = output / "controller-source/patches"
    generated.mkdir(parents=True)
    (generated / "iso_burst_context.S").write_text(source)
    patch = output / "controller/A"
    previous = old.ROOT
    try:
        old.ROOT = generated.parent
        old.build(nso, 1, TOOLCHAIN, patch, frame_lead=32, mps=256, burst=True,
                  event_audit=True, context_audit=True, followup_sia=True, interval=1)
    finally:
        old.ROOT = previous
    manifest = json.loads((patch / "manifest.json").read_text())
    code, before_code = (patch / "inject.bin").read_bytes(), (BASELINE / "inject.bin").read_bytes()
    require(sha(before_code) == sha(bytes.fromhex(baseline["edits"][0]["after"])), "baseline binary drift")
    require(len(code) == len(before_code) == 680 and manifest["symbols"] == baseline["symbols"] and
            manifest["edits"][1:] == baseline["edits"][1:], "unrelated controller edits")
    differences = [old.CAVE + i for i in range(0, len(code), 4) if code[i:i+4] != before_code[i:i+4]]
    require(len(differences) == 8, "expected seven length instructions plus one marker")
    manifest.update(schema="A23-short24-controller-offline-1", diagnostics_magic="IS24",
                    packet_bytes=24, transfer_bytes=384, offline_only=True,
                    acquisition_enabled=False, changed_instruction_addresses=differences)
    (patch / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    folder = output / "device"
    folder.mkdir()
    shutil.copytree(DEVICE / "candidate/source", folder / "source")
    header = folder / "source/uvc/iso_probe_protocol.h"
    text = header.read_text()
    text = replace(text, "#define ISO_PROBE_PACKET_SIZE 192", "#define ISO_PROBE_PACKET_SIZE 24")
    text = replace(text, "#define ISO_PROBE_BURST_INTERVAL_MAGIC 0x374f5349u",
                   "#define ISO_PROBE_BURST_INTERVAL_MAGIC 0x34325349u")
    text = replace(text, '(uint8_t)"ISO1"[offset]', '(uint8_t)"IS24"[offset]')
    header.write_text(text)
    path = folder / "source/uvc/uvc_device.c"
    text = replace(path.read_text(), "A23 HS ISO7 bInterval1 followup-SIA experiment",
                   "A23 short24 HS IS24 bInterval1 followup-SIA offline candidate")
    path.write_text(text)
    (folder / "source/uvc/iso_runtime_payload.h").write_text(runtime_header(manifest, nso))
    source_hashes = {p.relative_to(folder).as_posix(): sha(p.read_bytes())
                     for p in sorted((folder / "source").rglob("*"))
                     if p.is_file() and p.name != "ep0_candidate_recipe.h"}
    recipe = sha(json.dumps(dict(schema="A23-short24-device-recipe-1", parent=parent_seal,
        controller_sha256=sha(code), sources=source_hashes), sort_keys=True).encode())
    (folder / "source/uvc/ep0_candidate_recipe.h").write_text(
        "static const uint8_t ep0CandidateRecipe[32]={" +
        ",".join(str(n) for n in bytes.fromhex(recipe)) + "};\n")
    for name in ("sysmodule.json", "main.npdm"):
        shutil.copyfile(DEVICE / "candidate" / name, folder / name)
    (folder / "recipe.json").write_text(json.dumps(dict(schema="A23-short24-device-recipe-1",
        runtime_recipe_sha256=recipe, source_hashes=source_hashes, parent_manifest_sha256=parent_seal,
        packet_bytes=24, packets=16, total_bytes=384, interval=1, mps=256, window_ms=30000), indent=2) + "\n")
    # Replay only ARM compiler/link commands, remapping every output and source.
    # No native fixture, packaging, installer, or hardware command is inherited.
    audit = json.loads((DEVICE / "audit.json").read_text())
    commands = []
    (folder / "objects").mkdir()
    for command in audit["compiler_commands"]:
        if Path(command[0]).name != "aarch64-none-elf-gcc" or "-fsyntax-only" in command:
            continue
        command = [arg.replace(str(DEVICE / "candidate"), str(folder)) for arg in command]
        commands.append(command)
        result = subprocess.run(command, capture_output=True, text=True,
                                env=dict(os.environ, DEVKITPRO="/opt/devkitpro"))
        with (output / "compile.log").open("a") as log:
            log.write(result.stdout + result.stderr)
        require(result.returncode == 0, "ARM compile failed; see compile.log")
    object_count = len(list((folder / "source").rglob("*.c")))
    require(len(list((folder / "objects").glob("*.o"))) == object_count == 14 and
            (folder / "full.elf").exists(), "full14-object ARM link missing")
    for tool, args, name in [("objdump", ["-d"], "disassembly.txt"), ("readelf", ["-Ws"], "symbols.txt")]:
        data = subprocess.check_output([str(TOOLCHAIN / ("aarch64-none-elf-" + tool)), *args, str(folder / "full.elf")])
        (folder / name).write_bytes(data)
    summary = dict(schema="A23-short24-candidate-build-1", parent_manifest_sha256=parent_seal,
        baseline_patch_sha256=baseline["patch_sha256"], changed_instruction_addresses=differences,
        controller_bytes=len(code), device_elf_sha256=sha((folder / "full.elf").read_bytes()),
        controller_sha256=sha(code), runtime_recipe_sha256=recipe,
        object_count=object_count, arm_compiler_jobs=len(commands), compiler_commands=commands,
        source_hashes={str(Path(__file__).relative_to(ROOT)): sha(Path(__file__).read_bytes())},
        host_sdk_receiver_built=False, firmware_packaged=False, deployed=False,
        new_usb_operations=0, acquisition_enabled=False, hardware_verified=False)
    (output / "build.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = build(parser.parse_args().output)
    print(json.dumps({k: result[k] for k in ("controller_bytes", "object_count", "deployed")}))
