#!/usr/bin/env python3
"""Build host lead32 and run injected files/loops only; no acquisition or issuer."""
import argparse
import json
from pathlib import Path
import subprocess

import build_a23_lead32_receiver as b
import path_span_card_workflow as card
from analyze_io_usb_host_evidence import analyze as transfer_audit


def run(output):
    output=Path(output);b.require(output.is_absolute() and output==output.resolve() and not output.exists(),'new audit required')
    output.mkdir(mode=0o700)
    record=b.build(output/'receiver-build');b.write(output/'offline-record.json',record)
    build=Path(record['build']);commands=[]
    def execute(command,log):
        commands.append(command)
        with (output/log).open('xb') as handle:subprocess.run(command,stdout=handle,stderr=subprocess.STDOUT,check=True)
    cmd=b.compile_command(build,output/'injected-loop',fixture=True)
    execute(cmd,'loop-build.log');execute([str(output/'injected-loop'),str(output/'loop-models')],'loop.log')
    cmd=b.compile_command(build,output/'injected-driver',fixture=True)
    cmd[cmd.index(str(build/'generated/lead32_loop_fixture.m'))]=str(build/'generated/lead32_driver_fixture.m')
    execute(cmd,'driver-build.log');execute([str(output/'injected-driver'),str(output/'driver-models')],'driver.log')
    cmd=[commands[0][0],'-isysroot',commands[0][2],'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
         '-I'+str(build/'source/research/usb-ds-iso/host'),
         str(build/'source/research/usb-ds-iso/tests/a23_lead32_policy_fixture.c'),'-o',str(output/'policy-model')]
    execute(cmd,'policy-build.log');execute([str(output/'policy-model')],'policy.log')
    cases={}
    for kind in ('loop','driver'):
        group={}
        for folder in sorted((output/(kind+'-models')).iterdir()):
            result=b.load(folder/('waiting-entry-result.json' if kind=='loop' else 'result.json'))
            rows=[]
            if (folder/'session.jsonl').exists():
                rows=[json.loads(s) for s in (folder/'session.jsonl').read_bytes().splitlines()]
                b.require(rows[0]['details']['plan']==b.WAIT_PLAN['sdk_plan'],'injected SDK plan mismatch')
                for row in rows:
                    if row['event']=='adapter' and row['details']['event']=='frame_sample':
                        d=row['details']['details'];b.require(d['first_frame']==d['sample']['current_frame']+32,'wrong fixture frame')
            native=None
            if (folder/'transfer').exists():
                try:native=transfer_audit(folder/'transfer',burst=True)
                except ValueError as error:
                    native=dict(evidence_integrity_verified=False,usb_strict_pass=False,
                                partial_or_failed_bytes_preserved=True,error=str(error))
            group[folder.name]=dict(result=result,session_rows=len(rows),transfer=native)
        cases[kind]=group
    claims={};models=output/'claim-models';models.mkdir()
    for kind in ('matching','old-schema','old-plan','wrong-lead','wrong-reserve','integer-boolean','wrong-recipe','duplicate-key'):
        folder=models/kind;folder.mkdir();receipt=b.device.receipt(record)
        if kind=='old-schema':receipt['schema']='A23-waiting-burst-consumed-receipt-5'
        if kind=='old-plan':receipt['plan']=b.device.PREVIOUS_PLAN
        if kind=='wrong-lead':receipt['plan']['sdk_plan']['first_frame_lead']=64
        if kind=='wrong-reserve':receipt['plan']['sdk_plan']['runtime_budget']['reserve_ns']=16000000
        if kind=='integer-boolean':receipt['attempt_consumed']=1
        if kind=='wrong-recipe':receipt['recipe_sha256']='00'*32
        raw=b.canonical(receipt)
        if kind=='duplicate-key':raw=raw.replace(b'{',b'{"attempt_consumed":true,',1)
        card.pkg.put(folder,'waiting-authorization.json',raw)
        cmd=[str(output/'injected-loop'),'--claim-process-only',str(folder),str(build)]
        process=subprocess.run(cmd,capture_output=True,text=True);b.require(process.returncode==(0 if kind=='matching' else 2),'unexpected process claim result')
        claims[kind]=dict(process_returncode=process.returncode)
        if kind=='matching':
            repeat=subprocess.run(cmd,capture_output=True,text=True);b.require(repeat.returncode==2,'process reuse accepted')
            cmd[1]='--claim-sdk-only';sdk=subprocess.run(cmd,capture_output=True,text=True)
            b.require(sdk.returncode==0,'matching bound permit failed')
            again=subprocess.run(cmd,capture_output=True,text=True);b.require(again.returncode==2,'SDK claim reuse accepted')
            claims[kind].update(sdk_returncode=sdk.returncode,repeat_process_returncode=repeat.returncode,repeat_sdk_returncode=again.returncode)
        else:
            b.require(not (folder/'WAIT_PROCESS_CLAIMED').exists(),'rejected receipt created claim')
    b.verify_build(record)
    protected=b.load(b.ROOT/'private/analysis/A23-path-span-readiness-review-20261016/protected-inputs.json')
    for group,base in [('production',b.REPO),('tickets',b.ROOT/'private/analysis'),('offline_records_sha256',b.ROOT/'private/analysis')]:
        for n,h in protected[group].items():b.require(b.sha(b.plain(base/n))==h,'protected input drift')
    live={}
    for name in ('A23-quiet-once-20261016-interface2.json','A23-lifecycle-once-20261016-interface2.json','A23-path-span-once-20261016-interface2.json'):
        raw=b.plain(b.ROOT/'private/analysis'/name);value=json.loads(raw)
        b.require(value['stage']=='failed_no_retry' and value['remaining']==0,'live zero record changed')
        card.pkg.put(output,'records/'+name,raw);live[name]=b.sha(raw)
    result=dict(schema='A23-lead32-receiver-review-1',source_hashes=b.source_hashes(),offline_record=record,
                device_binding=record['device_binding'],native_cases=cases,claim_cases=claims,commands=commands,
                prior_sources_unchanged=235,policy_boundary_assertions=11,live_records_sha256=live,
                remaining=0,attempt_issued=False,receiver_acquire_invoked=False,real_sdk_objects=0,
                native_iokit_calls=0,usb_requests=0,sd_accesses=0,device_rebuilt=False,firmware_packaged=False,
                collection_analyzer_ready=False,issuer_ready=False,hardware_verified=False,root_cause_confirmed=False)
    b.write(output/'audit.json',result);b.write(output/'protected-inputs.json',protected);b.seal(output)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();r=run(a.output)
    print(json.dumps(dict(sources=len(r['source_hashes']),loop_cases=len(r['native_cases']['loop']),driver_cases=len(r['native_cases']['driver']),claims=len(r['claim_cases']),remaining=0)))
