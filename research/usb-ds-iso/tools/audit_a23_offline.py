#!/usr/bin/env python3
"""Audit frozen A23 sources and saved transfers without USB or state changes.

Default output is JSON on stdout. --output creates a new evidence directory;
existing directories, capture state and frozen inputs are never overwritten.
The only executed binary is a temporary C structure-layout probe (no USB API).
"""
import argparse
from collections import Counter
import contextlib
import difflib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

if sys.version_info < (3, 10):
    raise SystemExit('Python >=3.10 is required by the frozen diagnostic decoder; use python3.12 on this host.')

from analyze_a23_native_errors import analyze as legacy, verify_manifest
from analyze_clock_audit import clock_record
from analyze_native_serial_run import analyze as saved_transfer, rows
from build_patch import validate_module, build, BUILD_ID
from nso2elf import build_elf
from analyze_no_td_window import analyze as empty_window
from workflows.artifacts import ROOT, PRIVATE, archive_path, verify

MATCHED_RUNS = (
    'A-A23-HS-burst-window-20261009-203446',
    'A-A23-HS-matched-serial-20261009-223428',
    'A-A23-HS-matched-serial-20261011-210736',
    'A-A23-HS-matched-serial-20261011-221215',
)
CLOCK_RUNS = (
    'A-A23-HS-clock-audit-20261011-225058',
    'A-A23-HS-serial-clock-20261011-235126',
    'A-A23-HS-serial-clock-20261012-000235',
)
COLLECTIONS = ('A23-serial-clock-20261011-235558',
               'A23-serial-clock-20261012-000707')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def insertions(before, after):
    """Report all differences, including changes that are not pure additions."""
    a, b = before.splitlines(keepends=True), after.splitlines(keepends=True)
    changes = []
    for tag, i, j, k, l in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != 'equal':
            changes.append(dict(operation=tag, old_line=i + 1, new_line=k + 1,
                                before=''.join(a[i:j]), after=''.join(b[k:l])))
    return dict(only_insertions=all(c['operation'] == 'insert' for c in changes),
                changes=changes)


def native_batches(records):
    batches, current = [], []
    for r in records:
        if r.get('kind') != 'darwin_iso_native':
            continue
        if r['index'] == 0 and current:
            batches.append(current)
            current = []
        current.append(r)
    if current:
        batches.append(current)
    return batches


def classify(attempt):
    if attempt['passed']:
        return 'strict_per_attempt_pass'
    if attempt['exact_raw'] and attempt['consecutive'] and attempt['terminal'] and not attempt['native']:
        return 'native_error_with_correct_raw_and_device_completion'
    if not attempt['terminal']:
        return 'incomplete_device_completion'
    return 'other_failure'


def layout_probe(tree, folder):
    source = folder / 'layout.c'
    source.write_text('#include <stdio.h>\n#include <stddef.h>\n'
                      '#include "darwin_usb.h"\nint main(void) {\n'
                      'printf("%zu %zu %zu %zu\\n", sizeof(struct darwin_transfer_priv),\n'
                      'offsetof(struct darwin_transfer_priv, isoc_framelist),\n'
                      'offsetof(struct darwin_transfer_priv, result),\n'
                      'offsetof(struct darwin_transfer_priv, req)); return 0; }\n')
    target = folder / 'layout'
    subprocess.run(['cc', '-std=c11', '-DHAVE_CONFIG_H', '-I' + str(tree),
                    '-I' + str(tree / 'libusb'), '-I' + str(tree / 'libusb/os'),
                    str(source), '-o', str(target)], check=True, capture_output=True)
    values = subprocess.check_output([str(target)], text=True).split()
    return dict(zip(('sizeof', 'isoc_framelist_offset', 'result_offset', 'req_offset'),
                    map(int, values)))


