#!/usr/bin/env python3
"""Read saved A23 failure evidence and probe its actual EP0 source with stubs.

No USB/SD operations, firmware changes, acquisition or timeout-policy changes.
--output must be a new directory. Source injection is simulation only.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from analyze_io_usb_host_burst_sdk import analyze as host_audit
from audit_io_usb_host_device import decode_status
from nso2elf import Nso
from workflows.artifacts import ROOT, PRIVATE, verify

REPO = ROOT.parents[1]
RUN = PRIVATE/'runs/A-A23-HS-IOUSBHost-burst-20261013-090224-3c3789da'
CARD = PRIVATE/'card-cycles/20261013-174348-A23-IOUSBHost-burst-read'
COLLECTION = PRIVATE/'collections/A23-IOUSBHost-burst-failed-20261013-174348'
PACKAGE = PRIVATE/'packages-A23-interval1/A'
SCENARIOS = ('normal', 'no-iso-event', 'get-setup-failed', 'speed-error', 'full-speed',
             'super-speed', 'pending', 'retained', 'post-failed', 'ack-post-failed',
             'ack-timeout', 'ack-report-failed', 'ack-urb-failed', 'slow-log-kept',
             'slow-log-dropped', 'slow-log-replaced', 'disconnect-after-post')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def actual_source():
    text = (REPO/'source/uvc/uvc_device.c').read_text()
    # Compile the real functions, including the real synchronous ACK helper.
    spans = [('static u8* _ctrlBufferFor(', 'static void _ctrlStallError('),
             ('static void _handleIsoSetup(', '\n#endif\n\nstatic void _handleSetupPacket'),
             ('static void _handleSetupPacket(', '// ============================================================================\n// UAC (Audio) Implementation')]
    return '\n'.join(text[text.index(a):text.index(b, text.index(a))] for a, b in spans)


def source_probe(output):
    fixture = ROOT/'tests/a23_ep0_dispatch_fixture.c'
    template = fixture.read_text()
    if template.count('/* INSERT_ACTUAL_SOURCE */') != 1:
        raise ValueError('Invalid fixture source marker')
    generated = template.replace('/* INSERT_ACTUAL_SOURCE */', actual_source())
    (output/'probe.c').write_text(generated)
    command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
               '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g',
               '-DISO_PROBE', '-DISO_PROBE_BURST_MODE', '-DISO_PROBE_EVENT_AUDIT',
               '-DISO_PROBE_CONTEXT_AUDIT', '-DISO_PROBE_FOLLOWUP_SIA',
               '-I'+str(REPO), str(output/'probe.c'), '-o', str(output/'probe')]
    subprocess.run(command, check=True, capture_output=True, text=True)
    observations = []
    for name in SCENARIOS:
        result = subprocess.run([str(output/'probe'), name], check=True, capture_output=True, text=True)
        if result.stderr:
            raise ValueError('Unexpected sanitizer/probe stderr: '+result.stderr)
        observations.append(json.loads(result.stdout))
    return dict(kind='actual_source_with_injected_services', compiler_command=command,
                fixture_sha256=sha(fixture), generated_sha256=sha(output/'probe.c'),
                scenario_count=len(observations), scenarios=observations,
                hardware_observation=False, deadline_event_loss_assumed_not_measured=True)


def pfs_member(data, member):
    if data[:4] != b'PFS0':
        raise ValueError('Not a PFS0 NSP')
    count, size = struct.unpack_from('<II', data, 4)
    strings = 16+24*count
    base = strings+size
    for i in range(count):
        offset, length, name, _ = struct.unpack_from('<QQII', data, 16+24*i)
        value = data[strings+name:base].split(b'\0')[0].decode()
        if value == member:
            result = data[base+offset:base+offset+length]
            if len(result) != length:
                raise ValueError('Truncated PFS0 member')
            return result
    raise ValueError('Missing PFS0 member: '+member)


def bind_elf(nso_bytes, elf_bytes):
    if elf_bytes[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Expected little endian ELF64')
    phoff = struct.unpack_from('<Q', elf_bytes, 32)[0]
    entry_size, count = struct.unpack_from('<HH', elf_bytes, 54)
    loads = []
    for i in range(count):
        kind, _, offset, address, _, size, _, _ = struct.unpack_from('<II6Q', elf_bytes, phoff+i*entry_size)
        if kind == 1:
            loads.append((offset, address, size))
    matched = []
    for section in Nso(nso_bytes).sections:
        address, content = section['vaddr'], section['content']
        eligible = [(offset+address-start) for offset, start, size in loads
                    if start <= address and address+len(content) <= start+size]
        if len(eligible) != 1 or elf_bytes[eligible[0]:eligible[0]+len(content)] != content:
            raise ValueError('ELF load bytes do not match deployed NSO')
        matched.append(dict(segment=section['index'], address=address, bytes=len(content),
                            sha256=hashlib.sha256(content).hexdigest()))
    return matched


def audit(output):
    verified = [verify(p) for p in (RUN, CARD, COLLECTION, PACKAGE)]
    validation = json.loads((PACKAGE/'validation.json').read_text())
    source_matches = {}
    for name in ('source/uvc/uvc_device.c', 'source/sysmodule/main.c', 'source/uvc/iso_probe_protocol.h'):
        actual = sha(REPO/name)
        if actual != validation['sources_sha256'][name]:
            raise ValueError('Current source differs from frozen A23: '+name)
        source_matches[name] = actual
    nsp_name = 'atmosphere/contents/00FF0000A53BB666/exefs.nsp'
    nsp = (PACKAGE/nsp_name).read_bytes()
    if nsp != (CARD/'card-files'/nsp_name).read_bytes():
        raise ValueError('Read-back sysmodule differs from frozen package')
    legacy = PRIVATE/'legacy-builds/root'
    nso = pfs_member(nsp, 'main')
    if nso != (legacy/'exefs-iso-A.nso').read_bytes():
        raise ValueError('Legacy NSO is not the read-back sysmodule')
    elf = legacy/'exefs-iso-A.elf'
    segments = bind_elf(nso, elf.read_bytes())
    objdump = '/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump'
    functions = ('VideoStreamThread', 'LogFunctionImpl', 'UvcDeviceProcessRequests',
                 '_serviceSetup.part.0', '_ctrlAck', 'usbDsInterface_GetSetupPacket', 'usbDsGetSpeed')
    for function in functions:
        listing = subprocess.check_output([objdump, '--disassemble='+function, str(elf)], text=True)
        if '<'+function+'>:' not in listing:
            raise ValueError('Missing binary function: '+function)
        (output/(function+'.txt')).write_text(listing)
    host = host_audit(RUN/'host')
    if not host['host_binding_verified'] or host['host_observation_complete']:
        raise ValueError('Saved failed host evidence classification changed')
    rows = [json.loads(line) for line in (RUN/'host/session.jsonl').read_text().splitlines()]
    n, d = (rows[0]['details'][key] for key in ('timebase_numerator', 'timebase_denominator'))
    events = {row['details']['event']: row['details']['details'] for row in rows if row['event']=='adapter'}
    statuses = {phase:decode_status(base64.b64decode(events['status_'+phase]['raw_base64'], validate=True))
                for phase in ('before','after')}
    def ms(begin, end):
        return (end-begin)*n/d/1000000
    before, after = (events['status_'+p]['observation'] for p in ('before','after'))
    timing = dict(status_before_duration_ms=ms(before['begin_ticks'],before['end_ticks']),
                  status_before_end_to_trigger_ms=ms(before['end_ticks'],events['trigger_return']['start_ticks']),
                  trigger_to_control_callback_ms=ms(events['trigger_return']['start_ticks'],events['control_callback']['arrival_ticks']),
                  status_after_duration_ms=ms(after['begin_ticks'],after['end_ticks']),
                  cross_clock_alignment_verified=False, device_stage_durations_measured=False)
    if statuses['before'] != statuses['after'] or statuses['after']['sequence'] != 0:
        raise ValueError('Saved STATUS invariant changed')
    probes = source_probe(output)
    result = dict(schema='A23-EP0-offline-audit-1', usb_accessed=False, sd_accessed=False,
                  acquisition_state_modified=False, firmware_modified=False,
                  root_cause_confirmed=False, fix_verified=False,
                  verified_evidence=verified, frozen_source_matches=source_matches,
                  deployed_nsp_sha256=hashlib.sha256(nsp).hexdigest(),
                  deployed_nso_sha256=hashlib.sha256(nso).hexdigest(), elf_sha256=sha(elf),
                  elf_load_segments_match_deployed_nso=segments,
                  host_binding_verified=True, host_observation_complete=False,
                  statuses=statuses, timing=timing, source_probe=probes,
                  conclusions=dict(sequence_assigned_before_post=True,
                      post_or_ack_failure_alone_cannot_preserve_sequence_zero=True,
                      conditional_on_same_instance_and_valid_status=True,
                      idle_sleep_ns=50000000, followup_event_wait_ns=20000000,
                      synchronous_file_flushes_before_iso_handler=4,
                      device_ack_stage_wait_ns=1000000000, host_control_timeout_ns=16000000,
                      delayed_logging_alone_does_not_explain_unchanged_status=True,
                      exact_unseen_device_branch_unconfirmed=True),
                  provenance=dict(firmware_readback_bytes_bound=True, source_hashes_bound=True,
                      execution_of_all_source_branches_not_proven=True,
                      device_and_host_capture_origin_authenticated=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; refusing to overwrite evidence')
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        result = audit(args.output)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(str(error))
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr or '')
        return 1
    (args.output/'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    (args.output/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(args.output.iterdir()) if p.is_file()))
    print(json.dumps(dict(output=str(args.output.resolve()), scenarios=result['source_probe']['scenario_count'],
                         timing=result['timing'], root_cause_confirmed=False), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
