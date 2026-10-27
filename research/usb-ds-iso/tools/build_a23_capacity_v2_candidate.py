#!/usr/bin/env python3
"""Build isolated V2 capacity candidates and run computer-only boundary probes.

All transformations apply to new copies of a sealed input. Original device
sources, V1 formats, acquisition tickets and sealed evidence remain untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

import audit_a23_diagnostic_readiness as ready
import build_a23_log_guard_candidate as linked
from analyze_ep0_candidate_capture_v2 import decode_capture
from analyze_ep0_diagnostic_v2 import decode_diagnostic
from analyze_ep0_session_v2 import decode_session
from workflows.artifacts import verify

ROOT, REPO, SEALED = ready.ROOT, ready.REPO, ready.SEALED
PRIOR = SEALED.parent / 'A23-diagnostic-readiness-review-20261015'
DESIGN = SEALED.parent / 'A23-diagnostic-readiness-validation-20261015'
DECODERS = ('analyze_ep0_trace_v2.py', 'analyze_ep0_candidate_capture_v2.py',
            'analyze_ep0_diagnostic_v2.py', 'analyze_ep0_session_v2.py')
INPUTS = ('tools/build_a23_capacity_v2_candidate.py', 'tests/test_a23_capacity_v2_candidate.py',
          'tests/a23_capacity_v2_admission.c', 'tests/a23_capacity_v2_files.c',
          *('tools/' + name for name in DECODERS),
          'tools/build_a23_log_guard_candidate.py', 'tools/build_a23_log_candidate.py',
          'tools/build_a23_session_candidate.py', 'tools/analyze_a23_elf_boundaries.py')
FILE_CASES = ('ok', 'short-read', 'fs-open-error', 'create-error', 'collision',
              'file-open-error', 'write-error', 'silent-short-write', 'corrupt-write',
              'flush-error', 'size-error', 'extra-byte', 'short-size', 'read-error',
              'late-read-error', 'zero-read', 'oversize-read', 'commit-error')
FLAGS = ['-DISO_PROBE', '-DISO_PROBE_BURST_MODE', '-DISO_PROBE_EVENT_AUDIT',
         '-DISO_PROBE_CONTEXT_AUDIT', '-DISO_PROBE_FOLLOWUP_SIA']


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def revisions(name, source):
    """Explicit, unique replacements; never edit a source file in place."""
    edits = {
        'ep0_trace.h': [('#define EP0_TRACE_CAPACITY 128u', '#define EP0_TRACE_CAPACITY 256u'),
                        ('memcpy(out,"EP0TRC1",7)', 'memcpy(out,"EP0TRC2",7)'),
                        ('ep0_trace_u16(out+8,1)', 'ep0_trace_u16(out+8,2)')],
        'ep0_trace_owner.h': [('#define EP0_OWNER_SLOTS 16u', '#define EP0_OWNER_SLOTS 32u')],
        'ep0_candidate_capture.h': [('memcpy(out,"EP0OWN1",7)', 'memcpy(out,"EP0OWN2",7)'),
                                    ('ep0_trace_u16(out+8,1)', 'ep0_trace_u16(out+8,2)')],
        'ep0_diagnostic_capture.h': [('memcpy(out,"EP0DIA1",7)', 'memcpy(out,"EP0DIA2",7)'),
                                     ('ep0_trace_u16(out+8,1)', 'ep0_trace_u16(out+8,2)')],
        'ep0_session_capture.h': [('memcmp(input,"EP0DIA1\\0",8)', 'memcmp(input,"EP0DIA2\\0",8)'),
                                  ('memcpy(out,"EP0REL1",7)', 'memcpy(out,"EP0REL2",7)'),
                                  ('ep0_trace_u16(out+8,1)', 'ep0_trace_u16(out+8,2)')],
        'ep0_candidate_sink.h': [('#pragma once', '#pragma once\n#include "ep0_candidate_capture.h"'),
                                 ('n>6640', 'n>EP0_CAPTURE_MAX')],
        'ep0_session_sink.h': [('memcmp(bytes,"EP0REL1\\0",8)', 'memcmp(bytes,"EP0REL2\\0",8)')],
        'ep0_session_file.c': [('memcmp(bytes,"EP0REL1\\0",8)', 'memcmp(bytes,"EP0REL2\\0",8)')],
    }
    for old, new in edits.get(name, []):
        source = ready.base.trace.replace(source, old, new)
    return source


def prepare(folder, label, recipe):
    shutil.copytree(SEALED / label / 'source', folder / 'source')
    changed = []
    for path in sorted((folder / 'source/uvc').iterdir()):
        if not path.is_file():
            continue
        old = path.read_text()
        new = revisions(path.name, old)
        if old != new:
            path.write_text(new)
            changed.append(str(path.relative_to(folder / 'source')))
    header = folder / 'source/uvc/ep0_candidate_recipe.h'
    header.write_text('static const uint8_t ep0CandidateRecipe[32]={' +
                      ','.join(str(v) for v in bytes.fromhex(recipe)) + '};\n')
    changed.append(str(header.relative_to(folder / 'source')))
    return sorted(changed)


def compile_arm(folder, commands, old):
    result = linked.oldbuild.candidate.compile_elf(folder, commands)
    result['delta_from_v1'] = {key: result['sections'][key] - old['sections'][key]
                              for key in ('text', 'data', 'bss')}
    strict = []
    for command in list(commands):
        if '-c' not in command:
            continue
        source = Path(command[command.index('-c') + 1])
        if not source.is_relative_to(folder / 'source'):
            continue
        flags = [v for v in command[1:command.index('-c')] if v != '-fstack-usage']
        check = [command[0], *flags, '-Wformat=2', '-fsyntax-only', str(source)]
        ready.base.owner.command(check)
        commands.append(check)
        strict.append(str(source))
    if len(strict) != 13:
        raise ValueError('Expected 13 strict format units')
    result['strict_format_units'] = len(strict)
    objdump = ['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump', '-d', str(folder / 'full.elf')]
    text = ready.base.owner.command(objdump)
    commands.append(objdump)
    (folder / 'disassembly.txt').write_text(text)
    logger = linked.linked_logger((folder / 'full.elf').read_bytes(), text)
    if not logger['size_failure_skips_write'] or not logger['signed_clamp_511_verified']:
        raise ValueError('Final V2 logger lost the protected contract')
    result['logger_machine'] = logger
    metadata = linked.oldbuild.boundaries.elf_metadata((folder / 'full.elf').read_bytes())
    # Caller binds the recipe below, after obtaining section metadata.
    result['readonly_ranges'] = [{k: section[k] for k in ('name', 'offset', 'size')}
        for section in metadata['sections'] if section['flags'] & 2 and not section['flags'] & 1 and not section['flags'] & 4]
    symbols = (folder / 'symbols.txt').read_text()
    objects = {}
    for name in ('storage', 'exported', 'diagnostic_bytes', 'session_bytes', 'session_work', 'spans'):
        matches = [line.split() for line in symbols.splitlines()
                   if re.search(r'\s' + name + r'$', line) and 'OBJECT' in line]
        if len(matches) != 1:
            raise ValueError('Ambiguous final storage symbol: ' + name)
        objects[name] = dict(address=int(matches[0][1],16), bytes=int(matches[0][2]))
    expected = dict(exported=13040, diagnostic_bytes=13056, session_bytes=14368, session_work=14176, spans=768)
    for name, size in expected.items():
        if objects[name]['bytes'] != size:
            raise ValueError('Final V2 storage size mismatch: ' + name)
    result['linked_storage_objects'] = objects
    return result


def matrix(output, folders, recipes, commands):
    rows = []
    scenarios = ([(n, 'healthy') for n in range(9)] + [(n, 'reconnect') for n in range(9)] +
                 [(9, 'log-prefix')] + [(0, mode) for mode in ready.MODES if mode != 'healthy'])
    for label, folder in folders.items():
        for candidate in (False, True):
            name = label + ('-candidate' if candidate else '-baseline')
            source = output / (name + '.c')
            source.write_text(ready.native_source(folder, candidate, recipes[label]))
            commands.append(ready.base.trace.compile_native(source, output / name,
                            [*FLAGS, '-I' + str(folder / 'source/uvc')]))
            for n, mode in scenarios:
                stem = f'{name}-prelude{n}-{mode}'
                normal, diagnostic = (output / (stem + suffix)
                                      for suffix in ('.ownership.bin', '.diagnostic.bin'))
                row = json.loads(ready.base.owner.command([str(output / name), mode, str(n),
                                 '1' if candidate else '0', str(normal), str(diagnostic)]))
                row.update(configuration=label, recipe_digest=recipes[label])
                decoded = None
                for path, decoder in ((normal, decode_capture), (diagnostic, decode_diagnostic)):
                    if path.exists():
                        decoded = decoder(path.read_bytes(), recipes[label])
                        path.with_suffix('.json').write_text(json.dumps(decoded, indent=2) + '\n')
                        row['requests'] = ready.summarize_trace(decoded['trace'])
                row['evidence_assessment'] = ready.assess_evidence(decoded)
                if row['dropped'] or row['invalid'] or row['bound_violations']:
                    raise ValueError('Unbounded V2 trace: ' + stem)
                rows.append(row)
    return rows


def policies(output, folder, recipe, commands):
    source = ready.native_source(folder, True, recipe)
    marker = '/* Actual frozen EP0 functions with injected services.'
    if source.count(marker) != 1:
        raise ValueError('Native matrix fixture anchor drift')
    source = source[:source.index(marker)] + (ROOT / 'tests/a23_capacity_v2_admission.c').read_text()
    path = output / 'admission-policy.c'
    path.write_text(source)
    commands.append(ready.base.trace.compile_native(path, output / 'admission-policy',
                    [*FLAGS, '-I' + str(folder / 'source/uvc')]))
    cases = [('records', n) for n in range(257)] + [('identities', n) for n in (30, 31)]
    return [json.loads(ready.base.owner.command([str(output / 'admission-policy'), kind, str(n)]))
            for kind, n in cases]


def files(output, folder, commands):
    binary = output / 'file-policies'
    source = ROOT / 'tests/a23_capacity_v2_files.c'
    commands.append(ready.base.trace.compile_native(source, binary, ['-I' + str(folder / 'source/uvc')]))
    prefix = output / 'maximum'
    sizes = json.loads(ready.base.owner.command([str(binary), 'serialize', 'ok', str(prefix)]))
    maximum = {}
    for kind, decoder in (('ownership', decode_capture), ('diagnostic', decode_diagnostic), ('session', decode_session)):
        path = Path(str(prefix) + '.' + kind + '.bin')
        decoded = decoder(path.read_bytes(), '03' + '00' * 31)
        path.with_suffix('.json').write_text(json.dumps(decoded, indent=2) + '\n')
        maximum[kind] = dict(size=path.stat().st_size, analysis=decoded)
    rows = []
    for kind in ('normal', 'diagnostic', 'session'):
        scenarios = FILE_CASES + (() if kind == 'normal' else ('video-join-error', 'audio-join-error'))
        for fault in scenarios:
            prefix = output / (kind + '-' + fault)
            row = json.loads(ready.base.owner.command([str(binary), kind, fault, str(prefix)]))
            disk = Path(str(prefix) + '.disk.bin')
            if disk.exists() and row['ok']:
                decoder = {'normal': decode_capture, 'diagnostic': decode_diagnostic, 'session': decode_session}[kind]
                decoder(disk.read_bytes(), '03' + '00' * 31)
            if disk.exists():
                row['modeled_disk_image_sha256'] = ready.sha(disk)
            rows.append(row)
    return dict(serialization=sizes, maxima=maximum, file_cases=rows, file_case_count=len(rows),
                actual_file_adapter_bodies_used=True, filesystem_services_injected=True)


def run(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Refusing existing output: ' + str(output))
    seals = [verify(path) for path in (SEALED, PRIOR, DESIGN)]
    old = json.loads((SEALED / 'audit.json').read_text())
    prior = json.loads((PRIOR / 'audit.json').read_text())
    design = json.loads((DESIGN / 'design-plan.json').read_text())
    if ready.sha(PRIOR / 'audit.json') != design['baseline_review_sha256']:
        raise ValueError('Design/baseline mismatch')
    names = list(dict.fromkeys([*prior['source_hashes'], *INPUTS]))
    inputs = {name: ready.sha(ROOT / name) for name in names}
    for name, expected in prior['source_hashes'].items():
        if inputs[name] != expected:
            raise ValueError('Readiness input drift: ' + name)
    production = {name: ready.sha(REPO / name) for name in prior['production_sources_sha256']}
    tickets = {name: ready.sha(SEALED.parent / name) for name in prior['tickets_sha256']}
    if production != prior['production_sources_sha256'] or tickets != prior['tickets_sha256']:
        raise ValueError('Production or ticket drift')
    external_paths = ['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc',
                      '/opt/devkitpro/libnx/lib/libnx.a', '/opt/devkitpro/libnx/switch.specs']
    external = {name: ready.sha(name) for name in external_paths}
    sdk = Path('/opt/devkitpro/libnx/include')
    headers = {name: ready.sha(sdk / name) for name in linked.SDK_HEADERS}
    info = dict(source_sha256=inputs, external_sha256=external, sdk_headers_sha256=headers,
                prior_manifests_sha256={str(p): ready.sha(p / 'SHA256SUMS') for p in (SEALED, PRIOR, DESIGN)},
                compiler_version=ready.base.owner.command([external_paths[0], '--version']))
    identity = digest(info)
    output.mkdir(parents=True)
    (output / 'recipe.json').write_text(json.dumps(dict(input_digest=identity, inputs=info), indent=2)+'\n')
    folders, recipes, changes, commands = {}, {}, {}, []
    for label in ready.LABELS:
        folder = output / label
        config = dict(input_digest=identity, format_version=2, trace_records=256, identity_slots=32,
                      window_ms=old['builds'][label]['window_ms'], simulation_only=True)
        recipe = digest(config)
        folders[label], recipes[label] = folder, recipe
        changes[label] = prepare(folder, label, recipe)
        (folder / 'recipe.json').write_text(json.dumps(dict(input_digest=recipe, configuration=config), indent=2)+'\n')
    cases = matrix(output, folders, recipes, commands)
    boundary = policies(output, folders['dormant'], recipes['dormant'], commands)
    file_results = files(output, folders['dormant'], commands)
    builds = {}
    for label, folder in folders.items():
        build = compile_arm(folder, commands, old['builds'][label])
        blob = (folder / 'full.elf').read_bytes()
        matches = [s['name'] for s in build['readonly_ranges']
                   if bytes.fromhex(recipes[label]) in blob[s['offset']:s['offset']+s['size']]]
        if not matches:
            raise ValueError('Recipe absent from final readonly ELF')
        build.update(runtime_recipe_digest=recipes[label], recipe_readonly_sections=matches,
                     changed_source_files=changes[label], window_boundary=ready.window_boundary((folder/'source/sysmodule/main.c').read_text()))
        builds[label] = build
    for group, expected, base in ((inputs, inputs, ROOT), (production, production, REPO), (tickets, tickets, SEALED.parent)):
        if expected != {name: ready.sha(base / name) for name in group}:
            raise ValueError('Input changed during V2 build')
    if external != {name: ready.sha(name) for name in external} or headers != {name: ready.sha(sdk/name) for name in headers}:
        raise ValueError('Toolchain drift')
    for path in (SEALED, PRIOR, DESIGN):
        verify(path)
    for name in inputs:
        target = output / 'inputs' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    result = dict(schema='A23-capacity-v2-candidate-1', source_hashes=inputs,
        production_sources_sha256=production, tickets_sha256=tickets, sealed_inputs=seals,
        recipe_digest=identity, sdk_headers_sha256=headers, external_sha256=external,
        compiler_commands=commands, builds=builds, cases=cases, matrix_case_count=len(cases),
        admission_cases=boundary, admission_case_count=len(boundary), files=file_results,
        native_execution_count=len(cases)+len(boundary)+file_results['file_case_count']+1,
        production_modified=False, prior_runtime_modified=False, prior_evidence_modified=False,
        formats_v1_modified=False, usb_accessed=False, sd_accessed=False, arm_executed=False,
        firmware_packaged=False, actual_switch_threads_executed=False, full_arm_candidate_built=True,
        full_formatter_replay_on_new_elf=False, whole_thread_stack_verified=False,
        real_stop_time_bound=False, hardware_verified=False, root_cause_confirmed=False)
    (output / 'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    (output / 'SHA256SUMS').write_text(''.join(ready.sha(path)+'  '+str(path.relative_to(output))+'\n'
        for path in sorted(output.rglob('*')) if path.is_file()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps(dict(output=str(args.output), matrix_cases=result['matrix_case_count'],
        native_executions=result['native_execution_count'],
        builds={name: {key: value[key] for key in ('object_count','sections','delta_from_v1','linked','executed')}
                for name,value in result['builds'].items()}), indent=2))


if __name__ == '__main__':
    main()
