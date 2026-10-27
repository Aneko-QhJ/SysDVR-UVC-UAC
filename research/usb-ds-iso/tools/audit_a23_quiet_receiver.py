#!/usr/bin/env python3
"""Build and test bound identities using new mock records and file-only claims."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

import build_a23_quiet_receiver as builder
import collect_a23_quiet_execution as collection
import audit_a23_waiting_collection as prior_collection
import analyze_a23_waiting_entry as waiting
from workflows.artifacts import verify

ROOT=builder.ROOT;REPO=builder.REPO


def run(output,repo=REPO,device_root=builder.DEVICE/'window-30s'):
    output=Path(output);builder.require(output.is_absolute() and output==output.resolve() and not output.exists(),'new canonical audit required')
    output.mkdir(parents=True);record=builder.build(output/'receiver-build',repo,device_root);builder.write(output/'offline-record.json',record)
    build=Path(record['build']);command=builder.compile_command(build,output/'injected-loop',fixture=True)
    builder.write(output/'native-command.json',command)
    with (output/'native-build.log').open('x') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    with (output/'native.log').open('x') as log:subprocess.run([str(output/'injected-loop'),str(output/'native-fixtures')],check=True,stdout=log,stderr=subprocess.STDOUT)
    loops={}
    for p in sorted((output/'native-fixtures').iterdir()):
        try:loops[p.name]=waiting.analyze(p)
        except ValueError as e:
            builder.require(p.name=='signal-before-begin','unexpected injected loop failure');loops[p.name]=dict(prefix_preserved=True,error=str(e))
    source_root=builder.DEVICE/'window-30s/source/uvc';headers=prior_collection.header_closure(source_root)
    for n,h in headers.items():
        target=output/'serializer-headers'/n;target.parent.mkdir(exist_ok=True);shutil.copyfile(source_root/n,target)
        builder.require(builder.sha(builder.plain(target))==h,'serializer header changed')
    original=builder.plain(build/'source/research/usb-ds-iso/tests/a23_waiting_execution_fixture.c').decode()
    src=output/'bound-serializer-model.c';src.write_text(builder.device.once(original,'recipe[32]={3}',
        'recipe[32]={'+','.join(str(n) for n in bytes.fromhex(record['recipe_sha256']))+'}'))
    binary=output/'bound-serializer-model';native_command=[command[0],'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I'+str(output/'serializer-headers'),str(src),'-o',str(binary)]
    builder.write(output/'serializer-command.json',native_command)
    with (output/'serializer-build.log').open('x') as log:subprocess.run(native_command,check=True,stdout=log,stderr=subprocess.STDOUT)
    models=output/'models';models.mkdir();model_results={}
    for mode in prior_collection.MODES:
        p=subprocess.run([str(binary),mode,str(models/mode)],capture_output=True,text=True,check=True)
        model_results[mode]=json.loads(p.stdout)
    builder.write(models/'results.json',model_results)
    runs=output/'mock-runs';runs.mkdir();base=runs/'matching';base.mkdir()
    shutil.copytree(output/'native-fixtures/normal',base/'host')
    mock={**record,'stage':'consumed','artifact_origin':'injected_consumed_model','run':str(base)}
    builder.write(base/'record.json',mock);builder.write(base/'waiting-authorization.json',builder.device.receipt(mock))
    for mode in ('--claim-process-only','--claim-sdk-only'):
        subprocess.run([str(output/'injected-loop'),mode,str(base),str(build)],check=True,capture_output=True)
    (runs/'MOCK_ONLY.txt').write_text('Consumed stages and receipts are injected models. No issuer or receiver acquire was called.\n')
    cases={};dest=output/'collections';dest.mkdir()
    def collect(name,run=base,mode='matching',primary=True):
        cases[name]=collection.freeze(run/'host',models/(mode+'.execution.bin'),dest/name,run/'record.json',run,
            models/(mode+'.primary.bin') if primary else None,repo)
    for mode in prior_collection.MODES:collect(mode,mode=mode)
    collect('missing-primary',primary=False)
    receipt_faults=('wrong-device-npdm','wrong-device-config','wrong-main-stack','boolean-main-stack','v2-receipt')
    faults=('parent-as-runtime','wrong-device-elf','wrong-binding','old-receipt','partial-receipt',
        'duplicate-receipt','missing-process','process-mismatch','sdk-identity','missing-sdk-claim',
        *receipt_faults,'process-npdm','sdk-npdm','sdk-config','sdk-stack')
    for name in faults:
        run=runs/name;shutil.copytree(base,run)
        p=run/'waiting-authorization.json';receipt=builder.load(p)
        if name=='parent-as-runtime':receipt['recipe_sha256']=record['device_binding']['parent_input_digest']
        elif name=='wrong-device-elf':receipt['device_elf_sha256']='00'*32
        elif name=='wrong-binding':receipt['device_binding_sha256']='00'*32
        elif name=='old-receipt':receipt['schema']='A23-waiting-burst-consumed-receipt-1'
        elif name=='wrong-device-npdm':receipt['device_npdm_sha256']='00'*32
        elif name=='wrong-device-config':receipt['device_config_sha256']='00'*32
        elif name=='wrong-main-stack':receipt['main_thread_stack_request_bytes']=16384
        elif name=='boolean-main-stack':receipt['main_thread_stack_request_bytes']=True
        elif name=='v2-receipt':receipt['schema']='A23-waiting-burst-consumed-receipt-2'
        elif name=='partial-receipt':p.write_bytes(p.read_bytes()[:100])
        elif name=='duplicate-receipt':p.write_bytes(p.read_bytes().replace(b'{',b'{"recipe_sha256":"'+record['recipe_sha256'].encode()+b'",',1))
        elif name=='missing-process':(run/'WAIT_PROCESS_CLAIMED').unlink()
        elif name=='missing-sdk-claim':(run/'WAIT_RECEIVER_CLAIMED').unlink()
        elif name=='process-mismatch':
            value=builder.load(run/'WAIT_PROCESS_CLAIMED');value['checked']['parent_input_digest']='00'*32
            (run/'WAIT_PROCESS_CLAIMED').write_bytes(builder.canonical(value))
        elif name=='sdk-identity':
            value=builder.load(run/'WAIT_RECEIVER_CLAIMED');value['interface_id']=999
            (run/'WAIT_RECEIVER_CLAIMED').write_bytes(builder.canonical(value))
        elif name=='process-npdm':
            value=builder.load(run/'WAIT_PROCESS_CLAIMED');value['checked']['device_npdm_sha256']='00'*32
            (run/'WAIT_PROCESS_CLAIMED').write_bytes(builder.canonical(value))
        elif name in ('sdk-npdm','sdk-config','sdk-stack'):
            key={'sdk-npdm':'device_npdm_sha256','sdk-config':'device_config_sha256','sdk-stack':'main_thread_stack_request_bytes'}[name]
            value=builder.load(run/'WAIT_RECEIVER_CLAIMED');value[key]=16384 if name=='sdk-stack' else '00'*32
            (run/'WAIT_RECEIVER_CLAIMED').write_bytes(builder.canonical(value))
        if name in faults[:4] or name in receipt_faults:p.write_bytes(builder.canonical(receipt))
        collect(name,run)
    builder.verify_build(record,repo);previous=builder.load(builder.PARENT/'audit.json')
    for n,h in previous['production_sources_sha256'].items():builder.require(builder.sha(builder.plain(Path(repo)/n))==h,'production drift')
    for n,h in previous['tickets_sha256'].items():builder.require(builder.sha(builder.plain(builder.PARENT.parent/n))==h,'ticket drift')
    for p in (builder.PARENT,builder.PARENT.parent/'A23-quiet-window-validation-20261015',builder.DEVICE):verify(p)
    result=dict(schema='A23-quiet-receiver-review-1',offline_record=record,source_hashes=builder.source_hashes(repo),
        serializer_headers_sha256=headers,device_binding=record['device_binding'],native_loop_cases=loops,native_loop_case_count=len(loops),
        serializer_models=model_results,serializer_execution_count=len(model_results),collection_cases=cases,collection_count=len(cases),
        production_sources_sha256=previous['production_sources_sha256'],tickets_sha256=previous['tickets_sha256'],
        prior_seals=[verify(p) for p in (builder.PARENT,builder.PARENT.parent/'A23-quiet-window-validation-20261015',builder.DEVICE)],
        native_sanitizers='address,undefined',mock_consumed_records_only=True,receiver_capture_invoked=False,attempt_issued=False,remaining=0,
        native_iokit_calls=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,device_executed=False,hardware_verified=False,root_cause_confirmed=False)
    builder.write(output/'audit.json',result);builder.seal(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=run(a.output)
    print(json.dumps({k:r[k] for k in ('schema','native_loop_case_count','serializer_execution_count','collection_count','remaining')},indent=2))
