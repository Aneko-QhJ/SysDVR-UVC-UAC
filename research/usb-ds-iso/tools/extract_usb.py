#!/usr/bin/env python3
"""Extract a user's installed firmware usb ExeFS; never print key-tool output."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from nso2elf import Nso, build_elf


def run_tool(tool, keys, *args):
    # Key loading warnings can contain private material: capture both streams.
    result = subprocess.run([str(tool), '-k', str(keys), *map(str, args)],
                            capture_output=True, text=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--keys', type=Path, required=True)
    parser.add_argument('--hactool', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    candidate = args.out / 'candidate.nca'
    matches = []
    index = []
    for nca in sorted(args.firmware.glob('*.nca')):
        parts = sorted(p for p in nca.iterdir() if re.fullmatch(r'\d\d', p.name)) if nca.is_dir() else [nca]
        if not parts:
            continue
        with candidate.open('wb') as dest:
            for part in parts:
                with part.open('rb') as source:
                    shutil.copyfileobj(source, dest)
        result = run_tool(args.hactool, args.keys, '-t', 'nca', candidate)
        title = re.search(r'^Title ID:\s*(\w+)', result.stdout, re.M)
        kind = re.search(r'^Content Type:\s*(.+)', result.stdout, re.M)
        row = {'file': nca.name, 'title_id': title[1] if title else None,
               'type': kind[1].strip() if kind else None}
        index.append(row)
        if title and title[1].lower() == '0100000000000809' and row['type'] == 'Data':
            shutil.copyfile(candidate, args.out / 'system-version.nca')
        if title and title[1].lower() == '0100000000000006' and row['type'] == 'Program':
            matches.append(nca.name)
            if len(matches) > 1:
                raise SystemExit('Multiple usb programs found; refuse to select implicitly')
            shutil.copyfile(candidate, args.out / 'usb.nca')
    candidate.unlink(missing_ok=True)
    (args.out / 'firmware-index.json').write_text(json.dumps(index, indent=2) + '\n')
    if len(matches) != 1:
        raise SystemExit('usb program not found; inspect firmware-index.json (no key output recorded)')
    result = run_tool(args.hactool, args.keys, '-t', 'nca',
                      '--exefsdir=' + str(args.out / 'exefs'), args.out / 'usb.nca')
    main_path = args.out / 'exefs/main'
    if result.returncode or not main_path.is_file():
        raise SystemExit('ExeFS extraction failed; check tool/key generation compatibility locally')
    raw = main_path.read_bytes()
    nso = Nso(raw)
    (args.out / 'usb.elf').write_bytes(build_elf(nso))
    for s in nso.sections:
        (args.out / ['text.bin', 'rodata.bin', 'data.bin'][s['index']]).write_bytes(s['content'])
    metadata = {'program_id': '0100000000000006', 'nca': matches[0],
                'build_id': nso.build_id.hex().upper(), 'sha256': hashlib.sha256(raw).hexdigest(),
                'segments': [{k: v for k, v in s.items() if k != 'content'} for s in nso.sections]}
    version_nca = args.out / 'system-version.nca'
    if version_nca.exists():
        version_dir = args.out / 'system-version'
        result = run_tool(args.hactool, args.keys, '-t', 'nca', '--romfsdir='+str(version_dir), version_nca)
        version_file = version_dir / 'file'
        if result.returncode == 0 and version_file.exists():
            version = version_file.read_bytes()
            if len(version) == 256:
                metadata['firmware_version'] = '.'.join(str(v) for v in version[:3])
                metadata['firmware_revision'] = int(version[4])
    (args.out / 'module.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
