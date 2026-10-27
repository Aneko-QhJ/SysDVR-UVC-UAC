#!/usr/bin/env python3
"""Resolve selected virtual calls in a local kernelcache, without live I/O.

Supports root-cache pointer format 8 only; rejects unsupported cache levels,
formats and file ranges instead of silently masking an arbitrary pointer.
"""
import argparse
import json
from pathlib import Path

from audit_host_driver import DEFAULT_INPUT, Fileset, digest


class KernelCache:
    def __init__(self, fileset):
        self.fs = fileset
        self.segments = []
        fixups = None
        for cmd, offset, size in fileset.commands(0):
            if cmd == 0x19:
                name, vmaddr, vmsize, fileoff, filesize, *_ = fileset.unpack('<16sQQQQiiII', offset + 8)
                self.segments.append(dict(name=name.rstrip(b'\0').decode(), vmaddr=vmaddr,
                                          vmsize=vmsize, fileoff=fileoff, filesize=filesize))
            elif cmd == 0x80000034:
                fixups = fileset.unpack('<II', offset + 8)
        headers = [s for s in self.segments if s['fileoff'] == 0 and s['filesize'] >= 32]
        if len(headers) != 1 or fixups is None:
            raise ValueError('Cannot identify root image base or chained fixups')
        self.base = headers[0]['vmaddr']
        offset, size = fixups
        fileset.read(offset, size)
        version, starts_offset, *_ = fileset.unpack('<7I', offset)
        if version != 0 or not 28 <= starts_offset <= size - 4:
            raise ValueError('Unsupported chained fixup header')
        starts = offset + starts_offset
        count, = fileset.unpack('<I', starts)
        end = offset + size
        if count != len(self.segments) or count > (end - starts - 4) // 4:
            raise ValueError('Invalid chained segment count')
        self.formats = {}
        for i in range(count):
            relative, = fileset.unpack('<I', starts + 4 + i * 4)
            if relative == 0:
                continue
            pos = starts + relative
            if pos < starts + 4 + count * 4 or pos > end - 22:
                raise ValueError('Invalid chained segment offset')
            record_size, _, pointer_format, segment_offset, _, page_count = fileset.unpack('<IHHQIH', pos)
            if record_size < 22 + page_count * 2 or record_size > end - pos:
                raise ValueError('Invalid chained segment size')
            if self.segments[i]['vmaddr'] - self.base != segment_offset:
                raise ValueError('Chained segment does not match root mapping')
            self.formats[i] = pointer_format

    def locate(self, addr, size):
        for i, segment in enumerate(self.segments):
            delta = addr - segment['vmaddr']
            if size >= 0 and 0 <= delta <= segment['filesize'] - size:
                return i, segment['fileoff'] + delta
        raise ValueError('Virtual range is not backed by fileset bytes')

    def read(self, addr, size):
        _, offset = self.locate(addr, size)
        return self.fs.read(offset, size)

    def resolve(self, addr):
        segment, offset = self.locate(addr, 8)
        if self.formats.get(segment) != 8:
            raise ValueError('Unsupported chained pointer format')
        raw, = self.fs.unpack('<Q', offset)
        cache_level = (raw >> 30) & 3
        if cache_level != 0:
            raise ValueError('Non-root cache pointer requires another cache base')
        target = self.base + (raw & 0x3FFFFFFF)
        self.locate(target, 4)
        return dict(fileoff=offset, raw=f'{raw:016x}', pointer_format=8,
                    cache_level=cache_level, target=target)


def resolve_auth_stub(cache, addr):
    """Recognize the specific ADRP/ADD/LDR/BRAA stub before following its GOT."""
    import struct
    code = cache.read(addr, 16)
    adrp, add, ldr, braa = struct.unpack('<4I', code)
    if (adrp & 0x9F00001F != 0x90000011 or add & 0xFF8003FF != 0x91000231
            or ldr != 0xF9400230 or braa != 0xD71F0A11):
        raise ValueError('Unrecognized authenticated stub')
    immediate = ((adrp >> 5 & 0x7FFFF) << 2) | (adrp >> 29 & 3)
    if immediate & 0x100000:
        immediate -= 0x200000
    got = (addr & ~4095) + (immediate << 12) + ((add >> 10 & 0xFFF) << (12 if add & (1 << 22) else 0))
    return dict(**cache.resolve(got), stub_addr=addr, got_addr=got,
                stub_bytes=code.hex(), stub_sha256=digest(code))


