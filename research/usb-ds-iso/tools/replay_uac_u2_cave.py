#!/usr/bin/env python3
"""Replay the A23 and U2 producer caves under Unicorn and compare the TRB ring.

The A23 cave (patches/iso_burst_patch.S) is the hardware-proven producer; the
U2 cave (patches/iso_burst_uac84.S) only changes the endpoint word and the
completion/report constants.  This replays `iso_enter` for both with a
synthetic usb:ds endpoint object and asserts:

  * the EP0x84 cave accepts the UAC descriptor and rejects the vendor one,
  * the EP0x83 cave does the inverse,
  * both accepted runs build byte-identical TRB rings and mailbox state,
  * the ring has 16 Isoch + 16 ED TRBs with the expected addresses/lengths.

Requires unicorn (not a repo dependency; see UAC_U2_BURST.md for the local
venv command).  No USB/SD/hardware access.
"""
import argparse
import hashlib
import json
import struct
import sys
import tempfile
from pathlib import Path

from build_uac_u2_producer import CAVE, assemble, sha256

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")
ASM_A = ROOT / "patches/iso_burst_patch.S"
ASM_B = ROOT / "patches/iso_burst_uac84.S"

CODE = 0x00000000
STACK = 0x70000000
MANAGER = 0x10000000
MFI = 0x10100000
ENDPOINT = 0x20000000
RING = 0x30000000
DMA = 0x40000000
SENTINEL = 0x50000000

DOORBELL_TAIL = 0x31C74
REJECT_ORIGINAL = 0x30394
RET = b"\xc0\x03\x5f\xd6"

VENDOR = bytes([7, 5, 0x83, 0x01, 0x00, 0x01, 4, 0])   # 0x01000183, interval 4
UAC = bytes([7, 5, 0x84, 0x05, 0xC0, 0x00, 4, 0])      # 0x00C00584, interval 4
BURST_BYTES = 16 * 192
MFI_VALUE = 0x12340

REGIONS = (
    (CODE, 0x69000),
    (STACK, 0x10000),
    (MANAGER, 0x40000),
    (MFI, 0x1000),
    (ENDPOINT, 0x1000),
    (RING, 0x1000),
    (DMA, 0x1000),
    (SENTINEL, 0x1000),
)


def load_unicorn():
    try:
        import unicorn
        from unicorn import UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM, Uc
        from unicorn.arm64_const import (
            UC_ARM64_REG_SP, UC_ARM64_REG_X0, UC_ARM64_REG_X1,
            UC_ARM64_REG_X2, UC_ARM64_REG_X3,
        )
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "unicorn is required (python3 -m venv private/venv-unicorn && "
            "private/venv-unicorn/bin/pip install unicorn)"
        ) from exc
    return dict(unicorn=unicorn, Uc=Uc, UC_ARCH_ARM64=UC_ARCH_ARM64,
                UC_MODE_ARM=UC_MODE_ARM, UC_HOOK_CODE=UC_HOOK_CODE,
                SP=UC_ARM64_REG_SP, X0=UC_ARM64_REG_X0, X1=UC_ARM64_REG_X1,
                X2=UC_ARM64_REG_X2, X3=UC_ARM64_REG_X3)


def state(descriptor):
    """One synthetic endpoint object and the driver fields iso_enter reads."""
    ep = bytearray(0x1000)
    ep[0:8] = descriptor
    struct.pack_into("<Q", ep, 0x10, RING)          # TRB ring base
    struct.pack_into("<Q", ep, 0x18, RING)          # producer pointer (empty)
    struct.pack_into("<Q", ep, 0x20, RING)          # produced pointer (empty)
    struct.pack_into("<Q", ep, 0x28, RING + 0xF70)  # retained link slot
    ep[0x40] = 1                                     # cycle state
    return bytes(ep)


