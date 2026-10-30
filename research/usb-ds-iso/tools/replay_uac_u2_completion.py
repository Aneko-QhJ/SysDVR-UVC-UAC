#!/usr/bin/env python3
"""Replay the usb:ds request-completion path (0x2c690) under Unicorn.

The U2 cave finishes a 3072-byte ISO burst by calling complete_original
(0x2a980), which resolves the endpoint entry and calls 0x2c690 with
(force, transferred, lock).  This tool executes the real 0x2c690 with a
synthetic endpoint/request entry and stubs the driver calls it makes, so the
entry transition, the unmap call and the queue advance can be checked without
hardware.

Cases mirror UAC_U2_QUEUE_COMPAT_DESIGN.md section 7.2:

  full_force       requested=3072, transferred=3072, force=1
  full_no_force    requested=3072, transferred=3072, force=0
  partial_force    requested=3072, transferred=192,  force=1
  partial_retry    requested=3072, transferred=192,  force=0
  empty_queue      count=0 (must not unmap or crash)

Expected results:

  full_force       entry+44=3072, status=3, unmap=1, submit=0, count=0
  full_no_force    same
  partial_force    entry+44=192,  status=3, unmap=1, submit=0, count=0
  partial_retry    entry+44=192,  status=2, unmap=0, submit=1, count=1
  empty_queue      entry+44=0,    status=2, unmap=0, submit=0, count=0

With --report, run the real report builder (0x2c930) over one completed entry.
This is the driver path that the iso_report hook currently overwrites; expected
count=1, id=388, requested=3072, transferred=3072, status=3, and the entry
status is zeroed after the copy.

Requires unicorn (not a repo dependency):
  python3 -m venv private/venv-unicorn
  private/venv-unicorn/bin/pip install unicorn
  private/venv-unicorn/bin/python tools/replay_uac_u2_completion.py

No USB/SD/hardware access.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

from build_uac_descriptor_payload import load_elf_sections

ROOT = Path(__file__).resolve().parents[1]
ELF = ROOT / "private/module/usb.elf"

CODE = 0x00000000
CODE_SIZE = 0x100000
STACK = 0x10000000
ENDPOINT = 0x20000000
CONTROLLER = 0x30000000
VTABLE = CONTROLLER + 0x1000
SUBMIT_STUB = CONTROLLER + 0x2000
SENTINEL = 0x40000000
MANAGER = 0x50000000
BUFFER = 0x60000000
IOVA = 0x70000000
REPORT = 0x80000000

ENTRY_OFFSET = 0x78
ENTRY_STRIDE = 0x30
REQUESTED = 3072
URB_ID = 388
ENDPOINT_ADDR = 0x84
ENDPOINT_LIMIT = 0x1000

# Driver functions called by 0x2c690; every one is replaced by a stub.
LOCK = 0xBA60
UNLOCK = 0xBAB0
UNLOCK2 = 0xB470
REPORT_UNLOCK = 0xB4A0
DOMAIN = 0x30C0
UNMAP = 0x4C70
ZLP_CHECK = 0x2A8B0
CACHE_SYNC = 0x8EB0
ASSERT = 0x9540
COMPLETE = 0x2C690
REPORT_BUILDER = 0x2C930

REGIONS = (
    (CODE, CODE_SIZE),
    (STACK, 0x10000),
    (ENDPOINT, 0x1000),
    (CONTROLLER, 0x3000),
    (SENTINEL, 0x1000),
    (MANAGER, 0x1000),
    (BUFFER, 0x1000),
    (IOVA, 0x1000),
    (REPORT, 0x1000),
)

RET = 0xD65F03C0
MOV_W0_0 = 0x52800000
MOV_W0_1234 = 0x52800000 | (0x1234 << 5)
MOV_W0_55 = 0x52800000 | (0x55 << 5)

CASES = {
    "full_force": dict(requested=REQUESTED, transferred=0, force=1,
                        size=REQUESTED, count=1),
    "full_no_force": dict(requested=REQUESTED, transferred=0, force=0,
                          size=REQUESTED, count=1),
    "partial_force": dict(requested=REQUESTED, transferred=0, force=1,
                          size=192, count=1),
    "partial_retry": dict(requested=REQUESTED, transferred=0, force=0,
                          size=192, count=1),
    "empty_queue": dict(requested=REQUESTED, transferred=0, force=1,
                        size=REQUESTED, count=0),
}

EXPECTED = {
    "full_force": dict(transferred=3072, status=3, unmaps=1, submits=0, count=0),
    "full_no_force": dict(transferred=3072, status=3, unmaps=1, submits=0, count=0),
    "partial_force": dict(transferred=192, status=3, unmaps=1, submits=0, count=0),
    "partial_retry": dict(transferred=192, status=2, unmaps=0, submits=1, count=1),
    "empty_queue": dict(transferred=0, status=2, unmaps=0, submits=0, count=0),
}


def load_unicorn():
    try:
        from unicorn import (
            UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM, Uc,
        )
        from unicorn.arm64_const import (
            UC_ARM64_REG_CPACR_EL1, UC_ARM64_REG_LR, UC_ARM64_REG_PC,
            UC_ARM64_REG_SP, UC_ARM64_REG_X0, UC_ARM64_REG_X1,
            UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4,
        )
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "unicorn is required (python3 -m venv private/venv-unicorn && "
            "private/venv-unicorn/bin/pip install unicorn)"
        ) from exc
    return dict(
        Uc=Uc, UC_ARCH_ARM64=UC_ARCH_ARM64, UC_MODE_ARM=UC_MODE_ARM,
        UC_HOOK_CODE=UC_HOOK_CODE, CPACR=UC_ARM64_REG_CPACR_EL1,
        LR=UC_ARM64_REG_LR, PC=UC_ARM64_REG_PC, SP=UC_ARM64_REG_SP,
        X0=UC_ARM64_REG_X0, X1=UC_ARM64_REG_X1, X2=UC_ARM64_REG_X2,
        X3=UC_ARM64_REG_X3, X4=UC_ARM64_REG_X4,
    )


def word(data, sections, address):
    for sec in sections.values():
        if sec["type"] != 8 and sec["addr"] <= address < sec["addr"] + sec["size"]:
            off = sec["offset"] + address - sec["addr"]
            return int.from_bytes(data[off:off + 4], "little")
    raise ValueError(f"{address:#x} outside mapped sections")


def put32(uc, address, value):
    uc.mem_write(address, struct.pack("<I", value))


def put64(uc, address, value):
    uc.mem_write(address, struct.pack("<Q", value))


def load_code(uc, data, sections):
    for sec in sections.values():
        if sec["type"] == 8 or not sec["size"]:
            continue
        uc.mem_write(sec["addr"], data[sec["offset"]:sec["offset"] + sec["size"]])


def install_stubs(uc):
    """Replace external calls with ret / constant-return stubs."""
    for address in (LOCK, UNLOCK, UNLOCK2, REPORT_UNLOCK, UNMAP, CACHE_SYNC,
                    ASSERT, SUBMIT_STUB):
        put32(uc, address, RET)
    # Constant-return stubs need two instructions: mov w0, #imm; ret.
    uc.mem_write(ZLP_CHECK, struct.pack("<II", MOV_W0_0, RET))
    uc.mem_write(DOMAIN, struct.pack("<II", MOV_W0_1234, RET))

    # The controller object points at a vtable whose +136 entry is the submit
    # stub; 0x2c690 loads [endpoint+96] -> [controller] -> [vtable+136].
    put64(uc, CONTROLLER, VTABLE)
    put64(uc, VTABLE + 136, SUBMIT_STUB)


def setup_endpoint(uc, case):
    """Create one endpoint object with one request entry at index 0."""
    entry = ENDPOINT + ENTRY_OFFSET
    uc.mem_write(ENDPOINT, bytes(0x1000))
    put64(uc, ENDPOINT + 0x60, CONTROLLER)     # [endpoint+96]
    put64(uc, ENDPOINT + 0x68, MANAGER)        # [endpoint+104], ZLP helper arg
    uc.mem_write(ENDPOINT + 0x70, bytes([ENDPOINT_ADDR]))  # [endpoint+112]
    put32(uc, ENDPOINT + 0x74, ENDPOINT_LIMIT)  # [endpoint+116]
    put32(uc, ENDPOINT + 0x04, 0)              # queue index
    put32(uc, ENDPOINT + 0x08, case["count"])  # queue count

    # entry+32 requested, +36 remaining, +40 status, +44 transferred.
    put32(uc, entry + 0x00, URB_ID)
    put64(uc, entry + 0x08, BUFFER)
    put64(uc, entry + 0x10, IOVA)
    put64(uc, entry + 0x18, BUFFER)
    put32(uc, entry + 0x20, case["requested"])
    put32(uc, entry + 0x24, case["requested"])
    put32(uc, entry + 0x28, 2)
    put32(uc, entry + 0x2C, case["transferred"])


def run_case(uni, data, sections, name, case):
    Uc = uni["Uc"]
    uc = Uc(uni["UC_ARCH_ARM64"], uni["UC_MODE_ARM"])
    for address, size in REGIONS:
        uc.mem_map(address, size)
    load_code(uc, data, sections)
    install_stubs(uc)
    setup_endpoint(uc, case)
    put32(uc, SENTINEL, RET)

    unmaps = []
    submits = []
    locks = []
    assert_hits = []

    def hook(uc_, address, size, _user):
        if address == UNMAP:
            unmaps.append((uc_.reg_read(uni["X0"]), uc_.reg_read(uni["X1"])))
        elif address == SUBMIT_STUB:
            submits.append((
                uc_.reg_read(uni["X0"]), uc_.reg_read(uni["X1"]),
                uc_.reg_read(uni["X2"]), uc_.reg_read(uni["X3"]),
            ))
        elif address in (LOCK, UNLOCK, UNLOCK2):
            locks.append(address)
        elif address == ASSERT:
            assert_hits.append(uc_.reg_read(uni["LR"]))
            uc_.emu_stop()

    hook_handle = uc.hook_add(uni["UC_HOOK_CODE"], hook)
    uc.reg_write(uni["CPACR"], 3 << 20)
    uc.reg_write(uni["SP"], STACK + 0xF000)
    uc.reg_write(uni["LR"], SENTINEL)
    uc.reg_write(uni["X0"], ENDPOINT)
    uc.reg_write(uni["X1"], 0)
    uc.reg_write(uni["X2"], case["force"])
    uc.reg_write(uni["X3"], case["size"])
    uc.reg_write(uni["X4"], 1)
    uc.reg_write(uni["PC"], COMPLETE)
    uc.emu_start(COMPLETE, SENTINEL, count=20000)
    uc.hook_del(hook_handle)

    pc = uc.reg_read(uni["PC"])
    entry = ENDPOINT + ENTRY_OFFSET

    def rd32(address):
        return struct.unpack("<I", uc.mem_read(address, 4))[0]

    result = {
        "case": name,
        "completed": pc == SENTINEL and not assert_hits,
        "pc": f"0x{pc:x}",
        "assert": bool(assert_hits),
        "transferred": rd32(entry + 0x2C),
        "status": rd32(entry + 0x28),
        "requested": rd32(entry + 0x20),
        "remaining": rd32(entry + 0x24),
        "next_buffer": struct.unpack("<Q", uc.mem_read(entry + 0x18, 8))[0],
        "index": rd32(ENDPOINT + 0x04),
        "count": rd32(ENDPOINT + 0x08),
        "unmaps": [{"domain": f"0x{d:x}", "iova": f"0x{i:x}"} for d, i in unmaps],
        "submits": [
            {"x0": f"0x{x0:x}", "w1": f"0x{w1:x}", "x2": f"0x{x2:x}",
             "w3": f"0x{w3:x}"}
            for x0, w1, x2, w3 in submits
        ],
        "lock_calls": len(locks),
    }
    return result


def setup_report_entry(uc):
    """One completed entry, as left by a full 3072-byte completion."""
    setup_endpoint(uc, CASES["full_force"])
    entry = ENDPOINT + ENTRY_OFFSET
    put32(uc, ENDPOINT + 0x00, 0)       # report ring index
    put32(uc, entry + 0x20, REQUESTED)  # requested
    put32(uc, entry + 0x28, 3)          # status=done
    put32(uc, entry + 0x2C, REQUESTED)  # transferred


def run_report_case(uni, data, sections):
    """Run the real report builder (0x2c930) over one completed entry."""
    Uc = uni["Uc"]
    uc = Uc(uni["UC_ARCH_ARM64"], uni["UC_MODE_ARM"])
    for address, size in REGIONS:
        uc.mem_map(address, size)
    load_code(uc, data, sections)
    install_stubs(uc)
    setup_report_entry(uc)
    put32(uc, SENTINEL, RET)
    uc.mem_write(REPORT, bytes(0x1000))

    assert_hits = []

    def hook(uc_, address, size, _user):
        if address == ASSERT:
            assert_hits.append(uc_.reg_read(uni["LR"]))
            uc_.emu_stop()

    hook_handle = uc.hook_add(uni["UC_HOOK_CODE"], hook)
    uc.reg_write(uni["CPACR"], 3 << 20)
    uc.reg_write(uni["SP"], STACK + 0xF000)
    uc.reg_write(uni["LR"], SENTINEL)
    uc.reg_write(uni["X0"], ENDPOINT)
    uc.reg_write(uni["X1"], REPORT)
    uc.reg_write(uni["PC"], REPORT_BUILDER)
    uc.emu_start(REPORT_BUILDER, SENTINEL, count=20000)
    uc.hook_del(hook_handle)

    def rd32(address):
        return struct.unpack("<I", uc.mem_read(address, 4))[0]

    return {
        "case": "report",
        "completed": uc.reg_read(uni["PC"]) == SENTINEL and not assert_hits,
        "assert": bool(assert_hits),
        "count": rd32(REPORT + 128),
        "id": rd32(REPORT + 0),
        "requested": rd32(REPORT + 4),
        "transferred": rd32(REPORT + 8),
        "status": rd32(REPORT + 12),
        "entry_status_after": rd32(ENDPOINT + ENTRY_OFFSET + 0x28),
    }


def check_report(result):
    errors = []
    if not result["completed"]:
        errors.append("report builder did not complete")
    if result["assert"]:
        errors.append("hit 0x9540 assert")
    for key, expected in (("count", 1), ("id", URB_ID),
                          ("requested", REQUESTED), ("transferred", REQUESTED),
                          ("status", 3), ("entry_status_after", 0)):
        if result[key] != expected:
            errors.append(f"{key}={result[key]} expected {expected}")
    return errors


def check(result):
    expected = EXPECTED[result["case"]]
    errors = []
    if not result["completed"]:
        errors.append(f"did not complete (pc={result['pc']}, assert={result['assert']})")
    if result["assert"]:
        errors.append("hit 0x9540 assert")
    for key in ("transferred", "status"):
        if result[key] != expected[key]:
            errors.append(f"{key}={result[key]} expected {expected[key]}")
    if len(result["unmaps"]) != expected["unmaps"]:
        errors.append(f"unmaps={len(result['unmaps'])} expected {expected['unmaps']}")
    if len(result["submits"]) != expected["submits"]:
        errors.append(f"submits={len(result['submits'])} expected {expected['submits']}")
    if result["count"] != expected["count"]:
        errors.append(f"count={result['count']} expected {expected['count']}")
    if expected["unmaps"]:
        iova = result["unmaps"][0]["iova"] if result["unmaps"] else None
        if iova != f"0x{IOVA:x}":
            errors.append(f"unmap iova={iova} expected 0x{IOVA:x}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", action="append", choices=sorted(CASES),
                        help="run only the named case (repeatable)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    parser.add_argument("--report", action="store_true",
                        help="run the report builder (0x2c930) instead of completion cases")
    args = parser.parse_args()

    if not ELF.is_file():
        raise SystemExit(f"missing {ELF}")
    data, sections = load_elf_sections(ELF)
    uni = load_unicorn()

    if args.report:
        result = run_report_case(uni, data, sections)
        errors = check_report(result)
        result["errors"] = errors
        failures = [f"report: {e}" for e in errors]
        if args.json:
            print(json.dumps({"report": result, "failures": failures}, indent=2))
        else:
            print(f"report: completed={result['completed']} count={result['count']} "
                  f"id={result['id']} requested={result['requested']} "
                  f"transferred={result['transferred']} status={result['status']} "
                  f"entry_status_after={result['entry_status_after']} "
                  f"{'; '.join(errors) or 'ok'}")
    else:
        names = args.case or sorted(CASES)
        results = [run_case(uni, data, sections, name, CASES[name]) for name in names]
        failures = []
        for result in results:
            errors = check(result)
            result["errors"] = errors
            failures.extend(f"{result['case']}: {e}" for e in errors)

        if args.json:
            print(json.dumps({"results": results, "failures": failures}, indent=2))
        else:
            print(f"{'case':16} {'xfer':>5} {'st':>3} {'unmap':>5} {'submit':>6} "
                  f"{'count':>5}  errors")
            for result in results:
                print(f"{result['case']:16} {result['transferred']:5} {result['status']:3} "
                      f"{len(result['unmaps']):5} {len(result['submits']):6} "
                      f"{result['count']:5}  {'; '.join(result['errors']) or 'ok'}")
    if failures:
        print("\nFAIL", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
