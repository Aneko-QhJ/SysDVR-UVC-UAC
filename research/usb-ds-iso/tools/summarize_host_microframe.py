#!/usr/bin/env python3
"""Summarize raw host query observations, retaining failures and uncertainty."""
import argparse,json
from pathlib import Path

def summarize(text):
    rows=[]
    for line in text.splitlines():
        if line.startswith('{'):
            try:row=json.loads(line)
            except json.JSONDecodeError:continue
            if row.get('kind')=='darwin_microframe_observation':rows.append(row)
    stages=['iso_before_queue','iso_after_queue','burst_before_queue','burst_after_queue']
    usable=[]
    for row in rows:
        item=dict(row)
        valid=row.get('valid') is True and row.get('result')==0
        bracket=row.get('after_ticks',-1)>=row.get('before_ticks',0) and row.get('timebase_denom',0)>0
        item['usable']=valid and bracket
        if bracket:item['query_duration_ns']=(row['after_ticks']-row['before_ticks'])*row['timebase_numer']/row['timebase_denom']
        if item['usable']:item['reported_microframe_phase']=row['microframe']%8
        usable.append(item)
    return dict(expected_stages=stages,observed_count=len(rows),complete_stage_order=[r.get('stage') for r in rows]==stages,
        all_queries_usable=len(usable)==4 and all(r['usable'] for r in usable),observations=usable,
        SDK_timestamp_accuracy_ms=1,wire_time_verified=False,clock_sync_verified=False,root_cause_confirmed=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path);args=parser.parse_args()
    result=summarize((args.run/'native-stderr.txt').read_text())
    path=args.run/'host-microframe-evidence.json';path.write_text(json.dumps(result,indent=2)+'\n');print(path)
if __name__=='__main__':main()
