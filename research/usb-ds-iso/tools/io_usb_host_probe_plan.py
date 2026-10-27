#!/usr/bin/env python3
"""Fixed offline Mock observation plan. Printing this plan enables no capture."""
import argparse
import json
from analyze_io_usb_host_evidence import require

NO_TD_PLAN = dict(schema="A23-no-td-observation-plan-1",execution_mode="simulation",scenario={"kind":"no_td"},
    first_frame_lead=64,transaction_count=960,request_bytes_per_transaction=192,transfer_options=0,
    max_submissions=1,max_device_triggers=0,max_async_aborts=1,repeat=0,hardware_entry_enabled=False,
    hardware_verified=False,empty_status_policy="unverified",post_completion_requests="status_then_save_only",
    pending_exit="retain_until_process_exit")
RUNTIME_BUDGET = dict(schema="A23-runtime-budget-1",max_frame_query_ns=2000000,max_frame_age_ns=16000000,
    max_enqueue_call_ns=8000000,frame_period_ns_assumption=1000000,reserve_ns=16000000,
    exit_grace_ns=1000000000,hardware_timing_verified=False)
RUNTIME_PLAN = dict(NO_TD_PLAN,schema="A23-no-td-runtime-plan-2",runtime_budget=RUNTIME_BUDGET,
    service_reference="retain_before_identity_release_after_destroy",pending_exit="abort_once_wait_then_report_retained")
HARDWARE_PLAN = dict(RUNTIME_PLAN,schema='A23-no-td-hardware-plan-1',execution_mode='hardware',
    hardware_entry_enabled=True,completion_deadline_ns=2000000000,post_close_monitor_ns=250000000)


def validate_plan(plan):
    # Canonical JSON comparison also rejects bool/int/float substitution.
    encoded = json.dumps(plan,sort_keys=True,separators=(',',':'))
    require(type(plan) is dict and encoded in {json.dumps(p,sort_keys=True,separators=(',',':')) for p in (NO_TD_PLAN,RUNTIME_PLAN)},
            "unknown/changed no-TD plan")

def validate_hardware_plan(plan):
    require(type(plan) is dict and json.dumps(plan,sort_keys=True,separators=(',',':')) ==
            json.dumps(HARDWARE_PLAN,sort_keys=True,separators=(',',':')), 'unknown/changed hardware no-TD plan')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(RUNTIME_PLAN,sort_keys=True,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
