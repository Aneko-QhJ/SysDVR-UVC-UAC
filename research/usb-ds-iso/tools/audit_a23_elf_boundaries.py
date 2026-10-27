#!/usr/bin/env python3
"""Read-only ELF symbol/abort review against sealed A23 candidates, no new builds."""
import argparse,json,re,shutil
from pathlib import Path
import audit_a23_thread_paths as prior
from analyze_a23_elf_boundaries import analyze,no_return_policy,build_functions
from workflows.artifacts import verify
base=prior.base;ROOT=prior.ROOT;REPO=prior.REPO
SEALED=base.ep0.PRIVATE/'analysis/A23-thread-paths-review-20261014'
ELFS=prior.SEALED
INPUTS=('tools/analyze_a23_elf_boundaries.py','tools/audit_a23_elf_boundaries.py')
HEADERS=('switch/kernel/svc.h','switch/runtime/diag.h','switch/services/fatal.h','switch/types.h')
ROOTS=(*prior.ROOTS,'armDCacheFlush','__syscall_getreent','diagAbortWithResult','fatalThrow','LogFunctionImpl','svcBreak','svcExitProcess')

def compare_readelf_functions(text,metadata):
    if "Symbol table '.symtab'" not in text:raise ValueError('readelf full table missing')
    text=text.split("Symbol table '.symtab'",1)[1];rows=[]
    for line in text.splitlines():
        m=re.match(r'^\s*\d+:\s+([0-9a-f]+)\s+(\d+)\s+FUNC\s+(LOCAL|GLOBAL|WEAK)\s+\w+\s+(\d+)\s+(.*)$',line)
        if m:rows.append(dict(name=m[5],address=int(m[1],16),size=int(m[2]),bind={'LOCAL':0,'GLOBAL':1,'WEAK':2}[m[3]],section=int(m[4])))
    native=[{k:s[k] for k in ('name','address','size','bind','section')} for s in metadata['symbols'] if s['type']==2 and 0<s['section']<len(metadata['sections'])]
    if rows!=native:raise ValueError('ELF decoder/readelf FUNC disagreement')
    return len(rows)

def read_header_snapshots(output):
    sdk=Path('/opt/devkitpro/libnx/include');headers={n:(sdk/n).read_text() for n in HEADERS}
    for n in HEADERS:
        p=output/'sdk-headers'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(sdk/n,p)
    return headers,{n:base.ep0.sha(sdk/n) for n in HEADERS}

