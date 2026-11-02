#!/usr/bin/env python3
"""Build the U2 payload: UAC AS alt1 ISO producer plus the 26-edit base.

The producer is patches/iso_burst_uac84.S, the A23 16x192 B cave ported to
endpoint 0x84 / MPS192 / bmAttributes 0x05.  The payload carries 30 runtime
edits:

  1  cave injection at 0x68d54 (684 B, exactly the RX padding page)
  3  hooks: iso_enter (0x30364), iso_event (0x30898), iso_report (0x2cbe0)
  18 descriptor-length edits (u16 wTotalLength/offset)
  8  alt0-filter NOPs (install the alt1 endpoint)

Every "before" word is validated against the usb NSO and every branch is
encoded here; the assembler only produces the cave bytes.  No USB/SD/hardware
access.
"""
import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

from build_patch import (
    CAVE,
    CAVE_END,
    branch,
    branch_eq,
    read_mapped,
    validate_module,
)
from build_uac_descriptor_payload import (
    EDITS as DESCRIPTOR_EDITS,
    USB_BUILD_ID,
    USB_ELF_SHA256,
)
from build_uac_u2_base_payload import NOP_EDITS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NSO = ROOT / "private/module/exefs/main"
WORK = ROOT / "private/analysis/UAC-u2-producer-20261030"
ASM = ROOT / "patches/iso_burst_uac84.S"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")

ENTRY_HOOK = 0x30364          # b.eq original ISO branch -> iso_enter
EVENT_HOOK = 0x30898          # bl original event handler -> iso_event (link)
REPORT_HOOK = 0x2CBE0         # report epilogue -> iso_report
ENDPOINT_WORD = 0x00C00584    # addr 0x84, attrs 0x05 (ISO|async), MPS 192
BURST_BYTES = 16 * 192
EDITS_COUNT = 1 + 3 + len(DESCRIPTOR_EDITS) + len(NOP_EDITS)
EDITS_COUNT_NO_REPORT = 1 + 2 + len(DESCRIPTOR_EDITS) + len(NOP_EDITS)

# v29: queue patch.  0x2c520 only submits the queued entry when the queue is
# empty; the patch submits the entry it just appended and skips the
# completion-path auto-submit so the app owns the in-flight window.
QUEUE_STUB_ADDR = 0x0C4
QUEUE_GATE_ADDR = 0x2C628
QUEUE_SKIP_ADDR = 0x2C80C
QUEUE_STUB_BEFORE = bytes(12)
QUEUE_STUB_AFTER = bytes.fromhex("890500512909001258b10014")
QUEUE_GATE_BEFORE = bytes.fromhex("01020054")
QUEUE_GATE_AFTER = bytes.fromhex("a74eff17")
QUEUE_SKIP_BEFORE = bytes.fromhex("08020034")
QUEUE_SKIP_AFTER = bytes.fromhex("10000014")
QUEUE_EDITS = 3 if QUEUE_STUB_ADDR else 0

# v29d: the ring link must follow an even number of aligned 0x200 TD sets.
# The driver writes its link at +0xff0, which sits inside the 8th set, so the
# cave split a set at the link and the per-set mailbox drifted; both sides move
# the link to +0xc00 (six aligned sets).  Four inline copies of the endpoint
# setup (install, re-arm, alt set, completion error) each clear and fill the
# 16-byte link TRB, so each copy needs the address and both slot clears.
LINK_EDITS = tuple(
    (address, bytes.fromhex(before), bytes.fromhex(after), reason)
    for address, before, after, reason in (
        (0x2F530, "09c13f91", "09013091", "link slot: ring+0xff0 -> ring+0xc00"),
        (0x2F538, "1ffd07f9", "1f0506f9", "clear the new slot instead of ring+0xff8"),
        (0x2F53C, "1ff907f9", "1f0106f9", "clear the new slot instead of ring+0xff0"),
        (0x2FF40, "09c13f91", "09013091", "link slot: ring+0xff0 -> ring+0xc00"),
        (0x2FF48, "1ffd07f9", "1f0506f9", "clear the new slot instead of ring+0xff8"),
        (0x2FF4C, "1ff907f9", "1f0106f9", "clear the new slot instead of ring+0xff0"),
        (0x30578, "09c13f91", "09013091", "link slot: ring+0xff0 -> ring+0xc00"),
        (0x30580, "1ffd07f9", "1f0506f9", "clear the new slot instead of ring+0xff8"),
        (0x30584, "1ff907f9", "1f0106f9", "clear the new slot instead of ring+0xff0"),
        (0x310C8, "09c13f91", "09013091", "link slot: ring+0xff0 -> ring+0xc00"),
        (0x310D0, "1ffd07f9", "1f0506f9", "clear the new slot instead of ring+0xff8"),
        (0x310D4, "1ff907f9", "1f0106f9", "clear the new slot instead of ring+0xff0"),
    )
)
LINK_EDIT_COUNT = len(LINK_EDITS)

