from a23_sequence_binding import FIRST
#!/usr/bin/env python3
"""Offline SDK burst host binding audit. Integrity is not hardware provenance."""
import argparse
import base64
import hashlib
import json
import uuid
from pathlib import Path
from analyze_io_usb_host_sequence_evidence import analyze as core_audit, integer, require, unique_object
from analyze_io_usb_host_session import status_reply
from io_usb_host_lead32_policy import audit_admission, duration_ns
from audit_io_usb_host_device import decode_status

POLICY = ('hardware_entry_enabled', 'hardware_verified', 'baseline_accepted',
          'allow_next_burst', 'callback_drain_verified', 'usb_strict_pass')
ADAPTER_EVENTS = {'status_before', 'frame_sample', 'iso_intent', 'iso_return', 'trigger_intent',
                  'trigger_return', 'iso_callback', 'iso_snapshot', 'control_callback', 'after_intent',
                  'status_after', 'abort_intent', 'abort_return', 'close_intent', 'closed', 'stop'}
EVENTS = {'prepared', 'before_intent', 'frame_intent', 'adapter', 'stop', 'exit_requested',
          'save_intent', 'save_result', 'closed_observed', 'retained_checkpoint', 'final_checkpoint'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_plain(path, maximum):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= maximum,
            f'invalid/oversized file: {path.name}')
    return path.read_bytes()


def load(path):
    return json.loads(read_plain(path, 16384), object_pairs_hook=unique_object)


def checkpoint(path):
    require(path.is_dir() and not path.is_symlink() and
            {p.name for p in path.iterdir()} == {'checkpoint.json', 'SHA256SUMS', 'COMMITTED'}, 'incomplete checkpoint')
    raw = read_plain(path/'checkpoint.json', 16384)
    sums = read_plain(path/'SHA256SUMS', 1024)
    require(sums == f'{digest(raw)}  checkpoint.json\n'.encode() and
            read_plain(path/'COMMITTED', 65) == (digest(sums)+'\n').encode(), 'checkpoint hash/commit mismatch')
    return json.loads(raw, object_pairs_hook=unique_object)


