#!/usr/bin/env python3
"""Rebind new ELF literals/FILE/dispatch/locale; instruction profiles, no device."""
import argparse,json,shutil
from pathlib import Path
import build_a23_log_candidate as prior
import audit_a23_formatter as formatter
import analyze_a23_linked_logs as linked
from workflows.artifacts import verify
base=prior.base;ROOT=prior.ROOT;REPO=prior.logs.REPO
ELFS=base.ep0.PRIVATE/'analysis/A23-log-candidate-review-20261014';CATALOG=prior.LOG_REVIEW
INPUTS=('tools/analyze_a23_linked_logs.py','tools/audit_a23_linked_logs.py')
SEQUENCES=((0,),(1,),(511,),(512,),(513,),(1024,),(1,510,1),(64,)*20,(512,3),(1024,0,1))

def replay_append(blob,text):
    fs,_=linked.elf.build_functions(blob,text);cases=[];frontiers=[]
    for flags in (0x208,0x248):
        for capacity in (0,1,511):
            for chunks in SEQUENCES:
                machine=linked.StringAppendMachine(blob,text,capacity,flags,fs);steps=[]
                for length in chunks:steps.append(machine.append(length))
                last=steps[-1];expected=min(capacity,sum(chunks))
                assert last['stored']==expected and last['remaining']==capacity-expected and last['flags']==flags
                assert all(not r['growth_frontier'] and r['result']==0 and r['stack_restored'] for r in steps)
                assert sum(r['bytes'] for r in machine.copies)==expected
                cases.append(dict(flags=flags,capacity=capacity,chunks=list(chunks),steps=steps,copies=machine.copies))
    for flags in (0x288,0x608,0x688,0x2c8,0x648,0x6c8):
        machine=linked.StringAppendMachine(blob,text,511,flags,fs);row=machine.append(512);assert row['growth_frontier'];frontiers.append(dict(flags=flags,capacity=511,length=512,profile=row))
    masks=[value for value in range(65536) if (value|0x40)&0x480!=value&0x480];assert not masks
    return dict(schema='A23-string-append-instruction-profiles-1',elf_sha256=linked.hashlib.sha256(blob).hexdigest(),function_sha256=machine.function_sha256,
        nongrowth_scenarios=len(cases),growth_frontier_scenarios=len(frontiers),cases=cases,frontiers=frontiers,error_mask_exhaustive_values=65536,
        memcpy_is_bounded_model=True,caller_input_and_file_validity_assumed=True,actual_sdk_memcpy_executed=False,allocation_executed=False,
        observed_profiles_only=True,full_symbolic_proof=False,whole_formatter_paths_pruned=False,file_flags_lifecycle_verified=False,hardware_verified=False)

