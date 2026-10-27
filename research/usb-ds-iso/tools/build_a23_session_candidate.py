#!/usr/bin/env python3
"""New full ARM REL1 candidate, actual startup hooks and modeled FS shutdowns."""
import argparse,hashlib,json,os,re,shutil
from pathlib import Path
import build_a23_session_correlation as correlation
from analyze_ep0_session import decode_session
from analyze_ep0_startup import decode_startup,STEPS
from workflows.artifacts import verify
startup=correlation.startup;base=correlation.base;ROOT=correlation.ROOT
SEALED=correlation.SEALED;PROTOTYPE=base.ep0.PRIVATE/'analysis/A23-session-correlation-review-20261014'
DEVICE=('ep0_session_capture.h','ep0_session_runtime.h','ep0_session_runtime.c','ep0_session_sink.h','ep0_session_file.h','ep0_session_file.c')
INPUTS=(*('device/'+n for n in DEVICE),'tools/build_a23_session_candidate.py')
r=base.trace.replace
BRIDGE='''
const Ep0StartupJournal *Ep0StartupJournalForSession(void) { return Ep0StartupStatus()==2 ? &startup:NULL; }
uint64_t Ep0StartupWriterForSession(void) { return Ep0StartupStatus()==2 ? startup_writer:0; }
'''
STARTUP_CASES=(*startup.startup.CASES,*startup.EXTRA_CASES,'full-launch')
SHUTDOWN_CASES=(*startup.startup.sink.SHUTDOWN_CASES,'startup-identity-error','startup-zero-writer','bind-skipped','session-write-error','session-commit-error','session-collision')
FILE_CASES=('ok','short-read','fs-open-error','create-error','collision','file-open-error','write-error','silent-short-write',
    'corrupt-write','flush-error','size-error','extra-byte','short-size','read-error','late-read-error','zero-read','oversize-read','commit-error','maximum','maximum-short-read')

def native_device(name):
    return re.sub(r'#include "(ep0_[^"]+)"',r'#include "research/usb-ds-iso/device/\1"',(ROOT/'device'/name).read_text())

def fatal_hook(s):return s.replace('Ep0StartupFatal(rc);','Ep0StartupFatal(rc);\n        (void)Ep0SessionStartupOnly(ep0CandidateRecipe);')

def main_source(s):
    s='#include "../uvc/ep0_session_runtime.h"\n#include "../uvc/ep0_session_file.h"\n'+fatal_hook(s)
    s=r(s,'    Ep0CandidateWindow window={0};','    (void)Ep0SessionBind(writer,boot_nonce,session_nonce,ep0CandidateRecipe);\n    Ep0CandidateWindow window={0};')
    s=r(s,'        (void)Ep0StartupSeal();\n        return 1;','        (void)Ep0StartupSeal();\n        (void)Ep0SessionStartupOnly(ep0CandidateRecipe);\n        return 1;')
    s=r(s,'''    if(R_FAILED(video_join) || R_FAILED(audio_join) || R_FAILED(identity_rc)) {
        for(;;)svcSleepThread(1E+9);
    }''','''    if(R_FAILED(video_join) || R_FAILED(audio_join)) {
        (void)Ep0SessionJoined(ep0CandidateRecipe,exporter,video_join,audio_join,false);
        for(;;)svcSleepThread(1E+9);
    }
    if(R_FAILED(identity_rc)) {
        (void)Ep0SessionStartupOnly(ep0CandidateRecipe);
        for(;;)svcSleepThread(1E+9);
    }''')
    s=r(s,'        (void)Ep0CandidateSaveDiagnostic(exporter,video_join,audio_join,ep0CandidateRecipe);',
        '        bool diagnostic_saved=Ep0CandidateSaveDiagnostic(exporter,video_join,audio_join,ep0CandidateRecipe);\n'
        '        (void)Ep0SessionJoined(ep0CandidateRecipe,exporter,video_join,audio_join,true);\n'
        '        if(diagnostic_saved)(void)Ep0SessionSaveJoined(video_join,audio_join);')
    s=r(s,'    if(!Ep0CandidateSaveCapture()) { for(;;)svcSleepThread(1E+9); }',
        '    bool normal_saved=Ep0CandidateSaveCapture();\n    (void)Ep0SessionJoined(ep0CandidateRecipe,exporter,video_join,audio_join,false);\n'
        '    if(!normal_saved) { for(;;)svcSleepThread(1E+9); }')
    return s

