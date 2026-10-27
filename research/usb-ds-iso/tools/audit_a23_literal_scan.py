#!/usr/bin/env python3
"""Offline default-locale ASCII scan/init evidence against sealed final ELFs."""
import argparse
import hashlib
import json
from pathlib import Path
import audit_a23_parser_bridge as prior
import analyze_a23_literal_scan as scan
from workflows.artifacts import verify

ROOT, REPO, ELFS, base = prior.ROOT, prior.REPO, prior.ELFS, prior.base
SEALED=ELFS.parent/'A23-parser-bridge-review-20261015-final'
INPUTS=('tools/analyze_a23_literal_scan.py','tools/audit_a23_literal_scan.py','tests/test_a23_literal_scan.py')


def build_inputs(blob,text,catalog):
    functions,metadata=scan.parser.arg.elf.build_functions(blob,text)
    metadata['dispatch']=scan.parser.fmt.decode_dispatch(blob,text)
    metadata['locale']=scan.parser.fmt.default_locale(blob,text)
    bindings=scan.linked.linked_calls(blob,text,catalog)
    literals={value:address for site in bindings['sites'] for address,value in zip(site['format_addresses'],site['formats'])}
    assert set(literals)=={r['format'] for r in catalog}
    return functions,metadata,bindings,literals


def compact_trace(profile,full):
    trace=profile['prefix_visited']
    profile['prefix_instruction_count']=len(trace)
    profile['prefix_trace_sha256']=hashlib.sha256(json.dumps(trace,separators=(',',':')).encode()).hexdigest()
    if not full: del profile['prefix_visited']
    return profile


def profiles(blob,text,catalog):
    fs,meta,binding,literals=build_inputs(blob,text,catalog)
    rows=[]
    for item in catalog:
        first=item['conversions'][0] if item['conversions'] else None
        value=0x700000 if first and first['kind']=='s' else 0xfedcba9876543210
        for capacity in (0,1,512):
            for abi in ('register','stack'):
                machine=scan.FirstScanMachine(fs,blob,meta,literals[item['format']],capacity=capacity,abi=abi,value=value)
                row=machine.run_first()
                file=row['file_initialization']
                assert file['address']==machine.wrapper_sp+72 and file['flags']==0x208
                assert file['remaining']==max(capacity-1,0) and file['va_pointer']==machine.wrapper_sp+32
                assert file['format_pointer']==literals[item['format']] and row['cache_count_initialized']==0
                assert all(c['state']==0 and c['byte']<=127 for c in row['callbacks'])
                for callback in row['callbacks']:
                    assert callback['output_pointer']==machine.sp+316 and callback['state_pointer']==machine.sp+344
                    assert all(not (file['address']<=w['address']<file['address']+40) for w in callback.get('writes',[]))
                if first:
                    state,fetch=row['parser_state'],row['fetch']
                    kind='s' if first['kind']=='s' else first['kind']+('64' if first['length']=='ll' else '32')
                    percent=item['format'].index('%')
                    assert state==dict(path=kind,position=0,index=0,cached=0,va_pointer=machine.wrapper_sp+32,
                        percent_offset=percent,next_format_offset=percent+len(first['spec']))
                    assert fetch['result']==prior.prior.expected_value(kind,value) and not fetch['get_arg_frontier']
                    assert fetch['final_cached']==1 and fetch['next_index']==1 and fetch['stack_held_unchanged']
                    assert len(fetch['cache_writes'])==1 and len(row['callbacks'])==percent+1
                else:
                    assert row['outcome']=='literal-only-return' and row['return_value']==len(item['format']) and row['stack_restored']
                    stored=min(max(capacity-1,0),len(item['format']))
                    assert row['stored_bytes']==stored
                    if capacity:
                        assert row['output'][:stored]==list(item['format'].encode()[:stored]) and row['output'][stored]==0
                    assert len(row['callbacks'])==len(item['format'])+1
                row.update(case=item['case'],format=item['format'],abi=abi,capacity=capacity,input_value=value)
                rows.append(compact_trace(row,capacity==512 and abi=='register'))
    first=next(item for item in catalog if item['conversions']);address=literals[first['format']]
    control=scan.FirstScanMachine(fs,blob,meta,address,tls_magic=0)
    try: control.run_first()
    except scan.ScanError as e:
        assert 'diagAbortWithResult' in str(e)
        bad_tls=dict(outcome='diagnostic-frontier',reason=str(e),at=control.pc-4,calls=control.calls)
    else: raise AssertionError('Invalid TLS silently admitted')
    alternate=0x620000
    control=scan.FirstScanMachine(fs,blob,meta,address,thread_locale=alternate)
    raw=scan.parser.fmt.data_at(blob,meta,meta['locale']['global_locale_address'],656)
    for i,v in enumerate(raw): control.store(alternate+i,v,1)
    control.store(alternate+464,0,8)
    try: control.run_first()
    except scan.ScanError as e:
        assert 'Unknown locale callback' in str(e)
        bad_locale=dict(outcome='unknown-callback-frontier',reason=str(e),at=control.pc-4,calls=control.calls)
    else: raise AssertionError('Unknown locale callback silently admitted')
    named={f['name']:f for f in fs.values()}
    return dict(elf_sha256=hashlib.sha256(blob).hexdigest(),function_sha256={n:scan.parser.arg.elf.function_digest(named[n]) for n in scan.FirstScanMachine.ALLOWED},
        literal_binding=binding,dispatch=meta['dispatch'],locale=meta['locale'],profiles=rows,controls=[bad_tls,bad_locale],
        profiles_total=len(rows),first_fetch_profiles=sum(r['outcome']=='first-fetch' for r in rows),
        literal_return_profiles=sum(r['outcome']=='literal-only-return' for r in rows),
        callback_instructions_executed_in_model=True,tls_getter_instructions_executed_in_model=True,
        architectural_tls_and_reent_injected=True,caller_abi_va_and_values_injected=True,
        load_bias_zero_and_initial_global_locale_assumed=True,whole_file_lifecycle_verified=False,
        whole_thread_stack_verified=False,conversion_rendering_and_loop_executed=False,
        get_arg_globally_unreachable_proven=False,formatter_cfg_pruned=False)


