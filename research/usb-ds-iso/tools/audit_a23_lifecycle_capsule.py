#!/usr/bin/env python3
"""Offline lifecycle capsule prototype and insertion review. Not a device build."""
import argparse
import json
from pathlib import Path
import re
import subprocess

import a23_lifecycle_capsule as capsule
import build_a23_quiet_deployment as package
from analyze_a23_elf_boundaries import build_functions, function_digest

b=package.common;ROOT=package.ROOT;ANALYSIS=package.ANALYSIS
OLD=ANALYSIS/'A23-quiet-once-review-20261016'
NEW=('device/ep0_lifecycle_capsule.h','tools/a23_lifecycle_capsule.py',
     'tools/audit_a23_lifecycle_capsule.py','tests/a23_lifecycle_capsule_fixture.c','tests/test_a23_lifecycle_capsule.py')
SCENARIOS=('prepared-only','window-not-observed','video-join-blocked','audio-join-blocked','video-join-failed',
           'sd-open-blocked','sd-open-failed','create-blocked','create-failed','diagnostic-saved','capacity')
MODEL_RECIPE='03'+'00'*31


def original_review():
    source=package.DEVICE/'source';main=(source/'sysmodule/main.c').read_text()
    points={
      'prepare_before_usb':'    Result rc = UvcDeviceInitialize(&uvcConfig);',
      'persist_then_defer_before_workers':'    CoreSetDiagnosticQuiet(true);',
      'main_loop_has_left':'    g_running = false;\n    if(!ep0_cleanup_begin',
      'video_join_call':'    Result video_join=threadWaitForExit(&g_videoThread);',
      'audio_join_call':'    Result audio_join=threadWaitForExit(&g_audioThread);',
      'identity_after_joins':'    Result identity_rc=svcGetThreadId(&exporter,CUR_THREAD_HANDLE);',
      'resume_logging_after_success':'    CoreSetDiagnosticQuiet(false);  // Both workers have successfully joined.',
      'diagnostic_save':'        bool diagnostic_saved=Ep0CandidateSaveDiagnostic',
      'normal_save':'    bool normal_saved=Ep0CandidateSaveCapture();',
      'failed_save_retains':'    if(!normal_saved || !execution_saved) { for(;;)svcSleepThread(1E+9); }',
    }
    anchors={}
    for name,text in points.items():
        b.require(main.count(text)==1,'insertion point drift: '+name)
        offset=main.index(text);anchors[name]=dict(line=main[:offset].count('\n')+1,text=text)
    b.require('static atomic_bool g_running = true;' in main,'running flag drift')
    protocol=(source/'uvc/iso_probe_protocol.h').read_text()
    b.require('enum { ISO_PROBE_IDLE, ISO_PROBE_PENDING, ISO_PROBE_COMPLETE,\n       ISO_PROBE_FAILED, ISO_PROBE_RETAINED };' in protocol,'ISO state enum drift')
    files={n:b.sha(b.plain(source/n)) for n in ('sysmodule/main.c','uvc/iso_probe_protocol.h',
        'uvc/ep0_candidate_file.c','uvc/ep0_diagnostic_file.c','uvc/ep0_session_file.c')}
    for n in ('uvc/ep0_candidate_file.c','uvc/ep0_diagnostic_file.c','uvc/ep0_session_file.c'):
        text=(source/n).read_text();b.require('fsOpenSdCardFileSystem' in text and 'fsFsCreateFile' in text,'save adapter drift')
    blob=b.plain(package.DEVICE/'full.elf');text=(package.DEVICE/'disassembly.txt').read_text()
    functions,metadata=build_functions(blob,text)
    byname={alias:f for f in functions.values() for alias in f['aliases']}
    machine={}
    for name in ('main','VideoStreamThread','Ep0CandidateSaveCapture','Ep0CandidateSaveDiagnostic','Ep0ExecutionBuildJoined','Ep0ExecutionSaveJoined'):
        f=byname[name];calls=[]
        for pc,op,arg in f['instructions']:
            if op=='bl':calls.append(dict(address=pc,target=arg))
        machine[name]=dict(address=f['start'],function_sha256=function_digest(f),calls=calls)
    return dict(elf_sha256=b.sha(blob),source_hashes=files,insertion_points=anchors,elf_functions=machine,
        iso_state4='retained',window_may_wait_in_synchronous_call=True,source_and_elf_only=True,
        actual_exit_path_known=False,actual_save_failure_known=False)


