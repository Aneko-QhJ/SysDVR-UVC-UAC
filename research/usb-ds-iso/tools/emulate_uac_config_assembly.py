#!/usr/bin/env python3
"""Emulate the usb:ds configuration assembler with UAC descriptor sizes.

Calls FUN_0002bee0 from the extracted usb ELF under Unicorn with four
interface blocks (VC 57, VS 94/100, AC 47, AS 50/56) and reports the
configuration length field it produces, with and without the descriptor-only
runtime patch.  No USB, SD or hardware access; requires unicorn.
"""
import argparse
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ELF = ROOT / "private/module/usb.elf"

ASSEMBLER = 0x2BEE0
CONFIG_GETTER = 0x2BD80
SENTINEL = 0xDEAD0000
CTX = 0x30000000
STACK = 0x30200000
CODE_SIZE = 0x69000
RODATA = (0x69000, 0x24594)
DATA = (0x8E000, 0x440A8)
SIZE_TABLE = 0x74298
BLOB_TABLE = 0x742D8
HEADER_OFF = 0x1054
LENGTH_OFF = 0x1454
TOTAL_OFF = 0x1056
COUNT_OFF = 0x1058

BLOCKS_HS = [57, 94, 47, 50]   # VC, VS, AC, AS
BLOCKS_SS = [57, 100, 47, 56]  # VC, VS(+companion), AC, AS
EXPECTED = {
    "hs": {"bytes": 257, "unpatched_u8": 1, "patched": 257},
    "ss": {"bytes": 269, "unpatched_u8": 13, "patched": 269},
}


def load_elf(path):
    data = Path(path).read_bytes()
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF file")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    shentsize = struct.unpack_from("<H", data, 58)[0]
    shnum = struct.unpack_from("<H", data, 60)[0]
    sections = []
    for i in range(shnum):
        off = shoff + i * shentsize
        _name, sh_type, _flags, addr, offset, size = struct.unpack_from(
            "<IIQQQQ", data, off
        )
        sections.append(
            {"type": sh_type, "addr": addr, "offset": offset, "size": size}
        )
    return data, sections


def read_vaddr(data, sections, addr, size):
    for sec in sections:
        if sec["type"] == 8:
            continue
        if sec["addr"] <= addr and addr + size <= sec["addr"] + sec["size"]:
            off = sec["offset"] + addr - sec["addr"]
            return data[off:off + size]
    raise ValueError(f"address {addr:#x} outside mapped sections")


def build_ctx(sizes, size_off, blob_off):
    ctx = bytearray(0x2000)
    ctx[0x5E:0x66] = bytes([9, 2, 0, 0, 4, 1, 0, 0x80])
    ctx[0x66] = 0xFA
    ctx[0x67:0x6B] = b"\x01\x01\x01\x01"
    struct.pack_into("<I", ctx, 8, 4)
    for i, size in enumerate(sizes):
        struct.pack_into("<I", ctx, size_off + 4 * i, size)
        start = blob_off + 0x80 * i
        ctx[start:start + size] = bytes([0x40 + i]) * size
    return ctx


