#!/usr/bin/env python3
"""Offline ARM startup hook candidate plus actual-function native replays."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
import build_a23_startup_journal as journal
from analyze_ep0_startup import decode_startup
from workflows.artifacts import verify
base=journal.base;ROOT=journal.ROOT;startup=journal.startup
SEALED=base.ep0.PRIVATE/'analysis/A23-diagnostic-sink-review-20261014'
JOURNAL=base.ep0.PRIVATE/'analysis/A23-startup-journal-review-20261014'
DEVICE=('ep0_startup_journal.h','ep0_startup_runtime.h','ep0_startup_runtime.c')
INPUTS=(*('device/'+n for n in DEVICE),'tools/build_a23_startup_candidate.py','tests/ep0_startup_runtime_test.c')
EXTRA_CASES=('app-identity-error','app-zero-writer','app-identity-interrupted','repeat-begin')
r=base.trace.replace

def function(s,signature):
    if s.count(signature)!=1:raise ValueError('Unique function drift: '+signature)
    a=s.index(signature);b=s.index('{',a);depth=0
    for end in range(b,len(s)):
        if s[end]=='{':depth+=1
        elif s[end]=='}':
            depth-=1
            if not depth:return s[a:end+1]
    raise ValueError('Unclosed function')

def rc_call(s,anchor,expression,step):
    return r(s,anchor,f'Ep0StartupCall({step});\n    rc = {expression};\n    Ep0StartupResult({step},rc);')

def core_source(s):
    s=rc_call(s,'rc = fsInitialize();','fsInitialize()','EP0_I_FS_INIT')
    serial=function(s,'static Result _getSerialNumber(void)')
    modified=rc_call(serial,'rc = setsysInitialize();','setsysInitialize()','EP0_I_SETSYS_INIT')
    modified=rc_call(modified,'rc = setsysGetSerialNumber(&serial);','setsysGetSerialNumber(&serial)','EP0_I_SERIAL_GET')
    s=r(s,serial,modified)
    s=r(s,'    if (R_SUCCEEDED(fsOpenSdCardFileSystem(&g_sdCard))) {',
        '    Ep0StartupCall(EP0_I_SD_OPEN);\n    Result mount_rc=fsOpenSdCardFileSystem(&g_sdCard);\n    Ep0StartupResult(EP0_I_SD_OPEN,mount_rc);\n    if (R_SUCCEEDED(mount_rc)) {')
    for api,step in (('fsFsDeleteFile(&g_sdCard, "/logfile.txt")','EP0_I_LOG_DELETE'),('fsFsCreateFile(&g_sdCard, "/logfile.txt", 0, 0)','EP0_I_LOG_CREATE')):
        s=r(s,'        '+api+';',f'        Ep0StartupCall({step});\n        {{ Result log_rc={api};Ep0StartupResult({step},log_rc); }}')
    s=r(s,'        fsFsClose(&g_sdCard);','        Ep0StartupCall(EP0_I_SD_CLOSE);\n        fsFsClose(&g_sdCard);\n        Ep0StartupVoid(EP0_I_SD_CLOSE);')
    s=r(s,'    fsExit();','    Ep0StartupCall(EP0_I_FS_EXIT);\n    fsExit();\n    Ep0StartupVoid(EP0_I_FS_EXIT);')
    body=function(s,'Result CoreInit(void)')
    new=r(body,'{\n    if (g_coreInitialized)', '{\n    Ep0StartupCall(EP0_I_CORE_INIT);\n    if (g_coreInitialized)')
    if new.count('return 0;')!=2 or new.count('return rc;')!=1:raise ValueError('Core return drift')
    new=new.replace('return 0;','Ep0StartupResult(EP0_I_CORE_INIT,0);return 0;').replace('return rc;','Ep0StartupResult(EP0_I_CORE_INIT,rc);return rc;')
    s=r(s,body,new)
    s=r(s,'    Result rc = threadCreate(t, f, arg, stackLocation, stackSize, prio, -2);',
        '    unsigned create_step=Ep0StartupCreateStep(t),start_step=Ep0StartupStartStep(t);\n    Ep0StartupCall(create_step);\n    Result rc = threadCreate(t, f, arg, stackLocation, stackSize, prio, -2);\n    Ep0StartupResult(create_step,rc);')
    s=rc_call(s,'rc = threadStart(t);','threadStart(t)','start_step')
    if s.count('        R_THROW(rc);')!=2:raise ValueError('Launch fatal drift')
    return s.replace('        R_THROW(rc);','        Ep0StartupFatal(rc);\n        R_THROW(rc);')

def capture_source(s):
    for name,step in (('Video','EP0_I_VIDEO_OPEN'),('Audio','EP0_I_AUDIO_OPEN')):
        s=r(s,f'    R_RET_ON_FAIL(grcdServiceOpen(&g_grcd{name}));',
            f'    Ep0StartupCall({step});\n    {{ Result open_rc=grcdServiceOpen(&g_grcd{name});Ep0StartupResult({step},open_rc);if(R_FAILED(open_rc))return open_rc; }}')
        phase='EP0_I_'+name.upper()+'_CLOSE'
        s=r(s,f'    grcdServiceClose(&g_grcd{name});',f'    Ep0StartupCall({phase});\n    grcdServiceClose(&g_grcd{name});\n    Ep0StartupVoid({phase});')
    return s

def usb_source(s):
    body=function(s,'Result UvcDeviceInitialize(const UvcDeviceConfig* config)')
    new=r(body,'{\n    Result rc = 0;', '{\n    Ep0StartupCall(EP0_I_USB_DEVICE_INIT);\n    Result rc = 0;')
    for expression,step in (('usbDsInitialize()','EP0_I_USB_INIT'),('_setupDescriptors5x(config)','EP0_I_DESCRIPTORS'),
        ('_setupInterfaces5x()','EP0_I_INTERFACES'),('_setupIsoProbe()','EP0_I_ISO_SETUP'),('usbDsEnable()','EP0_I_USB_ENABLE')):
        new=rc_call(new,'rc = '+expression+';',expression,step)
    new=r(new,'return MAKERESULT(Module_Libnx, LibnxError_AlreadyInitialized);',
        'rc=MAKERESULT(Module_Libnx, LibnxError_AlreadyInitialized);Ep0StartupResult(EP0_I_USB_DEVICE_INIT,rc);return rc;')
    new=new.replace('return rc;','Ep0StartupResult(EP0_I_USB_DEVICE_INIT,rc);return rc;')
    # The reentry path must have exactly one result, like every other return.
    new=new.replace('Ep0StartupResult(EP0_I_USB_DEVICE_INIT,rc);Ep0StartupResult(EP0_I_USB_DEVICE_INIT,rc);','Ep0StartupResult(EP0_I_USB_DEVICE_INIT,rc);')
    new=new.replace('return 0;','Ep0StartupResult(EP0_I_USB_DEVICE_INIT,0);return 0;')
    return r(s,body,new)

def app_init(s):
    body=function(s,'void __appInit(void)')
    new=r(body,'    Result rc;','    (void)Ep0StartupBegin(ep0CandidateRecipe);\n    Result rc;')
    new=rc_call(new,'rc = smInitialize();','smInitialize()','EP0_I_SM_INIT')
    new=rc_call(new,'rc = setsysInitialize();','setsysInitialize()','EP0_I_SETSYS_INIT')
    new=r(new,'        if (R_SUCCEEDED(setsysGetFirmwareVersion(&fw))) {',
        '        Ep0StartupCall(EP0_I_FW_GET);\n        Result fw_rc=setsysGetFirmwareVersion(&fw);\n        Ep0StartupResult(EP0_I_FW_GET,fw_rc);\n        if (R_SUCCEEDED(fw_rc)) {')
    if new.count('        fatalThrow(rc);')!=2:raise ValueError('App fatal drift')
    new=new.replace('        fatalThrow(rc);','        Ep0StartupFatal(rc);\n        fatalThrow(rc);')
    return r(s,body,new)

def main_source(s):
    s=app_init(s)
    s=r(s,'    LaunchThread(&g_videoThread, VideoStreamThread, NULL,','    Ep0StartupBindThreads(&g_videoThread,&g_audioThread);\n    LaunchThread(&g_videoThread, VideoStreamThread, NULL,')
    s=r(s,'    LOG("SysDVR-UVC running (video + audio)\\n");','    (void)Ep0StartupSeal();\n    LOG("SysDVR-UVC running (video + audio)\\n");')
    return r(s,'        return 1;','        (void)Ep0StartupSeal();\n        return 1;')

def native_source(recipe):
    s=startup.native_source();s=core_source(capture_source(usb_source(app_init(s))))
    s=r(s,'    LaunchThread(&g_videoThread, VideoStreamThread, NULL,','    Ep0StartupBindThreads(&g_videoThread,&g_audioThread);\n    LaunchThread(&g_videoThread, VideoStreamThread, NULL,')
    # Native direct API scenarios do not call full main; seal after successful pair.
    launch=startup.extract(s,'static void launch_pair(void)','static unsigned mounted(void)')
    s=r(s,launch,launch.replace('\n}\n','\n    (void)Ep0StartupSeal();\n}\n'))
    runtime=(ROOT/'device/ep0_startup_runtime.c').read_text().replace('#include "ep0_startup_runtime.h"','#include "research/usb-ds-iso/device/ep0_startup_runtime.h"')
    setup='''#define EP0_CANDIDATE_NATIVE
#define CUR_THREAD_HANDLE 0
static const char *identity_case;static unsigned identity_queries;
static Result svcGetThreadId(uint64_t *id,unsigned h) {
    (void)h;identity_queries++;*id=!strcmp(identity_case,"app-zero-writer") ? 0:11;
    if(!strcmp(identity_case,"app-identity-interrupted"))longjmp(interrupted,3);
    return !strcmp(identity_case,"app-identity-error") ? 97:0;
}
'''+runtime+'\n'+journal.startup.sink.bounded.recipe_header(recipe)
    s=r(s,'static bool is(const char *s)',setup+'static bool is(const char *s)')
    s=r(s,'assert(argc==2);const char *name=argv[1];scenario=name;Result rc=0;',
        'assert(argc==3);const char *name=argv[1];scenario=name;identity_case=name;Result rc=0;\n'
        '    if(strncmp(name,"app-",4)) (void)Ep0StartupBegin(ep0CandidateRecipe);\n'
        '    if(!strcmp(name,"repeat-begin")) { scenario="launch-ok";assert(!Ep0StartupBegin(ep0CandidateRecipe)); }')
    s=r(s,'    /* CoreExit successful body is counted only in this generated fixture. */',
        '    (void)Ep0StartupSeal();\n    uint8_t bytes[EP0_INIT_MAX];size_t n=Ep0StartupSnapshot(bytes,sizeof(bytes));\n'
        '    if(n) { FILE *f=fopen(argv[2],"wb");assert(f);assert(fwrite(bytes,1,n,f)==n);assert(!fclose(f)); }\n'
        '    /* CoreExit successful body is counted only in this generated fixture. */')
    s=r(s,'\\"case\\":\\"%s\\",','\\"case\\":\\"%s\\",\\"startup_status\\":%u,\\"identity_queries\\":%u,\\"identity_result\\":%u,\\"startup_bytes\\":%zu,')
    return r(s,'           name,rc,exit_reason,','           name,Ep0StartupStatus(),identity_queries,Ep0StartupIdentityResult(),n,rc,exit_reason,')

def run(output):
    output=Path(output);sealed=verify(SEALED);jsealed=verify(JOURNAL);old=json.loads((JOURNAL/'audit.json').read_text())
    source_audit=base.owner.source_audit();assert source_audit==old['source_audit']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    names=list(dict.fromkeys([*old['source_hashes'],*INPUTS]));inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for n,h in old['source_hashes'].items():
        if inputs[n]!=h:raise ValueError('Dependency drift: '+n)
    production={n:base.ep0.sha(startup.REPO/n) for n in startup.PRODUCTION};assert production==old['production_sources_sha256']
    info=dict(source_sha256=inputs,arm_manifest_sha256=base.ep0.sha(SEALED/'SHA256SUMS'),journal_manifest_sha256=base.ep0.sha(JOURNAL/'SHA256SUMS'),
        libnx_a_sha256=base.ep0.sha(Path('/opt/devkitpro/libnx/lib/libnx.a')),compiler_version=base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','--version']))
    digest=hashlib.sha256(json.dumps(info,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=digest,inputs=info),indent=2)+'\n')
    commands=[];builds={}
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();shutil.copytree(SEALED/label/'source',folder/'source')
        for n in DEVICE:shutil.copyfile(ROOT/'device'/n,folder/'source/uvc'/n)
        config=dict(input_digest=digest,window_ms=0 if label=='dormant' else 30000,startup_identity_queries=1,offline_compile_only=True)
        recipe=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (folder/'recipe.json').write_text(json.dumps(dict(input_digest=recipe,configuration=config),indent=2)+'\n')
        (folder/'source/uvc/ep0_candidate_recipe.h').write_text(journal.startup.sink.bounded.recipe_header(recipe))
        for name,transform,header in (('core.c',core_source,'uvc/ep0_startup_runtime.h'),('capture.c',capture_source,'uvc/ep0_startup_runtime.h'),
            ('uvc/uvc_device.c',usb_source,'ep0_startup_runtime.h'),('sysmodule/main.c',main_source,'../uvc/ep0_startup_runtime.h')):
            p=folder/'source'/name;p.write_text('#include "'+header+'"\n'+transform(p.read_text()))
        builds[label]=base.compile_elf(folder,commands);builds[label].update(runtime_recipe_digest=recipe,window_ms=config['window_ms'])
        symbols=(folder/'symbols.txt').read_text()
        matches=re.findall(r'\s(\d+)\s+OBJECT\s+LOCAL\s+DEFAULT\s+\S+\s+startup$',symbols,re.M)
        if len(matches)!=1:raise ValueError('Startup storage symbol drift')
        builds[label]['startup_journal_bytes']=int(matches[0])
        builds[label]['startup_snapshot_linked']='Ep0StartupSnapshot' in symbols
        for name in ('Ep0StartupBegin','Ep0StartupCall','Ep0StartupResult','Ep0StartupFatal','Ep0StartupSeal'):
            if name not in symbols:raise ValueError('Missing startup hook: '+name)
    recipe=builds['dormant']['runtime_recipe_digest'];file=output/'startup-candidate-native.c';file.write_text(native_source(recipe))
    binary=output/'startup-candidate-native';commands.append(base.trace.compile_native(file,binary,[]))
    previous={r['case']:r for r in old['cases']};rows=[]
    for case in (*startup.CASES,*EXTRA_CASES):
        path=output/(case+'.startup.bin');row=json.loads(base.owner.command([str(binary),case,str(path)]))
        if case in previous:
            assert {k:v for k,v in row.items() if k not in ('startup_status','identity_queries','identity_result','startup_bytes')}=={k:v for k,v in previous[case].items() if k!='startup_journal'}
        if path.exists():
            row['startup_journal']=decode_startup(path.read_bytes(),recipe)
            (output/(case+'.startup.json')).write_text(json.dumps(row['startup_journal'],indent=2)+'\n')
        rows.append(row)
    policy=output/'runtime-policy';commands.append(base.trace.compile_native(ROOT/'tests/ep0_startup_runtime_test.c',policy,[]))
    policies=[json.loads(base.owner.command([str(policy),case,str(output/('runtime-policy-'+case+'.bin'))])) for case in ('unattempted','identity-error','zero-id','interrupted','normal','fatal','overflow')]
    assert inputs=={n:base.ep0.sha(ROOT/n) for n in names};assert production=={n:base.ep0.sha(startup.REPO/n) for n in startup.PRODUCTION}
    assert tickets=={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};verify(SEALED);verify(JOURNAL)
    result=dict(schema='A23-startup-candidate-1',source_audit=source_audit,source_hashes=inputs,production_sources_sha256=production,
        tickets_sha256=tickets,sealed_input=sealed,sealed_journal=jsealed,recipe_digest=digest,compiler_commands=commands,
        builds=builds,cases=rows,case_count=len(rows),policy=policies,full_arm_candidate_integrated=True,
        startup_exported_on_device=False,startup_identity_extra_svc_queries=1,identity_failure_changes_startup_flow=False,
        native_service_results_unchanged=True,descriptor_interface_iso_hooks_coarse=True,
        runtime_logger_modified=False,callback_writes_startup_journal=False,diagnostic_wire_modified=False,
        production_modified=False,prior_runtime_modified=False,usb_accessed=False,sd_accessed=False,arm_executed=False,
        firmware_packaged=False,actual_switch_threads_executed=False,actual_dma_executed=False,
        startup_cost_measured=False,initialization_rollback_implemented=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);s=run(a.output);print(json.dumps(dict(output=str(a.output),cases=s['case_count'],builds=s['builds']),indent=2))
if __name__=='__main__':main()
