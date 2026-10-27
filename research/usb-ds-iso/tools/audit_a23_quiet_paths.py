#!/usr/bin/env python3
"""Fresh quiet-ELF wait/logger/save profiles, never a hardware stack certificate."""
import argparse
import ast
import json
from pathlib import Path
import shutil
import subprocess

import build_a23_quiet_receiver as storage
import build_a23_quiet_candidate as candidate
import audit_a23_v3_stack_profiles as previous
from model_a23_v3_logger_stack import PathSnprintfMachine
from model_a23_quiet_paths import QuietLoggerMachine,JoinWaitMachine,main_handoff_certificate
from workflows.artifacts import verify

ROOT=storage.ROOT;REPO=storage.REPO
PARENT=ROOT/'private/analysis/A23-quiet-receiver-review-20261015'
DEVICE=storage.DEVICE/'window-30s'
NEW=('tools/model_a23_quiet_paths.py','tools/audit_a23_quiet_paths.py','tests/test_a23_quiet_paths.py')
elf=previous.elf;linked=previous.linked;formats=previous.formats


def dependency_sources():
    sources=dict(storage.load(PARENT/'audit.json')['source_hashes']);pending=list(NEW);seen=set()
    while pending:
        name=pending.pop()
        if name in seen:continue
        seen.add(name);path=ROOT/name;sources['research/usb-ds-iso/'+name]=candidate.sha(path)
        if path.suffix!='.py':continue
        for node in ast.walk(ast.parse(path.read_text())):
            names=[v.name for v in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
            for item in names:
                child='tools/'+item.replace('.','/')+'.py'
                if (ROOT/child).is_file():pending.append(child)
    for n,h in sources.items():storage.require(candidate.sha(REPO/n)==h,'parent/dependency source drift: '+n)
    return dict(sorted(sources.items()))


def catalog(output):
    audit=storage.load(storage.DEVICE/'audit.json');rows=[];commands=[];units=[]
    for original in audit['compiler_commands']:
        if not original[0].endswith('/aarch64-none-elf-gcc') or '-c' not in original:continue
        source=Path(original[original.index('-c')+1])
        if not source.is_relative_to(DEVICE/'source'):continue
        unit=source.relative_to(DEVICE/'source').as_posix();units.append(unit)
        flags=[v for v in original[1:original.index('-c')] if v!='-fstack-usage']
        cmd=[original[0],*flags,'-E','-P',str(source)];commands.append(cmd)
        raw=subprocess.check_output(cmd);dest=output/'preprocessed'/Path(unit).with_suffix('.i')
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        rows.extend(previous.contract.inventory(raw.decode(),unit))
    if len(units)!=len(set(units)) or len(units)!=13:raise ValueError('quiet compilation inventory drift')
    for i,row in enumerate(rows):row['case']=i
    return rows,commands


def compose(blob,text,rows,policy,waits,paths,quiet_bytes,resumed_bytes):
    fs,meta=elf.build_functions(blob,text);names={n:a for a,f in fs.items() for n in f['aliases']}
    contracts={int(a):c for a,c in policy['contracts'].items()};reported={r['function']:r['bytes'] for r in rows if r['kind']=='static'}
    frames={a:elf.frame_range(f,fs,reported.get(f['name']),contracts) for a,f in fs.items()}
    overrides={(s['caller_address'],s['at']):s for s in waits['sites']}
    path_overrides={(s['caller_address'],s['at']):s for s in paths}
    def walk(a,ancestors,quiet):
        if a in ancestors:return dict(bytes=0,path=[],unresolved=[fs[a]['name']+': recursive cycle'],substitutions=[])
        if a==names['LogFunctionImpl']:
            label='quiet=true guarded path' if quiet else 'quiet=false observed profiles'
            return dict(bytes=quiet_bytes if quiet else resumed_bytes,path=['LogFunctionImpl['+label+']'],
                unresolved=[],substitutions=['conditional-quiet-logger' if quiet else 'resumed-logger-profiles'])
        f=frames[a];best=f['machine_observed_frame'];path=[fs[a]['name']]
        unknown=[fs[a]['name']+': '+u for u in f['unresolved']];used=[]
        for e in f['edges']:
            if (a,e['at']) in path_overrides:
                p=path_overrides[a,e['at']];sub=dict(bytes=p['observed_stack_bytes'],path=['snprintf[hex filename profiles]'],
                    unresolved=[],substitutions=['filename-profiles'])
            elif (a,e['at']) in overrides:
                w=overrides[a,e['at']];sub=dict(bytes=w['observed_stack_bytes'],path=['waitObjects[handle profiles]'],
                    unresolved=[],substitutions=['wait-profiles-'+str(w['count'])])
            else:sub=walk(e['target'],ancestors|{a},quiet)
            unknown.extend(sub['unresolved']);used.extend(sub['substitutions'])
            amount=e['held_bytes']+sub['bytes']
            if amount>best:best=amount;path=[fs[a]['name'],*sub['path']]
        return dict(bytes=best,path=path,unresolved=sorted(set(unknown)),substitutions=sorted(set(used)))
    wrapper=frames[names['_EntryWrap']]['machine_observed_frame'];result={}
    for name in ('VideoStreamThread','AudioStreamThread','UvcDeviceProcessRequests','main',
                 'Ep0CandidateSaveCapture','Ep0CandidateSaveDiagnostic','Ep0ExecutionSaveJoined','Ep0SessionStartupOnly'):
        quiet=name in ('VideoStreamThread','AudioStreamThread','UvcDeviceProcessRequests')
        row=walk(names[name],set(),quiet);row['conditional_path_estimate_bytes']=row.pop('bytes')
        row.update(quiet_assumed=quiet,whole_thread_stack_bound_bytes=None)
        if name in ('VideoStreamThread','AudioStreamThread'):
            row['worker_wrapper_bytes']=wrapper;row['with_wrapper_conditional_estimate_bytes']=row['conditional_path_estimate_bytes']+wrapper
        result[name]=row
    return dict(schema='A23-quiet-path-composition-1',elf_sha256=meta['elf_sha256'],roots=result,
        estimates_are_not_whole_thread_bounds=True,wait_and_formatter_profiles_substituted=True,
        quiet_phase_and_valid_memory_contract_assumed=True,exception_and_kernel_stack_included=False,
        actual_thread_stack_budget_verified=False,whole_thread_stack_verified=False,runtime_peak_measured=False)


def join_profiles(text,functions):
    rows=[]
    for name,results in (('ok',(0,)),('error',(0xee01,)),('timeout',(0xea01,)),
                         ('cancel-then-ok',(0xec01,0)),('repeated-cancel-then-ok',(0xec01,)*3+(0,))):
        row=JoinWaitMachine(text,results=results).run();row.update(scenario=name)
        assert row['peak_user_stack_bytes']==96 and row['stack_restored']
        rows.append(row)
    byname={n:f for f in functions.values() for n in f['aliases']};f=byname['threadWaitForExit']
    calls=[pc for pc,op,arg in f['instructions'] if op=='bl' and arg.endswith('<waitHandles>')]
    code={p:(op,arg) for p,op,arg in f['instructions']}
    if len(calls)!=1 or code[calls[0]-20]!=('mov','x3, #0xffffffffffffffff') or code[calls[0]-16]!=('mov','w2, #0x1'):
        raise ValueError('thread join count/timeout drift')
    return dict(sites=[dict(caller='threadWaitForExit',at=calls[0],count=1,timeout='UINT64_MAX')],profiles=rows,
        functions_sha256={n:elf.function_digest(byname[n]) for n in ('threadWaitForExit','waitHandles','svcWaitSynchronization')},
        svc_results_and_valid_thread_handle_injected=True,svc_abi_register_preservation_assumed=True,
        termination_time_bound_verified=False,actual_join_executed=False)


def run(output):
    output=Path(output);storage.require(output.is_absolute() and output==output.resolve() and not output.exists(),'new canonical output required')
    sealed=[verify(p) for p in (PARENT,PARENT.parent/'A23-quiet-receiver-validation-20261015',storage.DEVICE)]
    parent=storage.load(PARENT/'audit.json');record=storage.load(PARENT/'offline-record.json');sources=dependency_sources()
    storage.verify_build(record);device=storage.device.identity(DEVICE)
    original=storage.load(storage.DEVICE/'audit.json')
    external={n:candidate.sha(n) for n in original['external_sha256']}
    if external!=original['external_sha256']:raise ValueError('toolchain drift')
    objdump=Path('/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump');external[str(objdump)]=candidate.sha(objdump)
    output.mkdir(parents=True);blob=storage.plain(DEVICE/'full.elf');text=storage.plain(DEVICE/'disassembly.txt').decode()
    if storage.sha(blob)!=device['device_elf_sha256']:raise ValueError('quiet ELF mismatch')
    command=[str(objdump),'-d',str(DEVICE/'full.elf')]
    if subprocess.check_output(command,text=True)!=text:raise ValueError('disassembly drift')
    commands=[command]
    for n,h in sources.items():
        p=output/'source'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/n,p)
        if candidate.sha(p)!=h:raise ValueError('source copy drift')
    headers={n:(Path('/opt/devkitpro/libnx/include')/n).read_text() for n in previous.SDK_HEADERS}
    for n,raw in headers.items():
        p=output/'sdk-headers'/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(raw)
    rows,preprocess=catalog(output);commands.extend(preprocess)
    binding=linked.linked_calls(blob,text,rows);covered={fmt for site in binding['sites'] for fmt in site['formats']}
    items=list({r['format']:r for r in rows if r['format'] in covered}.values())
    fs,meta=elf.build_functions(blob,text);meta['dispatch']=linked.fmt.decode_dispatch(blob,text);meta['locale']=linked.fmt.default_locale(blob,text)
    guard=candidate.quiet_guard_certificate(fs,meta);handoff=main_handoff_certificate(fs)
    literals={fmt:a for s in binding['sites'] for a,fmt in zip(s['format_addresses'],s['formats'])}
    oracle=formats.NativeOracle();resumed=[];quiet=[];controls=[]
    for item in items:
        for scenario in formats.SCENARIOS:
            values=formats.values_for(item,scenario);address=literals[item['format']]
            required,expected=oracle.format(item,values)
            row=QuietLoggerMachine(fs,blob,meta,address,values,quiet=False).run()
            assert row['required']==required and bytes.fromhex(row['rendered_hex'])==expected[:511]
            row.update(format=item['format'],scenario=scenario);resumed.append(row)
            row=QuietLoggerMachine(fs,blob,meta,address,values,quiet=True).run()
            assert row['observed_user_stack_bytes']==guard['conditional_held_stack_bytes']
            row.update(format=item['format'],scenario=scenario);quiet.append(row)
    item=next(i for i in items if i['conversions']);address=literals[item['format']];values=formats.values_for(item,'limits')
    for fault in ('open','size','write'):
        row=QuietLoggerMachine(fs,blob,meta,address,values,quiet=False,fs_fault=fault).run();row['case']=fault;controls.append(row)
    row=QuietLoggerMachine(fs,blob,meta,address,values,quiet=False,mounted=False).run();row['case']='unmounted';controls.append(row)
    for mounted in (False,True):
        m=QuietLoggerMachine(fs,blob,meta,address,values,quiet=True,mounted=mounted,tls_magic=0)
        m.put('x0',1);row=m.run();row.update(case='quiet-invalid-format-and-tls',mounted=mounted);controls.append(row)
    for name,kwargs,budget in (('resumed-invalid-tls',dict(quiet=False,tls_magic=0),100000),
                               ('quiet-instruction-budget',dict(quiet=True),1)):
        try:QuietLoggerMachine(fs,blob,meta,address,values,**kwargs).run(budget)
        except (ValueError,KeyError) as error:controls.append(dict(case=name,rejected=True,error=str(error)))
        else:raise ValueError('model should reject unsupported frontier')
    paths=[];path_profiles=[]
    for a,f in fs.items():
        for pc,op,arg in f['instructions']:
            if op in ('b','bl') and arg.endswith('<snprintf>'):
                addresses=linked.LiteralResolver(f).values(pc,'x2')
                if len(addresses)!=1:raise ValueError('filename literal ambiguity')
                address=next(iter(addresses));literal=linked.literal_at(blob,meta,address);peaks=[]
                for nonce in (b'0'*64,b'f'*64,b'0123456789abcdef'*4):
                    row=PathSnprintfMachine(fs,blob,meta,address,nonce).run()
                    assert bytes.fromhex(row['rendered_hex'])==literal.replace('%s',nonce.decode()).encode()
                    peaks.append(row['observed_user_stack_bytes']);row.update(caller=f['name'],at=pc,nonce=nonce.decode());path_profiles.append(row)
                paths.append(dict(caller=f['name'],caller_address=a,at=pc,format=literal,observed_stack_bytes=max(peaks)))
    if len(paths)!=2:raise ValueError('expected two quiet candidate filename sites')
    waits=previous.wait_profiles(text,fs);joins=join_profiles(text,fs);policy=elf.no_return_policy(blob,text,headers)
    stack_rows=storage.load(DEVICE/'stack-usage.json')
    static=elf.analyze(blob,text,stack_rows,policy,roots=(*QuietLoggerMachine.FS,'threadWaitForExit','Ep0ExecutionSaveJoined','AudioStreamThread'))
    assert all(r['user_prefix_bound_bytes'] is not None for r in static['roots'].values())
    peak=max(r['observed_user_stack_bytes'] for r in resumed)
    envelope=max(peak,guard['conditional_held_stack_bytes']+max(static['roots'][n]['user_prefix_bound_bytes'] for n in QuietLoggerMachine.FS))
    graph=compose(blob,text,stack_rows,policy,waits,paths,guard['conditional_held_stack_bytes'],envelope)
    results={'catalog.json':rows,'linked-calls.json':binding,'resumed-logger.json':resumed,'quiet-logger.json':quiet,
        'controls.json':controls,'quiet-guard.json':guard,'main-handoff.json':handoff,'wait-profiles.json':waits,
        'join-profiles.json':joins,'path-snprintf.json':dict(sites=paths,profiles=path_profiles),
        'no-return-policy.json':policy,'static-prefixes.json':static,'composition.json':graph,
        'commands.json':commands,'dispatch.json':meta['dispatch'],'locale.json':meta['locale']}
    for n,value in results.items():storage.write(output/n,value)
    for n,h in sources.items():assert candidate.sha(REPO/n)==h,n
    for group,base in ((parent['production_sources_sha256'],REPO),(parent['tickets_sha256'],PARENT.parent),(external,Path('/'))):
        for n,h in group.items():assert candidate.sha(base/n)==h,n
    for n,raw in headers.items():assert (Path('/opt/devkitpro/libnx/include')/n).read_text()==raw
    for entry in sealed:verify(entry['folder'])
    storage.verify_build(record)
    result=dict(schema='A23-quiet-paths-review-1',source_hashes=sources,sealed_inputs=sealed,
        production_sources_sha256=parent['production_sources_sha256'],tickets_sha256=parent['tickets_sha256'],
        device_binding=device,device_binding_sha256=record['device_binding_sha256'],elf_sha256=storage.sha(blob),
        runtime_recipe_sha256=record['recipe_sha256'],external_sha256=external,
        sdk_headers_sha256={n:storage.sha(raw.encode()) for n,raw in headers.items()},preprocessed_units=13,
        preprocessed_log_calls=len(rows),linked_log_sites=binding['direct_sites'],linked_formats=len(items),
        quiet_profile_count=len(quiet),resumed_profile_count=len(resumed),quiet_logger_stack_bytes=guard['conditional_held_stack_bytes'],
        resumed_logger_observed_stack_bytes=peak,path_snprintf_profile_count=len(path_profiles),
        wait_profile_count=waits['profile_count'],join_profile_count=len(joins['profiles']),control_count=len(controls),
        old_address_certificates_reused=False,profiles_are_not_all_input_proofs=True,main_npdm_request_bytes=8192,
        actual_kernel_thread_budget_verified=False,whole_thread_stack_verified=False,synchronous_call_time_bound_verified=False,
        native_sdk_calls=0,usb_requests=0,sd_accesses=0,actual_arm_executed=False,device_modified=False,
        new_device_elf_built=False,attempt_issued=False,hardware_verified=False,root_cause_confirmed=False)
    storage.write(output/'audit.json',result);storage.seal(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=run(a.output);print(json.dumps({k:r[k] for k in ('linked_log_sites','linked_formats','quiet_profile_count','resumed_profile_count','wait_profile_count','join_profile_count')},indent=2))