def native_startup(recipe):
    s=startup.native_source(recipe)
    extra='''typedef struct { unsigned unused; } UsbDsReportData;
#include "research/usb-ds-iso/device/ep0_session_runtime.h"
const Ep0TraceOwner *Ep0CandidateObservation(void) { assert(false);return NULL; }
const Ep0GuardObservation *Ep0CandidateGuardObservation(void) { assert(false);return NULL; }
const Ep0AdmissionObservation *Ep0CandidateAdmissionObservation(void) { assert(false);return NULL; }
const uint8_t *Ep0CandidateDiagnosticBytes(size_t *n) { (void)n;assert(false);return NULL; }
const Ep0SinkState *Ep0CandidateDiagnosticFileObservation(void) { assert(false);return NULL; }
'''+BRIDGE+native_device('ep0_session_runtime.c')+'\n'
    s=r(s,'static bool is(const char *s)',extra+'static bool is(const char *s)');s=fatal_hook(s)
    s=s.replace('static void Ep0CandidateRequestStop(void)','void Ep0CandidateRequestStop(void)')
    s=r(s,'        else if(!strncmp(name,"app-",4))__appInit();',
        '        else if(!strcmp(name,"full-launch")) { __appInit();UvcDeviceConfig c={0};assert(!UvcDeviceInitialize(&c));launch_pair(); }\n'
        '        else if(!strncmp(name,"app-",4))__appInit();')
    s=r(s,'    /* CoreExit successful body is counted only in this generated fixture. */',
        '    (void)Ep0SessionStartupOnly(ep0CandidateRecipe);\n'
        '    size_t correlated=0;const uint8_t *rel=Ep0SessionBytes(&correlated);assert(rel);\n'
        '    char path[1024];snprintf(path,sizeof(path),"%s.rel",argv[2]);FILE *f=fopen(path,"wb");assert(f);assert(fwrite(rel,1,correlated,f)==correlated);assert(!fclose(f));\n'
        '    /* CoreExit successful body is counted only in this generated fixture. */')
    return s

