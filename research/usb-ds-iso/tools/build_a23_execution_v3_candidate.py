#!/usr/bin/env python3
"""Create isolated execution candidates from sealed V2; never acquire hardware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import build_a23_capacity_v2_candidate as capacity
import audit_a23_execution_readiness as execution
from analyze_ep0_execution_v3 import decode_execution
from workflows.artifacts import verify

ROOT,REPO=capacity.ROOT,capacity.REPO
SEALED=execution.CANDIDATE
PRIOR=SEALED.parent/'A23-execution-readiness-review-20261015'
NEW_FILES=('ep0_execution_v3.h','ep0_execution_sink_v3.h')
INPUTS=('tools/build_a23_execution_v3_candidate.py','tools/analyze_ep0_execution_v3.py',
        'tests/a23_execution_v3_fixture.c','tests/test_a23_execution_v3_candidate.py',
        'host/a23_passive_wait_policy.h','tests/a23_passive_wait_policy_fixture.c',
        'device/ep0_execution_runtime_v3.inc','device/ep0_execution_file_v3.inc',
        *('device/'+name for name in NEW_FILES))


def replace(s,old,new):return capacity.ready.base.trace.replace(s,old,new)


def main_source(source):
    source='#include "../uvc/ep0_execution_v3.h"\n'+source
    begin=source.index('static void VideoStreamThread(void* arg)')
    end=source.index('// ============================================================================\n// Audio Streaming Thread',begin)
    video=source[begin:end]
    anchor='    LOG("Video stream thread started\\n");'
    import re
    ms=int(re.search(r'ep0_window_init\(&window,svcGetSystemTick\(\),armGetSystemTickFreq\(\),(\d+)\)',video)[1])
    video=replace(video,anchor,
        f'    if(!Ep0ExecutionWindowStarted(window.start,armGetSystemTickFreq(),{ms})) {{ g_running=false;Ep0CandidateRequestStop();(void)Ep0CandidateStop(svcGetSystemTick());return; }}\n'+anchor)
    check='        if(ep0_window_expired(&window,svcGetSystemTick()))Ep0CandidateRequestStop();\n        if(Ep0CandidateStopRequested()) { g_running=false;break; }\n'
    video=replace(video,'    while (g_running) {\n        Result rc = UvcDeviceWaitReady(1E+9);',
        '    while (g_running) {\n'+check+'        Result rc = UvcDeviceWaitReady(1E+9);')
    video=replace(video,'        if (R_SUCCEEDED(rc)) {\n            break;',
        '        if (R_SUCCEEDED(rc)) {\n            (void)Ep0ExecutionWindowReady(svcGetSystemTick());\n            break;')
    video=replace(video,'        UvcDeviceProcessRequests();',check+'        UvcDeviceProcessRequests();')
    video=replace(video,'    (void)Ep0CandidateStop(svcGetSystemTick());\n    LOG("Video stream thread exiting\\n");',
        '    uint64_t stopped_at=svcGetSystemTick();\n    (void)Ep0CandidateStop(stopped_at);\n'
        '    (void)Ep0ExecutionWindowStopped(stopped_at,window.expired ? 1u:2u);\n    LOG("Video stream thread exiting\\n");')
    source=source[:begin]+video+source[end:]
    source=replace(source,'        if(diagnostic_saved)(void)Ep0SessionSaveJoined(video_join,audio_join);',
        '        if(Ep0ExecutionBuildJoined(exporter,video_join,audio_join,2,diagnostic_saved))\n'
        '            (void)Ep0ExecutionSaveJoined(video_join,audio_join);')
    source=replace(source,'    if(!normal_saved) { for(;;)svcSleepThread(1E+9); }',
        '    bool execution_saved=Ep0ExecutionBuildJoined(exporter,video_join,audio_join,1,normal_saved) &&\n'
        '        Ep0ExecutionSaveJoined(video_join,audio_join);\n'
        '    if(!normal_saved || !execution_saved) { for(;;)svcSleepThread(1E+9); }')
    return source


def prepare(folder,label,recipe):
    shutil.copytree(SEALED/label/'source',folder/'source')
    src=folder/'source'
    p=src/'sysmodule/main.c';p.write_text(main_source(p.read_text()))
    for name in NEW_FILES:shutil.copyfile(ROOT/'device'/name,src/'uvc'/name)
    for target,fragment in (('ep0_session_runtime.c','ep0_execution_runtime_v3.inc'),
                            ('ep0_session_file.c','ep0_execution_file_v3.inc')):
        p=src/'uvc'/target;p.write_text(p.read_text()+'\n'+(ROOT/'device'/fragment).read_text())
    (src/'uvc/ep0_candidate_recipe.h').write_text('static const uint8_t ep0CandidateRecipe[32]={'+
        ','.join(map(str,bytes.fromhex(recipe)))+'};\n')
    expected=['sysmodule/main.c','uvc/ep0_session_runtime.c','uvc/ep0_session_file.c',
              'uvc/ep0_candidate_recipe.h',*('uvc/'+n for n in NEW_FILES)]
    changes=[]
    for p in sorted(src.rglob('*')):
        if not p.is_file():continue
        previous=SEALED/label/'source'/p.relative_to(src)
        if not previous.exists() or p.read_bytes()!=previous.read_bytes():changes.append(str(p.relative_to(src)))
    if sorted(changes)!=sorted(expected):raise ValueError('Unexpected candidate source change')
    return sorted(changes)


def window_replay(output,folder):
    main=(folder/'source/sysmodule/main.c').read_text()
    body=capacity.ready.extract(main,'static void VideoStreamThread(void* arg)',
        '// ============================================================================\n// Audio Streaming Thread')
    original=(ROOT/'tests/a23_execution_window_fixture.c').read_text()
    ms=0 if folder.name=='dormant' else 30000
    stubs='''
static bool Ep0ExecutionWindowStarted(uint64_t at,uint64_t frequency,uint32_t ms) {
    assert(at==window_start && frequency==1000 && ms==MODEL_WINDOW_MS);return true;
}
static bool Ep0ExecutionWindowReady(uint64_t at) { assert(at>=window_start);return true; }
static bool Ep0ExecutionWindowStopped(uint64_t at,uint32_t reason) { assert(at==stop_tick && reason==MODEL_STOP_REASON);return true; }
'''
    stubs=stubs.replace('MODEL_WINDOW_MS',str(ms)).replace('MODEL_STOP_REASON','1' if ms else '2')
    if not ms:
        original=replace(original,'clock_tick+=process_ms;\n}',
            'clock_tick+=process_ms;if(process_calls==3)stop_requested=true;\n}')
        original=replace(original,'assert(stop_requested && !g_running && stop_tick>=window_start+30000);',
            'assert(stop_requested && !g_running && process_calls==3);')
    text=replace(original,'/* INSERT_ACTUAL_VIDEO_THREAD */',stubs+body)
    source=output/(folder.name+'-video-window.c');source.write_text(text)
    binary=output/(folder.name+'-video-window')
    command=['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I'+str(folder/'source/uvc'),str(source),'-o',str(binary)]
    subprocess.run(command,check=True,capture_output=True,text=True)
    rows={}
    for name,args in (execution.CASES if ms else {'explicit_stop':(1000,1,0,0)}).items():
        rows[name]=json.loads(subprocess.run([str(binary),*map(str,args)],
            check=True,capture_output=True,text=True).stdout)
    return rows,command


def lifecycle_source(folder):
    # Reuse only the frozen V2 fixture helpers; new main executes the actual
    # candidate's exit branch, runtime, primary file adapters and EXE3 adapter.
    original=(SEALED/'inputs/tests/a23_capacity_v2_files.c').read_text()
    original=original[:original.index('int main(int argc,char **argv)')]
    old='const uint8_t *Ep0SessionBytes(size_t *n) { assert(!poison);session_reads++;*n=rel_n;return rel_n?rel_bytes:NULL; }'
    original=replace(original,old,'')
    original=replace(original,'#include "ep0_session_capture.h"','#include "ep0_execution_v3.h"\n#include "ep0_cleanup_gate.h"\n#include <setjmp.h>')
    original=replace(original,'static unsigned owner_reads,normal_reads,guard_reads,session_reads;',
        'static unsigned owner_reads,normal_reads,guard_reads;')
    original=replace(original,'static uint8_t image[EP0_REL_MAX+1];',
        'static uint8_t image[EP0_EXEC_MAX+1],primary_image[EP0_EXEC_MAX+1];\n'
        'static size_t primary_image_n;\nstatic unsigned file_reads;\nstatic const char *primary_fault,*execution_fault;')
    original=replace(original,'(void)f;fs_open++;return is("fs-open-error")?91:0;',
        '(void)f;fs_open++;file_reads=0;\n    if(fs_open==2) { primary_image_n=image_n;memcpy(primary_image,image,image_n);image[0]=0x7a;image_n=1; }\n'
        '    fault=fs_open==1?primary_fault:execution_fault;return is("fs-open-error")?91:0;')
    original=replace(original,'options==0);reads++;','options==0);reads++;file_reads++;')
    original=replace(original,'is("late-read-error") && reads==2','is("late-read-error") && file_reads==2')
    original=replace(original,'n<=EP0_REL_MAX && options==0','n<=EP0_EXEC_MAX && options==0')
    marker='static void append('
    bridge='''
const Ep0AdmissionObservation *Ep0CandidateAdmissionObservation(void) { assert(!poison);return &admission; }
unsigned Ep0StartupStatus(void) { return 2; }
uint32_t Ep0StartupIdentityResult(void) { return 0; }
const Ep0StartupJournal *Ep0StartupJournalForSession(void) { return &journal; }
uint64_t Ep0StartupWriterForSession(void) { return 22; }
#include "ep0_session_runtime.c"
'''
    original=replace(original,marker,bridge+'\n'+marker)
    main=(folder/'source/sysmodule/main.c').read_text()
    tail=main[main.index('    g_running = false;\n    if(!ep0_cleanup_begin'):]
    body=(ROOT/'tests/a23_execution_v3_fixture.c').read_text()
    return original+replace(body,'/* ACTUAL_EXIT_TAIL */',tail)


def lifecycle(output,folder):
    source=output/'execution-lifecycle.c';source.write_text(lifecycle_source(folder))
    command=capacity.ready.base.trace.compile_native(source,output/'execution-lifecycle',
        ['-I'+str(folder/'source/uvc')])
    rows=[]
    faults=capacity.FILE_CASES
    scenarios=list(dict.fromkeys([('ok',f) for f in faults]+[(f,'ok') for f in faults]))
    scenarios += [('video-join-error','ok'),('audio-join-error','ok'),('identity-error','ok')]
    for kind in ('normal','diagnostic'):
        for primary,sidecar in scenarios:
            stem=f'{kind}-primary-{primary}-execution-{sidecar}'
            prefix=output/stem
            row=json.loads(capacity.ready.base.owner.command([str(output/'execution-lifecycle'),kind,primary,sidecar,str(prefix)]))
            path=Path(str(prefix)+'.execution.bin')
            if path.exists():
                decoded=decode_execution(path.read_bytes(),'03'+'00'*31)
                path.with_suffix('.json').write_text(json.dumps(decoded,indent=2)+'\n')
                row['receipt']=decoded['primary_receipt']
            rows.append(row)
    return rows,command


def passive_wait(output):
    command=['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I'+str(ROOT/'host'),str(ROOT/'tests/a23_passive_wait_policy_fixture.c'),'-o',str(output/'passive-wait')]
    subprocess.run(command,check=True,capture_output=True,text=True)
    result=json.loads(subprocess.run([str(output/'passive-wait')],check=True,capture_output=True,text=True).stdout)
    return result,command


def compile_arm(folder,commands):
    compiler='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc'
    objects=folder/'objects';objects.mkdir();paths=[]
    flags=['-std=gnu11','-Wall','-Werror','-O3','-g','-ffunction-sections','-fstack-usage',
        '-march=armv8-a+crc+crypto','-mtune=cortex-a57','-mtp=soft','-fPIE','-D__SWITCH__',
        *capacity.ready.base.DEFINES,'-I'+str(folder/'source/uvc'),'-I/opt/devkitpro/libnx/include']
    for source in sorted((folder/'source').rglob('*.c')):
        obj=objects/(source.relative_to(folder/'source').as_posix().replace('/','-')+'.o')
        cmd=[compiler,*flags,'-c',str(source),'-o',str(obj)]
        capacity.ready.base.owner.command(cmd);commands.append(cmd);paths.append(str(obj))
    cmd=[compiler,'-specs=/opt/devkitpro/libnx/switch.specs',
        '-march=armv8-a+crc+crypto','-mtune=cortex-a57','-mtp=soft','-fPIE',*paths,
        '-L/opt/devkitpro/libnx/lib','-lnx','-Wl,-Map,'+str(folder/'full.map'),'-o',str(folder/'full.elf')]
    capacity.ready.base.owner.command(cmd,dict(os.environ,DEVKITPRO='/opt/devkitpro'));commands.append(cmd)
    symbols=capacity.ready.base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-readelf','-Ws',str(folder/'full.elf')])
    (folder/'symbols.txt').write_text(symbols)
    for name in ('Ep0ExecutionBuildJoined','Ep0ExecutionSaveJoined','Ep0ExecutionWindowStarted',
                 'Ep0ExecutionWindowStopped','VideoStreamThread','Ep0CandidateFinish','Ep0StartupBegin'):
        if name not in symbols:raise ValueError('Linked function missing: '+name)
    values=capacity.ready.base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-size',str(folder/'full.elf')]).splitlines()[1].split()
    stack=[]
    for path in sorted(objects.glob('*.su')):
        for line in path.read_text().splitlines():
            function,n,kind=line.rsplit('\t',2);stack.append(dict(function=function.split(':')[-1],bytes=int(n),kind=kind))
    (folder/'stack-usage.json').write_text(json.dumps(stack,indent=2)+'\n')
    return dict(elf_sha256=capacity.ready.sha(folder/'full.elf'),object_count=len(paths),linked=True,
        executed=False,sections=dict(zip(('text','data','bss'),map(int,values[:3]))),
        largest_project_function_stack=max(r['bytes'] for r in stack),whole_call_graph_stack_verified=False)


def run(output,*,arm=True):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Refusing existing output: '+str(output))
    seals=[verify(p) for p in (SEALED,PRIOR)]
    old=json.loads((SEALED/'audit.json').read_text())
    prior=json.loads((PRIOR/'audit.json').read_text())
    for parent in (old,prior):
        for name,expected in parent['source_hashes'].items():
            if capacity.ready.sha(ROOT/name)!=expected:raise ValueError('Parent input drift: '+name)
    external={name:capacity.ready.sha(name) for name in old['external_sha256']}
    headers={name:capacity.ready.sha(Path('/opt/devkitpro/libnx/include')/name) for name in old['sdk_headers_sha256']}
    if external!=old['external_sha256'] or headers!=old['sdk_headers_sha256']:
        raise ValueError('Toolchain/header drift from V2')
    production={n:capacity.ready.sha(REPO/n) for n in old['production_sources_sha256']}
    tickets={n:capacity.ready.sha(SEALED.parent/n) for n in old['tickets_sha256']}
    if production!=old['production_sources_sha256'] or tickets!=old['tickets_sha256']:
        raise ValueError('Protected source/ticket drift')
    names=list(dict.fromkeys([*old['source_hashes'],*prior['source_hashes'],*INPUTS]))
    sources={n:capacity.ready.sha(ROOT/n) for n in names}
    identity=capacity.digest(dict(sources=sources,parent=capacity.ready.sha(SEALED/'SHA256SUMS'),
        readiness=capacity.ready.sha(PRIOR/'SHA256SUMS'),external=external,sdk_headers=headers))
    output.mkdir(parents=True);folders={};recipes={};changes={};commands=[]
    for label in ('dormant','window-30s'):
        folder=output/label;recipe=capacity.digest(dict(inputs=identity,label=label,envelope=3))
        folders[label]=folder;recipes[label]=recipe;changes[label]=prepare(folder,label,recipe)
        (folder/'recipe.json').write_text(json.dumps(dict(input_digest=recipe,parent_input_digest=identity,
            source_hashes=sources,window_ms=old['builds'][label]['window_boundary']['window_ms']),indent=2)+'\n')
    windows,cmd=window_replay(output,folders['window-30s']);commands.append(cmd)
    dormant_windows,cmd=window_replay(output,folders['dormant']);commands.append(cmd)
    files,cmd=lifecycle(output,folders['window-30s']);commands.append(cmd)
    wait,cmd=passive_wait(output);commands.append(cmd)
    builds={}
    if arm:
        for label,folder in folders.items():
            result=compile_arm(folder,commands)
            strict=[]
            for cmd in list(commands):
                if '-c' not in cmd:continue
                path=Path(cmd[cmd.index('-c')+1])
                if not path.is_relative_to(folder/'source'):continue
                flags=[v for v in cmd[1:cmd.index('-c')] if v!='-fstack-usage']
                check=[cmd[0],*flags,'-Wformat=2','-fsyntax-only',str(path)]
                capacity.ready.base.owner.command(check);commands.append(check);strict.append(str(path))
            if len(strict)!=13:raise ValueError('Expected 13 strict format units')
            result['strict_format_units']=len(strict)
            result['delta_from_v2']={k:result['sections'][k]-old['builds'][label]['sections'][k] for k in ('text','data','bss')}
            dis=capacity.ready.base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d',str(folder/'full.elf')])
            (folder/'disassembly.txt').write_text(dis)
            result['logger_machine']=capacity.linked.linked_logger((folder/'full.elf').read_bytes(),dis)
            blob=(folder/'full.elf').read_bytes()
            metadata=capacity.linked.oldbuild.boundaries.elf_metadata(blob)
            sections=[s['name'] for s in metadata['sections'] if s['flags']&2 and not s['flags']&5 and
                bytes.fromhex(recipes[label]) in blob[s['offset']:s['offset']+s['size']]]
            if not sections:raise ValueError('Recipe missing from readonly ELF')
            objects={}
            for name in ('exported','diagnostic_bytes','session_bytes','session_work','execution_bytes','execution_window'):
                rows=[r.split() for r in (folder/'symbols.txt').read_text().splitlines()
                      if r.split() and r.split()[-1]==name and 'OBJECT' in r]
                if len(rows)!=1:raise ValueError('Storage symbol missing/ambiguous: '+name)
                objects[name]=dict(address=int(rows[0][1],16),bytes=int(rows[0][2]))
            if objects['execution_bytes']['bytes']!=14432:raise ValueError('Execution buffer size')
            result.update(runtime_recipe_digest=recipes[label],recipe_in_elf=True,
                recipe_readonly_sections=sections,linked_storage_objects=objects)
            builds[label]=result
    for group,base in ((sources,ROOT),(production,REPO),(tickets,SEALED.parent)):
        if group!={n:capacity.ready.sha(base/n) for n in group}:raise ValueError('Inputs changed')
    for p in (SEALED,PRIOR):verify(p)
    if external!={name:capacity.ready.sha(name) for name in external} or headers!={
        name:capacity.ready.sha(Path('/opt/devkitpro/libnx/include')/name) for name in headers}:
        raise ValueError('Toolchain changed during build')
    for name in names:
        target=output/'inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    result=dict(schema='A23-execution-v3-candidate-1',recipe_digest=identity,source_hashes=sources,
        production_sources_sha256=production,tickets_sha256=tickets,sealed_inputs=seals,
        changed_files=changes,window_cases=windows,dormant_window_cases=dormant_windows,
        lifecycle_cases=files,passive_wait_policy=wait,builds=builds,
        external_sha256=external,sdk_headers_sha256=headers,
        compiler_commands=commands,native_execution_count=len(windows)+len(dormant_windows)+len(files)+1,
        formats_v1_v2_modified=False,hardware_entry_integrated=False,arm_executed=False,
        firmware_packaged=False,usb_accessed=False,sd_accessed=False,attempt_issued=False,
        hardware_verified=False,root_cause_confirmed=False,whole_thread_stack_verified=False,
        full_formatter_replayed_on_new_elf=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(capacity.ready.sha(p)+'  '+str(p.relative_to(output))+'\n'
        for p in sorted(output.rglob('*')) if p.is_file()))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--native-only',action='store_true');args=p.parse_args()
    print(json.dumps(run(args.output,arm=not args.native_only),indent=2))


if __name__=='__main__':main()
