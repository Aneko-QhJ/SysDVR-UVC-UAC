#!/usr/bin/env python3
"""Read-only strict single-burst classifier; serial and stability stay false."""
import argparse,json
from pathlib import Path
from analyze_native_serial_run import analyze as analyze_serial,rows

def analyze(run):
    serial=analyze_serial(run);backend=rows(run/'native-stderr.txt')
    queues=[r for r in backend if r.get('kind')=='darwin_iso_queue_timing']
    schedules=[r for r in backend if r.get('kind')=='darwin_iso_schedule']
    attempt=serial['attempts'][0] if len(serial['attempts'])==1 else {}
    timing_ok=len(queues)==1 and queues[0]['queue_result']==0 and queues[0]['clock']=='CLOCK_MONOTONIC'
    if timing_ok:
        q=queues[0];timing_ok=q['frame_before_ns']<=q['frame_after_ns']<=q['queue_before_ns']<=q['queue_after_ns']<=q['callback_entry_ns']
    schedule_ok=len(schedules)==1 and all(schedules[0][k]==v for k,v in [('configured_lead_frames',64),('packets',960),('interval',1),('speed',3)])
    context=attempt.get('diagnostics',{}).get('context_snapshot',{})
    passed=bool(serial['target']==1 and serial['triggers']==serial['callbacks']==1 and
        attempt.get('passed') and attempt.get('own_first_two_ED_tags_match_ring') and
        context.get('valid') and context.get('configured_fields_match') and timing_ok and schedule_ok)
    return dict(device_revision='A23',host_revision='burst-window-1',target=1,attempts=serial['attempts'],
        triggers=serial['triggers'],callbacks=serial['callbacks'],host_single_burst_passed=passed,
        timing_verified=timing_ok,schedule_verified=schedule_ok,queue_timing=queues,schedule=schedules,
        no_submission_after_failure=serial['no_submission_after_failure'],switch_log_pending=True,
        strict_single_acceptance_passed=False,serial_acceptance_passed=False,root_cause_confirmed=False,stability_verified=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run',type=Path)
    print(json.dumps(analyze(parser.parse_args().run),indent=2))
