#!/usr/bin/env python3
"""Offline extension of sealed A23 handler candidate: one-shot sink and stop window.
Compiles dormant and 30-second sample ELFs; NEVER executes, packages or deploys ARM.
Filesystem ABI is modeled in native tests, no Switch/card/USB operations.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import build_a23_trace_candidate as base
from analyze_ep0_candidate_capture import decode_capture
from workflows.artifacts import verify

ROOT=base.ep0.ROOT
SEALED=base.ep0.PRIVATE/'analysis/A23-EP0-handler-candidate-review-20261013-terminal'
DEVICE=('ep0_candidate_sink.h','ep0_candidate_window.h','ep0_candidate_file.h','ep0_candidate_file.c')
CASES=('ok','short-read','fs-open-error','create-error','collision','file-open-error','write-error',
       'silent-short-write','corrupt-write','flush-error','size-error','extra-byte','short-size','read-error',
       'zero-read','oversize-read','commit-error','not-finished','pending','fault','join-error')


def validate_runtime(current=None):
    current=ROOT/'device' if current is None else Path(current)
    for name in base.DEVICE:
        if base.ep0.sha(current/name)!=base.ep0.sha(SEALED/'candidate/source/uvc'/name):
            raise ValueError('Native and sealed ARM runtime differ: '+name)


def main_source(s,ms):
    if ms not in (0,30000):raise ValueError('Only dormant or offline 30-second compile samples')
    replace=base.trace.replace
    s=replace(s,'#include "../uvc/ep0_candidate_recipe.h"',
              '#include "../uvc/ep0_candidate_recipe.h"\n#include "../uvc/ep0_candidate_file.h"\n#include "../uvc/ep0_candidate_window.h"')
    s=replace(s,'    LOG("Video stream thread started\\n");',
              f'    Ep0CandidateWindow window={{0}};\n'
              f'    if(!ep0_window_init(&window,svcGetSystemTick(),armGetSystemTickFreq(),{ms})) {{ g_running=false;Ep0CandidateRequestStop();(void)Ep0CandidateStop(svcGetSystemTick());return; }}\n'
              '    LOG("Video stream thread started\\n");')
    stop='        if(Ep0CandidateStopRequested()) { g_running=false;break; }'
    if s.count(stop)!=2:raise ValueError('Owner stop boundary count drift')
    s=s.replace(stop,'        if(ep0_window_expired(&window,svcGetSystemTick()))Ep0CandidateRequestStop();\n'+stop)
    s=replace(s,'    threadClose(&g_videoThread);threadClose(&g_audioThread);',
              '    // One save attempt after both joins and successful ownership export.\n'
              '    if(!Ep0CandidateSaveCapture()) { for(;;)svcSleepThread(1E+9); }\n'
              '    threadClose(&g_videoThread);threadClose(&g_audioThread);')
    return s


def run(output):
    output=Path(output);sealed=verify(SEALED);validate_runtime();source_audit=base.owner.source_audit()
    tickets={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS}
    names=[*('device/'+x for x in (*DEVICE,*base.DEVICE)),'tests/ep0_candidate_sink_test.c','tools/build_a23_trace_sink.py',
           'tools/build_a23_trace_candidate.py','tools/audit_a23_trace_owner.py','tools/audit_a23_ep0.py',
           'tools/probe_a23_ep0_trace.py','tools/analyze_ep0_candidate_capture.py','tools/analyze_ep0_trace.py',
           'tools/workflows/artifacts.py']
    inputs={n:base.ep0.sha(ROOT/n) for n in names}
    recipe_info=dict(previous_recipe=json.loads((SEALED/'recipe.json').read_text()),
                     previous_manifest_sha256=base.ep0.sha(SEALED/'SHA256SUMS'),source_sha256=inputs,
                     fs_header_sha256=base.ep0.sha(Path('/opt/devkitpro/libnx/include/switch/services/fs.h')),
                     libnx_a_sha256=base.ep0.sha(Path('/opt/devkitpro/libnx/lib/libnx.a')),
                     switch_specs_sha256=base.ep0.sha(Path('/opt/devkitpro/libnx/switch.specs')),
                     compiler_version=base.owner.command(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-gcc','--version']),
                     window_samples_ms=[0,30000],sd_operations_executed=False)
    recipe=hashlib.sha256(json.dumps(recipe_info,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    (output/'recipe.json').write_text(json.dumps(dict(input_digest=recipe,inputs=recipe_info),indent=2)+'\n')
    commands=[];binary=output/'sink-native'
    cmd=['clang','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-g',
         '-I'+str(base.ep0.REPO),str(ROOT/'tests/ep0_candidate_sink_test.c'),'-o',str(binary)]
    base.owner.command(cmd);commands.append(cmd);rows=[]
    for case in CASES:
        dest=output/(case+'.capture.bin');cmd=[str(binary),case,str(dest)]
        result=json.loads(base.owner.command(cmd));commands.append(cmd)
        if result['ok']!=(case in ('ok','short-read')):raise ValueError('Unexpected adapter result: '+case)
        if result['ok']:decode_capture(dest.read_bytes())
        rows.append(dict(case=case,observation=result))
    roundtrips=[]
    for i,src in enumerate(sorted(SEALED.glob('*-candidate-*.bin.capture.bin'))):
        original=decode_capture(src.read_bytes(),recipe_info['previous_recipe']['input_digest'])
        for case in ('ok','short-read','silent-short-write','late-read-error','commit-error'):
            dest=output/(f'roundtrip-{i:02d}-{case}.bin');cmd=[str(binary),case,str(dest),str(src)]
            result=json.loads(base.owner.command(cmd));commands.append(cmd)
            if result['ok']!=(case in ('ok','short-read')):raise ValueError('Unexpected roundtrip: '+case)
            if case in ('ok','short-read','commit-error'):
                if dest.read_bytes()!=src.read_bytes():raise ValueError('Readback roundtrip differs')
                if decode_capture(dest.read_bytes())!=decode_capture(src.read_bytes()):raise ValueError('Decoder differs')
            roundtrips.append(dict(source=src.name,source_sha256=base.ep0.sha(src),case=case,
                                   original_recipe=original['recipe_digest'],observation=result))
    builds={}
    for ms in (0,30000):
        folder=output/('dormant' if ms==0 else 'window-30s');folder.mkdir()
        configuration=dict(input_digest=recipe,window_ms=ms,activation='offline_compile_only')
        runtime_recipe=hashlib.sha256(json.dumps(configuration,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        (folder/'recipe.json').write_text(json.dumps(dict(input_digest=runtime_recipe,configuration=configuration),indent=2)+'\n')
        shutil.copytree(SEALED/'candidate/source',folder/'source')
        for name in DEVICE:shutil.copyfile(ROOT/'device'/name,folder/'source/uvc'/name)
        path=folder/'source/uvc/ep0_candidate_recipe.h'
        path.write_text('static const uint8_t ep0CandidateRecipe[32]={'+','.join(str(x) for x in bytes.fromhex(runtime_recipe))+'};\n')
        path=folder/'source/sysmodule/main.c';path.write_text(main_source(path.read_text(),ms))
        builds[folder.name]=base.compile_elf(folder,commands)
        builds[folder.name].update(window_ms=ms,runtime_recipe_digest=runtime_recipe)
        for symbol in ('Ep0CandidateSaveCapture','fsFileRead','fsFileWrite','fsFsCreateFile','fsFsCommit'):
            if symbol not in (folder/'symbols.txt').read_text():raise ValueError('Missing sink IPC: '+symbol)
    if source_audit!=base.owner.source_audit() or tickets!={n:base.ep0.sha(base.ep0.PRIVATE/'analysis'/n) for n in base.owner.TICKETS}:
        raise ValueError('Production or ticket changed')
    if inputs!={n:base.ep0.sha(ROOT/n) for n in names}:raise ValueError('Input changed')
    verify(SEALED)
    result=dict(schema='A23-EP0-candidate-sink-1',source_audit=source_audit,tickets_sha256=tickets,
                sealed_input=sealed,recipe_digest=recipe,compiler_commands=commands,adapter_cases=rows,
                adapter_case_count=len(rows),roundtrips=roundtrips,roundtrip_count=len(roundtrips),
                window_native_cases=11,builds=builds,usb_accessed=False,sd_accessed=False,
                production_modified=False,firmware_packaged=False,hardware_verified=False,root_cause_confirmed=False,
                filesystem_abi_modeled=True,filesystem_sink_implemented=True,window_default_disabled=True,
                window_checked_only_between_owner_calls=True,window_stop_latency_bounded=False,
                durable_after_power_loss_verified=False,failed_file_retained=True,automatic_retry=False)
    (output/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(base.ep0.sha(p)+'  '+str(p.relative_to(output))+'\n' for p in sorted(output.rglob('*')) if p.is_file()))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False);r=run(args.output)
    print(json.dumps(dict(output=str(args.output),adapter_cases=r['adapter_case_count'],roundtrips=r['roundtrip_count'],builds=r['builds']),indent=2))

if __name__=='__main__':main()
