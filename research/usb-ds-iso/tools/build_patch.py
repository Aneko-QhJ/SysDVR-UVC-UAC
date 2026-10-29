#!/usr/bin/env python3
"""Build fail-closed, Build-ID-specific A/B/C IPS32 experiment packages."""
import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from nso2elf import Nso

BUILD_ID = 'AD8D36F2029822A4C498F055ADBDAA789EB913C6000000000000000000000000'
SHA256 = '08e0c60a2879e59bb7ace77a17418f7fc0d18058e90a2f12516ff8b1ebe62dfb'
CAVE = 0x68d54
CAVE_END = 0x69000
ROOT = Path(__file__).resolve().parents[1]


def ips32(edits):
    out = bytearray(b'IPS32')
    end = 0
    for address, data in sorted(edits):
        if address < end or not 0 < len(data) < 65536:
            raise ValueError('overlapping or invalid IPS record')
        out += struct.pack('>IH', address + 0x100, len(data)) + data
        end = address + len(data)
    return bytes(out + b'EEOF')


def read_mapped(nso, address, size):
    for s in nso.sections:
        if s['vaddr'] <= address and address + size <= s['vaddr'] + s['size']:
            offset = address - s['vaddr']
            return s['content'][offset:offset + size]
    # Loader's zero-filled final text page. Never cross into rodata.
    text_end = nso.sections[0]['size']
    if text_end == CAVE and nso.sections[1]['vaddr'] == CAVE_END and CAVE <= address < address + size <= CAVE_END:
        return bytes(size)
    raise ValueError('address outside validated mapped segment')


def validate_module(raw):
    nso = Nso(raw)
    if nso.build_id.hex().upper() != BUILD_ID:
        raise ValueError('usb Build ID mismatch')
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError('original NSO hash mismatch; refusing a pre-patched/unknown input')
    if [s['vaddr'] for s in nso.sections] != [0, 0x69000, 0x8e000]:
        raise ValueError('segment layout mismatch')
    return nso


