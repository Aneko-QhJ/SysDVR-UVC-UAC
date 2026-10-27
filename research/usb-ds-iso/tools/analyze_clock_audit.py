#!/usr/bin/env python3
"""Read-only one-burst clock audit; estimates have 1 ms API uncertainty."""
import json,argparse
from pathlib import Path
from analyze_burst_window import analyze as burst
from analyze_native_serial_run import rows

def clock_record(r):
 required=['at_time_ticks','frame_before_ticks','frame_after_ticks','queue_before_ticks','queue_after_ticks','callback_ticks','queried_frame','start_frame','numer','denom','frame_result','clock']
 if not all(k in r for k in required):return dict(valid=False,error='Missing clock field')
 if r['numer']<=0 or r['denom']<=0:return dict(valid=False,error='Invalid timebase')
 scale=r['numer']/r['denom'];at=r['at_time_ticks']*scale
 stamps=[r[k]*scale for k in ['frame_before_ticks','frame_after_ticks','queue_before_ticks','queue_after_ticks','callback_ticks']]
 ordered=stamps==sorted(stamps) and stamps[0]>0
 timestamp_compatible=stamps[0]-1e6<=at<=stamps[1]+1e6 and at>0
 lead=r['start_frame']-r['queried_frame'];estimate=at+lead*1e6
 valid=bool(ordered and timestamp_compatible and r['frame_result']==0 and r['clock']=='mach_absolute_time' and lead==64)
 return dict(valid=valid,raw=r,ordered=ordered,at_time_compatible_with_1ms_API_bound=timestamp_compatible,
  lead_frames=lead,estimated_start_minus_queue_before_ms=(estimate-stamps[2])/1e6,
  estimated_start_minus_queue_after_ms=(estimate-stamps[3])/1e6,estimate_uncertainty_ms=1,
  kernel_enqueue_time_known=False,wire_service_time_verified=False)

def analyze(run):
 e=burst(run);raw=[r for r in rows(run/'native-stderr.txt') if r.get('kind')=='darwin_iso_clock_audit'];decoded=[clock_record(r) for r in raw]
 valid=len(decoded)==1 and decoded[0]['valid']
 e.update(host_revision='clock-audit-1',base_host_single_burst_passed=e['host_single_burst_passed'],clock_records=decoded,clock_audit_complete=bool(valid))
 e['host_single_burst_passed']=bool(e['host_single_burst_passed'] and valid)
 return e
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('run',type=Path);print(json.dumps(analyze(p.parse_args().run),indent=2))
