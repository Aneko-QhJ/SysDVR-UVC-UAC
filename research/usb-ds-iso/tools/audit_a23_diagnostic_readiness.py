#!/usr/bin/env python3
"""Bind the latest frozen EP0 candidate and replay prelude/diagnostic boundaries.

Computer-only native execution with injected USB/events/time/joins; no firmware
build, device access, deployment, evidence overwrite or acquisition changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import build_a23_trace_candidate as base
from analyze_ep0_candidate_capture import decode_capture
from analyze_ep0_diagnostic import decode_diagnostic
from workflows.artifacts import verify

ROOT = base.ep0.ROOT
REPO = base.ep0.REPO
SEALED = base.ep0.PRIVATE / 'analysis/A23-log-guard-candidate-review-20261015'
CARD = base.ep0.PRIVATE / 'card-cycles/20261013-174348-A23-IOUSBHost-burst-read'
LABELS = ('dormant', 'window-30s')
MODES = ('healthy', 'replaced', 'speed-error', 'full-speed', 'super-speed',
         'post-failed', 'ack-timeout', 'prestatus-timeout', 'setup-failed',
         'no-iso-event', 'iso-pending', 'video-join-error', 'audio-join-error')
INPUTS = ('tools/audit_a23_diagnostic_readiness.py',
          'tests/a23_diagnostic_readiness_fixture.c',
          'tests/test_a23_diagnostic_readiness.py',
          'tools/build_a23_trace_candidate.py', 'tools/probe_a23_ep0_trace.py',
          'tools/audit_a23_ep0.py', 'tools/audit_a23_hos_setup.py',
          'tools/audit_a23_trace_owner.py',
          'tests/a23_ep0_dispatch_fixture.c', 'tests/a23_hos_setup_fixture.c',
          'tests/a23_ep0_candidate_services.c', 'tests/a23_ep0_candidate_bridge.c',
          'tools/analyze_ep0_candidate_capture.py', 'tools/analyze_ep0_diagnostic.py',
          'tools/analyze_ep0_trace.py', 'tools/workflows/artifacts.py',
          'device/ep0_candidate.c')
SPANS = (('static u8* _ctrlBufferFor(', 'static void _ctrlStallError('),
         ('static void _handleIsoSetup(', '\n#endif\n\nstatic void _handleSetupPacket'),
         ('static void _handleSetupPacket(',
          '// ============================================================================\n// UAC (Audio) Implementation'))
STAGES = ('EVENT', 'CLEAR', 'SETUP', 'ISO_ENTER', 'GUARD', 'SPEED', 'SEQUENCE',
          'ISO_POST', 'CTRL_CLEAR_PRE', 'CTRL_POST', 'CTRL_WAIT', 'CTRL_CLEAR_DONE',
          'CTRL_REPORT', 'CTRL_PARSE', 'ACK', 'STATUS')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract(text, start, end):
    if text.count(start) != 1:
        raise ValueError('Source extraction anchor drift: ' + start)
    first = text.index(start)
    return text[first:text.index(end, first)]


def client_source(text):
    chunks = [extract(text, a, b) for a, b in SPANS]
    chunks.insert(0, extract(text, 'static void _pollIsoProbe(void)',
                             '\n#endif\n\n// UAC (Audio) context'))
    if 'static void _candidateProcessRequests(void)' in text:
        chunks.append(text[text.index('void UvcDeviceProcessRequests(void) {'):])
    return '\n'.join(chunks)


def coverage(text):
    result = {stage: text.count('trace_emit(EP0_T_' + stage + ',') for stage in STAGES}
    if any(not value for value in result.values()):
        raise ValueError('Required trace stage missing')
    for anchor in ('Ep0CandidateAdmissionReady()', 'Ep0CandidateAdmissionBurst(',
                   'Ep0CandidateAdmissionEnd()', 'trace_poll(iface,traceRc)',
                   'rc ? NULL : &setup,traceBegin,svcGetSystemTick()'):
        if anchor not in text:
            raise ValueError('Required candidate hook missing: ' + anchor)
    return result


def native_source(folder, candidate, recipe):
    """Use byte-identical function slices, retaining only modeled services.

    Class handlers are assert-fail stubs; standard GET_INTERFACE and vendor
    requests below cannot invoke them. No native debug trace export is called.
    """
    frozen = folder / 'source/uvc'
    original = (REPO / 'source/uvc/uvc_device.c').read_text()
    text = (frozen / 'uvc_device.c').read_text() if candidate else original
    client = client_source(text)
    generated = base.native_fixture('shared', client, recipe)
    old_runtime = (ROOT / 'device/ep0_candidate.c').read_text().replace(
        '#include "ep0_candidate.h"', '')
    old_runtime = old_runtime.replace('#include "ep0_candidate_capture.h"',
        '#include "research/usb-ds-iso/device/ep0_candidate_capture.h"')
    runtime = (frozen / 'ep0_candidate.c').read_text()
    guard = (frozen / 'ep0_candidate_guard.c').read_text()
    admission = (frozen / 'ep0_request_admission.c').read_text()
    generated = base.trace.replace(generated, old_runtime,
        '#include "ep0_candidate_guard.h"\n#include "ep0_request_admission.h"\n' +
        runtime + '\n' + guard + '\n' + admission)
    # Resolve every candidate header against the frozen source tree, including
    # the two headers originally emitted with repository-relative include paths.
    generated = generated.replace('"research/usb-ds-iso/device/', '"')
    # This is the only extra service fault hook; the actual client is untouched.
    generated = base.trace.replace(generated, '    assert(size==8);',
        '    assert(size==8);\n'
        '    if(get_setup_fail && i->interface_index==2)return 98;')
    generated = generated[:generated.index('int main(')]
    return generated + (ROOT / 'tests/a23_diagnostic_readiness_fixture.c').read_text()


def summarize_trace(trace):
    requests = []
    for request in trace['requests']:
        records = request['records']
        requests.append(dict(interface=request['interface'],
            setup_hex=request['setup_hex'], path=request['path'],
            stages=[r['stage'] for r in records],
            guards=[r['arg0'] for r in records if r['stage'] == 'guard'],
            speed_results=[r['result_u32'] for r in records if r['stage'] == 'speed']))
    return requests


def assess_evidence(decoded):
    """Describe only serialized observations, never infer a USB pass or cause.

    In particular, a valid ownership envelope can contain a speed failure or
    different SETUP reads. Missing interface-2 BURST is not proof of no event.
    """
    result = dict(usb_strict_pass=False, root_cause_confirmed=False,
                  interface2_event_absence_proven=False,
                  shared_setup_overwrite_proven=False)
    if decoded is None:
        return dict(result, observation='capture_unavailable')
    trace = decoded['trace']
    requests = trace['requests']
    if trace['dropped_records'] or trace['invalid_records']:
        return dict(result, observation='trace_incomplete')
    if decoded.get('guard_denials') and decoded.get('guard_reason') == 4:
        return dict(result, observation='candidate_capacity_denial')
    burst = '4154010002000000'
    status = 'c15100000200a800'
    matching = [q for q in requests if q['interface'] == 2 and q['setup_hex'] == burst]
    if matching:
        records = matching[0]['records']
        speed = next((r for r in records if r['stage'] == 'speed'), None)
        guard = next((r for r in records if r['stage'] == 'guard'), None)
        post = next((r for r in records if r['stage'] == 'iso_post'), None)
        ack = next((r for r in records if r['stage'] == 'ack'), None)
        if guard:
            observation = {2: 'busy_or_retained_observed', 3: 'speed_rejection_observed',
                           4: 'non_hs_observed'}.get(guard['arg0'], 'iso_guard_observed')
            if speed and speed['result_u32']:
                observation = 'speed_query_failed'
        elif post:
            observation = ('iso_post_failed' if post['result_u32'] else
                           'ack_failed' if ack and ack['result_u32'] else
                           'post_and_ack_observed' if ack else 'ack_unobserved')
        elif decoded.get('guard_denials'):
            observation = 'candidate_rejection_before_sequence'
        else:
            observation = 'burst_path_incomplete'
        return dict(result, observation=observation)
    for index in range(len(requests) - 2):
        first, second, third = requests[index:index + 3]
        if (first['interface'], second['interface'], third['interface']) == (0, 1, 2):
            if first['setup_hex'] == second['setup_hex'] == burst and third['setup_hex'] == status:
                return dict(result, observation='different_setup_at_interface2')
    if any(q['interface'] == 2 and q['path'] == 'setup_read_failed' for q in requests):
        return dict(result, observation='interface2_setup_read_failed')
    return dict(result, observation='interface2_burst_unobserved')


def window_boundary(main):
    match = re.search(r'ep0_window_init\(&window,svcGetSystemTick\(\),armGetSystemTickFreq\(\),(\d+)\)', main)
    if not match or main.count('ep0_window_init(') != 1:
        raise ValueError('Window initialization drift')
    if not (main.index('Ep0CandidateStart(') < match.start() < main.index('UvcDeviceWaitReady(')):
        raise ValueError('Window start order drift')
    video = extract(main, 'static void VideoStreamThread(void* arg)',
                    '// ============================================================================\n// Audio Streaming Thread')
    if video.count('ep0_window_expired(') != 2:
        raise ValueError('Window expiry check drift')
    if 'UvcDeviceProcessRequests();\n        // Explicit local stop' not in video:
        raise ValueError('Synchronous process boundary drift')
    return dict(window_ms=int(match.group(1)), start_precedes_usb_ready=True,
                stop_checked_after_synchronous_process=True,
                expiry_interrupts_process=False,
                starts_on_host_diagnostic_request=False,
                deadline_covers_host_preparation_when_enabled=True,
                runtime_elapsed_window_measured=False)


def historical_prelude():
    """Count log labels, explicitly without inventing a bus-request queue."""
    log = CARD / 'switch-logfile.txt'
    if sha(log) != '81337a5f62f4357f2045a48a1e0640953cb9bbf940c6c036882b968645a1e7de':
        raise ValueError('First-burst log drift')
    rows = log.read_text().splitlines()
    marker = 'EP0[0]: reqType=0x41 req=0x54 wVal=0x0001 wIdx=0x0002 wLen=0'
    if rows.count(marker) != 1:
        raise ValueError('Unique historical BURST log label missing')
    before = rows[:rows.index(marker)]
    return dict(log_sha256=sha(log), first_burst_interface0_line=rows.index(marker)+1,
        connected_notices=sum(x == 'USB host connected' for x in before),
        disconnected_notices=sum(x == 'USB host disconnected' for x in before),
        set_interface0_labels={str(i):sum(x == f'EP0[{i}]: reqType=0x01 req=0x0b wVal=0x0000 wIdx=0x0001 wLen=0'
                                       for x in before) for i in (0, 1)},
        exact_bus_request_count_proven=False, all_requests_present_proven=False,
        timing_or_capture_origin_authenticated=False)


def run(output):
    output = Path(output)
    if output.exists():
        raise ValueError('Output already exists: ' + str(output))
    sealed_check = verify(SEALED)
    card_check = verify(CARD)
    history = historical_prelude()
    old = json.loads((SEALED / 'audit.json').read_text())
    expected_production = dict(old['production_sources_sha256'])
    expected_production.update(old['source_audit']['production_sources_sha256'])
    production = {n: sha(REPO / n) for n in expected_production}
    if production != expected_production:
        raise ValueError('Production drift from frozen candidate input')
    tickets = {n: sha(base.ep0.PRIVATE / 'analysis' / n)
               for n in old['tickets_sha256']}
    if tickets != old['tickets_sha256']:
        raise ValueError('Ticket drift')
    inputs = {name: sha(ROOT / name) for name in INPUTS}
    output.mkdir(parents=True)
    commands, bindings, rows = [], {}, []
    flags = ['-DISO_PROBE', '-DISO_PROBE_BURST_MODE', '-DISO_PROBE_EVENT_AUDIT',
             '-DISO_PROBE_CONTEXT_AUDIT', '-DISO_PROBE_FOLLOWUP_SIA']
    scenarios = ([(n, 'healthy') for n in range(9)] +
                 [(n, 'reconnect') for n in range(9)] +
                 [(9, 'log-prefix')] +
                 [(0, m) for m in MODES if m != 'healthy'])
    for label in LABELS:
        folder = SEALED / label
        frozen = folder / 'source/uvc'
        recipe = old['builds'][label]['runtime_recipe_digest']
        client = client_source((frozen / 'uvc_device.c').read_text())
        stages = coverage(client)
        if sha(folder / 'full.elf') != old['builds'][label]['elf_sha256']:
            raise ValueError('Candidate ELF/audit mismatch: ' + label)
        bindings[label] = dict(elf_sha256=sha(folder / 'full.elf'),
            recipe_digest=recipe, trace_stages=stages,
            client_slice_sha256=hashlib.sha256(client.encode()).hexdigest(),
            source_files_sha256={str(p.relative_to(folder)): sha(p)
                for p in sorted((folder / 'source').rglob('*')) if p.is_file()},
            class_handler_stubs_unreachable_for_declared_inputs=True,
            actual_class_handlers_executed=False,
            window_boundary=window_boundary((folder / 'source/sysmodule/main.c').read_text()),
            window_checked_in_native_request_replay=False)
        for candidate in (False, True):
            name = label + ('-candidate' if candidate else '-baseline')
            source = output / (name + '.c')
            source.write_text(native_source(folder, candidate, recipe))
            commands.append(base.trace.compile_native(source, output / name,
                            [*flags, '-I' + str(frozen)]))
            for n, mode in scenarios:
                stem = f'{name}-prelude{n}-{mode}'
                normal = output / (stem + '.ownership.bin')
                diagnostic = output / (stem + '.diagnostic.bin')
                row = json.loads(base.owner.command([str(output / name), mode, str(n),
                    '1' if candidate else '0', str(normal), str(diagnostic)]))
                row.update(configuration=label, recipe_digest=recipe)
                decoded = None
                if normal.exists():
                    decoded = decode_capture(normal.read_bytes(), recipe)
                    (output / (stem + '.ownership.json')).write_text(json.dumps(decoded, indent=2)+'\n')
                    row['requests'] = summarize_trace(decoded['trace'])
                if diagnostic.exists():
                    decoded = decode_diagnostic(diagnostic.read_bytes(), recipe)
                    (output / (stem + '.diagnostic.json')).write_text(json.dumps(decoded, indent=2)+'\n')
                    row['requests'] = summarize_trace(decoded['trace'])
                    row['diagnostic_cleanup_authorized'] = decoded['cleanup_authorized']
                row['evidence_assessment'] = assess_evidence(decoded)
                if row['dropped'] or row['invalid'] or row['bound_violations']:
                    raise ValueError('Trace violated a bounded replay: ' + stem)
                rows.append(row)
    if production != {n: sha(REPO / n) for n in production}:
        raise ValueError('Production changed during audit')
    if tickets != {n: sha(base.ep0.PRIVATE / 'analysis' / n) for n in tickets}:
        raise ValueError('Ticket changed during audit')
    if inputs != {n: sha(ROOT / n) for n in inputs}:
        raise ValueError('Audit input changed')
    verify(SEALED)
    verify(CARD)
    for group, hashes, source_root in (('inputs', inputs, ROOT),
                                       ('production-inputs', production, REPO)):
        for name in hashes:
            destination = output / group / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            data = (source_root / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != hashes[name]:
                raise ValueError('Snapshot input drift: ' + name)
            destination.write_bytes(data)
    result = dict(schema='A23-diagnostic-readiness-1', sealed_input=sealed_check,
        historical_card_input=card_check, historical_log_prelude=history,
        source_hashes=inputs, production_sources_sha256=production, tickets_sha256=tickets,
        bindings=bindings, compiler_commands=commands, cases=rows, case_count=len(rows),
        modeled_prelude='0..8 GET_INTERFACE or SET_INTERFACE(0)/disconnect; plus 9 SET_INTERFACE/8 disconnect shape from log; no timing replay',
        actual_class_handlers_executed=False, real_enumeration_measured=False,
        service_results_and_log_delay_injected=True, actual_threads_executed=False,
        diagnostic_native_debug_export_used=False, whole_thread_stack_verified=False,
        new_arm_build=False, arm_executed=False, firmware_packaged=False,
        usb_accessed=False, sd_accessed=False, production_modified=False,
        prior_runtime_modified=False, hardware_verified=False, root_cause_confirmed=False)
    (output / 'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    (output / 'SHA256SUMS').write_text(''.join(sha(p)+'  '+str(p.relative_to(output))+'\n'
        for p in sorted(output.rglob('*')) if p.is_file()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps(dict(output=str(args.output), cases=result['case_count'],
        hardware_verified=False, root_cause_confirmed=False), indent=2))


if __name__ == '__main__':
    main()
