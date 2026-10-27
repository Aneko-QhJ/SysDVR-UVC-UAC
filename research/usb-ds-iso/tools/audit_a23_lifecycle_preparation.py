#!/usr/bin/env python3
"""Freeze offline package/workflow preparation, not a deployment or invocation."""
import argparse,json
from pathlib import Path
import analyze_a23_session_stack as stack
import analyze_a23_elf_boundaries as elf
import prepare_a23_lifecycle_once as once

b=once.build;ROOT=b.ROOT;ANALYSIS=once.ANALYSIS
PARENT=ANALYSIS/'A23-lifecycle-receiver-review-20261016'
NEW=('tools/build_a23_lifecycle_deployment.py','tools/prepare_a23_lifecycle_once.py',
     'tools/workflows/capture_a23_lifecycle_receiver.py','tools/audit_a23_lifecycle_preparation.py',
     'tests/test_a23_lifecycle_preparation.py')


def service_review():
    device=b.DEVICE/'candidate';blob=b.plain(device/'full.elf')
    functions,_=elf.build_functions(blob,(device/'disassembly.txt').read_text())
    names={alias:f for f in functions.values() for alias in f['aliases']}
    requested=('__appInit','CoreInit','main','CoreExit','Ep0LifePrepare','Ep0LifeNote','Ep0LifeContext','Ep0LifeFinish',
        'life_transfer','life_write_once','ep0_lcp_note','fsInitialize','fsOpenSdCardFileSystem','fsFsCommit','fsFsClose','fsFileClose','fsExit')
    rows={}
    for name in requested:
        variants=[f for f in functions.values() if any(alias==name or alias.startswith(name+'.') for alias in f['aliases'])]
        b.require(variants,'missing service review function: '+name)
        rows[name]=[dict(address=f['start'],aliases=f['aliases'],function_sha256=elf.function_digest(f),
            frame=stack.frame(f,functions),direct_calls=[dict(at=pc,target=int(m[1],16),aliases=functions[int(m[1],16)]['aliases'])
                for pc,op,arg in f['instructions'] if op in ('bl','b') and
                (m:=__import__('re').search(r'\b([0-9a-f]+) <([^>]+)>',arg)) and int(m[1],16) in functions and int(m[1],16)!=f['start']]) for f in variants]
    def calls(name,target):return any(target in e['aliases'] for row in rows[name] for e in row['direct_calls'])
    b.require(calls('__appInit','CoreInit') and calls('CoreInit','fsInitialize'),'FS initialization path changed')
    b.require(calls('main','Ep0LifePrepare') and calls('Ep0LifePrepare','fsOpenSdCardFileSystem'),'prepare/FS path changed')
    b.require(calls('life_transfer','fsFileClose') and calls('life_transfer','fsFsCommit'),'close/commit path changed')
    b.require(calls('CoreExit','fsExit'),'Core service exit path changed')
    for name in ('Ep0LifePrepare','Ep0LifeNote','Ep0LifeContext','Ep0LifeFinish','life_transfer','life_write_once'):
        b.require(not calls(name,'fsExit'),'lifecycle adapter must not exit shared FS service')
    source=device/'source';main=(source/'sysmodule/main.c').read_text();core=(source/'core.c').read_text();life=(source/'uvc/ep0_lifecycle_file.c').read_text()
    tail=main[main.index('int main('):]
    b.require(tail.index('Ep0LifePrepare(')<tail.index('UvcDeviceInitialize('),'prepare order')
    b.require(life.index('fsFileClose(&file)')<life.index('fsFsCommit(&life_fs)'),'close-before-commit order')
    b.require('fsFsClose(&life_fs)' in life and 'fsExit(' not in life,'journal handle lifetime')
    audit=b.load(b.DEVICE/'audit.json')
    defines=sorted({flag for cmd in audit['compiler_commands'] for flag in cmd if flag.startswith('-D')})
    b.require(any('FILE_LOGGING' in value for value in defines),'file logger definition missing')
    hashes={n:b.sha(b.plain(source/n)) for n in ('sysmodule/main.c','core.c','uvc/ep0_lifecycle_file.c','uvc/ep0_lifecycle_file.h')}
    return dict(schema='A23-lifecycle-service-source-elf-review-1',elf_sha256=b.sha(blob),functions=rows,source_hashes=hashes,
        compilation_defines=defines,core_fs_initialize_before_main_source_path=True,
        fs_initialize_failure_may_continue_core_init=True,core_capture_may_initialize_before_lifecycle_prepare=True,extra_journal_fs_object_only=True,
        file_closed_before_commit=True,life_does_not_call_shared_fs_exit=True,
        actual_fs_service_verified=False,actual_kernel_thread_budget_verified=False,whole_thread_stack_bound_verified=False,
        actual_timing_verified=False,main_return_authenticates_process_exit=False,root_cause_confirmed=False)


def run(output):
    output=once.package.output_path(output);parent=b.load(PARENT/'audit.json');hashes=dict(parent['source_hashes'])
    b.require(len(hashes)==202,'prior source inventory')
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'prior source drift: '+n)
    for n in NEW:hashes['research/usb-ds-iso/'+n]=b.sha(b.plain(ROOT/n))
    protected=b.load(PARENT/'protected-inputs.json');record=ANALYSIS/'A23-quiet-once-20261016-interface2.json';before=b.plain(record)
    output.mkdir(mode=0o700,parents=True)
    for n in NEW:once.package.put(output,'inputs/'+n,b.plain(ROOT/n))
    source,scope=once.materials();preview=once.prepare(ANALYSIS/'A23-lifecycle-once-next-preview.json')
    b.require(not Path(preview['record_path']).exists() and preview['remaining']==0,'preview created a record')
    b.write(output/'preview.json',preview);b.write(output/'service-review.json',service_review())
    refs=[]
    for folder in (PARENT,once.VALIDATION,once.PACKAGE):
        row=once.package.verify(folder);row['manifest_sha256']=b.sha(b.plain(folder/'SHA256SUMS'));refs.append(row)
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'source drift')
    for n,h in protected['production'].items():b.require(b.sha(b.plain(b.REPO/n))==h,'production drift')
    for group in ('tickets','offline_records_sha256'):
        for n,h in protected[group].items():b.require(b.sha(b.plain(ANALYSIS/n))==h,'ticket drift')
    b.require(b.plain(record)==before==b.plain(PARENT/'live-record-snapshot.json'),'live record drift')
    result=dict(schema='A23-lifecycle-preparation-review-1',source_hashes=hashes,parent_sources_unchanged=202,new_sources=len(NEW),
        package_verification=once.package.verify_review(once.PACKAGE),scope=scope,preview=preview,source_references=refs,
        receiver_and_device_unchanged=True,new_device_elf_built=False,firmware_packaged=True,deployed=False,
        real_new_deployment_present=False,formal_record_created=False,attempt_issued=False,remaining=0,
        sd_accesses=0,usb_requests=0,receiver_launched=False,device_executed=False,hardware_verified=False,root_cause_confirmed=False)
    b.write(output/'audit.json',result);b.write(output/'protected-inputs.json',protected);once.package.put(output,'live-record-snapshot.json',before)
    b.seal(output);once.package.verify(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();result=run(a.output)
    print(json.dumps(dict(source_files=len(result['source_hashes']),firmware_packaged=True,remaining=0)))
