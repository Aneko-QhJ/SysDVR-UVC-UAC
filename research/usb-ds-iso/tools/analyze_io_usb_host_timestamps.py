#!/usr/bin/env python3
"""Measure saved AbsoluteTime observations; never approves a native or bus policy."""
import argparse
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path

from analyze_io_usb_host_evidence import ROW, integer, require
from analyze_io_usb_host_no_td import analyze as observation


def timestamp_summary(timestamps, numerator, denominator, submit, callback, frame):
    require(type(timestamps) is list and timestamps and
            all(integer(t,0,2**64-1) for t in timestamps), 'invalid timestamp list')
    require(integer(numerator,1,2**32-1) and integer(denominator,1,2**32-1), 'invalid timebase')
    require(all(integer(t,1,2**64-1) for t in (submit,callback,frame)), 'invalid boundaries')
    require(submit <= callback, 'callback before submit')

    def ns(ticks):
        value=Fraction(ticks*numerator,denominator)
        return dict(numerator=value.numerator,denominator=value.denominator,
                    floor=value.numerator//value.denominator)

    nonzero=[t for t in timestamps if t]
    deltas=[b-a for a,b in zip(timestamps,timestamps[1:]) if a and b]
    run_lengths=[]
    for index,t in enumerate(timestamps):
        if not t:continue
        if index and timestamps[index-1]==t:run_lengths[-1]+=1
        else:run_lengths.append(1)
    return dict(count=len(timestamps),zero_count=len(timestamps)-len(nonzero),
                duplicate_nonzero_count=len(nonzero)-len(set(nonzero)),
                distinct_nonzero_timestamps=len(set(nonzero)),
                nonzero_run_length_counts=dict(sorted(Counter(run_lengths).items())),
                adjacent_comparable_count=len(deltas),backward_pairs=sum(d<0 for d in deltas),
                minimum_ticks=min(nonzero) if nonzero else None,
                maximum_ticks=max(nonzero) if nonzero else None,
                span_ns=ns(max(nonzero)-min(nonzero)) if nonzero else None,
                adjacent_min_ns=ns(min(deltas)) if deltas else None,
                adjacent_max_ns=ns(max(deltas)) if deltas else None,
                adjacent_mean_ns=ns(Fraction(sum(deltas),len(deltas))) if deltas else None,
                before_submit_count=sum(t<submit for t in nonzero),
                after_callback_count=sum(t>callback for t in nonzero),
                first_from_frame_ns=ns(nonzero[0]-frame) if nonzero else None,
                callback_from_last_ns=ns(callback-nonzero[-1]) if nonzero else None,
                submit_to_callback_ns=ns(callback-submit),
                interpretation='observed_completion_times_not_bus_service_times',
                timestamps_required_unique=False,bus_phase_verified=False,
                callback_drain_verified=False,baseline_accepted=False,allow_next_burst=False)


def analyze(root):
    root=Path(root)
    bound=observation(root,hardware=True)
    require(bound['observation_complete'], 'incomplete no-TD observation')
    metadata=json.loads((root/'transfer/metadata.json').read_bytes())
    rows=list(ROW.iter_unpack((root/'transfer/transactions.bin').read_bytes()))
    frame=bound['software_frame_sample']
    result=timestamp_summary([r[4] for r in rows],frame['timebase_numerator'],frame['timebase_denominator'],
                             metadata['submit_begin_ticks'],metadata['callback_arrival_ticks'],frame['frame_time'])
    result.update(schema='A23-saved-AbsoluteTime-analysis-1',
                  collection_manifest_sha256=bound['collection_manifest_sha256'],
                  timebase_numerator=frame['timebase_numerator'],timebase_denominator=frame['timebase_denominator'],
                  status_counts=bound['empty_status_counts'],native_overall_u32=bound['native_overall_u32'],
                  complete_counts_all_zero=all(r[3]==0 for r in rows),hardware_verified=False,usb_strict_pass=False)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('collection',type=Path)
    args=parser.parse_args()
    try:result=analyze(args.collection)
    except (OSError,ValueError,KeyError,TypeError,UnicodeError) as error:
        print(json.dumps(dict(error=str(error),baseline_accepted=False,allow_next_burst=False)));return 2
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
