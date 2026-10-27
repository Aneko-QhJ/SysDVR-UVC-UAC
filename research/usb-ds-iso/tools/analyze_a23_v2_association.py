#!/usr/bin/env python3
"""Offline comparison of supplied host and V2 files; never authenticates a run."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from analyze_ep0_candidate_capture_v2 import decode_capture
from analyze_ep0_diagnostic_v2 import decode_diagnostic
from analyze_ep0_session_v2 import decode_session
from analyze_io_usb_host_burst_sdk import analyze as audit_host, read_plain
from analyze_io_usb_host_burst_sdk_collection import replies
from analyze_io_usb_host_evidence import require, unique_object
from audit_io_usb_host_device import decode_status

DECODERS = {'ownership': (decode_capture, 13040), 'diagnostic': (decode_diagnostic, 13056),
            'session': (decode_session, 14368)}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def setup_hex(control):
    values = [control[k] for k in ('request_type', 'request', 'value', 'index', 'length')]
    require(all(type(v) is int for v in values), 'noninteger control field')
    return struct.pack('<BBHHH', *values).hex()


def compare(host_requests, statuses, trace):
    """Only compare bytes/order/state within supplied records, never subtract clocks."""
    target = [q for q in trace['requests'] if q['interface'] == 2 and
              q['setup_hex'] in {r['setup_hex'] for r in host_requests}]
    shape = [q['setup_hex'] for q in target] == [r['setup_hex'] for r in host_requests]
    observations = []
    if shape:
        for phase, group in zip(('before', 'burst', 'after'), target):
            snapshots = [r for r in group['records'] if r['stage'] == 'status_snapshot']
            if phase != 'burst':
                match = len(snapshots) == 1 and (
                    snapshots[0]['arg0'], snapshots[0]['arg1']) == (
                    statuses[phase]['state'], statuses[phase]['sequence'])
                observations.append(dict(phase=phase, state_and_sequence_match=match,
                                         snapshot_count=len(snapshots)))
    return dict(interface2_target_request_count=len(target), exact_target_setup_order_matches=shape,
                status_observations=observations,
                status_state_sequence_matches=bool(shape and len(observations) == 2 and
                    all(r['state_and_sequence_match'] for r in observations)),
                full_status_payload_binding_verified=False,
                missing_interface2_records_prove_event_absence=False,
                cross_clock_alignment_verified=False, bus_arrival_time_verified=False)


def analyze(host, artifacts, expected_recipe):
    require(artifacts and set(artifacts) <= set(DECODERS), 'supply V2 artifacts')
    require(type(expected_recipe) is str and len(expected_recipe) == 64 and
            all(c in '0123456789abcdef' for c in expected_recipe), 'invalid recipe')
    result = dict(schema='A23-v2-supplied-association-1', offline_only=True,
                  expected_recipe=expected_recipe, files={}, errors=[],
                  host_audit_valid=False, device_files_valid=False,
                  supplied_comparison_consistent=False, same_physical_run_verified=False,
                  source_authenticated=False, cross_clock_alignment_verified=False,
                  usb_strict_pass=False, hardware_verified=False, root_cause_confirmed=False,
                  cleanup_authorized=False, allow_next_burst=False)
    decoded = {}
    for name, path in artifacts.items():
        try:
            decoder, limit = DECODERS[name]
            raw = read_plain(Path(path), limit)
            result['files'][name] = dict(path=str(Path(path).resolve()), bytes=len(raw), sha256=sha(raw))
            decoded[name] = decoder(raw, expected_recipe)
        except (ValueError, OSError, KeyError, TypeError, struct.error) as error:
            result['errors'].append(dict(component=name, error=str(error)))
    traces = [(name, d['trace']) for name, d in decoded.items() if 'trace' in d]
    session = decoded.get('session')
    if session and session['diagnostic']:
        traces.append(('session', session['diagnostic']['trace']))
    trace_hashes = {t['sha256'] for _, t in traces}
    conflicts = []
    if len(trace_hashes) > 1:
        conflicts.append('device_trace_disagreement')
    if 'ownership' in decoded and ('diagnostic' in decoded or session and session['diagnostic']):
        conflicts.append('normal_and_diagnostic_exit_paths_mixed')
    if 'diagnostic' in decoded and session and session['diagnostic'] != decoded['diagnostic']:
        conflicts.append('session_diagnostic_disagreement')
    if session and 'ownership' in decoded:
        own = decoded['ownership']
        if not session['context_present'] or (session['ep0_writer'], session['boot_id_hex'], session['session_id_hex']) != (
                own['writer'], own['trace']['boot_id_hex'], own['trace']['session_id_hex']):
            conflicts.append('session_ownership_identity_disagreement')
    result.update(device_conflicts=conflicts, device_trace_sha256=sorted(trace_hashes),
                  device_files_valid=not result['errors'] and not conflicts,
                  device_decoded=decoded,
                  session_envelope_own_commit_authenticated=False)
    try:
        host = Path(host)
        journal = read_plain(host/'session.jsonl', 128*4096)
        result['host_journal_sha256'] = sha(journal)
        result['host'] = audit_host(host)
        require(result['host']['journal_sha256'] == sha(journal) and
                read_plain(host/'session.jsonl', 128*4096) == journal, 'host journal changed during audit')
        rows = [json.loads(line, object_pairs_hook=unique_object) for line in journal.splitlines()]
        events = {r['details']['event']: r['details']['details'] for r in rows if r['event'] == 'adapter'}
        requests = [dict(phase=p, setup_hex=setup_hex(events['status_'+p]['observation']['control']))
                    for p in ('before', 'after')]
        trigger = events['trigger_return']
        requests.insert(1, dict(phase='burst', setup_hex=setup_hex(trigger)))
        status = {k: decode_status(v) for k, v in replies(journal).items()}
        result.update(host_audit_valid=True, host_requests=requests, host_status=status,
                      host_observation_complete=result['host']['host_observation_complete'])
        if len(trace_hashes) == 1:
            result['comparison'] = compare(requests, status, traces[0][1])
            result['supplied_comparison_consistent'] = bool(result['device_files_valid'] and
                result['comparison']['exact_target_setup_order_matches'] and
                result['comparison']['status_state_sequence_matches'])
    except (ValueError, OSError, KeyError, TypeError, struct.error) as error:
        result['errors'].append(dict(component='host', error=str(error)))
    # A matching shape, CRC, recipe and nonce cannot bind independently supplied files.
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', type=Path, required=True)
    p.add_argument('--expected-recipe', required=True)
    for name in DECODERS:
        p.add_argument('--'+name, type=Path)
    args = p.parse_args()
    artifacts = {name: getattr(args, name) for name in DECODERS if getattr(args, name)}
    print(json.dumps(analyze(args.host, artifacts, args.expected_recipe), indent=2)+'\n')


if __name__ == '__main__':
    main()