# v29h: the alt0 teardown makes usb:ds map one more request; when its IOVA
# node allocator returns NULL (0x3140 -> 0xa410), the map error path branches
# to the panic stub at 0x40d0.  Return the failure to the submit path instead
# (0x409c accounts it and returns 0), so alt0 gets an error rather than a
# User Break.
MAP_SOFT_EDITS = (
    (0x3FE0, bytes.fromhex("800700b4"), bytes.fromhex("e00500b4"),
     "DMA-map node exhaustion returns an error instead of panicking"),
)
MAP_SOFT_EDIT_COUNT = len(MAP_SOFT_EDITS)
BREAKER_HOOK = 0x302C0          # bl complete_original in the ISO submit error path
BREAKER_BEFORE = bytes.fromhex("b0e9ff97")  # bl 0x2a980
BREAKER_AFTER = bytes.fromhex("1f2003d5")   # nop
EDITS_COUNT_BREAKER = EDITS_COUNT + 1
EDITS_COUNT_NO_REPORT_BREAKER = EDITS_COUNT_NO_REPORT + 1

LINKER = (
    "SECTIONS { . = 0x68d54; .text : { *(.text.iso) } }\n"
    "doorbell_tail = 0x31c74; reject_original = 0x30394;\n"
    "event_original = 0x30f70; complete_original = 0x2a980; "
    "report_epilogue = 0x2cbe4; copy_original = 0x60e50;\n"
    "rearm_endpoint = 0x2feb0; /* driver endpoint setup: commit + unhalt */\n"
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def payload_ready(work):
    """Load a generated manifest, refusing a missing or stale payload."""
    header = work / "uac_u2_payload.h"
    manifest_path = work / "manifest.json"
    if not header.is_file() or not manifest_path.is_file():
        raise SystemExit(f"missing payload under {work}; run build_uac_u2_producer.py")
    doc = json.loads(manifest_path.read_text())
    allowed = (EDITS_COUNT, EDITS_COUNT_BREAKER,
               EDITS_COUNT_NO_REPORT, EDITS_COUNT_NO_REPORT_BREAKER)
    if doc.get("driver_queue"):
        allowed = tuple(value + QUEUE_EDITS for value in allowed)
    if doc.get("driver_link"):
        allowed = tuple(value + LINK_EDIT_COUNT for value in allowed)
    if doc.get("driver_map_soft"):
        allowed = tuple(value + MAP_SOFT_EDIT_COUNT for value in allowed)
    if doc["edit_count"] not in allowed:
        raise SystemExit("payload manifest is inconsistent; rebuild it")
    if doc["cave_bytes"] > CAVE_END - CAVE:
        raise SystemExit("payload manifest is inconsistent; rebuild it")
    if sha256(header.read_bytes()) != doc["header_sha256"]:
        raise SystemExit("payload header is stale; rebuild it")
    return doc


def assemble(toolchain, out, asm=ASM, require_report=True):
    """Assemble a cave at its linker address and return (code, symbols)."""
    out.mkdir(parents=True, exist_ok=True)
    linker = out / "inject.ld"
    linker.write_text(LINKER)
    obj, elf, binary = (out / name for name in ("inject.o", "inject.elf", "inject.bin"))

    def run(tool, *args):
        subprocess.run(
            [str(toolchain / ("aarch64-none-elf-" + tool)), *map(str, args)],
            check=True,
        )

    run("gcc", "-c", asm, "-o", obj)
    run("ld", "-T", linker, obj, "-o", elf)
    run("objcopy", "-O", "binary", "--only-section=.text", elf, binary)
    symbols = {}
    nm = subprocess.check_output(
        [str(toolchain / "aarch64-none-elf-nm"), str(elf)], text=True
    )
    for line in nm.splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    required = ("iso_enter", "iso_event")
    if require_report:
        required += ("iso_report",)
    for name in required:
        if name not in symbols:
            raise ValueError(f"assembler lost symbol {name}")
    return binary.read_bytes(), symbols


def build_edits(nso, code, symbols, breaker=False, report=True,
                driver_queue=False, driver_link=False, driver_map_soft=False):
    """Return [(address, before, after, reason)] with every before verified."""
    if not code or CAVE + len(code) > CAVE_END:
        raise ValueError(
            f"cave {len(code)} B does not fit {CAVE_END - CAVE} B of RX padding"
        )
    edits = []

    def edit(address, before, after, reason):
        actual = read_mapped(nso, address, len(before))
        if actual != before:
            raise ValueError(
                f"{address:#x}: expected {before.hex()}, found {actual.hex()}"
            )
        if len(before) != len(after):
            raise ValueError(f"{address:#x}: edit length mismatch")
        edits.append((address, before, after, reason))

    edit(CAVE, bytes(len(code)), code, "UAC alt1 ISO producer cave")
    edit(
        ENTRY_HOOK,
        bytes.fromhex("80010054"),
        branch_eq(ENTRY_HOOK, symbols["iso_enter"]),
        "ISO submit enters the UAC producer; keep the non-ISO branch condition",
    )
    edit(
        EVENT_HOOK,
        bytes.fromhex("b6010094"),
        branch(EVENT_HOOK, symbols["iso_event"], link=True),
        "filter transfer events for the producer mailbox",
    )
    if report:
        edit(
            REPORT_HOOK,
            bytes.fromhex("60420091"),
            branch(REPORT_HOOK, symbols["iso_report"]),
            "diagnostics only for the empty report payload",
        )
    for address, before, after in DESCRIPTOR_EDITS:
        edit(
            address,
            struct.pack("<I", before),
            struct.pack("<I", after),
            "widen the usb:ds configuration length/offset to u16",
        )
    for address, before, after in NOP_EDITS:
        edit(
            address,
            struct.pack("<I", before),
            struct.pack("<I", after),
            "install the alt1 endpoint (NOP the alt0-only filter)",
        )
    if breaker:
        edit(BREAKER_HOOK, BREAKER_BEFORE, BREAKER_AFTER,
             "break the completion/retry recursion: skip the ISO submit error completion")
    if driver_queue:
        edit(QUEUE_STUB_ADDR, QUEUE_STUB_BEFORE, QUEUE_STUB_AFTER,
             "queue stub: submit the entry just appended at the tail")
        edit(QUEUE_GATE_ADDR, QUEUE_GATE_BEFORE, QUEUE_GATE_AFTER,
             "always run the submit block instead of only when the queue is empty")
        edit(QUEUE_SKIP_ADDR, QUEUE_SKIP_BEFORE, QUEUE_SKIP_AFTER,
             "skip the completion-path auto-submit (post-time submit owns it)")
    if driver_link:
        for address, before, after, reason in LINK_EDITS:
            edit(address, before, after, reason)
    if driver_map_soft:
        for address, before, after, reason in MAP_SOFT_EDITS:
            edit(address, before, after, reason)
    expected = ((EDITS_COUNT if report else EDITS_COUNT_NO_REPORT)
                + (1 if breaker else 0) + (QUEUE_EDITS if driver_queue else 0)
                + (LINK_EDIT_COUNT if driver_link else 0)
                + (MAP_SOFT_EDIT_COUNT if driver_map_soft else 0))
    if len(edits) != expected:
        raise ValueError(f"expected {expected} edits, built {len(edits)}")
    addresses = [address for address, _b, _a, _r in edits]
    if len(addresses) != len(set(addresses)):
        raise ValueError("overlapping edits")
    if sum(1 for address, *_ in edits if address == CAVE) != 1:
        raise ValueError("missing cave edit")
    return sorted(edits, key=lambda item: item[0])


def render(edits):
    lines = [
        "/* Generated by tools/build_uac_u2_producer.py; not tracked. */",
        "static const unsigned char uacU2BuildId[32]={"
        + ",".join(str(b) for b in USB_BUILD_ID)
        + "};",
    ]
    for i, (_address, before, after, _reason) in enumerate(edits):
        for label, data in (("before", before), ("after", after)):
            lines.append(
                f"static const unsigned char uacU2_{i}_{label}[]={{"
                + ",".join(str(b) for b in data)
                + "};"
            )
    records = [
        f"{{0x{address:x},{len(before)},uacU2_{i}_before,uacU2_{i}_after}}"
        for i, (address, before, _after, _reason) in enumerate(edits)
    ]
    lines.append("static const IsoRuntimeEdit uacU2Edits[]={" + ",".join(records) + "};")
    return "\n".join(lines) + "\n"


def manifest(edits, code, symbols, breaker=False, asm=ASM, report=True,
             segments=1, frames=None, driver_queue=False, driver_link=False,
             driver_map_soft=False):
    if frames is None:
        frames = 16 * segments
    return {
        "schema": "UAC-u2-producer-payload-1",
        "assembly": str(asm.relative_to(ROOT)),
        "assembly_sha256": sha256(asm.read_bytes()),
        "build_id": USB_BUILD_ID.hex().upper(),
        "elf_sha256": USB_ELF_SHA256,
        "cave_address": hex(CAVE),
        "cave_bytes": len(code),
        "cave_limit": CAVE_END - CAVE,
        "cave_free": CAVE_END - CAVE - len(code),
        "cave_sha256": sha256(code),
        "endpoint": {"word": hex(ENDPOINT_WORD), "address": "0x84",
                     "attributes": "0x05", "max_packet": 192, "interval": 4},
        "segments": segments,
        "frames": frames,
        "burst_bytes": 192 * frames,
        "edit_count": len(edits),
        "counts": {"cave": 1, "branch": (3 if report else 2) + (1 if breaker else 0),
                   "descriptor": len(DESCRIPTOR_EDITS), "nop": len(NOP_EDITS)},
        "breaker": bool(breaker),
        "report_hook": bool(report),
        "driver_queue": bool(driver_queue),
        "driver_link": bool(driver_link),
        "driver_map_soft": bool(driver_map_soft),
        "link_slot": "0xc00",
        "symbols": {name: hex(symbols[name])
                    for name in (("iso_enter", "iso_event", "iso_report")
                                 if report else ("iso_enter", "iso_event"))},
        "edits": [
            {"address": hex(address), "before": before.hex(),
             "after": after.hex(), "reason": reason}
            for address, before, after, reason in edits
        ],
        "includes_producer": True,
        "hardware_verified": False,
        "usb_accessed": False,
        "sd_accessed": False,
    }


def check(nso, work):
    """Validate an existing payload without assembling or writing anything."""
    header = (work / "uac_u2_payload.h").read_text()
    doc = json.loads((work / "manifest.json").read_text())
    asm = ROOT / doc["assembly"]
    if doc["assembly_sha256"] != sha256(asm.read_bytes()):
        raise SystemExit(f"payload is stale: {doc['assembly']} changed")
    report = doc.get("report_hook", True)
    expected = {"cave": 1,
                "branch": (3 if report else 2) + (1 if doc.get("breaker") else 0),
                "descriptor": len(DESCRIPTOR_EDITS), "nop": len(NOP_EDITS)}
    if doc["counts"] != expected:
        raise SystemExit("unexpected edit counts")
    allowed = (EDITS_COUNT if report else EDITS_COUNT_NO_REPORT,
               EDITS_COUNT_BREAKER if report else EDITS_COUNT_NO_REPORT_BREAKER)
    if doc.get("driver_queue"):
        allowed = tuple(value + QUEUE_EDITS for value in allowed)
    if doc.get("driver_link"):
        allowed = tuple(value + LINK_EDIT_COUNT for value in allowed)
    if doc.get("driver_map_soft"):
        allowed = tuple(value + MAP_SOFT_EDIT_COUNT for value in allowed)
    if doc["edit_count"] not in allowed:
        raise SystemExit("unexpected edit total")
    for entry in doc["edits"]:
        address = int(entry["address"], 16)
        before = bytes.fromhex(entry["before"])
        after = bytes.fromhex(entry["after"])
        if read_mapped(nso, address, len(before)) != before:
            raise SystemExit(f"before word mismatch at {address:#x}")
        if header.count(f"{{0x{address:x},{len(before)},") != 1:
            raise SystemExit(f"header record mismatch at {address:#x}")
    cave = next(e for e in doc["edits"] if int(e["address"], 16) == CAVE)
    code = bytes.fromhex(cave["after"])
    if len(code) != doc["cave_bytes"] or sha256(code) != doc["cave_sha256"]:
        raise SystemExit("cave bytes/hash mismatch")
    if not endpoint_constants_ok(code, require_report=report):
        raise SystemExit("cave does not encode endpoint 0x84 / MPS192 / attrs 0x05")
    segments = doc.get("segments", 1)
    frames = doc.get("frames", 16 * segments)
    if doc["burst_bytes"] != 192 * frames:
        raise SystemExit("burst_bytes does not match frames")
    print(f"ok: {len(doc['edits'])} edits, cave {len(code)}/{doc['cave_limit']} B")


def endpoint_constants_ok(code, require_report=True):
    """The ported cave must build 0x00C00584, complete and report 0x84."""
    words = struct.unpack_from(f"<{len(code) // 4}I", code, 0)
    low = high = False
    for i, word in enumerate(words):
        if (word & 0xFFE0001F) == 0x5280000A and (word >> 5) & 0xFFFF == 0x584:
            low = True
            if i + 1 < len(words):
                nxt = words[i + 1]
                high = (
                    (nxt & 0xFFE0001F) == 0x72A0000A
                    and (nxt >> 5) & 0xFFFF == 0x00C0
                    and (nxt >> 21) & 0x3 == 1
                )
    report_word = 0x7102111F in words  # cmp w8, #0x84 (iso_report only)
    return (
        low
        and high
        and 0x52801081 in words  # mov w1, #0x84
        and (report_word or not require_report)
    )


def main():
    global ENDPOINT_WORD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nso", type=Path, default=DEFAULT_NSO)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--toolchain", type=Path, default=TOOLCHAIN)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--breaker", action="store_true",
                        help="add the 0x302c0 error-completion breaker edit")
    parser.add_argument("--asm", type=Path, default=ASM,
                        help="cave assembly (default patches/iso_burst_uac84.S)")
    parser.add_argument("--segments", type=int, default=1, choices=(1, 2),
                        help="v28 only: 3072 B segments in one transfer (1..2)")
    parser.add_argument("--driver-queue", action="store_true",
                        help="v29: submit the appended request immediately and "
                             "skip the completion auto-submit")
    parser.add_argument("--driver-link", action="store_true",
                        help="v29d: move the driver ring link from +0xff0 to "
                             "+0xc00 so six aligned TD sets fit")
    parser.add_argument("--driver-map-soft", action="store_true",
                        help="v29h: return DMA-map node exhaustion as an error "
                             "instead of the 0x40d0 panic")
    parser.add_argument("--frames", type=int, default=None,
                        help="v28 only: 192 B frames in one transfer (1..32; "
                             "overrides --segments)")
    parser.add_argument("--endpoint-word", type=lambda x: int(x, 0),
                        default=ENDPOINT_WORD,
                        help="endpoint descriptor word (default 0x00C00584)")
    parser.add_argument("--no-report", action="store_true",
                        help="omit the 0x2cbe0 report hook (driver report builder)")
    args = parser.parse_args()
    ENDPOINT_WORD = args.endpoint_word
    work = args.work.resolve()
    args.asm = args.asm.resolve()
    nso = validate_module(args.nso.read_bytes())

    if args.check:
        check(nso, work)
        return

    report = not args.no_report
    code, symbols = assemble(args.toolchain, work / "asm", args.asm,
                             require_report=report)
    edits = build_edits(nso, code, symbols, breaker=args.breaker, report=report,
                        driver_queue=args.driver_queue, driver_link=args.driver_link,
                        driver_map_soft=args.driver_map_soft)
    header = render(edits)
    if args.frames is not None and not 1 <= args.frames <= 32:
        raise SystemExit("--frames must be 1..32")
    doc = manifest(edits, code, symbols, breaker=args.breaker, asm=args.asm,
                   report=report, segments=args.segments, frames=args.frames,
                   driver_queue=args.driver_queue, driver_link=args.driver_link,
                   driver_map_soft=args.driver_map_soft)
    doc["header_sha256"] = sha256(header.encode())
    work.mkdir(parents=True, exist_ok=True)
    (work / "uac_u2_payload.h").write_text(header)
    (work / "manifest.json").write_text(json.dumps(doc, indent=2) + "\n")
    print(
        f"wrote {work / 'uac_u2_payload.h'}: {len(edits)} edits, "
        f"cave {len(code)}/{CAVE_END - CAVE} B, "
        f"endpoint {ENDPOINT_WORD:#010x}, {doc['frames']} frame(s)"
        + (", driver-queue" if doc["driver_queue"] else "")
        + (", driver-link" if doc["driver_link"] else "")
        + (", driver-map-soft" if doc["driver_map_soft"] else "")
    )


if __name__ == "__main__":
    main()
