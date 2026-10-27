"""Offline SDK driver review. Fake operations only; never opens a device."""
import argparse,difflib,json,shutil,struct,subprocess
from pathlib import Path
import audit_a23_paired_sdk as prior
from a23_two_epoch_sdk_source import render,render_analyzer
from analyze_a23_two_epoch_sdk import analyze,sha
w=prior.w
PARENT=w.A/'A23-paired-sdk-closeout-20261018'
PARENT_SUM='b2f33bff678b558ee034acd691bdf637dbe54e36a9c94861f5ace8aed075c9c4'
NEW=('host/a23_two_epoch_sdk_driver.h','host/a23_two_epoch_sdk_driver.m','tests/a23_two_epoch_sdk_fixture.inc',
     'tools/a23_two_epoch_sdk_source.py','tools/analyze_a23_two_epoch_sdk.py','tools/audit_a23_two_epoch_sdk.py','tests/test_a23_two_epoch_sdk.py')
NATIVE=prior.NATIVE+('a23_two_epoch_sdk_driver.m',)

def sources():
    w.card.seal_verify(PARENT);w.require(w.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent closeout differs')
    current=prior.sources();w.require(len(current)==329 and current==w.load(PARENT/'closeout.json')['source_hashes'],'prior329 drift')
    for name in NEW:
        key='research/usb-ds-iso/'+name;w.require(key not in current,'new overlap');current[key]=sha(w.plain(w.ROOT/name))
    return dict(sorted(current.items()))

def generated_fixture(source):
    root=Path(source)/'research/usb-ds-iso';parts=[]
    for name in ('a23_two_epoch_receiver_test.m','a23_paired_sdk_fixture.inc'):
        text=(root/'tests'/name).read_text();w.require(text.count('\nint main(')==1,'fixture entry ambiguous');parts.append(text.split('\nint main(')[0])
    parts.append((root/'tests/a23_two_epoch_sdk_fixture.inc').read_text());return '\n'.join(parts)

def compile_command(source,binary):
    root=Path(source)/'research/usb-ds-iso'
    return ['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-g',
        '-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',*(str(root/'host'/n) for n in NATIVE),
        str(root/'tests/generated_sdk_driver.m'),'-o',str(binary)]

def derivations(source):
    root=Path(source)/'research/usb-ds-iso';out={}
    for old,new,fn in (('host/a23_two_epoch_receiver.m','host/a23_two_epoch_sdk_driver.m',render),
                       ('tools/analyze_a23_two_epoch.py','tools/analyze_a23_two_epoch_sdk.py',render_analyzer)):
        a=(root/old).read_text();b=(root/new).read_text();w.require(fn(a)==b,'unreviewed derivative: '+new)
        out[new]=''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile=old,tofile=new))
    return out

def write_json(path,value):path.write_text(json.dumps(value,sort_keys=True,separators=(',',':')))

def manifest(folder,names):
    sums=''.join(sha((folder/n).read_bytes())+'  '+n+'\n' for n in sorted(names)).encode()
    (folder/'SHA256SUMS').write_bytes(sums);(folder/'COMMITTED').write_text(sha(sums)+'\n')

