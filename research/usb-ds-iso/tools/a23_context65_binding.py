"""Independent sequence65/context candidate; old49 build and issuers frozen."""
from copy import deepcopy
import a23_sequence_binding as parent
import a23_context65_history as history
from a23_execution_context import POLICY as CONTEXT_POLICY

FILES=parent.FILES;EXTRA=parent.EXTRA;DEVICE=parent.DEVICE
load=parent.load;identity=parent.identity;binding_hash=parent.binding_hash
supplied_material=parent.supplied_material;once=parent.once
HISTORY,HISTORY_DIGEST=history.verify_scope(live=False)
FIRST=HISTORY['proposed']
parent.parent.parent.old.require(FIRST==65,'candidate requires reviewed65 block')
WAIT_PLAN=deepcopy(parent.WAIT_PLAN);WAIT_PLAN.update(schema='A23-waiting-burst-plan-4',execution_context_policy=CONTEXT_POLICY)
SDK_PLAN=WAIT_PLAN['sdk_plan'];SDK_PLAN['schema']='A23-burst-sdk-plan-4';SDK_PLAN['scenario']['first_sequence']=FIRST

def receipt(record):
    result=parent.receipt(record);result.update(schema='A23-waiting-burst-consumed-receipt-8',plan=deepcopy(WAIT_PLAN));return result

def generated(sources,bound):
    result={n:raw.decode() for n,raw in parent.generated(sources,bound).items()}
    for n in result:
        for before,after in [('A23-waiting-burst-consumed-receipt-7','A23-waiting-burst-consumed-receipt-8'),
            ('A23-waiting-receiver-description-7','A23-waiting-receiver-description-8'),
            ('A23-waiting-burst-plan-3','A23-waiting-burst-plan-4'),('A23-burst-sdk-plan-3','A23-burst-sdk-plan-4')]:
            result[n]=result[n].replace(before,after)
    for n in ('a23_waiting_receiver.m','a23_waiting_burst_entry.m','a23_waiting_build_guard.m'):
        result[n]='#import "a23_execution_context.h"\n'+result[n]
    result['a23_waiting_receiver.m']=once(result['a23_waiting_receiver.m'],'host-sequence-witness-1','host-sequence65-context-1')
    result['a23_waiting_receiver.m']=once(result['a23_waiting_receiver.m'],'@"first_sequence":@49', '@"execution_context_policy":A23ExecutionContextPolicy(),@"first_sequence":@65')
    result['a23_waiting_receiver.m']=once(result['a23_waiting_receiver.m'],parent.HISTORY_DIGEST,HISTORY_DIGEST)
    result['a23_waiting_burst_entry.m']=once(result['a23_waiting_burst_entry.m'],'@"sdk_plan":A23DormantBurstSDKPlan(),',
        '@"sdk_plan":A23DormantBurstSDKPlan(),@"execution_context_policy":A23ExecutionContextPolicy(),')
    for n in ('io_usb_host_burst_sdk_driver.m','io_usb_host_evidence.m'):
        result[n]=once(result[n],'@"first_sequence":@49','@"first_sequence":@65')
    result['io_usb_host_burst_sdk_transport.m']=once(result['io_usb_host_burst_sdk_transport.m'],'@"value":@49,@"index":@2','@"value":@65,@"index":@2')
    result['io_usb_host_sdk_adapter.m']=once(result['io_usb_host_sdk_adapter.m'],'.wValue=49,','.wValue=65,')
    fixture=result['lead32_driver_fixture.m']
    for before,after in [('s.sequence=49;s.state=2;','s.sequence=65;s.state=2;'),('(uint16_t)(p+49)','(uint16_t)(p+65)'),('boundRequest.wValue==49','boundRequest.wValue==65')]:fixture=once(fixture,before,after)
    result['lead32_driver_fixture.m']=fixture
    guard=result.pop('a23_sequence_device_guard.inc')
    result['a23_context65_device_guard.inc']=once(once(guard,'generated.count!=13','generated.count!=14'),'A23-waiting-receiver-build-7','A23-waiting-receiver-build-8')
    guard=result['a23_waiting_build_guard.m']
    guard=once(guard,'"a23_sequence_device_guard.inc"','"a23_context65_device_guard.inc"')
    for before,after in [('hashes.count>320','hashes.count>352'),('names.count>320','names.count>352')]:guard=once(guard,before,after)
    # Context bytes are checked and hashed into the process claim. The SDK
    # handoff rechecks the same file; no physical process identity is implied.
    old='BOOL A23ClaimWaitingProcess(NSString *run,NSDictionary *checked)\n{return A23SaveBurstEntryResult(run,@"WAIT_PROCESS_CLAIMED",@{@"schema":@"A23-waiting-process-claim-1",@"checked":checked});}'
    new='''static NSData *contextBytes(NSString *run,NSDictionary *checked)
{
    NSData *raw=readFile([run stringByAppendingPathComponent:@"execution-context.json"],16384);
    NSDictionary *context=raw ? [NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL] : nil;
    if(!A23ValidateExecutionContext(context,checked[@"receiver_sha256"]))return nil;
    NSMutableData *line=[raw mutableCopy];[line appendBytes:"\\n" length:1];
    NSData *encoded=encode(context);
    return [raw isEqual:encoded] || [line isEqual:encoded] ? raw : nil;
}
BOOL A23ClaimWaitingProcess(NSString *run,NSDictionary *checked)
{
    NSData *raw=contextBytes(run,checked);if(!raw)return NO;
    return A23SaveBurstEntryResult(run,@"WAIT_PROCESS_CLAIMED",@{@"schema":@"A23-waiting-process-claim-2",
        @"checked":checked,@"execution_context_sha256":sha(raw)});
}'''
    guard=once(guard,old,new)
    guard=once(guard,'NSDictionary *expected=@{@"schema":@"A23-waiting-process-claim-1",@"checked":_checked};',
        'NSData *contextRaw=contextBytes(_run,_checked);if(!contextRaw)return NO;\n    NSDictionary *expected=@{@"schema":@"A23-waiting-process-claim-2",@"checked":_checked,@"execution_context_sha256":sha(contextRaw)};')
    result['a23_waiting_build_guard.m']=guard
    main=sources['research/usb-ds-iso/host/a23_waiting_receiver_main.m'].decode()
    main='#import "a23_execution_context.h"\n'+main
    main=once(main,'BOOL buildOnly=argc==3', '''if(argc==2 && !strcmp(argv[1],"--execution-context")){
            char *path=realpath(argv[0],NULL);if(!path)return 2;NSString *binary=@(path);free(path);
            return printJSON(A23ReadExecutionContext(binary));
        }
        BOOL buildOnly=argc==3''')
    main=once(main,'if(!A23ClaimWaitingProcess(run,checked))', '''NSDictionary *context=A23ReadExecutionContext(binary);
        if(!A23SaveBurstEntryResult(run,@"execution-context.json",context))return 1;
        if(!A23ValidateExecutionContext(context,checked[@"receiver_sha256"])){
            fputs("Execution context rejected before process claim or native wait; no retry.\\n",stderr);return 1;
        }
        if(!A23ClaimWaitingProcess(run,checked))''')
    result['a23_waiting_receiver_main.m']=main
    parent.parent.parent.old.require(len(result)==14,'context65 generated closure drift')
    return {n:raw.encode() for n,raw in result.items()}
