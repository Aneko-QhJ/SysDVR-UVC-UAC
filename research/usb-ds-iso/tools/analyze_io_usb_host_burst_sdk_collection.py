#!/usr/bin/env python3
"""Freeze/audit supplied SDK burst artifacts offline; no acquisition or approval."""
import argparse
import base64
from collections import Counter
import json
from pathlib import Path

from analyze_io_usb_host_evidence import ROW, integer, require, unique_object
from analyze_io_usb_host_collection import read_file, sha, durable_write, sync_dir
from analyze_io_usb_host_burst_sdk import analyze as audit_host, checkpoint
from analyze_io_usb_host_burst_collection import control_trace
from audit_io_usb_host_device import audit as audit_device
from io_usb_host_runtime_policy import duration_ns

ORIGINS = ('injected_sdk_fixture', 'supplied_sdk_artifacts_unverified')
POLICY = ('hardware_entry_enabled', 'hardware_verified', 'usb_strict_pass', 'baseline_accepted',
          'allow_next_burst', 'callback_drain_verified', 'firmware_bytes_verified',
          'bus_phase_verified', 'cross_clock_alignment_verified', 'hardware_trigger_binding_verified',
          'device_log_bound', 'capture_binding_verified', 'empty_status_policy_verified')
HOST_POLICY = ('hardware_entry_enabled','hardware_verified','usb_strict_pass','baseline_accepted',
               'allow_next_burst','callback_drain_verified')
BASE_LIMITS = {
    'host/session.jsonl':128*4096,
    'host/transfer/raw.bin':184320, 'host/transfer/transactions.bin':26880,
    'host/transfer/metadata.json':16384, 'host/transfer/SHA256SUMS':1024, 'host/transfer/COMMITTED':65,
    'host/final/checkpoint.json':16384, 'host/final/SHA256SUMS':1024, 'host/final/COMMITTED':65,
    'status-before.bin':2048, 'status-after.bin':2048, 'device-log.txt':1024*1024,
    'collection.json':8192, 'ORIGIN.txt':512,
}
FIXTURE_LIMITS = {'host/MOCK_ONLY.txt':512, 'host/fixture-calls.json':16384, 'host/result.json':16384}
RETAINED_LIMITS = {'host/retained/checkpoint.json':16384, 'host/retained/SHA256SUMS':1024, 'host/retained/COMMITTED':65}
ORIGIN_TEXT = {
    'injected_sdk_fixture':b'Injected SDK host fixture and supplied synthetic A23 log. No hardware provenance or capture permission.\n',
    'supplied_sdk_artifacts_unverified':b'Supplied SDK host artifacts and device log; origin and capture association unverified. No capture permission.\n',
}


