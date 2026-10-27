#!/usr/bin/env python3
"""CPU-only regression checks for short24 filesystem path input capacity."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

import build_a23_short24_path_span_candidate as candidate
import build_a23_lifecycle_candidate as lifecycle

b = candidate.short


def audit(build, output):
    build, output = build.resolve(), output.resolve()
    b.verify_tree(build)
    b.require(not output.exists(), 'fresh audit output required')
    output.mkdir(parents=True)
    commands, rows = [], []
    for fixture, name in [('exit-model.c', 'exit-model'), ('file-adapter-model.c', 'file-adapter-model')]:
        source = output / fixture
        shutil.copyfile(candidate.PARENT / fixture, source)
        commands.append(lifecycle.compile_model(source, output / name, build / 'device'))
        # Negative SDK model reads the entire advertised span, independently of
        # tail contents. A padding assertion must not mask the actual overread.
        negative = output / ('negative-' + fixture)
        text = source.read_text()
        b.require(text.count('if(i>length)assert(!value);') == 1, 'SDK fixture changed')
        negative.write_text(text.replace('if(i>length)assert(!value);', '(void)value;'))
        commands.append(lifecycle.compile_model(negative, output / (name + '-old'), candidate.PREVIOUS / 'device'))

    for kind, primary, execution in [('normal', 'ok', 'ok'), ('diagnostic', 'ok', 'ok'),
                                     ('normal', 'create-error', 'ok'), ('normal', 'ok', 'create-error')]:
        name = '-'.join((kind, primary, execution))
        cmd = [str(output / 'exit-model'), kind, primary, execution, str(output / name)]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        (output / (name + '.stderr')).write_text(p.stderr)
        b.require(p.returncode == 0, 'fixed adapter check failed: ' + name)
        rows.append(dict(name=name, expected='success_and_preserved_failure_retention', result=json.loads(p.stdout)))
        commands.append(cmd)
    cmd = [str(output / 'file-adapter-model'), 'ok', str(output / 'fixed-lifecycle.bin')]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    b.require(p.returncode == 0, 'fixed lifecycle path check failed')
    rows.append(dict(name='lifecycle-full-span', result=json.loads(p.stdout)))
    commands.append(cmd)
    for name, cmd in [
        ('old-normal-path', [str(output / 'exit-model-old'), 'normal', 'ok', 'ok', str(output / 'old-normal')]),
        ('old-lifecycle-path', [str(output / 'file-adapter-model-old'), 'ok', str(output / 'old-lifecycle.bin')])]:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        (output / (name + '.stderr')).write_text(p.stderr)
        b.require(p.returncode != 0 and 'AddressSanitizer' in p.stderr and 'buffer-overflow' in p.stderr,
                  'old undersized input not rejected: ' + name)
        rows.append(dict(name=name, expected_failure=True, exit_code=p.returncode, full_span_overread_detected=True))
        commands.append(cmd)
    result = dict(schema='A23-short24-path-span-audit-1', native_scenarios=len(rows), rows=rows,
                  candidate_manifest_sha256=b.verify_tree(build), compiler_and_run_commands=commands,
                  modeled_sdk_reads_769_bytes=True, kernel_error_reproduced=False,
                  hardware_verified=False, sd_accesses=0, usb_operations=0)
    (output / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    shutil.copyfile(__file__, output / 'audit-tool.py')
    raw = ''.join(b.sha(p.read_bytes()) + '  ' + p.relative_to(output).as_posix() + '\n'
                  for p in sorted(output.rglob('*')) if p.is_file()).encode()
    (output / 'SHA256SUMS').write_bytes(raw)
    (output / 'COMMITTED').write_text(b.sha(raw) + '\n')
    b.verify_tree(output)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    r = audit(**vars(parser.parse_args()))
    print(json.dumps(dict(native_scenarios=r['native_scenarios'], hardware_verified=False)))
