#!/usr/bin/env python3
"""Independently bind injected burst journals to saved bytes. Simulation only."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from analyze_io_usb_host_evidence import require,integer,unique_object,analyze as evidence
from audit_io_usb_host_device import decode_status
from io_usb_host_burst_draft import assess_candidate
from io_usb_host_runtime_policy import audit_admission,duration_ns

PLAN=dict(schema='A23-burst-executor-plan-1',execution_mode='simulation',max_submissions=1,max_device_triggers=1,
    max_async_aborts=1,max_status_reads=2,repeat=0,transaction_count=960,request_count=192,first_frame_lead=64,
    first_sequence=1,trigger_timeout_ns=16000000,max_trigger_gap_ns=8000000,max_trigger_end_age_ns=48000000,
    completion_deadline_ns=2000000000,exit_grace_ns=1000000000,hardware_entry_enabled=False,hardware_verified=False,allow_next_burst=False)
EVENTS={'begin','status_before','iso_begin','iso_return','iso_callback','iso_snapshot','trigger_intent','trigger_return',
        'control_callback','status_after','save_begin','bundle_committed','stop','abort_intent','abort_return','close_begin','closed'}

def digest(raw):return hashlib.sha256(raw).hexdigest()
def load(path):return json.loads(path.read_bytes(),object_pairs_hook=unique_object)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'))
def analyze(root):
    root=Path(root);require(root.is_dir() and not root.is_symlink(),'invalid model directory')
    raw=(root/'journal.jsonl').read_bytes();require(0<len(raw)<=512*1024 and raw.endswith(b'\n'),'partial/oversized journal')
    rows=[json.loads(line,object_pairs_hook=unique_object) for line in raw.splitlines()]
    by={k:[] for k in EVENTS}
    for i,row in enumerate(rows,1):
        require(set(row)=={'schema','execution_mode','index','ticks','event','details'} and
                row['schema']=='A23-burst-executor-event-1' and row['execution_mode']=='simulation' and
                integer(row['index'],i,i) and integer(row['ticks'],1) and type(row['details']) is dict and
                row['event'] in EVENTS,'invalid journal record')
        require(i==1 or row['ticks']>=rows[i-2]['ticks'],'journal clock regressed')
        by[row['event']].append(row)
    for k in EVENTS-{'stop','iso_callback','control_callback'}:require(len(by[k])<=1,'repeated '+k)
    require(rows[0]['event']=='begin' and canonical(rows[0]['details'].get('plan'))==canonical(PLAN),'changed simulation plan')
    result=load(root/'result.json')
    require(result.get('schema')=='A23-burst-executor-result-1' and result.get('execution_mode')=='simulation','invalid result mode')
    for k in ['started','closed','saved','control_pending','storage_retained','unresolved','journal_failed',
              'hardware_entry_enabled','hardware_verified','allow_next_burst','baseline_accepted','usb_strict_pass','callback_drain_verified']:
        require(type(result.get(k)) is bool,'invalid result boolean')
    for k in ['hardware_entry_enabled','hardware_verified','allow_next_burst','baseline_accepted','usb_strict_pass','callback_drain_verified']:
        require(result[k] is False,'model grants hardware policy')
    for k,bound in [('trigger_attempts',1),('host_aborts',1),('iso_callbacks',128),('control_callbacks',128)]:
        require(integer(result.get(k),0,bound),'invalid result count')
    require(type(result.get('failure_reasons')) is list and all(type(s) is str for s in result['failure_reasons']),'invalid failures')
    reasons=[row['details'].get('reason') for row in by['stop']]
    require(all(type(s) is str and s for s in reasons) and len(set(reasons))==len(reasons),'invalid stop reasons')
    expected=set(reasons)|({'journal_failed'} if result['journal_failed'] else set())
    require(result['started'] and set(result['failure_reasons'])==expected and
            len(result['failure_reasons'])==len(expected),'result erased or invented failures')
    require(result['trigger_attempts']==len(by['trigger_return']) and result['host_aborts']==len(by['abort_return']) and
            result['iso_callbacks']==len(by['iso_callback']) and result['control_callbacks']==len(by['control_callback']),
            'result/journal count mismatch')
    if result['journal_failed']:
        # A durable prefix can outlive the sink's success reply. It cannot bind
        # later unlogged callbacks or certify a successful model execution.
        require(not result['closed'],'failed journal claims close')
    require(result['closed']==bool(by['closed']) and result['saved']==bool(by['bundle_committed']),'result/journal lifecycle mismatch')
    pending=bool(by['trigger_return'] and by['trigger_return'][0]['details'].get('accepted') and not by['control_callback'])
    require(result['control_pending']==pending,'result/control pending mismatch')
    statuses={}
    for name in ['status_before','status_after']:
        if by[name]:
            detail=by[name][0]['details'];b=base64.b64decode(detail['raw_base64'],validate=True)
            require(len(b)<=2048 and digest(b)==detail['sha256'],'raw STATUS binding mismatch')
            try:statuses[name]=decode_status(b)
            except ValueError:statuses[name]=None
    iso_frame_number=None
    if by['iso_return']:
        require(by['iso_begin'] and by['iso_begin'][0]['index']<by['iso_return'][0]['index'],'ISO return ordering')
        d=by['iso_begin'][0]['details'];s=d['sample'];require(all(integer(s.get(k)) for k in ['begin_ticks','end_ticks','current_frame']),'invalid frame')
        require(integer(d.get('first_frame'),1) and s['current_frame']+64==d['first_frame'],'firstFrame mismatch')
        iso_frame_number=d['first_frame']
        frame=dict(s,timebase_numerator=d['timebase_numerator'],timebase_denominator=d['timebase_denominator'])
        admission=by['iso_return'][0]['details']['admission'];audit_admission(admission,frame)
        require(type(by['iso_return'][0]['details']['accepted']) is bool and
                by['iso_return'][0]['details']['accepted']==admission['accepted'],'ISO accepted mismatch')
    if by['trigger_return']:
        require(by['trigger_intent'] and by['iso_return'] and by['iso_return'][0]['index']<by['trigger_intent'][0]['index']<by['trigger_return'][0]['index'],
                'trigger ordering')
        ret=by['trigger_return'][0];d=ret['details']
        require(canonical({k:d.get(k) for k in ['attempt','request_type','request','value','index','length','timeout_ns']})==
                canonical(dict(attempt=1,request_type=0x41,request=0x54,value=1,index=2,length=0,timeout_ns=16000000)), 'changed trigger tuple')
        require(type(d.get('accepted')) is bool and integer(d.get('start_ticks'),1),'invalid trigger result')
        require(d.get('error') is None or (type(d['error']) is dict and set(d['error'])=={'domain','code'} and
                type(d['error']['domain']) is str and type(d['error']['code']) is int),'invalid trigger error')
        require(admission['accepted'] and admission['budget_pass'] and not any(r['index']<ret['index'] for r in by['iso_callback']),
                'trigger after rejected/finished ISO')
        require(by['trigger_intent'][0]['ticks']<=d['start_ticks']<=ret['ticks'],'trigger clock ordering')
        gap=duration_ns(admission['return_ticks'],d['start_ticks'],frame['timebase_numerator'],frame['timebase_denominator'])
        age=duration_ns(frame['begin_ticks'],d['start_ticks'],frame['timebase_numerator'],frame['timebase_denominator'])
        require(integer(d.get('gap_ns')) and integer(d.get('age_ns')) and d['gap_ns']==gap and d['age_ns']==age and
                gap is not None and gap<=8000000 and age is not None and age+16000000<=48000000,'trigger budget mismatch')
    for name in ['iso_callback','control_callback']:
        for i,row in enumerate(by[name],1):
            detail=row['details'];require(integer(detail.get('count'),i,i) and integer(detail.get('status_u32'),0,2**32-1) and
                integer(detail.get('arrival_ticks'),1),'invalid callback')
            if name=='iso_callback':require(type(detail.get('pointer_mismatch')) is bool,'invalid pointer observation')
            else:require(by['trigger_return'] and by['trigger_return'][0]['index']<row['index'] and integer(detail.get('bytes')),'control callback ordering')
    if by['status_after']:require(by['iso_callback'] and by['iso_snapshot'] and by['iso_snapshot'][0]['index']<by['status_after'][0]['index'],'after before own completion')
    if by['abort_return']:
        require(by['abort_intent'] and by['abort_intent'][0]['index']<by['abort_return'][0]['index'] and
                not any(row['index']<by['abort_intent'][0]['index'] for row in by['iso_callback']),'abort after callback')
    bundle=root/'transfer';native=None;candidate=None
    if result['saved']:
        require((bundle/'COMMITTED').is_file(),'saved result lacks core')
        native=evidence(bundle);candidate=assess_candidate(bundle);meta=load(bundle/'metadata.json')
        require(iso_frame_number is not None and by['iso_snapshot'] and by['save_begin'] and
                by['iso_snapshot'][0]['index']<by['save_begin'][0]['index']<by['bundle_committed'][0]['index'],'save ordering')
        if not native['submission_rejected']:
            require(by['status_after'] and by['status_after'][0]['index']<by['save_begin'][0]['index'],'save before after STATUS')
        snap=by['iso_snapshot'][0]['details'];commit=by['bundle_committed'][0]['details']
        require(snap['raw_sha256']==digest((bundle/'raw.bin').read_bytes()) and
                snap['transactions_sha256']==digest((bundle/'transactions.bin').read_bytes()) and
                snap['overall_u32']==meta.get('overall_u32') and snap['callback_arrival_ticks']==meta['callback_arrival_ticks'] and
                commit['manifest_sha256']==digest((bundle/'SHA256SUMS').read_bytes()) and
                commit['callback_count']==meta['callback_count_at_save'] and meta['first_frame']==iso_frame_number,
                'snapshot/core binding mismatch')
        if not native['submission_rejected']:
            require(by['iso_callback'][0]['details']['arrival_ticks']==meta['callback_arrival_ticks'] and
                    by['iso_callback'][0]['details']['status_u32']==meta['overall_u32'],'native callback binding mismatch')
    if result['closed']:
        require(by['close_begin'],'closed without close intent')
        close=by['close_begin'][0]
        require(set(close['details'])=={'control_pending','saved','prepared'} and
                all(type(v) is bool for v in close['details'].values()) and close['details']['saved']==result['saved'] and
                close['index']<by['closed'][0]['index'] and close['details']['control_pending'] is False and
                not result['storage_retained'] and not result['unresolved'],'invalid close')
        if not close['details']['prepared']:
            require(by['bundle_committed'] and by['bundle_committed'][0]['index']<close['index'],'close before commit')
        if by['trigger_return'] and by['trigger_return'][0]['details']['accepted']:
            require(by['control_callback'] and by['control_callback'][0]['index']<close['index'],'close while control pending')
    clean_control=bool(by['trigger_return'] and by['trigger_return'][0]['details']['accepted'] and
                       by['trigger_return'][0]['details']['error'] is None and len(by['control_callback'])==1 and
                       by['control_callback'][0]['details']['status_u32']==0 and by['control_callback'][0]['details']['bytes']==0)
    after=statuses.get('status_after');before=statuses.get('status_before')
    headers=bool(before and after and all(before[k]==0 for k in ['sequence','state','urb_id','report_id','post_result',
                 'requested','transferred','urb_status','report_count','report_result']) and before['speed'] in (0,3) and
                 before['endpoint']==after['endpoint']==0x83 and
                 after['sequence']==1 and after['state']==2 and after['requested']==after['transferred']==3072 and
                 after['urb_id']==after['report_id']>0 and after['speed']==3 and after['urb_status']==3 and
                 after['post_result']==after['report_result']==0 and after['report_count'] in (0,1))
    complete=bool(result['closed'] and result['saved'] and not result['journal_failed'] and not result['failure_reasons'] and
                  candidate and candidate['candidate_rule_matches'] and len(by['iso_callback'])==1 and clean_control and headers)
    return dict(schema='A23-burst-executor-analysis-1',execution_mode='simulation',journal_sha256=digest(raw),
                simulation_execution_complete=complete,journal_core_binding_verified=bool(native),candidate=candidate,
                result=result,device_log_bound=False,hardware_trigger_binding_verified=False,callback_drain_verified=False,
                hardware_verified=False,usb_strict_pass=False,baseline_accepted=False,allow_next_burst=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path);args=parser.parse_args()
    try:result=analyze(args.directory)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError) as error:
        print(json.dumps(dict(error=str(error),hardware_verified=False,allow_next_burst=False)));return 2
    print(json.dumps(result,indent=2));return 0 if result['simulation_execution_complete'] else 1
if __name__=='__main__':raise SystemExit(main())
