"""Offline deadline trials and read-only verification of sealed observations."""
from pathlib import Path
import argparse
import json
import shutil
import sys
import tempfile

import a23_terminal_deadline as candidate
import audit_a23_terminal_intake as previous

f, a, BASE = previous.f, previous.a, previous.BASE
seal, sealed, reference = previous.seal, previous.sealed, previous.reference
PARENT = 'A23-terminal-intake-closeout-20261021'
PARENT_SUM = '25a3cb217c72a377b1f3e943fbdc3543fb55070cc2916b648f6acdf07960ab4f'
REVIEW_SUM = '39abf3216cb012e2578074564484e43ad6421c218c033a3bcee33a9dc4c5a577'
NEW = ('tools/a23_terminal_deadline.py', 'tools/a23_terminal_deadline_worker.py',
       'tools/audit_a23_terminal_deadline.py', 'tests/a23_terminal_deadline_fixture.py',
       'tests/test_a23_terminal_deadline.py')
FAULTS = ('blocked-read', 'ignore-term', 'no-input', 'partial', 'after-eof',
          'oversized', 'malformed', 'exit7', 'forged-report')


def sources():
    import audit_a23_pinned_view as old
    w = old.w
    root = w.A / PARENT
    w.card.seal_verify(root)
    f.require(f.sha(w.plain(root / 'SHA256SUMS')) == PARENT_SUM, 'parent pin differs')
    out = previous.sources()
    f.require(out == w.load(root / 'closeout.json')['source_hashes'] and len(out) == 557, 'prior557 drift')
    for name in NEW:
        key = BASE + name
        f.require(key not in out, 'source overlap')
        out[key] = f.sha(w.plain(w.ROOT / name))
    return dict(sorted(out.items()))


def semantic(state):
    return {k: v for k, v in state.items() if k not in ('elapsed_seconds', 'response_sha256', 'response_size')}


def validate(name, state, cache, report, args):
    f.require(state['spawned'] and state['direct_wait_verified'] and not state['pending_handle_retained'], 'sampler child not directly waited')
    f.require(state['task_complete'] is False and all(state[k] is False for k in candidate.intake.recovery.FALSE), 'deadline authority differs')
    accepted = name.startswith('base/')
    f.require(state['accepted'] is accepted, 'unexpected deadline verdict ' + name + ': ' + str(state))
    if accepted:
        f.require(cache == args[2] and report is not None and state['returncode'] == 0 and state['reason'] == 'sampled', 'historical sample differs')
    else:
        f.require(cache is None and report is None, 'failed sampler leaked cache')
        fault = name.removeprefix('fault/')
        timeout = fault in ('blocked-read', 'ignore-term', 'no-input', 'partial', 'after-eof')
        f.require(state['deadline_expired'] is timeout, 'deadline flag differs ' + name)
        if timeout:
            f.require(state['reason'] == 'deadline' and state['terminate_attempted'], 'timeout lifecycle differs')
        if fault == 'ignore-term':
            f.require(state['kill_attempted'] and state['returncode'] == -9, 'SIGKILL escalation not observed')
        if fault in ('blocked-read', 'ignore-term', 'no-input'):
            f.require(state['response_sha256'] == f.sha(b'blocked-read\n'), 'blocked-read checkpoint not reached')
        if fault == 'after-eof':
            f.require(state['response_size'] > 100 and state['reason'] == 'deadline', 'EOF incorrectly accepted without wait')
    return semantic(state)


def exercise(inputs, output):
    output.mkdir(mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix='a23-terminal-deadline-', dir='/private/tmp'))
    rows = {}
    jobs = sorted((inputs / 'jobs').iterdir())
    fixture = Path(__file__).resolve().parents[1] / 'tests/a23_terminal_deadline_fixture.py'
    names = ['base/' + job.name for job in jobs] + ['fault/' + fault for fault in FAULTS]
    for name in names:
        args = previous.previous.args_at(inputs / 'jobs' / (name.removeprefix('base/') if name.startswith('base/') else 'normal'))
        directory = previous.prepare(stage / name, args[2])
        command = None if name.startswith('base/') else [sys.executable, '-B', str(fixture), name.removeprefix('fault/')]
        result = candidate.capture(directory, *args[:2], timeout=4.0 if command is None else 1.5, cleanup_grace=0.2, _command=command)
        state = result.lifecycle
        # A failed wait must keep ownership. Do not launch more cases if it occurs.
        if result.pending_process is not None:
            a.put(output, 'pending-observation.json', f.encode(state))
            raise RuntimeError('child still owned by this invocation; no success or further trials')
        rows[name] = validate(name, state, result.cache, result.report, args)
        target = output / 'cases' / name
        a.put(target, 'lifecycle.json', f.encode(state))
        if result.cache is not None:
            for filename, raw in result.cache.items():
                a.put(target, 'captured/' + filename, raw)
            a.put(target, 'report.json', f.encode(result.report))
            a.put(target, 'classification.json', f.encode(result.classification))
    f.require(len(jobs) == 58 and len(rows) == 67, 'deadline case inventory differs')
    return dict(passed=True, model_cases=67, historical_snapshots=58, fault_cases=9,
                sampler_child_processes=67, directly_waited_sampler_children=67,
                deadline_expiries=5, kill_escalations=1, semantic=rows,
                temporary_directory=str(stage), usb_requests=0, sd_accesses=0,
                formal_records=0, formal_reservations=0, authorization_consumptions=0,
                permit_claim_invocations=0, task_complete=False,
                **candidate.intake.recovery.FALSE)