def native_shutdown(folder,full_journal):
    s=startup.startup.sink.native_source(folder)
    s=s.replace('static bool opened;','static bool opened;static unsigned stage_reads;').replace('opened=true;return 0;','opened=true;stage_reads=0;return 0;').replace('read_file++;','read_file++;stage_reads++;').replace('read_file==2','stage_reads==2')
    s=s.replace('static uint8_t image[6657]','static uint8_t image[7969]').replace('n<=6656','n<=7968')
    s=r(s,'static bool is(const char *s) { return strcmp(scenario,s)==0; }',
        '''static bool is(const char *s) {
    if(!strcmp(scenario,s))return true;
    if(fs_open>=2 && !strncmp(scenario,"session-",8)) {
        const char *name=scenario+8;
        if(!strcmp(name,"maximum-short-read"))return !strcmp(s,"short-read");
        return !strcmp(name,s);
    }
    return false;
}''')
    s=r(s,'static Result svcGetThreadId(uint64_t *id,unsigned h) { (void)h;*id=22;return is("exporter-error") ? 99:0; }',
        '''static unsigned identity_queries;
static Result svcGetThreadId(uint64_t *id,unsigned h) {
    (void)h;identity_queries++;*id=identity_queries==1 && is("startup-zero-writer") ? 0:22;
    return identity_queries==1 ? (is("startup-identity-error") ? 97:0):(is("exporter-error") ? 99:0);
}''')
    setup=native_device('ep0_startup_runtime.c')+BRIDGE+'\nvoid Ep0CandidateGuardReject(unsigned reason) { (void)reject(reason); }\n'+native_device('ep0_request_admission.c')+'\n'
    # Track the new runtime getters independently of legacy diagnostic reads.
    setup+='''static unsigned session_owner_reads,receipt_reads;
static const Ep0TraceOwner *session_tracked_owner(void) { session_owner_reads++;assert(!poison);return Ep0CandidateObservation(); }
static const Ep0SinkState *session_tracked_receipt(void) { receipt_reads++;assert(!poison);return Ep0CandidateDiagnosticFileObservation(); }
#define Ep0CandidateObservation session_tracked_owner
#define Ep0CandidateDiagnosticFileObservation session_tracked_receipt
'''+native_device('ep0_session_runtime.c')+'''
#undef Ep0CandidateObservation
#undef Ep0CandidateDiagnosticFileObservation
'''+native_device('ep0_session_file.c')+'\n'
    setup+='static void replay_startup(void) {\n'
    for row in full_journal['records']:
        event=row['event'];step=STEPS.index(row['step'])+1;result=row['result']
        if event=='call':setup+=f'    Ep0StartupCall({step});\n'
        elif event=='result':setup+=f'    Ep0StartupResult({step},{result});\n'
        elif event=='void_return':setup+=f'    Ep0StartupVoid({step});\n'
        else:raise ValueError('Replay event drift: '+event)
    setup+=f'    if(is("maximum") || !strncmp(scenario,"session-maximum",15)) {{ for(unsigned i={full_journal["count"]};i<64;i+=2) {{ Ep0StartupCall(EP0_I_FS_INIT);Ep0StartupResult(EP0_I_FS_INIT,0); }} }}\n    (void)Ep0StartupSeal();\n}}\n'
    s=r(s,'static void UvcDeviceExit(void)',setup+'static void UvcDeviceExit(void)')
    start=s.index('    if(is("limits")) {');end=s.index('    uint8_t b[16]={1},s[16]={2};',start)
    s=s[:start]+"""    if(is("limits")) {
        uint8_t input[7969];memset(input,0x5a,sizeof(input));memcpy(input,"EP0REL1\\0",8);
        Ep0SessionFileIo io={0};Ep0SinkIo ops={&io,session_file_create_open,session_file_write_at,session_file_flush,session_file_file_size,session_file_read_at,session_file_close_file,session_file_commit};
        Ep0SinkState over={0},shorter={0},magic={0},normal={0},diagnostic={0},valid={0};
        assert(!ep0_session_sink_once(&over,&ops,"ignored",input,7969) && !create);
        assert(!ep0_session_sink_once(&shorter,&ops,"ignored",input,191) && !create);
        input[0]=0;assert(!ep0_session_sink_once(&magic,&ops,"ignored",input,192) && !create);input[0]='E';
        assert(!ep0_sink_once(&normal,&ops,"ignored",input,7968) && !create);
        assert(!ep0_diagnostic_sink_once(&diagnostic,&ops,"ignored",input,7968) && !create);
        assert(ep0_session_sink_once(&valid,&ops,"/ep0-0000000000000000000000000000000000000000000000000000000000000000.session.bin",input,7968));
        assert(valid.verified_bytes==7968 && !memcmp(input,image,7968));
        printf("{\\\"passed\\\":true,\\\"cases\\\":6,\\\"maximum\\\":7968,\\\"legacy_caps_unchanged\\\":true}\\n");return 0;
    }
"""+s[end:]
    s=r(s,'    uint8_t b[16]={1},s[16]={2};',
        '    (void)Ep0StartupBegin(ep0CandidateRecipe);if(Ep0StartupStatus()==2)replay_startup();\n    uint8_t b[16]={1},s[16]={2};')
    s=r(s,'    bool healthy=is("healthy") || is("normal-sink-error");',
        '    if(!unstarted && !is("bind-skipped")) { assert(Ep0SessionBind(11,b,s,ep0CandidateRecipe));assert(!Ep0SessionBind(11,b,s,ep0CandidateRecipe)); }\n'
        '    bool healthy=is("healthy") || is("normal-sink-error");')
    s=r(s,'    if(is("maximum")) {','    if(is("maximum") || !strncmp(scenario,"session-maximum",15)) {')
    # All session-file errors occur only after a successful old DIA1 save.
    a=s.index('    if(shutdown) {');b=s.index('    assert(!opened);size_t n=0;',a)
    s=s[:a]+'''    if(shutdown) {
        poison=g_videoThread.result || g_audioThread.result;
        if(setjmp(retained))held=true;else {
            if(is("callback-live") || is("callback-unstarted"))__appExit();
            else { native_shutdown();__appExit();__appExit(); }
        }
    } else {
        if(!unstarted && !is("live"))(void)Ep0CandidateFinish(22,g_videoThread.result | g_audioThread.result);
        Ep0TraceOwner before=storage;Ep0GuardObservation g_before=*Ep0CandidateGuardObservation();
        poison=g_videoThread.result || g_audioThread.result;
        bool saved=Ep0CandidateSaveDiagnostic(22,g_videoThread.result,g_audioThread.result,ep0CandidateRecipe);
        assert(Ep0SessionJoined(ep0CandidateRecipe,22,g_videoThread.result,g_audioThread.result,true));
        if(saved)ok=Ep0SessionSaveJoined(g_videoThread.result,g_audioThread.result);
        unsigned calls=fs_open+create+write_file+read_file+commit_fs;
        assert(!Ep0SessionSaveJoined(g_videoThread.result,g_audioThread.result));
        assert(calls==fs_open+create+write_file+read_file+commit_fs);
        assert(!memcmp(&storage,&before,sizeof(before)) && !memcmp(Ep0CandidateGuardObservation(),&g_before,sizeof(g_before)));
    }
    size_t rel_n=0;const uint8_t *rel=Ep0SessionBytes(&rel_n);
    if(rel) { char path[1024];snprintf(path,sizeof(path),"%s.rel",argv[3]);FILE *f=fopen(path,"wb");assert(f);assert(fwrite(rel,1,rel_n,f)==rel_n);assert(!fclose(f)); }
    if(rel) { assert(!Ep0SessionStartupOnly(ep0CandidateRecipe));size_t again=0;assert(Ep0SessionBytes(&again)==rel && again==rel_n); }
    if(poison)assert(!session_owner_reads && !receipt_reads);
    const Ep0SinkState *rel_state=Ep0SessionFileObservation();
'''+s[b:]
    s=r(s,'    printf("{\\"ok\\":%s,',
        '    printf("{\\"session_bytes\\":%zu,\\"session_attempted\\":%s,\\"session_phase\\":%u,\\"session_result\\":%u,\\"session_verified\\":%s,\\"session_ack\\":%s,\\"session_owner_reads\\":%u,\\"receipt_reads\\":%u,\\"identity_queries\\":%u,\\"ok\\":%s,')
    return r(s,'        ok?"true":"false",held?',
        '        rel_n,rel_state->attempted?"true":"false",rel_state->phase,rel_state->result,rel_state->content_verified?"true":"false",rel_state->commit_acknowledged?"true":"false",session_owner_reads,receipt_reads,identity_queries,ok?"true":"false",held?')