def run(output):
    output=Path(output);verify(ELFS);verify(CATALOG);old=json.loads((ELFS/'audit.json').read_text());catalog=json.loads((CATALOG/'audit.json').read_text())
    names=list(dict.fromkeys([*old['source_hashes'],*INPUTS]));inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for n,h in old['source_hashes'].items():assert inputs[n]==h,n
    production={n:base.ep0.sha(REPO/n) for n in old['production_sources_sha256']};assert production==old['production_sources_sha256']
    tickets={n:base.ep0.sha(ELFS.parent/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256'];source=base.owner.source_audit();assert source==old['source_audit']
    headers=formatter.snapshot_headers(output);sdk=Path('/opt/devkitpro/libnx/include');sdk_names=('switch/kernel/svc.h','switch/runtime/diag.h','switch/services/fatal.h','switch/types.h');sdk_headers={n:(sdk/n).read_text() for n in sdk_names}
    for n in sdk_names:dest=output/'sdk-headers'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(sdk/n,dest)
    stdio=Path('/opt/devkitpro/devkitA64/aarch64-none-elf/include/stdio.h');shutil.copyfile(stdio,output/'stdio.h')
    for name,value in (('__SWR',8),('__SSTR',512),('__SMBF',128),('__SOPT',1024),('__SERR',64)):
        match=linked.re.search(r'^#define\s+'+name+r'\s+(0x[0-9a-fA-F]+)',stdio.read_text(),linked.re.M);assert match and int(match[1],16)==value
    profiles={};commands=[]
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();input_folder=ELFS/label;elf=input_folder/'full.elf';blob=elf.read_bytes();text=(input_folder/'disassembly.txt').read_text()
        command=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d',str(elf)];assert text==base.owner.command(command);commands.append(command);(folder/'disassembly.txt').write_text(text)
        rows=catalog['profiles'][label]['reviewed_catalog'];binding=linked.linked_calls(blob,text,rows);state=linked.file_state(blob,text);append=replay_append(blob,text)
        dispatch=linked.fmt.decode_dispatch(blob,text);locale=linked.fmt.default_locale(blob,text)
        command=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-readelf','-rW',str(elf)];relocations=base.owner.command(command);commands.append(command);(folder/'relocations.txt').write_text(relocations)
        assert formatter.relocation_oracle(relocations)==locale['relative_relocation_locations']
        cases=[dict(character=c,target=linked.fmt.select_dispatch(dispatch,c)) for c in range(256)]
        policy=linked.elf.no_return_policy(blob,text,sdk_headers);wait=prior.paths.certificate(text,old['wait_audit'][label]);stack_rows=json.loads((input_folder/'stack-usage.json').read_text())
        graph=linked.fmt.analyze_formatter(blob,text,stack_rows,policy,wait,formatter.ROOTS,dispatch,locale)
        assert graph['roots']['session_capture']['user_prefix_bound_bytes']==352 and graph['roots']['Ep0SessionSaveJoined']['user_prefix_bound_bytes']==768
        for name in ('main','LogFunctionImpl','VideoStreamThread','AudioStreamThread'):
            root=graph['roots'][name];assert root['user_prefix_bound_bytes'] is None and root['whole_thread_stack_bound_bytes'] is None
            assert any('get_arg:' in v for v in root['unresolved']) and any('recursive call cycle' in v for v in root['unresolved'])
        pf=next(f for f in linked.elf.build_functions(blob,text)[0].values() if f['name']=='_svfprintf_r')
        get_arg=[pc for pc,op,arg in pf['instructions'] if op=='bl' and arg.endswith('<get_arg>')]
        profile=dict(elf_sha256=base.ep0.sha(elf),linked_calls=binding,file_state=state,append_profiles=append,dispatch=dispatch,default_locale=locale,
            dispatch_byte_cases=cases,no_return_policy=policy,wait_site_certificate=wait,conditional_stack=graph,get_arg_direct_call_sites=get_arg,
            get_arg_unreachable_for_catalog_proven=False)
        for name,data in profile.items():
            if isinstance(data,(dict,list)):(folder/(name.replace('_','-')+'.json')).write_text(json.dumps(data,indent=2)+'\n')
        profiles[label]=profile
    assert production=={n:base.ep0.sha(REPO/n) for n in production} and source==base.owner.source_audit() and tickets=={n:base.ep0.sha(ELFS.parent/n) for n in tickets}
    assert inputs=={n:base.ep0.sha(ROOT/n) for n in inputs};verify(ELFS);verify(CATALOG)
    result=dict(schema='A23-linked-logs-1',source_audit=source,source_hashes=inputs,production_sources_sha256=production,tickets_sha256=tickets,sealed_inputs=[verify(ELFS),verify(CATALOG)],
        newlib_headers_sha256=headers,sdk_headers_sha256={n:base.ep0.sha(sdk/n) for n in sdk_names},stdio_header_sha256=base.ep0.sha(stdio),commands=commands,profiles=profiles,
        all_direct_log_call_sites_bound=True,formatter_local_error_mask_preservation_verified=True,string_append_instruction_profiles=True,
        get_arg_unreachable_for_catalog_proven=False,indirect_log_invocations_excluded=False,file_flags_lifecycle_verified=False,formatter_cfg_pruned=False,
        full_symbolic_proof=False,thread_tls_lifecycle_verified=False,whole_thread_stack_verified=False,actual_recursion_observed=False,
        production_modified=False,prior_runtime_modified=False,prior_evidence_modified=False,new_arm_build=False,arm_executed=False,firmware_packaged=False,
        usb_accessed=False,sd_accessed=False,actual_switch_threads_executed=False,cleanup_authorized=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n');(output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False);result=run(args.output)
    print(json.dumps({label:dict(sites=p['linked_calls']['direct_sites'],unique=p['linked_calls']['unique_linked_formats'],catalog_only=p['linked_calls']['catalog_only_formats'],append=p['append_profiles']['nongrowth_scenarios'],main_unknowns=len(p['conditional_stack']['roots']['main']['unresolved'])) for label,p in result['profiles'].items()},indent=2))
if __name__=='__main__':main()
