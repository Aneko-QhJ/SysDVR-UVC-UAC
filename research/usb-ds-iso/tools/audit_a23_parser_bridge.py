#!/usr/bin/env python3
"""Audit conversion entry to actual fetch against existing sealed ELFs, offline."""
import argparse
import json
import re
from pathlib import Path
import audit_a23_argument_cache as prior
import analyze_a23_parser_bridge as bridge
import analyze_a23_linked_logs as linked
from workflows.artifacts import verify

ROOT, REPO, ELFS, base = prior.ROOT, prior.REPO, prior.ELFS, prior.base
SEALED = ELFS.parent / 'A23-argument-cache-review-20261014'
INPUTS = ('tools/analyze_a23_parser_bridge.py', 'tools/audit_a23_parser_bridge.py', 'tests/test_a23_parser_bridge.py')
POISONS = (0xdeadbeef, 0xffffffffffffffff)


def slot_inventory(function):
    """Direct SP accesses only; indirect aliases remain unresolved."""
    rows = []
    for pc, op, operands in function['instructions']:
        if not op.startswith(('ld', 'st')):
            continue
        match = re.search(r'\[sp(?:, #(-?(?:0x[0-9a-f]+|\d+)))?\]', operands)
        if not match:
            continue
        offset = int(match[1] or '0', 0)
        register = operands.split(',')[0].strip()
        size = 1 if op.endswith('b') else 2 if op.endswith('h') else 4 if register.startswith(('w', 's')) else 16 if register.startswith(('q', 'v')) else 8
        if op in ('ldp', 'stp'):
            size *= 2
        if offset < 140 and offset + size > 136:
            rows.append(dict(at=pc, operation=op, operands=operands, offset=offset, bytes=size,
                             kind='write' if op.startswith('st') else 'read'))
    return dict(direct_accesses=rows, indirect_aliases_resolved=False,
                whole_function_slot_liveness_verified=False)


def replay(blob, text, catalog):
    fs, meta = bridge.arg.elf.build_functions(blob, text)
    dispatch = bridge.fmt.decode_dispatch(blob, text)
    certificate = bridge.arg.certificate(blob, text)
    function = next(f for f in fs.values() if f['name'] == '_svfprintf_r')
    paths = {name: dict(entry=function['start'] + p[0], stop=function['start'] + p[1]) for name, p in bridge.PATHS.items()}
    rows = []
    for item in catalog:
        matches = list(re.finditer(r'%[0 #+\-]*\d*(?:ll)?[dsux]', item['format']))
        if [m[0] for m in matches] != [c['spec'] for c in item['conversions']]:
            raise bridge.BridgeError('Independent literal conversion count mismatch')
        for index, (match, conversion) in enumerate(zip(matches, item['conversions'])):
            kind = 's' if conversion['kind'] == 's' else conversion['kind'] + ('64' if conversion['length'] == 'll' else '32')
            for abi in ('register', 'stack'):
                for poison in POISONS:
                    value = 0x700000 if kind == 's' else 0xfedcba9876543210
                    model = bridge.ConversionMachine(fs, blob, meta, match[0], index=index,
                                                     abi=abi, poison=poison, value=value, dispatch=dispatch)
                    row = model.bridge()
                    state, fetch = row['parser_state'], row['fetch']
                    assert state['path'] == kind and state['position'] == 0 and state['index'] == index and state['positional_index'] == index
                    assert state['cached'] == index and state['va_pointer'] == model.va and state['width'] == conversion['width']
                    assert state['next_format_offset'] == len(match[0])
                    assert fetch['result'] == prior.expected_value(kind, value) and not fetch['get_arg_frontier']
                    assert fetch['final_cached'] == index + 1 and fetch['next_index'] == index + 1 and fetch['stack_restored']
                    writes = [e for e in row['position_slot_events'] if e['kind'] == 'write']
                    assert writes == [dict(at=certificate['conversion_position_reset'], kind='write', bytes=4, value=0)]
                    assert len(fetch['cache_writes']) == 1
                    row.update(case=item['case'], format=item['format'], percent_offset=match.start(), argument_index=index,
                               abi=abi, previous_slot_poison=poison, input_value=value)
                    rows.append(row)
    controls = []
    for spec in ('%1$d', '%32$u', '%33$u', '%0008x', '%12x', '%llx'):
        model = bridge.ConversionMachine(fs, blob, meta, spec, dispatch=dispatch)
        row = model.bridge()
        if '$' in spec and spec != '%33$u':
            assert row['parser_state']['position'] == 1 and row['fetch']['get_arg_frontier']
        elif spec == '%33$u':
            assert row['outcome'] == 'rejected-index'
        else:
            assert row['parser_state']['position'] == 0 and not row['fetch']['get_arg_frontier']
        controls.append(dict(spec=spec, profile=row))
    inventory = slot_inventory(function)
    return dict(certificate=certificate, actual_conversion_paths=paths, profiles=rows, controls=controls,
                slot_inventory=inventory, catalog_profiles=len(rows), control_profiles=len(controls),
                prior_hex_labeled_region_dispatch_character='o',
                prior_hex_labeled_region_actual_entry=dispatch['entries'][ord('o')-32]['target'],
                current_hex_region_entry=dispatch['entries'][ord('x')-32]['target'],
                hex_region_correction_required=True,
                format_to_fetch_local_state_preserved=True, full_parser_executed=False,
                percent_pointer_index_cache_and_abi_injected=True, formatter_cfg_pruned=False,
                get_arg_globally_unreachable_proven=False, whole_thread_stack_verified=False)