def analyze(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'invalid host observation directory')
    raw = read_plain(root/'session.jsonl', 128*4096)
    lines = raw.splitlines()
    require(raw.endswith(b'\n') and 0 < len(lines) <= 128 and all(len(s) <= 4095 for s in lines), 'partial/oversized journal')
    rows = [json.loads(s, object_pairs_hook=unique_object) for s in lines]
    by = {k: [] for k in EVENTS | ADAPTER_EVENTS}
    previous = adapter_index = 0
    binding = rows[0].get('details', {}).get('binding')
    require(type(binding) is dict and set(binding) == {'session_id', 'identity', 'descriptor_sha256'} and
            type(binding['session_id']) is str and str(uuid.UUID(binding['session_id'])).upper() == binding['session_id'].upper(), 'missing/invalid prepared binding')
    identity = binding['identity']
    require(type(identity) is dict and len(identity) == 3 and all(integer(identity.get(k), 1) for k in ('device_id', 'interface_id', 'parent_device_id')) and
            identity['device_id'] == identity['parent_device_id'] and identity['device_id'] != identity['interface_id'], 'invalid registry relationship')
    for index, row in enumerate(rows, 1):
        require(type(row) is dict and row.get('schema') == 'A23-burst-sdk-session-event-1' and
                row.get('backend') == 'iousbhost-single-burst-1' and row.get('session_id') == binding.get('session_id') and
                integer(row.get('index'), index, index) and integer(row.get('ticks'), max(1, previous)) and
                row.get('hardware_verified') is False and row.get('hardware_entry_enabled') is False and
                row.get('event') in EVENTS and type(row.get('details')) is dict, 'invalid session record')
        previous = row['ticks']
        by[row['event']].append(row)
        if row['event'] == 'adapter':
            event = row['details']
            adapter_index += 1
            require(event.get('schema') == 'A23-burst-sdk-adapter-event-1' and
                    event.get('backend_role') == 'sdk_capability_adapter' and integer(event.get('index'), adapter_index, adapter_index) and
                    integer(event.get('ticks'), 1, row['ticks']) and event.get('hardware_verified') is False and
                    event.get('hardware_entry_enabled') is False and event.get('event') in ADAPTER_EVENTS and
                    type(event.get('details')) is dict, 'invalid SDK adapter event')
            # Keep outer ordering/index; native SDK fields remain unmodified.
            by[event['event']].append(dict(row, details=event['details']))
    require(rows[0]['event'] == 'prepared', 'missing initial preparation')
    for name in (EVENTS | ADAPTER_EVENTS) - {'adapter', 'stop', 'iso_callback', 'control_callback'}:
        require(len(by[name]) <= 1, 'repeated '+name)
    prepared = rows[0]['details']
    n, d = prepared.get('timebase_numerator'), prepared.get('timebase_denominator')
    require(integer(n, 1, 2**32-1) and integer(d, 1, 2**32-1), 'invalid timebase')
    plan = prepared.get('plan', {})
    fixed = dict(schema='A23-burst-sdk-plan-3', backend='iousbhost-single-burst-1', first_frame_lead=32,
                 transaction_count=960, request_bytes_per_transaction=192, transfer_options=0, max_submissions=1,
                 max_device_triggers=1, max_async_aborts=1, repeat=0, control_deadline_ns=16000000,
                 iso_deadline_ns=2000000000, exit_wait_ns=1000000000, closed_observation_ns=250000000, max_trigger_gap_ns=2000000, max_trigger_age_ns=8000000, max_trigger_end_age_ns=24000000)
    require(all(plan.get(k) == v and type(plan.get(k)) is type(v) for k, v in fixed.items()) and
            plan.get('scenario') == {'kind': 'single_burst', 'first_sequence': FIRST} and type(plan['scenario']['first_sequence']) is int and
            all(plan.get(k) is False for k in ('hardware_entry_enabled', 'hardware_verified', 'allow_next_burst')), 'changed fixed plan')
    expected_budget = dict(schema='A23-runtime-budget-2', max_frame_query_ns=2000000, max_frame_age_ns=4000000,
        max_enqueue_call_ns=2000000, reserve_ns=8000000, frame_period_ns_assumption=1000000,
        exit_grace_ns=1000000000, hardware_timing_verified=False)
    require(json.dumps(plan.get('runtime_budget'), sort_keys=True) == json.dumps(expected_budget, sort_keys=True), 'changed runtime budget')
    from a23_sequence_binding import SDK_PLAN
    from build_a23_waiting_receiver import typed
    require(typed(plan,SDK_PLAN), 'changed sequence plan inventory/types')
    descriptors = prepared.get('descriptor_base64', {})
    require(set(descriptors) == {'device_descriptor', 'configuration_descriptor', 'active_interface'} and
            set(binding.get('descriptor_sha256', {})) == set(descriptors), 'missing descriptor binding')
    descriptor_bytes = {}
    for key, value in descriptors.items():
        b = base64.b64decode(value, validate=True)
        require(len(b) <= 1024 and base64.b64encode(b).decode() == value and digest(b) == binding['descriptor_sha256'][key], 'descriptor byte/hash mismatch')
        descriptor_bytes[key] = b
    require(base64.b64decode(descriptors['active_interface']) == bytes((9,4,2,0,1,255,73,1,0)), 'wrong active interface')
    dev = descriptor_bytes['device_descriptor'];cfg = descriptor_bytes['configuration_descriptor']
    require(len(dev) == 18 and dev[:2] == bytes((18,1)) and dev[8:12] == bytes((9,18,87,202)), 'wrong device identity')
    require(len(cfg) >= 9 and cfg[:2] == bytes((9,2)) and int.from_bytes(cfg[2:4], 'little') == len(cfg) and cfg[5] > 0, 'wrong configuration header')
    pos = 9;target = False;targets = endpoints = expected = 0;seen = set();interfaces = set()
    while pos < len(cfg):
        require(len(cfg)-pos >= 2 and 2 <= cfg[pos] <= len(cfg)-pos, 'truncated descriptor')
        r = cfg[pos:pos+cfg[pos]]
        if r[1] == 4:
            require(len(r) == 9 and endpoints == expected and (r[2],r[3]) not in seen, 'invalid interface layout')
            seen.add((r[2],r[3]));interfaces.add(r[2]);endpoints=0;expected=r[4]
            target = r[5:7] == bytes((255,73))
            if target:
                targets += 1
                require(r == descriptor_bytes['active_interface'], 'wrong target alternate')
        elif r[1] == 5:
            require(seen and len(r) == 7, 'invalid endpoint layout');endpoints += 1
            if target:
                require(r == bytes((7,5,131,1,0,1,1)), 'wrong target endpoint')
        else:
            require(r[1] not in (1,2,48,49), 'unexpected nested/SS descriptor')
        pos += len(r)
    require(targets == 1 and endpoints == expected and len(interfaces) == cfg[4], 'missing/ambiguous descriptor target')
    statuses = {}
    for name, phase in (('status_before', 'before'), ('status_after', 'after')):
        if by[name]:
            row = by[name][0];detail = row['details']
            statuses[phase] = status_reply(dict(detail, phase=phase, raw_sha256=detail.get('sha256')), row['ticks'], hardware=True)
    frame = admission = None
    if by['iso_return']:
        require(by['frame_sample'] and by['iso_intent'] and by['status_before'], 'ISO lacks preflight')
        f = by['frame_sample'][0]['details'];sample = f.get('sample', {})
        require(sample.get('source') == 'sdk_frame_number' and integer(sample.get('current_frame'), 1, 2**64-33) and
                integer(sample.get('frame_time')) and integer(sample.get('begin_ticks'), 1) and
                integer(sample.get('end_ticks'), sample['begin_ticks'], by['frame_sample'][0]['ticks']) and
                sample['begin_ticks'] >= statuses['before'][1]['end_ticks'] and
                statuses['before'][1]['begin_ticks'] >= rows[0]['ticks'] and statuses['before'][2] and
                integer(f.get('first_frame'), sample['current_frame']+32, sample['current_frame']+32), 'invalid preflight/frame binding')
        require(f.get('timebase_numerator') == n and f.get('timebase_denominator') == d, 'frame timebase mismatch')
        frame = dict(sample, timebase_numerator=n, timebase_denominator=d)
        admission = by['iso_return'][0]['details'].get('admission', {})
        audit_admission(admission, frame, hardware=True)
        require(by['iso_return'][0]['details'].get('accepted') is admission['accepted'], 'ISO admission/result mismatch')
    trigger = None
    if by['trigger_return']:
        require(admission and admission['accepted'] and admission['budget_pass'] and by['trigger_intent'], 'trigger without admitted ISO')
        row = by['trigger_return'][0];trigger = row['details']
        expected = dict(request_type=65, request=84, value=FIRST, index=2, length=0, timeout_ns=16000000)
        require(all(type(trigger.get(k)) is int and trigger[k] == v for k, v in expected.items()) and
                type(trigger.get('accepted')) is bool and integer(trigger.get('start_ticks'), 1) and
                by['iso_return'][0]['index'] < by['trigger_intent'][0]['index'] < row['index'] and
                by['trigger_intent'][0]['ticks'] <= trigger['start_ticks'] <= row['ticks'] and
                not any(r['index'] < row['index'] for r in by['iso_callback']), 'invalid trigger ordering/tuple')
        gap = duration_ns(admission['return_ticks'], trigger['start_ticks'], n, d)
        age = duration_ns(frame['begin_ticks'], trigger['start_ticks'], n, d)
        require(gap is not None and gap <= 2000000 and age is not None and age <= 8000000 and
                integer(trigger.get('gap_ns'), gap, gap) and integer(trigger.get('age_ns'), age, age), 'trigger budget mismatch')
        if trigger.get('error') is not None:
            e = trigger['error']
            require(type(e) is dict and type(e.get('domain')) is str and type(e.get('code')) is int and
                    integer(e.get('code_u32'), 0, 2**32-1) and e['code_u32'] == e['code'] & 0xffffffff, 'invalid original SDK error')
    for name in ('iso_callback', 'control_callback'):
        for ordinal, row in enumerate(by[name], 1):
            detail = row['details']
            require(integer(detail.get('count'), ordinal, ordinal) and integer(detail.get('status_u32'), 0, 2**32-1) and
                    integer(detail.get('arrival_ticks'), 1, row['ticks']), 'invalid callback observation')
            if name == 'control_callback':
                require(trigger and integer(detail.get('bytes')) and row['index'] > by['trigger_return'][0]['index'], 'unbound control callback')
            else:
                require(type(detail.get('pointer_mismatch')) is bool and by['iso_return'] and
                        integer(detail.get('sdk_arrival_ticks'), 1, detail['arrival_ticks']), 'unbound ISO callback')
    result_path = 'final' if (root/'final/COMMITTED').is_file() else 'retained'
    result = checkpoint(root/result_path)
    require(result.get('schema') == 'A23-burst-sdk-checkpoint-1' and result.get('backend') == 'iousbhost-single-burst-1' and
            result.get('binding') == binding and all(result.get(k) is False for k in POLICY), 'invalid checkpoint binding/policy')
    for key in ('started', 'finished', 'unresolved', 'core_saved', 'save_attempted', 'exit_requested', 'journal_failed',
                'retained_checkpoint_saved', 'final_checkpoint_saved'):
        require(type(result.get(key)) is bool, 'invalid checkpoint boolean')
    require(integer(result.get('exit_code'), 0, 1), 'invalid exit code')
    for key in ('submitted_at_ticks', 'trigger_start_ticks', 'exit_at_ticks'):
        require(integer(result.get(key)), 'invalid coordinator clock')
    if by['iso_return']:
        require(by['frame_sample'][0]['ticks'] <= result['submitted_at_ticks'] <= by['iso_intent'][0]['ticks'], 'unbound coordinator submission time')
    else:
        require(result['submitted_at_ticks'] == 0, 'fabricated submission time')
    require(result['trigger_start_ticks'] == (trigger['start_ticks'] if trigger else 0), 'unbound coordinator control time')
    transport = result.get('transport', {})
    require(transport.get('schema') == 'A23-burst-sdk-adapter-result-1' and transport.get('backend_role') == 'sdk_capability_adapter' and
            all(transport.get(k) is False for k in POLICY if k != 'usb_strict_pass'), 'invalid transport policy')
    for key in ('closed', 'iso_accepted', 'control_pending', 'storage_retained', 'detached', 'journal_failed'):
        require(type(transport.get(key)) is bool, 'invalid transport boolean')
    for key, name in (('iso_attempts', 'iso_return'), ('trigger_attempts', 'trigger_return'), ('host_aborts', 'abort_return'),
                      ('iso_callbacks', 'iso_callback'), ('control_callbacks', 'control_callback'), ('after_reads', 'after_intent')):
        require(integer(transport.get(key)) and (result['journal_failed'] or transport[key] == len(by[name])), 'checkpoint/journal count mismatch')
    native = None
    if result['core_saved']:
        native = core_audit(root/'transfer', burst=True);meta = load(root/'transfer/metadata.json')
        require(meta['binding'] == binding and by['save_intent'] and by['save_result'] and by['save_result'][0]['details']['saved'] is True and
                by['save_intent'][0]['details']['binding'] == binding and by['iso_snapshot'] and
                by['iso_snapshot'][0]['index'] < by['save_intent'][0]['index'] < by['save_result'][0]['index'] and
                meta['first_frame'] == frame['current_frame']+32, 'core/session/save binding mismatch')
        snap = by['iso_snapshot'][0]['details']
        require(snap.get('raw_sha256') == digest((root/'transfer/raw.bin').read_bytes()) and
                snap.get('transactions_sha256') == digest((root/'transfer/transactions.bin').read_bytes()) and
                snap.get('arrival_ticks') == meta['callback_arrival_ticks'] and snap.get('overall_u32') == meta.get('overall_u32'), 'core/snapshot mismatch')
        if not native['submission_rejected']:
            observed = by['iso_callback'][0]['details']
            require(observed['arrival_ticks'] == meta['callback_arrival_ticks'] and observed['status_u32'] == meta['overall_u32'] and
                    observed['pointer_mismatch'] is meta['callback_pointer_mismatch'] and
                    meta['callback_count_at_save'] == sum(r['index'] < by['save_result'][0]['index'] for r in by['iso_callback']) and
                    result['submitted_at_ticks'] <= meta['submit_begin_ticks'] <= admission['check_ticks'] <=
                    admission['return_ticks'] <= meta['submit_return_ticks'], 'core/own callback and submission clock mismatch')
    if by['status_after']:
        require(by['iso_callback'] and len(by['iso_callback']) == 1 and
                by['iso_callback'][0]['details']['pointer_mismatch'] is False and
                by['iso_snapshot'][0]['index'] < by['after_intent'][0]['index'] < by['status_after'][0]['index'] and
                statuses['after'][1]['begin_ticks'] >= by['iso_callback'][0]['details']['arrival_ticks'], 'after before own completion')
        if trigger and trigger['accepted']:
            require(by['control_callback'] and by['control_callback'][0]['index'] < by['after_intent'][0]['index'], 'after while control pending')
    if by['abort_return']:
        require(by['abort_intent'] and by['abort_intent'][0]['index'] < by['abort_return'][0]['index'] and
                not any(r['index'] < by['abort_intent'][0]['index'] for r in by['iso_callback']) and
                not any(r['details'].get('reason') == 'detached' and r['index'] < by['abort_intent'][0]['index'] for r in by['stop']), 'abort after callback/detach')
    if transport['closed']:
        require(by['close_intent'] and by['closed'] and by['close_intent'][0]['index'] < by['closed'][0]['index'] and
                not transport['storage_retained'] and not transport['control_pending'] and not result['unresolved'], 'invalid closed lifecycle')
        close = by['close_intent'][0]
        require(type(close['details'].get('prepared')) is bool, 'invalid close mode')
        if not close['details']['prepared']:
            require(result['core_saved'] and close['details'].get('owner_acknowledged') is True and
                    by['save_result'][0]['index'] < close['index'], 'close before committed owner acknowledgment')
        if trigger and trigger['accepted']:
            require(by['control_callback'] and by['control_callback'][0]['index'] < close['index'], 'close while control pending')
    reasons = [r['details'].get('reason') for r in by['stop'] if r['event'] == 'stop']
    require(type(result.get('failure_reasons')) is list and type(transport.get('failure_reasons')) is list and
            all(type(s) is str for s in result['failure_reasons']+transport['failure_reasons']), 'invalid failure reasons')
    expected_reasons = set(reasons) | ({'journal_failed'} if result['journal_failed'] else set())
    require(expected_reasons <= set(result['failure_reasons']) if result['journal_failed'] else
            expected_reasons == set(result['failure_reasons']), 'checkpoint erased failures')
    adapter_reasons = {r['details'].get('reason') for r in by['stop'] if r['event'] == 'adapter'}
    require(adapter_reasons <= set(transport['failure_reasons']) if result['journal_failed'] else
            adapter_reasons == set(transport['failure_reasons']), 'checkpoint erased SDK failures')
    control_ns = duration_ns(trigger['start_ticks'], by['control_callback'][0]['details']['arrival_ticks'], n, d) if trigger and by['control_callback'] else None
    require(not (trigger and by['control_callback']) or control_ns is not None, 'control ingress clock regressed')
    timed_control = control_ns is not None and control_ns > 16000000
    if timed_control:
        require('control_deadline' in reasons, 'late control callback erased deadline')
    if by['iso_callback']:
        iso_ns = duration_ns(result['submitted_at_ticks'], by['iso_callback'][0]['details']['sdk_arrival_ticks'], n, d)
        require(iso_ns is not None, 'ISO ingress clock regressed')
        if iso_ns > 2000000000:
            require('iso_deadline' in reasons, 'late ISO callback erased deadline')
    control_clean = bool(trigger and trigger['accepted'] and trigger.get('error') is None and len(by['control_callback']) == 1 and
        by['control_callback'][0]['details']['status_u32'] == by['control_callback'][0]['details']['bytes'] == 0 and not timed_control)
    final_confirmed = bool(by['final_checkpoint'] and by['final_checkpoint'][0]['details'].get('saved') is True)
    if result_path == 'final':
        require(by['closed_observed'] and duration_ns(by['closed_observed'][0]['ticks'], result['ticks'], n, d) >= 250000000,
                'final checkpoint before closed observation interval')
    else:
        require(result['unresolved'] and not result['finished'] and not transport['closed'] and
                (result['journal_failed'] or (by['exit_requested'] and
                    duration_ns(by['exit_requested'][0]['ticks'], result['ticks'], n, d) >= 1000000000)), 'invalid retained checkpoint')
    after_header = decode_status(statuses['after'][0]) if statuses.get('after', (None,None,False))[2] else None
    header_candidate = bool(after_header and all(after_header[k] == v for k, v in dict(sequence=FIRST, state=2,
        post_result=0, requested=3072, transferred=3072, urb_status=3, report_result=0, speed=3).items()) and
        after_header['urb_id'] == after_header['report_id'] > 0 and after_header['report_count'] in (0,1))
    complete = bool(native and native['host_transaction_candidate'] and control_clean and
        statuses.get('before', (None,None,False))[2] and header_candidate and
        final_confirmed and transport['closed'] and result['finished'] and result['exit_code'] == 0 and
        not result['failure_reasons'] and not transport['failure_reasons'])
    return dict(schema='A23-sequence-sdk-host-analysis-1', journal_sha256=digest(raw),
        host_binding_verified=not result['journal_failed'], journal_prefix_only=result['journal_failed'],
        host_observation_complete=complete and not result['journal_failed'], core=native, checkpoint=result_path,
        injected_fixture=(root/'MOCK_ONLY.txt').is_file(), **{k:False for k in POLICY},
        device_log_bound=False, empty_status_policy_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        result = analyze(args.directory)
    except (ValueError, OSError, TypeError, KeyError, UnicodeError) as error:
        print(json.dumps(dict(host_binding_verified=False, hardware_verified=False, usb_strict_pass=False, error=str(error)), indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['host_observation_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
