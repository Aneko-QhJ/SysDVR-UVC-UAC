#!/usr/bin/env python3
"""Build a distinct receiver and exercise static lifecycle collections; no acquire."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import zlib

import build_a23_lifecycle_receiver as builder
import collect_a23_lifecycle_execution as collection
import audit_a23_waiting_collection as serializers
import analyze_a23_waiting_entry as waiting

ROOT=builder.ROOT;REPO=builder.REPO
NONCE='03'+'00'*15
NAME='ep0-life-'+NONCE+'.bin'


def run(output,repo=REPO,device_root=builder.DEVICE/'candidate'):
    output=Path(output);repo=Path(repo)
    builder.require(output.is_absolute() and output==output.resolve() and not output.exists(),'new canonical audit required')
    output.mkdir(parents=True,mode=0o700)
    record=builder.build(output/'receiver-build',repo,device_root);builder.write(output/'offline-record.json',record)
    build=Path(record['build']);commands=[]
    command=builder.compile_command(build,output/'injected-loop',fixture=True);commands.append(command)
    with (output/'native-build.log').open('x') as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
    with (output/'native.log').open('x') as log:subprocess.run([str(output/'injected-loop'),str(output/'native-fixtures')],check=True,stdout=log,stderr=subprocess.STDOUT)
    loops={}
    for path in sorted((output/'native-fixtures').iterdir()):
        try:loops[path.name]=waiting.analyze(path)
        except ValueError as error:
            builder.require(path.name=='signal-before-begin','unexpected loop error');loops[path.name]=dict(prefix_preserved=True,error=str(error))
    source=Path(device_root)/'source/uvc';headers=serializers.header_closure(source)
    headers['ep0_lifecycle_capsule.h']=builder.sha(builder.plain(source/'ep0_lifecycle_capsule.h'))
    includes=output/'serializer-headers';includes.mkdir()
    for n,h in headers.items():
        shutil.copyfile(source/n,includes/n);builder.require(builder.sha(builder.plain(includes/n))==h,'header changed')
    models=output/'models';models.mkdir()
    recipe='recipe[32]={'+','.join(map(str,bytes.fromhex(record['recipe_sha256'])))+'}'
    for name,fixture in [('execution','a23_waiting_execution_fixture.c'),('lifecycle','a23_lifecycle_collection_fixture.c')]:
        text=builder.plain(build/'source/research/usb-ds-iso/tests'/fixture).decode()
        target=output/(name+'-model.c');target.write_text(builder.device.once(text,'recipe[32]={3}',recipe))
        command=[commands[0][0],'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+str(includes),str(target),'-o',str(output/(name+'-model'))]
        commands.append(command);subprocess.run(command,check=True,capture_output=True,text=True)
    for mode in serializers.MODES:subprocess.run([str(output/'execution-model'),mode,str(models/mode)],check=True,capture_output=True)
    for name,count in [('joined',13),('prepared',1),('quiet',4),('before-context',11)]:
        subprocess.run([str(output/'lifecycle-model'),str(count),str(models/(name+'.bin'))],check=True,capture_output=True)
    runs=output/'mock-runs';runs.mkdir();base=runs/'matching';base.mkdir();shutil.copytree(output/'native-fixtures/normal',base/'host')
    mock={**record,'stage':'consumed','artifact_origin':'injected_consumed_model','run':str(base)}
    builder.write(base/'record.json',mock);builder.write(base/'waiting-authorization.json',builder.device.receipt(mock))
    for mode in ('--claim-process-only','--claim-sdk-only'):
        subprocess.run([str(output/'injected-loop'),mode,str(base),str(build)],check=True,capture_output=True)
    (runs/'MOCK_ONLY.txt').write_text('Injected consumed records, receipts and bytes only. No issuer or receiver acquisition called.\n')
    collections=output/'collections';collections.mkdir();supplied=output/'supplied';supplied.mkdir();cases={}
    joined=builder.plain(models/'joined.bin')
    def collect(name,raws=None,execution='matching',primary='matching',run=base):
        folder=supplied/name;folder.mkdir();paths=[]
        for filename,raw in (raws if raws is not None else {NAME:joined}).items():
            path=folder/filename;builder.old.durable_write(path,raw);paths.append(path)
        cases[name]=collection.freeze(run/'host',collections/name,run/'record.json',run,paths,
            models/(execution+'.execution.bin') if execution is not None else None,
            models/(primary+'.primary.bin') if primary is not None else None,repo)
    collect('matching');collect('missing-execution',execution=None);collect('missing-primary',primary=None)
    collect('missing-both-results',execution=None,primary=None);collect('missing-lifecycle',{})
    for name in ('prepared','quiet','before-context'):collect(name,{NAME:builder.plain(models/(name+'.bin'))})
    collect('short-zero-tail',{NAME:joined[:128+12*96]+bytes(17)})
    collect('truncated-header',{NAME:joined[:80]});collect('partial-after-context',{NAME:joined[:128+12*96+17]})
    corrupt=bytearray(joined);corrupt[128+12*96+25]^=1;collect('bad-tail-crc',{NAME:bytes(corrupt)})
    corrupt=bytearray(joined);corrupt[124]^=1;collect('bad-header-crc',{NAME:bytes(corrupt)})
    def header_change(offset,value):
        raw=bytearray(joined);raw[offset:offset+len(value)]=value;struct.pack_into('<I',raw,124,zlib.crc32(raw[:124]));return bytes(raw)
    collect('wrong-recipe',{NAME:header_change(56,bytes(32))})
    collect('wrong-writer',{NAME:header_change(16,struct.pack('<Q',99))})
    collect('wrong-frequency',{NAME:header_change(24,struct.pack('<Q',1001))})
    collect('different-nonce',{NAME:header_change(40,bytes([4])+bytes(15))})
    raw=bytearray(joined);off=128+11*96;raw[off+32]=9;struct.pack_into('<I',raw,off+92,zlib.crc32(raw[off:off+92]));collect('wrong-context',{NAME:bytes(raw)})
    raw2=header_change(40,bytes([4])+bytes(15))
    collect('multiple-lifecycle',{NAME:joined,'ep0-life-'+('04'+'00'*15)+'.bin':raw2})
    collect('old-quiet-lifecycle',{NAME:header_change(56,bytes.fromhex(record['device_binding']['parent_input_digest']))})
    for mode in ('sequence-mismatch','shape-mismatch','primary-receipt-failure'):collect(mode,execution=mode,primary=mode)
    path=models/'partial.execution.bin';builder.old.durable_write(path,builder.plain(models/'matching.execution.bin')[:100]);collect('partial-execution',execution='partial')
    collect('primary-mismatch',primary='shape-mismatch')
    for fault in ('old-receipt','wrong-runtime','wrong-npdm','missing-process','sdk-mismatch','duplicate-receipt'):
        run=runs/fault;shutil.copytree(base,run);path=run/'waiting-authorization.json';receipt=builder.load(path)
        if fault=='old-receipt':receipt['schema']='A23-waiting-burst-consumed-receipt-3'
        if fault=='wrong-runtime':receipt['recipe_sha256']=record['device_binding']['parent_input_digest']
        if fault=='wrong-npdm':receipt['device_npdm_sha256']='00'*32
        if fault in ('old-receipt','wrong-runtime','wrong-npdm'):path.write_bytes(builder.canonical(receipt))
        if fault=='missing-process':(run/'WAIT_PROCESS_CLAIMED').unlink()
        if fault=='sdk-mismatch':
            path=run/'WAIT_RECEIVER_CLAIMED';value=builder.load(path);value['interface_id']=999;path.write_bytes(builder.canonical(value))
        if fault=='duplicate-receipt':path.write_bytes(path.read_bytes().replace(b'{',b'{"attempt_consumed":true,',1))
        collect(fault,run=run)
    builder.verify_build(record,repo)
    parent=builder.load(builder.PARENT/'audit.json');protected=builder.load(builder.PARENT/'protected-inputs.json')
    for n,h in protected['production'].items():builder.require(builder.sha(builder.plain(repo/n))==h,'production drift')
    for group in ('tickets','offline_records_sha256'):
        for n,h in protected[group].items():builder.require(builder.sha(builder.plain(builder.PARENT.parent/n))==h,'ticket drift')
    live=builder.PARENT.parent/'A23-quiet-once-20261016-interface2.json'
    builder.require(builder.plain(live)==builder.plain(builder.PARENT/'live-record-snapshot.json'),'live record drift')
    result=dict(schema='A23-lifecycle-receiver-review-1',source_hashes=builder.source_hashes(repo),offline_record=record,
        device_binding=record['device_binding'],native_loop_cases=loops,native_loop_case_count=len(loops),
        serializer_headers_sha256=headers,compiler_commands=commands,collection_cases=cases,collection_count=len(cases),
        prior_sources_unchanged=len(parent['source_hashes']),mock_consumed_records_only=True,receiver_acquire_invoked=False,
        remaining=0,attempt_issued=False,device_rebuilt=False,device_executed=False,firmware_packaged=False,deployed=False,
        native_iokit_calls=0,real_sdk_objects=0,usb_requests=0,sd_accesses=0,hardware_verified=False,root_cause_confirmed=False)
    builder.write(output/'audit.json',result);builder.write(output/'protected-inputs.json',protected)
    builder.old.durable_write(output/'live-record-snapshot.json',builder.plain(live));builder.seal(output);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();result=run(a.output)
    print(json.dumps(dict(source_files=len(result['source_hashes']),collections=result['collection_count'],loops=result['native_loop_case_count'])))