def load(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def limits_for(origin, has_retained):
    require(origin in ORIGINS and type(has_retained) is bool, 'invalid origin/checkpoint declaration')
    limits = dict(BASE_LIMITS)
    if origin == 'injected_sdk_fixture':limits.update(FIXTURE_LIMITS)
    if has_retained:limits.update(RETAINED_LIMITS)
    return limits


def host_layout(host, origin, has_retained):
    names = {'session.jsonl', 'transfer', 'final'}
    if has_retained:names.add('retained')
    if origin == 'injected_sdk_fixture':names.update({'MOCK_ONLY.txt','fixture-calls.json','result.json'})
    require(host.is_dir() and not host.is_symlink() and {p.name for p in host.iterdir()} == names,
            'missing/extra or relabeled host source files')
    for name, expected in [('transfer',{'raw.bin','transactions.bin','metadata.json','SHA256SUMS','COMMITTED'}),
                           ('final',{'checkpoint.json','SHA256SUMS','COMMITTED'}),
                           *([('retained',{'checkpoint.json','SHA256SUMS','COMMITTED'})] if has_retained else [])]:
        directory = host/name
        require(directory.is_dir() and not directory.is_symlink() and {p.name for p in directory.iterdir()} == expected,
                'missing/extra or symlinked '+name+' files')


def replies(journal):
    result = {}
    for line in journal.splitlines():
        row = load(line)
        if row.get('event') != 'adapter':continue
        event = row['details']
        if event.get('event') not in ('status_before','status_after'):continue
        require(event.get('schema') == 'A23-burst-sdk-adapter-event-1' and
                event.get('backend_role') == 'sdk_capability_adapter', 'STATUS not from SDK adapter record')
        phase = event['event'].split('_')[1];detail = event['details']
        require(phase not in result and detail['observation'].get('source') == 'sdk_control_reply',
                'duplicate/wrong-source STATUS phase')
        raw = base64.b64decode(detail['raw_base64'],validate=True)
        require(len(raw) <= 2048 and base64.b64encode(raw).decode() == detail['raw_base64'] and
                sha(raw) == detail['sha256'], 'STATUS byte/hash mismatch')
        result[phase] = raw
    require(set(result) == {'before','after'}, 'collection needs both original SDK STATUS replies')
    return result


def metadata(files, origin, has_retained):
    core = load(files['host/transfer/metadata.json'])
    return dict(schema='A23-burst-sdk-collection-1', backend='iousbhost-single-burst-1',
        execution_mode='hardware', artifact_origin=origin, has_retained_checkpoint=has_retained,
        injected_fixture=origin == 'injected_sdk_fixture',
        status_source='journal_raw_sdk_reply',
        device_log_source='supplied_synthetic_A23_log' if origin == 'injected_sdk_fixture' else 'supplied_device_log_unverified',
        log_format='A23-interface-dispatch', scenario=dict(kind='single_burst',first_sequence=1),
        binding=core['binding'], first_frame=core['first_frame'], expected_runtime_record=21,
        journal_sha256=sha(files['host/session.jsonl']),
        transfer_manifest_sha256=sha(files['host/transfer/SHA256SUMS']),
        final_checkpoint_manifest_sha256=sha(files['host/final/SHA256SUMS']),
        retained_checkpoint_manifest_sha256=sha(files['host/retained/SHA256SUMS']) if has_retained else None,
        before_sha256=sha(files['status-before.bin']), after_sha256=sha(files['status-after.bin']),
        device_log_sha256=sha(files['device-log.txt']),
        host_origin_verified=False, device_log_origin_verified=False, **{k:False for k in POLICY})


def validate_history(host, final, has_retained):
    require(final['retained_checkpoint_saved'] is has_retained, 'missing/invented retained checkpoint history')
    rows = [load(s) for s in read_file(host/'session.jsonl',128*4096).splitlines()]
    final_events = [r for r in rows if r['event'] == 'final_checkpoint']
    require(len(final_events) == 1 and final_events[0]['details'].get('saved') is True and
            final.get('final_checkpoint_saved') is False, 'final checkpoint lacks successful durable acknowledgment')
    if not has_retained:return
    retained = checkpoint(host/'retained')
    require(retained.get('schema') == 'A23-burst-sdk-checkpoint-1' and retained.get('binding') == final['binding'] and
            retained.get('backend') == 'iousbhost-single-burst-1' and retained.get('unresolved') is True and
            retained.get('finished') is False and retained.get('exit_requested') is True and
            retained['transport'].get('closed') is False and integer(retained.get('ticks'),1,final['ticks']) and
            retained.get('journal_failed') is False and retained.get('retained_checkpoint_saved') is False and
            retained.get('final_checkpoint_saved') is False and integer(retained.get('exit_code'),1,1) and final['exit_code'] == 1 and
            all(retained.get(k) is False for k in HOST_POLICY) and
            all(retained['transport'].get(k) is False for k in HOST_POLICY if k != 'usb_strict_pass'), 'invalid retained/final binding')
    for previous,later in [(retained.get('failure_reasons'),final['failure_reasons']),
                            (retained['transport'].get('failure_reasons'),final['transport']['failure_reasons'])]:
        require(type(previous) is list and all(type(s) is str for s in previous) and
                previous == later[:len(previous)], 'final erased retained failure history')
    for key in ['submitted_at_ticks','trigger_start_ticks','exit_at_ticks']:
        require(integer(retained.get(key),final[key],final[key]), 'retained coordinator clock differs from final')
    prepared = rows[0]['details']
    elapsed = duration_ns(retained['exit_at_ticks'],retained['ticks'],prepared['timebase_numerator'],prepared['timebase_denominator'])
    require(elapsed is not None and elapsed >= 1000000000, 'retained checkpoint before exit wait expired')
    events = [r for r in rows if r['event'] == 'retained_checkpoint']
    require(len(events) == 1 and events[0]['details'].get('saved') is True and
            retained['ticks'] <= events[0]['ticks'] <= final['ticks'] and events[0]['index'] < final_events[0]['index'],
            'unbound retained checkpoint acknowledgment')
    for key in ['iso_attempts','trigger_attempts','host_aborts','iso_callbacks','control_callbacks','after_reads']:
        require(integer(retained['transport'].get(key),0,final['transport'][key]), 'retained counter exceeds final')
    for key in ['core_saved','save_attempted']:
        require(type(retained.get(key)) is bool and (retained[key] is False or final[key] is True), 'final lost committed core')
    for key in ['closed','iso_accepted','control_pending','storage_retained','detached','journal_failed']:
        require(type(retained['transport'].get(key)) is bool, 'invalid retained transport flag')


def validate_fixture(files, final):
    marker = files['host/MOCK_ONLY.txt']
    require(b'injection' in marker and b'0' in marker, 'missing injection marker')
    calls = load(files['host/fixture-calls.json']);last = load(files['host/result.json'])
    require(calls.get('execution_mode') == 'simulation' and calls.get('injected_only') is True and
            all(integer(calls.get(k),0,0) for k in ['real_sdk_calls','registry_calls','usb_requests','sd_accesses']),
            'fixture provenance contradicts injection')
    require(last.get('schema') == final['schema'] and last.get('binding') == final['binding'] and
            last.get('final_checkpoint_saved') is True and last.get('transport') == final['transport'] and
            last.get('failure_reasons') == final['failure_reasons'] and last.get('exit_code') == final['exit_code'] and
            last.get('core_saved') is True and last.get('finished') is True and last.get('unresolved') is False and
            last.get('journal_failed') is False and all(last.get(k) is False for k in HOST_POLICY),
            'fixture result contradicts final checkpoint')
    t = final['transport']
    for key, count in [('iso_submissions',t['iso_attempts']),('burst_enqueues',t['trigger_attempts']),
                       ('host_aborts',t['host_aborts']),('status_reads',2),('destroys',1),('releases',1)]:
        require(integer(calls.get(key),count,count), 'fixture counter mismatch: '+key)


def native_candidate(files, native):
    rows = list(ROW.iter_unpack(files['host/transfer/transactions.bin']))
    empty = Counter(f'0x{r[0]:08x}' for r in rows if r[3] == 0)
    empty_match = len(rows)-len(native['active_indices']) == 944 and empty == {'0x00000000':944}
    return dict(payload_matches=native['payload_matches'], active_native_clean=native['active_native_clean'],
        callback_clean=native['callback_clean'], transactions_finalized=native['transactions_finalized'],
        active_indices=native['active_indices'], empty_status_counts=dict(sorted(empty.items())),
        empty_matches_saved_zero_observation=empty_match,
        candidate_rule_matches=native['host_transaction_candidate'] and empty_match,
        timestamp_nonzero_count=sum(r[4] > 0 for r in rows), timestamp_unique_count=len({r[4] for r in rows}),
        empty_status_policy_verified=False, bus_phase_verified=False)


def analyze(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink() and {p.name for p in root.iterdir()} ==
            {'host','status-before.bin','status-after.bin','device-log.txt','collection.json','ORIGIN.txt','SHA256SUMS','COMMITTED'},
            'missing/extra or symlinked collection files')
    meta = load(read_file(root/'collection.json',8192))
    require(type(meta) is dict, 'invalid collection metadata')
    origin, has_retained = meta.get('artifact_origin'), meta.get('has_retained_checkpoint')
    limits = limits_for(origin,has_retained);host = root/'host'
    host_layout(host,origin,has_retained)
    files = {name:read_file(root/name,maximum) for name,maximum in limits.items()}
    manifest = read_file(root/'SHA256SUMS',8192)
    require(manifest == ''.join(f'{sha(files[k])}  {k}\n' for k in sorted(files)).encode() and
            read_file(root/'COMMITTED',65) == (sha(manifest)+'\n').encode(), 'collection manifest/commit mismatch')
    require(json.dumps(meta,sort_keys=True) == json.dumps(metadata(files,origin,has_retained),sort_keys=True) and
            files['ORIGIN.txt'] == ORIGIN_TEXT[origin], 'collection source/binding/hash/policy mismatch')
    checked = audit_host(host);final = checkpoint(host/'final')
    require(checked['host_binding_verified'] and checked['checkpoint'] == 'final' and final['core_saved'] and
            final['finished'] and not final['unresolved'] and final['transport']['closed'], 'host lacks complete committed ownership history')
    validate_history(host,final,has_retained)
    if origin == 'injected_sdk_fixture':validate_fixture(files,final)
    original = replies(files['host/session.jsonl'])
    require(original['before'] == files['status-before.bin'] and original['after'] == files['status-after.bin'],
            'STATUS differs from original SDK journal bytes')
    require(load(files['host/transfer/metadata.json'])['scenario'] == meta['scenario'], 'scenario mismatch')
    device = trace = None;device_error = trace_error = None
    try:device = audit_device(original['before'],original['after'],files['device-log.txt'],'single_burst',1)
    except (ValueError,UnicodeError) as e:device_error = str(e)
    try:trace = control_trace(files['device-log.txt'])
    except (ValueError,UnicodeError) as e:trace_error = str(e)
    device_match = bool(device and device['device_status_and_log_relation_matches'])
    trace_match = bool(trace and trace['matches_fixed_plan'])
    record_match = bool(device and device['runtime_record'] == meta['expected_runtime_record'])
    report_match = bool(device and device['after_status']['report_count'] in (0,1))
    candidate = native_candidate(files,checked['core'])
    complete = bool(checked['host_observation_complete'] and candidate['candidate_rule_matches'] and
                    device_match and trace_match and record_match and report_match)
    failures = [reason for good,reason in [(checked['host_observation_complete'],'host_observation_failed'),
        (candidate['candidate_rule_matches'],'native_candidate_failed'),(device_match,'device_relation_failed'),
        (trace_match,'control_dispatch_failed'),(record_match,'runtime_record_mismatch'),(report_match,'report_count_invalid')] if not good]
    return dict(schema='A23-burst-sdk-collection-analysis-1',backend='iousbhost-single-burst-1',execution_mode='hardware',
        artifact_origin=origin,injected_fixture=origin == 'injected_sdk_fixture',
        collection_integrity_verified=True,collection_manifest_sha256=sha(manifest),
        sdk_status_byte_binding_verified=True,device_log_byte_binding_verified=True,
        supplied_device_relation_matches=device_match and trace_match and record_match and report_match,
        supplied_artifact_relation_complete=complete,failure_reasons=failures,host=checked,native_candidate=candidate,
        device=device,device_error=device_error,control_trace=trace,control_trace_error=trace_error,
        host_origin_verified=False,device_log_origin_verified=False, **{k:False for k in POLICY})


def freeze(host, device_log, output, *, origin):
    """Supplied quiescent files only. No USB, card read, receipt or policy mutation."""
    host, device_log, output = map(Path,(host,device_log,output))
    has_retained = (host/'retained').exists()
    limits = limits_for(origin,has_retained)
    host_layout(host,origin,has_retained)
    paths = {k:v for k,v in limits.items() if k.startswith('host/')}
    files = {k:read_file(host/k.removeprefix('host/'),v) for k,v in paths.items()}
    checked = audit_host(host);final = checkpoint(host/'final')
    require(checked['host_binding_verified'] and checked['core'] and checked['checkpoint'] == 'final' and
            final['finished'] and final['core_saved'] and final['transport']['closed'] and
            not final['unresolved'], 'incomplete host cannot acquire a collection')
    validate_history(host,final,has_retained)
    if origin == 'injected_sdk_fixture':validate_fixture(files,final)
    original = replies(files['host/session.jsonl'])
    require(sha(files['host/session.jsonl']) == checked['journal_sha256'], 'host journal changed while freezing')
    for name,maximum in paths.items():
        require(files[name] == read_file(host/name.removeprefix('host/'),maximum), 'host changed while freezing: '+name)
    files.update({'status-before.bin':original['before'],'status-after.bin':original['after'],
        'device-log.txt':read_file(device_log,limits['device-log.txt']),'ORIGIN.txt':ORIGIN_TEXT[origin]})
    files['collection.json'] = (json.dumps(metadata(files,origin,has_retained),sort_keys=True,indent=2)+'\n').encode()
    output.mkdir(mode=0o700);(output/'host').mkdir(mode=0o700)
    for name in ['transfer','final',*(['retained'] if has_retained else [])]:(output/'host'/name).mkdir(mode=0o700)
    for name in sorted(files):durable_write(output/name,files[name])
    # Validate copied host before outer commit. A copied partial/mismatched
    # core never receives a collection commit marker.
    audit_host(output/'host')
    for name,raw in files.items():
        require(read_file(output/name,limits[name]) == raw, 'copied file differs before collection commit: '+name)
    manifest = ''.join(f'{sha(files[k])}  {k}\n' for k in sorted(files)).encode()
    durable_write(output/'SHA256SUMS',manifest)
    for directory in [output/'host/transfer',output/'host/final',*([output/'host/retained'] if has_retained else []),output/'host',output]:sync_dir(directory)
    durable_write(output/'COMMITTED',(sha(manifest)+'\n').encode());sync_dir(output);sync_dir(output.parent)
    return analyze(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__);sub = parser.add_subparsers(dest='command',required=True)
    check = sub.add_parser('audit');check.add_argument('collection',type=Path)
    make = sub.add_parser('freeze');make.add_argument('host',type=Path);make.add_argument('device_log',type=Path);make.add_argument('output',type=Path)
    make.add_argument('--origin',choices=ORIGINS,required=True)
    args = parser.parse_args()
    try:result = analyze(args.collection) if args.command == 'audit' else freeze(args.host,args.device_log,args.output,origin=args.origin)
    except (ValueError,OSError,TypeError,KeyError,UnicodeError) as error:
        print(json.dumps(dict(error=str(error),collection_integrity_verified=False,hardware_verified=False,allow_next_burst=False)));return 2
    print(json.dumps(result,indent=2));return 0 if result['supplied_artifact_relation_complete'] else 1


if __name__ == '__main__':raise SystemExit(main())