def source_review():
    old, new = [PRIVATE / name for name in ('host-A23-matched-serial-2', 'host-A23-serial-clock-1')]
    metas = [json.loads((p / 'manifest.json').read_text()) for p in (old, new)]
    libs = [Path(m['library']) for m in metas]
    trees = [p.parents[2] for p in libs]
    checks = [verify(p) for p in (old, new, PRIVATE / 'host-A23-no-td-window',
                                 PRIVATE / 'host-A23-clock-audit-1', PRIVATE / 'packages-A23-interval1/A')]
    for m, p, tree in zip(metas, libs, trees):
        if sha(p) != m['static_library_sha256'] or sha(tree / 'libusb/os/darwin_usb.c') != m['backend_sha256']:
            raise ValueError('Library/backend does not match the frozen receiver manifest')
    source_files = ('receiver-source.c', 'native_file_guard.h', 'serial_ring_guard.h',
                    'iso_probe_protocol.h', 'preflight.c')
    identical = {name: (old / name).read_bytes() == (new / name).read_bytes() for name in source_files}
    comparisons, diffs, inputs = {}, {}, []
    for name in ('darwin_usb.c', 'darwin_usb.h'):
        paths = [tree / 'libusb/os' / name for tree in trees]
        texts = [p.read_text() for p in paths]
        comparisons[name] = insertions(*texts)
        diffs[name] = ''.join(difflib.unified_diff(texts[0].splitlines(True), texts[1].splitlines(True),
                                                 fromfile='matched/' + name, tofile='clock/' + name))
        inputs.extend(dict(path=str(p), sha256=sha(p)) for p in paths)
    names = [subprocess.check_output(['ar', '-t', str(p)], text=True).splitlines() for p in libs]
    changed = []
    for name in sorted(set(names[0]) | set(names[1])):
        content = [subprocess.check_output(['ar', '-p', str(p), name]) if name in members else b''
                   for p, members in zip(libs, names)]
        if content[0] != content[1]:
            changed.append(dict(member=name, bytes=[len(b) for b in content],
                                sha256=[hashlib.sha256(b).hexdigest() for b in content]))
    with tempfile.TemporaryDirectory(prefix='a23-offline-layout-') as tmp:
        layouts = []
        for i, tree in enumerate(trees):
            folder = Path(tmp) / str(i)
            folder.mkdir()
            layouts.append(layout_probe(tree, folder))
    return dict(verified_artifacts=checks, receiver_files_identical=identical,
                backend_comparisons=comparisons, library_member_lists_identical=names[0] == names[1],
                changed_library_members=changed, private_layouts=dict(matched=layouts[0], clock=layouts[1]),
                source_inputs=inputs), diffs


def transfer_review():
    historical = legacy()
    attempts, verified = [], []
    for index, r in enumerate(historical['runs']):
        group = 'original-host64' if index < 2 else 'microframe-observation'
        attempts.append(dict(run=r['run'], group=group, sequence=1,
                             classification=('strict_per_attempt_pass' if r['strict_single_success'] else
                                             'native_error_with_correct_raw_and_device_completion'),
                             exact_raw=r['exact_raw_packets'], terminal=r['terminal_success'],
                             not_sent_prefix=r['empty_not_sent_prefix_slots'],
                             payloads=len(r['active_indices']), indices=r['active_indices'],
                             overall=r['overall_codes'], context_words=r['context_words'],
                             valid_mach_record=False, full_log_matches_host=r['full_log_matches_host']))
        verified.append(dict(folder=r['source'], files=len(r['verified_files']), sha256_verified=True))
    for name in MATCHED_RUNS + CLOCK_RUNS:
        run = PRIVATE / 'runs' / name
        files = verify_manifest(run)
        verified.append(dict(folder=str(run), files=len(files), sha256_verified=True))
        evidence, backend = saved_transfer(run), rows(run / 'native-stderr.txt')
        batches = native_batches(backend)
        clocks = [clock_record(r) for r in backend if r.get('kind') == 'darwin_iso_clock_audit']
        queues = [r for r in backend if r.get('kind') == 'darwin_iso_queue_timing']
        if len(batches) != len(evidence['attempts']) or (clocks and len(clocks) != len(batches)) or len(queues) != len(batches):
            raise ValueError('Unmatched transfer/native/timing records: ' + name)
        for i, (a, batch, q) in enumerate(zip(evidence['attempts'], batches, queues)):
            if [r['index'] for r in batch] != list(range(960)):
                raise ValueError('Missing/duplicate native slots: ' + name)
            prefix = 0
            for r in batch:
                if r['status'] != 0xE000400E or r['actual'] != 0:
                    break
                prefix += 1
            c = clocks[i] if clocks else None
            attempts.append(dict(run=name, group='matched-timing' if name in MATCHED_RUNS else 'mach-observation',
                                 sequence=a['sequence'], classification=classify(a), exact_raw=a['exact_raw'],
                                 terminal=a['terminal'], not_sent_prefix=prefix, payloads=len(a['indices']),
                                 indices=a['indices'], overall=sorted({f"{r['overall']:08X}" for r in batch}),
                                 native_status_counts={f'{k:08X}': v for k, v in Counter(r['status'] for r in batch).items()},
                                 context=a['diagnostics'].get('context_snapshot'),
                                 terminal_code=a['diagnostics'].get('terminal'),
                                 valid_mach_record=bool(c and c['valid']),
                                 estimated_start_minus_queue_after_ms=c['estimated_start_minus_queue_after_ms'] if c else None,
                                 queue_duration_ms=(q['queue_after_ns'] - q['queue_before_ns']) / 1e6,
                                 observed_ring_wraps_in_run=evidence['observed_ring_wraps']))
    groups = {}
    for group in dict.fromkeys(a['group'] for a in attempts):
        selected = [a for a in attempts if a['group'] == group]
        groups[group] = dict(bursts=len(selected), classifications=dict(Counter(a['classification'] for a in selected)),
                             valid_mach_records=sum(a['valid_mach_record'] for a in selected),
                             valid_mach_records_on_failure=sum(a['valid_mach_record'] for a in selected
                                                              if a['classification'] != 'strict_per_attempt_pass'))
    collections = []
    for name, run_name in zip(COLLECTIONS, CLOCK_RUNS[1:]):
        folder = PRIVATE / 'collections' / name
        checked = verify(folder)
        data = json.loads((folder / 'collection.json').read_text())
        if data['run'] != str(PRIVATE / 'runs' / run_name) or sha(folder / 'switch-logfile.txt') != data['log_sha256']:
            raise ValueError('Collection/log association mismatch')
        collections.append(dict(**checked, run=run_name, log_bytes=data['log_bytes'],
                                strict_serial_acceptance_passed=data['strict_serial_acceptance_passed'],
                                runtime_revision_identity_verified=data['runtime_revision_identity_verified'],
                                all_submissions_and_completions_match=data['all_submissions_and_completions_match'],
                                observed_ring_wraps=data['observed_ring_wraps']))
    empty = PRIVATE / 'runs/A-A23-HS-no-td-window-20261009-185001'
    empty_files = verify_manifest(empty)
    baseline = empty_window(empty)
    baseline = {k: baseline[k] for k in ('host_baseline_passed', 'native_records', 'native_status_counts',
                                       'overall_codes', 'initial_empty_not_sent_slots', 'raw_all_zero')}
    baseline.update(verified_files=len(empty_files), run=empty.name,
                    one_baseline_does_not_exclude_intermittent_host_fault=True)
    return dict(groups=groups, attempts=attempts, verified_runs=verified, verified_collections=collections,
                no_td_baseline=baseline,
                total_bursts=len(attempts), classification_totals=dict(Counter(a['classification'] for a in attempts)),
                no_cross_backend_success_rate_computed=True)


