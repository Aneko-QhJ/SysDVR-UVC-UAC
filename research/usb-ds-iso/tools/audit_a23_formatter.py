#!/usr/bin/env python3
"""Formatter switch/locale frontier review; offline only, sealed candidates unchanged."""
import argparse,json,re,shutil
from pathlib import Path
import audit_a23_elf_boundaries as prior
from analyze_a23_formatter import decode_dispatch,default_locale,select_dispatch,analyze_formatter
from workflows.artifacts import verify
base=prior.base;ROOT=prior.ROOT;REPO=prior.REPO
SEALED=base.ep0.PRIVATE/'analysis/A23-elf-boundaries-review-20261014';ELFS=prior.ELFS
INPUTS=('tools/analyze_a23_formatter.py','tools/audit_a23_formatter.py')
ROOTS=(*prior.prior.ROOTS,'LogFunctionImpl','_svfprintf_r','__utf8_mbtowc')

def relocation_oracle(text):
    if "Relocation section '.relr.dyn'" not in text:raise ValueError('RELR oracle missing')
    addresses=[]
    for line in text.splitlines():
        m=re.match(r'^\d{4}:\s+[0-9a-f]{16}\s+([0-9a-f]{16})',line)
        if not m:m=re.match(r'^\s{5,}([0-9a-f]{16})(?:\s|$)',line)
        if m:addresses.append(int(m[1],16))
    if len(addresses)!=len(set(addresses)):raise ValueError('RELR oracle duplicate')
    return sorted(addresses)

def snapshot_headers(output):
    # These are provenance of the reent/locale declarations, not a proof that
    # their C offsets equal the final linked machine ABI or runtime TLS state.
    sdk=Path('/opt/devkitpro/devkitA64/aarch64-none-elf/include')
    names=('sys/reent.h','sys/_locale.h','newlib.h','sys/config.h');hashes={n:base.ep0.sha(sdk/n) for n in names}
    for n in names:
        dest=output/'newlib-headers'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(sdk/n,dest)
    assert 'struct __locale_t *_locale;' in (sdk/'sys/reent.h').read_text()
    return hashes

