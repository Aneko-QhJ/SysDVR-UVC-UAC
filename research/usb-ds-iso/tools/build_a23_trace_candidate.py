#!/usr/bin/env python3
"""Generate isolated A23 handler copies, replay them, and link full ELF only.

No package/USB/SD/installation/ticket operation. Output must be a new directory.
Native report ABI is modeled; ARM ELF is compiled but never executed.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import audit_a23_ep0 as ep0
import audit_a23_hos_setup as hos
import audit_a23_trace_owner as owner
import probe_a23_ep0_trace as trace
from analyze_ep0_trace import decode
from analyze_ep0_candidate_capture import decode_capture
from build_patch import validate_module,read_mapped,BUILD_ID,SHA256
from workflows.artifacts import verify

DEVICE=('ep0_trace.h','ep0_trace_owner.h','ep0_candidate.h','ep0_candidate.c','ep0_candidate_capture.h')
OWNER_CASES=('drained','iso-pending','iso-wrong-id','iso-state-1','iso-state-2','iso-terminal-4','iso-terminal-5',
             'iso-report-error','iso-duplicate','iso-count-9','ctrl-terminal-4','ctrl-terminal-5','ctrl-timeout',
             'ctrl-report-error','ctrl-wrong-id','ctrl-unknown-status','ctrl-duplicate','failed-post',
             'stop-inside-wait','join-error','trace-overflow','capacity-storm','ctrl-late-terminal')
DEFINES=['-DISO_PROBE','-DISO_RUNTIME_PATCH','-DFILE_LOGGING','-DISO_PROBE_BURST_MODE',
         '-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_CONTEXT_AUDIT','-DISO_PROBE_FOLLOWUP_SIA',
         '-DISO_PROBE_INTERVAL_EXPERIMENT','-DISO_PROBE_INTERVAL=1','-DISO_PROBE_MPS=256']


def poll_source():
    s=(ep0.REPO/'source/uvc/uvc_device.c').read_text()
    return s[s.index('static void _pollIsoProbe(void)'):s.index('\n#endif\n\n// UAC (Audio) context')]


def integrate(s):
    s=trace.instrument(s)
    for direction,channel in [('In',0),('Out',1)]:
        post=f'Result rc = usbDsInterface_Ctrl{direction}PostBufferAsync(iface, buf, len, &urbId);'
        s=trace.replace(s,post,post+f'\n    Ep0CandidateObservePost(iface->interface_index*2+{channel},rc,rc==0,rc ? 0 : urbId);')
        report=f'rc = usbDsInterface_GetCtrl{direction}ReportData(iface, &rpt);'
        s=trace.replace(s,report,report+f'\n    Ep0CandidateObserveReports(iface->interface_index*2+{channel},rc,rc ? NULL : &rpt);')
    post='''rc = usbDsEndpoint_PostBufferAsync(g_isoEndpoint, g_isoBuffer,
            length, &urbId);'''
    s=trace.replace(s,post,post+'\n        Ep0CandidateObservePost(8,rc,rc==0,rc ? 0 : urbId);')
    report='Result rc = usbDsEndpoint_GetReportData(g_isoEndpoint, &report);'
    s=trace.replace(s,report,report+'\n    Ep0CandidateObserveReports(8,rc,rc ? NULL : &report);')
    s=trace.replace(s,'void UvcDeviceProcessRequests(void)','static void _candidateProcessRequests(void)')
    s+='''
void UvcDeviceProcessRequests(void) {
    bool entered=Ep0CandidateEnter();
    if(entered)Ep0CandidateObserveIsoOwnership(g_isoStatus.state,g_isoStatus.urb_id);
    _candidateProcessRequests();
    if(entered)Ep0CandidateLeave();
}
'''
    return s


def instrument_main(s):
    s=trace.replace(s,'#include <string.h>','#include <string.h>\n#include <stdatomic.h>')
    s=trace.replace(s,'static volatile bool g_running = true;','static atomic_bool g_running = true;')
    s=trace.replace(s,'#include "../uvc/uvc_device.h"','#include "../uvc/uvc_device.h"\n#include "../uvc/ep0_candidate.h"\n#include "../uvc/ep0_candidate_recipe.h"')
    s=trace.replace(s,'    LOG("Video stream thread started\\n");','''    uint64_t writer=0;uint8_t boot_nonce[16],session_nonce[16];
    Result identity_rc=svcGetThreadId(&writer,CUR_THREAD_HANDLE);
    randomGet(boot_nonce,sizeof(boot_nonce));randomGet(session_nonce,sizeof(session_nonce));
    if(R_FAILED(identity_rc) || !Ep0CandidateStart(writer,armGetSystemTickFreq(),svcGetSystemTick(),boot_nonce,session_nonce,ep0CandidateRecipe)) {
        g_running=false;return;
    }
    LOG("Video stream thread started\\n");''')
    s=trace.replace(s,'        UvcDeviceProcessRequests();','''        UvcDeviceProcessRequests();
        // Explicit local stop is checked only after the synchronous owner call.
        if(Ep0CandidateStopRequested()) { g_running=false;break; }''')
    s=trace.replace(s,'        Result rc = UvcDeviceWaitReady(1E+9);',
                    '        Result rc = UvcDeviceWaitReady(1E+9);\n'
                    '        if(Ep0CandidateStopRequested()) { g_running=false;break; }')
    s=trace.replace(s,'    LOG("Video stream thread exiting\\n");','''    Ep0CandidateRequestStop();
    (void)Ep0CandidateStop(svcGetSystemTick());
    LOG("Video stream thread exiting\\n");''')
    s=trace.replace(s,'''    JoinThread(&g_videoThread);
    JoinThread(&g_audioThread);
    UvcDeviceExit();''','''    Result video_join=threadWaitForExit(&g_videoThread);
    Result audio_join=threadWaitForExit(&g_audioThread);
    uint64_t exporter=0;
    Result identity_rc=svcGetThreadId(&exporter,CUR_THREAD_HANDLE);
    // Retain buffers/services on unknown ownership or failed thread handoff.
    // No cancel/close/retry is used to make the memory export pass.
    if(R_FAILED(video_join) || R_FAILED(audio_join) || R_FAILED(identity_rc) ||
       !Ep0CandidateFinish(exporter,video_join)) {
        for(;;)svcSleepThread(1E+9);
    }
    threadClose(&g_videoThread);threadClose(&g_audioThread);
    UvcDeviceExit();''')
    return s


def payload_header():
    manifest=json.loads((ep0.PACKAGE/'manifest.json').read_text())
    module=(ep0.PRIVATE/'module/exefs/main').read_bytes();nso=validate_module(module)
    if manifest['build_id']!=BUILD_ID or manifest['original_sha256']!=SHA256:
        raise ValueError('Runtime target binding mismatch')
    ips=ep0.PACKAGE/'atmosphere/exefs_patches/SysDVR-ISO'/(BUILD_ID+'.ips')
    if ep0.sha(ips)!=manifest['patch_sha256']:raise ValueError('Frozen IPS mismatch')
    lines=['/* Isolated output from frozen A23 edits; never writes the private input header. */',
           'static const unsigned char isoRuntimeBuildId[32]={'+','.join(str(x) for x in bytes.fromhex(BUILD_ID))+'};']
    entries=[]
    for i,e in enumerate(manifest['edits']):
        address=int(e['address'],16);before=bytes.fromhex(e['before']);after=bytes.fromhex(e['after'])
        if before!=read_mapped(nso,address,len(before)) or len(before)!=len(after) or len(before)>1024:
            raise ValueError('Frozen runtime edit mismatch')
        for name,data in [('before',before),('after',after)]:
            lines.append(f'static const unsigned char isoRuntime_{i}_{name}[]={{'+','.join(str(x) for x in data)+'};')
        entries.append(f'{{{address},{len(before)},isoRuntime_{i}_before,isoRuntime_{i}_after}}')
    lines.append('static const IsoRuntimeEdit isoRuntimeEdits[]={'+','.join(entries)+'};')
    return '\n'.join(lines)+'\n'


def native_fixture(family,client,recipe):
    s=trace.fixture_copy(family,client)
    services=(ep0.ROOT/'tests/a23_ep0_candidate_services.c').read_text()
    # Exact legacy stubs are replaced only in this isolated copy. Other modeled
    # services and each original scenario/assertion remain unchanged.
    s=trace.replace(s,'typedef struct { unsigned unused; } UsbDsReportData;',
                    'typedef struct { u32 id,requestedSize,transferredSize,urb_status; } UsbDsReportEntry;\n'
                    'typedef struct { UsbDsReportEntry report[8];u32 report_count; } UsbDsReportData;')
    a=s.index('static Result usbDsEndpoint_PostBufferAsync(');b=s.index('static Result usbDsInterface_GetSetupPacket(',a)
    s=s[:a]+services+'\n'+s[b:]
    s=trace.replace(s,'static void _pollIsoProbe(void) { /* No device reports in this fixture. */ }','')
    s=trace.scoped(s,'static Result eventWait(Event *e, u64 timeout) {','static Result eventClear(',
                   lambda chunk:trace.replace(chunk,'static Result eventWait(Event *e, u64 timeout) {',
                    'static bool inject_stop_in_wait;\nstatic void candidate_wait_hook(void);\n'
                    'static Result eventWait(Event *e, u64 timeout) {\n'
                    '    if(inject_stop_in_wait && e->kind==1)candidate_wait_hook();'))
    old=(ep0.ROOT/'tests/a23_ep0_trace_bridge.c').read_text()
    runtime=(ep0.ROOT/'device/ep0_candidate.c').read_text().replace('#include "ep0_candidate.h"','')
    runtime=runtime.replace('#include "ep0_candidate_capture.h"',
                            '#include "research/usb-ds-iso/device/ep0_candidate_capture.h"')
    bridge=(ep0.ROOT/'tests/a23_ep0_candidate_bridge.c').read_text()
    bridge=trace.replace(bridge,'/* CANDIDATE_RECIPE_BYTES */',','.join(str(x) for x in bytes.fromhex(recipe)))
    glue='#define EP0_CANDIDATE_NATIVE\n#include "research/usb-ds-iso/device/ep0_candidate.h"\n'+runtime+'\n'+bridge
    s=trace.replace(s,old,glue)
    if family!='dispatch':
        # Preserve the shared-setup scheduling model; add control fault handling
        # before its delivery logic, using the same injected legacy deadline.
        target='''    (void)timeout;
    deliver_setup();
    return e->signaled ? 0 : 1;'''
        s=trace.replace(s,target,'''    if(e->kind==1 && ack_wait_rc) { now_ns+=timeout;return ack_wait_rc; }
    if(inject_stop_in_wait && e->kind==1)candidate_wait_hook();
    deliver_setup();
    return e->signaled ? 0 : 1;''')
    return s


def compile_elf(folder,commands):
    compiler='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc'
    objects=folder/'objects';objects.mkdir();paths=[]
    flags=['-std=gnu11','-Wall','-Werror','-O3','-g','-ffunction-sections',
           '-march=armv8-a+crc+crypto','-mtune=cortex-a57','-mtp=soft','-fPIE',
           '-D__SWITCH__',*DEFINES,'-I'+str(folder/'source/uvc'),'-I/opt/devkitpro/libnx/include']
    for source in sorted((folder/'source').rglob('*.c')):
        obj=objects/(source.relative_to(folder/'source').as_posix().replace('/','-')+'.o')
        cmd=[compiler,*flags,'-c',str(source),'-o',str(obj)];owner.command(cmd);commands.append(cmd);paths.append(str(obj))
    cmd=[compiler,'-specs=/opt/devkitpro/libnx/switch.specs','-march=armv8-a+crc+crypto',
         '-mtune=cortex-a57','-mtp=soft','-fPIE',*paths,'-L/opt/devkitpro/libnx/lib','-lnx',
         '-Wl,-Map,'+str(folder/'full.map'),'-o',str(folder/'full.elf')]
    owner.command(cmd,dict(os.environ,DEVKITPRO='/opt/devkitpro'));commands.append(cmd)
    symbols=owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-readelf','-Ws',str(folder/'full.elf')])
    (folder/'symbols.txt').write_text(symbols)
    # -O3 may inline static control helpers; require the surviving caller and
    # real IPC callees rather than treating an absent local symbol as missing code.
    for symbol in ('UvcDeviceProcessRequests','VideoStreamThread','usbDsInterface_GetCtrlInReportData',
                   'usbDsInterface_GetCtrlOutReportData','usbDsEndpoint_GetReportData'):
        if symbol not in symbols:raise ValueError('Full ELF lost real source: '+symbol)
    if (folder/'source/uvc/ep0_candidate.c').exists():
        for symbol in ('Ep0CandidateObservePost','Ep0CandidateObserveReports','Ep0CandidateStop',
                       'Ep0CandidateFinish','trace_emit'):
            if symbol not in symbols:raise ValueError('Full candidate lost hook: '+symbol)
    return dict(elf_sha256=ep0.sha(folder/'full.elf'),object_count=len(paths),linked=True,executed=False)


def run(output):
    output=Path(output).resolve();audit=owner.source_audit()
    tickets={name:ep0.sha(ep0.PRIVATE/'analysis'/name) for name in owner.TICKETS}
    module_header=payload_header();poll=poll_source()
    sources=sorted((ep0.REPO/'source').rglob('*'))
    inputs={str(p.relative_to(ep0.REPO)):ep0.sha(p) for p in sources if p.is_file()}
    for name in [*('device/'+x for x in DEVICE),'tools/build_a23_trace_candidate.py',
                 'tools/analyze_ep0_candidate_capture.py','tools/probe_a23_ep0_trace.py','tools/analyze_ep0_trace.py',
                 'tools/audit_a23_ep0.py','tools/audit_a23_hos_setup.py','tools/audit_a23_trace_owner.py',
                 'tests/a23_ep0_dispatch_fixture.c','tests/a23_hos_setup_fixture.c','tests/a23_ep0_trace_bridge.c',
                 'tests/a23_ep0_trace_session.c','tests/a23_ep0_candidate_services.c',
                 'tests/a23_ep0_candidate_bridge.c','tests/a23_ep0_candidate_session.c']:
        inputs[str((ep0.ROOT/name).relative_to(ep0.REPO))]=ep0.sha(ep0.ROOT/name)
    recipe_info=dict(source_sha256=inputs,defines=DEFINES,payload_sha256=hashlib.sha256(module_header.encode()).hexdigest(),
                     libnx_a_sha256=ep0.sha(Path('/opt/devkitpro/libnx/lib/libnx.a')),
                     libnx_usbds_header_sha256=ep0.sha(Path('/opt/devkitpro/libnx/include/switch/services/usbds.h')),
                     libnx_switch_specs_sha256=ep0.sha(Path('/opt/devkitpro/libnx/switch.specs')),
                     compiler_version=owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','--version']))
    recipe=hashlib.sha256(json.dumps(recipe_info,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=recipe,inputs=recipe_info),indent=2)+'\n')
    original=ep0.actual_source();client=integrate(poll+'\n'+original)
    (output/'instrumented-handler.c').write_text(client)
    commands=[];rows=[]
    defines=['-DISO_PROBE','-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_CONTEXT_AUDIT',
             '-DISO_PROBE_FOLLOWUP_SIA','-DSTATUS_BEGIN_NS='+str(math.ceil(hos.host_timing()['after_status_begin_ms']*1e6)),
             '-DSTATUS_END_NS='+str(math.ceil(hos.host_timing()['after_status_end_ms']*1e6))]
    for family,cases in [('dispatch',ep0.SCENARIOS),('shared',hos.SCENARIOS),
                         ('session',('session-kept','session-replaced')),('owner',OWNER_CASES)]:
        for label,source in [('candidate',client),('baseline',poll+'\n'+original)]:
            text=native_fixture('dispatch' if family=='dispatch' else 'shared',source,recipe)
            if family in ('session','owner'):
                suffix='a23_ep0_trace_session.c' if family=='session' else 'a23_ep0_candidate_session.c'
                text=text[:text.index('int main(')]+(ep0.ROOT/'tests'/suffix).read_text()
            file=output/(family+'-'+label+'.c');file.write_text(text)
            commands.append(trace.compile_native(file,output/(family+'-'+label),defines))
        for case in cases:
            observations=[];policies=[];ids=[uuid.uuid4().hex,uuid.uuid4().hex]
            for label in ('candidate','baseline'):
                binary=output/(family+'-'+label+'-'+case+'.bin')
                observations.append(json.loads(owner.command([str(output/(family+'-'+label)),case,str(binary),*ids])))
                policies.append(json.loads(Path(str(binary)+'.owner.json').read_text()))
            if observations[0]!=observations[1]:raise ValueError('USB service behavior changed: '+case)
            if policies[0]['services']!=policies[1]['services']:raise ValueError('USB service call count changed: '+case)
            path=output/(family+'-candidate-'+case+'.bin')
            analysis=decode(path.read_bytes());(path.with_suffix('.json')).write_text(json.dumps(analysis,indent=2)+'\n')
            policy=policies[0]
            if policy['export_allowed']:
                capture=decode_capture(Path(str(path)+'.capture.bin').read_bytes(),recipe)
                if capture['trace']!=analysis:raise ValueError('Capture inner trace mismatch')
                Path(str(path)+'.capture.json').write_text(json.dumps(capture,indent=2)+'\n')
            rows.append(dict(family=family,case=case,baseline_identical=True,service_observation=observations[0],
                             owner=policy,trace=path.name,records=analysis['record_count']))
    builds={}
    for label in ('baseline','candidate'):
        folder=output/label;folder.mkdir();shutil.copytree(ep0.REPO/'source',folder/'source')
        (folder/'source/uvc/iso_runtime_payload.h').write_text(module_header)
        if label=='candidate':
            for name in DEVICE:shutil.copyfile(ep0.ROOT/'device'/name,folder/'source/uvc'/name)
            (folder/'source/uvc/ep0_candidate_recipe.h').write_text(
                'static const uint8_t ep0CandidateRecipe[32]={'+','.join(str(x) for x in bytes.fromhex(recipe))+'};\n')
            src=folder/'source/uvc/uvc_device.c'
            src.write_text('#include "ep0_candidate.h"\n'+integrate(src.read_text()))
            src=folder/'source/sysmodule/main.c';src.write_text(instrument_main(src.read_text()))
        builds[label]=compile_elf(folder,commands)
    if owner.source_audit()!=audit or tickets!={n:ep0.sha(ep0.PRIVATE/'analysis'/n) for n in owner.TICKETS}:
        raise ValueError('Production/ticket changed during candidate work')
    if any(ep0.sha(ep0.REPO/p)!=sha for p,sha in inputs.items()):raise ValueError('Input changed during build')
    result=dict(schema='A23-EP0-handler-candidate-1',source_audit=audit,tickets_sha256=tickets,
                compiler_commands=commands,source_replays=rows,source_replay_count=len(rows),builds=builds,
                production_modified=False,firmware_packaged=False,usb_accessed=False,sd_accessed=False,
                hardware_verified=False,root_cause_confirmed=False,actual_handler_hooks_inserted_in_isolated_copy=True,
                complete_instrumented_a23_elf_link=True,filesystem_sink_implemented=False,
                stop_request_api_implemented=True,live_stop_trigger_present=False,
                simulation_wire_only=True,real_trace_overhead_measured=False,
                native_report_services_modeled=True,hos_machine_code_emulated=False,
                runtime_payload_records=module_header.count('static const unsigned char isoRuntime_')//2)
    result['recipe_digest']=recipe;result['recipe_inputs']=recipe_info
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    for name in ('A23-EP0-trace-owner-review-20261013','A23-EP0-trace-owner-validation-20261013'):
        verify(ep0.PRIVATE/'analysis'/name)
    args.output.mkdir(parents=True,exist_ok=False);r=run(args.output)
    print(json.dumps(dict(output=str(args.output),source_replays=r['source_replay_count'],builds=r['builds']),indent=2))


if __name__=='__main__':main()
