#!/usr/bin/env python3
"""Offline short24 rebuild retaining the previously reviewed FS path capacity fix.

No package, SD access, authorization issuance or receiver launch. The consumed
first-live candidate and its sources remain unchanged.
"""
import argparse
import json
from pathlib import Path

import build_a23_short24_candidate as short
import build_a23_path_span_candidate as span

PARENT = short.ROOT / 'private/analysis/A23-path-span-device-review-20261016'
PARENT_HASH = '2cc16ce7a6c81bea4fb90f559edf3bc0f66e9d949ca996abc2d7b4983bcb606f'
PREVIOUS = short.ROOT / 'private/analysis/A23-short24-candidate-20261027-r2'
PREVIOUS_HASH = '80bb47ac8e02a8cfdce8dd25a074792f6e7a8b2731c6db13047ad6ec43ecbe98'


def build(output):
    output = output.resolve()
    short.require(short.verify_tree(PARENT) == PARENT_HASH, 'full-width parent changed')
    short.require(short.verify_tree(PREVIOUS) == PREVIOUS_HASH, 'first-live candidate changed')
    before_parent = short.DEVICE
    try:
        short.DEVICE = PARENT
        result = short.build(output)
    finally:
        short.DEVICE = before_parent
    old = PREVIOUS / 'device/source'
    new = output / 'device/source'
    names = {p.relative_to(new).as_posix() for p in new.rglob('*') if p.is_file()}
    old_names = {p.relative_to(old).as_posix() for p in old.rglob('*') if p.is_file()}
    changed = sorted(n for n in names | old_names if n not in names or n not in old_names or
                     (new / n).read_bytes() != (old / n).read_bytes())
    expected = sorted('uvc/' + n for n in (
        'ep0_candidate_file.c', 'ep0_candidate_recipe.h', 'ep0_diagnostic_file.c',
        'ep0_fs_path_span.h', 'ep0_lifecycle_file.c', 'ep0_session_file.c'))
    short.require(changed == expected, 'unrelated change relative to tested short24')
    short.require((output / 'controller/A/inject.bin').read_bytes() ==
                  (PREVIOUS / 'controller/A/inject.bin').read_bytes(), 'short24 controller changed')
    short.require((new / 'uvc/iso_runtime_payload.h').read_bytes() ==
                  (old / 'uvc/iso_runtime_payload.h').read_bytes(), 'runtime controller changed')
    machine = span.machine_review(output / 'device')
    short.require(len(machine['linked_path_objects']) == 5 and
                  machine['path_objects_in_bss'] and machine['total_path_storage_bytes'] == 3845,
                  'SDK paths lack complete linked storage')
    result.update(schema='A23-short24-path-span-candidate-1',
                  previous_candidate_manifest_sha256=PREVIOUS_HASH,
                  changed_device_sources=changed, machine_review=machine,
                  preserves_tested_short24_controller=True,
                  real_file_creation_verified=False, first_live_kernel_cause_confirmed=False,
                  receiver_rebound=False, remaining=0)
    result['source_hashes'][str(Path(__file__).relative_to(short.ROOT))] = short.sha(Path(__file__).read_bytes())
    (output / 'build.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    for p in (Path(__file__), Path(short.__file__), Path(span.__file__)):
        target = output / 'builder-sources' / p.name
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(p.read_bytes())
    raw = ''.join(short.sha(p.read_bytes()) + '  ' + p.relative_to(output).as_posix() + '\n'
                  for p in sorted(output.rglob('*')) if p.is_file()).encode()
    (output / 'SHA256SUMS').write_bytes(raw)
    (output / 'COMMITTED').write_text(short.sha(raw) + '\n')
    short.verify_tree(output)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    r = build(parser.parse_args().output)
    print(json.dumps({k: r[k] for k in ('runtime_recipe_sha256', 'object_count',
        'changed_device_sources', 'deployed', 'real_file_creation_verified')}))
