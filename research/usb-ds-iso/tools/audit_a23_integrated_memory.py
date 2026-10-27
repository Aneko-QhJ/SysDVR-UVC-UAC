#!/usr/bin/env python3
"""Rebind new linked ELFs and replay formatter/SDK helpers together; no device access."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import audit_a23_format_loop as formats
import audit_a23_memory_log_guard as sdk_audit
import build_a23_log_guard_candidate as candidate
import analyze_a23_integrated_memory as model
from workflows.artifacts import verify

ROOT, REPO, base = candidate.ROOT, candidate.REPO, candidate.base
ELFS = candidate.SEALED.parent/'A23-log-guard-candidate-review-20261015'
SEALED = candidate.SEALED.parent/'A23-format-loop-review-20261015'
INPUTS = ('tools/analyze_a23_integrated_memory.py', 'tools/audit_a23_integrated_memory.py',
          'tests/test_a23_integrated_memory.py')
STRING_OFFSETS = (1, 15, 31, 4095)


def profiles(blob, text, catalog):
    functions, metadata, binding, literals = formats.prior.build_inputs(blob, text, catalog)
    oracle = formats.NativeOracle()
    rows, oracles = [], []
    for item in catalog:
        offsets = (0, *STRING_OFFSETS) if any(c['kind'] == 's' for c in item['conversions']) else (0,)
        for scenario in formats.SCENARIOS:
            values = formats.values_for(item, scenario)
            required, expected = oracle.format(item, values)
            oracle_id = len(oracles)
            oracles.append(dict(case=item['case'], scenario=scenario, required=required,
                                full_text=expected.decode('ascii'),
                                argument_values=[v.decode('ascii') if isinstance(v, bytes) else v for v in values],
                                typed_arguments=[dict(kind=c['kind'], length=c['length']) for c in item['conversions']]))
            for offset in offsets:
                for capacity in formats.CAPACITIES:
                    for abi in ('register', 'stack'):
                        machine = model.IntegratedMachine(functions, blob, metadata, literals[item['format']], values,
                                                          capacity=capacity, abi=abi, string_offset=offset)
                        row = machine.run_full()
                        formats.check_result(machine, row, item, values, required, expected, abi, capacity)
                        assert row['helper_calls'] and not any(c.get('modeled') for c in row['calls'])
                        assert all(h['instruction_count'] > 0 and h['stack_restored'] for h in row['helper_calls'])
                        row.update(case=item['case'], scenario=scenario, capacity=capacity, abi=abi,
                                   string_offset=offset, native_oracle_id=oracle_id)
                        rows.append(formats.compact(row, scenario == 'limits' and capacity == 512 and abi == 'register' and offset == 0))
    controls = []
    item = next(r for r in catalog if r['conversions'])

    def reject(machine, phrase, outcome):
        try:
            machine.run_full()
        except model.sdk.fmt.scan.ScanError as error:
            assert phrase in str(error), str(error)
            controls.append(dict(outcome=outcome, reason=str(error), at=machine.pc))
        else:
            raise AssertionError('Expected integrated model rejection: '+outcome)

    def machine(**kwargs):
        return model.IntegratedMachine(functions, blob, metadata, literals[item['format']], formats.values_for(item, 'limits'), **kwargs)

    fault = machine()
    reset = fault.start+0x1fc
    assert fault.code[reset] == ('mov', 'w3, #0x0')
    fault.code[reset] = ('mov', 'w3, #0x1')
    reject(fault, 'get_arg', 'position-reset-fault')
    reject(machine(tls_magic=0), 'diagAbortWithResult', 'invalid-tls-frontier')
    alternate = 0x620000
    fault = machine(thread_locale=alternate)
    raw = model.sdk.fmt.scan.parser.fmt.data_at(blob, metadata, metadata['locale']['global_locale_address'], 656)
    for i, byte in enumerate(raw):
        fault.store(alternate+i, byte, 1)
    fault.store(alternate+464, 0, 8)
    reject(fault, 'Unknown locale callback', 'unknown-locale-callback')
    serial = next(r for r in catalog if any(c['kind'] == 's' and c['argument'] == 'g_serialNumber' for c in r['conversions']))
    fault = model.IntegratedMachine(functions, blob, metadata, literals[serial['format']], formats.values_for(serial, 'zero'))
    pointer = fault.string_objects[0]['pointer']
    del fault.mem[pointer+1]
    reject(fault, 'Uninitialized', 'missing-string-page-byte')
    try:
        machine().run_full(budget=1)
    except model.sdk.fmt.LoopError as error:
        controls.append(dict(outcome='instruction-budget', reason=str(error)))
    else:
        raise AssertionError('Integrated instruction budget bypassed')
    try:
        model.sdk.MemoryMachine(functions, blob, metadata, literals[item['format']], 'memset', 192, byte=0).run_helper()
    except model.sdk.MemoryError as error:
        assert 'DCZID/ZVA' in str(error)
        controls.append(dict(outcome='large-memset-architectural-frontier', reason=str(error)))
    else:
        raise AssertionError('Unmodeled DCZID silently accepted')
    helpers = [h for row in rows for h in row['helper_calls']]
    return dict(elf_sha256=hashlib.sha256(blob).hexdigest(), literal_binding=binding,
                function_sha256={f['name']: model.sdk.fmt.scan.parser.arg.elf.function_digest(f)
                                 for f in functions.values() if f['name'] in model.IntegratedMachine.ALLOWED},
                dispatch=metadata['dispatch'], locale=metadata['locale'], profiles=rows, native_oracles=oracles,
                controls=controls, profile_total=len(rows), fetch_total=sum(len(r['fetches']) for r in rows),
                helper_calls=len(helpers), helper_counts={n: sum(h['name'] == n for h in helpers) for n in model.IntegratedMachine.HELPERS},
                strlen_max_read_before=max(h.get('read_before_string', 0) for h in helpers),
                strlen_max_read_after_nul=max(h.get('read_after_nul', 0) for h in helpers),
                observed_stack_bytes=sorted({r['observed_stack_bytes'] for r in rows}),
                memset_lengths=sorted({h['length'] for h in helpers if h['name'] == 'memset'}),
                memory_helper_abstract_models_used=False, helper_state_reinjected=False,
                mapped_string_pages_injected=True, readonly_elf_mapping_and_initial_locale_assumed=True,
                full_symbolic_proof=False, get_arg_globally_unreachable_proven=False,
                formatter_cfg_pruned=False, whole_thread_stack_verified=False)


def run(output):
    verify(ELFS)
    verify(SEALED)
    old = json.loads((ELFS/'audit.json').read_text())
    hashes = {n: base.ep0.sha(ROOT/n) for n in dict.fromkeys([*old['source_hashes'], *INPUTS])}
    assert all(hashes[n] == h for n, h in old['source_hashes'].items())
    production = {n: base.ep0.sha(REPO/n) for n in old['production_sources_sha256']}
    tickets = {n: base.ep0.sha(ELFS.parent/n) for n in old['tickets_sha256']}
    assert production == old['production_sources_sha256'] and tickets == old['tickets_sha256']
    assert base.owner.source_audit() == old['source_audit']
    catalog = json.loads((SEALED/'linked-catalog.json').read_text())
    (output/'linked-catalog.json').write_text(json.dumps(catalog, indent=2)+'\n')
    data, standalone = {}, {}
    for label in candidate.LABELS:
        folder = output/label
        folder.mkdir()
        blob, text = (ELFS/label/'full.elf').read_bytes(), (ELFS/label/'disassembly.txt').read_text()
        actual = base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump', '-d', str(ELFS/label/'full.elf')])
        normalize = lambda value: re.sub(r'^.*:\s+file format .*$', 'ELF: file format normalized-path', value, flags=re.M)
        assert normalize(text) == normalize(actual)
        logger = candidate.linked_logger(blob, text)
        assert logger == old['builds'][label]['logger_machine']
        (folder/'logger-machine.json').write_text(json.dumps(logger, indent=2)+'\n')
        data[label] = profiles(blob, text, catalog)
        (folder/'profiles.json').write_text(json.dumps(data[label], indent=2)+'\n')
        standalone[label] = sdk_audit.helper_profiles(blob, text, catalog)
        (folder/'standalone-sdk-memory.json').write_text(json.dumps(standalone[label], indent=2)+'\n')
    assert [data[label]['literal_binding']['direct_sites'] for label in candidate.LABELS] == [79, 80]
    assert hashes == {n: base.ep0.sha(ROOT/n) for n in hashes}
    assert production == {n: base.ep0.sha(REPO/n) for n in production}
    assert tickets == {n: base.ep0.sha(ELFS.parent/n) for n in tickets}
    assert base.owner.source_audit() == old['source_audit']
    result = dict(schema='A23-integrated-memory-1', source_hashes=hashes, production_sources_sha256=production,
                  tickets_sha256=tickets, source_audit=old['source_audit'], sealed_inputs=[verify(ELFS), verify(SEALED)],
                  profiles={label: {k: v for k, v in row.items() if k not in ('profiles', 'native_oracles')} for label, row in data.items()},
                  standalone_helpers={label: {k: v for k, v in row.items() if k != 'profiles'} for label, row in standalone.items()},
                  linked_formats=73, linked_conversions=97,
                  formatter_profiles=sum(p['profile_total'] for p in data.values()),
                  fetch_profiles=sum(p['fetch_total'] for p in data.values()),
                  actual_helper_calls_in_model=sum(p['helper_calls'] for p in data.values()),
                  native_oracle_formats=sum(len(p['native_oracles']) for p in data.values()),
                  standalone_helper_profiles=sum(p['profile_count'] for p in standalone.values()),
                  rejection_controls=sum(len(p['controls']) for p in data.values()),
                  old_address_certificates_reused=False, final_guarded_logger_rechecked=True,
                  memory_helper_abstract_models_used=False, helper_state_reinjected=False,
                  actual_sdk_memory_helpers_executed_in_model=True, actual_sdk_helpers_executed_natively=False,
                  mapped_string_pages_injected=True, mapped_page_precondition_verified_on_device=False,
                  tls_reent_abi_values_initial_locale_and_readonly_mapping_assumed=True,
                  all_inputs_symbolically_verified=False, formatter_cfg_pruned=False, whole_thread_stack_verified=False,
                  new_arm_build=False, arm_executed=False, firmware_packaged=False,
                  production_modified=False, prior_runtime_modified=False, prior_evidence_modified=False,
                  usb_accessed=False, sd_accessed=False, hardware_verified=False, root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    sdk_audit.prior.prior.prior.seal(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    result = run(args.output)
    print(json.dumps({k: result[k] for k in ('formatter_profiles', 'fetch_profiles', 'actual_helper_calls_in_model',
                                            'native_oracle_formats', 'standalone_helper_profiles', 'rejection_controls')}, indent=2))


if __name__ == '__main__':
    main()
