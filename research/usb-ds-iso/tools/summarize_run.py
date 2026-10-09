#!/usr/bin/env python3
"""Decode host JSONL and raw controller words; preserve unverified claims."""
import argparse
import json
import struct
from pathlib import Path


def decode_diag(value):
    b = bytes.fromhex(value)
    if len(b) != 112:
        return None
    marker = struct.unpack_from('<I', b)[0]
    if marker == 0xd1:
        return {'stage': 'report_hook_reached', 'producer_entry_observed': False}
    if marker == 0xd2:
        entry = b[16:32]
        return {'stage': 'producer_validation_rejected', 'producer_entry_observed': True,
                'input_length': struct.unpack_from('<I', b, 8)[0],
                'input_dma': f'{struct.unpack_from("<Q", b, 32)[0]:016X}',
                'endpoint_entry_hex': entry.hex(), 'endpoint_address': entry[2],
                'attributes': entry[3], 'mps': struct.unpack_from('<H', entry, 4)[0],
                'interval': entry[6], 'burst': entry[9], 'mult': entry[10],
                'bytes_per_interval': struct.unpack_from('<H', entry, 11)[0]}
    if marker in (0x334f5349, 0x344f5349, 0x354f5349, 0x364f5349, 0x374f5349):
        interval1 = marker == 0x374f5349
        context = marker in (0x364f5349, 0x374f5349)
        doorbell = marker == 0x354f5349
        publication = marker in (0x344f5349, 0x354f5349)
        _, error_offset, control, terminal, bitmap, actual, first = struct.unpack_from('<IIIIIIQ', b)
        retained = bool(terminal & 0x80000000)
        def audit_event(offset, role):
            words = struct.unpack_from('<IIII', b, offset)
            # Only the control sentinel is cleared at submission. Old bytes
            # in an invalid slot are intentionally excluded from the result.
            if not words[3]:
                return {'role': role, 'valid': False}
            return {'role': role, 'valid': True, 'dwords': [f'{x:08X}' for x in words],
                    'mfi': struct.unpack_from('<I', b, offset + 16)[0],
                    'type': words[3] >> 10 & 63, 'ed': bool(words[3] & 4),
                    'completion_code': words[2] >> 24, 'raw_count': words[2] & 0xffffff,
                    'pointer_or_tag': f'{words[0] | words[1] << 32:016X}',
                    'endpoint_index': words[3] >> 16 & 31}
        records = [audit_event(32, 'td0_success'),
                   audit_event(52, 'first_matched_error' if retained else 'td1_success')]
        td0, td1 = records
        if not publication and not context:
            records += [audit_event(72, 'first_filtered'), audit_event(92, 'first_post_terminal')]
        # The report copies several independent words. A racing read can see
        # terminal retention before TD1 has been replaced with the error.
        error_consistent = (retained and td1['valid'] and td1['completion_code'] == (terminal & 255) and
                            (td1['completion_code'] != 1 or (td1['ed'] and td1['raw_count'] != 192)))
        error = td1 if error_consistent else None
        if retained and td1['valid'] and not error_consistent:
            td1['role'] = 'td1_or_error_transition'
        trb = control >> 10 & 63 == 5
        result = {'variant': 'HS-burst-context' if context else 'HS-burst-doorbell' if doorbell else 'HS-burst-publication' if publication else 'HS-burst-audit',
                'diagnostics_layout': 'ISO7' if interval1 else 'ISO6' if context else 'ISO5' if doorbell else 'ISO4' if publication else 'ISO3', 'burst_packets': 16,
                'completed_bitmap': f'{bitmap:04X}', 'completed_packets': bitmap.bit_count(),
                'actual_sum': actual, 'terminal': terminal, 'terminal_success': terminal == 1,
                'retained_after_error': retained, 'latched_completion_code': terminal & 255 if retained else None,
                'first_virtual_trb': f'{first:016X}',
                'first_trb_control_only': trb, 'first_trb_control': f'{control:08X}',
                'first_trb_snapshot_available': trb,
                'frame_id': control >> 20 & 0x7ff if trb else None, 'cycle': control & 1 if trb else None,
                'raw_event_capture_available': any(r['valid'] for r in records),
                'context_snapshot_available': False, 'audit_records': records,
                'td1_snapshot_replaced_by_error': bool(error_consistent),
                'error_record_matches_terminal': bool(error_consistent),
                'error_event_snapshot_available': error is not None,
                'error_event_dwords': error['dwords'] if error else None,
                'error_mfi': error['mfi'] if error else None,
                'error_matched_offset': error_offset if error else None,
                'error_td_index': error_offset // 32 if error else None,
                'first_two_ed_mfi_delta': (td1['mfi'] - td0['mfi']) & 0x3fff
                    if not retained and td0['valid'] and td1['valid'] else None,
                'filtered_reason_recorded': False, 'total_event_count_available': False,
                'later_events_omitted': True, 'mfi_is_handler_observation': True,
                'multi_field_snapshot_atomic': False,
                'wire_trace_verified': False, 'host_device_clocks_synchronized': False}
        if context:
            selected, valid = struct.unpack_from('<II', b, 72)
            complete = valid == 1
            consistent = complete and trb and selected < 16384 and (
                (control >> 20 & 0x7ff) == ((selected >> 3) + 32) & 0x7ff)
            snapshot = {'valid': bool(consistent), 'capture_complete': complete,
                        'header_consistent': bool(consistent),
                        'sample_point': 'before_first_cycle_publication',
                        'hardware_context_modified': False, 'snapshot_atomic': False,
                        'software_observation_only': True, 'data_pid_verified': False}
            if consistent:
                words = struct.unpack_from('<8I', b, 80)
                info0, info1, deq_lo, deq_hi, tx, sequence, errors, progress = words
                snapshot.update(frame_select_mfi=selected, context_dwords=[f'{x:08X}' for x in words],
                    state=info0 & 7, mult=info0 >> 8 & 3, interval=info0 >> 16 & 255,
                    endpoint_type=info1 >> 3 & 7, cerr=info1 >> 1 & 3,
                    max_burst=info1 >> 8 & 255, max_packet_size=info1 >> 16,
                    dequeue_pointer=f'{(deq_hi << 32) | (deq_lo & ~15):016X}', dcs=deq_lo & 1,
                    average_trb_length=tx & 65535, max_esit_payload=tx >> 16,
                    edtla=sequence & 0xffffff, sequence_byte=sequence >> 24,
                    partial_td=bool(sequence & (1 << 25)), cerr_count=errors >> 18 & 3,
                    data_offset=progress & 0x1ffff, num_trbs=progress >> 22 & 31,
                    configured_fields_match=(info0 & 7) == 1 and (info0 >> 8 & 3) == 0 and
                        (info0 >> 16 & 255) == (1 if interval1 else 4) and (info1 >> 3 & 7) == 5 and
                        (info1 >> 8 & 255) == 0 and info1 >> 16 == 256 and tx >> 16 == 256)
            result.update(context_snapshot=snapshot, context_snapshot_available=bool(consistent),
                          filtered_event_sampling_available=False, post_terminal_event_sampling_available=False,
                          reserved_bytes_interpreted=False)
            if interval1:
                result.update(expected_interval=1, service_interval_microframes=1,
                              nominal_host_slots_per_frame=8, following_td_sia=True)
        if publication:
            selected, before_publish, before_doorbell, valid = struct.unpack_from('<IIII', b, 72)
            # The sentinel is cleared before selection. ISO4 stores1 after
            # its reads; ISO5 stores the tail's returned DB operand after its
            # reads. Neither is a transaction ID or an atomic snapshot.
            complete = valid == (0x700 if doorbell else 1)
            consistent = complete and trb and all(x < 16384 for x in (selected, before_publish, before_doorbell)) and (
                (control >> 20 & 0x7ff) == ((selected >> 3) + 32) & 0x7ff)
            anchors = {'valid': bool(consistent), 'capture_complete': complete,
                       'header_consistent': bool(consistent), 'doorbell_write_timestamped': False,
                       'software_observations_only': True, 'multi_field_snapshot_atomic': False}
            if consistent and not doorbell:
                anchors.update(frame_select_mfi=selected, before_publish_mfi=before_publish,
                    before_doorbell_mfi=before_doorbell,
                    select_to_before_publish_mfi_delta=(before_publish-selected) & 0x3fff,
                    publish_bracket_mfi_delta=(before_doorbell-before_publish) & 0x3fff,
                    select_to_before_doorbell_mfi_delta=(before_doorbell-selected) & 0x3fff,
                    target_minus_before_doorbell_mfi_mod16384=((control >> 20 & 0x7ff)*8-before_doorbell) & 0x3fff)
            if doorbell:
                anchors.update(doorbell_marker=f'{valid:08X}', original_tail_store_executed=bool(consistent),
                               controller_doorbell_acceptance_verified=False)
                if consistent:
                    anchors.update(frame_select_mfi=selected, before_tail_mfi=before_publish, after_tail_mfi=before_doorbell,
                        select_to_before_tail_mfi_delta=(before_publish-selected) & 0x3fff,
                        original_tail_bracket_mfi_delta=(before_doorbell-before_publish) & 0x3fff,
                        select_to_after_tail_mfi_delta=(before_doorbell-selected) & 0x3fff,
                        target_minus_after_tail_mfi_mod16384=((control >> 20 & 0x7ff)*8-before_doorbell) & 0x3fff)
            result.update(**({'doorbell_anchors': anchors} if doorbell else {'publication_anchors': anchors}), filtered_event_sampling_available=False,
                          post_terminal_event_sampling_available=False, reserved_bytes_interpreted=False)
        return result
    if marker == 0x324f5349:
        bitmap, actual = struct.unpack_from('<II', b, 16)
        terminal = struct.unpack_from('<I', b, 12)[0]
        first_trb = struct.unpack_from('<IIII', b, 48)
        snapshot = first_trb[3] >> 10 & 63 == 5
        error_words = struct.unpack_from('<IIII',b,64)
        error_snapshot = bool(terminal & 0x80000000) and (error_words[3] >> 10 & 63 == 32)
        return {'variant': 'HS-burst', 'burst_packets': 16,
                'completed_bitmap': f'{bitmap:04X}', 'completed_packets': bitmap.bit_count(),
                'actual_sum': actual, 'terminal': terminal, 'terminal_success': terminal == 1,
                'retained_after_error': bool(terminal & 0x80000000),
                'latched_completion_code': terminal & 255 if terminal & 0x80000000 else None,
                'first_virtual_trb': f'{struct.unpack_from("<Q", b, 24)[0]:016X}',
                'raw_event_capture_available': error_snapshot, 'context_snapshot_available': False,
                'first_trb_snapshot_available': snapshot,
                'iso_trb': [f'{x:08X}' for x in first_trb] if snapshot else None,
                'frame_id': first_trb[3] >> 20 & 0x7ff if snapshot else None,
                'cycle': first_trb[3] & 1 if snapshot else None,
                'first_trb_control_only': snapshot and not any(first_trb[:3]),
                'error_event_snapshot_available': error_snapshot,
                'error_event_dwords': [f'{x:08X}' for x in error_words] if error_snapshot else None,
                'error_mfi': struct.unpack_from('<I',b,8)[0] if error_snapshot else None,
                'error_matched_offset': struct.unpack_from('<I',b,4)[0] if error_snapshot else None,
                'error_td_index': struct.unpack_from('<I',b,4)[0] // 32 if error_snapshot else None}
    if marker != 0x314f5349:
        return None
    magic, variant, count, terminal = struct.unpack_from('<IIII', b)
    iso_physical, ed_tag = struct.unpack_from('<QQ', b, 32)
    iso = struct.unpack_from('<IIII', b, 48)
    ed = struct.unpack_from('<IIII', b, 64)
    events = []
    def event(words):
        return {'dwords': [f'{x:08X}' for x in words], 'type': words[3] >> 10 & 63,
                       'ed': bool(words[3] & 4), 'completion_code': words[2] >> 24,
                       'raw_count': words[2] & 0xffffff, 'pointer_or_tag': f'{words[0] | words[1] << 32:016X}',
                       'endpoint_index': words[3] >> 16 & 31}
    for i in range(min(count, 2)):
        events.append(event(struct.unpack_from('<IIII', b, 80 + i*16)))
    latest = count > 2 and ed[3] >> 10 & 63 == 32
    if latest:
        last = event(ed)
        last['event_number'] = count
        events.append(last)
    return {'variant': 'ABC'[variant-1] if 1 <= variant <= 3 else variant,
            'event_count': count, 'events_omitted': max(count-len(events), 0), 'terminal': terminal,
            'terminal_success': terminal == 1, 'retained_after_error': bool(terminal & 0x80000000),
            'hardware_success_retained': terminal == 0x40000001,
            'latched_completion_code': terminal & 0xff if terminal & 0x80000000 else None,
            'context_dwords': [f'{x:08X}' for x in struct.unpack_from('<IIII', b, 16)],
            'ep_state_at_submit': struct.unpack_from('<I', b, 16)[0] & 7,
            'endpoint_type_at_submit': struct.unpack_from('<I', b, 20)[0] >> 3 & 7,
            'iso_physical': f'{iso_physical:016X}', 'ed_tag': f'{ed_tag:016X}',
            'iso_trb': [f'{x:08X}' for x in iso],
            'ed_trb': None if latest else [f'{x:08X}' for x in ed],
            'ed_snapshot_replaced_with_latest_event': latest,
            'sia': bool(iso[3] & (1 << 31)), 'frame_id': iso[3] >> 20 & 0x7ff,
            'ioc': bool(iso[3] & 32),
            'cycle': iso[3] & 1, 'tbc': iso[3] >> 7 & 3, 'tlbpc': iso[3] >> 16 & 15,
            'events': events}


def summarize(rows):
    runs = {}
    session = None
    burst_packets = next((r.get("burst_packets",1) for r in rows if r.get("kind") == "experiment"),1)
    frame_report = next((r for r in rows if r.get('kind') == 'frame_report'), None)
    samples = [r for r in rows if r.get('kind') == 'frame_sample']
    rates = []
    valid = bool(frame_report and frame_report.get('no_td_submitted') and len(samples) == 8)
    for i, sample in enumerate(samples):
        valid &= (sample['result'] == 0 and sample['raw_mfi'] < 16384 and
                  sample['ticks_after'] >= sample['ticks_before'] and int(sample['mmio'], 16) != 0)
        if i:
            previous = samples[i-1]
            dt = ((sample['ticks_before'] + sample['ticks_after']) -
                  (previous['ticks_before'] + previous['ticks_after'])) / 2
            du = (sample['raw_mfi'] - previous['raw_mfi']) & 0x3fff
            rate = du * frame_report['tick_frequency'] / dt if dt > 0 else 0
            rates.append(rate)
            valid &= (7200 <= rate <= 8800 and sample['mmio'] == previous['mmio'])
    for row in rows:
        kind = row.get('kind')
        if kind == 'session': session = row; continue
        sequence = row.get('sequence')
        if sequence is None: continue
        run = runs.setdefault(sequence, {'sequence': sequence})
        if kind == 'device_status':
            run['device'] = row
            diag = decode_diag(row['diagnostics_hex'])
            if diag: run['diagnostics'] = diag
        elif kind == 'iso_transfer':
            run['host_transfer_status'] = row['status']
            run['received_packets'] = [p for p in row['packets'] if p['length']]
            expected = b'ISO1' + (sequence & 0xffff).to_bytes(2, 'little') + bytes(
                (i ^ sequence ^ (sequence >> 8)) & 255 for i in range(6, 192))
            def expected_packet(p):
                raw = bytes.fromhex(p.get('data_hex',''))
                if burst_packets == 1: return expected
                if len(raw) != 192: return b''
                seq = int.from_bytes(raw[4:6], 'little')
                if (seq-sequence) & 0xffff >= burst_packets: return b''
                return b'ISO1' + seq.to_bytes(2,'little') + bytes((i ^ seq ^ (seq >> 8)) & 255 for i in range(6,192))
            run['exact_payload_observations'] = [
                {'packet_index': p['index'], 'packet_status': p['status'],
                 'all_192_bytes_match': True, 'error_free': p['status'] == 0}
                for p in run['received_packets']
                if p['length'] == 192 and bytes.fromhex(p.get('data_hex', '')) == expected_packet(p)]
        elif kind == 'raw_buffer': run['raw_buffer'] = row
        elif kind == 'result': run['result'] = row
    # The initial STATUS may describe a completed TD from a previous invocation.
    attempts = [r for s, r in sorted(runs.items()) if s != 0 and
                ('result' in r or 'host_transfer_status' in r)]
    passed = sum(bool(r.get('result', {}).get('iso_payload_verified')) for r in attempts)
    terminal = sum(bool(r.get('result', {}).get('completion_verified')) for r in attempts)
    observed = sum(len(r.get('exact_payload_observations', [])) for r in attempts)
    return {'session': session, 'burst_packets': burst_packets, 'frame_samples': samples, 'frame_rates_per_second': rates,
            'frame_time_basis_verified': bool(valid), 'attempts': len(attempts), 'payload_passes': passed,
            'terminal_report_passes': terminal, 'exact_payload_observations': observed,
            'type5_hardware_data_observed': observed > 0,
            'legacy_completion_reuse_verified': False, 'wire_trace_verified': False,
            'residual_count_semantics_verified': False, 'runs': attempts}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log', type=Path)
    p.add_argument('--out', type=Path)
    args = p.parse_args()
    rows = [json.loads(line) for line in args.log.read_text().splitlines() if line.strip()]
    text = json.dumps(summarize(rows), indent=2) + '\n'
    if args.out: args.out.write_text(text)
    else: print(text, end='')


if __name__ == '__main__': main()