SLOTS = {
    '__ZTV18IOMemoryDescriptor': (0x1E8,),
    '__ZTV40AppleUSBHostClientBufferMemoryDescriptor': (0x1E8,),
    '__ZTV31AppleUSBHostInterfaceUserClient': (0xA00, 0xA08, 0xA68, 0xA80),
    '__ZTV17AppleUSBIORequest': (0x1B0, 0x1B8, 0x1C0, 0x1C8, 0x1D0),
    '__ZTV30AppleUSBXHCIIsochronousRequest': (0x160, 0x1A8, 0x2B8, 0x2C0, 0x308, 0x318),
    '__ZTV34AppleUSBXHCIIsochronousRequestPool': (0x1A8,),
    '__ZTV12AppleUSBXHCI': (0xAC8, 0xAD0, 0xB10, 0xBF0, 0xBF8, 0xCD0),
    '__ZTV17AppleT8112USBXHCI': (0xAC8, 0xAD0, 0xB10, 0xBF0, 0xBF8, 0xCD0),
    '__ZTV15AppleUSBXHCIARM': (0xAC8, 0xAD0, 0xB10, 0xBF0, 0xBF8, 0xCD0),
    '__ZTV17AppleT8101USBXHCI': (0xB10,),
}


def audit(input_path):
    data = input_path.read_bytes()
    fs = Fileset(data)
    cache = KernelCache(fs)
    modules = [fs.module(n) for n in fs.members if 'USB' in n or n == 'com.apple.kernel']
    names = {}
    addresses = {}
    for module in modules:
        for symbol in module['symbols']:
            names.setdefault(symbol['name'], []).append((module['name'], symbol))
            addresses.setdefault(symbol['addr'], []).append(symbol['name'])
    rows = []
    for name, slots in SLOTS.items():
        entries = names.get(name, [])
        if len(entries) != 1:
            raise ValueError(f'Expected unique vtable: {name}')
        module, table = entries[0]
        for slot in slots:
            address = table['addr'] + 16 + slot  # Itanium ABI address point.
            row = cache.resolve(address)
            target_names = addresses.get(row['target'], [])
            if not target_names:
                raise ValueError(f'Unresolved virtual target: {name} + {slot:x}')
            rows.append(dict(**row, module=module, vtable=name, vtable_addr=table['addr'],
                             slot=slot, names=target_names))
    direction_name = '__ZNK18IOMemoryDescriptor12getDirectionEv'
    entries = names[direction_name]
    if len(entries) != 1:
        raise ValueError('Ambiguous getDirection implementation')
    module, symbol = entries[0]
    primitive = cache.read(symbol['addr'], 16)
    endpoint_type_stub = resolve_auth_stub(cache, 0xFFFFFE000B5BD400)
    endpoint_type_stub['names'] = addresses.get(endpoint_type_stub['target'], [])
    if endpoint_type_stub['names'] != ['__ZN11StandardUSB15getEndpointTypeEPKNS_18EndpointDescriptorE']:
        raise ValueError('Unexpected endpoint type stub target; this audit is version-specific')
    return dict(schema='A23-host-driver-dispatch-1', usb_accessed=False,
                root_cause_confirmed=False, runtime_controller_identity_verified=False,
                input_sha256=digest(data), fileset_uuid=fs.uuid, root_base=cache.base,
                pointer_formats=cache.formats, slots=rows,
                endpoint_type_stub=endpoint_type_stub,
                direction_primitive=dict(module=module, name=direction_name, addr=symbol['addr'],
                                         bytes=primitive.hex(), sha256=digest(primitive)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    print(json.dumps(audit(args.input), indent=2))


if __name__ == '__main__':
    main()