def seal(folder):
    (folder / 'SHA256SUMS').write_text(''.join(base.ep0.sha(p) + '  ' + str(p.relative_to(folder)) + '\n'
        for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'))


def run(output):
    verify(SEALED)
    verify(ELFS)
    old = json.loads((SEALED / 'audit.json').read_text())
    hashes = {n: base.ep0.sha(ROOT/n) for n in dict.fromkeys([*old['source_hashes'], *INPUTS])}
    assert all(hashes[n] == h for n, h in old['source_hashes'].items())
    production = {n: base.ep0.sha(REPO/n) for n in old['production_sources_sha256']}
    tickets = {n: base.ep0.sha(ELFS.parent/n) for n in old['tickets_sha256']}
    assert production == old['production_sources_sha256'] and tickets == old['tickets_sha256']
    source = base.owner.source_audit()
    assert source == old['source_audit']
    catalog = json.loads((SEALED / 'linked-catalog.json').read_text())
    (output / 'linked-catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
    profiles = {}
    for label in ('dormant', 'window-30s'):
        folder = output / label
        folder.mkdir()
        blob = (ELFS / label / 'full.elf').read_bytes()
        text = (ELFS / label / 'disassembly.txt').read_text()
        assert text == base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump', '-d', str(ELFS/label/'full.elf')])
        binding = linked.linked_calls(blob, text, catalog)
        assert {s for site in binding['sites'] for s in site['formats']} == {row['format'] for row in catalog}
        profile = replay(blob, text, catalog)
        profile['fresh_literal_binding'] = binding
        assert profile['certificate']['elf_sha256'] == old['profiles'][label]['certificate']['elf_sha256']
        (folder / 'profiles.json').write_text(json.dumps(profile, indent=2) + '\n')
        profiles[label] = profile
    assert hashes == {n: base.ep0.sha(ROOT/n) for n in hashes}
    assert production == {n: base.ep0.sha(REPO/n) for n in production}
    assert tickets == {n: base.ep0.sha(ELFS.parent/n) for n in tickets}
    assert source == base.owner.source_audit()
    result = dict(schema='A23-parser-bridge-1', source_hashes=hashes, production_sources_sha256=production,
                  tickets_sha256=tickets, source_audit=source, sealed_inputs=[verify(SEALED), verify(ELFS)],
                  profiles=profiles, linked_formats=len(catalog), linked_conversions=sum(len(r['conversions']) for r in catalog),
                  catalog_profiles=sum(p['catalog_profiles'] for p in profiles.values()),
                  control_profiles=sum(p['control_profiles'] for p in profiles.values()),
                  hex_region_correction_required=True, fetch_state_reinjected=False,
                  percent_pointer_index_cache_and_abi_injected=True, full_parser_executed=False,
                  get_arg_globally_unreachable_proven=False, formatter_cfg_pruned=False,
                  whole_function_slot_liveness_verified=False, whole_thread_stack_verified=False,
                  production_modified=False, prior_runtime_modified=False, prior_evidence_modified=False,
                  new_arm_build=False, arm_executed=False, firmware_packaged=False,
                  usb_accessed=False, sd_accessed=False, hardware_verified=False, root_cause_confirmed=False)
    (output / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    seal(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = run(args.output)
    print(json.dumps({k: result[k] for k in ('linked_formats', 'linked_conversions', 'catalog_profiles', 'control_profiles', 'hex_region_correction_required')}, indent=2))


if __name__ == '__main__':
    main()
