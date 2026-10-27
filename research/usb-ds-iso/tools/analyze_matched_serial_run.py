#!/usr/bin/env python3
"""Read-only matched serial analysis; full device log remains a separate gate."""
import argparse,json
from pathlib import Path
from analyze_native_serial_run import analyze as serial,rows

def analyze(run):
    e=serial(run);host=rows(run/'host.jsonl');native=rows(run/'native-stderr.txt')
    gates=[r for r in host if r.get('kind')=='serial_ring_gate']
    queues=[r for r in native if r.get('kind')=='darwin_iso_queue_timing']
    schedules=[r for r in native if r.get('kind')=='darwin_iso_schedule']
    attempts=e['attempts'];count=len(attempts)
    context=bool(count and all((a.get('diagnostics') or {}).get('context_snapshot',{}).get('valid') and a['diagnostics']['context_snapshot'].get('configured_fields_match') for a in attempts))
    gate_ok=bool(count and len(gates)==count and all(g.get('sequence')==a['sequence'] and g.get('passed') is True and g.get('slot')==(a['first_virtual_trb']&4095)//16 and g.get('cycle')==a['first_cycle'] for g,a in zip(gates,attempts)) and gates[-1].get('wraps')==e['observed_ring_wraps'])
    timing=bool(count and len(queues)==count and all(q.get('queue_result')==0 and q.get('clock')=='CLOCK_MONOTONIC' and q['frame_before_ns']<=q['frame_after_ns']<=q['queue_before_ns']<=q['queue_after_ns']<=q['callback_entry_ns'] for q in queues))
    schedule=bool(count and len(schedules)==count and all(all(q.get(k)==v for k,v in [('configured_lead_frames',64),('packets',960),('interval',1),('speed',3)]) for q in schedules))
    host_pass=bool(e['strict_acceptance_passed'] and context and gate_ok and timing and schedule and (run/'exit-code.txt').read_text().strip()=='0')
    failures=[a['sequence'] for a in attempts if not a['passed'] or not a['own_first_two_ED_tags_match_ring']]
    failures += [g['sequence'] for g in gates if not g.get('passed')]
    first_failure=min(failures) if failures else None
    trigger_rows=[r for r in host if r.get('kind')=='host_trigger_timing']
    e.update(host_revision='native-guard-serial-2',host_serial_passed=host_pass,
        strict_acceptance_passed=False,serial_acceptance_passed=False,context_verified=context,
        runtime_ring_gate_verified=gate_ok,timing_verified=timing,schedule_verified=schedule,
        runtime_ring_gates=gates,queue_timing=queues,schedules=schedules,
        first_failure_sequence=first_failure,no_submission_after_failure=first_failure is None or all(r['sequence']<=first_failure for r in trigger_rows))
    return e

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path)
    print(json.dumps(analyze(p.parse_args().run),indent=2))
