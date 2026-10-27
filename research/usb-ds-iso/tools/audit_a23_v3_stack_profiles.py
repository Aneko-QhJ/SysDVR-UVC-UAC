#!/usr/bin/env python3
"""Current V3 logger and handle-wait profiles, with explicit non-proof boundaries."""
import argparse
import ast
from collections import deque
import json
from pathlib import Path
import re
import shutil
import subprocess

import build_a23_bound_receiver as storage
import analyze_a23_log_contract as contract
import analyze_a23_elf_boundaries as elf
import analyze_a23_session_stack as simple
import analyze_a23_linked_logs as linked
import audit_a23_format_loop as formats
from model_a23_wait_machine import HandleWaitMachine
from model_a23_v3_logger_stack import LoggerMachine,LoggerModelError,PathSnprintfMachine
from workflows.artifacts import verify

ROOT=storage.ROOT;REPO=storage.REPO
PARENT=ROOT/'private/analysis/A23-bound-receiver-review-20261015'
DEVICE=storage.DEVICE/'window-30s'
NEW=('tools/model_a23_v3_logger_stack.py','tools/audit_a23_v3_stack_profiles.py','tests/test_a23_v3_stack_profiles.py')
SDK_HEADERS=('switch/types.h','switch/kernel/svc.h','switch/runtime/diag.h','switch/services/fatal.h')


def dependency_sources():
    """Freeze local Python import closure as well as the prior 129 inputs."""
    old=storage.load(PARENT/'audit.json');hashes=dict(old['source_hashes']);pending=list(NEW);seen=set()
    while pending:
        name=pending.pop()
        if name in seen:continue
        seen.add(name);p=ROOT/name;hashes['research/usb-ds-iso/'+name]=storage.sha(storage.plain(p))
        if p.suffix!='.py':continue
        for node in ast.walk(ast.parse(p.read_text())):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
            for n in names:
                candidate='tools/'+n.replace('.','/')+'.py'
                if (ROOT/candidate).is_file():pending.append(candidate)
    for n,h in old['source_hashes'].items():
        if storage.sha(storage.plain(REPO/n))!=h:raise ValueError('Parent source drift: '+n)
    return dict(sorted(hashes.items()))


def catalog(output):
    audit=storage.load(storage.DEVICE/'audit.json');rows=[];commands=[];units=[]
    for original in audit['compiler_commands']:
        if not original[0].endswith('/aarch64-none-elf-gcc') or '-c' not in original:continue
        source=Path(original[original.index('-c')+1])
        if not source.is_relative_to(DEVICE/'source'):continue
        unit=source.relative_to(DEVICE/'source').as_posix();units.append(unit)
        flags=[s for s in original[1:original.index('-c')] if s!='-fstack-usage']
        cmd=[original[0],*flags,'-E','-P',str(source)];commands.append(cmd)
        raw=subprocess.check_output(cmd);dest=output/'preprocessed'/Path(unit).with_suffix('.i');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        rows.extend(contract.inventory(raw.decode(),unit))
    assert len(units)==len(set(units))==13
    for i,row in enumerate(rows):row['case']=i
    return rows,commands


