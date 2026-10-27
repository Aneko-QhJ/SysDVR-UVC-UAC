"""Fixed SDK diagnostic plan; software fields never certify hardware."""
import json
from analyze_io_usb_host_evidence import require

PLAN=dict(schema='A23-burst-sdk-plan-1',backend='iousbhost-single-burst-1',
    scenario=dict(kind='single_burst',first_sequence=1),first_frame_lead=64,
    transaction_count=960,request_bytes_per_transaction=192,transfer_options=0,
    max_submissions=1,max_device_triggers=1,max_async_aborts=1,repeat=0,
    runtime_budget=dict(schema='A23-runtime-budget-1',max_frame_query_ns=2000000,max_frame_age_ns=16000000,
        max_enqueue_call_ns=8000000,reserve_ns=16000000,frame_period_ns_assumption=1000000,
        exit_grace_ns=1000000000,hardware_timing_verified=False),
    control_deadline_ns=16000000,iso_deadline_ns=2000000000,exit_wait_ns=1000000000,
    closed_observation_ns=250000000,hardware_entry_enabled=False,hardware_verified=False,allow_next_burst=False)
SCOPE=dict(kind='single_fresh_A23_diagnostic',runtime_record=21,video_disabled_required=True,
    connection_speed_required=3,baseline_accepted=False,allow_next_burst=False)
def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def validate_plan(value):require(canonical(value)==canonical(PLAN),'changed SDK burst diagnostic plan')
def validate_scope(value):require(canonical(value)==canonical(SCOPE),'changed SDK burst diagnostic scope')
