#!/usr/bin/env python3
"""Independent A23 diagnostic sink candidate; native FS models and ARM link only."""
import argparse,hashlib,json,shutil
from pathlib import Path
import build_a23_bounded_candidate as bounded
from analyze_ep0_diagnostic import decode_diagnostic
from workflows.artifacts import verify
base=bounded.base;ROOT=bounded.ROOT
SEALED=base.ep0.PRIVATE/'analysis/A23-bounded-candidate-review-20261014'
DEVICE=('ep0_diagnostic_capture.h','ep0_diagnostic_sink.h','ep0_diagnostic_file.h','ep0_diagnostic_file.c')
INPUTS=(*('device/'+n for n in DEVICE),'device/ep0_candidate_sink.h','device/ep0_candidate_file.h','device/ep0_candidate_file.c',
        'tools/build_a23_diagnostic_sink.py','tests/ep0_diagnostic_file_test.c')
ADAPTER_CASES=('ok','short-read','fs-open-error','create-error','collision','file-open-error','write-error','silent-short-write',
    'corrupt-write','flush-error','size-error','extra-byte','short-size','read-error','late-read-error','zero-read','oversize-read',
    'commit-error','not-finished','unstarted','live','video-join-error','audio-join-error','wrong-exporter','healthy','fault','maximum')
SHUTDOWN_CASES=('ok','healthy','normal-sink-error','video-join-error','audio-join-error','exporter-error','unstarted','live',
    'callback-live','callback-unstarted','commit-error','collision','fs-open-error','maximum')

def main_source(s):
    r=base.trace.replace
    s=r(s,'#include "../uvc/ep0_cleanup_gate.h"','#include "../uvc/ep0_cleanup_gate.h"\n#include "../uvc/ep0_diagnostic_file.h"')
    old='''    if(R_FAILED(video_join) || R_FAILED(audio_join) || R_FAILED(identity_rc) ||
       !Ep0CandidateFinish(exporter,video_join)) {
        for(;;)svcSleepThread(1E+9);
    }'''
    new='''    if(R_FAILED(video_join) || R_FAILED(audio_join) || R_FAILED(identity_rc)) {
        for(;;)svcSleepThread(1E+9);
    }
    if(!Ep0CandidateFinish(exporter,video_join)) {
        // Joined CPU metadata only. Saving a diagnostic never permits teardown.
        (void)Ep0CandidateSaveDiagnostic(exporter,video_join,audio_join,ep0CandidateRecipe);
        for(;;)svcSleepThread(1E+9);
    }'''
    return r(s,old,new)

def native_source(folder):
    s=(ROOT/'tests/ep0_diagnostic_file_test.c').read_text();r=base.trace.replace
    runtime=(folder/'source/uvc/ep0_candidate.c').read_text()
    for header in ('ep0_candidate.h','ep0_candidate_capture.h'):
        runtime=runtime.replace('#include "'+header+'"','#include "research/usb-ds-iso/device/'+header+'"')
    s=r(s,'/* INSERT_RUNTIME */',runtime)
    s=r(s,'/* INSERT_RECIPE */',(folder/'source/uvc/ep0_candidate_recipe.h').read_text())
    main=(folder/'source/sysmodule/main.c').read_text()
    callback=bounded.guard.audit.extract(main,'void __appExit(void)','// ============================================================================\n// Main Entry Point')
    tail=bounded.guard.audit.extract(main,'    g_running = false;\n    if(!ep0_cleanup_begin','    LOG("SysDVR-UVC exiting')
    s=r(s,'/* INSERT_APP_EXIT */',callback)
    return r(s,'/* INSERT_SHUTDOWN */',tail)

