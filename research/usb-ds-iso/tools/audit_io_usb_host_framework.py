#!/usr/bin/env python3
"""Export the local IOUSBHost framework and selected kernel paths, without USB I/O.

The stub inspector resolves loaded code addresses only. This audit is pinned to
the local framework UUID and kernelcache hash; it never opens a USB object.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from audit_host_driver import DEFAULT_INPUT, Fileset, audit, digest
from audit_host_driver_dispatch import KernelCache

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = '/System/Library/Frameworks/IOUSBHost.framework/Versions/A/IOUSBHost'
UUID = 'B0D41EEF-C9BF-39DD-A1C4-226DCB94E78B'
KERNEL_SHA = '06846c718a67715f540c7f5a5d5a183da6185d94b6fc01f1ce57a30b601be44d'
KERNEL_TARGETS = (
    'FrameworkInterfaceClient16_hostPipeIOIsoch', 'FrameworkInterfaceClient14_hostPipeAbort',
    'FrameworkInterfaceClient13hostPipeAbort', 'FrameworkInterfaceClient14externalMethod',
    'FrameworkInterfaceClient10hostPipeIOEhP18IOMemoryDescriptorP31IOUSBHostIsochronousTransaction',
    'FrameworkInterfaceClient32isochronousTransactionCompletion',
    '13IOUSBHostPipe2ioEP18IOMemoryDescriptorP31IOUSBHostIsochronousTransaction',
    '13IOUSBHostPipe18isochronousIoGated', '13IOUSBHostPipe5abortE', '13IOUSBHostPipe10abortGated',
    '27AppleUSBHostFrameworkClient19copyKernelMemoryMap',
    '27AppleUSBHostFrameworkClient24copyDataMemoryDescriptor',
    '17AppleUSBIORequest7prepareEP13IOUSBHostPipeP18IOMemoryDescriptorP31IOUSBHostIsochronousTransaction',
)
SLOTS = {
    '__ZTV36AppleUSBHostFrameworkInterfaceClient': (0xa10, 0xa18, 0xa70, 0xa88, 0xa90, 0xaa0),
    '__ZTV13IOUSBHostPipe': (0x198, 0x548, 0x598),
    '__ZTV30AppleUSBXHCIIsochronousRequest': (0x290,),
    '__ZTV12AppleUSBXHCI': (0x998,), '__ZTV17AppleT8112USBXHCI': (0x998,),
    '__ZTV34AppleUSBXHCIIsochronousRequestPool': (0x148,),
}


def parse_text_bytes(text):
    data = bytearray()
    base = None
    for line in text.splitlines():
        if not line.startswith('0x'):
            continue
        match = re.fullmatch(r'0x([0-9a-fA-F]+): ((?:[0-9a-fA-F]{2} ?)+)\s*', line)
        if not match:
            raise ValueError('Malformed section byte row')
        address = int(match[1], 16)
        chunk = bytes.fromhex(match[2])
        if base is None:
            base = address
        if address != base + len(data):
            raise ValueError('Non-contiguous section bytes')
        data.extend(chunk)
    if base is None:
        raise ValueError('No section bytes')
    return base, bytes(data)


def function_ranges(metadata, base, data):
    starts = metadata.split('    -function_starts:\n', 1)[1].split('    -objc:', 1)[0]
    functions = []
    for line in starts.splitlines():
        match = re.fullmatch(r'\s+0x([0-9a-fA-F]+)\s+(.+)', line)
        if match:
            functions.append((int(match[1], 16), match[2]))
    if not functions or functions[0][0] != base:
        raise ValueError('Function starts do not match text base')
    rows = []
    for i, (address, name) in enumerate(functions):
        end = functions[i + 1][0] if i + 1 < len(functions) else base + len(data)
        if not base <= address < end <= base + len(data):
            raise ValueError('Invalid function range')
        label = 'f_' + f'{address:x}_' + re.sub(r'[^a-zA-Z0-9_]', '_', name)
        rows.append(dict(addr=address, end=end, name=name, label=label,
                         sha256=digest(data[address - base:end - base])))
    return rows


def kernel_dispatch(data):
    fs = Fileset(data)
    cache = KernelCache(fs)
    modules = [fs.module(n) for n in fs.members if 'USB' in n or n == 'com.apple.kernel']
    names = {}
    addresses = {}
    for module in modules:
        for symbol in module['symbols']:
            names.setdefault(symbol['name'], []).append(symbol)
            addresses.setdefault(symbol['addr'], []).append(symbol['name'])
    rows = []
    for name, slots in SLOTS.items():
        if len(names.get(name, [])) != 1:
            raise ValueError(f'Ambiguous vtable: {name}')
        table = names[name][0]['addr']
        for slot in slots:
            pointer = cache.resolve(table + 16 + slot)
            target = addresses.get(pointer['target'])
            if not target:
                raise ValueError('Unresolved vtable target')
            rows.append(dict(**pointer, vtable=name, slot=slot, names=target))
    # sMethods base is verified in this image's externalMethod machine code.
    for selector in (0x15, 0x17, 0x1c):
        address = 0xfffffe0008960128 + selector * 24
        pointer = cache.resolve(address)
        _, *counts = struct.unpack('<Q4I', cache.read(address, 24))
        rows.append(dict(**pointer, selector=selector, counts=counts,
                         names=addresses[pointer['target']]))
    return rows


def export(output, objdump=None):
    if output.exists():
        raise FileExistsError(f'Refusing existing output: {output}')
    kernel_data = DEFAULT_INPUT.read_bytes()
    if digest(kernel_data) != KERNEL_SHA:
        raise ValueError('Kernelcache differs from audited image')
    commands = [
        ['/usr/bin/dyld_info', '-uuid', '-segments', '-function_starts', '-objc', '-imports', FRAMEWORK],
        ['/usr/bin/dyld_info', '-section_bytes', '__TEXT', '__text', FRAMEWORK],
        ['/usr/bin/dyld_info', '-disassemble', FRAMEWORK],
    ]
    metadata, byte_text, assembly = [subprocess.check_output(c, text=True) for c in commands]
    if UUID not in metadata:
        raise ValueError('Framework UUID differs from audited image')
    base, text = parse_text_bytes(byte_text)
    if len(text) != 95236 or base != 0x197acad58:
        raise ValueError('Unexpected framework code range')
    functions = function_ranges(metadata, base, text)
    dispatch = kernel_dispatch(kernel_data)
    inspector = ROOT / 'host/io_usb_host_framework_inspect.m'
    with tempfile.TemporaryDirectory(prefix='a23-framework-inspect-') as directory:
        binary = str(Path(directory) / 'inspect')
        compile_command = ['/usr/bin/clang', '-std=c11', '-fobjc-arc', '-Wall', '-Wextra', '-Werror',
                           '-framework', 'Foundation', '-framework', 'IOUSBHost', str(inspector), '-o', binary]
        subprocess.run(compile_command, check=True)
        stubs = json.loads(subprocess.check_output([binary], text=True))
    output.mkdir(parents=True, exist_ok=False)
    for name, content in (('framework-metadata.txt', metadata), ('framework-section-bytes.txt', byte_text),
                          ('framework.asm', assembly)):
        (output / name).write_text(content)
    (output / 'framework.text').write_bytes(text)
    kernel = audit(DEFAULT_INPUT, output / 'kernel', objdump,
                   ('com.apple.iokit.IOUSBHostFamily',), KERNEL_TARGETS)
    result = dict(schema='A23-IOUSBHost-framework-1', usb_accessed=False, sd_accessed=False,
                  root_cause_confirmed=False, historical_framework_identity_verified=False,
                  framework_uuid=UUID, text_base=base, text_bytes=len(text), text_sha256=digest(text),
                  framework_functions=functions, kernel_dispatch=dispatch,
                  kernel_sha256=KERNEL_SHA, kernel_targets=kernel['modules'][0]['targets'],
                  stubs=stubs, commands=commands, inspector_compile_command=compile_command)
    (output / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    (output / inspector.name).write_bytes(inspector.read_bytes())
    (output / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--objdump')
    args = parser.parse_args()
    result = export(args.output, args.objdump)
    print(json.dumps(dict(output=str(args.output), usb_accessed=False,
                         framework_functions=len(result['framework_functions']),
                         kernel_targets=len(result['kernel_targets'])), indent=2))


if __name__ == '__main__':
    main()
