#!/usr/bin/env python3
"""Replay the sealed V2 video loop with simulated services; offline planning only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import audit_a23_diagnostic_readiness as ready
from analyze_a23_v2_association import analyze
from analyze_io_usb_host_evidence import require
from workflows.artifacts import verify

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT/'private/analysis/A23-capacity-v2-candidate-review-20261015'
HISTORICAL = ROOT/'private/runs/A-A23-HS-IOUSBHost-burst-20261013-090224-3c3789da'
SOURCES = ('tools/audit_a23_execution_readiness.py', 'tools/analyze_a23_v2_association.py',
           'tests/a23_execution_window_fixture.c', 'tests/test_a23_execution_readiness.py',
           'host/io_usb_host_burst_main.m', 'host/io_usb_host_burst_entry.m',
           'tools/workflows/capture_io_usb_host_burst.py')
SOURCES += tuple('tools/'+name+'.py' for name in (
    'analyze_ep0_candidate_capture_v2', 'analyze_ep0_diagnostic_v2', 'analyze_ep0_session_v2',
    'analyze_ep0_trace_v2', 'analyze_ep0_startup', 'analyze_io_usb_host_burst_sdk',
    'analyze_io_usb_host_burst_sdk_collection', 'analyze_io_usb_host_evidence',
    'analyze_io_usb_host_session', 'audit_io_usb_host_device', 'io_usb_host_runtime_policy',
    'audit_a23_diagnostic_readiness'))
CASES = {'idle': (1000, 1, 0, 0), 'ready_at_expiry': (30000, 1, 0, 0),
         'ready_returns_late': (45000, 1, 0, 0), 'process_returns_late': (1000, 45000, 0, 0),
         'process_crosses_deadline': (29999, 5, 0, 0), 'idle_sleep_crosses_deadline': (29990, 1, 0, 0),
         'capture_returns_late': (1000, 1, 0, 45000), 'separate_trace_start': (1000, 1, 321, 0),
         'very_late_process_return': (1000, 86400000, 0, 0)}


def source_contract(main, host, wrapper, session_file):
    window = ready.window_boundary(main)
    # Fail closed on source drift. This is a scoped source audit, not a compiler proof.
    require(host.count('IOServiceGetMatchingServices(') == 1 and
            'IOServiceAddMatchingNotification' not in host and
            'if(services.count==1 && !exitWanted)' in host and
            '[entry startCandidates:candidates provider:provider]' in host,
            'single-discovery host structure changed')
    finish = main[main.index('if(!Ep0CandidateFinish('):]
    normal = finish[finish.index('bool normal_saved='):]
    require('if(diagnostic_saved)(void)Ep0SessionSaveJoined(video_join,audio_join);' in finish and
            'Ep0SessionSaveJoined(' not in normal and
            '(void)Ep0SessionJoined(ep0CandidateRecipe,exporter,video_join,audio_join,false);' in normal,
            'session persistence exit paths changed')
    require('process.wait(timeout=20)' in wrapper and 'receiver_left_running=True' in wrapper and
            'forced_exit=False' in wrapper, 'wrapper retained-process behavior changed')
    require('!(bytes[16]&8)' in session_file and '!(bytes[16]&64)' in session_file and
            'bytes[72]!=EP0_SINK_ACKNOWLEDGED' in session_file and
            '!(bytes[80]&8)' in session_file, 'session file diagnostic/receipt gate changed')
    return dict(window=window, current_host_has_hotplug_wait=False,
                current_host_discovery_calls=1, current_host_can_be_prearmed_without_device=False,
                normal_exit_writes_ownership=True, normal_exit_writes_session_file=False,
                session_file_requires_diagnostic_and_acknowledged_receipt=True,
                diagnostic_exit_session_save_requires_diagnostic_save=True,
                wrapper_wait_seconds=20, wrapper_wait_is_force_kill_deadline=False,
                window_start_tick_persisted_explicitly=False,
                source_audit_only=True)


def arm_policy(events):
    """Executable design oracle, NOT wired to any receiver or capture entry point.

    A future implementation must register notification first, drain iterator,
    remain passive, reject ambiguous/old identities, and consume at most one
    fresh selection. Timeout or detach must never lead to automatic re-selection.
    """
    state = 'unregistered'
    selected = None
    for event in events:
        if state in ('stopped', 'selected'):
            if event['kind'] == 'detach' and state == 'selected':
                state = 'stopped'
            continue
        kind = event['kind']
        if state == 'unregistered':
            if kind != 'notification_registered':
                state = 'stopped'
            else:
                state = 'draining'
        elif state == 'draining':
            if kind != 'initial_iterator_drained' or event.get('existing_ids'):
                state = 'stopped'
            else:
                state = 'waiting'
        elif kind in ('timeout', 'detach', 'interrupt'):
            state = 'stopped'
        elif kind == 'arrival':
            ids = event.get('fresh_ids')
            if type(ids) is list and len(ids) == 1 and type(ids[0]) is int and ids[0] > 0:
                selected = ids[0]
                state = 'selected'
            else:
                state = 'stopped'
        else:
            state = 'stopped'
    return dict(state=state, selected_registry_id=selected, design_model_only=True,
                receiver_implemented=False, usb_requests=0, attempt_issued=False)


def run(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Refusing existing output: '+str(output))
    seal = verify(CANDIDATE)
    historical_seal = verify(HISTORICAL)
    audit = json.loads((CANDIDATE/'audit.json').read_text())
    snapshots = {name: ready.sha(ROOT/name) for name in SOURCES}
    production = {name: ready.sha(ready.REPO/name) for name in audit['production_sources_sha256']}
    tickets = {name: ready.sha(CANDIDATE.parent/name) for name in audit['tickets_sha256']}
    if production != audit['production_sources_sha256'] or tickets != audit['tickets_sha256']:
        raise ValueError('Production/tickets changed from V2 candidate')
    main_path = CANDIDATE/'window-30s/source/sysmodule/main.c'
    main = main_path.read_text()
    contract = source_contract(main, (ROOT/'host/io_usb_host_burst_main.m').read_text(),
                               (ROOT/'tools/workflows/capture_io_usb_host_burst.py').read_text(),
                               (CANDIDATE/'window-30s/source/uvc/ep0_session_file.c').read_text())
    require('if(candidates.count!=1)return [self preflightFailure:@"missing_or_ambiguous_interface"' in
            (ROOT/'host/io_usb_host_burst_entry.m').read_text(), 'zero-device preflight changed')
    video = ready.extract(main, 'static void VideoStreamThread(void* arg)',
        '// ============================================================================\n// Audio Streaming Thread')
    template = (ROOT/'tests/a23_execution_window_fixture.c').read_text()
    if template.count('/* INSERT_ACTUAL_VIDEO_THREAD */') != 1:
        raise ValueError('Fixture anchor changed')
    output.mkdir(parents=True)
    frozen = output/'inputs'
    for name in SOURCES:
        target = frozen/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    header = CANDIDATE/'window-30s/source/uvc/ep0_candidate_window.h'
    shutil.copyfile(header, output/header.name)
    (output/'actual-video-thread.c').write_text(video)
    source = output/'window.c'
    source.write_text(template.replace('/* INSERT_ACTUAL_VIDEO_THREAD */', video))
    command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
               '-fno-omit-frame-pointer', '-I'+str(output), str(source), '-o', str(output/'window')]
    subprocess.run(command, check=True, capture_output=True, text=True)
    cases = {}
    for name, args in CASES.items():
        process = subprocess.run([str(output/'window'), *map(str,args)], check=True, capture_output=True, text=True)
        cases[name] = json.loads(process.stdout)
    recipe = audit['builds']['window-30s']['runtime_recipe_digest']
    associations = {}
    for mode in ('healthy', 'replaced', 'iso-pending', 'no-iso-event'):
        kind = 'diagnostic' if mode == 'iso-pending' else 'ownership'
        file = CANDIDATE/f'window-30s-candidate-prelude0-{mode}.{kind}.bin'
        associations[mode] = analyze(HISTORICAL/'host', {kind: file}, recipe)
    (output/'associations.json').write_text(json.dumps(associations, indent=2)+'\n')
    for name, old in snapshots.items():
        if ready.sha(ROOT/name) != old:
            raise ValueError('Audit source changed: '+name)
    if production != {name: ready.sha(ready.REPO/name) for name in production} or tickets != {
            name: ready.sha(CANDIDATE.parent/name) for name in tickets}:
        raise ValueError('Protected input changed')
    verify(CANDIDATE)
    verify(HISTORICAL)
    result = dict(schema='A23-execution-readiness-1', source_contract=contract, window_cases=cases,
                  compiler_command=command, source_hashes=snapshots,
                  actual_video_thread_sha256=hashlib.sha256(video.encode()).hexdigest(),
                  window_header_sha256=ready.sha(header), sealed_inputs=[seal,historical_seal],
                  candidate_manifest_sha256=ready.sha(CANDIDATE/'SHA256SUMS'),
                  historical_manifest_sha256=ready.sha(HISTORICAL/'SHA256SUMS'),
                  production_sources_sha256=production, tickets_sha256=tickets,
                  association_scenarios=list(associations),
                  associations_are_deliberately_unrelated_supplied_inputs=True,
                  arm_wait_policy_implemented=False, window_start_observed_on_hardware=False,
                  arm_executed=False, actual_switch_threads_executed=False,
                  usb_accessed=False, sd_accessed=False, attempt_issued=False,
                  hardware_verified=False, root_cause_confirmed=False)
    (output/'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(ready.sha(p)+'  '+str(p.relative_to(output))+'\n'
        for p in sorted(output.rglob('*')) if p.is_file()))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(run(args.output), indent=2))


if __name__ == '__main__':
    main()
