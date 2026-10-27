#!/usr/bin/env python3
"""Current linked format loops vs typed native snprintf; all work is offline."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import audit_a23_literal_scan as prior
import analyze_a23_format_loop as loop
from workflows.artifacts import verify

ROOT, REPO, ELFS, base=prior.ROOT,prior.REPO,prior.ELFS,prior.base
SEALED=ELFS.parent/'A23-literal-scan-review-20261015-final'
INPUTS=('tools/analyze_a23_format_loop.py','tools/audit_a23_format_loop.py','tests/test_a23_format_loop.py')
CAPACITIES=(0,1,32,512)
SCENARIOS=('zero','limits','mixed')


def values_for(item,scenario):
    values=[]
    for i,c in enumerate(item['conversions']):
        kind=c['kind'];bits=64 if c['length']=='ll' else 32
        if kind=='s':
            if c['argument']=='"1.0.0"':value=b'1.0.0'
            elif scenario=='zero':value=b''
            else:
                pattern=b'S' if scenario=='limits' else b'Ab9%/\n'
                value=(pattern*(c['max_output_bytes']+1))[:c['max_output_bytes']]
        elif scenario=='zero':value=0
        elif scenario=='limits':value=-(1<<(bits-1)) if kind=='d' else (1<<bits)-1
        elif kind=='d':value=-1 if i%2 else (1<<(bits-1))-1
        else:value=((0x1020304050607080 if bits==64 else 0x12345678)+17*i)&((1<<bits)-1)
        values.append(value)
    return values


class NativeOracle:
    def __init__(self):
        self.library=ctypes.CDLL(None)
        self.snprintf=self.library.snprintf
        self.snprintf.restype=ctypes.c_int
        self.snprintf.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_char_p]

    def format(self,item,values):
        if len(values)!=len(item['conversions']):raise ValueError('Oracle argument count mismatch')
        typed=[]
        for c,value in zip(item['conversions'],values):
            if c['kind']=='s':typed.append(ctypes.c_char_p(value))
            else:
                t=ctypes.c_int64 if c['kind']=='d' and c['length']=='ll' else ctypes.c_int32 if c['kind']=='d' else ctypes.c_uint64 if c['length']=='ll' else ctypes.c_uint32
                typed.append(t(value))
        buffer=ctypes.create_string_buffer(4096)
        required=self.snprintf(buffer,4096,item['format'].encode('ascii'),*typed)
        if required<0 or required>=4096:raise ValueError('Native oracle escaped output bound')
        text=buffer.raw[:required]
        if b'\0' in text:raise ValueError('Native oracle emitted embedded NUL')
        return required,text


def check_result(machine,row,item,values,required,text,abi,capacity):
    assert row['return_value']==required and row['stack_restored'] and row['final_file_flags']==0x208
    stored=min(required,max(capacity-1,0));assert row['stored_bytes']==stored
    assert bytes(row['output'][:stored])==text[:stored]
    if capacity:assert row['output'][stored]==0 and row['output'][stored+1:]==[0xa5]*(capacity-stored-1)
    assert row['remaining']==max(capacity-1,0)-stored and row['final_cached']==len(values)
    assert len(row['fetches'])==len(values) and len(row['resets'])==len(values)
    assert len(row['scan_entries'])==len(values)+1
    for i,fetch in enumerate(row['fetches']):
        c=item['conversions'][i];kind='s' if c['kind']=='s' else c['kind']+('64' if c['length']=='ll' else '32')
        assert (fetch['path'],fetch['index'],fetch['position'],fetch['cached_before'],fetch['cached_after'],fetch['next_index'])==(kind,i,0,i,i+1,i+1)
        assert fetch['result']==prior.prior.prior.expected_value(kind,machine.argument_words[i])
        assert len(fetch['cache_writes'])==1
    assert [r['index'] for r in row['scan_entries']]==list(range(len(values)+1))
    assert [r['cached'] for r in row['scan_entries']]==list(range(len(values)+1))
    assert row['original_gr_offs']==((-56)&0xffffffff if abi=='register' else 0)
    assert row['copied_gr_offs']==((min(-56+8*len(values),0))&0xffffffff if abi=='register' else 0)
    stack_items=max(len(values)-7,0) if abi=='register' else len(values)
    assert row['copied_stack_pointer']==machine.stack_arg+8*stack_items
    assert all(c['state']==0 for c in row['callbacks'])
    assert not any(c['name']=='get_arg' for c in row['calls'])


def compact(row,full):
    trace=row['visited'];row['instruction_count']=len(trace)
    row['trace_sha256']=hashlib.sha256(json.dumps(trace,separators=(',',':')).encode()).hexdigest()
    if not full:del row['visited']
    return row


def profiles(blob,text,catalog):
    fs,meta,binding,literals=prior.build_inputs(blob,text,catalog)
    oracle=NativeOracle();rows=[];oracles=[]
    for item in catalog:
        for scenario in SCENARIOS:
            values=values_for(item,scenario);required,expected=oracle.format(item,values)
            oracle_id=len(oracles)
            oracles.append(dict(case=item['case'],scenario=scenario,required=required,full_text=expected.decode('ascii'),
                argument_values=[v.decode('ascii') if isinstance(v,bytes) else v for v in values],
                typed_arguments=[dict(kind=c['kind'],length=c['length']) for c in item['conversions']]))
            for capacity in CAPACITIES:
                for abi in ('register','stack'):
                    machine=loop.FormatMachine(fs,blob,meta,literals[item['format']],values,capacity=capacity,abi=abi)
                    row=machine.run_full();check_result(machine,row,item,values,required,expected,abi,capacity)
                    row.update(case=item['case'],scenario=scenario,capacity=capacity,abi=abi,native_oracle_id=oracle_id)
                    rows.append(compact(row,scenario=='limits' and capacity==512 and abi=='register'))
    item=next(r for r in catalog if r['conversions']);machine=loop.FormatMachine(fs,blob,meta,literals[item['format']],values_for(item,'limits'))
    reset=machine.start+0x1fc
    assert machine.code[reset]==('mov','w3, #0x0')
    machine.code[reset]=('mov','w3, #0x1')
    try:machine.run_full()
    except loop.scan.ScanError as e:
        assert 'get_arg' in str(e)
        control=dict(reason=str(e),at=machine.pc-4,outcome='get_arg-frontier-after-position-reset-fault')
    else:raise AssertionError('Position mode fault silently bypassed helper')
    return dict(elf_sha256=hashlib.sha256(blob).hexdigest(),literal_binding=binding,
        function_sha256={f['name']:loop.scan.parser.arg.elf.function_digest(f) for f in fs.values() if f['name'] in machine.ALLOWED},
        dispatch=meta['dispatch'],locale=meta['locale'],profiles=rows,native_oracles=oracles,controls=[control],
        profile_total=len(rows),fetch_total=sum(len(r['fetches']) for r in rows),
        observed_stack_bytes=sorted({r['observed_stack_bytes'] for r in rows}),
        file_flags_preserved_for_profiles=True,parameters_and_cache_continuous_for_profiles=True,
        full_symbolic_proof=False,get_arg_globally_unreachable_proven=False,formatter_cfg_pruned=False,whole_thread_stack_verified=False)


def run(output):
    verify(SEALED);verify(ELFS);old=json.loads((SEALED/'audit.json').read_text())
    hashes={n:base.ep0.sha(ROOT/n) for n in dict.fromkeys([*old['source_hashes'],*INPUTS])}
    assert all(hashes[n]==h for n,h in old['source_hashes'].items())
    production={n:base.ep0.sha(REPO/n) for n in old['production_sources_sha256']}
    tickets={n:base.ep0.sha(ELFS.parent/n) for n in old['tickets_sha256']}
    assert production==old['production_sources_sha256'] and tickets==old['tickets_sha256']
    source=base.owner.source_audit();assert source==old['source_audit']
    catalog=json.loads((SEALED/'linked-catalog.json').read_text())
    (output/'linked-catalog.json').write_text(json.dumps(catalog,indent=2)+'\n')
    data={}
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();blob=(ELFS/label/'full.elf').read_bytes();text=(ELFS/label/'disassembly.txt').read_text()
        assert text==base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d',str(ELFS/label/'full.elf')])
        data[label]=profiles(blob,text,catalog);(folder/'profiles.json').write_text(json.dumps(data[label],indent=2)+'\n')
    assert hashes=={n:base.ep0.sha(ROOT/n) for n in hashes}
    assert production=={n:base.ep0.sha(REPO/n) for n in production}
    assert tickets=={n:base.ep0.sha(ELFS.parent/n) for n in tickets} and source==base.owner.source_audit()
    result=dict(schema='A23-format-loop-1',source_hashes=hashes,production_sources_sha256=production,tickets_sha256=tickets,source_audit=source,
        sealed_inputs=[verify(SEALED),verify(ELFS)],profiles=data,linked_formats=73,linked_conversions=97,
        instruction_profiles=sum(p['profile_total'] for p in data.values()),fetch_profiles=sum(p['fetch_total'] for p in data.values()),
        control_profiles=2,native_oracle_formats=438,native_printf_is_host_reference_only=True,
        formatter_conversion_loop_executed_in_model=True,parameters_and_cache_continuous_for_profiles=True,
        file_flags_preserved_for_profiles=True,index_cache_percent_and_file_state_reinjected=False,
        actual_sdk_memory_helpers_executed=False,architectural_tls_reent_va_values_and_strings_injected=True,
        initial_global_locale_zero_bias_and_valid_readonly_mapping_assumed=True,whole_file_lifecycle_verified=False,
        full_symbolic_proof=False,get_arg_globally_unreachable_proven=False,formatter_cfg_pruned=False,whole_thread_stack_verified=False,
        new_arm_build=False,arm_executed=False,firmware_packaged=False,production_modified=False,prior_runtime_modified=False,
        prior_evidence_modified=False,usb_accessed=False,sd_accessed=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n');prior.prior.seal(output);return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);result=run(args.output)
    print(json.dumps({k:result[k] for k in ('instruction_profiles','fetch_profiles','control_profiles','native_oracle_formats')},indent=2))


if __name__=='__main__':main()