def firmware_review():
    original = PRIVATE / 'module/exefs/main'
    nso = validate_module(original.read_bytes())
    module = archive_path() / 'module'
    # Tie archived ELF and C/disassembly context to the validated original module.
    if (module / 'exefs/main').read_bytes() != original.read_bytes():
        raise ValueError('Archived original differs from validated current NSO')
    if (module / 'usb.elf').read_bytes() != build_elf(nso):
        raise ValueError('Archived ELF differs from the validated NSO conversion')
    with tempfile.TemporaryDirectory(prefix='a23-offline-patch-') as tmp:
        out = Path(tmp) / 'A'
        with contextlib.redirect_stdout(io.StringIO()):
            build(nso, 1, Path('/opt/devkitpro/devkitA64/bin'), out, frame_lead=32,
                  explicit_all=True, mps=256, burst=True, event_audit=True,
                  context_audit=True, followup_sia=True, interval=1)
        baseline = PRIVATE / 'packages-A23-interval1/A'
        files = ('inject.bin', 'atmosphere/exefs_patches/SysDVR-ISO/' + BUILD_ID + '.ips')
        rebuilt = {name: (out / name).read_bytes() == (baseline / name).read_bytes() for name in files}
        if not all(rebuilt.values()):
            raise ValueError('Current patch source differs from frozen deployed A23 code')
    listing = (module / 'decompiled.c').read_text()
    functions = {}
    for address in ('302e0', '31ab0', '30700', '30f70', '2a980', '2c690', '30470'):
        marker = '// ---- FUN_000' + address + ' @ 000' + address + ' ----'
        start = listing.index(marker)
        end = listing.find('// ---- ', start + len(marker))
        functions[address] = dict(line=listing[:start].count('\n') + 1,
                                  text=listing[start:end if end >= 0 else None])
    return dict(original_path=str(original), original_sha256=sha(original),
                build_id=nso.build_id.hex().upper(), archive_original_identical=True,
                archived_elf_matches_validated_nso=True, patch_rebuild_matches_frozen=rebuilt,
                archived_inputs=[dict(path=str(module / name), sha256=sha(module / name))
                                 for name in ('usb.elf', 'decompiled.c', 'disassembly.txt')],
                patch_source=dict(path=str(ROOT / 'patches/iso_burst_context.S'), sha256=sha(ROOT / 'patches/iso_burst_context.S')),
                functions=functions, decompilation_is_not_a_wire_trace=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Create a new directory; never overwrite an existing one')
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('Output already exists; refusing to overwrite evidence')
    sources, diffs = source_review()
    result = dict(schema='A23-offline-review-1', usb_accessed=False, sd_accessed=False,
                  analysis_tool_sha256=sha(Path(__file__)),
                  capture_state_modified=False, frozen_evidence_modified=False,
                  root_cause_confirmed=False, fix_verified=False, stability_verified=False,
                  source_review=sources, transfer_review=transfer_review(), firmware_review=firmware_review())
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
        for name, diff in diffs.items():
            (args.output / (name + '.diff')).write_text(diff)
        entries = [sha(p) + '  ' + p.name for p in sorted(args.output.iterdir())]
        (args.output / 'SHA256SUMS').write_text('\n'.join(entries) + '\n')
        print(json.dumps(dict(output=str(args.output.resolve()), total_bursts=result['transfer_review']['total_bursts'],
                              groups=result['transfer_review']['groups']), indent=2))
    else:
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