def run(output):
    verify(SEALED);verify(ELFS)
    old=json.loads((SEALED/'audit.json').read_text())
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
        folder=output/label;folder.mkdir()
        blob=(ELFS/label/'full.elf').read_bytes();text=(ELFS/label/'disassembly.txt').read_text()
        assert text==base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d',str(ELFS/label/'full.elf')])
        data[label]=profiles(blob,text,catalog)
        (folder/'profiles.json').write_text(json.dumps(data[label],indent=2)+'\n')
    assert hashes=={n:base.ep0.sha(ROOT/n) for n in hashes}
    assert production=={n:base.ep0.sha(REPO/n) for n in production}
    assert tickets=={n:base.ep0.sha(ELFS.parent/n) for n in tickets} and source==base.owner.source_audit()
    result=dict(schema='A23-literal-scan-1',source_hashes=hashes,production_sources_sha256=production,tickets_sha256=tickets,source_audit=source,
        sealed_inputs=[verify(SEALED),verify(ELFS)],profiles=data,linked_formats=73,first_conversion_formats=50,literal_only_formats=23,
        instruction_profiles=876,first_fetch_profiles=600,literal_return_profiles=276,control_profiles=4,
        wrapper_file_va_copy_and_formatter_initialization_connected=True,percent_index_cache_and_file_state_injected=False,
        architectural_tls_and_reent_injected=True,default_locale_runtime_measured=False,whole_file_lifecycle_verified=False,
        get_arg_globally_unreachable_proven=False,formatter_cfg_pruned=False,whole_thread_stack_verified=False,
        full_formatter_with_conversions_executed=False,actual_sdk_memory_helpers_executed=False,
        new_arm_build=False,arm_executed=False,firmware_packaged=False,production_modified=False,prior_runtime_modified=False,
        prior_evidence_modified=False,usb_accessed=False,sd_accessed=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n');prior.seal(output)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);result=run(args.output)
    print(json.dumps({k:result[k] for k in ('instruction_profiles','first_fetch_profiles','literal_return_profiles','control_profiles')},indent=2))


if __name__=='__main__': main()
