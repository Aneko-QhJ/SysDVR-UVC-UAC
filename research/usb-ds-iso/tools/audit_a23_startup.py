#!/usr/bin/env python3
"""Audit actual startup functions with injected service/thread failures, offline only."""
import argparse,json,shutil
from pathlib import Path
import build_a23_diagnostic_sink as sink
from workflows.artifacts import verify
base=sink.base;ROOT=sink.ROOT;REPO=base.ep0.REPO
SEALED=base.ep0.PRIVATE/'analysis/A23-diagnostic-sink-review-20261014'
CASES=('core-ok','core-video-error','core-audio-error','core-fs-error','core-sd-error','core-fs-audio-error','core-sd-audio-error',
       'serial-init-error','serial-get-error','log-delete-error','log-create-error','core-reentry','retry-partial',
       'capture-ok','capture-video-error','capture-audio-error',
       'usb-init-error','usb-descriptor-error','usb-vc-error','usb-vs-error','usb-append-error','usb-video-ep-error',
       'usb-iso-register-error','usb-iso-append-error','usb-iso-ep-error','usb-iso-enable-error','usb-enable-error','usb-unsupported','usb-ok','usb-reentry',
       'app-sm-error','app-setsys-error','app-fw-error','app-core-video-error','app-core-audio-error',
       'video-create-error','video-start-error','audio-create-error','audio-start-error','launch-ok')
INPUTS=('tools/audit_a23_startup.py','tests/a23_startup_fixture.c')
PRODUCTION=('source/core.c','source/core.h','source/capture.c','source/grcd.c','source/uvc/uvc_device.c','source/sysmodule/main.c')

def extract(s,start,end):return sink.bounded.guard.audit.extract(s,start,end)

def native_source():
    s=(ROOT/'tests/a23_startup_fixture.c').read_text();r=base.trace.replace
    core=(REPO/'source/core.c').read_text();capture=(REPO/'source/capture.c').read_text();grcd=(REPO/'source/grcd.c').read_text()
    main=(SEALED/'dormant/source/sysmodule/main.c').read_text();usb=(REPO/'source/uvc/uvc_device.c').read_text()
    capture=extract(capture,'Result CaptureInitialize(void)','bool CaptureReadVideoFrame')
    grcd='void grcdServiceClose(Service* svc);\n'+extract(grcd,'Result grcdServiceOpen(Service* out)','Result grcdServiceBegin')
    logging=extract(core,'static FsFileSystem g_sdCard;','void LogFunctionImpl(const char* fmt, ...)')
    body=extract(core,'static Result _getSerialNumber(void)','const char* CoreGetSerialNumber')
    body=r(body,'    CaptureFinalize();','    callback_core++; /* Native observation, after initialized check. */\n    CaptureFinalize();')
    core='static char g_serialNumber[32]="SysDVR-UVC";\nstatic bool g_coreInitialized=false;\n'+logging+body
    usb=extract(usb,'Result UvcDeviceInitialize(const UvcDeviceConfig* config)','void UvcDeviceExit(void)')
    launch=extract(main,'    LaunchThread(&g_videoThread, VideoStreamThread, NULL,','    LOG("SysDVR-UVC running')
    appinit=extract(main,'void __appInit(void)','// Called after main() returns to cleanup')
    callback=extract(main,'void __appExit(void)','// ============================================================================\n// Main Entry Point')
    for marker,text in [('GRCD',grcd),('CAPTURE',capture),('CORE',core),('USB',usb),('APP_INIT',appinit),('APP_EXIT',callback),('LAUNCH',launch)]:
        s=r(s,'/* INSERT_'+marker+' */',text)
    header=(REPO/'source/core.h').read_text()
    for macro in ('#define R_RET_ON_FAIL(x) do { Result rc = x; if (R_FAILED(rc)) return rc; } while (0)',
                  '#define R_THROW(x) do { Result r = x; if (R_FAILED(r)) { fatalThrow(r); } } while(0)'):
        if header.count(macro)!=1:raise ValueError('Failure macro drift')
    return s

def run(output):
    output=Path(output);sealed=verify(SEALED);validated=verify(base.ep0.PRIVATE/'analysis/A23-diagnostic-sink-validation-20261014');old=json.loads((SEALED/'audit.json').read_text())
    audit=base.owner.source_audit();assert audit==old['source_audit']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    for n in PRODUCTION:
        frozen=base.ep0.PRIVATE/'analysis/A23-diagnostic-sink-validation-20261014/production-source-snapshots'/n
        if not frozen.exists():frozen=SEALED/'dormant'/n
        assert (REPO/n).read_bytes()==frozen.read_bytes(),n
    names=list(dict.fromkeys([*old['source_hashes'],*INPUTS]));inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for n,h in old['source_hashes'].items():
        if inputs[n]!=h:raise ValueError('Dependency drift: '+n)
    production={n:base.ep0.sha(REPO/n) for n in PRODUCTION}
    for n in PRODUCTION:
        dest=output/'production-source-snapshots'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(REPO/n,dest)
    for n in names:
        dest=output/'source-snapshots'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest)
    api=Path('/opt/devkitpro/libnx/include/switch/services/usbds.h');shutil.copyfile(api,output/'usbds-header.h')
    source=output/'startup-native.c';source.write_text(native_source());binary=output/'startup-native'
    command=base.trace.compile_native(source,binary,[]);rows=[]
    for case in CASES:
        rows.append(json.loads(base.owner.command([str(binary),case])))
    assert production=={n:base.ep0.sha(REPO/n) for n in PRODUCTION};assert inputs=={n:base.ep0.sha(ROOT/n) for n in names}
    assert tickets=={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};verify(SEALED)
    result=dict(schema='A23-startup-audit-1',source_audit=audit,production_sources_sha256=production,source_hashes=inputs,
        tickets_sha256=tickets,sealed_input=sealed,sealed_validation_input=validated,libnx_usbds_header_sha256=base.ep0.sha(api),compiler_commands=[command],
        cases=rows,case_count=len(rows),actual_core_capture_grcd_functions_replayed=True,actual_top_level_usb_init_replayed=True,
        usb_descriptor_interface_iso_helpers_modeled=True,usb_exit_auto_close_is_model=True,fatal_callback_forced_not_observed=True,
        production_modified=False,prior_runtime_modified=False,new_arm_build=False,firmware_packaged=False,
        usb_accessed=False,sd_accessed=False,arm_executed=False,actual_threads_executed=False,
        actual_dma_executed=False,fatal_callback_reachability_verified=False,initialization_rollback_implemented=False,
        hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);r=run(a.output);print(json.dumps(dict(output=str(a.output),cases=r['case_count']),indent=2))
if __name__=='__main__':main()
