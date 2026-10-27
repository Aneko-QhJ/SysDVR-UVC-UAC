#!/usr/bin/env python3
"""Read-only bounded serial clock audit; frame estimates retain 1 ms uncertainty."""
import argparse,json
from pathlib import Path
from analyze_matched_serial_run import analyze as serial
from analyze_clock_audit import clock_record
from analyze_native_serial_run import rows

def analyze(run):
    e=serial(run)
    records=[r for r in rows(run/'native-stderr.txt') if r.get('kind')=='darwin_iso_clock_audit']
    decoded=[]
    for r in records:
        try:decoded.append(clock_record(r))
        except (TypeError,ValueError,OverflowError):decoded.append(dict(valid=False,error='Invalid clock value type'))
    schedules=e['schedules'];attempts=e['attempts'];count=len(attempts)
    aligned=bool(count and len(decoded)==len(schedules)==count and e['callbacks']==count)
    if aligned:
        for i,(c,s,a) in enumerate(zip(decoded,schedules,attempts)):
            raw=c.get('raw',{})
            match=c['valid'] and raw.get('queried_frame')==s.get('queried_frame') and raw.get('start_frame')==s.get('frame_start')
            ordered=i==0 or (decoded[i-1].get('raw',{}).get('callback_ticks',float('inf'))<=raw.get('frame_before_ticks',0) and decoded[i-1].get('raw',{}).get('numer')==raw.get('numer') and decoded[i-1].get('raw',{}).get('denom')==raw.get('denom'))
            c.update(sequence=a['sequence'],schedule_matches=bool(match),serial_order_matches=bool(ordered))
        aligned=all(c['schedule_matches'] and c['serial_order_matches'] for c in decoded)
    e.update(host_revision='serial-clock-1',base_host_serial_passed=e['host_serial_passed'],clock_records=decoded,clock_audit_complete=aligned)
    e['host_serial_passed']=bool(e['host_serial_passed'] and aligned)
    e.update(strict_acceptance_passed=False,serial_acceptance_passed=False,root_cause_confirmed=False,stability_verified=False,switch_log_pending=True)
    return e

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path)
    print(json.dumps(analyze(parser.parse_args().run),indent=2))
