#!/usr/bin/env python3
"""Fixed REL1 path candidate and SDK handle-wait machine audit; no device access."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
import build_a23_session_candidate as candidate
import audit_a23_session_concurrency as concurrency
from analyze_a23_session_stack import parse_disassembly,frame,analyze
from analyze_ep0_session import decode_session
from analyze_ep0_startup import decode_startup
from model_a23_wait_machine import replay
from workflows.artifacts import verify
base=candidate.base;ROOT=candidate.ROOT;SEALED=concurrency.SEALED
CONCURRENT=base.ep0.PRIVATE/'analysis/A23-session-concurrency-review-20261014-final'
INPUTS=('device/ep0_session_path.h','device/ep0_session_fixed_file.c','tests/ep0_session_path_test.c','tools/model_a23_wait_machine.py','tools/build_a23_wait_path_candidate.py')
SDK_HEADERS=('switch/kernel/wait.h','switch/kernel/event.h','switch/kernel/svc.h','switch/types.h')
r=base.trace.replace

def fixed_native(folder,full):
    text=candidate.native_shutdown(folder,full)
    old=candidate.native_device('ep0_session_file.c')
    new=re.sub(r'#include "(ep0_[^"]+)"',r'#include "research/usb-ds-iso/device/\1"',(ROOT/'device/ep0_session_fixed_file.c').read_text())
    return r(text,old,new)

def wait_audit(disassembly):
    functions=parse_disassembly(disassembly);named={v['name']:(a,v) for a,v in functions.items()}
    events=named['eventWait'][1]['instructions'];calls=[(p,op,arg) for p,op,arg in events if op=='bl']
    assert len(calls)==1 and '<waitObjects>' in calls[0][2]
    before={p:(op,arg) for p,op,arg in events}
    assert before[calls[0][0]-12]==('mov','w2, #0x1')
    assert any(op=='ldrb' and arg=='w0, [x0, #8]' for _,op,arg in events)
    assert any(op=='str' and arg=='w0, [sp, #32]' for _,op,arg in events)
    assert frame(named['eventWait'][1],functions)['machine_observed_frame']==48
    wait=named['waitObjects'][1]['instructions'];body='\n'.join(op+' '+arg for _,op,arg in wait)
    for anchor in ('stp x29, x30, [sp, #-224]!','ubfiz x0, x1, #2, #32','mov w0, #0x30','umull x0, w1, w0',
                   'cmp w1, #0x40','and x1, x1, #0x7fffffff0','and x1, x1, #0x7ffffffff0','sub sp, sp, x1'):
        assert anchor in body,anchor
    counts=[]
    for name in ('threadWaitForExit','waitHandles'):
        a,f=named[name];data=frame(f,functions);assert data['frame_bytes'] in (32,80)
        counts.append(dict(name=name,address=a,local_frame=data['frame_bytes']))
    # No global suppression of dynamic/indirect edges: this is an explicit profile.
    model=replay(disassembly);model['event_wait_address']=named['eventWait'][0]
    sites=[]
    for a,f in functions.items():
        for pc,op,arg in f['instructions']:
            if op in ('bl','b') and re.search(r'<eventWait>$',arg):sites.append(dict(caller=f['name'],at=pc,kind=op))
    return dict(model=model,event_wait_sites=sites,join_wait=counts,
                event_validity_assumed=True,kernel_success_index_validity_assumed=True,
                scalar_count_proven_at_event_wait=True,waiter_type_0_or_1_from_valid_event=True,
                all_generic_waitable_paths_bounded=False,real_wait_or_stop_time_bound=False)

def run(output):
    output=Path(output).resolve();verify(SEALED);verify(CONCURRENT)
    old=json.loads((SEALED/'audit.json').read_text());prior=json.loads((CONCURRENT/'audit.json').read_text())
    source_audit=base.owner.source_audit();assert source_audit==prior['source_audit']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==prior['tickets_sha256']
    names=list(dict.fromkeys([*prior['source_hashes'],*INPUTS]));inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for n,h in prior['source_hashes'].items():assert inputs[n]==h,n
    production={n:base.ep0.sha(candidate.startup.startup.REPO/n) for n in candidate.startup.startup.PRODUCTION};assert production==old['production_sources_sha256']
    sdk=Path('/opt/devkitpro/libnx/include');headers={n:base.ep0.sha(sdk/n) for n in SDK_HEADERS}
    snap=output/'sdk-headers';snap.mkdir()
    for n in SDK_HEADERS:p=snap/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(sdk/n,p)
    info=dict(source_sha256=inputs,sealed_manifest_sha256=base.ep0.sha(SEALED/'SHA256SUMS'),concurrency_manifest_sha256=base.ep0.sha(CONCURRENT/'SHA256SUMS'),
        sdk_headers_sha256=headers,libnx_a_sha256=base.ep0.sha(Path('/opt/devkitpro/libnx/lib/libnx.a')),
        compiler_version=base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','--version']))
    digest=hashlib.sha256(json.dumps(info,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=digest,inputs=info),indent=2)+'\n');commands=[];builds={};stacks={};waits={}
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();shutil.copytree(SEALED/label/'source',folder/'source')
        shutil.copyfile(ROOT/'device/ep0_session_fixed_file.c',folder/'source/uvc/ep0_session_file.c')
        shutil.copyfile(ROOT/'device/ep0_session_path.h',folder/'source/uvc/ep0_session_path.h')
        config=dict(input_digest=digest,window_ms=old['builds'][label]['window_ms'],fixed_session_path_bytes=82,offline_compile_only=True)
        recipe=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (folder/'recipe.json').write_text(json.dumps(dict(input_digest=recipe,configuration=config),indent=2)+'\n')
        (folder/'source/uvc/ep0_candidate_recipe.h').write_text(candidate.startup.journal.startup.sink.bounded.recipe_header(recipe))
        builds[label]=candidate.compile_elf(folder,commands);builds[label].update(runtime_recipe_digest=recipe,window_ms=config['window_ms'])
        for field in ('text','data','bss'):builds[label].setdefault('delta_from_session_candidate',{})[field]=builds[label]['sections'][field]-old['builds'][label]['sections'][field]
        cmd=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d',str(folder/'full.elf')];disassembly=base.owner.command(cmd);commands.append(cmd);(folder/'disassembly.txt').write_text(disassembly)
        data=analyze(disassembly,json.loads((folder/'stack-usage.json').read_text()));data['elf_sha256']=builds[label]['elf_sha256'];stacks[label]=data
        (folder/'stack-analysis.json').write_text(json.dumps(data,indent=2)+'\n');waits[label]=wait_audit(disassembly)
        (folder/'wait-audit.json').write_text(json.dumps(waits[label],indent=2)+'\n')
        assert 'snprintf' not in data['roots']['Ep0SessionSaveJoined']['reachable_functions']
        assert not any('indirect' in s for s in data['roots']['Ep0SessionSaveJoined']['unresolved'])
    recipe=builds['dormant']['runtime_recipe_digest'];file=output/'startup-native.c';file.write_text(candidate.native_startup(recipe));binary=output/'startup-native'
    commands.append(base.trace.compile_native(file,binary,[]));startup_rows=[];previous={r['case']:r for r in old['startup_cases']}
    for case in candidate.STARTUP_CASES:
        path=output/('startup-'+case+'.bin');row=json.loads(base.owner.command([str(binary),case,str(path)]))
        assert row=={k:v for k,v in previous[case].items() if k not in ('session','startup_journal')}
        row['session']=decode_session(Path(str(path)+'.rel').read_bytes(),recipe)
        if path.exists():row['startup_journal']=decode_startup(path.read_bytes(),recipe)
        (output/('startup-'+case+'.json')).write_text(json.dumps(row,indent=2)+'\n');startup_rows.append(row)
    full=next(r for r in startup_rows if r['case']=='full-launch')['startup_journal']
    file=output/'shutdown-native.c';file.write_text(fixed_native(output/'dormant',full));binary=output/'shutdown-native';commands.append(base.trace.compile_native(file,binary,[]))
    limits=json.loads(base.owner.command([str(binary),'limits','adapter',str(output/'unused')]))
    shutdown=[];files=[]
    for mode,cases,key in (('shutdown',candidate.SHUTDOWN_CASES,'shutdown_cases'),('adapter',tuple('session-'+c for c in candidate.FILE_CASES),'file_cases')):
        expected={r['case']:r for r in old[key]}
        for case in cases:
            path=output/(mode+'-'+case+'.bin');row=json.loads(base.owner.command([str(binary),case,mode,str(path)]));row.update(case=case,mode=mode)
            assert row=={k:v for k,v in expected[case].items() if k not in ('session','disk_session')}
            rel=Path(str(path)+'.rel');disk=Path(str(path)+'.disk')
            if rel.exists():row['session']=decode_session(rel.read_bytes(),recipe)
            if disk.exists() and disk.read_bytes()[:8]==b'EP0REL1\0':row['disk_session']=decode_session(disk.read_bytes(),recipe) if row['session_verified'] else None
            (output/(mode+'-'+case+'.json')).write_text(json.dumps(row,indent=2)+'\n');(shutdown if mode=='shutdown' else files).append(row)
    binary=output/'path-policy';commands.append(base.trace.compile_native(ROOT/'tests/ep0_session_path_test.c',binary,[]));path_policy=json.loads(base.owner.command([str(binary)]))
    assert inputs=={n:base.ep0.sha(ROOT/n) for n in names};assert production=={n:base.ep0.sha(candidate.startup.startup.REPO/n) for n in production}
    assert tickets=={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in tickets};assert headers=={n:base.ep0.sha(sdk/n) for n in headers};verify(SEALED);verify(CONCURRENT)
    result=dict(schema='A23-wait-fixed-path-1',source_audit=source_audit,source_hashes=inputs,production_sources_sha256=production,tickets_sha256=tickets,
        sdk_headers_sha256=headers,recipe_digest=digest,compiler_commands=commands,builds=builds,stack_analysis=stacks,wait_audit=waits,
        startup_cases=startup_rows,shutdown_cases=shutdown,file_cases=files,limit_policy=limits,path_policy=path_policy,
        native_legacy_cases=91,native_path_cases=path_policy['cases'],wait_machine_profiles_per_elf=waits['dormant']['model']['profile_count'],
        native_results_and_paths_preserved=True,fixed_path_in_candidate=True,old_source_modified=False,old_runtime_modified=False,
        old_wire_modified=False,normal_sink_modified=False,main_worker_callback_modified=False,cleanup_authorized_by_path=False,
        wait_implementation_modified=False,full_arm_candidate_built=True,arm_executed=False,firmware_packaged=False,
        usb_accessed=False,sd_accessed=False,actual_switch_threads_executed=False,actual_dma_executed=False,
        full_symbolic_proof=False,whole_thread_stack_verified=False,real_wait_or_stop_time_bound=False,
        hardware_verified=False,root_cause_confirmed=False,source_authenticated=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    s=run(a.output);print(json.dumps({k:s[k] for k in ('path_policy','wait_machine_profiles_per_elf','builds')},indent=2))
if __name__=='__main__':main()
