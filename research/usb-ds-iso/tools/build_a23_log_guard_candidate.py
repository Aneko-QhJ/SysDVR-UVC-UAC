#!/usr/bin/env python3
"""Link isolated GetSize protection with new identities; never execute ARM or access devices."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
import build_a23_log_candidate as oldbuild
import audit_a23_memory_log_guard as guard
from workflows.artifacts import verify

ROOT, REPO, base = guard.ROOT, guard.REPO, guard.base
SEALED = guard.ELFS
GUARD = SEALED.parent/'A23-memory-log-guard-review-20261015'
INPUTS = ('tools/build_a23_log_guard_candidate.py', 'tests/test_a23_log_guard_candidate.py')
SDK_HEADERS = (*oldbuild.SDK_HEADERS, 'switch/result.h', 'switch/services/fs.h')
LABELS = ('dormant', 'window-30s')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def linked_logger(blob, text):
    elf = oldbuild.boundaries
    functions, metadata = elf.build_functions(blob, text)
    fn = next(f for f in functions.values() if f['name'] == 'LogFunctionImpl')
    code = {pc: (op, arg) for pc, op, arg in fn['instructions']}
    words = {pc: elf.raw_word(blob, metadata, pc) for pc in code}
    calls = {}
    for pc, (op, arg) in code.items():
        if op != 'bl':
            continue
        target, name = re.fullmatch(r'([0-9a-f]+) <([^>]+)>', arg).groups()
        target = int(target, 16)
        assert target in functions and name in functions[target]['aliases']
        assert words[pc] & 0xfc000000 == 0x94000000
        raw = words[pc] & 0x3ffffff
        if raw & 0x2000000:
            raw -= 0x4000000
        assert pc + raw*4 == target
        assert name not in calls
        calls[name] = pc
    assert set(calls) == {'vsnprintf', 'fsFsOpenFile', 'fsFileGetSize', 'fsFileWrite', 'fsFileClose'}
    fmt, opened, size, write = (calls[n] for n in ('vsnprintf', 'fsFsOpenFile', 'fsFileGetSize', 'fsFileWrite'))
    start = fn['start']
    assert code[start] == ('sub', 'sp, sp, #0x340')

    def branch(pc, bits, shift):
        raw = (words[pc] >> shift) & ((1 << bits)-1)
        if raw & (1 << (bits-1)):
            raw -= 1 << bits
        target = pc + raw*4
        assert target == int(re.search(r'([0-9a-f]+) <', code[pc][1])[1], 16)
        return target

    assert code[opened+4][0] == 'cbnz' and code[opened+4][1].startswith('w0, ')
    assert words[opened+4] & 0xff00001f == 0x35000000
    exit_pc = branch(opened+4, 19, 5)
    assert [code[exit_pc+i] for i in (0, 4, 8)] == [
        ('ldp', 'x29, x30, [sp]'), ('add', 'sp, sp, #0x340'), ('ret', '')]
    assert [(pc, op, arg) for pc, (op, arg) in code.items() if arg.startswith('sp,')] == [
        (start, 'sub', 'sp, sp, #0x340'), (exit_pc+4, 'add', 'sp, sp, #0x340')]
    assert code[fmt-12] == ('mov', 'x1, #0x200')
    assert code[fmt+4] == ('mov', 'w5, w0') and code[fmt+8] == ('cmp', 'w0, #0x0')
    assert code[fmt+12][0] == 'b.le' and words[fmt+12] & 0xff00001f == 0x5400000d
    assert branch(fmt+12, 19, 5) == exit_pc
    assert code[opened-8] == ('str', 'w5, [sp, #24]')
    assert code[size+4] == ('ldr', 'w5, [sp, #24]')
    assert not any('[sp, #24]' in arg for pc, (op, arg) in code.items() if opened-8 < pc < size+4)
    assert code[size+8][0] == 'cbz' and code[size+8][1].startswith('w0, ')
    assert words[size+8] & 0xff00001f == 0x34000000
    clamp = branch(size+8, 19, 5)
    expected = [('mov', 'w0, #0x1ff'), ('ldr', 'x1, [sp, #72]'), ('cmp', 'w5, #0x1ff'),
                ('add', 'x2, sp, #0x80'), ('csel', 'w3, w5, w0, le'), ('mov', 'w4, #0x1'),
                ('add', 'x0, sp, #0x50'), ('sxtw', 'x3, w3')]
    assert clamp + 4*len(expected) == write
    assert [code[clamp+4*i] for i in range(len(expected))] == expected
    assert code[size-4] == ('str', 'xzr, [sp, #72]')
    assert code[size-8] == ('add', 'x0, sp, #0x50') and code[size-12] == ('add', 'x1, sp, #0x48')

    def path(status):
        pc, result, events, visited = size+4, status, [], []
        while True:
            assert pc in code and pc not in visited
            visited.append(pc)
            op, arg = code[pc]
            next_pc = pc+4
            name = next((n for n, at in calls.items() if at == pc), None)
            if name:
                assert name in ('fsFileWrite', 'fsFileClose')
                events.append(name)
                result = None
            elif op == 'ret':
                break
            elif op == 'b':
                assert words[pc] & 0xfc000000 == 0x14000000
                next_pc = branch(pc, 26, 0)
            elif op == 'cbz':
                assert arg.startswith('w0, ') and result is not None
                assert words[pc] & 0xff00001f == 0x34000000
                target = branch(pc, 19, 5)
                if result == 0:
                    next_pc = target
            elif op.startswith('b.') or op in ('br', 'blr', 'cbnz', 'tbz', 'tbnz'):
                raise AssertionError('Unmodeled linked logger guard branch')
            elif arg.startswith(('w0,', 'x0,')):
                result = None
            pc = next_pc
        assert events == (['fsFileWrite', 'fsFileClose'] if status == 0 else ['fsFileClose'])
        return dict(result=status, calls=events, visited=visited)

    profiles = [path(status) for status in (0, 1, 72, 0xffffffff)]
    local = elf.frame_range(fn, functions)
    assert local['frame_bytes'] == 832 and not local['unresolved']
    return dict(elf_sha256=metadata['elf_sha256'], function_sha256=elf.function_digest(fn),
                function_start=start, function_end=fn['end'], function_bytes=fn['end']-start,
                logger_frame_bytes=832, max_write_bytes=511, calls=calls, result_paths=profiles,
                size_failure_skips_write=True, close_once_after_successful_open=True,
                nonpositive_returns_skip_filesystem=True, signed_clamp_511_verified=True,
                raw_call_targets_and_branch_words_verified=True, return_spill_preserved=True,
                sdk_abi_callee_preservation_assumed=True, vsnprintf_sdk_contract_assumed=True,
                whole_thread_stack_verified=False, arm_executed=False)


def lifecycle(output, source_folder, recipe, prior):
    candidate = oldbuild.candidate
    output.mkdir()
    commands = []
    src = output/'startup-native.c'
    src.write_text(candidate.native_startup(recipe))
    binary = output/'startup-native'
    commands.append(base.trace.compile_native(src, binary, []))
    previous = {r['case']: r for r in prior['startup_cases']}
    startup = []
    for case in candidate.STARTUP_CASES:
        path = output/('startup-'+case+'.bin')
        row = json.loads(base.owner.command([str(binary), case, str(path)]))
        assert row == {k: v for k, v in previous[case].items() if k not in ('session', 'startup_journal')}
        row['session'] = oldbuild.decode_session(Path(str(path)+'.rel').read_bytes(), recipe)
        if path.exists():
            row['startup_journal'] = oldbuild.decode_startup(path.read_bytes(), recipe)
        (output/('startup-'+case+'.json')).write_text(json.dumps(row, indent=2)+'\n')
        startup.append(row)
    full = next(r for r in startup if r['case'] == 'full-launch')['startup_journal']
    src = output/'shutdown-native.c'
    src.write_text(oldbuild.fixed_native(source_folder, full))
    binary = output/'shutdown-native'
    commands.append(base.trace.compile_native(src, binary, []))
    limits = json.loads(base.owner.command([str(binary), 'limits', 'adapter', str(output/'unused')]))
    assert limits == prior['limit_policy'] and limits['cases'] == 6
    shutdown, files = [], []
    for mode, cases, key in (('shutdown', candidate.SHUTDOWN_CASES, 'shutdown_cases'),
                             ('adapter', tuple('session-'+c for c in candidate.FILE_CASES), 'file_cases')):
        previous = {r['case']: r for r in prior[key]}
        for case in cases:
            path = output/(mode+'-'+case+'.bin')
            row = json.loads(base.owner.command([str(binary), case, mode, str(path)]))
            row.update(case=case, mode=mode)
            assert row == {k: v for k, v in previous[case].items() if k not in ('session', 'disk_session')}
            rel, disk = Path(str(path)+'.rel'), Path(str(path)+'.disk')
            if rel.exists():
                row['session'] = oldbuild.decode_session(rel.read_bytes(), recipe)
            if disk.exists() and disk.read_bytes()[:8] == b'EP0REL1\0':
                row['disk_session'] = oldbuild.decode_session(disk.read_bytes(), recipe) if row['session_verified'] else None
            (output/(mode+'-'+case+'.json')).write_text(json.dumps(row, indent=2)+'\n')
            (shutdown if mode == 'shutdown' else files).append(row)
    assert (len(startup), len(shutdown), len(files)) == (45, 20, 20)
    return dict(startup_cases=startup, shutdown_cases=shutdown, file_cases=files, limit_policy=limits,
                native_checks=91, log_is_noop=True, actual_switch_threads_executed=False), commands


def run(output):
    output = Path(output).resolve()
    verify(SEALED)
    verify(GUARD)
    old = json.loads((SEALED/'audit.json').read_text())
    previous = json.loads((GUARD/'audit.json').read_text())
    names = list(dict.fromkeys([*previous['source_hashes'], *INPUTS]))
    inputs = {n: base.ep0.sha(ROOT/n) for n in names}
    assert all(inputs[n] == h for n, h in previous['source_hashes'].items())
    production = {n: base.ep0.sha(REPO/n) for n in previous['production_sources_sha256']}
    tickets = {n: base.ep0.sha(SEALED.parent/n) for n in previous['tickets_sha256']}
    assert production == previous['production_sources_sha256'] and tickets == previous['tickets_sha256']
    assert base.owner.source_audit() == previous['source_audit']
    sdk = Path('/opt/devkitpro/libnx/include')
    headers = {n: base.ep0.sha(sdk/n) for n in SDK_HEADERS}
    for n in headers:
        target = output/'sdk-headers'/n
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sdk/n, target)
    compiler = '/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc'
    external = ['/opt/devkitpro/libnx/lib/libnx.a', '/opt/devkitpro/libnx/switch.specs', compiler]
    info = dict(source_sha256=inputs, sealed_manifest_sha256=base.ep0.sha(SEALED/'SHA256SUMS'),
                guard_manifest_sha256=base.ep0.sha(GUARD/'SHA256SUMS'), sdk_headers_sha256=headers,
                external_sha256={p: base.ep0.sha(Path(p)) for p in external},
                compiler_version=base.owner.command([compiler, '--version']))
    identity = digest(info)
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=identity, inputs=info), indent=2)+'\n')
    commands, builds, stacks, waits, cycles = [], {}, {}, {}, {}
    for label in LABELS:
        folder = output/label
        folder.mkdir()
        shutil.copytree(SEALED/label/'source', folder/'source')
        core = folder/'source/core.c'
        text = core.read_text()
        assert text.count(guard.logger_source(False)) == 1
        core.write_text(text.replace(guard.logger_source(False), guard.logger_source(True)))
        config = dict(input_digest=identity, window_ms=old['builds'][label]['window_ms'],
                      logger_write_limit=511, skip_write_on_failed_get_size=True, offline_compile_only=True)
        recipe = digest(config)
        assert recipe != old['builds'][label]['runtime_recipe_digest']
        (folder/'recipe.json').write_text(json.dumps(dict(input_digest=recipe, configuration=config), indent=2)+'\n')
        (folder/'source/uvc/ep0_candidate_recipe.h').write_text(
            oldbuild.candidate.startup.journal.startup.sink.bounded.recipe_header(recipe))
        changes = sorted(p.relative_to(SEALED/label/'source').as_posix() for p in (SEALED/label/'source').rglob('*')
                         if p.is_file() and p.read_bytes() != (folder/'source'/p.relative_to(SEALED/label/'source')).read_bytes())
        assert changes == ['core.c', 'uvc/ep0_candidate_recipe.h']
        builds[label] = oldbuild.candidate.compile_elf(folder, commands)
        builds[label].update(runtime_recipe_digest=recipe, window_ms=config['window_ms'], changed_source_files=changes)
        cmd = ['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump', '-d', str(folder/'full.elf')]
        text = base.owner.command(cmd)
        commands.append(cmd)
        (folder/'disassembly.txt').write_text(text)
        machine = linked_logger((folder/'full.elf').read_bytes(), text)
        builds[label]['logger_machine'] = machine
        (folder/'logger-machine.json').write_text(json.dumps(machine, indent=2)+'\n')
        metadata = oldbuild.boundaries.elf_metadata((folder/'full.elf').read_bytes())
        readonly = [s for s in metadata['sections'] if s['flags'] & 2 and not s['flags'] & 1 and not s['flags'] & 4]
        blob = (folder/'full.elf').read_bytes()
        matches = [s['name'] for s in readonly if bytes.fromhex(recipe) in blob[s['offset']:s['offset']+s['size']]]
        assert matches
        builds[label]['recipe_readonly_sections'] = matches
        builds[label]['delta_from_log_candidate'] = {k: builds[label]['sections'][k]-old['builds'][label]['sections'][k]
                                                     for k in ('text', 'data', 'bss')}
        stacks[label] = oldbuild.analyze(text, json.loads((folder/'stack-usage.json').read_text()))
        stacks[label]['elf_sha256'] = builds[label]['elf_sha256']
        assert stacks[label]['roots']['Ep0SessionSaveJoined']['stack_bound_bytes'] == 768
        assert stacks[label]['roots']['session_capture']['stack_bound_bytes'] == 352
        (folder/'stack-analysis.json').write_text(json.dumps(stacks[label], indent=2)+'\n')
        waits[label] = oldbuild.wait_audit(text)
        (folder/'wait-audit.json').write_text(json.dumps(waits[label], indent=2)+'\n')
        cert = oldbuild.paths.certificate(text, waits[label])
        (folder/'wait-site-certificate.json').write_text(json.dumps(cert, indent=2)+'\n')
        strict = []
        for command in commands[:]:
            if '-c' in command and Path(command[command.index('-c')+1]).is_relative_to(folder/'source'):
                flags = [f for f in command[1:command.index('-c')] if f != '-fstack-usage']
                source = command[command.index('-c')+1]
                check = [command[0], *flags, '-Wformat=2', '-fsyntax-only', source]
                base.owner.command(check)
                commands.append(check)
                strict.append(source)
        assert len(strict) == 13
        builds[label]['strict_format_units'] = len(strict)
        cycles[label], checks = lifecycle(output/(label+'-native'), folder, recipe, old)
        commands.extend(checks)
    assert builds['dormant']['runtime_recipe_digest'] != builds['window-30s']['runtime_recipe_digest']
    catalog = json.loads((guard.SEALED/'linked-catalog.json').read_text())
    native_folder = output/'logger-native'
    native_folder.mkdir()
    native = guard.native_audit(native_folder, catalog, commands)
    path_binary = output/'path-policy'
    commands.append(base.trace.compile_native(ROOT/'tests/ep0_session_path_test.c', path_binary, []))
    paths = json.loads(base.owner.command([str(path_binary)]))
    assert paths == old['path_policy']
    assert inputs == {n: base.ep0.sha(ROOT/n) for n in names}
    assert production == {n: base.ep0.sha(REPO/n) for n in production}
    assert tickets == {n: base.ep0.sha(SEALED.parent/n) for n in tickets}
    assert headers == {n: base.ep0.sha(sdk/n) for n in headers}
    assert info['external_sha256'] == {p: base.ep0.sha(Path(p)) for p in external}
    assert base.owner.source_audit() == previous['source_audit']
    seals = [verify(SEALED), verify(GUARD)]
    result = dict(schema='A23-log-guard-candidate-1', source_hashes=inputs, production_sources_sha256=production,
                  tickets_sha256=tickets, source_audit=previous['source_audit'], sealed_inputs=seals,
                  sdk_headers_sha256=headers, recipe_digest=identity, compiler_commands=commands,
                  builds=builds, stack_analysis=stacks, wait_audit=waits, lifecycle=cycles, path_policy=paths,
                  native_log_checks=native, native_lifecycle_checks=182, native_path_checks=paths['cases'],
                  native_checks=182+paths['cases']+native['total_checks'],
                  actual_logger_body_bound_to_each_candidate=True, lifecycle_harness_log_is_noop=True,
                  full_arm_candidate_built=True, logger_get_size_guard_in_linked_candidate=True,
                  production_modified=False, prior_runtime_modified=False, prior_evidence_modified=False,
                  main_worker_callback_modified=False, wait_implementation_modified=False,
                  whole_thread_stack_verified=False, full_formatter_models_replaced=False,
                  arm_executed=False, firmware_packaged=False, actual_switch_threads_executed=False,
                  usb_accessed=False, sd_accessed=False, hardware_verified=False, root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    guard.prior.prior.prior.seal(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = run(args.output)
    print(json.dumps(dict(native_checks=result['native_checks'], builds=result['builds']), indent=2))


if __name__ == '__main__':
    main()