def run(output):
    output=package.output_path(output);protected=b.load(OLD/'protected-inputs.json')
    hashes=b.load(OLD/'source-hashes.json');b.require(len(hashes)==184,'prior source inventory')
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'prior source drift: '+n)
    for n,h in protected['production'].items():b.require(b.sha(b.plain(b.REPO/n))==h,'production drift')
    for kind in ('tickets','offline_records_sha256'):
        for n,h in protected[kind].items():b.require(b.sha(b.plain(ANALYSIS/n))==h,'record drift')
    record=ANALYSIS/'A23-quiet-once-20261016-interface2.json';record_raw=b.plain(record)
    live=b.load(record);b.require(live['stage']=='failed_no_retry' and live['remaining']==0 and live['acquisition_enabled'] is False,'live record drift')
    refs=[]
    for name in ('A23-quiet-first-live-recovery-validation-20261016','A23-quiet-first-live-host-20261016'):
        root=ANALYSIS/name;row=package.verify(root);row['manifest_sha256']=b.sha(b.plain(root/'SHA256SUMS'));refs.append(row)
    refs.append(package.verify(package.device.DEVICE))
    output.mkdir(mode=0o700,parents=True)
    for n in NEW:
        name='research/usb-ds-iso/'+n;raw=b.plain(ROOT/n);hashes[name]=b.sha(raw);package.put(output,'inputs/'+n,raw)
    original=original_review();b.write(output/'original-path-review.json',original)
    command=['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
             '-I'+str(output/'inputs/device'),str(output/'inputs/tests/a23_lifecycle_capsule_fixture.c'),'-o',str(output/'native-model')]
    compile_result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=True)
    package.put(output,'compile.log',compile_result.stdout);b.write(output/'compile-command.json',command)
    cases={}
    def execute(name,scenario,fail_at):
        path=output/(name+'.bin');row=json.loads(subprocess.check_output([str(output/'native-model'),scenario,str(fail_at),str(path)]))
        decoded=capsule.decode(b.plain(path),MODEL_RECIPE)
        b.require(decoded['error'] is None and decoded['tail'] in ('zero_tail','capacity_end'),'native format invalid')
        b.write(output/(name+'.json'),dict(model=row,decoded=decoded));cases[name]=row
    for scenario in SCENARIOS:execute(scenario,scenario,0)
    for i in range(1,cases['diagnostic-saved']['writes']+1):execute('write-failure-'+str(i),'diagnostic-saved',i)
    b.require(b.plain(record)==record_raw,'live record changed')
    for n,h in hashes.items():b.require(b.sha(b.plain(b.REPO/n))==h,'source changed')
    result=dict(schema='A23-lifecycle-capsule-prototype-review-1',source_hashes=hashes,prior_sources=184,new_sources=len(NEW),
        original_elf_sha256=original['elf_sha256'],native_model_cases=cases,prototype_format_bytes=capsule.MAX,
        stage_count=len(capsule.STAGES),model_recipe=MODEL_RECIPE,source_references=refs,
        device_instrumentation_integrated=False,device_rebuilt=False,host_rebuilt=False,firmware_packaged=False,
        deployed=False,usb_requests=0,sd_accesses=0,attempt_issued=False,remaining=0,
        hardware_verified=False,root_cause_confirmed=False,new_device_stack_bound_verified=False,
        limitations=['No production SDK file adapter or ARM integration yet','Stage notes report observations, not ownership or latest execution proof',
                     'No periodic I/O while main waits for g_running; missing loop-left note cannot prove a hang',
                     'Journal I/O can itself block; a final valid record cannot authenticate its own commit'])
    b.write(output/'audit.json',result);b.write(output/'protected-inputs.json',protected);package.put(output,'live-record-snapshot.json',record_raw)
    b.seal(output);package.verify(output);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);args=parser.parse_args()
    result=run(args.output);print(json.dumps(dict(source_files=len(result['source_hashes']),model_cases=len(result['native_model_cases']),device_integrated=False)))
