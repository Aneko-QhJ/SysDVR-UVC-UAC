#!/usr/bin/env python3
"""Independently check saved serial native/raw/device evidence; never access USB."""
from pathlib import Path
import argparse,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'private/packages-A23-interval1/A'))
from summarize_run import decode_diag

def rows(path):
    result=[]
    for line in path.read_text().splitlines():
        if line.startswith('{'):
            try:result.append(json.loads(line))
            except json.JSONDecodeError:continue
    return result

def analyze(run):
    host=rows(run/'host.jsonl');native=rows(run/'native-stderr.txt')
    transfers=[r for r in host if r.get('kind')=='iso_transfer']
    gates=[r for r in host if r.get('kind')=='native_serial_gate']
    triggers=[r for r in host if r.get('kind')=='host_trigger_timing']
    statuses=[r for r in host if r.get('kind')=='device_status']
    results=[r for r in host if r.get('kind')=='result']
    native_records=[r for r in native if r.get('kind')=='darwin_iso_native']
    batches=[];current=[]
    for r in native_records:
        if r['index']==0 and current:batches.append(current);current=[]
        current.append(r)
    if current:batches.append(current)
    attempts=[]
    for position,t in enumerate(transfers):
        seq=t['sequence'];batch=batches[position] if position<len(batches) else []
        packets=t['packets'];active=[p for p in packets if p['length']]
        indices=[p['index'] for p in active]
        native_ok=len(batch)==960 and [p['index'] for p in batch]==list(range(960)) and all(p['overall']==0 and p['requested']==192 for p in batch)
        native_active=[p for p in batch if p['actual']]
        native_ok=native_ok and len(native_active)==16 and [p['index'] for p in native_active]==indices and all(p['actual']==192 and p['status']==0 for p in native_active)
        raw_path=run/('host.jsonl.seq'+str(seq)+'.buffer.bin');raw=raw_path.read_bytes() if raw_path.exists() else b''
        exact=len(raw)==960*192 and len(active)==16
        for ordinal,p in enumerate(active):
            expected_seq=(seq+ordinal)&65535
            expected=b'ISO1'+expected_seq.to_bytes(2,'little')+bytes((j^expected_seq^(expected_seq>>8))&255 for j in range(6,192))
            actual=raw[p['index']*192:(p['index']+1)*192]
            exact=exact and p['length']==192 and actual==expected and actual==bytes.fromhex(p.get('data_hex',''))
        if len(raw)==960*192:
            exact=exact and all(not raw[i*192:(i+1)*192].strip(b'\0') for i in range(960) if i not in indices)
        consecutive=len(indices)==16 and indices==list(range(indices[0],indices[0]+16))
        device=next((s for s in reversed(statuses) if s['sequence']==seq),None)
        diag=decode_diag(device['diagnostics_hex']) if device else None
        terminal=bool(device and diag and device['state']==2 and device['post_result']==device['report_result']==0 and device['urb_id']==device['report_id'] and device['urb_status']==3 and device['requested']==device['raw_count']==3072 and diag.get('diagnostics_layout')=='ISO7' and diag.get('terminal')==1 and diag.get('completed_bitmap')=='FFFF' and diag.get('actual_sum')==3072)
        public=t['status']==0 and all(p['status']==0 for p in active)
        gate=next((g for g in gates if g['sequence']==seq),None)
        receipt=next((r for r in results if r['sequence']==seq),None)
        passed=bool(native_ok and exact and consecutive and public and terminal and gate and gate['passed'] and gate['raw_saved'] and receipt and receipt['iso_payload_verified'] and receipt['completion_verified'])
        first=int(diag.get('first_virtual_trb','0'),16) if diag else 0
        tag_ok=False
        if first and diag:
            base=first&~4095;slot=(first-base)//16
            events=diag.get('audit_records',[])
            tag_ok=len(events)==2 and all(ev['valid'] and ev['completion_code']==1 and ev['raw_count']==192 and int(ev['pointer_or_tag'],16)==base+((slot+1+2*i)%247)*16 for i,ev in enumerate(events))
        attempts.append(dict(sequence=seq,passed=passed,native=native_ok,public=public,exact_raw=exact,consecutive=consecutive,terminal=terminal,own_first_two_ED_tags_match_ring=tag_ok,first_virtual_trb=first,first_cycle=diag.get('cycle') if diag else None,indices=indices,raw_sha256=hashlib.sha256(raw).hexdigest(),device=device,diagnostics=diag))
    first_failure=next((a['sequence'] for a in attempts if not a['passed']),None)
    failure_stop=first_failure is None or all(r['sequence']<=first_failure for r in triggers)
    ordered=[t['sequence'] for t in triggers]==list(range(1,len(triggers)+1))
    sessions=[r for r in host if r.get('kind')=='session'];target=sessions[0]['repeats'] if sessions else 0
    pages=[a['first_virtual_trb']&~4095 for a in attempts]
    slots=[(a['first_virtual_trb']&4095)//16 for a in attempts]
    cycles=[a['first_cycle'] for a in attempts]
    ring_progress=bool(attempts and len(set(pages))==1 and all(s<247 for s in slots) and all(slots[i]==(slots[i-1]+32)%247 and cycles[i]==(cycles[i-1]^int(slots[i-1]+32>=247)) for i in range(1,len(slots))))
    success=bool(target==16 and len(triggers)==len(attempts)==16 and ordered and all(a['passed'] for a in attempts) and ring_progress and any(slots[i]<slots[i-1] for i in range(1,len(slots))) and all(a['own_first_two_ED_tags_match_ring'] for a in attempts))
    return dict(device_revision='A23',host_revision='native-guard-serial-1',target=target,triggers=len(triggers),callbacks=len(attempts),strict_acceptance_passed=success,first_failure_sequence=first_failure,no_submission_after_failure=failure_stop,sequence_ordered=ordered,ring_progression_verified=ring_progress,observed_ring_wraps=sum(slots[i]<slots[i-1] for i in range(1,len(slots))),all_own_event_tags_match=bool(attempts and all(a['own_first_two_ED_tags_match_ring'] for a in attempts)),attempts=attempts,switch_log_pending=True,runtime_revision_identity_verified=False,stability_verified=False,root_cause_confirmed=False,wire_trace_verified=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);a=p.parse_args();e=analyze(a.run)
    (a.run/'serial-evidence.json').write_text(json.dumps(e,indent=2)+'\n')
    print(json.dumps({k:v for k,v in e.items() if k!='attempts'},indent=2))
if __name__=='__main__':main()