def wait_profiles(text,functions):
    old=simple.parse_disassembly(text);names={v['name']:(a,v) for a,v in old.items()}
    selected=('waitObjects','svcWaitSynchronization','svcResetSignal')
    short='\n'.join(format(pc,'x')+' <'+name+'>:\n'+'\n'.join(
        format(p,'x')+': 00000000 '+op+' '+arg for p,op,arg in f['instructions'])
        for name in selected for pc,f in [names[name]])
    cases=[]
    for count in (1,3):
        for mask in range(1<<count):
            types=tuple((mask>>i)&1 for i in range(count))
            for tag,results,resets in (('ok',(0,),(0,)),('timeout',(0xea01,),(0,)),
                ('cancel-then-ok',(0xec01,0),(0,)),('reset-retry',(0,0),(0xfa01,0))):
                row=HandleWaitMachine(short,count=count,types=types,timeout=20000000,results=results,reset_results=resets).run()
                assert row['stack_restored'] and not row['indirect_callbacks_reached']
                assert row['peak_user_stack_bytes']<={1:304,3:400}[count]
                cases.append(dict(count=count,types=list(types),scenario=tag,**row))
    sites=[]
    for a,f in functions.items():
        for pc,op,arg in f['instructions']:
            if op=='bl' and arg.endswith('<waitObjects>'):
                assert f['name'] in ('eventWait','UvcDeviceProcessRequests')
                code={p:(o,v) for p,o,v in f['instructions']};count=1 if f['name']=='eventWait' else 3
                assert code[pc-(12 if count==1 else 60)]==('mov','w2, #0x'+str(count))
                offsets=((-20,'ldrb','w0, [x0, #8]'),(-8,'str','w0, [sp, #32]')) if count==1 else (
                    (-32,'ldrb','w8, [x6, #28]'),(-24,'ldrb','w6, [x4, #28]'),(-20,'ldrb','w4, [x5, #28]'),
                    (-16,'str','w8, [sp, #112]'),(-8,'str','w6, [sp, #80]'),(-4,'str','w4, [sp, #96]'))
                for delta,op_,arg_ in offsets:assert code[pc+delta]==(op_,arg_)
                sites.append(dict(caller=f['name'],caller_address=a,at=pc,count=count,observed_stack_bytes={1:304,3:400}[count]))
    assert len(sites)==2
    return dict(sites=sites,profiles=cases,profile_count=len(cases),
        functions_sha256={n:elf.function_digest(f) for f in functions.values() for n in selected if n in f['aliases']},
        svc_results_and_ticks_injected=True,valid_event_and_kernel_index_assumed=True,
        indirect_waiter_callbacks_covered=False,termination_time_bound_verified=False,full_symbolic_proof=False)


def profile_graph(blob,text,rows,policy,waits,logger_peak,path_sites):
    fs,metadata=elf.build_functions(blob,text);names={n:a for a,f in fs.items() for n in f['aliases']}
    contracts={int(a):c for a,c in policy['contracts'].items()};reported={r['function']:r['bytes'] for r in rows if r['kind']=='static'}
    frames={a:elf.frame_range(f,fs,reported.get(f['name']),contracts) for a,f in fs.items()}
    overrides={(s['caller_address'],s['at']):s for s in waits['sites']}
    path_overrides={(s['caller_address'],s['at']):s for s in path_sites}
    def walk(a,ancestors):
        if a in ancestors:return dict(bytes=0,path=[],unresolved=[fs[a]['name']+': recursive call cycle'],substitutions=[])
        if a==names['LogFunctionImpl']:
            return dict(bytes=logger_peak,path=['LogFunctionImpl[observed profiles only]'],unresolved=[],substitutions=['logger-observed-profile'])
        f=frames[a];best=f['machine_observed_frame'];path=[fs[a]['name']]
        unknown=[fs[a]['name']+': '+s for s in f['unresolved']];used=[]
        for e in f['edges']:
            if (a,e['at']) in path_overrides:
                s=path_overrides[a,e['at']];sub=dict(bytes=s['observed_stack_bytes'],path=['snprintf[hex filename profiles]'],unresolved=[],substitutions=['path-snprintf-observed-profile'])
            elif (a,e['at']) in overrides:
                w=overrides[a,e['at']];sub=dict(bytes=w['observed_stack_bytes'],path=['waitObjects[handle profiles]'],unresolved=[],substitutions=['wait-'+str(w['count'])])
            else:sub=walk(e['target'],ancestors|{a})
            unknown.extend(sub['unresolved']);used.extend(sub['substitutions'])
            amount=e['held_bytes']+sub['bytes']
            if amount>best:best=amount;path=[fs[a]['name'],*sub['path']]
        return dict(bytes=best,path=path,unresolved=sorted(set(unknown)),substitutions=sorted(set(used)))
    result={}
    assert frames[names['_EntryWrap']]['machine_observed_frame']==48
    for name in ('main','VideoStreamThread','AudioStreamThread','Ep0SessionStartupOnly','Ep0ExecutionSaveJoined',
                 'Ep0CandidateSaveCapture','Ep0CandidateSaveDiagnostic','session_capture'):
        r=walk(names[name],set());r['profile_path_estimate_bytes']=r.pop('bytes');r['whole_thread_stack_bound_bytes']=None
        r['worker_wrapper_bytes_excluded']=48 if name in ('VideoStreamThread','AudioStreamThread') else 0
        if r['worker_wrapper_bytes_excluded']:r['with_worker_wrapper_profile_estimate_bytes']=r['profile_path_estimate_bytes']+48
        result[name]=r
    return dict(schema='A23-V3-profile-composition-1',roots=result,elf_sha256=metadata['elf_sha256'],
        observed_profiles_substituted=True,profile_estimates_are_not_bounds=True,
        untested_format_values_not_covered=True,exception_and_kernel_stack_included=False,
        whole_thread_stack_verified=False,runtime_peak_measured=False)


