#!/usr/bin/env python3
"""Read-only parser/cache profiles against sealed final ELFs; no device."""
import argparse,json,shutil
from pathlib import Path
import audit_a23_linked_logs as prior
import analyze_a23_argument_cache as machine
from workflows.artifacts import verify
base=prior.base;ROOT=prior.ROOT;REPO=prior.REPO;ELFS=prior.ELFS
SEALED=ELFS.parent/'A23-linked-logs-review-20261014'
INPUTS=('tools/analyze_a23_argument_cache.py','tools/audit_a23_argument_cache.py')
TOKENS=('2x','4x','8x','12x','1$d','32$u','33$u','0008x')

def expected_value(path,value):
    if path=='d32':return ((value&0xffffffff)-(1<<32) if value&(1<<31) else value&0xffffffff)&machine.MASK
    return value&0xffffffff if path in ('u32','x32') else value&machine.MASK

def profiles(blob,text):
    fs,_=machine.elf.build_functions(blob,text);cert=machine.certificate(blob,text);rows=[]
    for path in machine.PATHS:
        configurations=[dict(index=i,abi=abi,category='catalog-index') for i in range(8) for abi in ('register','stack')]
        configurations.extend(dict(index=i,abi=abi,category='cache-limit') for i in (31,32) for abi in ('register','stack'))
        configurations.extend((dict(index=0,cached=1,category='cache-hit'),dict(index=0,cached=0,position=True,category='positional-cold'),dict(index=0,cached=1,position=True,category='positional-hit')))
        for config in configurations:
            category=config['category'];args={k:v for k,v in config.items() if k!='category'};value=0x600000 if path=='s' else 0xfedcba9876543210
            model=machine.FetchMachine(fs,path,value=value,**args);result=model.run();result.update(category=category,abi=args.get('abi','register'),position=args.get('position',False),input_value=value)
            cold=category=='positional-cold';assert result['get_arg_frontier']==cold and result['stack_restored']
            if not cold:
                assert result['result']==expected_value(path,value)
                assert result['final_cached']<=32
                if category in ('catalog-index','cache-limit'):
                    assert result['next_index']==args['index']+1 and result['final_cached']==min(args['index']+1,32)
                    assert len(result['cache_writes'])==int(args['index']<32)
                else:assert result['cache_writes']==[]
            rows.append(result)
    assert len(rows)==161
    decimal=[dict(token=token,**machine.DecimalMachine(fs,token).run()) for token in TOKENS]
    assert [r['outcome'] for r in decimal]==['width']*4+['position','position','rejected-index','width']
    return dict(certificate=cert,fetch_profiles=rows,decimal_profiles=decimal,fetch_profile_count=161,decimal_profile_count=8,
        profile_total=169,parser_entry_state_injected=True,full_parser_executed=False,get_arg_executed=False,
        parser_reaches_injected_state_proven=False,get_arg_globally_unreachable_proven=False,formatter_cfg_pruned=False,whole_thread_stack_verified=False)

def run(output):
    output=Path(output);verify(SEALED);verify(ELFS);old=json.loads((SEALED/'audit.json').read_text())
    inputs={n:base.ep0.sha(ROOT/n) for n in dict.fromkeys([*old['source_hashes'],*INPUTS])}
    for n,h in old['source_hashes'].items():assert inputs[n]==h,n
    production={n:base.ep0.sha(REPO/n) for n in old['production_sources_sha256']};assert production==old['production_sources_sha256'];source=base.owner.source_audit();assert source==old['source_audit']
    tickets={n:base.ep0.sha(ELFS.parent/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    catalog=json.loads((prior.CATALOG/'dormant/reviewed-catalog.json').read_text());covered={v for r in old['profiles']['dormant']['linked_calls']['sites'] for v in r['formats']};linked_rows=[r for r in catalog if r['format'] in covered]
    assert len(linked_rows)==73 and max(len(r['conversions']) for r in linked_rows)==8
    kinds={('s' if c['kind']=='s' else c['kind']+('64' if c['length']=='ll' else '32')) for r in linked_rows for c in r['conversions']};assert kinds<=machine.PATHS.keys()
    (output/'linked-catalog.json').write_text(json.dumps(linked_rows,indent=2)+'\n');result_profiles={};commands=[]
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();elf=ELFS/label/'full.elf';blob=elf.read_bytes();text=(ELFS/label/'disassembly.txt').read_text();cmd=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d',str(elf)];assert text==base.owner.command(cmd);commands.append(cmd);(folder/'disassembly.txt').write_text(text)
        p=profiles(blob,text);assert p['certificate']['elf_sha256']==old['profiles'][label]['elf_sha256']
        (folder/'profiles.json').write_text(json.dumps(p,indent=2)+'\n');result_profiles[label]=p
    assert inputs=={n:base.ep0.sha(ROOT/n) for n in inputs} and production=={n:base.ep0.sha(REPO/n) for n in production} and tickets=={n:base.ep0.sha(ELFS.parent/n) for n in tickets} and source==base.owner.source_audit();verify(SEALED);verify(ELFS)
    result=dict(schema='A23-argument-cache-1',source_audit=source,source_hashes=inputs,production_sources_sha256=production,tickets_sha256=tickets,sealed_inputs=[verify(SEALED),verify(ELFS)],commands=commands,
        linked_format_count=73,linked_max_arguments=8,linked_argument_fetch_kinds=sorted(kinds),linked_argument_conversions=sum(len(r['conversions']) for r in linked_rows),profiles=result_profiles,
        instruction_profiles=338,fetch_profiles=322,decimal_profiles=16,cache_entries=32,cache_stride=16,cache_bytes=512,
        sequential_cache_exhaustion_alone_reaches_get_arg=False,position_slot_global_zero_invariant_valid=False,parser_entry_state_injected=True,
        parser_reaches_injected_state_proven=False,get_arg_globally_unreachable_proven=False,full_parser_executed=False,get_arg_executed=False,formatter_cfg_pruned=False,
        whole_thread_stack_verified=False,production_modified=False,prior_runtime_modified=False,prior_evidence_modified=False,new_arm_build=False,arm_executed=False,firmware_packaged=False,
        usb_accessed=False,sd_accessed=False,actual_switch_threads_executed=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n');(output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False);a=run(args.output)
    print(json.dumps({k:a[k] for k in ('linked_max_arguments','linked_argument_fetch_kinds','instruction_profiles','fetch_profiles','decimal_profiles')},indent=2))
if __name__=='__main__':main()