def branch(source, target, link=False):
    delta = target - source
    if delta % 4 or not -(1 << 27) <= delta < (1 << 27):
        raise ValueError('branch out of range/alignment')
    return struct.pack('<I', (0x94000000 if link else 0x14000000) | ((delta // 4) & 0x3ffffff))


def branch_eq(source, target):
    delta = target - source
    if delta % 4 or not -(1 << 20) <= delta < (1 << 20):
        raise ValueError('conditional branch out of range/alignment')
    return struct.pack('<I', 0x54000000 | (((delta // 4) & 0x7ffff) << 5))


def build(nso, variant, toolchain, out, frame_lead=0, retain_success=False, explicit_all=False, mps=192, burst=False, event_audit=False, publication_audit=False, doorbell_audit=False, context_audit=False, followup_sia=False, interval=4, assembly_override=None):
    if interval not in (1, 4) or (interval == 1 and not (context_audit and followup_sia)):
        raise ValueError('bInterval1 requires the A22 context/followup-SIA baseline')
    if followup_sia and not context_audit:
        raise ValueError('followup SIA requires the ISO6 context-audit baseline')
    if context_audit and (not event_audit or publication_audit or doorbell_audit):
        raise ValueError('context audit requires event audit without publication/doorbell audit')
    if event_audit and not burst:
        raise ValueError('event audit requires the HS burst producer')
    if publication_audit and not event_audit:
        raise ValueError('publication audit requires the bounded event audit')
    if doorbell_audit and not publication_audit:
        raise ValueError('doorbell audit requires the publication audit')
    if burst and (variant != 1 or mps != 256 or frame_lead != 32 or retain_success):
        raise ValueError('burst requires A, HS MPS256, lead32, normal completion')
    if mps not in (192, 256): raise ValueError('unsupported experimental MPS')
    out.mkdir(parents=True, exist_ok=True)
    linker = out / 'inject.ld'
    linker.write_text('SECTIONS { . = 0x68d54; .text : { *(.text.iso) } }\n'
        'doorbell_tail = 0x31c74; reject_original = 0x30394;\n'
        'event_original = 0x30f70; complete_original = 0x2a980; report_epilogue = 0x2cbe4; copy_original = 0x60e50;\n')
    obj, elf, binary = [out / name for name in ('inject.o', 'inject.elf', 'inject.bin')]
    def run(tool, *args):
        subprocess.run([str(toolchain / ('aarch64-none-elf-' + tool)), *map(str, args)], check=True)
    assembly = assembly_override or ROOT / 'patches' / ('iso_burst_context.S' if context_audit else 'iso_burst_doorbell.S' if doorbell_audit else 'iso_burst_phase.S' if publication_audit else 'iso_burst_audit.S' if event_audit else 'iso_burst_patch.S' if burst else 'iso_patch.S')
    run('gcc', '-c', '-DVARIANT=' + str(variant), '-DFRAME_LEAD='+str(frame_lead),
        '-DRETAIN_SUCCESS='+str(int(retain_success)), '-DEXPLICIT_ALL='+str(int(explicit_all)),
        '-DISO_MPS='+str(mps), '-DFOLLOWUP_SIA='+str(int(followup_sia)), '-DISO_INTERVAL='+str(interval), assembly, '-o', obj)
    run('ld', '-T', linker, obj, '-o', elf)
    run('objcopy', '-O', 'binary', '--only-section=.text', elf, binary)
    syms = subprocess.check_output([str(toolchain / 'aarch64-none-elf-nm'), str(elf)], text=True)
    symbols = {line.split()[2]: int(line.split()[0], 16) for line in syms.splitlines() if len(line.split()) == 3}
    code = binary.read_bytes()
    if not code or CAVE + len(code) > CAVE_END:
        raise ValueError('injection exceeds RX page padding')
    edits, manifest = [], []
    def edit(address, old, new, reason):
        expected = bytes.fromhex(old) if isinstance(old, str) else old
        if read_mapped(nso, address, len(expected)) != expected or len(expected) != len(new):
            raise ValueError(f'original bytes/length mismatch at {address:#x}')
        edits.append((address, new))
        manifest.append({'address': hex(address), 'before': expected.hex(), 'after': new.hex(), 'reason': reason})
    edit(CAVE, bytes(len(code)), code, 'bounded device-only Isoch producer/event/report hooks')
    edit(0x30364, '80010054', branch_eq(0x30364, symbols['iso_enter']), 'ISO enters producer; preserve non-ISO branch condition')
    edit(0x30898, 'b6010094', branch(0x30898, symbols['iso_event'], True), 'observe/filter experimental transfer events')
    edit(0x2cbe0, '60420091', branch(0x2cbe0, symbols['iso_report']), 'diagnostics in empty report payload only')
    # Restore the established descriptor-length fix with a u16 in adjacent padding.
    instructions = {}
    for address in (0x2bf1c, 0x2bf94, 0x2c028, 0x2c0a0, 0x2c11c):
        instructions[address] = 'strh w21, [x22, #0x454]'
    for address in (0x2bf8c, 0x2c020, 0x2c098, 0x2c114):
        instructions[address] = 'ldrh w8, [x22, #0x454]'
    for address in (0x2bfb8, 0x2c0b0, 0x2c138, 0x2c148):
        instructions[address] = 'ldrh w21, [x22, #0x454]'
    for address in (0x2bfec, 0x2c064, 0x2c0e0):
        instructions[address] = 'add x0, x23, w21, uxtw'
    instructions[0x2c158] = 'mov w8, w21'
    instructions[0x2bdb8] = 'ldrh w8, [x19, x8]'
    assembly = out / 'descriptor.S'
    assembly.write_text('.text\n' + '\n'.join(instructions.values()) + '\n')
    run('gcc', '-c', assembly, '-o', out / 'descriptor.o')
    run('objcopy', '-O', 'binary', '--only-section=.text', out / 'descriptor.o', out / 'descriptor.bin')
    encoded = (out / 'descriptor.bin').read_bytes()
    expected_words = {
        **{a: 0x391152d5 for a in (0x2bf1c, 0x2bf94, 0x2c028, 0x2c0a0, 0x2c11c)},
        **{a: 0x395152c8 for a in (0x2bf8c, 0x2c020, 0x2c098, 0x2c114)},
        **{a: 0x395152d5 for a in (0x2bfb8, 0x2c0b0, 0x2c138, 0x2c148)},
        **{a: 0x8b3502e0 for a in (0x2bfec, 0x2c064, 0x2c0e0)},
        0x2c158: 0x12001ea8, 0x2bdb8: 0x38686a68,
    }
    for i, address in enumerate(instructions):
        edit(address, struct.pack('<I', expected_words[address]), encoded[i*4:i*4+4], 'restore u16 configuration length/offset')
    patch = ips32(edits)
    patchdir = out / 'atmosphere/exefs_patches/SysDVR-ISO'
    patchdir.mkdir(parents=True, exist_ok=True)
    path = patchdir / (BUILD_ID + '.ips')
    path.write_bytes(patch)
    (out / 'manifest.json').write_text(json.dumps({'build_id': BUILD_ID, 'original_sha256': SHA256,
        'variant': 'ABC'[variant-1], 'frame_lead': frame_lead if variant == 2 or explicit_all else 0,
        'burst_packets': 16 if burst else 1, 'first_trb_snapshot': bool(burst), 'first_trb_control_only': bool(burst),
        'error_event_and_mfi_snapshot': bool(burst), 'bounded_event_audit': bool(event_audit),
        'publication_mfi_snapshot': bool(publication_audit),
        'doorbell_tail_mfi_snapshot': bool(doorbell_audit),
        'prepublication_context_snapshot': bool(context_audit),
        'followup_sia': bool(followup_sia),
        'interval': interval, 'service_interval_microframes': 1 << (interval-1),
        'diagnostics_magic': 'ISO7' if interval == 1 else 'ISO6' if context_audit else 'ISO5' if doorbell_audit else 'ISO4' if publication_audit else 'ISO3' if event_audit else 'ISO2' if burst else 'ISO1',
        'injection_bytes': len(code), 'injection_limit': CAVE_END-CAVE,
        'retain_success': bool(retain_success and (variant == 2 or explicit_all)), 'mps': mps,
        'patch_sha256': hashlib.sha256(patch).hexdigest(),
        'symbols': symbols, 'edits': manifest}, indent=2) + '\n')
    print(f"Variant {'ABC'[variant-1]}: {len(code)} bytes of {CAVE_END-CAVE} RX padding; {path}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--nso', type=Path, default=ROOT / 'private/module/exefs/main')
    p.add_argument('--toolchain', type=Path, default=Path('/opt/devkitpro/devkitA64/bin'))
    p.add_argument('--out', type=Path, default=ROOT / 'private/packages')
    p.add_argument('--frame-lead', type=int, choices=(0,4,8,16,32), default=0,
                   help='B only: explicit 1 ms Frame ID lead; 0 keeps SIA/frame probe')
    p.add_argument('--retain-success', action='store_true',
                   help='B only: record hardware success without completing/releasing URB')
    p.add_argument('--explicit-all', action='store_true',
                   help='extend explicit Frame ID and retained success to A/C for ED comparisons')
    p.add_argument('--mps', type=int, choices=(192,256), default=192)
    p.add_argument('--burst', action='store_true', help='A13 HS-only 16 independent TDs in one URB; builds A only')
    p.add_argument('--event-audit', action='store_true', help='ISO3 bounded first-TD/filtered/post-terminal event audit; requires --burst')
    p.add_argument('--publication-audit', action='store_true', help='ISO4 first-two-ED and publication MFI anchors; requires --event-audit')
    p.add_argument('--doorbell-audit', action='store_true', help='ISO5 original doorbell-tail MFI bracket; requires --publication-audit')
    p.add_argument('--context-audit', action='store_true', help='ISO6 pre-publication EP7 context snapshot; requires event audit only')
    p.add_argument('--followup-sia', action='store_true', help='A22: TD0 explicit lead32, TD1..15 SIA1/FrameID0; requires --context-audit')
    p.add_argument('--interval', type=int, choices=(1,4), default=4, help='A23: HS bInterval1 requires context audit and followup SIA; default4 preserves A22')
    args = p.parse_args()
    if args.interval == 1 and not (args.context_audit and args.followup_sia):
        p.error('--interval 1 requires --context-audit and --followup-sia')
    if args.followup_sia and not args.context_audit:
        p.error('--followup-sia requires --context-audit')
    if args.context_audit and (not args.event_audit or args.publication_audit or args.doorbell_audit):
        p.error('--context-audit requires --event-audit without publication/doorbell audit')
    if args.event_audit and not args.burst:
        p.error('--event-audit requires --burst')
    if args.publication_audit and not args.event_audit:
        p.error('--publication-audit requires --event-audit')
    if args.doorbell_audit and not args.publication_audit:
        p.error('--doorbell-audit requires --publication-audit')
    if args.burst and (args.frame_lead != 32 or args.mps != 256 or args.retain_success or not args.explicit_all):
        p.error('--burst requires --frame-lead 32 --explicit-all --mps 256 without --retain-success')
    if args.explicit_all and not args.frame_lead:
        p.error('--explicit-all requires a nonzero --frame-lead')
    nso = validate_module(args.nso.read_bytes())
    for variant in ((1,) if args.burst else (1, 2, 3)):
        build(nso, variant, args.toolchain, args.out / 'ABC'[variant-1], args.frame_lead, args.retain_success, args.explicit_all, args.mps, args.burst, args.event_audit, args.publication_audit, args.doorbell_audit, args.context_audit, args.followup_sia, args.interval)


if __name__ == '__main__':
    main()