def run_case(uni, cave, descriptor):
    Uc = uni["Uc"]
    uc = Uc(uni["UC_ARCH_ARM64"], uni["UC_MODE_ARM"])
    for address, size in REGIONS:
        uc.mem_map(address, size)
    uc.mem_write(CAVE, cave)
    uc.mem_write(DOORBELL_TAIL, RET)
    uc.mem_write(REJECT_ORIGINAL, RET)
    uc.mem_write(SENTINEL, RET)

    uc.mem_write(ENDPOINT, state(descriptor))
    uc.mem_write(MANAGER + 0x22 * 0x1000 + 0xA58, struct.pack("<I", 3))  # HS
    uc.mem_write(MANAGER + 0x22 * 0x1000 + 8, struct.pack("<Q", MFI))
    uc.mem_write(MFI + 0x48, struct.pack("<I", MFI_VALUE))
    uc.mem_write(STACK + 0x8000 - 16, bytes(16))

    uc.reg_write(uni["X0"], MANAGER)
    uc.reg_write(uni["X1"], ENDPOINT)
    uc.reg_write(uni["X2"], DMA)
    uc.reg_write(uni["X3"], BURST_BYTES)
    uc.reg_write(uni["SP"], STACK + 0x8000)

    stopped = {"pc": None, "steps": 0}

    def on_code(uc_, address, size, user):
        stopped["steps"] += 1
        if address in (DOORBELL_TAIL, REJECT_ORIGINAL):
            stopped["pc"] = address
            uc_.emu_stop()

    hook = uc.hook_add(uni["UC_HOOK_CODE"], on_code)
    error = None
    try:
        uc.emu_start(CAVE, SENTINEL, count=100000)
    except Exception as exc:  # Unicorn raises UcError on invalid memory etc.
        error = str(exc)
    finally:
        uc.hook_del(hook)

    ring = bytes(uc.mem_read(RING, 0x1000))
    endpoint = bytes(uc.mem_read(ENDPOINT, 0x100))
    return {
        "descriptor": descriptor[2:6].hex(),
        "outcome": ("accept" if stopped["pc"] == DOORBELL_TAIL
                    else "reject" if stopped["pc"] == REJECT_ORIGINAL
                    else "error"),
        "pc": stopped["pc"],
        "steps": stopped["steps"],
        "error": error,
        "ring_sha256": sha256(ring),
        "ring": ring,
        "endpoint": endpoint,
        "producer": struct.unpack_from("<Q", endpoint, 0x18)[0],
        "cycle": endpoint[0x40],
        "mailbox": {
            "magic": struct.unpack_from("<I", ring, 0xF80)[0],
            "completed": struct.unpack_from("<I", ring, 0xF90)[0],
            "actual": struct.unpack_from("<I", ring, 0xF94)[0],
            "first_trb": struct.unpack_from("<Q", ring, 0xF98)[0],
            "retained": struct.unpack_from("<I", ring, 0xFBC)[0],
        },
    }


def expected_control(index, cycle=1):
    frame = ((MFI_VALUE >> 3) + 32 + index) & 0x7FF
    return ((frame << 20) | 0x1410 | cycle) & 0xFFFFFFFF


def check_ring(result):
    """Verify the 16 Isoch+16 ED TRB layout and the retained mailbox."""
    ring = result["ring"]
    problems = []
    for i in range(16):
        isoch = struct.unpack_from("<4I", ring, 32 * i)
        ed = struct.unpack_from("<4I", ring, 32 * i + 16)
        if isoch[0] != DMA + 192 * i:
            problems.append(f"isoch[{i}].addr={isoch[0]:#x}")
        if isoch[2] & 0x1FFFF != 192:
            problems.append(f"isoch[{i}].length={isoch[2]}")
        if isoch[3] != expected_control(i):
            problems.append(f"isoch[{i}].control={isoch[3]:#x}")
        if ed[0] != RING + 32 * i + 16:
            problems.append(f"ed[{i}].tag={ed[0]:#x}")
        if ed[3] != 0x1C20 | 1:
            problems.append(f"ed[{i}].control={ed[3]:#x}")
    if any(ring[0x200:0xF70]):
        problems.append("unexpected TRB data past the 16-packet burst")
    mailbox = result["mailbox"]
    if mailbox["magic"] != 0x324F5349:
        problems.append(f"mailbox.magic={mailbox['magic']:#x}")
    if mailbox["first_trb"] != RING:
        problems.append(f"mailbox.first_trb={mailbox['first_trb']:#x}")
    if mailbox["retained"] != expected_control(0):
        problems.append(f"mailbox.retained={mailbox['retained']:#x}")
    if result["producer"] != RING + 0x200:
        problems.append(f"producer={result['producer']:#x}")
    if result["cycle"] != 1:
        problems.append(f"cycle={result['cycle']}")
    return problems