def emulate(data, sections, edits, speed, sizes, patched):
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_PROT_ALL, UC_HOOK_CODE
    from unicorn.arm64_const import (
        UC_ARM64_REG_LR,
        UC_ARM64_REG_PC,
        UC_ARM64_REG_SP,
        UC_ARM64_REG_X0,
        UC_ARM64_REG_X1,
        UC_ARM64_REG_X2,
        UC_ARM64_REG_X3,
    )

    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.mem_map(0, CODE_SIZE, UC_PROT_ALL)
    code = max(
        (s for s in sections if s["addr"] == 0 and s["type"] == 1),
        key=lambda s: s["size"],
    )
    mu.mem_write(0, read_vaddr(data, sections, 0, code["size"]))
    for base, size in (RODATA, DATA):
        mu.mem_map(base, (size + 0xFFF) & ~0xFFF, UC_PROT_ALL)
        mu.mem_write(base, read_vaddr(data, sections, base, size))
    mu.mem_map(CTX, 0x4000, UC_PROT_ALL)
    mu.mem_map(STACK, 0x4000, UC_PROT_ALL)

    if patched:
        for address, _before, after in edits:
            mu.mem_write(address, struct.pack("<I", after))

    size_off = struct.unpack("<Q", read_vaddr(data, sections, SIZE_TABLE + (speed - 1) * 8, 8))[0]
    blob_off = struct.unpack("<Q", read_vaddr(data, sections, BLOB_TABLE + (speed - 1) * 8, 8))[0]
    mu.mem_write(CTX, bytes(build_ctx(sizes, size_off, blob_off)))

    def skip(uc, address, size_, _user):
        if address in (0xBA60, 0xBAB0, 0xD5E0):
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    mu.hook_add(UC_HOOK_CODE, skip)
    mu.reg_write(UC_ARM64_REG_SP, STACK + 0x3000)
    mu.reg_write(UC_ARM64_REG_X0, CTX)
    mu.reg_write(UC_ARM64_REG_X1, speed)
    mu.reg_write(UC_ARM64_REG_LR, SENTINEL)
    mu.emu_start(ASSEMBLER, SENTINEL, count=200000)

    total = struct.unpack_from("<H", mu.mem_read(CTX + TOTAL_OFF, 2))[0]
    count = mu.mem_read(CTX + COUNT_OFF, 1)[0]
    stored = struct.unpack_from("<H", mu.mem_read(CTX + LENGTH_OFF, 2))[0]
    header = bytes(mu.mem_read(CTX + HEADER_OFF, 9))

    def getter(request):
        dst = CTX + 0x1800
        mu.reg_write(UC_ARM64_REG_X0, CTX)
        mu.reg_write(UC_ARM64_REG_X1, dst)
        mu.reg_write(UC_ARM64_REG_X2, 0)
        mu.reg_write(UC_ARM64_REG_X3, request)
        mu.reg_write(UC_ARM64_REG_LR, SENTINEL)
        mu.emu_start(CONFIG_GETTER, SENTINEL, count=20000)
        return mu.reg_read(UC_ARM64_REG_X0)

    return {
        "speed": speed,
        "patched": patched,
        "wTotalLength": total,
        "bNumInterfaces": count,
        "stored_length": stored,
        "bLength": header[0],
        "bDescriptorType": header[1],
        "getter_9": getter(9),
        "getter_257": getter(257),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    data, sections = load_elf(args.elf)
    from build_uac_descriptor_payload import EDITS

    rows = []
    for name, speed, sizes in (("hs", 2, BLOCKS_HS), ("ss", 3, BLOCKS_SS)):
        for patched in (False, True):
            row = emulate(data, sections, EDITS, speed, sizes, patched)
            rows.append({"config": name, **row})
    failures = []
    for row in rows:
        expected = EXPECTED[row["config"]]
        want = expected["patched"] if row["patched"] else expected["unpatched_u8"]
        if row["wTotalLength"] != want:
            failures.append(f"{row['config']} patched={row['patched']}: {row['wTotalLength']} != {want}")
        if row["bNumInterfaces"] != 4:
            failures.append(f"{row['config']}: bNumInterfaces {row['bNumInterfaces']} != 4")
        want9 = min(9, want)
        want257 = min(257, want)
        if row["getter_9"] != want9:
            failures.append(f"{row['config']} patched={row['patched']}: getter(9) {row['getter_9']} != {want9}")
        if row["getter_257"] != want257:
            failures.append(f"{row['config']} patched={row['patched']}: getter(257) {row['getter_257']} != {want257}")
    result = {
        "schema": "UAC-config-emulation-1",
        "elf_sha256": __import__("hashlib").sha256(data).hexdigest(),
        "blocks_hs": BLOCKS_HS,
        "blocks_ss": BLOCKS_SS,
        "rows": rows,
        "failures": failures,
    }
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