def run(output):
    output=Path(output);verify(SEALED);verify(ELFS);old=json.loads((SEALED/'audit.json').read_text())
    inputs={n:base.ep0.sha(ROOT/n) for n in dict.fromkeys([*old['source_hashes'],*INPUTS])}
    for n,h in old['source_hashes'].items():assert inputs[n]==h,n
    production={n:base.ep0.sha(REPO/n) for n in old['production_sources_sha256']};assert production==old['production_sources_sha256']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    source=base.owner.source_audit();assert source==old['source_audit'];headers=snapshot_headers(output);commands=[];profiles={}
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();elf=ELFS/label/'full.elf';blob=elf.read_bytes()
        for name,args in (('disassembly.txt',['objdump','-d']),('relocations.txt',['readelf','-rW']),('rodata.txt',['readelf','-x','.rodata'])):
            command=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-'+args[0],*args[1:],str(elf)];text=base.owner.command(command);commands.append(command);(folder/name).write_text(text)
        text=(folder/'disassembly.txt').read_text();assert text==(ELFS/label/'disassembly.txt').read_text()
        rows=json.loads((ELFS/label/'stack-usage.json').read_text());(folder/'stack-usage.json').write_text(json.dumps(rows,indent=2)+'\n')
        p=old['profiles'][label];assert base.ep0.sha(elf)==p['elf_sha256'];dispatch=decode_dispatch(blob,text);locale=default_locale(blob,text)
        assert len(dispatch['entries'])==91 and len(dispatch['targets'])==28 and locale['relative_relocation_count']==382
        assert relocation_oracle((folder/'relocations.txt').read_text())==locale['relative_relocation_locations']
        cases=[dict(character=c,target=select_dispatch(dispatch,c),table_used=32<=c<=122) for c in range(256)]
        for c in cases:
            assert c['target']==(dispatch['entries'][c['character']-32]['target'] if c['table_used'] else dispatch['default_target'])
        jump=analyze_formatter(blob,text,rows,p['no_return_policy'],p['wait_profile_certificate'],ROOTS,dispatch)
        conditional=analyze_formatter(blob,text,rows,p['no_return_policy'],p['wait_profile_certificate'],ROOTS,dispatch,locale)
        for kind,value in (('dispatch.json',dispatch),('default-locale.json',locale),('byte-dispatch-cases.json',cases),('jump-stack.json',jump),('default-locale-stack.json',conditional)):
            (folder/kind).write_text(json.dumps(value,indent=2)+'\n')
        for graph in (jump,conditional):
            for n,v in (('session_capture',352),('Ep0SessionSaveJoined',768),('__utf8_mbtowc',16)):assert graph['roots'][n]['user_prefix_bound_bytes']==v
            for n in ('main','LogFunctionImpl','VideoStreamThread','AudioStreamThread'):
                r=graph['roots'][n];assert r['user_prefix_bound_bytes'] is None and r['whole_thread_stack_bound_bytes'] is None
                assert not any('_svfprintf_r:' in v and 'indirect br x1' in v for v in r['unresolved'])
                assert any('_wcrtomb_r:' in v or 'get_arg:' in v for v in r['unresolved'])
                assert any('recursive call cycle' in v for v in r['unresolved'])
        for n in ('main','LogFunctionImpl','VideoStreamThread','AudioStreamThread'):
            assert any('_svfprintf_r:' in v and 'indirect blr x23' in v for v in jump['roots'][n]['unresolved'])
            assert not any('_svfprintf_r:' in v and 'indirect blr x23' in v for v in conditional['roots'][n]['unresolved'])
            assert conditional['roots'][n]['default_locale_conditions_required']
        assert not conditional['roots']['__utf8_mbtowc']['default_locale_conditions_required']
        profiles[label]=dict(input_elf=str(elf),elf_sha256=p['elf_sha256'],dispatch=dispatch,default_locale=locale,dispatch_byte_cases=cases,
                            jump_stack=jump,default_locale_stack=conditional,no_return_policy=p['no_return_policy'],wait_profile_certificate=p['wait_profile_certificate'])
    assert source==base.owner.source_audit() and inputs=={n:base.ep0.sha(ROOT/n) for n in inputs}
    assert production=={n:base.ep0.sha(REPO/n) for n in production} and tickets=={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in tickets}
    sdk=Path('/opt/devkitpro/devkitA64/aarch64-none-elf/include');assert headers=={n:base.ep0.sha(sdk/n) for n in headers};verify(SEALED);verify(ELFS)
    result=dict(schema='A23-formatter-frontier-1',source_audit=source,source_hashes=inputs,production_sources_sha256=production,tickets_sha256=tickets,sealed_inputs=[verify(SEALED),verify(ELFS)],newlib_headers_sha256=headers,
                read_only_commands=commands,profiles=profiles,dispatch_entries_per_elf=91,dispatch_targets_per_elf=28,dispatch_byte_cases_per_elf=256,relative_relocation_locations_per_elf=382,
                guarded_dispatch_resolved=True,default_locale_initial_callback='__utf8_mbtowc',default_callback_user_frame_bytes=16,
                default_locale_callback_only_conditional=True,all_indirect_targets_resolved=False,nonnull_thread_locale_resolved=False,runtime_locale_measured=False,
                new_reachable_library_gaps_retained=True,whole_thread_stack_verified=False,exception_and_kernel_stack_included=False,actual_abort_executed=False,
                actual_recursion_observed=False,format_specific_pruning=False,thread_tls_lifecycle_verified=False,new_arm_build=False,arm_executed=False,firmware_packaged=False,
                prior_runtime_modified=False,production_modified=False,prior_evidence_modified=False,usb_accessed=False,sd_accessed=False,actual_switch_threads_executed=False,
                cleanup_authorized=False,hardware_verified=False,root_cause_confirmed=False,source_authenticated=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n');(output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);r=run(a.output)
    print(json.dumps({label:dict(dispatch_targets=len(p['dispatch']['targets']),callback=p['default_locale']['initial_callback_name'],main_unknowns=len(p['default_locale_stack']['roots']['main']['unresolved']),main_known_prefix=p['default_locale_stack']['roots']['main']['known_user_prefix_bytes']) for label,p in r['profiles'].items()},indent=2))
if __name__=='__main__':main()