def replay(toolchain=DEFAULT_TOOLCHAIN, asm_a=ASM_A, asm_b=ASM_B):
    uni = load_unicorn()
    with tempfile.TemporaryDirectory() as tmp:
        cave_a, _sym_a = assemble(toolchain, Path(tmp) / "a", asm_a)
        cave_b, _sym_b = assemble(toolchain, Path(tmp) / "b", asm_b)
    if len(cave_a) != len(cave_b):
        raise SystemExit("cave sizes differ")

    cases = {}
    for name, cave in (("vendor-a23", cave_a), ("u2", cave_b)):
        for label, descriptor in (("vendor", VENDOR), ("uac", UAC)):
            cases[f"{name}/{label}"] = run_case(uni, cave, descriptor)

    problems = []
    expected = {
        "vendor-a23/vendor": "accept",
        "vendor-a23/uac": "reject",
        "u2/uac": "accept",
        "u2/vendor": "reject",
    }
    for name, want in expected.items():
        case = cases[name]
        if case["outcome"] != want:
            problems.append(f"{name}: outcome {case['outcome']} != {want} (pc={case['pc']}, error={case['error']})")
        if case["error"]:
            problems.append(f"{name}: unicorn error {case['error']}")
    accepted = [cases["vendor-a23/vendor"], cases["u2/uac"]]
    if accepted[0]["ring_sha256"] != accepted[1]["ring_sha256"]:
        problems.append("accepted runs build different TRB rings")
    else:
        problems.extend(check_ring(accepted[1]))
    for name in ("vendor-a23/uac", "u2/vendor"):
        if any(cases[name]["ring"]):
            problems.append(f"{name}: rejected run wrote the ring")

    report = {
        "schema": "UAC-u2-cave-replay-1",
        "unicorn": uni["unicorn"].__version__,
        "caves": {
            "a23": {"asm": str(asm_a.relative_to(ROOT)), "sha256": sha256(cave_a),
                    "bytes": len(cave_a)},
            "u2": {"asm": str(asm_b.relative_to(ROOT)), "sha256": sha256(cave_b),
                   "bytes": len(cave_b)},
        },
        "ring_identical": accepted[0]["ring_sha256"] == accepted[1]["ring_sha256"],
        "ring_sha256": accepted[1]["ring_sha256"],
        "cases": {
            name: {k: case[k] for k in ("descriptor", "outcome", "pc", "steps",
                                        "error", "ring_sha256", "producer",
                                        "cycle", "mailbox")}
            for name, case in cases.items()
        },
        "problems": problems,
        "check_passed": not problems,
        "usb_operations": 0,
        "sd_accesses": 0,
        "hardware_verified": False,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asm-a", type=Path, default=ASM_A)
    parser.add_argument("--asm-b", type=Path, default=ASM_B)
    parser.add_argument("--toolchain", type=Path, default=DEFAULT_TOOLCHAIN)
    parser.add_argument("--out", type=Path, default=None, help="JSON report path")
    args = parser.parse_args()
    report = replay(args.toolchain, args.asm_a, args.asm_b)
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    print(text)
    if report["problems"]:
        raise SystemExit("replay problems: " + "; ".join(report["problems"]))


if __name__ == "__main__":
    main()
