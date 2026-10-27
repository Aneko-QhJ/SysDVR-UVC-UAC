"""Isolated host candidate: fixed history-scoped sequence, unchanged device bytes."""
from copy import deepcopy
import a23_lead32_binding as parent
import a23_sequence_history as history

FILES=parent.FILES;EXTRA=parent.EXTRA;DEVICE=parent.DEVICE
load=parent.load;identity=parent.identity;binding_hash=parent.binding_hash
supplied_material=parent.supplied_material;once=parent.once
HISTORY,HISTORY_DIGEST=history.verify_scope(live=False)
FIRST=HISTORY['proposed']
WAIT_PLAN=deepcopy(parent.WAIT_PLAN);WAIT_PLAN['schema']='A23-waiting-burst-plan-3'
SDK_PLAN=WAIT_PLAN['sdk_plan'];SDK_PLAN['schema']='A23-burst-sdk-plan-3'
SDK_PLAN['scenario']['first_sequence']=FIRST


def receipt(record):
    result=parent.receipt(record)
    result.update(schema='A23-waiting-burst-consumed-receipt-7',plan=deepcopy(WAIT_PLAN))
    return result


def generated(sources,bound):
    result={n:v.decode() for n,v in parent.generated(sources,bound).items()};prefix='research/usb-ds-iso/'
    for n in result:
        result[n]=result[n].replace('A23-waiting-burst-consumed-receipt-6','A23-waiting-burst-consumed-receipt-7')
        result[n]=result[n].replace('A23-waiting-receiver-description-6','A23-waiting-receiver-description-7')
    result['a23_waiting_receiver.m']=once(result['a23_waiting_receiver.m'],
        '@"host_configuration":@"host-lead32-window-1",',
        '@"host_configuration":@"host-sequence-witness-1",'+
        f'@"first_sequence":@{FIRST},@"sequence_history_manifest_sha256":@"{HISTORY_DIGEST}",')
    result['a23_waiting_burst_entry.m']=once(result['a23_waiting_burst_entry.m'],'A23-waiting-burst-plan-2','A23-waiting-burst-plan-3')
    result['io_usb_host_burst_sdk_driver.m']=once(result['io_usb_host_burst_sdk_driver.m'],'A23-burst-sdk-plan-2','A23-burst-sdk-plan-3')
    result['io_usb_host_burst_sdk_driver.m']=once(result['io_usb_host_burst_sdk_driver.m'],'@"first_sequence":@1',f'@"first_sequence":@{FIRST}')
    result['io_usb_host_burst_sdk_transport.m']=once(result['io_usb_host_burst_sdk_transport.m'],
        '@"value":@1,@"index":@2',f'@"value":@{FIRST},@"index":@2')
    guard=result.pop('a23_lead32_device_guard.inc')
    guard=once(guard,'generated.count!=11','generated.count!=13')
    result['a23_sequence_device_guard.inc']=once(guard,'A23-waiting-receiver-build-6','A23-waiting-receiver-build-7')
    result['a23_waiting_build_guard.m']=once(result['a23_waiting_build_guard.m'],'"a23_lead32_device_guard.inc"','"a23_sequence_device_guard.inc"')
    adapter=sources[prefix+'host/io_usb_host_sdk_adapter.m'].decode()
    request='IOUSBDeviceRequest request={.bmRequestType=0x41,.bRequest=0x54,.wValue=1,.wIndex=2,.wLength=0};'
    adapter=once(adapter,request,'IOUSBDeviceRequest request=A23BoundSequenceBurstRequest();')
    helper=f'IOUSBDeviceRequest A23BoundSequenceBurstRequest(void) {{ return (IOUSBDeviceRequest){{.bmRequestType=0x41,.bRequest=0x54,.wValue={FIRST},.wIndex=2,.wLength=0}}; }}\n'
    result['io_usb_host_sdk_adapter.m']=once(adapter,'static BOOL adapterError(',helper+'\nstatic BOOL adapterError(')
    evidence=sources[prefix+'host/io_usb_host_evidence.m'].decode()
    result['io_usb_host_evidence.m']=once(evidence,'@"first_sequence":@1',f'@"first_sequence":@{FIRST}')
    fixture=result['lead32_driver_fixture.m']
    fixture=once(fixture,'s.sequence=1;s.state=2;',f's.sequence={FIRST};s.state=2;')
    fixture=once(fixture,'(uint16_t)(p+1)','(uint16_t)(p+'+str(FIRST)+')')
    fixture='extern IOUSBDeviceRequest A23BoundSequenceBurstRequest(void);\n'+fixture
    fixture=once(fixture,'assert(argc==2);NSString *root=',
        f'IOUSBDeviceRequest boundRequest=A23BoundSequenceBurstRequest();assert(boundRequest.bmRequestType==0x41 && boundRequest.bRequest==0x54 && boundRequest.wValue=={FIRST} && boundRequest.wIndex==2 && !boundRequest.wLength);\n        assert(argc==2);NSString *root=')
    # Declare the helper after SDK types are imported by the first header.
    fixture=fixture.replace('extern IOUSBDeviceRequest A23BoundSequenceBurstRequest(void);\n','',1)
    fixture=once(fixture,'#include <stdio.h>','#include <stdio.h>\nextern IOUSBDeviceRequest A23BoundSequenceBurstRequest(void);')
    result['lead32_driver_fixture.m']=fixture
    parent.parent.old.require(len(result)==13,'sequence generated closure drift')
    return {n:v.encode() for n,v in result.items()}