def compile_elf(folder,commands):
    compiler='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc';objects=folder/'objects';objects.mkdir();paths=[]
    flags=['-std=gnu11','-Wall','-Werror','-O3','-g','-ffunction-sections','-fstack-usage','-march=armv8-a+crc+crypto','-mtune=cortex-a57','-mtp=soft','-fPIE',
           '-D__SWITCH__',*base.DEFINES,'-I'+str(folder/'source/uvc'),'-I/opt/devkitpro/libnx/include']
    for source in sorted((folder/'source').rglob('*.c')):
        obj=objects/(source.relative_to(folder/'source').as_posix().replace('/','-')+'.o')
        cmd=[compiler,*flags,'-c',str(source),'-o',str(obj)];base.owner.command(cmd);commands.append(cmd);paths.append(str(obj))
    cmd=[compiler,'-specs=/opt/devkitpro/libnx/switch.specs','-march=armv8-a+crc+crypto','-mtune=cortex-a57','-mtp=soft','-fPIE',*paths,
         '-L/opt/devkitpro/libnx/lib','-lnx','-Wl,-Map,'+str(folder/'full.map'),'-o',str(folder/'full.elf')]
    base.owner.command(cmd,dict(os.environ,DEVKITPRO='/opt/devkitpro'));commands.append(cmd)
    symbols=base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-readelf','-Ws',str(folder/'full.elf')]);(folder/'symbols.txt').write_text(symbols)
    for name in ('Ep0SessionBind','Ep0SessionJoined','Ep0SessionStartupOnly','Ep0SessionBytes','Ep0SessionSaveJoined','VideoStreamThread','Ep0CandidateFinish','Ep0StartupBegin'):
        assert name in symbols,name
    def sizes(p):
        text=base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-size',str(p)]);values=text.splitlines()[1].split();return dict(zip(('text','data','bss'),map(int,values[:3])))
    size=sizes(folder/'full.elf');old=sizes(SEALED/folder.name/'full.elf')
    stack=[]
    for p in sorted(objects.glob('*.su')):
        for line in p.read_text().splitlines():
            f,n,kind=line.rsplit('\t',2);stack.append(dict(function=f.split(':')[-1],bytes=int(n),kind=kind))
    (folder/'stack-usage.json').write_text(json.dumps(stack,indent=2)+'\n')
    return dict(elf_sha256=base.ep0.sha(folder/'full.elf'),object_count=len(paths),linked=True,executed=False,sections=size,
        delta_from_startup_candidate={k:size[k]-old[k] for k in size},largest_project_function_stack=max(r['bytes'] for r in stack),
        whole_call_graph_stack_verified=False)

