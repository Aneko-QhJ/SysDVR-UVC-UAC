#!/usr/bin/env python3
"""Compare five frozen A23 runs without modifying evidence or accessing USB."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
RUNS = (
    'A-A23-HS-interval1-20261008-000112',
    'A-A23-HS-interval1-20261008-003952',
    'A-A23-host-microframe-20261008-014103',
    'A-A23-host-microframe-20261008-015927',
    'A-A23-HS-native-serial-20261009-164428',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    result = []
    for line in path.read_text().splitlines():
        if not line.startswith('{'):
            continue
        result.append(json.loads(line))
    return result


def verify_manifest(run):
    entries = []
    for line in (run / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        name = name.removeprefix('*')
        path = run / name
        if not path.resolve().is_relative_to(run.resolve()):
            raise ValueError(f'Unsafe manifest path: {name}')
        actual = digest(path)
        if actual != expected:
            raise ValueError(f'Frozen evidence mismatch: {path}')
        entries.append({'file': name, 'sha256': actual})
    return entries


def compare(run):
    verified = verify_manifest(run)
    host = rows(run / 'host.jsonl')
    backend = rows(run / 'native-stderr.txt')
    native = [r for r in backend if r.get('kind') == 'darwin_iso_native']
    transfers = [r for r in host if r.get('kind') == 'iso_transfer']
    assert len(transfers) == 1, 'This comparison requires exactly one transfer'
    assert [r['index'] for r in native] == list(range(960))
    assert all(r['requested'] == 192 for r in native)
    transfer = transfers[0]
    packets = transfer['packets']
    assert [p['index'] for p in packets] == list(range(960))
    active = [r for r in native if r['actual']]
    indices = [r['index'] for r in active]
    assert indices and indices == [p['index'] for p in packets if p['length']]
    assert all(r['actual'] == packets[r['index']]['length'] for r in native)
    raw = (run / f"host.jsonl.seq{transfer['sequence']}.buffer.bin").read_bytes()
    assert len(raw) == 960 * 192
    exact = len(active) == 16
    for ordinal, index in enumerate(indices):
        seq = (transfer['sequence'] + ordinal) & 65535
        expected = b'ISO1' + seq.to_bytes(2, 'little') + bytes(
            (j ^ seq ^ (seq >> 8)) & 255 for j in range(6, 192))
        actual = raw[index * 192:(index + 1) * 192]
        exact = exact and actual == expected and actual == bytes.fromhex(packets[index]['data_hex'])
    empty_raw_zero = all(not any(raw[i * 192:(i + 1) * 192])
                         for i in range(960) if i not in indices)
    segments = []
    for r in native:
        key = (f"{r['status']:08X}", r['actual'])
        if not segments or (segments[-1]['status'], segments[-1]['actual']) != key:
            segments.append(dict(first=r['index'], last=r['index'], status=key[0], actual=key[1], count=1))
        else:
            segments[-1]['last'] = r['index']
            segments[-1]['count'] += 1
    prefix = 0
    for r in native:
        if r['status'] != 0xE000400E or r['actual'] != 0:
            break
        prefix += 1
    schedule = next(r for r in backend if r.get('kind') == 'darwin_iso_schedule')
    timing = next(r for r in host if r.get('kind') == 'host_trigger_timing')
    device = [r for r in host if r.get('kind') == 'device_status'][-1]
    b = bytes.fromhex(device['diagnostics_hex'])
    assert len(b) == 112 and b[:4] == b'ISO7'
    _, _, control, terminal, bitmap, total, first_trb = struct.unpack_from('<6IQ', b)
    events = []
    page, slot = first_trb & ~4095, (first_trb & 4095) // 16
    for ordinal, offset in enumerate((32, 52)):
        tag, count_cc, flags, mfi = struct.unpack_from('<QIII', b, offset)
        events.append(dict(tag=f'{tag:016X}', cc=count_cc >> 24, actual=count_cc & 0xFFFFFF,
                           ed=bool(flags & 4), mfi=mfi,
                           own_tag=tag == page + ((slot + 1 + 2 * ordinal) % 247) * 16))
    native_ok = all(r['overall'] == 0 for r in native) and all(r['status'] == 0 and r['actual'] == 192 for r in active)
    public_ok = transfer['status'] == 0 and all(packets[i]['status'] == 0 for i in indices)
    terminal_ok = (terminal == 1 and bitmap == 65535 and total == 3072 and device['state'] == 2
                   and device['urb_status'] == 3 and device['urb_id'] == device['report_id']
                   and device['requested'] == device['raw_count'] == 3072
                   and device['post_result'] == device['report_result'] == 0)
    consecutive = indices == list(range(indices[0], indices[0] + 16))
    log = json.loads((run / 'switch-log-evidence.json').read_text())
    frame_id = (control >> 20) & 2047
    declared = ((frame_id - schedule['frame_start'] % 2048) % 2048) * 8
    trigger_return = round(1000 * (timing['trigger_after'] - timing['submit_before']), 6)
    nominal_end = schedule['configured_lead_frames'] + prefix * 0.125 if prefix else None
    result = dict(run=run.name, source=str(run.resolve()), verified_files=verified,
                  native_records=len(native), native_segments=segments,
                  native_status_counts={f'{k:08X}': v for k, v in Counter(r['status'] for r in native).items()},
                  overall_codes=sorted({f"{r['overall']:08X}" for r in native}),
                  empty_not_sent_prefix_slots=prefix, nominal_prefix_duration_ms=prefix * 0.125,
                  active_indices=indices, active_native_codes=sorted({f"{r['status']:08X}" for r in active}),
                  public_overall_status=transfer['status'], exact_raw_packets=exact,
                  empty_raw_zero=empty_raw_zero, raw_sha256=digest(run / 'host.jsonl.seq1.buffer.bin'),
                  native_success=native_ok, public_success=public_ok, terminal_success=terminal_ok,
                  strict_single_success=bool(native_ok and public_ok and terminal_ok and exact and consecutive),
                  schedule=schedule, host_timing=timing, trigger_return_from_submit_before_ms=trigger_return,
                  nominal_prefix_end_from_submit_before_ms=nominal_end,
                  approximate_trigger_return_minus_prefix_end_ms=round(trigger_return - nominal_end, 6) if prefix else None,
                  nominal_timing_is_approximate=True, host_frame_query_accuracy_ms=1,
                  device_timing=log['device_timing'], full_log_sha256=log['log_sha256'],
                  full_log_matches_host=log['device_status_matches_host'],
                  unique_device_submission=log['unique_submission_verified'],
                  first_trb_control=f'{control:08X}', frame_id=frame_id, first_trb=f'{first_trb:016X}',
                  declared_first_slot=declared, observed_minus_declared_slots=indices[0] - declared,
                  context_words=[f'{w:08X}' for w in struct.unpack_from('<8I', b, 80)], events=events,
                  native_microframe_queries=[r for r in backend if r.get('kind') == 'iso_host_microframe'])
    return result


def analyze():
    archive = ROOT.parents[1] / '.git/experiment-artifacts/uac/research/usb-ds-iso/private/runs'
    results = []
    for name in RUNS:
        local = ROOT / 'private/runs' / name
        results.append(compare(local if local.is_dir() else archive / name))
    return dict(schema='A23-native-error-comparison-1', usb_accessed=False, frozen_evidence_modified=False,
                root_cause_confirmed=False, runs=results,
                frozen_files_verified=sum(len(r['verified_files']) for r in results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New directory only; existing paths are rejected')
    args = parser.parse_args()
    result = analyze()
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        target = args.output / 'comparison.json'
        target.write_text(encoded)
        print(json.dumps({'output': str(target.resolve()), 'runs': len(result['runs']),
                          'frozen_files_verified': result['frozen_files_verified']}))
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