def negative_cases(normal,root):
    root.mkdir();out={}
    cases=('mock-status','mock-frame','mock-budget','mixed-origin','zero-frame-time','short-quiet','poisoned-lease',
        'extra-status','boolean-lease-count','callback-count','hardware-claim','offline-result','stale-receipt',
        'missing-receipt','snapshot-differs','receipt-binding','raw-corrupt','same-urb','duplicate-json','journal-partial')
    for case in cases:
        folder=root/case;shutil.copytree(normal,folder);epoch=folder/'epoch-1';result=json.loads((folder/'result.json').read_text())
        m=json.loads((epoch/'metadata.json').read_text());rows=[json.loads(r) for r in (folder/'session.jsonl').read_text().splitlines()]
        receipt=folder/'sdk-receipt';r=json.loads((receipt/'receipt.json').read_text());status=json.loads((folder/'receipt-status.json').read_text())
        if case=='mock-status':m['before_observation']['source']='mock_control_reply'
        elif case=='mock-frame':m['sample']['source']='mock_frame_number'
        elif case=='mock-budget':m['budget']['source']='offline_runtime_budget'
        elif case=='mixed-origin':m['after_observation'].pop('injected_fixture')
        elif case=='zero-frame-time':m['sample']['frame_time']=0
        elif case=='short-quiet':
            result['quiet_start_ticks']=result['quiet_end_ticks']
            rows[-1]['details']['quiet_start_ticks']=result['quiet_end_ticks']
        elif case=='poisoned-lease':result['lease']['poisoned']=True
        elif case=='extra-status':result['lease']['status_reads']=5
        elif case=='boolean-lease-count':result['lease']['aborts']=False
        elif case=='callback-count':result['lease']['iso_callbacks']=[2,1]
        elif case=='hardware-claim':result['hardware_verified']=True
        elif case=='offline-result':result['execution_mode']='offline_simulation'
        elif case=='stale-receipt':status['stale']=True
        elif case=='receipt-binding':r['binding']['first_sequence']=97
        elif case=='raw-corrupt':
            raw=bytearray((epoch/'raw.bin').read_bytes());raw[120*192+6]^=1;(epoch/'raw.bin').write_bytes(raw)
        elif case=='same-urb':
            raw=bytearray((epoch/'after.bin').read_bytes());struct.pack_into('<II',raw,20,501,501);(epoch/'after.bin').write_bytes(raw)
        write_json(epoch/'metadata.json',m);manifest(epoch,('after.bin','before.bin','metadata.json','raw.bin','transactions.bin'))
        for row in rows:
            if row['details'].get('epoch')!=1:continue
            if row['event']=='saved':row['details']['metadata_sha256']=sha((epoch/'metadata.json').read_bytes())
            if row['event']=='iso_intent':row['details']['sample']=m['sample']
            if row['event']=='iso_return':row['details']['budget']=m['budget']
        write_json(folder/'result.json',result);write_json(folder/'receipt-status.json',status)
        write_json(receipt/'snapshot.json',result);r['snapshot']=result;r['snapshot_sha256']=sha((receipt/'snapshot.json').read_bytes())
        if case=='snapshot-differs':r['snapshot']['first_sequence']=97
        write_json(receipt/'receipt.json',r);manifest(receipt,('receipt.json','snapshot.json'))
        if case=='missing-receipt':(receipt/'COMMITTED').unlink()
        journal=''.join(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n' for row in rows)
        (folder/'session.jsonl').write_text(journal[:-1] if case=='journal-partial' else journal)
        if case=='duplicate-json':
            raw=(folder/'result.json').read_text();(folder/'result.json').write_text('{"complete":true,'+raw[1:])
        try:analyze(folder)
        except (ValueError,KeyError,TypeError,struct.error,FileNotFoundError) as error:out[case]=dict(rejected=True,integrity_rebound=True,reason=str(error))
        else:raise ValueError('invalid SDK archive accepted: '+case)
    return out

def run(output):
    output=w.canonical(output);w.require(not output.exists(),'new review required');before=sources();output.mkdir(mode=0o700)
    for name,digest in before.items():
        raw=w.plain(w.b.REPO/name,2*1024*1024);w.require(sha(raw)==digest,'source changed');w.card.put(output,'source/'+name,raw)
    source=output/'source'
    for n,(name,diff) in enumerate(derivations(source).items()):w.card.put(output,'derivation-'+str(n)+'.diff',diff.encode())
    fixture=source/'research/usb-ds-iso/tests/generated_sdk_driver.m';fixture.write_text(generated_fixture(source))
    command=compile_command(source,output/'sdk-test');compiled=subprocess.run(command,capture_output=True,text=True)
    w.card.put(output,'compile.log',(compiled.stdout+compiled.stderr).encode());w.require(compiled.returncode==0,'native compile failed')
    models=output/'models';models.mkdir();native=subprocess.run([str(output/'sdk-test'),str(models)],capture_output=True,text=True)
    w.card.put(output,'native.stdout',native.stdout.encode());w.card.put(output,'native.stderr',native.stderr.encode());w.require(native.returncode==0,'native matrix failed')
    matrix=json.loads(native.stdout);w.require(matrix['case_count']==42,'wrong native count');accepted={};rejected={}
    for name,row in matrix['cases'].items():
        if row.get('init_rejected'):rejected[name]='unused SDK capability rejected before buffer initialization/submission';continue
        try:accepted[name]=analyze(models/name)
        except (ValueError,KeyError,TypeError,FileNotFoundError) as error:rejected[name]=str(error)
    w.require(set(accepted)=={'normal','queued-delay'} and len(rejected)==40,'native classification differs')
    negative=negative_cases(models/'normal',output/'negative-archives');w.require(len(negative)==20,'negative count differs')
    w.require(sources()==before,'source drift')
    plan=dict(schema='A23-two-epoch-sdk-offline-plan-1',sdk_execution_driver_implemented=True,caller_supplied_unused_sdk_lease=True,
        native_ingress_clock=True,per_epoch_durable_save_required=True,observation_minimum_ns=250000000,
        observation_is_callback_drain_proof=False,receipt_is_live_checkpoint=True,real_sdk_objects=0,actual_sdk_mapping_tested=False,
        dedicated_executable_implemented=False,formal_issuance_available=False,hardware_entry_enabled=False,sequences_allocated=False,
        device_trace_verified=False,device_package_reuse_established=False,remaining=0)
    w.write(output/'offline-plan.json',plan)
    audit=dict(schema='A23-two-epoch-sdk-offline-audit-1',passed=True,source_hashes=before,source_count=len(before),prior_sources_unchanged=329,
        native_cases=42,matrix=matrix,accepted=accepted,rejected=rejected,negative_archives=negative,compiler_command=command,
        generated_fixture_sha256=sha(fixture.read_bytes()),sanitizers=['address','undefined'],usb_requests=0,sd_accesses=0,real_sdk_objects=0,
        actual_sdk_mapping_tested=False,formal_records=0,formal_reservations=0,remaining=0,firmware_built=False,device_package_changed=False,hardware_verified=False)
    w.write(output/'audit.json',audit);w.b.seal(output)
    return dict(reference=w.reference(output),source_count=len(before),native_cases=42,accepted=list(accepted),rejected_native=40,negative_archives=20,passed=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
