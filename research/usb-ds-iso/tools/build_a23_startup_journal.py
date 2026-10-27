#!/usr/bin/env python3
"""Independent startup journal, native API adapter hooks and ARM object only."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
import audit_a23_startup as startup
from analyze_ep0_startup import decode_startup
from workflows.artifacts import verify
base=startup.base;ROOT=startup.ROOT
SEALED=base.ep0.PRIVATE/'analysis/A23-startup-review-20261014'
INPUTS=('device/ep0_startup_journal.h','tools/analyze_ep0_startup.py','tools/build_a23_startup_journal.py','tests/ep0_startup_journal_test.c')
# Native service adapter boundaries only. Original extracted function bodies stay
# unchanged; ARM compilation below does NOT install these hooks in firmware.
WRAPS=(
('fsInitialize','void','','EP0_I_FS_INIT',False),
('fsOpenSdCardFileSystem','FsFileSystem *s','s','EP0_I_SD_OPEN',False),
('fsFsDeleteFile','FsFileSystem *s,const char *p','s,p','EP0_I_LOG_DELETE',False),
('fsFsCreateFile','FsFileSystem *s,const char *p,unsigned n,unsigned opt','s,p,n,opt','EP0_I_LOG_CREATE',False),
('grcdServiceOpen','Service *s','s','s==&g_grcdVideo ? EP0_I_VIDEO_OPEN:EP0_I_AUDIO_OPEN',False),
('usbDsInitialize','void','','EP0_I_USB_INIT',False),
('_setupDescriptors5x','const UvcDeviceConfig *c','c','EP0_I_DESCRIPTORS',False),
('_setupInterfaces5x','void','','EP0_I_INTERFACES',False),
('_setupIsoProbe','void','','EP0_I_ISO_SETUP',False),
('usbDsEnable','void','','EP0_I_USB_ENABLE',False),
('threadCreate','Thread *t,ThreadFunc f,void *a,void *stack,u32 sz,u32 prio,int cpu','t,f,a,stack,sz,prio,cpu','t->index ? EP0_I_AUDIO_CREATE:EP0_I_VIDEO_CREATE',False),
('threadStart','Thread *t','t','t->index ? EP0_I_AUDIO_START:EP0_I_VIDEO_START',False),
('smInitialize','void','','EP0_I_SM_INIT',False),
('setsysInitialize','void','','EP0_I_SETSYS_INIT',False),
('setsysGetFirmwareVersion','SetSysFirmwareVersion *s','s','EP0_I_FW_GET',False),
('setsysGetSerialNumber','SetSysSerialNumber *s','s','EP0_I_SERIAL_GET',False),
('CoreInit','void','','EP0_I_CORE_INIT',False),
('UvcDeviceInitialize','const UvcDeviceConfig *c','c','EP0_I_USB_DEVICE_INIT',False),
('fsExit','void','','EP0_I_FS_EXIT',True),
('fsFsClose','FsFileSystem *s','s','EP0_I_SD_CLOSE',True),
('grcdServiceClose','Service *s','s','s==&g_grcdVideo ? EP0_I_VIDEO_CLOSE:EP0_I_AUDIO_CLOSE',True))

def native_source(recipe):
    s=startup.native_source();prototypes=[];wrappers=[]
    for name,args,call,step,void in WRAPS:
        kind='void' if void else 'Result'
        pattern=r'(?m)^(static )?'+kind+r' '+re.escape(name)+r'\(([^\n]*)\)(?=\s*\{)'
        s,n=re.subn(pattern,lambda m:(m[1] or '')+kind+' raw_'+name+'('+m[2]+')',s)
        if n!=1:raise ValueError('Unique API adapter drift: '+name)
        prototypes.append(kind+' '+name+'('+args+');')
        beginning=f'{kind} {name}({args}) {{ unsigned step={step};(void)ep0_startup_record(&journal,11,step,EP0_I_CALL,0);'
        if void:body=f'raw_{name}({call});(void)ep0_startup_record(&journal,11,step,EP0_I_VOID_RETURN,0);'
        else:body=f'Result rc=raw_{name}({call});(void)ep0_startup_record(&journal,11,step,EP0_I_RESULT,rc);return rc;'
        wrappers.append(beginning+body+' }')
    s,n=re.subn(r'(?m)^static void fatalThrow\(Result rc\)(?=\s*\{)','static void raw_fatalThrow(Result rc)',s)
    if n!=1:raise ValueError('Fatal adapter drift')
    prototypes.append('void fatalThrow(Result rc);')
    wrappers.append('void fatalThrow(Result rc) { (void)ep0_startup_record(&journal,11,EP0_I_FATAL,EP0_I_FATAL_RESULT,rc);raw_fatalThrow(rc); }')
    r=base.trace.replace
    declarations='#include "research/usb-ds-iso/device/ep0_startup_journal.h"\nstatic Ep0StartupJournal journal;\n'+ '\n'.join(prototypes)+'\n'
    s=r(s,'static const char *scenario;',declarations+'static const char *scenario;')
    s=r(s,'assert(argc==2);const char *name=argv[1];',
        'assert(argc==3);const uint8_t recipe[32]={'+','.join(str(x) for x in bytes.fromhex(recipe))+'};assert(ep0_startup_init(&journal,11,recipe));const char *name=argv[1];')
    s=r(s,'    /* CoreExit successful body is counted only in this generated fixture. */',
        '    assert(ep0_startup_seal(&journal,11));\n    uint8_t journal_bytes[EP0_INIT_MAX];size_t journal_size=ep0_startup_snapshot(&journal,journal_bytes,sizeof(journal_bytes));assert(journal_size);\n'
        '    FILE *f=fopen(argv[2],"wb");assert(f);assert(fwrite(journal_bytes,1,journal_size,f)==journal_size);assert(!fclose(f));\n'
        '    /* CoreExit successful body is counted only in this generated fixture. */')
    return s+'\n'+'\n'.join(wrappers)+'\n'

def run(output):
    output=Path(output);sealed=verify(SEALED);old=json.loads((SEALED/'audit.json').read_text());source_audit=base.owner.source_audit()
    assert source_audit==old['source_audit']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    names=list(dict.fromkeys([*old['source_hashes'],*INPUTS]));inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for n,h in old['source_hashes'].items():
        if inputs[n]!=h:raise ValueError('Dependency drift: '+n)
    production={n:base.ep0.sha(startup.REPO/n) for n in startup.PRODUCTION};assert production==old['production_sources_sha256']
    recipe_info=dict(source_sha256=inputs,sealed_manifest_sha256=base.ep0.sha(SEALED/'SHA256SUMS'),capacity=64,startup_only=True)
    recipe=hashlib.sha256(json.dumps(recipe_info,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=recipe,inputs=recipe_info),indent=2)+'\n')
    file=output/'journal-startup.c';file.write_text(native_source(recipe));binary=output/'journal-startup'
    commands=[base.trace.compile_native(file,binary,[])];rows=[];previous={r['case']:r for r in old['cases']}
    for case in startup.CASES:
        path=output/(case+'.startup.bin');row=json.loads(base.owner.command([str(binary),case,str(path)]));assert row==previous[case]
        decoded=decode_startup(path.read_bytes(),recipe);row['startup_journal']=decoded
        (output/(case+'.startup.json')).write_text(json.dumps(decoded,indent=2)+'\n');rows.append(row)
    policy=output/'journal-policy';commands.append(base.trace.compile_native(ROOT/'tests/ep0_startup_journal_test.c',policy,['-pthread']))
    policies=json.loads(base.owner.command([str(policy),str(output/'policy')]))
    tsan=output/'journal-policy-tsan'
    cmd=['cc','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=thread','-g','-pthread',
         '-I'+str(startup.REPO),str(ROOT/'tests/ep0_startup_journal_test.c'),'-o',str(tsan)]
    base.owner.command(cmd);commands.append(cmd)
    tsan_policy=json.loads(base.owner.command([str(tsan),str(output/'tsan-policy')]))
    # Pure header/API ABI object; no old/full candidate integration or ELF link.
    arm=output/'startup-arm.c';arm.write_text('#include "ep0_startup_journal.h"\nbool startup_append(Ep0StartupJournal *s,uint64_t w,unsigned p,unsigned e,uint32_t r) { return ep0_startup_record(s,w,p,e,r); }\nsize_t startup_copy(const Ep0StartupJournal *s,uint8_t *o,size_t n) { return ep0_startup_snapshot(s,o,n); }\n')
    cmd=['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','-std=gnu11','-Wall','-Wextra','-Werror','-O3','-D__SWITCH__',
         '-I'+str(ROOT/'device'),'-c',str(arm),'-o',str(output/'startup-arm.o')]
    base.owner.command(cmd);commands.append(cmd)
    assert inputs=={n:base.ep0.sha(ROOT/n) for n in names};assert production=={n:base.ep0.sha(startup.REPO/n) for n in startup.PRODUCTION}
    assert tickets=={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};verify(SEALED)
    result=dict(schema='A23-startup-journal-1',source_audit=source_audit,source_hashes=inputs,production_sources_sha256=production,
        tickets_sha256=tickets,sealed_input=sealed,recipe_digest=recipe,compiler_commands=commands,cases=rows,case_count=len(rows),
        policy=policies,thread_sanitizer_policy=tsan_policy,arm_object_sha256=base.ep0.sha(output/'startup-arm.o'),native_service_results_unchanged=True,
        native_api_adapter_hooks_only=True,header_arm_compiled=True,full_arm_candidate_integrated=False,
        startup_files_saved_on_native_host_only=True,diagnostic_wire_modified=False,cleanup_authorized=False,
        production_modified=False,prior_runtime_modified=False,usb_accessed=False,sd_accessed=False,arm_executed=False,
        firmware_packaged=False,actual_switch_threads_executed=False,actual_dma_executed=False,
        initialization_rollback_implemented=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);r=run(a.output);print(json.dumps(dict(output=str(a.output),cases=r['case_count'],policy=r['policy']),indent=2))
if __name__=='__main__':main()
