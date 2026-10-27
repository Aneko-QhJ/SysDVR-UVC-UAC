#!/usr/bin/env python3
"""Build an isolated USB-only, quiet-window candidate; no hardware execution."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

import build_a23_execution_v3_candidate as v3
import analyze_a23_elf_boundaries as elf
from workflows.artifacts import verify

ROOT, REPO = v3.ROOT, v3.REPO
PARENT = ROOT/'private/analysis/A23-v3-stack-profiles-review-20261015'
DEVICE = ROOT/'private/analysis/A23-execution-v3-candidate-review-20261015'
NEW = ('tools/build_a23_quiet_candidate.py', 'tests/test_a23_quiet_candidate.py')
NPDMTOOL = Path('/opt/devkitpro/tools/bin/npdmtool')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2)+'\n')


def seal(folder):
    names=sorted(p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (folder/'SHA256SUMS').write_text(''.join(sha(folder/n)+'  '+n+'\n' for n in names))


def source_hashes():
    old=json.loads((PARENT/'audit.json').read_text())['source_hashes']
    hashes=dict(old)
    pending=list(NEW);seen=set()
    while pending:
        name=pending.pop()
        if name in seen: continue
        seen.add(name);path=ROOT/name
        hashes['research/usb-ds-iso/'+name]=sha(path)
        if path.suffix!='.py': continue
        for node in ast.walk(ast.parse(path.read_text())):
            imports=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
            for item in imports:
                candidate='tools/'+item.replace('.','/')+'.py'
                if (ROOT/candidate).is_file():pending.append(candidate)
    for n,h in hashes.items():
        if sha(REPO/n)!=h:raise ValueError('Frozen source drift: '+n)
    return dict(sorted(hashes.items()))


QUIET_API = '''static atomic_bool g_diagnosticQuiet = false;
void CoreSetDiagnosticQuiet(bool quiet)
{
    atomic_store_explicit(&g_diagnosticQuiet,quiet,memory_order_release);
}
bool CoreDiagnosticQuiet(void)
{
    return atomic_load_explicit(&g_diagnosticQuiet,memory_order_acquire);
}

'''


def main_source(text):
    # Derive only the new diagnostic candidate. Production source is untouched.
    start=text.index('    VideoFrame frame;')
    end=text.index('    Ep0CandidateRequestStop();\n    uint64_t stopped_at=',start)
    loop=text[start:end]
    cutoff=loop.index('        if (!UvcDeviceIsStreaming())')
    loop=loop[:cutoff]+'        svcSleepThread(1E+6);  // Diagnostic pacing; no production capture.\n    }\n\n'
    loop=loop.replace('    VideoFrame frame;\n\n','')
    text=text[:start]+loop+text[end:]
    start=text.index('static void AudioStreamThread(void* arg)')
    end=text.index('// ============================================================================\n// Sysmodule Lifecycle',start)
    text=text[:start]+'''static void AudioStreamThread(void* arg)
{
    (void)arg;
    // Keep the two-worker handoff; the diagnostic does not produce audio.
    while (g_running) svcSleepThread(100E+6);
}

'''+text[end:]
    text=v3.replace(text,'    Ep0StartupBindThreads(&g_videoThread,&g_audioThread);',
        '    CoreSetDiagnosticQuiet(true);\n    Ep0StartupBindThreads(&g_videoThread,&g_audioThread);')
    text=v3.replace(text,'    if(R_FAILED(identity_rc)) {\n        (void)Ep0SessionStartupOnly',
        '    CoreSetDiagnosticQuiet(false);  // Both workers have successfully joined.\n    if(R_FAILED(identity_rc)) {\n        (void)Ep0SessionStartupOnly')
    text=text.replace('USB ready, starting video capture loop','USB ready, starting diagnostic request loop')
    text=text.replace('SysDVR-UVC running (video + audio)','SysDVR-UVC diagnostic running (USB requests only)')
    return text


def prepare(folder, recipe):
    original=DEVICE/'window-30s/source';source=folder/'source'
    shutil.copytree(original,source)
    p=source/'sysmodule/main.c';p.write_text(main_source(p.read_text()))
    p=source/'core.h';p.write_text(p.read_text()+'\n// Main owns the gate: before worker launch until both successful joins.\nvoid CoreSetDiagnosticQuiet(bool quiet);\nbool CoreDiagnosticQuiet(void);\n')
    p=source/'core.c';text=p.read_text()
    text='#include <stdatomic.h>\n'+text
    text=v3.replace(text,'static bool g_coreInitialized = false;', 'static bool g_coreInitialized = false;\n\n'+QUIET_API)
    if text.count('void LogFunctionImpl(const char* fmt, ...)\n{')!=2:raise ValueError('Logger entry drift')
    text=text.replace('void LogFunctionImpl(const char* fmt, ...)\n{','void LogFunctionImpl(const char* fmt, ...)\n{\n    if (CoreDiagnosticQuiet()) return;')
    p.write_text(text)
    (source/'uvc/ep0_candidate_recipe.h').write_text('static const uint8_t ep0CandidateRecipe[32]={'+','.join(map(str,bytes.fromhex(recipe)))+'};\n')
    changed=[p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file() and p.read_bytes()!=(original/p.relative_to(source)).read_bytes()]
    if sorted(changed)!=['core.c','core.h','sysmodule/main.c','uvc/ep0_candidate_recipe.h']:raise ValueError('Unexpected candidate delta')
    return sorted(changed)


def compile_native(source, binary, includes=()):
    cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined',
         *('-I'+str(p) for p in includes),str(source),'-o',str(binary)]
    compiled=subprocess.run(cmd,capture_output=True,text=True)
    if compiled.returncode:raise ValueError(compiled.stderr)
    return cmd


def video_cases(output, folder):
    # Use the actual new video body with the previous modeled services.
    body=v3.capacity.ready.extract((folder/'source/sysmodule/main.c').read_text(),
        'static void VideoStreamThread(void* arg)','// ============================================================================\n// Audio Streaming Thread')
    text=(ROOT/'tests/a23_execution_window_fixture.c').read_text()
    stubs='''static bool Ep0ExecutionWindowStarted(uint64_t a,uint64_t f,uint32_t ms) { assert(a==window_start && f==1000 && ms==30000);return true; }
static bool Ep0ExecutionWindowReady(uint64_t a) { assert(a>=window_start);return true; }
static bool Ep0ExecutionWindowStopped(uint64_t a,uint32_t r) { assert(a==stop_tick && r==1);return true; }
'''
    text=v3.replace(text,'/* INSERT_ACTUAL_VIDEO_THREAD */',stubs+body)
    # Removed production APIs become fail-fast sentinels, including configured streaming.
    text=text.replace('(void)frame;++capture_calls;clock_tick+=capture_ms;return false;',
        '(void)frame;++capture_calls;assert(false);return false;')
    p=output/'video-window.c';p.write_text(text);binary=output/'video-window'
    command=compile_native(p,binary,[folder/'source/uvc'])
    cases={'idle':(0,1,0,0),'streaming':(0,1,0,30000),'process_returns_late':(0,46000,0,0),
           'ready_returns_late':(45000,1,0,0),'bind_before_window':(0,1,45000,99999)}
    rows={n:json.loads(subprocess.check_output([str(binary),*map(str,args)])) for n,args in cases.items()}
    assert all(r['capture_calls']==r['process_calls_started_after_expiry']==0 for r in rows.values())
    return rows,command


def lifecycle_cases(output, folder):
    text=v3.lifecycle_source(folder)
    # The fixture initially models a window that has already begun. Clear is
    # checked against actual successful join observations, including failures.
    text=v3.replace(text,'static unsigned thread_closes;', '''static unsigned thread_closes,join_mask,quiet_clears;
static bool diagnostic_quiet=true;
static void CoreSetDiagnosticQuiet(bool quiet) {
    assert(!quiet && diagnostic_quiet && join_mask==3);diagnostic_quiet=false;quiet_clears++;
}''')
    text=v3.replace(text,'    return 0;\n}\n#define CUR_THREAD_HANDLE',
        '    join_mask|=thread==&g_videoThread?1u:2u;return 0;\n}\n#define CUR_THREAD_HANDLE')
    text=v3.replace(text,'    assert(!opened);', '''    bool failed_join=!strcmp(primary_fault,"video-join-error") || !strcmp(primary_fault,"audio-join-error");
    assert(diagnostic_quiet==failed_join);
    assert(quiet_clears==(failed_join?0u:1u));
    assert(!opened);''')
    text=text.replace('\\"simulation\\":true}', '\\"quiet_after_exit\\":%s,\\"quiet_clears\\":%u,\\"simulation\\":true}')
    text=v3.replace(text,'sink->commit_acknowledged?"true":"false",sink->content_verified?"true":"false");',
        'sink->commit_acknowledged?"true":"false",sink->content_verified?"true":"false",diagnostic_quiet?"true":"false",quiet_clears);')
    p=output/'execution-lifecycle.c';p.write_text(text)
    cmd=compile_native(p,output/'execution-lifecycle',[folder/'source/uvc'])
    faults=v3.capacity.FILE_CASES
    scenarios=list(dict.fromkeys([('ok',f) for f in faults]+[(f,'ok') for f in faults]))
    scenarios += [('video-join-error','ok'),('audio-join-error','ok'),('identity-error','ok')]
    rows=[]
    for kind in ('normal','diagnostic'):
        for primary,sidecar in scenarios:
            prefix=output/f'{kind}-primary-{primary}-execution-{sidecar}'
            row=json.loads(subprocess.check_output([str(output/'execution-lifecycle'),kind,primary,sidecar,str(prefix)]))
            p=Path(str(prefix)+'.execution.bin')
            if p.exists():write(p.with_suffix('.json'),v3.decode_execution(p.read_bytes(),'03'+'00'*31))
            rows.append(row)
    return rows,cmd


def logger_cases(output,folder):
    core=(folder/'source/core.c').read_text();start=core.index('void LogFunctionImpl',core.index('#elif FILE_LOGGING'))
    logger=core[start:core.index('\n#endif',start)]
    text=(ROOT/'tests/a23_file_log_fixture.c').read_text()
    text='#include <stdatomic.h>\n'+text
    text=v3.replace(text,'/* INSERT_LOGGER */',QUIET_API+logger)
    text=v3.replace(text,'/* INSERT_CATALOG */','case 0: LogFunctionImpl("test %u",7u);break;')
    text=v3.replace(text,'    if(!strcmp(scenario,"unmounted"))g_sdMounted=false;',
        '    if(!strcmp(scenario,"unmounted"))g_sdMounted=false;\n'
        '    if(!strcmp(scenario,"quiet"))CoreSetDiagnosticQuiet(true);\n'
        '    if(!strcmp(scenario,"resumed")) { CoreSetDiagnosticQuiet(true);LogFunctionImpl((const char*)1);CoreSetDiagnosticQuiet(false); }')
    p=output/'quiet-logger.c';p.write_text(text);binary=output/'quiet-logger'
    cmd=compile_native(p,binary)
    rows={}
    for scenario in ('quiet','resumed','ok','open-error','size-error','write-error','format-error','unmounted'):
        for n in (0,1,511,512,1024):
            rows[f'{scenario}-{n}']=json.loads(subprocess.check_output([str(binary),scenario,str(n)]))
    assert all(r['formats']==r['opens']==r['sizes']==r['writes']==r['closes']==0 for n,r in rows.items() if n.startswith('quiet-'))
    return rows,cmd


def launch_audio_cases(output,folder):
    main=(folder/'source/sysmodule/main.c').read_text()
    launch=main[main.index('    CoreSetDiagnosticQuiet(true);'):main.index('    // Main thread just sleeps')]
    audio=v3.capacity.ready.extract(main,'static void AudioStreamThread(void* arg)',
        '// ============================================================================\n// Sysmodule Lifecycle')
    text='''#include <assert.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>
'''+QUIET_API+'''
static atomic_bool g_running=true;
static int g_videoThread,g_audioThread,g_videoThreadStack[1],g_audioThreadStack[1];
static unsigned calls,sleeps,seals,fail_at;
static jmp_buf failed;
#define VIDEO_THREAD_STACK_SIZE 20480
#define AUDIO_THREAD_STACK_SIZE 12288
#define STREAM_THREAD_PRIORITY 44
#define LOG(...) assert(CoreDiagnosticQuiet())
static void svcSleepThread(double n) { assert(n==100E+6);assert(CoreDiagnosticQuiet());if(++sleeps==3)g_running=false; }
static void VideoStreamThread(void *arg) { (void)arg; }
'''+audio+'''
static void Ep0StartupBindThreads(int *v,int *a) { assert(v==&g_videoThread && a==&g_audioThread && CoreDiagnosticQuiet()); }
static void LaunchThread(int *t,void (*entry)(void*),void *arg,int *stack,unsigned size,unsigned priority) {
    (void)stack;assert(CoreDiagnosticQuiet() && priority==44);calls++;
    assert((t==&g_videoThread && entry==VideoStreamThread && size==20480) ||
           (t==&g_audioThread && entry==AudioStreamThread && size==12288));
    if(calls==fail_at)longjmp(failed,1);
    if(t==&g_audioThread)entry(arg);
}
static bool Ep0StartupSeal(void) { assert(CoreDiagnosticQuiet());seals++;return true; }
static void launch(void) {
'''+launch+'''
}
int main(int argc,char **argv) {
    assert(argc==2);fail_at=(unsigned)strtoul(argv[1],NULL,10);
    bool retained=false;if(setjmp(failed))retained=true;else launch();
    assert(CoreDiagnosticQuiet() && retained==(fail_at!=0));
    assert(calls==(fail_at?fail_at:2) && sleeps==(fail_at?0:3) && seals==(fail_at?0:1));
    printf("{\\"launches\\":%u,\\"audio_sleeps\\":%u,\\"quiet_retained\\":true,\\"injected_launch_failure\\":%u,\\"simulation\\":true}\\n",calls,sleeps,fail_at);
}
'''
    p=output/'launch-audio.c';p.write_text(text);binary=output/'launch-audio';cmd=compile_native(p,binary)
    return [json.loads(subprocess.check_output([str(binary),str(n)])) for n in (0,1,2)],cmd


def npdm(folder):
    # Explicit configuration path: independent of Makefile's default/override selection.
    dest=folder/'sysmodule.json';shutil.copyfile(REPO/'sysmodule.json',dest)
    command=[str(NPDMTOOL),str(dest),str(folder/'main.npdm')]
    compiled=subprocess.run(command,check=True,capture_output=True,text=True)
    config=json.loads(dest.read_text());raw=(folder/'main.npdm').read_bytes()
    if raw[:4]!=b'META' or len(raw)<0x80:raise ValueError('Invalid NPDM META')
    stack=struct.unpack_from('<I',raw,0x1c)[0]
    if stack!=int(config['main_thread_stack_size'],0) or raw[14]!=config['main_thread_priority'] or raw[15]!=config['default_cpu_id']:
        raise ValueError('NPDM main configuration mismatch')
    # A second, explicitly non-deployable control proves which generated bytes
    # respond to the requested stack value on this installed tool.
    control=dict(config,main_thread_stack_size='0x00004000')
    write(folder/'npdm-control.json',control)
    control_command=[str(NPDMTOOL),str(folder/'npdm-control.json'),str(folder/'npdm-control.npdm')]
    control_result=subprocess.run(control_command,check=True,capture_output=True,text=True)
    write(folder/'npdm-build-results.json',[
        dict(command=command,returncode=compiled.returncode,stdout=compiled.stdout,stderr=compiled.stderr),
        dict(command=control_command,returncode=control_result.returncode,stdout=control_result.stdout,stderr=control_result.stderr)])
    other=(folder/'npdm-control.npdm').read_bytes()
    if len(other)!=len(raw) or other[:0x1c]!=raw[:0x1c] or other[0x20:]!=raw[0x20:] or struct.unpack_from('<I',other,0x1c)[0]!=16384:
        raise ValueError('NPDM stack perturbation control mismatch')
    return dict(config_sha256=sha(dest),npdm_sha256=sha(folder/'main.npdm'),tool_sha256=sha(NPDMTOOL),
        main_thread_stack_request_bytes=stack,main_thread_priority=raw[14],default_cpu_id=raw[15],
        meta_stack_offset=28,perturbation_control_verified=True,explicit_config_path=True,
        actual_kernel_thread_budget_verified=False,loaded_on_device=False),command


def quiet_guard_certificate(functions,metadata):
    """Check one conditional machine path afresh; no old address/model reuse.

    This proves the syntactic guard path for an already true atomic byte. It
    does not prove the scheduler, all SDK callbacks, or physical stack budget.
    """
    byname={n:f for f in functions.values() for n in f['aliases']}
    flags=[s for s in metadata['symbols'] if s['name']=='g_diagnosticQuiet' and s['type']==1 and s['size']==1]
    if len(flags)!=1:raise ValueError('Quiet flag symbol missing/ambiguous')
    flag=flags[0]['address'];logger=byname['LogFunctionImpl'];code=logger['instructions'];start=logger['start']
    prefix=[('sub','sp, sp, #0x340'),('adrp',f'x8, {flag&~4095:x} <g_diagnosticQuiet>'),
            ('add',f'x8, x8, #0x{flag&4095:x}'),('add','x9, sp, #0x280'),
            ('stp','x29, x30, [sp]'),('mov','x29, sp')]
    for i in range(8):
        if i:prefix.append(('add',f'x9, sp, #0x{0x280+i*16:x}'))
        prefix.append(('str',f'q{i}, [x9]'))
    prefix += [('add','x9, sp, #0x308'),('stp','x1, x2, [x9]'),('stp','x3, x4, [x9, #16]'),
               ('str','x5, [sp, #808]'),('str','x6, [sp, #816]'),('str','x7, [sp, #824]'),('ldarb','w1, [x8]')]
    if [(op,arg) for _,op,arg in code[:len(prefix)]]!=prefix:raise ValueError('Quiet logger prefix drift')
    pc,op,arg=code[len(prefix)]
    branch=re.fullmatch(r'w1, #0, ([0-9a-f]+) <LogFunctionImpl\+0x[0-9a-f]+>',arg)
    if op!='tbnz' or not branch:raise ValueError('Quiet branch drift')
    target=int(branch[1],16);mapping={pc:(op,arg) for pc,op,arg in code}
    epilogue=[('ldp','x29, x30, [sp]'),('add','sp, sp, #0x340'),('ret','')]
    if [mapping.get(target+i*4) for i in range(3)]!=epilogue:raise ValueError('Quiet epilogue drift')
    setter=byname['CoreSetDiagnosticQuiet']
    if [(op,arg) for _,op,arg in setter['instructions']]!=[
        ('adrp',f'x1, {flag&~4095:x} <g_diagnosticQuiet>'),('add',f'x1, x1, #0x{flag&4095:x}'),
        ('stlrb','w0, [x1]'),('ret','')]:raise ValueError('Quiet release store drift')
    return dict(schema='A23-quiet-guard-path-1',flag_address=flag,logger_address=start,
        logger_function_sha256=elf.function_digest(logger),setter_function_sha256=elf.function_digest(setter),
        quiet_branch_at=pc,quiet_return_at=target+8,quiet_path_instruction_count=len(prefix)+4,
        conditional_held_stack_bytes=832,acquire_load_and_release_store_verified=True,
        quiet_true_path_calls=[],format_or_filesystem_reached_on_quiet_true_path=False,
        stack_writes_still_performed=True,atomic_byte_true_and_valid_stack_assumed=True,
        actual_arm_executed=False,whole_thread_stack_verified=False)


def linked_checks(folder,recipe):
    blob=(folder/'full.elf').read_bytes();text=subprocess.check_output([
        '/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump','-d',str(folder/'full.elf')],text=True)
    (folder/'disassembly.txt').write_text(text)
    functions,metadata=elf.build_functions(blob,text)
    byname={n:f for f in functions.values() for n in f['aliases']}
    roots={}
    for name in ('VideoStreamThread','AudioStreamThread'):
        pending=[byname[name]['start']];seen=set();unresolved=[];calls=[]
        while pending:
            a=pending.pop()
            if a in seen:continue
            seen.add(a)
            for pc,op,arg in functions[a]['instructions']:
                if op in ('blr','br'):unresolved.append(dict(function=functions[a]['name'],at=pc,op=op))
                if op in ('b','bl'):
                    m=re.fullmatch(r'([0-9a-f]+) <([^>]+)>',arg)
                    if m and int(m[1],16) in functions and int(m[1],16)!=a:
                        pending.append(int(m[1],16));calls.append(m[2])
        forbidden={'CaptureReadVideoFrame','CaptureReadAudioFrame','UvcDeviceSendFrame','UacDeviceSendAudio'}
        if forbidden.intersection(calls):raise ValueError('Production capture reachable')
        roots[name]=dict(direct_reachable_functions=sorted(functions[a]['name'] for a in seen),
                        indirect_sites=unresolved,production_capture_on_direct_graph=False,
                        all_indirect_edges_resolved=not unresolved)
    symbols=[s for s in metadata['symbols'] if s['name']=='ep0CandidateRecipe' and s['type']==1]
    def at(a,n):
        s=next(s for s in metadata['sections'] if s['flags']&2 and s['address']<=a and a+n<=s['address']+s['size'])
        off=s['offset']+a-s['address'];return blob[off:off+n]
    if len(symbols)!=2 or any(at(s['address'],32)!=bytes.fromhex(recipe) for s in symbols):raise ValueError('ELF recipe binding mismatch')
    logger=byname['LogFunctionImpl']
    (folder/'logger-disassembly.json').write_text(json.dumps(logger,indent=2)+'\n')
    return dict(elf_sha256=sha(folder/'full.elf'),recipe_addresses=[s['address'] for s in symbols],
        runtime_recipe_sha256=recipe,worker_graphs=roots,
        logger_function_sha256=elf.function_digest(logger),logger_function_address=logger['start'],
        quiet_guard_path=quiet_guard_certificate(functions,metadata),
        old_address_certificates_reused=False,whole_thread_stack_verified=False,
        quiet_guard_arm_execution_verified=False)


def run(output,arm=True):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Refusing existing output: '+str(output))
    seals=[verify(p) for p in (PARENT,DEVICE)]
    sources=source_hashes();old=json.loads((DEVICE/'audit.json').read_text())
    protected={n:sha(REPO/n) for n in old['production_sources_sha256']}
    tickets={n:sha(DEVICE.parent/n) for n in old['tickets_sha256']}
    if protected!=old['production_sources_sha256'] or tickets!=old['tickets_sha256']:raise ValueError('Protected source/ticket drift')
    extra={'sysmodule.json':sha(REPO/'sysmodule.json'),'Makefile':sha(REPO/'Makefile')}
    external={n:sha(n) for n in old['external_sha256']}
    if external!=old['external_sha256']:raise ValueError('Toolchain drift')
    external[str(NPDMTOOL)]=sha(NPDMTOOL)
    headers={n:sha(Path('/opt/devkitpro/libnx/include')/n) for n in old['sdk_headers_sha256']}
    if headers!=old['sdk_headers_sha256']:raise ValueError('SDK header drift')
    recipe=digest(dict(schema='A23-quiet-window-recipe-1',sources=sources,config=extra,external=external,
        sdk_headers=headers,device_manifest=sha(DEVICE/'SHA256SUMS'),parent_manifest=sha(PARENT/'SHA256SUMS'),
        window_ms=30000,diagnostic_pacing_ns=1000000,production_capture=False,quiet_until_both_joins=True))
    output.mkdir(parents=True);folder=output/'window-30s';changed=prepare(folder,recipe)
    write(folder/'recipe.json',dict(schema='A23-quiet-window-recipe-1',input_digest=recipe,
        parent_input_digest=old['recipe_digest'],parent_runtime_recipe=old['builds']['window-30s']['runtime_recipe_digest'],
        window_ms=30000,diagnostic_pacing_ns=1000000,production_capture=False,quiet_until_both_joins=True,
        source_hashes=sources,config_hashes=extra))
    commands=[];rows={}
    for name,method in (('video',video_cases),('lifecycle',lifecycle_cases),('logger',logger_cases),('launch_audio',launch_audio_cases)):
        rows[name],command=method(output,folder);commands.append(command)
    configuration,command=npdm(folder);commands.append(command)
    build=None;binding=None
    if arm:
        build=v3.compile_arm(folder,commands)
        strict=[]
        for cmd in list(commands):
            if '-c' not in cmd:continue
            check=[cmd[0],*[v for v in cmd[1:cmd.index('-c')] if v!='-fstack-usage'],
                '-Wformat=2','-fsyntax-only',cmd[cmd.index('-c')+1]]
            subprocess.run(check,check=True,capture_output=True,text=True);commands.append(check);strict.append(check[-1])
        if len(strict)!=13:raise ValueError('Expected 13 strict units')
        build['strict_format_units']=len(strict);build['linked_checks']=linked_checks(folder,recipe)
        files=('full.elf','recipe.json','symbols.txt','source/uvc/ep0_candidate_recipe.h','sysmodule.json','main.npdm')
        binding=dict(schema='A23-quiet-device-binding-1',runtime_recipe_sha256=recipe,
            device_elf_sha256=sha(folder/'full.elf'),npdm_sha256=sha(folder/'main.npdm'),
            config_sha256=sha(folder/'sysmodule.json'),main_thread_stack_request_bytes=configuration['main_thread_stack_request_bytes'],
            artifact_hashes={n:sha(folder/n) for n in files},software_material_agreement_only=True,
            host_receiver_rebound=False,actual_kernel_thread_budget_verified=False)
        write(folder/'device-binding.json',binding)
    for name in sources:
        p=output/'inputs'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/name,p)
    for name in extra:shutil.copyfile(REPO/name,output/'inputs'/name)
    for group,base in ((sources,REPO),(protected,REPO),(tickets,DEVICE.parent),(extra,REPO),(external,Path('/')),(headers,Path('/opt/devkitpro/libnx/include'))):
        if group!={n:sha(base/n) for n in group}:raise ValueError('Inputs changed during build')
    for p in (PARENT,DEVICE):verify(p)
    result=dict(schema='A23-quiet-window-candidate-1',runtime_recipe_sha256=recipe,source_hashes=sources,
        production_sources_sha256=protected,tickets_sha256=tickets,config_sources_sha256=extra,
        external_sha256=external,sdk_headers_sha256=headers,sealed_inputs=seals,changed_files=changed,
        cases=rows,npdm=configuration,build=build,device_binding=binding,compiler_commands=commands,
        native_execution_count=sum(len(v) for v in rows.values()),usb_accessed=False,sd_accessed=False,
        attempt_issued=False,arm_executed=False,firmware_packaged=False,deployed=False,
        host_receiver_rebound=False,root_cause_confirmed=False,whole_thread_stack_verified=False,
        synchronous_call_time_bound_verified=False)
    write(output/'audit.json',result);seal(output);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native-only',action='store_true');args=parser.parse_args()
    result=run(args.output,arm=not args.native_only)
    print(json.dumps(dict(output=str(args.output),recipe=result['runtime_recipe_sha256'],native_executions=result['native_execution_count'],build=result['build']),indent=2))


if __name__=='__main__':main()