def run(output):
    output=Path(output).resolve();verify(SEALED);verify(PROTOTYPE);old=json.loads((PROTOTYPE/'audit.json').read_text())
    assert base.owner.source_audit()==old['source_audit'];source_audit=old['source_audit']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    names=list(dict.fromkeys([*old['source_hashes'],*INPUTS]));inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for n,h in old['source_hashes'].items():assert inputs[n]==h,n
    production={n:base.ep0.sha(startup.startup.REPO/n) for n in startup.startup.PRODUCTION};assert production==old['production_sources_sha256']
    info=dict(source_sha256=inputs,startup_manifest_sha256=base.ep0.sha(SEALED/'SHA256SUMS'),prototype_manifest_sha256=base.ep0.sha(PROTOTYPE/'SHA256SUMS'),
        libnx_a_sha256=base.ep0.sha(Path('/opt/devkitpro/libnx/lib/libnx.a')),compiler_version=base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','--version']))
    digest=hashlib.sha256(json.dumps(info,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=digest,inputs=info),indent=2)+'\n');commands=[];builds={}
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();shutil.copytree(SEALED/label/'source',folder/'source')
        for n in DEVICE:shutil.copyfile(ROOT/'device'/n,folder/'source/uvc'/n)
        config=dict(input_digest=digest,window_ms=0 if label=='dormant' else 30000,session_max=7968,save_only_after_diagnostic_success=True)
        recipe=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (folder/'recipe.json').write_text(json.dumps(dict(input_digest=recipe,configuration=config),indent=2)+'\n')
        (folder/'source/uvc/ep0_candidate_recipe.h').write_text(startup.journal.startup.sink.bounded.recipe_header(recipe))
        p=folder/'source/uvc/ep0_startup_runtime.c';p.write_text(p.read_text()+BRIDGE)
        p=folder/'source/core.c';p.write_text('#include "uvc/ep0_session_runtime.h"\n#include "uvc/ep0_candidate_recipe.h"\n'+fatal_hook(p.read_text()))
        p=folder/'source/sysmodule/main.c';p.write_text(main_source(p.read_text()))
        builds[label]=compile_elf(folder,commands);builds[label].update(runtime_recipe_digest=recipe,window_ms=config['window_ms'])
    recipe=builds['dormant']['runtime_recipe_digest'];file=output/'startup-native.c';file.write_text(native_startup(recipe));binary=output/'startup-native'
    commands.append(base.trace.compile_native(file,binary,[]));rows=[];prior=json.loads((SEALED/'audit.json').read_text());previous={r['case']:r for r in prior['cases']}
    for case in STARTUP_CASES:
        path=output/('startup-'+case+'.bin');row=json.loads(base.owner.command([str(binary),case,str(path)]))
        if case in previous:
            assert row=={k:v for k,v in previous[case].items() if k!='startup_journal'}
        row['session']=decode_session(Path(str(path)+'.rel').read_bytes(),recipe)
        if path.exists():row['startup_journal']=decode_startup(path.read_bytes(),recipe)
        (output/('startup-'+case+'.json')).write_text(json.dumps(row,indent=2)+'\n');rows.append(row)
    full=next(r for r in rows if r['case']=='full-launch')['startup_journal'];assert not full['overflow'] and not full['invalid']
    file=output/'shutdown-native.c';file.write_text(native_shutdown(output/'dormant',full));binary=output/'shutdown-native';commands.append(base.trace.compile_native(file,binary,[]))
    limits=json.loads(base.owner.command([str(binary),'limits','adapter',str(output/'unused')]))
    shutdown=[];files=[]
    for mode,cases in (('shutdown',SHUTDOWN_CASES),('adapter',tuple('session-'+c for c in FILE_CASES))):
        for case in cases:
            path=output/(mode+'-'+case+'.bin');row=json.loads(base.owner.command([str(binary),case,mode,str(path)]));row.update(case=case,mode=mode)
            rel=Path(str(path)+'.rel')
            if rel.exists():row['session']=decode_session(rel.read_bytes(),recipe)
            disk=Path(str(path)+'.disk')
            if disk.exists() and disk.read_bytes()[:8]==b'EP0REL1\0':row['disk_session']=decode_session(disk.read_bytes(),recipe) if row['session_verified'] else None
            (output/(mode+'-'+case+'.json')).write_text(json.dumps(row,indent=2)+'\n');(shutdown if mode=='shutdown' else files).append(row)
    assert inputs=={n:base.ep0.sha(ROOT/n) for n in names};assert production=={n:base.ep0.sha(startup.startup.REPO/n) for n in startup.startup.PRODUCTION}
    assert tickets=={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};verify(SEALED);verify(PROTOTYPE)
    result=dict(schema='A23-session-candidate-1',source_audit=source_audit,source_hashes=inputs,production_sources_sha256=production,tickets_sha256=tickets,
        recipe_digest=digest,compiler_commands=commands,builds=builds,startup_cases=rows,shutdown_cases=shutdown,file_cases=files,
        startup_case_count=len(rows),shutdown_case_count=len(shutdown),file_case_count=len(files),startup_full_records=full['count'],limit_policy=limits,
        full_arm_candidate_integrated=True,real_startup_hooks_in_candidate=True,existing_nonce_bound_in_candidate=True,
        save_receipt_from_adapter_return=True,save_outcome_injected=False,startup_shutdown_harness_replays_actual_hook_records=True,
        session_filesystem_in_candidate=True,session_save_after_diagnostic_failure=False,failed_join_filesystem_calls=0,
        initialization_failure_filesystem_export=False,callback_modified=False,old_wire_modified=False,normal_sink_modified=False,
        cleanup_authorized_by_session=False,production_modified=False,prior_runtime_modified=False,usb_accessed=False,sd_accessed=False,
        firmware_packaged=False,arm_executed=False,actual_switch_threads_executed=False,actual_dma_executed=False,startup_cost_measured=False,
        whole_call_graph_stack_verified=False,hardware_verified=False,root_cause_confirmed=False,source_authenticated=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    s=run(a.output);print(json.dumps({k:s[k] for k in ('startup_case_count','shutdown_case_count','file_case_count','startup_full_records','builds')},indent=2))
if __name__=='__main__':main()
