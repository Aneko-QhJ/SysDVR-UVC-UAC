#!/usr/bin/env python3
"""Offline buffer/cleanup guarded A23 candidate, native models and ELF link only.
Preserves production and earlier prototypes; no ARM execution/packaging/USB/SD.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import audit_a23_control_buffers as audit
from workflows.artifacts import verify
base=audit.base;ROOT=audit.ROOT;SINK=audit.SINK
DEVICE=('ep0_buffer_guard.h','ep0_candidate_guard.h','ep0_candidate_guard.c','ep0_cleanup_gate.h')
POLICY_CASES=('range','overlap','missing','active','zero','terminal','capacity','writer','cleanup')
ADAPTER_CASES=('failed-post','zero-id','missing-map','mismatched-post','invalid-range')


def guarded_handler(s):
    r=base.trace.replace
    for name in ('In','Out'):
        anchor=f'static Result _ctrl{name}Xfer(UsbDsInterface* iface, u8* buf, size_t len, u32* transferred)\n{{'
        s=r(s,anchor,anchor+'\n    if(!Ep0CandidateGuardAllow(buf,len,1))return EP0_GUARD_RESULT;')
        channel=0 if name=='In' else 1
        anchor=f'    Ep0CandidateObservePost(iface->interface_index*2+{channel},rc,rc==0,rc ? 0 : urbId);'
        s=r(s,anchor,anchor+f'\n    Ep0CandidateGuardPost(iface->interface_index*2+{channel},rc,rc==0,rc ? 0 : urbId,buf,len);')
    # Whole-request reservation prevents copying/posting a GET/SET data stage
    # when there would be no identity slot for its status stage.
    s=r(s,'static void _ctrlWrite(UsbDsInterface* iface, const void* data, size_t len)\n{',
        'static void _ctrlWrite(UsbDsInterface* iface, const void* data, size_t len)\n{\n    if(!Ep0CandidateGuardAllow(_ctrlBufferFor(iface),len,2))return;')
    s=r(s,'static bool _ctrlRead(UsbDsInterface* iface, void* data, size_t len)\n{',
        'static bool _ctrlRead(UsbDsInterface* iface, void* data, size_t len)\n{\n    if(!Ep0CandidateGuardAllow(_ctrlBufferFor(iface),len,2))return false;')
    s=r(s,'static void _ctrlAck(UsbDsInterface* iface)\n{',
        'static void _ctrlAck(UsbDsInterface* iface)\n{\n    if(!Ep0CandidateGuardAllow(_ctrlBufferFor(iface),0,1))return;')
    s=r(s,'        memset(&g_isoStatus, 0, sizeof(g_isoStatus));',
        '        if(!Ep0CandidateGuardAllow(g_isoBuffer,length,2))return;\n        memset(&g_isoStatus, 0, sizeof(g_isoStatus));')
    anchor='        Ep0CandidateObservePost(8,rc,rc==0,rc ? 0 : urbId);'
    return r(s,anchor,anchor+'\n        Ep0CandidateGuardPost(8,rc,rc==0,rc ? 0 : urbId,g_isoBuffer,length);')


def fault_function():
    return '\nvoid Ep0CandidateGuardFault(void) { storage.fault=1;Ep0CandidateRequestStop(); }\n'


def guarded_main(s):
    r=base.trace.replace
    s=r(s,'#include "../uvc/ep0_candidate_window.h"',
        '#include "../uvc/ep0_candidate_window.h"\n#include "../uvc/ep0_cleanup_gate.h"\nstatic Ep0CleanupGate ep0Cleanup;')
    s=r(s,'    Result video_join=threadWaitForExit(&g_videoThread);',
        '    if(!ep0_cleanup_begin(&ep0Cleanup)) { for(;;)svcSleepThread(1E+9); }\n    Result video_join=threadWaitForExit(&g_videoThread);')
    s=r(s,'    threadClose(&g_videoThread);threadClose(&g_audioThread);\n    UvcDeviceExit();',
        '    threadClose(&g_videoThread);threadClose(&g_audioThread);\n'
        '    if(!ep0_cleanup_authorize(&ep0Cleanup)) { for(;;)svcSleepThread(1E+9); }')
    s=r(s,'void __appExit(void)\n{\n    g_running = false;',
        'void __appExit(void)\n{\n    g_running = false;\n    Ep0CandidateRequestStop();\n'
        '    if(ep0_cleanup_done(&ep0Cleanup))return;\n'
        '    if(!ep0_cleanup_claim(&ep0Cleanup)) { for(;;)svcSleepThread(1E+9); }')
    return r(s,'    smExit();\n}', '    smExit();\n    (void)ep0_cleanup_complete(&ep0Cleanup);\n}')


def native_buffer():
    s=guarded_handler(audit.buffer_fixture(True));r=base.trace.replace
    s=r(s,'static UsbDsInterface interfaces[3];',
        '#define EP0_CANDIDATE_NATIVE\n#include "research/usb-ds-iso/device/ep0_candidate_guard.h"\nstatic UsbDsInterface interfaces[3];')
    adapter=(ROOT/'device/ep0_candidate_guard.c').read_text().replace('#include "ep0_candidate_guard.h"','')
    s=r(s,'static void trace_id(',fault_function()+adapter+'\nstatic void trace_id(')
    s=r(s,'    Ep0CandidateRequestStop();assert(Ep0CandidateStop(svcGetSystemTick()));',
        '    bool guard_stop=Ep0CandidateStopRequested();\n    const Ep0GuardObservation *guard=Ep0CandidateGuardObservation();\n'
        '    Ep0CandidateRequestStop();assert(Ep0CandidateStop(svcGetSystemTick()));')
    s=r(s,'\\"pending_spans\\":%u,',
        '\\"guard_denials\\":%u,\\"guard_reason\\":%u,\\"guard_stop_requested\\":%s,\\"pending_spans\\":%u,')
    return r(s,'           name,pending,nonzero,zero,',
        '           name,guard->denials,guard->last_reason,guard_stop ? "true":"false",pending,nonzero,zero,')


def native_adapter():
    s=native_buffer();anchor='int main(int argc,char **argv) {'
    if s.count(anchor)!=1:raise ValueError('Adapter main drift')
    return s[:s.index(anchor)]+r'''int main(int argc,char **argv) {
    assert(argc==2);const char *name=argv[1];
    trace_probe_begin("01000000000000000000000000000000","02000000000000000000000000000000");
    assert(Ep0CandidateEnter());
    if(!strcmp(name,"failed-post")) {
        Ep0CandidateObservePost(4,93,false,0);Ep0CandidateGuardPost(4,93,false,0,g_controlBuffer,32);
    } else {
        Ep0CandidateObservePost(4,0,true,0);
        if(!strcmp(name,"zero-id")) {
            Ep0CandidateGuardPost(4,0,true,0,g_controlBuffer,32);
            assert(Ep0CandidateGuardAllow(g_vcControlBuffer,32,2));
            assert(!Ep0CandidateGuardAllow(g_controlBuffer,32,2));
        } else if(!strcmp(name,"missing-map")) {
            assert(!Ep0CandidateGuardAllow(g_vcControlBuffer,32,2));
        } else if(!strcmp(name,"mismatched-post")) {
            Ep0CandidateGuardPost(5,0,true,0,g_controlBuffer,32);
        } else {
            assert(!strcmp(name,"invalid-range"));Ep0CandidateGuardPost(4,0,true,0,NULL,32);
        }
    }
    assert(Ep0CandidateObservation()->fault);assert(Ep0CandidateStopRequested());
    assert(!Ep0CandidateGuardAllow(g_vcControlBuffer,32,2));Ep0CandidateLeave();
    assert(Ep0CandidateStop(svcGetSystemTick()));assert(!Ep0CandidateFinish(22,0));
    printf("{\"case\":\"%s\",\"passed\":true,\"fault\":1,\"stop_requested\":true,\"export_allowed\":false}\n",name);
    return 0;
}
'''


def native_exit():
    s=audit.exit_fixture();main=guarded_main((SINK/'window-30s/source/sysmodule/main.c').read_text())
    original=audit.extract((base.ep0.REPO/'source/sysmodule/main.c').read_text(),'void __appExit(void)','// ============================================================================\n// Main Entry Point')
    callback=audit.extract(main,'void __appExit(void)','// ============================================================================\n// Main Entry Point')
    s=base.trace.replace(s,original,callback)
    old=audit.extract((SINK/'window-30s/source/sysmodule/main.c').read_text(),'    Result video_join=threadWaitForExit','    LOG("SysDVR-UVC exiting')
    new=audit.extract(main,'    if(!ep0_cleanup_begin(&ep0Cleanup))','    LOG("SysDVR-UVC exiting')
    s=base.trace.replace(s,old,new)
    s=base.trace.replace(s,'static Thread g_videoThread=',
        '#include "research/usb-ds-iso/device/ep0_cleanup_gate.h"\nstatic Ep0CleanupGate ep0Cleanup;\nstatic Thread g_videoThread=')
    s=base.trace.replace(s,'candidate_normal();__appExit();','candidate_normal();__appExit();__appExit();')
    s=base.trace.replace(s,'assert(Ep0CandidateStart(11,19200000,0,boot,session,recipe));',
        'if(strcmp(name,"callback-unstarted"))assert(Ep0CandidateStart(11,19200000,0,boot,session,recipe));')
    s=base.trace.replace(s,'if(!active) { Ep0CandidateRequestStop();assert(Ep0CandidateStop(10)); }',
        'if(!active && strcmp(name,"callback-unstarted")) { Ep0CandidateRequestStop();assert(Ep0CandidateStop(10)); }')
    # Extra probes: an unstarted callback is rejected, as is reentry after a
    # cleanup claim (never reopen/duplicate teardown).
    s=base.trace.replace(s,'    bool held=false;',
        '    if(!strcmp(name,"callback-claimed")) { assert(ep0_cleanup_begin(&ep0Cleanup));assert(ep0_cleanup_authorize(&ep0Cleanup));assert(ep0_cleanup_claim(&ep0Cleanup)); }\n'
        '    bool held=false;')
    return s


def run(output):
    output=Path(output);sealed=verify(SINK);previous=audit.base.ep0.PRIVATE/'analysis/A23-control-buffer-cleanup-review-20261013';verify(previous)
    source_audit=base.owner.source_audit();tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS}
    names=[*audit.INPUTS,*('device/'+x for x in DEVICE),'tools/build_a23_guard_candidate.py','tools/build_a23_trace_sink.py','tests/ep0_guard_policy_test.c']
    inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for name in base.DEVICE:
        if base.ep0.sha(ROOT/'device'/name)!=base.ep0.sha(SINK/'dormant/source/uvc'/name):raise ValueError('Runtime drift')
    info=dict(source_sha256=inputs,sealed_sink_manifest_sha256=base.ep0.sha(SINK/'SHA256SUMS'),
              libnx_a_sha256=base.ep0.sha(Path('/opt/devkitpro/libnx/lib/libnx.a')),
              compiler_version=base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','--version']))
    recipe=hashlib.sha256(json.dumps(info,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=recipe,inputs=info),indent=2)+'\n')
    commands=[];flags=['-DISO_PROBE','-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_CONTEXT_AUDIT','-DISO_PROBE_FOLLOWUP_SIA']
    file=output/'guard-buffers.c';file.write_text(native_buffer());commands.append(base.trace.compile_native(file,output/'guard-buffers',flags))
    rows=[];oldrows={r['case']:r['candidate'] for r in json.loads((previous/'audit.json').read_text())['buffer_cases']}
    for case in audit.BUFFER_CASES:
        row=json.loads(base.owner.command([str(output/'guard-buffers'),case]));rows.append(dict(case=case,guarded=row,previous=oldrows[case]))
        if row['cpu_write_overlaps'] or row['same_address_reposts']:raise ValueError('Unsafe reuse remained: '+case)
    file=output/'guard-exit.c';file.write_text(native_exit());commands.append(base.trace.compile_native(file,output/'guard-exit',['-DISO_PROBE']))
    exit_cases=[c for c in audit.EXIT_CASES if not c.startswith('original')]+['callback-claimed','callback-unstarted']
    exits=[json.loads(base.owner.command([str(output/'guard-exit'),case])) for case in exit_cases]
    file=output/'guard-adapter.c';file.write_text(native_adapter());commands.append(base.trace.compile_native(file,output/'guard-adapter',flags))
    adapters=[json.loads(base.owner.command([str(output/'guard-adapter'),case])) for case in ADAPTER_CASES]
    policy=output/'policy-test';commands.append(base.trace.compile_native(ROOT/'tests/ep0_guard_policy_test.c',policy,[]))
    policies=[json.loads(base.owner.command([str(policy),c])) for c in POLICY_CASES]
    builds={}
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();shutil.copytree(SINK/label/'source',folder/'source')
        for name in DEVICE:shutil.copyfile(ROOT/'device'/name,folder/'source/uvc'/name)
        path=folder/'source/uvc/ep0_candidate.c';path.write_text(path.read_text()+fault_function())
        path=folder/'source/uvc/uvc_device.c';path.write_text('#include "ep0_candidate_guard.h"\n'+guarded_handler(path.read_text()))
        path=folder/'source/sysmodule/main.c';path.write_text(guarded_main(path.read_text()))
        configuration=dict(input_digest=recipe,window_ms=0 if label=='dormant' else 30000,offline_compile_only=True)
        digest=hashlib.sha256(json.dumps(configuration,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (folder/'recipe.json').write_text(json.dumps(dict(input_digest=digest,configuration=configuration),indent=2)+'\n')
        (folder/'source/uvc/ep0_candidate_recipe.h').write_text('static const uint8_t ep0CandidateRecipe[32]={'+','.join(str(x) for x in bytes.fromhex(digest))+'};\n')
        builds[label]=base.compile_elf(folder,commands);builds[label].update(runtime_recipe_digest=digest,window_ms=configuration['window_ms'])
    if source_audit!=base.owner.source_audit() or tickets!={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS}:raise ValueError('Production/ticket changed')
    if inputs!={n:base.ep0.sha(ROOT/n) for n in names}:raise ValueError('Input changed')
    verify(SINK);verify(previous)
    result=dict(schema='A23-guarded-candidate-1',source_audit=source_audit,tickets_sha256=tickets,recipe_digest=recipe,
                sealed_input=sealed,source_hashes=inputs,compiler_commands=commands,buffer_cases=rows,buffer_case_count=len(rows),
                exit_cases=exits,exit_case_count=len(exits),policy_cases=policies,policy_case_count=len(policies),builds=builds,
                adapter_cases=adapters,adapter_case_count=len(adapters),
                production_modified=False,prior_runtime_modified=False,usb_accessed=False,sd_accessed=False,firmware_packaged=False,
                hardware_verified=False,root_cause_confirmed=False,unknown_reuse_rejected_before_copy=True,
                cleanup_deferred_to_authorized_callback=True,early_unstarted_cleanup_allowed=False,
                original_usb_behavior_preserved_on_guard_denial=False,live_late_report_recovery_implemented=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);r=run(args.output);print(json.dumps(dict(output=str(args.output),buffers=r['buffer_case_count'],exits=r['exit_case_count'],builds=r['builds']),indent=2))
if __name__=='__main__':main()
