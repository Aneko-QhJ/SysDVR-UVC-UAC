"""File-only paired SDK capability review, mocked preparation and runtime I/O."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

import audit_a23_two_epoch as prior
from audit_a23_multiburst_admission import function_span
from analyze_a23_paired_resources import analyze

w=prior.w
PARENT=w.A/'A23-two-epoch-closeout-20261018'
PARENT_SUM='8ae71fea40c27746bf3b2d82b4561f08506445e655e1e160878534c30049f7c6'
NEW=('host/a23_paired_sdk_adapter.h','host/a23_paired_sdk_adapter.m','tests/a23_paired_sdk_fixture.inc',
     'tools/analyze_a23_paired_resources.py','tools/audit_a23_paired_sdk.py','tests/test_a23_paired_sdk.py')
NATIVE=('io_usb_host_transaction_owner.m','io_usb_host_runtime_guard.m','io_usb_host_evidence.m',
        'io_usb_host_session.m','io_usb_host_sdk_adapter.m','a23_two_epoch_receiver.m','a23_paired_sdk_adapter.m')
SDK=Path('/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/IOUSBHost.framework/Headers')


def sources():
    w.card.seal_verify(PARENT);w.require(w.sha(w.plain(PARENT/'SHA256SUMS'))==PARENT_SUM,'parent closeout differs')
    parent=w.load(PARENT/'closeout.json');current=prior.sources();w.require(len(current)==323 and current==parent['source_hashes'],'prior323 drift')
    for n in NEW:
        key='research/usb-ds-iso/'+n;w.require(key not in current,'new overlap');current[key]=w.sha(w.plain(w.ROOT/n))
    return dict(sorted(current.items()))


def generated_fixture(source):
    root=Path(source)/'research/usb-ds-iso';old=(root/'tests/a23_two_epoch_receiver_test.m').read_text()
    w.require(old.count('\nint main(')==1,'frozen fixture entry ambiguous')
    return old[:old.index('\nint main(')]+'\n'+(root/'tests/a23_paired_sdk_fixture.inc').read_text()


def compile_command(source,binary):
    root=Path(source)/'research/usb-ds-iso'
    return ['clang','-fobjc-arc','-fblocks','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-g',
        '-framework','Foundation','-framework','IOUSBHost','-framework','IOKit',
        *(str(root/'host'/n) for n in NATIVE),str(root/'tests/generated_paired_test.m'),'-o',str(binary)]


def accessor_binding(source):
    root=Path(source)/'research/usb-ds-iso';old=(root/'host/io_usb_host_sdk_adapter.m').read_text().split('@implementation A23DormantSDKOperations')[0]
    new=(root/'host/a23_paired_sdk_adapter.m').read_text().split('@implementation A23PairedSDKOperations')[0];result={}
    for signature in ('- (NSDictionary *)descriptorBytes:(NSError **)error','- (id<A23TransactionTransport>)copyTransport:(NSError **)error',
        '- (NSData *)currentEndpointBytes','- (NSMutableData *)allocate:(NSUInteger)length shared:(BOOL)shared error:(NSError **)error',
        '- (NSDictionary *)readStatus','- (NSDictionary *)readFrameSample','- (void)destroy'):
        x,y=function_span(old,signature);a,b=function_span(new,signature);w.require(old[x:y]==new[a:b],'SDK accessor changed: '+signature)
        result[signature]=w.sha(old[x:y].encode())
    all_new=(root/'host/a23_paired_sdk_adapter.m').read_text()
    w.require('request.wValue = 0;' in all_new and '.wValue=first' in all_new and 'interest(message);' in all_new and
        'dispatch_async(queue, ^{ interest(message); });' not in all_new,'paired control/native interest boundary differs')
    return result


def negatives(normal,root):
    root.mkdir();results={}
    cases=('poisoned','sdk-mode','dropped-reference','destroyed','three-allocations','two-pipes','duplicate-callback',
        'extra-status','boolean-count','receiver-mismatch','save-claim','hardware-claim')
    for case in cases:
        folder=root/case;shutil.copytree(normal,folder);path=folder/'paired-result.json';row=json.loads(path.read_text());lease=row['lease']
        if case=='poisoned':lease['poisoned']=True
        elif case=='sdk-mode':lease['execution_mode']='sdk_capability'
        elif case=='dropped-reference':lease['service_retained']=False
        elif case=='destroyed':row['destroys']=1
        elif case=='three-allocations':row['mapped_calls']=3
        elif case=='two-pipes':row['pipe_copies']=2
        elif case=='duplicate-callback':lease['iso_callbacks']=[2,1]
        elif case=='extra-status':lease['status_reads']=5
        elif case=='boolean-count':lease['aborts']=False
        elif case=='receiver-mismatch':row['receiver']['aborts']=False
        elif case=='save-claim':lease['continuation_save_verified']=True
        elif case=='hardware-claim':lease['hardware_verified']=True
        path.write_text(json.dumps(row,sort_keys=True))
        try:analyze(folder)
        except (ValueError,KeyError,TypeError) as error:results[case]=dict(rejected=True,reason=str(error))
        else:raise ValueError('bad paired receipt accepted: '+case)
    return results


def run(output):
    output=w.canonical(output);w.require(not output.exists(),'new review required');before=sources();output.mkdir(mode=0o700)
    for name,digest in before.items():
        raw=w.plain(w.b.REPO/name,2*1024*1024);w.require(w.sha(raw)==digest,'source changed')
        target=output/'source'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    source=output/'source';fixture=source/'research/usb-ds-iso/tests/generated_paired_test.m';fixture.write_text(generated_fixture(source))
    accessors=accessor_binding(source);headers={}
    for name in ('IOUSBHostDefinitions.h','IOUSBHostObject.h','IOUSBHostInterface.h','IOUSBHostPipe.h'):
        raw=w.plain((SDK/name).resolve());w.card.put(output,'sdk/'+name,raw);headers[name]=w.sha(raw)
    command=compile_command(source,output/'paired-test');compiled=subprocess.run(command,capture_output=True,text=True)
    w.card.put(output,'compile.log',(compiled.stdout+compiled.stderr).encode());w.require(compiled.returncode==0,'paired compile failed')
    models=output/'models';models.mkdir();native=subprocess.run([str(output/'paired-test'),str(models)],capture_output=True,text=True)
    w.card.put(output,'native.stdout',native.stdout.encode());w.card.put(output,'native.stderr',native.stderr.encode());w.require(native.returncode==0,'paired native matrix failed')
    matrix=json.loads(native.stdout);w.require(matrix['preparation_cases']==40 and matrix['runtime_cases']==23,'matrix dimensions differ')
    accepted={};rejected={}
    for name,row in matrix['runtime'].items():
        if row.get('core_rejected_sdk_mode'):rejected[name]='SDK resources rejected by frozen offline receiver';continue
        try:accepted[name]=analyze(models/name)
        except (ValueError,KeyError,TypeError) as error:rejected[name]=str(error)
    w.require(set(accepted)=={'normal'} and len(rejected)==22,'paired combined classification differs')
    negative=negatives(models/'normal',output/'negative-receipts');w.require(len(negative)==12,'negative count differs')
    w.require(sources()==before,'source drift during paired audit')
    plan=dict(schema='A23-paired-sdk-offline-plan-1',distinct_simulation_and_sdk_providers=True,sdk_objects_created=0,sdk_mapping_actually_tested=False,
        production_sdk_driver_implemented=False,frozen_offline_receiver_accepts_sdk_resources=False,preparation_attempts_per_provider=1,
        interface_opens_per_provider=1,pipe_copies=1,allocation_calls=4,iso_limit=2,trigger_limit=2,status_limit=4,frame_limit=2,abort_limit=1,
        saved_epoch_gate_owned_by_coordinator=True,lease_itself_proves_durable_save=False,no_active_resource_destroy_api=True,
        hardware_entry_enabled=False,sequences_allocated=False,formal_records=0,formal_reservations=0,remaining=0)
    w.write(output/'offline-plan.json',plan)
    audit=dict(schema='A23-paired-sdk-offline-audit-1',passed=True,source_hashes=before,source_count=len(before),prior_sources_unchanged=323,
        preparation_cases=40,runtime_cases=23,matrix=matrix,accepted=accepted,rejected=rejected,negative_receipts=negative,
        sdk_accessors_bound=accessors,sdk_header_hashes=headers,generated_fixture_sha256=w.sha(fixture.read_bytes()),compiler_command=command,
        usb_requests=0,sd_accesses=0,real_sdk_objects=0,actual_sdk_mapping_tested=False,formal_records=0,formal_reservations=0,remaining=0,
        firmware_built=False,device_package_changed=False,hardware_verified=False)
    w.write(output/'audit.json',audit);w.b.seal(output)
    return dict(reference=w.reference(output),sources=len(before),preparation_cases=40,runtime_cases=23,negative_receipts=12,accepted=list(accepted),passed=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(p.parse_args().output),indent=2))
