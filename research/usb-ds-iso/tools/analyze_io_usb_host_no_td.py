#!/usr/bin/env python3
"""Audit no-TD observations in their declared log format; native policy stays unverified."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

from analyze_io_usb_host_collection import analyze as analyze_collection
from analyze_io_usb_host_evidence import analyze as analyze_bundle, require, unique_object, ROW


def control_trace(log, *, hardware=False):
    """Audit a declared log format; interface labels are not request IDs.

    A23 logs ignored SetupEvent deliveries on VC/VS, but not the ISO owner.
    Require two complete, adjacent 0/1 delivery pairs; never deduplicate text.
    This checks software dispatch shape, not the number of bus transactions.
    """
    vendor = []
    malformed = []
    positions = []
    lines = log.decode('utf-8',errors='strict').splitlines()
    packets = {}
    ignored = []
    for position,line in enumerate(lines):
        if not line.startswith('EP0['):
            continue
        ignore = re.fullmatch(r'EP0\[(\d+)\]: wIndex mismatch, ignoring',line)
        if hardware and ignore:
            ignored.append((position,int(ignore[1])))
            continue
        match = re.fullmatch(r'EP0\[(\d+)\]: reqType=0x([0-9a-f]+) req=0x([0-9a-f]+) wVal=0x([0-9a-f]+) wIdx=0x([0-9a-f]+) wLen=(\d+)',line)
        if not match:
            malformed.append(line)
            continue
        entry = [int(match[1])] + [int(match[i],16) for i in range(2,6)] + [int(match[6])]
        packets[position] = entry
        if entry[1] & 0x60 == 0x40:
            vendor.append(entry)
            positions.append(position)
    expected = [0xc1,0x51,0,2,168]
    correct = (not malformed and len(vendor) == 2 and all(v[1:] == expected for v in vendor) and vendor[0][0] < vendor[1][0])
    if hardware:
        # Ignore markers must belong to the immediately preceding wrong-owner
        # interface request, including any standard requests elsewhere in log.
        ignored_bound = all(p-1 in packets and packets[p-1][0] == interface and
                            packets[p-1][1] & 0x1f == 1 and
                            packets[p-1][4] & 0xff != interface for p,interface in ignored)
        correct = bool(not malformed and ignored_bound and len(vendor) == 4 and
                       all(v[1:] == expected for v in vendor) and
                       [v[0] for v in vendor] == [0,1,0,1] and
                       positions == list(range(positions[0],positions[0]+8,2)) and
                       all(lines[p+1:p+2] == [f'EP0[{v[0]}]: wIndex mismatch, ignoring']
                           for p,v in zip(positions,vendor)))
    return {"vendor_records":vendor,"malformed_records":malformed,"matches_fixed_plan":bool(correct),
            "log_format":'A23-interface-dispatch' if hardware else 'mock-request-sequence',
            "inferred_status_requests":2 if correct else None,
            "request_count_verified":False,
            "bus_capture_verified":False}


def status_spans(rows):
    spans = []
    for index,row in enumerate(rows):
        if row[3] != 0:
            continue
        value = f'0x{row[0]:08x}'
        if spans and spans[-1]['status_u32_hex'] == value and spans[-1]['last_index']+1 == index:
            spans[-1]['last_index'] = index; spans[-1]['count'] += 1
        else:
            spans.append(dict(first_index=index,last_index=index,count=1,status_u32_hex=value))
    return spans


def analyze(root, *, hardware=False):
    root = Path(root)
    collection = analyze_collection(root,hardware=hardware)
    native_meta = json.loads((root/'transfer/metadata.json').read_bytes(),object_pairs_hook=unique_object)
    require(native_meta['scenario'] == {'kind':'no_td'}, 'not a no-TD observation')
    require(collection['session']['probe_plan_bound'] and collection['session']['frame_sample_bound'],
            'no fixed plan/frame binding; legacy observation cannot supply a new baseline')
    native = analyze_bundle(root/'transfer',hardware=hardware)
    journal = [json.loads(line,object_pairs_hook=unique_object) for line in (root/'session.jsonl').read_bytes().splitlines()]
    frame = next(r['details'] for r in journal if r['event']=='frame_sample')
    rows = list(ROW.iter_unpack((root/'transfer/transactions.bin').read_bytes()))
    counts = Counter(f'0x{r[0]:08x}' for r in rows if r[3] == 0)
    spans = status_spans(rows)
    trace = control_trace((root/'device-log.txt').read_bytes(),hardware=hardware)
    failures = list(collection['session']['stop_reasons'])
    if not native['payload_matches']: failures.append('nonempty_window')
    if not native['transactions_finalized']: failures.append('unfinished_transactions')
    if not native['callback_clean']: failures.append('native_completion_not_clean')
    if not collection['simulation_collection_pass']: failures.append('collection_observation_failed')
    if not trace['matches_fixed_plan']: failures.append('control_trace_does_not_match_plan')
    complete = bool(collection['simulation_collection_pass'] and trace['matches_fixed_plan'])
    return {"schema":"A23-no-td-observation-analysis-1","execution_mode":'hardware' if hardware else "simulation",
            "collection_manifest_sha256":collection['collection_manifest_sha256'],"session_id":collection['session_id'],
            "observation_complete":complete,"failure_reasons":list(dict.fromkeys(failures)),
            "transaction_count":len(rows),"empty_count":sum(counts.values()),"active_indices":native['active_indices'],
            "empty_status_counts":dict(sorted(counts.items())),"empty_status_spans":spans,
            "initial_empty_span":spans[0] if spans and spans[0]['first_index'] == 0 else None,
            "native_overall_u32":native['overall_u32'],"raw_zero":(root/'transfer/raw.bin').read_bytes() == bytes(184320),
            "planned_first_frame":frame['first_frame'],"software_frame_sample":frame,
            "frame_query_duration_ticks":frame['end_ticks']-frame['begin_ticks'],
            "frame_end_to_native_submit_ticks":native_meta['submit_begin_ticks']-frame['end_ticks'],
            "native_submit_elapsed_ticks":native_meta['submit_return_ticks']-native_meta['submit_begin_ticks'],
            "software_frame_freshness_verified":False,
            "frame_timebase_converted":bool(collection['session']['admission'] and collection['session']['admission']['converted']),
            "runtime_budget_bound":collection['session']['runtime_budget_bound'],
            "software_budget_verified":collection['session']['software_budget_verified'],
            "admission":collection['session']['admission'],
            "exit_requested":collection['session']['exit_requested'],
            "exit_wait_expired":collection['session']['exit_wait_expired'],
            "control_trace":trace,"status_header_unchanged":bool(collection['device'] and
                collection['device']['device_status_and_log_relation_matches']),
            "empty_native_policy":"unverified","empty_status_policy_verified":False,
            "baseline_accepted":False,"allow_next_burst":False,"hardware_entry_enabled":False,
            "hardware_verified":False,"callback_drain_verified":False,"usb_strict_pass":False,
            "bus_phase_verified":False,"root_cause_confirmed":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('collection',type=Path); args=parser.parse_args()
    try:
        result = analyze(args.collection)
    except (ValueError,OSError,TypeError,KeyError,UnicodeError) as error:
        print(json.dumps(dict(observation_complete=False,baseline_accepted=False,allow_next_burst=False,
                             hardware_verified=False,usb_strict_pass=False,error=str(error)),indent=2))
        return 2
    print(json.dumps(result,indent=2))
    return 0 if result['observation_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
