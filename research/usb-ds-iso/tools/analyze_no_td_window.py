#!/usr/bin/env python3
"""Classify saved no-TD evidence without writing inputs or accessing USB."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.startswith('{')]

def analyze(run):
    host=rows(run/'host.jsonl');backend=rows(run/'native-stderr.txt')
    pick=lambda data,kind:[r for r in data if r.get('kind')==kind]
    native=pick(backend,'darwin_iso_native');transfers=pick(host,'iso_transfer')
    statuses=pick(host,'device_status');gates=pick(host,'native_empty_gate')
    windows=pick(host,'receive_only_baseline');timings=pick(host,'no_td_window_timing')
    queues=pick(backend,'darwin_iso_queue_timing');schedules=pick(backend,'darwin_iso_schedule')
    raw_path=run/'host.jsonl.seq0.buffer.bin';raw=raw_path.read_bytes() if raw_path.exists() else b''
    errors=[]
    if len(transfers)!=1 or len(native)!=960 or [r['index'] for r in native]!=list(range(960)):
        errors.append('missing/duplicate/out-of-order transfer or native records')
    if len(raw)!=184320 or any(raw):errors.append('raw missing, wrong size, or not zero')
    if len(statuses)!=2 or any(r['state']!=0 or r['sequence']!=0 or r['urb_id']!=0 for r in statuses):
        errors.append('device not fresh idle throughout')
    if len(statuses)==2 and any(statuses[0][k]!=statuses[1][k] for k in
        ['state','sequence','urb_id','report_id','requested','raw_count','urb_status','post_result','report_result','diagnostics_hex']):
        errors.append('device status changed')
    if pick(host,'host_trigger_timing'):errors.append('unexpected trigger')
    if len(windows)!=1 or not windows[0]['no_td_submitted'] or not windows[0]['device_state_unchanged'] or windows[0]['host_cancel_requested']:
        errors.append('missing/changed/cancelled window')
    if len(timings)!=1 or timings[0]['requested_wait_ms']!=40 or timings[0]['burst_control_sent'] or timings[0]['actual_wait_ms']<40:
        errors.append('wait/control mismatch')
    if len(queues)!=1 or queues[0]['clock']!='CLOCK_MONOTONIC' or queues[0]['queue_result']!=0:
        errors.append('missing/failed native queue timing')
    elif not (queues[0]['frame_before_ns']<=queues[0]['frame_after_ns']<=queues[0]['queue_before_ns']<=queues[0]['queue_after_ns']<=queues[0]['callback_entry_ns']):
        errors.append('native queue timestamps out of order')
    if len(schedules)!=1 or any(schedules[0][k]!=v for k,v in [('configured_lead_frames',64),('packets',960),('interval',1),('speed',3)]):
        errors.append('schedule mismatch')
    if transfers:
        packets=transfers[0]['packets']
        if len(packets)!=960 or [p['index'] for p in packets]!=list(range(960)) or any(p['length'] for p in packets):
            errors.append('public packets incomplete/nonempty')
    if any(r['requested']!=192 or r['actual']!=0 for r in native):errors.append('native requested/actual mismatch')
    if len(gates)!=1 or gates[0]['records']!=960 or gates[0]['payloads']!=0 or not gates[0]['raw_saved']:
        errors.append('callback evidence missing')
    if len(pick(host,'host_callback_time'))!=1:errors.append('missing/duplicate callback')
    allowed={0,0xE00002E7};anomaly=any(r['status'] not in allowed or r['overall'] not in allowed for r in native)
    prefix=0
    for r in native:
        if r['status']!=0xE000400E or r['actual']:break
        prefix+=1
    public_ok=bool(transfers and transfers[0]['status']==0 and all(p['status']==0 for p in transfers[0]['packets']))
    clean=not errors and not anomaly and public_ok and bool(gates and gates[0]['passed'])
    return dict(device_revision='A23',host_revision='no-td-window-1',evidence_complete=not errors,evidence_errors=errors,
        host_baseline_passed=clean,native_anomaly=anomaly,native_records=len(native),
        native_status_counts={f'{k:08X}':v for k,v in Counter(r['status'] for r in native).items()},
        overall_codes=sorted({f"{r['overall']:08X}" for r in native}),initial_empty_not_sent_slots=prefix,
        raw_size=len(raw),raw_all_zero=len(raw)==184320 and not any(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),
        schedule=schedules,queue_timing=queues,host_timing=timings,device_statuses=statuses,
        microframe_observations=pick(backend,'darwin_microframe_observation'),device_no_td_log_verified=False,
        switch_log_pending=True,strict_no_td_acceptance_passed=False,root_cause_confirmed=False,
        stability_verified=False,usb_accessed_by_analyzer=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path);args=parser.parse_args()
    print(json.dumps(analyze(args.run),indent=2))

if __name__=='__main__':main()