def verify(root, pin):
    root = a.canonical(root)
    _, _, digest = sealed(root)
    f.require(f.hex64(pin) and pin == digest, 'external review pin differs')
    audit = f.load(root / 'audit.json')
    result = f.load(root / 'results.json')
    f.require(audit['source_count'] == 562 and audit['prior_sources_unchanged'] == 557 and len(audit['source_hashes']) == 562, 'deadline source inventory differs')
    for name, expected in audit['source_hashes'].items():
        f.require(f.sha(a.read(root / 'source' / name)) == expected, 'frozen deadline source differs')
    expected_names = {'base/' + p.name for p in (root / 'inputs/jobs').iterdir()} | {'fault/' + name for name in FAULTS}
    f.require(set(result['semantic']) == expected_names and len(expected_names) == 67, 'saved deadline cases differ')
    for name in expected_names:
        args = previous.previous.args_at(root / 'inputs/jobs' / (name.removeprefix('base/') if name.startswith('base/') else 'normal'))
        directory = root / 'work/cases' / name
        state = f.load(directory / 'lifecycle.json')
        cache = previous.cache(directory / 'captured') if state['accepted'] else None
        report = f.load(directory / 'report.json') if state['accepted'] else None
        f.require(validate(name, state, cache, report, args) == result['semantic'][name], 'saved deadline verdict differs')
        if state['accepted']:
            wire = candidate.encode(dict(schema='A23-terminal-deadline-wire-1', files={n: candidate.base64.b64encode(v).decode() for n, v in cache.items()}, report=report))
            _, _, classified = candidate.decode_response(wire, *args[:2])
            f.require(classified == f.load(directory / 'classification.json'), 'saved cache classification differs')
        else:
            f.require(not (directory / 'captured').exists() and not (directory / 'report.json').exists() and not (directory / 'classification.json').exists(), 'rejected saved artifacts present')
    f.require(result['sampler_child_processes'] == result['directly_waited_sampler_children'] == 67 and result['deadline_expiries'] == 5 and result['kill_escalations'] == 1, 'saved lifecycle totals differ')
    f.require(all(result[k] is False for k in candidate.intake.recovery.FALSE), 'saved authority upgraded')
    return result


def run(output):
    import audit_a23_pinned_view as old
    w = old.w
    output = a.canonical(output)
    f.require(not output.exists(), 'new deadline review required')
    frozen = sources()
    output.mkdir(mode=0o700)
    for name, expected in frozen.items():
        raw = w.plain(w.b.REPO / name)
        f.require(f.sha(raw) == expected, 'deadline source drift')
        a.put(output, 'source/' + name, raw)
    parent = f.load(w.A / PARENT / 'closeout.json')
    review = Path(parent['references']['review']['directory'])
    previous.verify(review, REVIEW_SUM)
    shutil.copytree(review / 'inputs/jobs', output / 'inputs/jobs')
    a.put(output, 'inputs/provenance.json', f.encode(dict(source_review=parent['references']['review'], historical_anchors_and_bytes_reused=True, production_execution=False)))
    try:
        result = exercise(output / 'inputs', output / 'work')
    except Exception as exc:
        a.put(output, 'failure.json', f.encode(dict(error=str(exc), scope='offline-sampler-deadline-only')))
        seal(output)
        raise
    f.require(sources() == frozen, 'deadline source drift after trials')
    a.put(output, 'results.json', f.encode(result))
    a.put(output, 'audit.json', f.encode(dict(passed=True, source_count=562, prior_sources_unchanged=557, source_hashes=frozen)))
    seal(output)
    return dict(passed=True, review_sha256=f.sha(a.read(output / 'SHA256SUMS')), model_cases=67, sampler_child_processes=67)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output', type=Path)
    group.add_argument('--check', type=Path)
    parser.add_argument('--expected-sha256')
    args = parser.parse_args()
    if args.check and not args.expected_sha256:
        parser.error('--check requires --expected-sha256')
    try:
        value = run(args.output) if args.output else verify(args.check, args.expected_sha256)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps(dict(passed=False, error=str(exc))))
        raise SystemExit(2)
    print(json.dumps(value if args.output else dict(passed=True, model_cases=value['model_cases'], process_execution=False), indent=2))