def run(output):
    output=Path(output);storage.require(output.is_absolute() and output==output.resolve() and not output.exists(),'new canonical output required')
    seals=[verify(p) for p in (PARENT,PARENT.parent/'A23-bound-receiver-validation-20261015',storage.DEVICE)]
    parent=storage.load(PARENT/'audit.json');source_hashes=dependency_sources();record=storage.load(PARENT/'offline-record.json')
    original=storage.load(storage.DEVICE/'audit.json');external={n:storage.sha(storage.plain(Path(n),128*1024*1024)) for n in original['external_sha256']}
    assert external==original['external_sha256']
    objdump=Path('/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump');external[str(objdump)]=storage.sha(storage.plain(objdump,128*1024*1024))
    blob=storage.plain(DEVICE/'full.elf');text=storage.plain(DEVICE/'disassembly.txt').decode()
    assert storage.sha(blob)==record['device_binding']['device_elf_sha256']
    output.mkdir(parents=True)
    for name,h in source_hashes.items():
        dest=output/'source'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/name,dest);assert storage.sha(storage.plain(dest))==h
    sdk={n:storage.plain(Path('/opt/devkitpro/libnx/include')/n).decode() for n in SDK_HEADERS}
    for n,raw in sdk.items():
        dest=output/'sdk-headers'/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(raw)
    commands=[['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d',str(DEVICE/'full.elf')]]
    actual=subprocess.check_output(commands[0],text=True);assert actual==text
    rows,preprocess=catalog(output);commands.extend(preprocess)
    binding=linked.linked_calls(blob,text,rows);covered={fmt for s in binding['sites'] for fmt in s['formats']}
    reviewed={r['format']:r for r in rows if r['format'] in covered};items=list(reviewed.values())
    fs,meta=elf.build_functions(blob,text);meta['dispatch']=linked.fmt.decode_dispatch(blob,text);meta['locale']=linked.fmt.default_locale(blob,text)
    literals={fmt:a for s in binding['sites'] for a,fmt in zip(s['format_addresses'],s['formats'])}
    oracle=formats.NativeOracle();profiles=[];control_rows=[]
    for item in items:
        for scenario in formats.SCENARIOS:
            values=formats.values_for(item,scenario);required,expected=oracle.format(item,values)
            m=LoggerMachine(fs,blob,meta,literals[item['format']],values);row=m.run()
            assert row['required']==required and bytes.fromhex(row['rendered_hex'])==expected[:511]
            assert [c['name'] for c in row['fs_calls']]==list(LoggerMachine.FS)
            assert row['fs_calls'][2]['length']==min(required,511)
            row.update(case=item['case'],scenario=scenario,format=item['format'],native_required=required)
            profiles.append(row)
    item=next(r for r in items if r['conversions']);values=formats.values_for(item,'limits');address=literals[item['format']]
    for fault in ('open','size','write'):
        row=LoggerMachine(fs,blob,meta,address,values,fs_fault=fault).run();row['case']=fault;control_rows.append(row)
    row=LoggerMachine(fs,blob,meta,address,values,mounted=False).run();row['case']='unmounted';control_rows.append(row)
    for fault,kwargs,budget in (('invalid-tls',{'tls_magic':0},100000),('instruction-budget',{},1)):
        try:LoggerMachine(fs,blob,meta,address,values,**kwargs).run(budget)
        except (ValueError,KeyError) as error:control_rows.append(dict(case=fault,rejected=True,error=str(error)))
        else:raise AssertionError('Expected logger frontier rejection')
    path_sites=[];path_rows=[]
    for a,f in fs.items():
        for pc,op,arg in f['instructions']:
            if op in ('b','bl') and arg.endswith('<snprintf>'):
                addresses=linked.LiteralResolver(f).values(pc,'x2');assert len(addresses)==1
                address=next(iter(addresses));literal=linked.literal_at(blob,meta,address)
                assert literal in ('/ep0-%s.capture.bin','/ep0-%s.diagnostic.bin')
                for nonce in (b'0'*64,b'f'*64,b'0123456789abcdef'*4):
                    row=PathSnprintfMachine(fs,blob,meta,address,nonce).run()
                    assert bytes.fromhex(row['rendered_hex'])==literal.replace('%s',nonce.decode()).encode()
                    assert row['observed_user_stack_bytes']==1904
                    row.update(caller=f['name'],at=pc,nonce=nonce.decode());path_rows.append(row)
                path_sites.append(dict(caller=f['name'],caller_address=a,at=pc,format=literal,observed_stack_bytes=1904))
    assert len(path_sites)==2 and len(path_rows)==6
    waits=wait_profiles(text,fs);policy=elf.no_return_policy(blob,text,sdk)
    stack_rows=storage.load(DEVICE/'stack-usage.json')
    fs_graph=elf.analyze(blob,text,stack_rows,policy,roots=LoggerMachine.FS)
    assert all(r['user_prefix_bound_bytes'] is not None for r in fs_graph['roots'].values())
    logger_observed=max(r['observed_user_stack_bytes'] for r in profiles)
    assert logger_observed==2592
    combined=max(logger_observed,832+max(r['user_prefix_bound_bytes'] for r in fs_graph['roots'].values()))
    graph=profile_graph(blob,text,stack_rows,policy,waits,combined,path_sites)
    for name,value in (('catalog.json',rows),('linked-calls.json',binding),('logger-profiles.json',profiles),('controls.json',control_rows),
        ('wait-profiles.json',waits),('no-return-policy.json',policy),('fs-stack.json',fs_graph),('profile-composition.json',graph),
        ('commands.json',commands),('dispatch.json',meta['dispatch']),('locale.json',meta['locale']),
        ('path-snprintf.json',dict(sites=path_sites,profiles=path_rows))):storage.write(output/name,value)
    for n,h in source_hashes.items():assert storage.sha(storage.plain(REPO/n))==h,n
    for n,h in parent['production_sources_sha256'].items():assert storage.sha(storage.plain(REPO/n))==h,n
    for n,h in parent['tickets_sha256'].items():assert storage.sha(storage.plain(PARENT.parent/n))==h,n
    for n,h in external.items():assert storage.sha(storage.plain(Path(n),128*1024*1024))==h,n
    for n,raw in sdk.items():assert storage.plain(Path('/opt/devkitpro/libnx/include')/n).decode()==raw,n
    for entry in seals:verify(entry['folder'])
    result=dict(schema='A23-V3-stack-profiles-review-1',source_hashes=source_hashes,sealed_inputs=seals,
        production_sources_sha256=parent['production_sources_sha256'],tickets_sha256=parent['tickets_sha256'],
        elf_sha256=storage.sha(blob),runtime_recipe_sha256=record['recipe_sha256'],device_binding_sha256=record['device_binding_sha256'],
        sdk_headers_sha256={n:storage.sha(v.encode()) for n,v in sdk.items()},external_sha256=external,
        preprocessed_units=13,preprocessed_log_calls=len(rows),linked_log_sites=binding['direct_sites'],linked_formats=len(items),
        linked_conversions=sum(len(i['conversions']) for i in items),logger_profile_count=len(profiles),
        logger_observed_user_stack_bytes=logger_observed,logger_fs_user_profile_envelope_bytes=combined,
        wait_profile_count=waits['profile_count'],control_count=len(control_rows),
        path_snprintf_sites=len(path_sites),path_snprintf_profiles=len(path_rows),path_snprintf_observed_stack_bytes=1904,
        profiles_are_not_full_input_proofs=True,fs_results_injected=True,old_address_certificates_reused=False,
        zero_load_bias_default_locale_readonly_and_valid_string_mapping_assumed=True,
        nonlogger_snprintf_observed_profiles_only=True,synchronous_log_latency_bound_verified=False,whole_thread_stack_verified=False,
        actual_arm_executed=False,device_modified=False,new_device_elf_built=False,native_sdk_calls=0,usb_requests=0,sd_accesses=0,
        attempt_issued=False,hardware_verified=False,root_cause_confirmed=False)
    storage.write(output/'audit.json',result);storage.seal(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.output)
    print(json.dumps({k:r[k] for k in ('linked_log_sites','linked_formats','logger_profile_count','wait_profile_count','logger_observed_user_stack_bytes')},indent=2))
