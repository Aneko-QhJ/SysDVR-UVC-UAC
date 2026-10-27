#!/usr/bin/env python3
"""Build bound sequence candidate; injected SDK, serializers and file claims only."""
import argparse
import json
from pathlib import Path
import subprocess

import build_a23_context65_receiver as b
import analyze_io_usb_host_context65 as sdk
import analyze_a23_context65_entry as waiting
import analyze_io_usb_host_lead32 as legacy_sdk
import collect_a23_context65_execution as collection
import audit_a23_waiting_collection as serializers
import shutil
import a23_execution_context as context
import analyze_io_usb_host_sequence as old_sequence_sdk
import path_span_card_workflow as card
from analyze_io_usb_host_context65_evidence import analyze as transfer_audit


def extra_checks(output,record,commands):
    native={}
    for group,fn,expected in [('driver-models',sdk.analyze,{'final-save-failed','retained-save-failed'}),('loop-models',waiting.analyze,{'signal-before-begin'})]:
        rows={}
        for path in sorted((output/group).iterdir()):
            try:rows[path.name]=dict(valid=True,analysis=fn(path));b.require(path.name not in expected,'incomplete native journal passed')
            except ValueError as error:
                b.require(path.name in expected,'unexpected sequence analyzer error '+path.name+': '+str(error));rows[path.name]=dict(valid=False,error=str(error))
        native[group]=rows
    try:legacy_sdk.analyze(output/'driver-models/iso-first')
    except ValueError as error:old_rejection=str(error)
    else:raise ValueError('old fixed parser accepted sequence candidate')
    try:old_sequence_sdk.analyze(output/'driver-models/iso-first')
    except ValueError:pass
    else:raise ValueError('old49 parser accepted65 candidate')
    frozen=Path(record['build']);source=Path(record['device_binding']['device_source_root'])/'source/uvc'
    headers=serializers.header_closure(source);headers['ep0_lifecycle_capsule.h']=b.sha(b.plain(source/'ep0_lifecycle_capsule.h'))
    includes=output/'serializer-headers';includes.mkdir()
    for n,h in headers.items():
        shutil.copyfile(source/n,includes/n);b.require(b.sha(b.plain(includes/n))==h,'serializer header drift')
    recipe='recipe[32]={'+','.join(map(str,bytes.fromhex(record['recipe_sha256'])))+'}'
    for name,fixture in [('execution','a23_waiting_execution_fixture.c'),('lifecycle','a23_lifecycle_collection_fixture.c')]:
        text=b.plain(frozen/'source/research/usb-ds-iso/tests'/fixture).decode();text=b.device.once(text,'recipe[32]={3}',recipe)
        if name=='execution':
            text=b.device.once(text,'burst[8]={0x41,0x54,1,0,2,0,0,0}',f'burst[8]={{0x41,0x54,{b.device.FIRST},0,2,0,0,0}}')
            text=b.device.once(text,'EP0_T_SEQUENCE,2,1,0,NULL','EP0_T_SEQUENCE,2,'+str(b.device.FIRST)+',0,NULL')
            text=b.device.once(text,'2,seq?0:1,NULL','2,seq?0:'+str(b.device.FIRST)+',NULL')
        path=output/(name+'-model.c');path.write_text(text)
        command=[commands[0][0],'-isysroot',commands[0][2],'-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+str(includes),str(path),'-o',str(output/(name+'-model'))]
        commands.append(command);subprocess.run(command,check=True,capture_output=True,text=True)
    models=output/'models';models.mkdir()
    for mode in ('matching','sequence-mismatch','shape-mismatch','primary-receipt-failure'):
        subprocess.run([str(output/'execution-model'),mode,str(models/mode)],check=True,capture_output=True)
    subprocess.run([str(output/'lifecycle-model'),'13',str(models/'joined.bin')],check=True,capture_output=True)
    base=output/'mock-run';base.mkdir();shutil.copytree(output/'loop-models/normal',base/'host')
    mock={**record,'stage':'consumed','artifact_origin':'injected_model_no_issuer','run':str(base)}
    b.write(base/'record.json',mock);b.write(base/'waiting-authorization.json',b.device.receipt(mock))
    b.write(base/'execution-context.json',context.model(record['receiver_sha256'],Path(record['build'])/'receiver'))
    for mode in ('--claim-process-only','--claim-sdk-only'):
        subprocess.run([str(output/'injected-loop'),mode,str(base),str(frozen)],check=True,capture_output=True)
    cases={};NAME='ep0-life-'+('03'+'00'*15)+'.bin'
    for mode in ('matching','sequence-mismatch','shape-mismatch','primary-receipt-failure'):
        folder=output/('lifecycle-'+mode);folder.mkdir();path=folder/NAME;path.write_bytes(b.plain(models/'joined.bin'))
        cases[mode]=collection.freeze(base/'host',output/('collection-'+mode),base/'record.json',base,[path],models/(mode+'.execution.bin'),models/(mode+'.primary.bin'))
    snapshot=b.ROOT/'private/card-cycles/20261017-133944-lead32-repeat1-live-read/card'
    for prefix,life in [('698c','1ff8'),('383d','4d7b')]:
        ex=next(snapshot.glob('ep0-'+prefix+'*.execution.bin'));lc=next(snapshot.glob('ep0-life-'+life+'*.bin'))
        cases['old-success-'+prefix]=collection.freeze(base/'host',output/('collection-old-success-'+prefix),base/'record.json',base,[lc],ex,ex.with_name(ex.name.replace('.execution.bin','.capture.bin')))
    b.require(cases['matching']['analysis']['supplied_chain_complete'],'new sequence supplied model incomplete')
    b.require(not any(v['analysis']['supplied_chain_complete'] for k,v in cases.items() if k!='matching'),'sequence mismatch or known old record passed')
    return dict(native=native,old_parser_rejection=old_rejection,collection_cases=cases,first_sequence=b.device.FIRST,sequence_reserved=False,issuer_ready=False)


def context_checks_run(output,record,commands):
    build=Path(record['build']);host=build/'source/research/usb-ds-iso/host';test=build/'source/research/usb-ds-iso/tests/a23_execution_context_fixture.m'
    command=[commands[0][0],'-isysroot',commands[0][2],'-std=c11','-fobjc-arc','-Wall','-Wextra','-Werror',
        '-fsanitize=address,undefined','-I'+str(host),'-framework','Foundation','-framework','IOUSBHost',str(host/'a23_execution_context.m'),str(test),'-o',str(output/'context-model')]
    commands.append(command)
    with (output/'context-build.log').open('xb') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    run=subprocess.run([str(output/'context-model')],capture_output=True,check=True);card.pkg.put(output,'context-model.log',run.stdout+run.stderr)
    model_log=run.stdout.decode()
    native=json.loads(subprocess.check_output([str(build/'receiver'),'--execution-context']))
    b.require(native['receiver_sha256']==record['receiver_sha256'],'context self code hash differs')
    b.require(native['sandbox_query_available'] is True,'context query availability is not a boolean')
    b.write(output/'context-self-observation.json',native)
    faults={};work=output/'context-claim-models';work.mkdir()
    changes={'missing':None,'sandbox-active':{'sandbox_query_result':1},'sandbox-unknown':{'sandbox_query_result':-1},
        'sandbox-boolean':{'sandbox_query_result':False},'wrong-os':{'os_build':'other'},'wrong-framework':{'framework_uuid':'other'},
        'wrong-receiver':{'receiver_sha256':'00'*32},'extra-field':{'extra':1}}
    for name,change in changes.items():
        folder=work/name;folder.mkdir();b.write(folder/'waiting-authorization.json',b.device.receipt(record))
        if change is not None:
            value=context.model(record['receiver_sha256'],build/'receiver');value.update(change);b.write(folder/'execution-context.json',value)
        command=[str(output/'injected-loop'),'--claim-process-only',str(folder),str(build)]
        run=subprocess.run(command,capture_output=True)
        b.require(run.returncode==2 and not (folder/'WAIT_PROCESS_CLAIMED').exists(),'context fault reached claim')
        faults[name]=dict(returncode=run.returncode,claim_created=False)
    folder=work/'changed-after-claim';folder.mkdir();b.write(folder/'waiting-authorization.json',b.device.receipt(record))
    value=context.model(record['receiver_sha256'],build/'receiver');b.write(folder/'execution-context.json',value)
    command=[str(output/'injected-loop'),'--claim-process-only',str(folder),str(build)];subprocess.run(command,check=True,capture_output=True)
    value['pid']+=1;(folder/'execution-context.json').write_bytes(b.canonical(value));command[1]='--claim-sdk-only'
    run=subprocess.run(command,capture_output=True);b.require(run.returncode==2 and not (folder/'WAIT_RECEIVER_CLAIMED').exists(),'changed context reached SDK permit')
    faults['changed-after-claim']=dict(returncode=run.returncode,sdk_claim_created=False)
    main=b.plain(build/'generated/a23_waiting_receiver_main.m').decode()
    markers=['A23ReadExecutionContext(binary);','A23SaveBurstEntryResult(run,@"execution-context.json"','A23ValidateExecutionContext(context,checked','A23ClaimWaitingProcess(run,checked)','a23_wait_native_ops(']
    positions=[main.index(x) for x in markers];b.require(positions==sorted(positions),'context is not before claim and IOKit')
    return dict(native_admission_model_log=model_log,claim_faults=faults,source_order_verified=True,
        self_observation=native,self_query_proves_usb_permission=False,usb_requests=0,sd_accesses=0)


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
    for kind in ('matching','old-schema','old-plan','wrong-sequence','wrong-lead','wrong-reserve','integer-boolean','wrong-recipe','duplicate-key'):
        folder=models/kind;folder.mkdir();receipt=b.device.receipt(record)
        if kind=='old-schema':receipt['schema']='A23-waiting-burst-consumed-receipt-7'
        if kind=='old-plan':receipt['plan']=b.device.parent.WAIT_PLAN
        if kind=='wrong-sequence':receipt['plan']['sdk_plan']['scenario']['first_sequence']=1
        if kind=='wrong-lead':receipt['plan']['sdk_plan']['first_frame_lead']=64
        if kind=='wrong-reserve':receipt['plan']['sdk_plan']['runtime_budget']['reserve_ns']=16000000
        if kind=='integer-boolean':receipt['attempt_consumed']=1
        if kind=='wrong-recipe':receipt['recipe_sha256']='00'*32
        raw=b.canonical(receipt)
        if kind=='duplicate-key':raw=raw.replace(b'{',b'{"attempt_consumed":true,',1)
        card.pkg.put(folder,'waiting-authorization.json',raw)
        b.write(folder/'execution-context.json',context.model(record['receiver_sha256'],build/'receiver'))
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
    extra=extra_checks(output,record,commands)
    context_checks=context_checks_run(output,record,commands)
    b.verify_build(record)
    protected=b.load(b.ROOT/'private/analysis/A23-path-span-readiness-review-20261016/protected-inputs.json')
    for group,base in [('production',b.REPO),('tickets',b.ROOT/'private/analysis'),('offline_records_sha256',b.ROOT/'private/analysis')]:
        for n,h in protected[group].items():b.require(b.sha(b.plain(base/n))==h,'protected input drift')
    live={}
    for name in ('A23-quiet-once-20261016-interface2.json','A23-lifecycle-once-20261016-interface2.json','A23-path-span-once-20261016-interface2.json'):
        raw=b.plain(b.ROOT/'private/analysis'/name);value=json.loads(raw)
        b.require(value['stage']=='failed_no_retry' and value['remaining']==0,'live zero record changed')
        card.pkg.put(output,'records/'+name,raw);live[name]=b.sha(raw)
    result=dict(schema='A23-context65-receiver-review-1',source_hashes=b.source_hashes(),offline_record=record,
                device_binding=record['device_binding'],native_cases=cases,claim_cases=claims,commands=commands,
                prior_sources_unchanged=272,policy_boundary_assertions=11,live_records_sha256=live,
                remaining=0,attempt_issued=False,receiver_acquire_invoked=False,real_sdk_objects=0,
                native_iokit_calls=0,usb_requests=0,sd_accesses=0,execution_context_checks=context_checks,device_rebuilt=False,firmware_packaged=False,extra=extra,
                collection_analyzer_ready=False,issuer_ready=False,hardware_verified=False,root_cause_confirmed=False)
    b.write(output/'audit.json',result);b.write(output/'protected-inputs.json',protected);b.seal(output)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();r=run(a.output)
    print(json.dumps(dict(sources=len(r['source_hashes']),loop_cases=len(r['native_cases']['loop']),driver_cases=len(r['native_cases']['driver']),claims=len(r['claim_cases']),remaining=0)))
