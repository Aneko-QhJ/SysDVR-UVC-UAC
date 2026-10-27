#!/usr/bin/env python3
"""Validate supplied waiting/SDK file ordering. Never authenticates a device run."""
import json
from pathlib import Path
import uuid

import analyze_io_usb_host_context65 as sdk
from analyze_io_usb_host_evidence import unique_object, require
from a23_context65_binding import WAIT_PLAN

FLAGS=('begun','prepare_attempted','permit_claimed','prepared','started','waiter_closed',
       'wait_journal_failed','preflight_failed','finished','unresolved','hardware_verified',
       'usb_strict_pass','allow_next_burst')
EVENTS={'begin','adapter','claim_intent','claim_committed','sdk_open_intent','waiter_closed',
        'prepared','start_intent','preflight_failed'}


def uint(value,maximum=2**64-1):return type(value) is int and 0<=value<=maximum


def typed(a,b):
    if type(a) is not type(b):return False
    if type(b) is dict:return a.keys()==b.keys() and all(typed(a[k],v) for k,v in b.items())
    if type(b) is list:return len(a)==len(b) and all(typed(x,y) for x,y in zip(a,b))
    return a==b


def lines(path):
    raw=sdk.read_plain(Path(path),128*4096)
    rows=raw.splitlines()
    require(raw.endswith(b'\n') and 0<len(rows)<=128 and all(len(r)<=4095 for r in rows),'partial or oversized wait journal')
    return [json.loads(r,object_pairs_hook=unique_object) for r in rows]


