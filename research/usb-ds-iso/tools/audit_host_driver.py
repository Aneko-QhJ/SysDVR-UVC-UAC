#!/usr/bin/env python3
"""Read a decoded local MH_FILESET; export bounded, reproducible USB evidence.

No device access, kernel inspection, capture, or writes to existing outputs.
Mach-O offsets in a fileset member are relative to the complete fileset.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / 'private/host-driver-inputs/macos-27.0.1-26A434/kernelcache.macho'
MODULES = ('com.apple.iokit.IOUSBHostFamily', 'com.apple.driver.usb.AppleUSBXHCI')
TARGETS = (
    'translateIOReturnToLegacy', 'isochronousRequestCompletion',
    '31AppleUSBHostInterfaceUserClient2ioEhP25IOUSBHostIsochronousFrame',
    '17AppleUSBIORequest8completeEv', 'translateCompletionCode',
    'IsochronousRequest6update', 'IsochronousRequest7prepare',
    'IsochronousRequest6finishEi', '19AppleUSBXHCIRequest6finishEi',
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Fileset:
    def __init__(self, data):
        self.data = data
        header = self.unpack('<8I', 0)
        if header[0] != 0xFEEDFACF or header[1] != 0x100000C or header[3] != 12:
            raise ValueError('Expected an ARM64 little-endian MH_FILESET')
        self.members = {}
        self.uuid = None
        for cmd, offset, size in self.commands(0):
            if cmd == 0x1B:
                self.uuid = self.read(offset + 8, 16).hex()
            if cmd == 0x80000035:
                vmaddr, fileoff, nameoff, _ = self.unpack('<QQII', offset + 8)
                if not 32 <= nameoff < size:
                    raise ValueError('Invalid fileset entry name offset')
                name = self.cstring(offset + nameoff, offset + size)
                if name in self.members:
                    raise ValueError('Duplicate fileset entry')
                self.read(fileoff, 32)
                self.members[name] = {'fileoff': fileoff, 'vmaddr': vmaddr}

    def read(self, offset, size):
        if offset < 0 or size < 0 or offset > len(self.data) - size:
            raise ValueError('Range outside fileset')
        return self.data[offset:offset + size]

    def unpack(self, fmt, offset):
        return struct.unpack(fmt, self.read(offset, struct.calcsize(fmt)))

    def cstring(self, offset, end):
        if not 0 <= offset <= end <= len(self.data):
            raise ValueError('String range outside fileset')
        terminator = self.data.find(b'\0', offset, end)
        if terminator < 0:
            raise ValueError('Unterminated Mach-O string')
        return self.data[offset:terminator].decode('utf-8')

    def commands(self, base):
        magic, _, _, _, ncmds, size, _, _ = self.unpack('<8I', base)
        if magic != 0xFEEDFACF:
            raise ValueError('Invalid member Mach-O magic')
        if ncmds > size // 8:
            raise ValueError('Invalid load command count')
        offset, end = base + 32, base + 32 + size
        self.read(offset, size)
        for _ in range(ncmds):
            cmd, cmdsize = self.unpack('<II', offset)
            if cmdsize < 8 or cmdsize % 8 or cmdsize > end - offset:
                raise ValueError('Invalid load command size')
            yield cmd, offset, cmdsize
            offset += cmdsize
        if offset != end:
            raise ValueError('Load commands do not cover sizeofcmds')

    def module(self, name):
        entry = self.members[name]
        sections, symbols, uuid, symtab = [], [], None, None
        for cmd, offset, size in self.commands(entry['fileoff']):
            if cmd == 0x1B:
                if size != 24:
                    raise ValueError('Invalid UUID command')
                uuid = self.read(offset + 8, 16).hex()
            elif cmd == 0x19:
                if size < 72:
                    raise ValueError('Truncated segment command')
                fields = self.unpack('<16sQQQQiiII', offset + 8)
                nsects = fields[7]
                if size != 72 + 80 * nsects:
                    raise ValueError('Invalid section count')
                for i in range(nsects):
                    sec = self.unpack('<16s16sQQIIIIIIII', offset + 72 + i * 80)
                    sections.append(dict(name=sec[0].rstrip(b'\0').decode(),
                                         segment=sec[1].rstrip(b'\0').decode(),
                                         addr=sec[2], size=sec[3], offset=sec[4], flags=sec[8]))
            elif cmd == 2:
                if size != 24:
                    raise ValueError('Invalid symbol command')
                symtab = self.unpack('<IIII', offset + 8)
        if symtab is None:
            raise ValueError('No symbol table')
        symoff, nsyms, stroff, strsize = symtab
        self.read(symoff, nsyms * 16)
        strings = self.read(stroff, strsize)
        for i in range(nsyms):
            index, kind, section, _, addr = self.unpack('<IBBHQ', symoff + 16 * i)
            if index >= len(strings):
                raise ValueError('Invalid symbol string offset')
            if kind & 0xE != 0xE or kind & 0xE0:
                continue  # Only defined section symbols, excluding STAB records.
            if not 1 <= section <= len(sections):
                raise ValueError('Invalid symbol section')
            symbol = self.cstring(stroff + index, stroff + strsize)
            symbols.append(dict(name=symbol, addr=addr, section=section))
        return dict(name=name, uuid=uuid, entry=entry, sections=sections, symbols=symbols)


def selected(name, targets=TARGETS):
    return any(t in name for t in targets) and '.cold' not in name and 'thunk' not in name


def audit(input_path, output=None, objdump=None, module_names=MODULES, targets=TARGETS):
    if output is not None and output.exists():
        raise FileExistsError(f'Refusing existing output: {output}')
    data = input_path.read_bytes()
    fs = Fileset(data)
    modules = [fs.module(name) for name in module_names]
    result = dict(schema='A23-local-host-driver-1', usb_accessed=False,
                  root_cause_confirmed=False, input=str(input_path.resolve()),
                  input_bytes=len(data), input_sha256=digest(data), fileset_uuid=fs.uuid,
                  modules=[])
    # Parse and validate all inputs before creating the new output directory.
    for module in modules:
        text = next(s for s in module['sections'] if s['name'] == '__text')
        code = fs.read(text['offset'], text['size'])
        funcs = sorted((s for s in module['symbols']
                        if module['sections'][s['section'] - 1]['name'] == '__text'),
                       key=lambda s: s['addr'])
        selected_targets = []
        for s in funcs:
            if selected(s['name'], targets):
                end = next((z['addr'] for z in funcs if z['addr'] > s['addr']),
                           text['addr'] + text['size'])
                if not text['addr'] <= s['addr'] < end <= text['addr'] + text['size']:
                    raise ValueError('Function range outside text')
                start_offset = text['offset'] + s['addr'] - text['addr']
                selected_targets.append(dict(**s, end=end, fileoff=start_offset,
                                    sha256=digest(fs.read(start_offset, end - s['addr']))))
        result['modules'].append(dict(name=module['name'], uuid=module['uuid'], text=text,
                                      text_sha256=digest(code), targets=selected_targets))
    if output is not None:
        output.mkdir(parents=True, exist_ok=False)
        for module, entry in zip(modules, result['modules']):
            stem = module['name'].rsplit('.', 1)[-1]
            text = entry['text']
            codefile = output / (stem + '.text')
            codefile.write_bytes(fs.read(text['offset'], text['size']))
            (output / (stem + '.json')).write_text(json.dumps(module, indent=2) + '\n')
            lines = []
            for s in module['symbols']:
                if module['sections'][s['section'] - 1]['name'] == '__text':
                    lines.append(f'{s["addr"]:x}\t{s["name"]}' + ('\tselected' if selected(s['name'], targets) else ''))
            (output / (stem + '.tsv')).write_text('\n'.join(lines) + '\n')
            if objdump:
                for target in entry['targets']:
                    cmd = [objdump, '-D', '-b', 'binary', '-m', 'aarch64',
                           f'--adjust-vma={hex(text["addr"])}',
                           f'--start-address={hex(target["addr"])}',
                           f'--stop-address={hex(target["end"])}', str(codefile)]
                    asm = subprocess.check_output(cmd, text=True)
                    (output / (target['name'] + '.asm')).write_text(asm)
        (output / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
        files = sorted(p for p in output.iterdir() if p.is_file())
        (output / 'SHA256SUMS').write_text(''.join(f'{digest(p.read_bytes())}  {p.name}\n' for p in files))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=DEFAULT_INPUT)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--objdump', help='Optional AArch64 GNU objdump executable')
    parser.add_argument('--module', action='append', default=[], help='Additional fileset module name')
    parser.add_argument('--target', action='append', default=[], help='Additional function name fragment')
    args = parser.parse_args()
    modules = tuple(dict.fromkeys((*MODULES, *args.module)))
    targets = (*TARGETS, *args.target)
    print(json.dumps(audit(args.input, args.output, args.objdump, modules, targets), indent=2))


if __name__ == '__main__':
    main()
