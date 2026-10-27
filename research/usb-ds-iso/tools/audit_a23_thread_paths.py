#!/usr/bin/env python3
"""Sealed wait-site profiles and actual capture retry/race checks; offline only."""
import argparse,hashlib,json,os,re,shutil,subprocess
from pathlib import Path
import build_a23_wait_path_candidate as prior
from analyze_a23_session_stack import parse_disassembly,frame,analyze,ROOTS
from model_a23_wait_machine import HandleWaitMachine
from workflows.artifacts import verify
base=prior.base;ROOT=prior.ROOT;REPO=base.ep0.REPO
SEALED=base.ep0.PRIVATE/'analysis/A23-wait-fixed-path-review-20261014'
INPUTS=('tests/a23_capture_retry_fixture.c','tools/audit_a23_thread_paths.py')
CASES=('direct-ok','transfer-error','small','init-ok','init-error','init-repeated-error','init-retry-error','cross-stream')

def digest_function(f):
    return hashlib.sha256(json.dumps(f,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def certificate(text,old):
    fs=parse_disassembly(text);named={f['name']:(a,f) for a,f in fs.items()}
    required=('eventWait','UvcDeviceProcessRequests','waitObjects','svcWaitSynchronization','svcResetSignal')
    hashes={n:digest_function(named[n][1]) for n in required}
    sites=[]
    for a,f in fs.items():
        for pc,op,arg in f['instructions']:
            if op=='bl' and re.search(r'<waitObjects>$',arg):sites.append(dict(caller=f['name'],caller_address=a,at=pc))
    assert {s['caller'] for s in sites}=={'eventWait','UvcDeviceProcessRequests'} and len(sites)==2
    for s in sites:
        n=1 if s['caller']=='eventWait' else 3
        body=named[s['caller']][1]['instructions'];by_pc={p:(op,arg) for p,op,arg in body}
        if n==1:
            assert by_pc[s['at']-12]==('mov','w2, #0x1')
            assert by_pc[s['at']-20]==('ldrb','w0, [x0, #8]')
            assert by_pc[s['at']-8]==('str','w0, [sp, #32]')
        else:
            assert by_pc[s['at']-60]==('mov','w2, #0x3')
            # Concrete Waiter.type stores from each SetupEvent.autoclear bool.
            for offset,ins in ((-32,('ldrb','w8, [x6, #28]')),(-24,('ldrb','w6, [x4, #28]')),(-20,('ldrb','w4, [x5, #28]')),
                               (-16,('str','w8, [sp, #112]')),(-8,('str','w6, [sp, #80]')),(-4,('str','w4, [sp, #96]'))):
                assert by_pc[s['at']+offset]==ins,(offset,by_pc[s['at']+offset])
        peak=224+((4*n+15)//16)*16+((48*n+15)//16)*16+16
        s.update(count=n,wait_objects_observed_peak_bytes=peak,waiter_types=[0,1],valid_event_objects_assumed=True)
    assert old['model']['profile_count']==156 and old['model']['wait_objects_one_handle_with_svc']==304
    # Extra mixed-three-event profiles execute the same sealed instructions.
    short='\n'.join(line for n in ('waitObjects','svcWaitSynchronization','svcResetSignal') for line in function_text(text,n))
    profiles=[]
    scenarios=(('ok',(0,),(0,)),('timeout',(0xea01,),(0,)),('cancel',(0xec01,0),(0,)),('reset-retry',(0,0),(0xfa01,0)))
    for mask in range(8):
        types=tuple((mask>>i)&1 for i in range(3))
        for name,results,resets in scenarios:
            row=HandleWaitMachine(short,count=3,types=types,timeout=20000000,results=results,reset_results=resets).run()
            assert row['stack_restored'] and not row['indirect_callbacks_reached'] and row['peak_user_stack_bytes']<=400
            row.update(name=name,types=list(types));profiles.append(row)
    return dict(schema='A23-wait-site-profile-certificate-1',functions_sha256=hashes,sites=sites,three_event_profiles=profiles,
                full_symbolic_proof=False,valid_event_objects_assumed=True,kernel_success_index_validity_assumed=True,
                observed_profiles_only=True,termination_bound_verified=False)

def function_text(text,name):
    lines=text.splitlines();start=next(i for i,line in enumerate(lines) if re.match(r'^[0-9a-f]+ <'+re.escape(name)+r'>:$',line))
    end=next((i for i in range(start+1,len(lines)) if re.match(r'^[0-9a-f]+ <[^>]+>:$',lines[i])),len(lines))
    return lines[start:end]

def conditional_graph(text,rows,cert):
    fs=parse_disassembly(text);named={f['name']:a for a,f in fs.items()}
    for name,h in cert['functions_sha256'].items():
        if digest_function(fs[named[name]])!=h:raise ValueError('Certificate function drift: '+name)
    if cert['full_symbolic_proof'] or not cert['observed_profiles_only']:raise ValueError('Profile cannot assert proof')
    overrides={(s['caller_address'],s['at']):s for s in cert['sites']}
    reported={r['function']:r['bytes'] for r in rows if r['kind']=='static'}
    frames={a:frame(f,fs,reported.get(f['name'])) for a,f in fs.items()}
    for (address,pc),s in overrides.items():
        matches=[e for e in frames[address]['edges'] if e['at']==pc and e['target']==named['waitObjects']]
        if len(matches)!=1:raise ValueError('Wait profile edge missing')
        if s['count'] not in (1,3) or s['wait_objects_observed_peak_bytes']!={1:304,3:400}[s['count']]:raise ValueError('Wait profile amount drift')
    def walk(address,ancestors):
        f=frames[address];name=fs[address]['name']
        if address in ancestors:return dict(known_profile_path_bytes=0,path=[],unresolved=[name+': recursive call cycle'],used_sites=[])
        unknown=[name+': '+v for v in f['unresolved']];best=f['machine_observed_frame'];path=[name];used=[]
        for edge in f['edges']:
            s=overrides.get((address,edge['at']))
            if s:
                amount=edge['held_bytes']+s['wait_objects_observed_peak_bytes'];subpath=['waitObjects[handle-profile n='+str(s['count'])+']'];used.append(s['at'])
            else:
                sub=walk(edge['target'],ancestors|{address});unknown.extend(sub['unresolved']);used.extend(sub['used_sites'])
                amount=edge['held_bytes']+sub['known_profile_path_bytes'];subpath=sub['path']
            if amount>best:best=amount;path=[name,*subpath]
        return dict(known_profile_path_bytes=best,path=path,unresolved=sorted(set(unknown)),used_sites=sorted(set(used)))
    roots={}
    for name in ROOTS:
        roots[name]=walk(named[name],set());roots[name]['stack_bound_bytes']=None
    strict=analyze(text,rows)
    return dict(schema='A23-conditional-thread-path-1',roots=roots,strict_roots=strict['roots'],
                profile_substitution_only=True,whole_thread_stack_verified=False,full_symbolic_proof=False,
                exception_and_kernel_stack_included=False,runtime_peak_measured=False,hardware_verified=False)

def native_source(control=False):
    capture=(REPO/'source/capture.c').read_text();capture=re.sub(r'^#include .*\n','',capture,flags=re.M)
    if control:
        old='    if (g_grcdBeginCalled)\n        return false;\n\n    mutexLock(&g_grcdBeginMutex);'
        assert capture.count(old)==1;capture=capture.replace(old,'    mutexLock(&g_grcdBeginMutex);')
    return '#define CAPTURE_LOCKED_CONTROL '+str(int(control))+'\n'+base.trace.replace((ROOT/'tests/a23_capture_retry_fixture.c').read_text(),'/* INSERT_CAPTURE */',capture)

def capture_audit(output,commands):
    rows=[];races=[]
    for control in (False,True):
        tag='locked-control' if control else 'actual';src=output/(tag+'-capture.c');src.write_text(native_source(control))
        for sanitizer in ('address-undefined','thread'):
            flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if sanitizer=='address-undefined' else ['-fsanitize=thread']
            binary=output/(tag+'-'+sanitizer);cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-g','-pthread',*flags,str(src),'-o',str(binary)]
            base.owner.command(cmd);commands.append(cmd)
            if sanitizer=='address-undefined':
                for case in CASES:
                    for stream in (0,1):
                        row=json.loads(base.owner.command([str(binary),case,str(stream)]));row.update(case=case,control=control);rows.append(row)
            else:
                for stream in (0,1):
                    cmd=[str(binary),'concurrent',str(stream)];p=subprocess.run(cmd,capture_output=True,text=True,timeout=20,env={**os.environ,'TSAN_OPTIONS':'halt_on_error=0:abort_on_error=0:exitcode=66'});commands.append(cmd)
                    prefix=output/(tag+'-race-'+str(stream));prefix.with_suffix('.stdout').write_text(p.stdout);prefix.with_suffix('.stderr').write_text(p.stderr)
                    if control:assert p.returncode==0 and not p.stderr,p.stderr
                    else:
                        assert p.returncode!=0 and 'WARNING: ThreadSanitizer: data race' in p.stderr and 'g_grcdBeginCalled' in p.stderr,p.stderr
                        assert 'read of size 1' in p.stderr.lower() and 'write of size 1' in p.stderr.lower()
                    row=json.loads(p.stdout);row.update(control=control,tsan_expected_race=not control,exit_code=p.returncode);races.append(row)
    before=[{k:v for k,v in r.items() if k!='control'} for r in rows if not r['control']]
    after=[{k:v for k,v in r.items() if k!='control'} for r in rows if r['control']];assert before==after
    return dict(sequential_cases_per_source=16,sequential_total_cases=len(rows),concurrent_cases=len(races),cases=rows,race_cases=races,
                actual_capture_functions_replayed=True,production_flag_unchanged=True,locked_read_control_test_only=True,
                production_parallel_reader_race_reproduced=True,actual_switch_concurrent_capture_reachability_verified=False,
                unbounded_recursion_observed=False,maximum_transfer_calls_observed=2,maximum_begin_calls_observed=1)

def run(output):
    output=Path(output);verify(SEALED);old=json.loads((SEALED/'audit.json').read_text())
    inputs={n:base.ep0.sha(ROOT/n) for n in dict.fromkeys([*old['source_hashes'],*INPUTS])}
    for n,h in old['source_hashes'].items():assert inputs[n]==h,n
    production={n:base.ep0.sha(REPO/n) for n in old['production_sources_sha256']};assert production==old['production_sources_sha256']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    assert base.owner.source_audit()==old['source_audit'];commands=[];stacks={};certs={}
    cap=capture_audit(output,commands)
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();elf=SEALED/label/'full.elf';cmd=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d',str(elf)]
        text=base.owner.command(cmd);commands.append(cmd);assert text==(SEALED/label/'disassembly.txt').read_text()
        assert base.ep0.sha(elf)==old['builds'][label]['elf_sha256'];(folder/'disassembly.txt').write_text(text)
        rows=json.loads((SEALED/label/'stack-usage.json').read_text());(folder/'stack-usage.json').write_text(json.dumps(rows,indent=2)+'\n')
        cert=certificate(text,old['wait_audit'][label]);graph=conditional_graph(text,rows,cert)
        assert not any('waitObjects:' in s for s in graph['roots']['VideoStreamThread']['unresolved'])
        assert any('recursive call cycle' in s for s in graph['roots']['VideoStreamThread']['unresolved'])
        cert['elf_sha256']=base.ep0.sha(elf);graph['elf_sha256']=cert['elf_sha256'];certs[label]=cert;stacks[label]=graph
        (folder/'wait-site-certificate.json').write_text(json.dumps(cert,indent=2)+'\n');(folder/'conditional-stack.json').write_text(json.dumps(graph,indent=2)+'\n')
    usb=(REPO/'source/uvc/uvc_device.c').read_text();init=usb.split('Result UvcDeviceInitialize(',1)[1].split('void UvcDeviceExit(',1)[0]
    assert 'memset(&g_uacCtx, 0, sizeof(g_uacCtx));' in init and '(void)_setupAudioInterfaces5x;' in init
    assert '_setupAudioInterfaces5x();' not in init and usb.count('g_uacCtx.initialized = true;')==1
    assert '_setupAudioInterfaces5x' not in {f['name'] for f in parse_disassembly(text).values()}
    reach=dict(uac_setup_disabled_in_current_candidate=True,uac_positive_initializer_not_linked=True,
               audio_capture_pruned_from_stack_graph=False,single_capture_worker_assumption_requires_valid_lifecycle=True,
               memory_corruption_and_external_calls_excluded_from_single_worker_argument=True,
               host_race_is_not_current_switch_execution_evidence=True)
    for n,h in production.items():assert base.ep0.sha(REPO/n)==h
    for n,h in tickets.items():assert base.ep0.sha(base.ep0.PRIVATE/'analysis'/n)==h
    assert inputs=={n:base.ep0.sha(ROOT/n) for n in inputs};verify(SEALED)
    result=dict(schema='A23-thread-paths-1',source_audit=old['source_audit'],source_hashes=inputs,production_sources_sha256=production,tickets_sha256=tickets,
        sealed_input=verify(SEALED),compiler_commands=commands,capture_audit=cap,wait_site_certificates=certs,conditional_stacks=stacks,current_uac_reachability=reach,
        new_wait_profiles_per_elf=32,native_sequential_checks=32,native_concurrency_checks=4,expected_tsan_reports=2,clean_control_tsan_runs=2,
        prior_runtime_modified=False,production_modified=False,prior_evidence_modified=False,new_arm_build=False,arm_executed=False,firmware_packaged=False,
        actual_switch_threads_executed=False,usb_accessed=False,sd_accessed=False,cleanup_authorized=False,
        full_symbolic_proof=False,whole_thread_stack_verified=False,real_wait_or_stop_time_bound=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    r=run(a.output);print(json.dumps({k:r[k] for k in ('native_sequential_checks','native_concurrency_checks','expected_tsan_reports','new_wait_profiles_per_elf')},indent=2))
if __name__=='__main__':main()