def analyze(root):
    root=Path(root)
    result=json.loads(sdk.read_plain(root/'waiting-entry-result.json',16384),object_pairs_hook=unique_object)
    require(type(result) is dict and set(result)==set(FLAGS)|{'schema','wait_session_id','handoffs',
        'failed_releases','unreleased_tokens','failure','preparation_error','host_result'},'invalid waiting result fields')
    require(result['schema']=='A23-waiting-burst-entry-result-1' and all(type(result[k]) is bool for k in FLAGS),'invalid waiting result types')
    require(all(result[k] is False for k in ('hardware_verified','usb_strict_pass','allow_next_burst')),'unexpected authority')
    session=result['wait_session_id'];require(type(session) is str and str(uuid.UUID(session)).upper()==session.upper(),'invalid wait session')
    require(uint(result['handoffs'],1) and uint(result['failed_releases'],5) and type(result['unreleased_tokens']) is list and
        len(result['unreleased_tokens'])==result['failed_releases'] and all(uint(n,2**32-1) and n for n in result['unreleased_tokens']),'invalid retained references')
    rows=lines(root/'wait.jsonl');previous=adapter_last=0;adapter_index=0;by={k:[] for k in EVENTS}
    for i,row in enumerate(rows,1):
        require(type(row) is dict and set(row)=={'schema','session_id','index','ticks','event','details','hardware_verified','allow_next_burst'},'invalid wait row fields')
        require(row['schema']=='A23-waiting-burst-event-1' and row['session_id']==session and uint(row['index']) and row['index']==i and
            uint(row['ticks']) and row['ticks']>=previous and row['hardware_verified'] is False and row['allow_next_burst'] is False and
            row['event'] in EVENTS and type(row['details']) is dict,'invalid wait row')
        previous=row['ticks'];by[row['event']].append(row)
        if row['event']=='adapter':
            d=row['details'];adapter_index+=1
            require(set(d)=={'index','event','phase','reason','ticks','interface_id','device_id','count','native_result'} and
                all(uint(v) for v in d.values()) and d['index']==adapter_index and 1<=d['event']<=6 and d['phase']<=6 and
                adapter_last<=d['ticks']<=row['ticks'] and d['count']<=65 and d['native_result']<=2**32-1,'invalid adapter row')
            adapter_last=d['ticks']
    for name in EVENTS-{'adapter'}:require(len(by[name])<=1,'repeated wait event '+name)
    require(rows[0]['event']=='begin','missing wait begin')
    begin=rows[0]['details']
    require(set(begin)=={'plan','deadline','timebase_numerator','timebase_denominator'} and typed(begin['plan'],WAIT_PLAN) and
        uint(begin['deadline']) and all(uint(begin[k],2**32-1) and begin[k] for k in ('timebase_numerator','timebase_denominator')),'invalid wait plan/clock')
    started=result['started'];host=None
    if started:
        require(all(result[k] for k in ('begun','prepare_attempted','permit_claimed','prepared','waiter_closed')) and
            not result['wait_journal_failed'] and not result['preflight_failed'] and result['failed_releases']==0 and result['handoffs']==1,'started without successful handoff')
        order=['begin','claim_intent','claim_committed','sdk_open_intent','waiter_closed','prepared','start_intent']
        require(all(len(by[n])==1 for n in order),'missing start prerequisite')
        require([by[n][0]['index'] for n in order]==sorted(by[n][0]['index'] for n in order),'incorrect handoff/start order')
        adapters=by['adapter'];require([r['details']['event'] for r in adapters]==[1,2,3,4,5,6],'incomplete successful adapter sequence')
        require([r['details']['phase'] for r in adapters]==[1,2,3,4,5,6] and all(r['details']['reason']==0 and r['details']['native_result']==0 for r in adapters),'failed adapter before start')
        selected=adapters[3]['details'];ids=(selected['interface_id'],selected['device_id'])
        require(all(ids) and ids[0]!=ids[1] and all((r['details']['interface_id'],r['details']['device_id'])==ids for r in adapters[3:]),'changed selected identity')
        require(adapters[4]['details']['ticks']<begin['deadline'] and all(r['details']['count']==1 for r in adapters[3:]),'late or ambiguous handoff')
        require(adapters[4]['index']<by['claim_intent'][0]['index'] and
            by['sdk_open_intent'][0]['index']<adapters[5]['index']<by['waiter_closed'][0]['index'],'wait close/handoff outside preparation')
        for name in ('claim_intent','sdk_open_intent'):
            d=by[name][0]['details'];require(all(uint(d.get(k)) for k in ('interface_id','device_id')) and (d['interface_id'],d['device_id'])==ids,'mismatched handoff identity')
        require(typed(by['waiter_closed'][0]['details'],{'failed_releases':0,'handoffs':1}),'failed waiter close')
        sdk_rows=lines(root/'session.jsonl');first=sdk_rows[0]
        require(first.get('event')=='prepared' and by['waiter_closed'][0]['ticks']<=first['ticks']<=by['prepared'][0]['ticks'],'SDK driver constructed before wait close')
        binding=first['details']['binding']
        require(typed(by['prepared'][0]['details'],{'binding':binding}) and typed(by['start_intent'][0]['details'],{'binding':binding}) and
            typed(result['host_result']['binding'],binding),'SDK/wait binding mismatch')
        require(all(first['details'].get(k)==begin[k] for k in ('timebase_numerator','timebase_denominator')),'SDK/wait timebase mismatch')
        require((binding['identity']['interface_id'],binding['identity']['device_id'])==ids,'SDK identity mismatch')
        require(all(r['ticks']>=by['start_intent'][0]['ticks'] for r in sdk_rows[1:]),'SDK event before start intent')
        host=sdk.analyze(root)
    else:
        require(result['preflight_failed'] and result['finished'] and not result['unresolved'],'unstarted entry not closed as preflight failure')
    return dict(schema='A23-context65-waiting-entry-analysis-1',started=started,wait_rows=len(rows),
        supplied_order_consistent=True,sdk_analysis=host,
        journal_acknowledgement_verified=False,build_source_closure_verified=False,
        same_physical_run_verified=False,hardware_verified=False,usb_strict_pass=False,allow_next_burst=False)
