#!/usr/bin/env python3
"""Build a separate LCP1 device candidate, never package, deploy, issue or run ARM."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

import audit_a23_lifecycle_capsule as parent
import build_a23_quiet_candidate as quiet

b=parent.b;ROOT=parent.ROOT;ANALYSIS=parent.ANALYSIS
PARENT=ANALYSIS/'A23-lifecycle-capsule-review-20261016'
DEVICE=parent.package.DEVICE
NEW=('device/ep0_lifecycle_file.h','device/ep0_lifecycle_file.c','tools/build_a23_lifecycle_candidate.py',
     'tests/a23_lifecycle_file_fixture.c','tests/a23_lifecycle_startup_fixture.c','tests/test_a23_lifecycle_candidate.py')
MODEL_RECIPE='03'+'00'*31

MAIN=r'''int main(int argc, char* argv[])
{
    (void)argc;(void)argv;
    LOG("SysDVR-UVC starting...\n");
    Result life_rc=Ep0LifePrepare(ep0CandidateRecipe);
    if(R_FAILED(life_rc)) {
        LOG("Lifecycle prepare failed phase=%u rc=0x%x\n",Ep0LifeLastPhase(),life_rc);
        return 1; /* No USB initialization or worker launch after preparation failure. */
    }
    UvcDeviceConfig uvcConfig={.vendorId=UVC_VENDOR_ID,.productId=UVC_PRODUCT_ID,
        .manufacturer="Nintendo Switch",.product="SysDVR-UVC Capture",.serialNumber=CoreGetSerialNumber()};
    (void)Ep0LifeNote(EP0_L_USB_INIT_CALL,0,0,0);
    Result rc=UvcDeviceInitialize(&uvcConfig);
    (void)Ep0LifeNote(EP0_L_USB_INIT_RESULT,rc,0,0);
    if(R_FAILED(rc)) {
        LOG("UvcDeviceInitialize failed: 0x%x\n",rc);
        (void)Ep0StartupSeal();(void)Ep0SessionStartupOnly(ep0CandidateRecipe);
        Ep0LifeFinish(EP0_L_MAIN_RETURN,1,1);return 1;
    }
    CaptureSetInjectSPSPPS(true);
    (void)Ep0LifeNote(EP0_L_QUIET_ENTER,0,0,0);
    CoreSetDiagnosticQuiet(true);
    Ep0StartupBindThreads(&g_videoThread,&g_audioThread);
    LaunchThread(&g_videoThread,VideoStreamThread,NULL,g_videoThreadStack,VIDEO_THREAD_STACK_SIZE,STREAM_THREAD_PRIORITY);
    LaunchThread(&g_audioThread,AudioStreamThread,NULL,g_audioThreadStack,AUDIO_THREAD_STACK_SIZE,STREAM_THREAD_PRIORITY);
    (void)Ep0StartupSeal();
    LOG("SysDVR-UVC diagnostic running (USB requests only)\n");
    // Main thread just sleeps - all work is done in streaming threads
    while (g_running) { svcSleepThread(1E+9); }

    g_running = false;
    (void)Ep0LifeNote(EP0_L_MAIN_LOOP_LEFT,0,0,0);
    bool cleanup_started=ep0_cleanup_begin(&ep0Cleanup);
    (void)Ep0LifeNote(EP0_L_CLEANUP_RESULT,cleanup_started,0,0);
    if(!cleanup_started) { Ep0LifeFinish(EP0_L_RETAIN,0,1);for(;;)svcSleepThread(1E+9); }
    (void)Ep0LifeNote(EP0_L_VIDEO_JOIN_CALL,0,0,0);
    Result video_join=threadWaitForExit(&g_videoThread);
    (void)Ep0LifeNote(EP0_L_VIDEO_JOIN_RESULT,video_join,0,0);
    (void)Ep0LifeNote(EP0_L_AUDIO_JOIN_CALL,0,0,0);
    Result audio_join=threadWaitForExit(&g_audioThread);
    (void)Ep0LifeNote(EP0_L_AUDIO_JOIN_RESULT,audio_join,0,0);
    uint64_t exporter=0;Result identity_rc=svcGetThreadId(&exporter,CUR_THREAD_HANDLE);
    (void)Ep0LifeNote(EP0_L_EXPORTER_RESULT,identity_rc,0,0);
    if(R_FAILED(video_join) || R_FAILED(audio_join)) {
        (void)Ep0SessionJoined(ep0CandidateRecipe,exporter,video_join,audio_join,false);
        Ep0LifeFinish(EP0_L_RETAIN,video_join?video_join:audio_join,2);for(;;)svcSleepThread(1E+9);
    }
    CoreSetDiagnosticQuiet(false);
    if(R_FAILED(identity_rc)) {
        (void)Ep0SessionStartupOnly(ep0CandidateRecipe);
        Ep0LifeFinish(EP0_L_RETAIN,identity_rc,3);for(;;)svcSleepThread(1E+9);
    }
    const Ep0TraceOwner *life_owner=Ep0CandidateObservation();
    (void)Ep0LifeContext(life_owner->trace.boot_id,life_owner->trace.session_id);
    bool ownership_ready=Ep0CandidateFinish(exporter,video_join);
    (void)Ep0LifeNote(EP0_L_OWNER_FINISH_RESULT,ownership_ready,0,0);
    if(!ownership_ready) {
        (void)Ep0LifeNote(EP0_L_PRIMARY_SAVE_CALL,0,2,0);
        bool diagnostic_saved=Ep0CandidateSaveDiagnostic(exporter,video_join,audio_join,ep0CandidateRecipe);
        const Ep0SinkState *observation=Ep0CandidateDiagnosticFileObservation();
        (void)Ep0LifeNote(EP0_L_PRIMARY_SAVE_RESULT,diagnostic_saved,observation->phase,observation->result);
        (void)Ep0SessionJoined(ep0CandidateRecipe,exporter,video_join,audio_join,true);
        bool built=Ep0ExecutionBuildJoined(exporter,video_join,audio_join,2,diagnostic_saved);
        (void)Ep0LifeNote(EP0_L_EXEC_BUILD_RESULT,built,2,0);
        if(built) {
            (void)Ep0LifeNote(EP0_L_EXEC_SAVE_CALL,0,0,0);
            bool saved=Ep0ExecutionSaveJoined(video_join,audio_join);
            observation=Ep0ExecutionFileObservation();
            (void)Ep0LifeNote(EP0_L_EXEC_SAVE_RESULT,saved,observation->phase,observation->result);
        }
        Ep0LifeFinish(EP0_L_RETAIN,0,4);for(;;)svcSleepThread(1E+9);
    }
    (void)Ep0LifeNote(EP0_L_PRIMARY_SAVE_CALL,0,1,0);
    bool normal_saved=Ep0CandidateSaveCapture();
    const Ep0SinkState *observation=Ep0CandidateFileObservation();
    (void)Ep0LifeNote(EP0_L_PRIMARY_SAVE_RESULT,normal_saved,observation->phase,observation->result);
    (void)Ep0SessionJoined(ep0CandidateRecipe,exporter,video_join,audio_join,false);
    bool built=Ep0ExecutionBuildJoined(exporter,video_join,audio_join,1,normal_saved);
    (void)Ep0LifeNote(EP0_L_EXEC_BUILD_RESULT,built,1,0);
    bool execution_saved=false;
    if(built) {
        (void)Ep0LifeNote(EP0_L_EXEC_SAVE_CALL,0,0,0);
        execution_saved=Ep0ExecutionSaveJoined(video_join,audio_join);
        observation=Ep0ExecutionFileObservation();
        (void)Ep0LifeNote(EP0_L_EXEC_SAVE_RESULT,execution_saved,observation->phase,observation->result);
    }
    if(!normal_saved || !execution_saved) { Ep0LifeFinish(EP0_L_RETAIN,0,5);for(;;)svcSleepThread(1E+9); }
    threadClose(&g_videoThread);threadClose(&g_audioThread);
    if(!ep0_cleanup_authorize(&ep0Cleanup)) { Ep0LifeFinish(EP0_L_RETAIN,0,6);for(;;)svcSleepThread(1E+9); }
    LOG("SysDVR-UVC exiting\n");
    Ep0LifeFinish(EP0_L_MAIN_RETURN,0,0);return 0;
}
'''


def replace(text,old,new):
    b.require(text.count(old)==1,'source anchor drift: '+old[:80]);return text.replace(old,new)


def prepare(folder,recipe):
    original=DEVICE/'source';shutil.copytree(original,folder/'source');source=folder/'source'
    main=(source/'sysmodule/main.c').read_text();main=main[:main.index('int main(int argc, char* argv[])')]+MAIN
    (source/'sysmodule/main.c').write_text('#include "../uvc/ep0_lifecycle_file.h"\n'+main)
    for n in ('ep0_lifecycle_capsule.h','ep0_lifecycle_file.h','ep0_lifecycle_file.c'):
        shutil.copyfile(ROOT/'device'/n,source/'uvc'/n)
    header=source/'uvc/ep0_lifecycle_capsule.h';original_header=header.read_text()
    formatted=replace(original_header,'if(!p)return false;uint8_t x=0;', 'if(!p)return false;\n uint8_t x=0;')
    formatted=replace(formatted,'if(joined_context32)memcpy(r+32,joined_context32,32);ep0_lcp_u32',
        'if(joined_context32)memcpy(r+32,joined_context32,32);\n ep0_lcp_u32')
    b.require(''.join(original_header.split())==''.join(formatted.split()),'header formatting changed tokens')
    header.write_text(formatted)  # Resolve GCC indentation diagnostics without modifying the frozen prototype.
    (source/'uvc/ep0_candidate_recipe.h').write_text('static const uint8_t ep0CandidateRecipe[32]={'+','.join(map(str,bytes.fromhex(recipe)))+'};\n')
    for name,role in (('ep0_candidate_file.c',1),('ep0_diagnostic_file.c',2),('ep0_session_file.c',3)):
        path=source/'uvc'/name;text=path.read_text();text='#include "ep0_lifecycle_file.h"\n'+text
        marker='    Result rc=fsFsCreateFile(&io->fs,path,n,0);'
        text=replace(text,marker,
            f'    (void)Ep0LifeNote(EP0_L_FILE_CREATE_CALL,0,{role},(uint32_t)n);\n'+marker+
            f'\n    (void)Ep0LifeNote(EP0_L_FILE_CREATE_RESULT,rc,{role},(uint32_t)n);')
        marker='Result rc=fsOpenSdCardFileSystem(&io.fs);'
        if name=='ep0_session_file.c':
            # Only EXE3, not the unused REL2 save entry. The shared create adapter role is
            # explicitly "session-sidecar" (3), not a general EXE3 provenance assertion.
            split=text.index('bool Ep0ExecutionSaveJoined(');head,tail=text[:split],text[split:]
            tail=replace(tail,marker,f'(void)Ep0LifeNote(EP0_L_SD_OPEN_CALL,0,{role},0);'+marker+
                f'(void)Ep0LifeNote(EP0_L_SD_OPEN_RESULT,rc,{role},0);');text=head+tail
        else:
            text=replace(text,marker,f'(void)Ep0LifeNote(EP0_L_SD_OPEN_CALL,0,{role},0);'+marker+
                f'(void)Ep0LifeNote(EP0_L_SD_OPEN_RESULT,rc,{role},0);')
        path.write_text(text)
    changed=sorted(p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file() and
        (not (original/p.relative_to(source)).exists() or p.read_bytes()!=(original/p.relative_to(source)).read_bytes()))
    b.require(len(changed)==8,'unexpected generated source delta');return changed


def compile_model(source,binary,folder):
    command=['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=address,undefined',
        '-I'+str(folder/'source/uvc'),str(source),'-o',str(binary)]
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if result.returncode:raise ValueError(result.stdout.decode())
    return command


def adapter_models(output,folder):
    source=output/'file-adapter-model.c';shutil.copyfile(ROOT/'tests/a23_lifecycle_file_fixture.c',source)
    binary=output/'file-adapter-model';command=compile_model(source,binary,folder);rows={}
    for scenario in ('ok','identity-error','zero-nonce','sd-open-error','create-error','collision','open-error','write-error',
                     'flush-error','size-error','short-size','read-error','short-read','zero-read','oversize-read','corrupt-write','commit-error','header-commit-error','record-commit-error','record-write-error','wrong-writer'):
        path=output/('adapter-'+scenario+'.bin')
        row=json.loads(subprocess.check_output([str(binary),scenario,str(path)]))
        if row['header_valid']:
            row['decoded']=parent.capsule.decode(b.plain(path),MODEL_RECIPE)
        rows[scenario]=row
    return rows,command


def startup_models(output,folder):
    main=(folder/'source/sysmodule/main.c').read_text();start=main.index('int main(int argc, char* argv[])')
    prefix=main[start:main.index('    // Main thread just sleeps',start)].replace('int main(', 'static int replay_start(')
    fixture=(ROOT/'tests/a23_lifecycle_startup_fixture.c').read_text().replace('/* ACTUAL_STARTUP_BODY */',prefix+'    return 42;\n}\n')
    source=output/'startup-model.c';source.write_text(fixture);binary=output/'startup-model';command=compile_model(source,binary,folder)
    rows={name:json.loads(subprocess.check_output([str(binary),name])) for name in ('ok','prepare-error','usb-error')}
    return rows,command


def lifecycle_models(output,folder):
    text=quiet.v3.lifecycle_source(DEVICE)
    old_main=(DEVICE/'source/sysmodule/main.c').read_text()
    old_tail=old_main[old_main.index('    g_running = false;\n    if(!ep0_cleanup_begin'):]
    new_main=(folder/'source/sysmodule/main.c').read_text()
    new_tail=new_main[new_main.index('    g_running = false;\n    (void)Ep0LifeNote(EP0_L_MAIN_LOOP_LEFT'):]
    text=replace(text,old_tail,new_tail)
    text=replace(text,'#include <setjmp.h>','#include <setjmp.h>\n#include "ep0_lifecycle_file.h"')
    observer=r'''
static Ep0LifecycleCapsule model_capsule;
static uint8_t model_disk[EP0_LCP_MAX];static uint64_t model_tick;
static unsigned model_writes,model_close_count,join_mask;
static uint32_t model_write(void *unused,size_t off,const void *bytes,size_t n) {
    (void)unused;assert(off+n<=sizeof(model_disk));memcpy(model_disk+off,bytes,n);model_writes++;
    return !strcmp(execution_fault,"journal-write-error") && model_writes==4 ? 99:0;
}
bool Ep0LifeNote(unsigned stage,uint32_t rc,uint32_t a,uint32_t d) {
    return ep0_lcp_note(&model_capsule,22,stage,++model_tick,rc,a,d,NULL);
}
bool Ep0LifeContext(const uint8_t *boot_id,const uint8_t *session_id) {
    assert(join_mask==3);uint8_t context[32];memcpy(context,boot_id,16);memcpy(context+16,session_id,16);
    return ep0_lcp_note(&model_capsule,22,EP0_L_CONTEXT,++model_tick,0,0,0,context);
}
void Ep0LifeClose(void) { model_close_count++; }
void Ep0LifeFinish(unsigned stage,uint32_t rc,uint32_t why) { (void)Ep0LifeNote(stage,rc,why,0);Ep0LifeClose(); }
static void CoreSetDiagnosticQuiet(bool quiet) { assert(!quiet && join_mask==3); }
'''
    text=replace(text,'static void append(',observer+'\nstatic void append(')
    text=replace(text,'    return 0;\n}\n#define CUR_THREAD_HANDLE','    join_mask|=thread==&g_videoThread?1u:2u;return 0;\n}\n#define CUR_THREAD_HANDLE')
    text=replace(text,'    if(setjmp(retained_jump))retained=true;else exit_code=replay_exit();',
        '    uint8_t life_nonce[16]={7};assert(ep0_lcp_init(&model_capsule,NULL,model_write,22,1000,0,life_nonce,recipe));\n'
        '    assert(Ep0LifeNote(EP0_L_PREPARED,0,0,0));assert(Ep0LifeNote(EP0_L_QUIET_ENTER,0,0,0));\n'
        '    if(setjmp(retained_jump))retained=true;else exit_code=replay_exit();\n'
        '    assert(model_close_count==1 && (!model_capsule.disabled || !strcmp(execution_fault,"journal-write-error")));\n'
        '    save(argv[4],"lifecycle.bin",model_disk,sizeof(model_disk));')
    text=replace(text,'bool execution_good=!strcmp(execution_fault,"ok") || !strcmp(execution_fault,"short-read");',
        'bool execution_good=!strcmp(execution_fault,"ok") || !strcmp(execution_fault,"short-read") || !strcmp(execution_fault,"journal-write-error");')
    source=output/'exit-model.c';source.write_text(text);binary=output/'exit-model';command=compile_model(source,binary,folder)
    scenarios=[('ok','ok'),('fs-open-error','ok'),('create-error','ok'),('commit-error','ok'),
               ('ok','fs-open-error'),('ok','create-error'),('ok','commit-error'),
               ('video-join-error','ok'),('audio-join-error','ok'),('identity-error','ok'),('ok','journal-write-error')]
    rows={}
    for kind in ('normal','diagnostic'):
        for primary,execution in scenarios:
            name=f'{kind}-{primary}-{execution}';prefix=output/name
            row=json.loads(subprocess.check_output([str(binary),kind,primary,execution,str(prefix)]))
            decoded=parent.capsule.decode(b.plain(Path(str(prefix)+'.lifecycle.bin')),MODEL_RECIPE)
            b.require(decoded['error'] is None and decoded['tail']=='zero_tail','invalid lifecycle model')
            row['capsule']=decoded;rows[name]=row
    return rows,command


def run(output,*,arm=True):
    output=parent.package.output_path(output);parent.package.verify(PARENT)
    prior=b.load(PARENT/'audit.json');hashes=dict(prior['source_hashes']);b.require(len(hashes)==189,'parent source inventory')
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'parent source drift: '+n)
    protected=b.load(PARENT/'protected-inputs.json');record=ANALYSIS/'A23-quiet-once-20261016-interface2.json';record_raw=b.plain(record)
    for n in NEW:hashes['research/usb-ds-iso/'+n]=b.sha(b.plain(ROOT/n))
    old=b.load(parent.package.device.DEVICE/'audit.json')
    for n,h in old['external_sha256'].items():b.require(quiet.sha(n)==h,'toolchain drift: '+n)
    for n,h in old['sdk_headers_sha256'].items():b.require(quiet.sha(Path('/opt/devkitpro/libnx/include')/n)==h,'SDK header drift: '+n)
    recipe=quiet.digest(dict(schema='A23-lifecycle-device-recipe-1',source_hashes=hashes,parent_manifest=b.sha(b.plain(PARENT/'SHA256SUMS')),
        device_elf_sha256=b.sha(b.plain(DEVICE/'full.elf')),npdm_sha256=b.sha(b.plain(DEVICE/'main.npdm')),window_ms=30000))
    output.mkdir(mode=0o700,parents=True);folder=output/'candidate';changed=prepare(folder,recipe)
    for name in ('main.npdm','sysmodule.json'):shutil.copyfile(DEVICE/name,folder/name)
    b.write(folder/'recipe.json',dict(schema='A23-lifecycle-device-recipe-1',runtime_recipe_sha256=recipe,parent_runtime_recipe=b.load(DEVICE/'recipe.json')['input_digest'],window_ms=30000,source_hashes=hashes))
    commands=[];models={}
    for name,method in (('adapter',adapter_models),('startup',startup_models),('lifecycle',lifecycle_models)):
        models[name],command=method(output,folder);commands.append(command)
    build=None;binding=None
    if arm:
        build=quiet.v3.compile_arm(folder,commands)
        strict=[]
        for cmd in list(commands):
            if '-c' not in cmd:continue
            check=[cmd[0],*[x for x in cmd[1:cmd.index('-c')] if x!='-fstack-usage'],'-Wformat=2','-fsyntax-only',cmd[cmd.index('-c')+1]]
            subprocess.run(check,check=True,capture_output=True,text=True);strict.append(check);commands.append(check)
        b.require(len(strict)==14,'expected 14 strict units');build['strict_format_units']=len(strict)
        build['linked_checks']=quiet.linked_checks(folder,recipe)
        functions,_=quiet.elf.build_functions(b.plain(folder/'full.elf'),(folder/'disassembly.txt').read_text())
        from analyze_a23_session_stack import frame
        wanted=('main','Ep0LifePrepare','Ep0LifeNote','Ep0LifeContext','Ep0LifeFinish','life_write_once','life_transfer')
        machine={}
        for name in wanted:
            variants=[f for f in functions.values() if any(a==name or a.startswith(name+'.') for a in f['aliases'])]
            b.require(variants,'missing lifecycle machine function: '+name)
            machine[name]=dict(variants=[dict(address=f['start'],aliases=f['aliases'],function_sha256=quiet.elf.function_digest(f),
                frame=frame(f,functions)) for f in variants])
        build['lifecycle_machine_review']=machine
        files=('full.elf','recipe.json','symbols.txt','source/uvc/ep0_candidate_recipe.h','main.npdm','sysmodule.json')
        binding=dict(schema='A23-lifecycle-device-material-1',runtime_recipe_sha256=recipe,parent_runtime_recipe=b.load(DEVICE/'recipe.json')['input_digest'],
            device_elf_sha256=b.sha(b.plain(folder/'full.elf')),artifact_hashes={n:b.sha(b.plain(folder/n)) for n in files},
            main_thread_stack_request_bytes=8192,actual_kernel_thread_budget_verified=False,host_receiver_rebound=False)
        b.write(folder/'device-binding.json',binding)
    for n in NEW:parent.package.put(output,'inputs/'+n,b.plain(ROOT/n))
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'source changed: '+n)
    for n,h in old['external_sha256'].items():b.require(quiet.sha(n)==h,'toolchain changed: '+n)
    for n,h in old['sdk_headers_sha256'].items():b.require(quiet.sha(Path('/opt/devkitpro/libnx/include')/n)==h,'SDK header changed: '+n)
    for n,h in protected['production'].items():b.require(b.sha(b.plain(b.REPO/n))==h,'production drift')
    for group in ('tickets','offline_records_sha256'):
        for n,h in protected[group].items():b.require(b.sha(b.plain(ANALYSIS/n))==h,'record drift')
    b.require(b.plain(record)==record_raw,'live record changed')
    result=dict(schema='A23-lifecycle-device-candidate-1',source_hashes=hashes,prior_sources=189,changed_files=changed,
        runtime_recipe_sha256=recipe,models=models,model_count=sum(len(v) for v in models.values()),build=build,device_binding=binding,
        compiler_commands=commands,real_sdk_adapter_source_integrated=True,device_elf_built=arm,arm_executed=False,
        actual_fs_service_verified=False,firmware_packaged=False,deployed=False,host_receiver_rebound=False,
        sd_accesses=0,usb_requests=0,attempt_issued=False,remaining=0,root_cause_confirmed=False,whole_thread_stack_verified=False)
    b.write(output/'audit.json',result);b.write(output/'protected-inputs.json',protected);parent.package.put(output,'live-record-snapshot.json',record_raw)
    b.seal(output);parent.package.verify(output);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);parser.add_argument('--native-only',action='store_true');args=parser.parse_args()
    result=run(args.output,arm=not args.native_only);print(json.dumps(dict(recipe=result['runtime_recipe_sha256'],models=result['model_count'],arm_built=result['device_elf_built'])))