def run(output):
    output=Path(output);verify(SEALED);verify(ELFS);old=json.loads((SEALED/'audit.json').read_text())
    inputs={n:base.ep0.sha(ROOT/n) for n in dict.fromkeys([*old['source_hashes'],*INPUTS])}
    for n,h in old['source_hashes'].items():assert inputs[n]==h,n
    production={n:base.ep0.sha(REPO/n) for n in old['production_sources_sha256']};assert production==old['production_sources_sha256']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    source=base.owner.source_audit();assert source==old['source_audit']
    headers,header_hashes=read_header_snapshots(output);commands=[];profiles={};sdk=Path('/opt/devkitpro/libnx/include')
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();elf=ELFS/label/'full.elf';blob=elf.read_bytes()
        for name,flags in (('disassembly.txt',['objdump','-d']),('symbols.txt',['readelf','-Ws']),('sections.txt',['readelf','-SW']),('elf-header.txt',['readelf','-h'])):
            command=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-'+flags[0],*flags[1:],str(elf)];text=base.owner.command(command);commands.append(command);(folder/name).write_text(text)
        text=(folder/'disassembly.txt').read_text();assert text==(ELFS/label/'disassembly.txt').read_text()
        rows=json.loads((ELFS/label/'stack-usage.json').read_text());(folder/'stack-usage.json').write_text(json.dumps(rows,indent=2)+'\n')
        certificate=old['wait_site_certificates'][label];assert base.ep0.sha(elf)==certificate['elf_sha256']
        policy=no_return_policy(blob,text,headers)
        typed=analyze(blob,text,rows,roots=ROOTS)
        contracted=analyze(blob,text,rows,policy,roots=ROOTS)
        conditional=analyze(blob,text,rows,policy,certificate,ROOTS)
        fs,metadata=build_functions(blob,text)
        oracle_count=compare_readelf_functions((folder/'symbols.txt').read_text(),metadata)
        (folder/'elf-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');(folder/'no-return-policy.json').write_text(json.dumps(policy,indent=2)+'\n')
        for name,value in (('typed-stack.json',typed),('contract-stack.json',contracted),('conditional-stack.json',conditional)):
            (folder/name).write_text(json.dumps(value,indent=2)+'\n')
        assert typed['roots']['armDCacheFlush']['user_prefix_bound_bytes']==0
        assert any('falls outside symbol range' in v for v in typed['roots']['__syscall_getreent']['unresolved'])
        assert contracted['roots']['__syscall_getreent']['user_prefix_bound_bytes']==48
        assert contracted['roots']['diagAbortWithResult']['user_prefix_bound_bytes']==32
        assert contracted['roots']['fatalThrow']['user_prefix_bound_bytes']==224
        assert contracted['roots']['svcBreak']['user_prefix_bound_bytes']==0 and not contracted['roots']['svcBreak']['sdk_no_return_contracts']
        for name in ('session_capture','Ep0SessionSaveJoined'):
            expected=352 if name=='session_capture' else 768
            assert typed['roots'][name]['user_prefix_bound_bytes']==contracted['roots'][name]['user_prefix_bound_bytes']==conditional['roots'][name]['user_prefix_bound_bytes']==expected
        for name in prior.ROOTS[4:]:
            root=conditional['roots'][name]
            assert root['whole_thread_stack_bound_bytes'] is None and root['user_prefix_bound_bytes'] is None
            assert any('_svfprintf_r:' in v and 'indirect' in v for v in root['unresolved'])
            assert not any('falls outside' in v or 'armDCacheFlush:' in v or 'waitObjects:' in v for v in root['unresolved'])
        # The only remaining full-root gaps under these explicit contracts are
        # formatting's two indirect instructions and capture's recursive edges.
        assert len(conditional['roots']['VideoStreamThread']['unresolved'])==3
        assert len(conditional['roots']['AudioStreamThread']['unresolved'])==3
        assert len(conditional['roots']['main']['unresolved'])==2
        profiles[label]=dict(elf_sha256=base.ep0.sha(elf),input_elf=str(elf),typed_stack=typed,contract_stack=contracted,conditional_stack=conditional,
            no_return_policy=policy,wait_profile_certificate=certificate,
            function_count=len(fs),readelf_function_symbols_checked=oracle_count,local_labels_merged=sum(len(f['local_labels']) for f in fs.values()),
            executable_instruction_words_compared=sum(len(f['instructions']) for f in fs.values()))
    for n,h in production.items():assert base.ep0.sha(REPO/n)==h
    for n,h in tickets.items():assert base.ep0.sha(base.ep0.PRIVATE/'analysis'/n)==h
    assert source==base.owner.source_audit() and inputs=={n:base.ep0.sha(ROOT/n) for n in inputs}
    assert header_hashes=={n:base.ep0.sha(sdk/n) for n in HEADERS};verify(SEALED);verify(ELFS)
    result=dict(schema='A23-ELF-boundaries-1',source_audit=source,source_hashes=inputs,production_sources_sha256=production,tickets_sha256=tickets,
                sealed_inputs=[verify(SEALED),verify(ELFS)],sdk_headers_sha256=header_hashes,read_only_commands=commands,profiles=profiles,
                elf64_little_endian_aarch64_decoded=True,symbol_type_and_size_checked=True,disassembly_raw_words_compared=True,
                ordinary_user_prefix_cache_flush_bytes=0,conditional_tls_user_prefix_bytes=48,conditional_abort_user_prefix_bytes=32,conditional_fatal_user_prefix_bytes=224,
                formatter_indirect_targets_resolved=False,capture_recursion_bounded_in_graph=False,whole_thread_stack_verified=False,
                exception_and_kernel_stack_included=False,kernel_contract_measured=False,actual_abort_executed=False,
                sdk_no_return_contract_assumed=True,wait_profile_is_full_proof=False,new_arm_build=False,arm_executed=False,firmware_packaged=False,
                prior_runtime_modified=False,production_modified=False,prior_evidence_modified=False,usb_accessed=False,sd_accessed=False,
                actual_switch_threads_executed=False,cleanup_authorized=False,hardware_verified=False,root_cause_confirmed=False,source_authenticated=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    r=run(a.output);print(json.dumps({label:dict(functions=v['function_count'],local_labels=v['local_labels_merged'],video_unknown=v['conditional_stack']['roots']['VideoStreamThread']['unresolved']) for label,v in r['profiles'].items()},indent=2))
if __name__=='__main__':main()
