#!/usr/bin/env python3
"""Offline ISO7 error/host-window comparison. No device access or authorization."""
import argparse
import base64
import json
from pathlib import Path
import re
import struct
import subprocess

import path_span_card_workflow as card
from analyze_io_usb_host_burst_sdk import analyze as host_audit
from audit_io_usb_host_device import decode_status, iso7
from build_patch import build, validate_module, BUILD_ID
from summarize_run import decode_diag

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT/'private'
RECORDS = ('A23-quiet-once-20261016-interface2.json',
           'A23-lifecycle-once-20261016-interface2.json',
           'A23-path-span-once-20261016-interface2.json')
SNAPSHOT = PRIVATE/'card-cycles/20261016-232422-path-span-first-live-read'
DEVICE = PRIVATE/'analysis/A23-path-span-device-review-20261016/candidate'
SDK = Path('/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/System/Library/Frameworks/IOUSBHost.framework/Headers')
POLICY = dict(root_cause_confirmed=False, usb_strict_pass=False, hardware_verified=False,
              bus_phase_verified=False, allow_next_burst=False, cleanup_authorized=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def retained_error(raw):
    """Only expose a coherent error slot; invalid/stale slot bytes are not evidence."""
    require(type(raw) is bytes and len(raw) == 112, 'expected 112 diagnostic bytes')
    magic, offset, control, terminal, bitmap, total, first = struct.unpack_from('<6IQ', raw)
    require(magic == 0x374f5349, 'expected ISO7')
    require(bitmap <= 0xffff, 'out-of-range completed bitmap')
    lo, hi, status, flags, mfi = struct.unpack_from('<5I', raw, 52)
    cc, ed = status >> 24, bool(flags & 4)
    latched = bool(terminal & 0x80000000)
    coherent = bool(latched and cc > 0 and terminal == (0x80000000 | cc) and
                    (flags >> 10 & 63) == 32 and (flags >> 16 & 31) == 7 and
                    cc == (terminal & 0xff) and 0 <= offset < 512 and
                    offset % 32 == (16 if ed else 0) and mfi < 16384 and
                    (cc != 1 or (ed and status & 0xffffff != 192)))
    selected, valid = struct.unpack_from('<2I', raw, 72)
    frame = control >> 20 & 2047
    context = struct.unpack_from('<8I', raw, 80)
    header = bool(valid == 1 and selected < 16384 and control >> 10 & 63 == 5 and
                  not control >> 31 and frame == (((selected >> 3) + 32) & 2047))
    pointer = lo | hi << 32
    dequeue = context[3] << 32 | (context[2] & ~15)
    return dict(raw_sha256=card.b.sha(raw), terminal=terminal, retained=latched,
                completed_bitmap=bitmap, accepted_success_bytes=total, first_virtual_trb=first,
                header_consistent=header, context_valid_flag=valid,
                frame_select_mfi=selected if header else None, target_frame=frame if header else None,
                error_slot_consistent=coherent,
                error=(dict(dwords=[lo, hi, status, flags], completion_code=cc, ed=ed,
                            raw_count=status & 0xffffff, pointer=pointer, mfi=mfi,
                            matched_offset=offset, td_index=offset//32,
                            pointer_equals_prepublication_dequeue=pointer == dequeue,
                            handler_mfi_minus_target_microframes=(mfi-frame*8) % 16384 if header else None)
                       if coherent else None),
                raw_count_is_transferred_bytes=False, event_mfi_is_service_timestamp=False,
                snapshot_atomic=False, device_cc_semantics_confirmed=False, **POLICY)


def geometry(target_frame, host_first_frame, leads=(16, 24, 32, 64)):
    """Conditional modular frame arithmetic, not synchronization or bus evidence."""
    require(type(target_frame) is int and 0 <= target_frame < 2048 and
            type(host_first_frame) is int and host_first_frame >= 64, 'invalid frame input')
    current = host_first_frame-64
    delta = (target_frame-current) % 2048
    require(delta < 1024, 'frame distance ambiguous or outside forward half-wrap')
    rows = []
    for lead in leads:
        require(type(lead) is int and 0 < lead < 1024, 'invalid modeled lead')
        position = (delta-lead)*8
        rows.append(dict(modeled_lead_frames=lead, first_target_slot=position,
                         sixteen_reference_slots_fit=0 <= position and position+15 < 960,
                         following_sia_slots_are_predictions=False))
    return dict(conditional_same_bus_frame_domain=True, frame_domain_alignment_verified=False,
                current_mod2048=current % 2048, host_first_mod2048=host_first_frame % 2048,
                device_target_frame=target_frame, device_target_after_host_sample_frames=delta,
                host_first_after_device_target_frames=64-delta,
                reference_slot_at_current_lead=(delta-64)*8,
                modeled_windows=rows, schedule_only=True, **POLICY)


def observe_run(run):
    files = card.seal_verify(run)
    checked = host_audit(run/'host')
    rows = [json.loads(s) for s in files['host/session.jsonl'].splitlines()]
    events = [r['details'] for r in rows if r['event'] == 'adapter']
    by = {}
    for event in events:
        by.setdefault(event['event'], []).append(event['details'])
    require(all(len(by.get(n, [])) == 1 for n in
                ('status_before', 'status_after', 'frame_sample', 'iso_return', 'trigger_return')),
            'missing or ambiguous single-attempt events')
    status = decode_status(base64.b64decode(by['status_after'][0]['raw_base64'], validate=True))
    raw = bytes.fromhex(status['diagnostics_hex'])
    decoded = retained_error(raw)
    require(decoded['header_consistent'], 'inconsistent frame-selection header')
    frame = by['frame_sample'][0]
    require(frame['first_frame'] == frame['sample']['current_frame']+64, 'host lead differs from64')
    return dict(run=str(run), manifest_sha256=card.b.sha(card.b.plain(run/'SHA256SUMS')),
                entries=len(files), host_analysis=checked, status=status, diagnostics=decoded,
                existing_decoder=decode_diag(raw.hex()), frame_sample=frame,
                geometry=geometry(decoded['target_frame'], frame['first_frame']),
                enqueue_admission=by['iso_return'][0]['admission'],
                trigger_admission=by['trigger_return'][0], **POLICY)


def audit(output):
    output = Path(output)
    require(output.is_absolute() and output == output.resolve() and not output.exists(), 'new canonical output required')
    # Check all preconditions before creating the packet; never mutate existing evidence.
    source_audit = card.b.load(PRIVATE/'analysis/A23-path-span-readiness-review-20261016/audit.json')
    for name, expected in source_audit['source_hashes'].items():
        require(card.b.sha(card.b.plain(ROOT.parents[1]/name)) == expected, 'prior source drift: '+name)
    protected = card.b.load(PRIVATE/'analysis/A23-path-span-readiness-review-20261016/protected-inputs.json')
    for group, base in (('production',ROOT.parents[1]),('tickets',PRIVATE/'analysis'),
                        ('offline_records_sha256',PRIVATE/'analysis')):
        for name, expected in protected[group].items():
            require(card.b.sha(card.b.plain(base/name)) == expected, 'protected input drift: '+name)
    for path in (PRIVATE/'analysis/A23-path-span-readiness-review-20261016/records').iterdir():
        require(card.b.plain(path) == card.b.plain(PRIVATE/'analysis'/path.name), 'old live record drift')
    snapshots = card.verify_snapshot(SNAPSHOT)
    records = {n:card.b.plain(PRIVATE/'analysis'/n) for n in RECORDS}
    require(all(card.b.load(PRIVATE/'analysis'/n)['stage'] == 'failed_no_retry' and
                card.b.load(PRIVATE/'analysis'/n)['remaining'] == 0 for n in RECORDS), 'live record changed')
    runs = [observe_run(Path(json.loads(raw)['run'])) for raw in records.values()]
    candidate = card.b.plain(DEVICE/'source/uvc/uvc_device.c').decode()
    require('Result rc = usbDsEndpoint_GetReportData(g_isoEndpoint, &report);\n'
            '    Ep0CandidateObserveReports(8,rc,rc ? NULL : &report);' in candidate,
            'deployed poll observer drift')
    poll = candidate[candidate.index('static void _pollIsoProbe(void)'):candidate.index('// UAC (Audio) context')]
    require('g_isoStatus.state = ISO_PROBE_RETAINED;' in poll and
            'r->urb_status >= 3 && r->urb_status <= 5' in poll, 'deployed retention policy drift')
    log = snapshots['card/logfile.txt'].decode()
    matches = re.findall(r'ISO usb module\[0\] BuildID='+BUILD_ID+r' base=([0-9a-f]+) size=([0-9a-f]+)',log)
    require(len(matches) == 1, 'ambiguous saved module identity')
    base, size = (int(x,16) for x in matches[0])
    strict = iso7(bytes.fromhex(runs[-1]['status']['diagnostics_hex']),base,size)
    output.mkdir(mode=0o700)
    # Reassemble the actual patch and compare ALL 22 IPS edits with the card copy.
    module = card.b.plain(PRIVATE/'module/exefs/main')
    patch_dir = output/'patch-rebuild'
    build(validate_module(module),1,Path('/opt/devkitpro/devkitA64/bin'),patch_dir,
          frame_lead=32,mps=256,burst=True,event_audit=True,context_audit=True,
          followup_sia=True,interval=1)
    manifest = card.b.load(patch_dir/'manifest.json')
    disassembly = subprocess.check_output(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump',
                                          '-d',str(patch_dir/'inject.elf')])
    card.pkg.put(output,'patch-disassembly.txt',disassembly)
    rebuilt = card.b.plain(patch_dir/'atmosphere/exefs_patches/SysDVR-ISO'/(BUILD_ID+'.ips'))
    saved = snapshots['card/atmosphere/exefs_patches/SysDVR-ISO/'+BUILD_ID+'.ips']
    require(rebuilt == saved, 'rebuilt patch differs from recovered IPS')
    # Header comments define API units only, not observed wire timing.
    for name in ('IOUSBHostObject.h','IOUSBHostPipe.h'):
        card.pkg.put(output,'sdk/'+name,card.b.plain((SDK/name).resolve()))
    paths = ('patches/iso_burst_context.S','tools/build_patch.py','tools/analyze_a23_iso_retention.py',
             'tools/summarize_run.py','tools/audit_io_usb_host_device.py',
             'host/io_usb_host_sdk_adapter.m','host/io_usb_host_transaction_owner.m',
             'host/io_usb_host_burst_sdk_transport.m','tests/test_a23_iso_retention.py')
    for name in paths:
        card.pkg.put(output,'source/'+name,card.b.plain(ROOT/name))
    card.pkg.put(output,'source/deployed-uvc_device.c',candidate.encode())
    card.pkg.put(output,'source/deployed-ep0_trace_owner.h',card.b.plain(DEVICE/'source/uvc/ep0_trace_owner.h'))
    for name, raw in records.items():
        require(card.b.plain(PRIVATE/'analysis'/name) == raw, 'record changed during audit')
        card.pkg.put(output,'records/'+name,raw)
    result = dict(schema='A23-ISO-retention-window-audit-1', runs=runs,
                  recovered_snapshot_manifest_sha256=card.b.sha(card.b.plain(SNAPSHOT/'SHA256SUMS')),
                  rebuilt_ips_matches_recovered=True, patch_manifest=manifest,
                  latest_context_and_ring_range=strict, parent_sources_checked=len(source_audit['source_hashes']),
                  protected_inputs_checked={k:len(protected[k]) for k in ('production','tickets','offline_records_sha256')},
                  old_live_records_unchanged=True,
                  hardware_test_performed=False, new_usb_requests=0, card_files_written=False,
                  remaining=0, timeout_policy_changed=False,
                  conclusion='Three SDK observations share coherent first-TD CC23 retention; conditional host window begins31 frames after device target. Test overlap hypothesis separately.',
                  **POLICY)
    card.b.write(output/'analysis.json',result)
    card.b.seal(output)
    return dict(output=str(output),entries=len(card.seal_verify(output)),
                manifest_sha256=card.b.sha(card.b.plain(output/'SHA256SUMS')),
                run_count=len(runs),**POLICY)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(audit(parser.parse_args().output),indent=2))
