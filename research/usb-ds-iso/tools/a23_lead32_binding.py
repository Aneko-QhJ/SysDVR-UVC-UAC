"""New host-only plan and receipt; the six path-span device materials stay identical."""
from copy import deepcopy
import a23_path_span_device_binding as parent
from build_a23_waiting_receiver import WAIT_PLAN as PREVIOUS_PLAN

FILES=parent.FILES;EXTRA=parent.EXTRA;DEVICE=parent.DEVICE
load=parent.load;identity=parent.identity;binding_hash=parent.binding_hash
supplied_material=parent.supplied_material;once=parent.once
WAIT_PLAN=deepcopy(PREVIOUS_PLAN)
WAIT_PLAN['schema']='A23-waiting-burst-plan-2'
SDK_PLAN=WAIT_PLAN['sdk_plan']
SDK_PLAN.update(schema='A23-burst-sdk-plan-2',first_frame_lead=32,
                max_trigger_gap_ns=2000000,max_trigger_age_ns=8000000,max_trigger_end_age_ns=24000000)
SDK_PLAN['runtime_budget'].update(schema='A23-runtime-budget-2',max_frame_age_ns=4000000,
                                  max_enqueue_call_ns=2000000,reserve_ns=8000000)


def receipt(record):
    result=parent.receipt(record)
    result.update(schema='A23-waiting-burst-consumed-receipt-6',plan=deepcopy(WAIT_PLAN))
    return result


def generated(sources,bound):
    prefix='research/usb-ds-iso/'
    result={n:raw.decode() for n,raw in parent.generated(sources,bound).items()}
    for name in result:
        result[name]=result[name].replace('A23-waiting-burst-consumed-receipt-5','A23-waiting-burst-consumed-receipt-6')
        result[name]=result[name].replace('A23-waiting-receiver-description-5','A23-waiting-receiver-description-6')
    result['a23_waiting_receiver.m']=once(result['a23_waiting_receiver.m'],
        '@"device_configuration":@"path-span-window-30s",',
        '@"device_configuration":@"path-span-window-30s",@"host_configuration":@"host-lead32-window-1",')
    name='a23_waiting_burst_entry.m'
    result[name]=once(result[name],'A23-waiting-burst-plan-1','A23-waiting-burst-plan-2')
    guard=result['a23_waiting_build_guard.m']
    guard=once(guard,'"a23_path_span_device_guard.inc"','"a23_lead32_device_guard.inc"')
    for before,after in [('hashes.count>256','hashes.count>320'),('names.count>256','names.count>320'),('++entries>512','++entries>768')]:
        guard=once(guard,before,after)
    result['a23_waiting_build_guard.m']=guard
    guard=sources[prefix+'host/a23_path_span_device_guard.inc'].decode()
    guard=once(guard,'generated.count!=4','generated.count!=11')
    guard=once(guard,'A23-waiting-receiver-build-5','A23-waiting-receiver-build-6')
    result['a23_lead32_device_guard.inc']=guard
    runtime=sources[prefix+'host/io_usb_host_runtime_guard.m'].decode()
    runtime='#include "a23_lead32_policy.h"\n'+runtime
    for before,after in [('A23-runtime-budget-1','A23-runtime-budget-2'),
                         ('@"max_frame_age_ns":@16000000','@"max_frame_age_ns":@4000000'),
                         ('@"max_enqueue_call_ns":@8000000','@"max_enqueue_call_ns":@2000000'),
                         ('@"reserve_ns":@16000000','@"reserve_ns":@8000000'),
                         ('queryNS <= 2000000 && ageNS <= 16000000','A23Lead32Admission(queryNS,ageNS)'),
                         ('callNS <= 8000000','A23Lead32Call(callNS)')]:
        runtime=once(runtime,before,after)
    result['io_usb_host_runtime_guard.m']=runtime
    driver=sources[prefix+'host/io_usb_host_burst_sdk_driver.m'].decode()
    for before,after in [('A23-burst-sdk-plan-1','A23-burst-sdk-plan-2'),('@"first_frame_lead":@64','@"first_frame_lead":@32')]:
        driver=once(driver,before,after)
    driver=once(driver,'@"runtime_budget":A23RuntimeBudget(),',
                '@"max_trigger_gap_ns":@2000000,@"max_trigger_age_ns":@8000000,@"max_trigger_end_age_ns":@24000000,@"runtime_budget":A23RuntimeBudget(),')
    result['io_usb_host_burst_sdk_driver.m']=driver
    transport=sources[prefix+'host/io_usb_host_burst_sdk_transport.m'].decode()
    transport='#include "a23_lead32_policy.h"\n'+transport
    require=parent.old.require
    require(transport.count(']+64')==3,'transport lead anchors drift')
    transport=transport.replace(']+64',']+32')
    transport=once(transport,'UINT64_MAX-64','UINT64_MAX-32')
    transport=once(transport,'gap<=8000000 && age<=32000000','A23Lead32Trigger(gap,age)')
    result['io_usb_host_burst_sdk_transport.m']=transport
    # Models compile isolated copies of the old fixtures, with the expected first frame36+32.
    mock=sources[prefix+'tests/io_usb_host_mock_adapter.h'].decode()
    mock=once(mock,'frame == 100','frame == 68').replace('../host/','')
    result['lead32_mock_adapter.h']=mock
    fixture=sources[prefix+'tests/io_usb_host_burst_sdk_driver_test.m'].decode()
    fixture=fixture.replace('"io_usb_host_mock_adapter.h"','"lead32_mock_adapter.h"').replace('../host/','').replace('../../../source/uvc/','')
    result['lead32_driver_fixture.m']=fixture
    loop=sources[prefix+'tests/a23_waiting_receiver_fixture.m'].decode()
    loop=once(loop,'"io_usb_host_burst_sdk_driver_test.m"','"lead32_driver_fixture.m"').replace('../host/','')
    result['lead32_loop_fixture.m']=loop
    require(len(result)==11,'generated closure drift')
    return {n:raw.encode() for n,raw in result.items()}