def run(output):
    output=Path(output);sealed=verify(SEALED);old=json.loads((SEALED/'audit.json').read_text())
    source_audit=base.owner.source_audit();assert source_audit==old['source_audit']
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};assert tickets==old['tickets_sha256']
    names=list(dict.fromkeys([*old['source_hashes'],*INPUTS]));inputs={n:base.ep0.sha(ROOT/n) for n in names}
    for n,h in old['source_hashes'].items():
        if inputs[n]!=h:raise ValueError('Sealed input drift: '+n)
    info=dict(source_sha256=inputs,sealed_manifest_sha256=base.ep0.sha(SEALED/'SHA256SUMS'),
        libnx_a_sha256=base.ep0.sha(Path('/opt/devkitpro/libnx/lib/libnx.a')),
        fs_header_sha256=base.ep0.sha(Path('/opt/devkitpro/libnx/include/switch/services/fs.h')),
        compiler_version=base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','--version']))
    recipe=hashlib.sha256(json.dumps(info,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    input_digest=recipe
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=recipe,inputs=info),indent=2)+'\n')
    commands=[];builds={}
    for label in ('dormant','window-30s'):
        folder=output/label;folder.mkdir();shutil.copytree(SEALED/label/'source',folder/'source')
        for n in DEVICE:shutil.copyfile(ROOT/'device'/n,folder/'source/uvc'/n)
        config=dict(input_digest=recipe,window_ms=old['builds'][label]['window_ms'],offline_compile_only=True,
            diagnostic_max=6656,diagnostic_format='EP0DIA1',diagnostic_never_authorizes_cleanup=True)
        digest=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (folder/'recipe.json').write_text(json.dumps(dict(input_digest=digest,configuration=config),indent=2)+'\n')
        (folder/'source/uvc/ep0_candidate_recipe.h').write_text(bounded.recipe_header(digest))
        p=folder/'source/sysmodule/main.c';p.write_text(main_source(p.read_text()))
        builds[label]=base.compile_elf(folder,commands);builds[label].update(runtime_recipe_digest=digest,window_ms=config['window_ms'])
        symbols=(folder/'symbols.txt').read_text()
        for name in ('Ep0CandidateSaveDiagnostic','fsFsCreateFile','fsFileRead','fsFsCommit'):
            if name not in symbols:raise ValueError('Missing symbol '+name)
    file=output/'diagnostic-file-native.c';file.write_text(native_source(output/'dormant'))
    binary=output/'diagnostic-file-native';commands.append(base.trace.compile_native(file,binary,[]))
    limits=json.loads(base.owner.command([str(binary),'limits','adapter',str(output/'unused')]))
    rows=[];recipe=builds['dormant']['runtime_recipe_digest']
    for mode,cases in (('adapter',ADAPTER_CASES),('shutdown',SHUTDOWN_CASES)):
        for case in cases:
            path=output/(mode+'-'+case+'.diagnostic.bin');cmd=[str(binary),case,mode,str(path)]
            row=json.loads(base.owner.command(cmd));commands.append(cmd);row.update(case=case,mode=mode)
            if path.exists():
                row['diagnostic']=decode_diagnostic(path.read_bytes(),recipe)
                (output/(mode+'-'+case+'.diagnostic.json')).write_text(json.dumps(row['diagnostic'],indent=2)+'\n')
            if mode=='shutdown':
                healthy=case=='healthy'
                assert row['held']!=healthy
                assert (row['thread_closes'],row['uvc_closes'],row['core_closes'],row['sm_closes'])==((2,1,1,1) if healthy else (0,0,0,0))
            rows.append(row)
    roundtrips=[]
    for src in sorted(SEALED.glob('*.diagnostic.bin')):
        original=decode_diagnostic(src.read_bytes())
        for case in ('ok','short-read','silent-short-write','late-read-error','commit-error'):
            path=output/('roundtrip-'+src.stem+'-'+case+'.bin');cmd=[str(binary),case,'roundtrip',str(path),str(src)]
            row=json.loads(base.owner.command(cmd));commands.append(cmd)
            assert row['ok']==(case in ('ok','short-read'))
            if case in ('ok','short-read','commit-error'):
                assert path.read_bytes()==src.read_bytes();assert decode_diagnostic(path.read_bytes())==original
            roundtrips.append(dict(source=src.name,source_sha256=base.ep0.sha(src),case=case,observation=row))
    assert inputs=={n:base.ep0.sha(ROOT/n) for n in names};assert source_audit==base.owner.source_audit()
    assert tickets=={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS};verify(SEALED)
    result=dict(schema='A23-diagnostic-sink-1',source_audit=source_audit,source_hashes=inputs,tickets_sha256=tickets,
        sealed_input=sealed,recipe_digest=input_digest,recipe_inputs=info,compiler_commands=commands,builds=builds,cases=rows,
        adapter_case_count=len(ADAPTER_CASES),shutdown_case_count=len(SHUTDOWN_CASES),roundtrips=roundtrips,roundtrip_count=len(roundtrips),
        limit_policy=limits,diagnostic_sink_in_candidate=True,diagnostic_authorizes_cleanup=False,diagnostic_max=6656,
        failed_file_retained=True,automatic_retry=False,normal_sink_modified=False,diagnostic_wire_modified=False,
        admission_counters_in_diagnostic_wire=False,initialization_rollback_implemented=False,
        filesystem_abi_modeled=True,durable_after_power_loss_verified=False,actual_threads_executed=False,
        production_modified=False,prior_runtime_modified=False,usb_accessed=False,sd_accessed=False,
        firmware_packaged=False,arm_executed=False,hardware_verified=False,root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);r=run(a.output)
    print(json.dumps(dict(output=str(a.output),adapters=r['adapter_case_count'],shutdown=r['shutdown_case_count'],roundtrips=r['roundtrip_count'],builds=r['builds']),indent=2))
if __name__=='__main__':main()
