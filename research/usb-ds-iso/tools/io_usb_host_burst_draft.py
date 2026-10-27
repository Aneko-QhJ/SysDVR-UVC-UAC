#!/usr/bin/env python3
"""Print/check an offline single-burst draft. Contains no USB executor or ticket writer."""
import argparse
from collections import Counter
import json
from pathlib import Path

from analyze_io_usb_host_evidence import ROW, analyze as evidence, integer, require

PLAN = dict(schema='A23-single-burst-diagnostic-draft-1',execution_mode='offline_model',
    scenario={'kind':'single_burst','first_sequence':1},transaction_count=960,request_bytes_per_transaction=192,
    expected_packets=16,first_frame_lead=64,transfer_options=0,max_submissions=1,max_device_triggers=1,
    max_async_aborts=1,max_device_cancels=0,max_status_reads=2,repeat=0,
    trigger={'request_type':0x41,'request':0x54,'value':1,'index':2,'length':0,'requested_timeout_ns':16000000},
    trigger_budget={'max_query_ns':2000000,'max_frame_age_ns':16000000,'max_enqueue_call_ns':8000000,
                    'max_enqueue_to_trigger_ns':8000000,'max_trigger_end_age_ns':48000000,
                    'reserve_ns':16000000,'frame_period_ns_assumption':1000000},
    empty_rule={'expected_status_u32':0,'origin':'one_saved_no_td_observation','verified':False},
    sdk_timeout_granularity_verified=False,transport_implemented=False,hardware_entry_enabled=False,
    hardware_verified=False,baseline_accepted=False,allow_next_burst=False,callback_drain_verified=False)


def validate_plan(plan):
    require(type(plan) is dict and json.dumps(plan,sort_keys=True,separators=(',',':')) ==
            json.dumps(PLAN,sort_keys=True,separators=(',',':')), 'changed/offline burst draft')


def trigger_decision(*, query_ns, age_ns, enqueue_ns, gap_ns, before_valid, enqueue_accepted,
                     owner_pending, journal_ok, interrupted, detached, previous_triggers):
    require(all(integer(t,0,2**64-1) for t in (query_ns,age_ns,enqueue_ns,gap_ns)) and
            integer(previous_triggers,0,1), 'invalid trigger measurements/count')
    require(all(type(b) is bool for b in (before_valid,enqueue_accepted,owner_pending,journal_ok,interrupted,detached)),
            'invalid trigger state')
    failures=[]
    for good,reason in [(before_valid,'before_status_invalid'),(enqueue_accepted,'enqueue_not_accepted'),
                        (owner_pending,'completion_before_trigger'),(journal_ok,'journal_failed'),
                        (not interrupted,'interrupted'),(not detached,'detached'),
                        (previous_triggers==0,'trigger_already_attempted')]:
        if not good:failures.append(reason)
    budget=PLAN['trigger_budget']
    if age_ns<query_ns:failures.append('frame_age_before_query_end')
    for value,key in [(query_ns,'max_query_ns'),(age_ns,'max_frame_age_ns'),
                      (enqueue_ns,'max_enqueue_call_ns'),(gap_ns,'max_enqueue_to_trigger_ns')]:
        if value>budget[key]:failures.append(key+'_exceeded')
    end_age=age_ns+enqueue_ns+gap_ns+PLAN['trigger']['requested_timeout_ns']
    if end_age>budget['max_trigger_end_age_ns']:failures.append('trigger_end_age_budget_exceeded')
    return dict(model_trigger_allowed=not failures,failure_reasons=failures,projected_trigger_end_age_ns=end_age,
                timing_basis='software_budget_assumption_not_wire_deadline',hardware_entry_enabled=False,
                allow_next_burst=False,hardware_timing_verified=False)


def lifecycle_disposition(state, *, committed, pointer_matches, detached, abort_attempts, journal_ok,
                          control_pending=False):
    require(state in {'prepared','rejected','pending','completed','retained'} and
            all(type(b) is bool for b in (committed,pointer_matches,detached,journal_ok,control_pending)) and
            integer(abort_attempts,0,1),'invalid lifecycle input')
    close=False;abort=False
    if not journal_ok or state=='retained' or (state in {'pending','completed'} and not pointer_matches):
        action='retain_resources'
    elif state=='prepared' and not control_pending:action='close_prepared';close=True
    elif state in {'rejected','completed'} and committed and not control_pending:action='close_after_commit';close=True
    elif state=='pending' and not detached and not abort_attempts:action='abort_once_then_wait';abort=True
    else:action='retain_wait'
    return dict(model_action=action,may_close_host=close,may_request_host_abort=abort,
                may_cancel_device=False,may_resubmit=False,callback_drain_verified=False,allow_next_burst=False)


def assess_candidate(bundle):
    # Only simulation-format byte bundles are supported. Hardware session/trigger
    # binding is not implemented and cannot be supplied by this candidate check.
    bundle=Path(bundle);native=evidence(bundle)
    meta=json.loads((bundle/'metadata.json').read_bytes())
    require(meta['scenario']==PLAN['scenario'],'not the fresh sequence-1 burst draft')
    rows=list(ROW.iter_unpack((bundle/'transactions.bin').read_bytes()))
    empty=Counter(f'0x{r[0]:08x}' for r in rows if r[3]==0)
    failures=[]
    for good,reason in [(native['payload_matches'],'payload_mismatch'),(native['active_native_clean'],'active_native_error'),
                        (native['transactions_finalized'],'unfinished_transactions'),(native['callback_clean'],'callback_or_overall_error'),
                        (all(r[0]==0 for r in rows if r[3]==0),'empty_status_differs_from_observed_zero')]:
        if not good:failures.append(reason)
    return dict(schema='A23-burst-candidate-model-1',source='simulation_bundle',active_indices=native['active_indices'],
                payload_matches=native['payload_matches'],active_native_clean=native['active_native_clean'],
                overall_u32=native['overall_u32'],empty_status_counts=dict(sorted(empty.items())),
                candidate_rule_matches=not failures,failure_reasons=failures,empty_status_policy_verified=False,
                device_relation_verified=False,trigger_journal_binding_verified=False,hardware_entry_enabled=False,
                hardware_verified=False,usb_strict_pass=False,baseline_accepted=False,allow_next_burst=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('plan');sub.add_parser('candidate').add_argument('bundle',type=Path)
    args=parser.parse_args()
    try:result=PLAN if args.command=='plan' else assess_candidate(args.bundle)
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as error:
        print(json.dumps(dict(error=str(error),hardware_entry_enabled=False,allow_next_burst=False)));return 2
    print(json.dumps(result,indent=2));return 0 if args.command=='plan' or result['candidate_rule_matches'] else 1


if __name__=='__main__':raise SystemExit(main())
