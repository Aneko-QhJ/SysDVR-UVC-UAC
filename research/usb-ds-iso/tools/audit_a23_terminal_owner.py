"""Offline caller interruption and retained-handle transfer trials."""
from pathlib import Path
from unittest.mock import patch
import argparse
import json
import signal
import shutil
import subprocess
import sys
import tempfile

import a23_terminal_owner as candidate
import audit_a23_terminal_deadline as previous
f, a, BASE = previous.f, previous.a, previous.BASE
seal, sealed, reference = previous.seal, previous.sealed, previous.reference
PARENT = 'A23-terminal-deadline-closeout-20261022'
PARENT_SUM = '205ecaabd5e6bd7ea795857d88b42054e863055a0e4a705e8b8a954293687309'
REVIEW_SUM = 'd94144f0cb66106efaf77ccd3e2b4adc94a9e207c36d83b59a44b6d1498e3696'
NEW = ('tools/a23_terminal_owner.py', 'tools/audit_a23_terminal_owner.py', 'tests/test_a23_terminal_owner.py')
INTERRUPT_POINTS = ('before_spawn', 'after_spawn', 'exchange', 'after_exchange', 'wait', 'after_wait', 'after_decode')
CASES = (*('interrupt/' + phase for phase in INTERRUPT_POINTS),
         'interrupt/cleanup-terminate', 'interrupt/cleanup-wait', 'interrupt/cleanup-close',
         'interrupt/double', 'interrupt/system-exit', 'interrupt/timer',
         'handoff/normal', 'handoff/prepared-interrupt', 'handoff/committed-interrupt')


def sources():
    import audit_a23_pinned_view as old
    w = old.w
    parent = w.A / PARENT
    w.card.seal_verify(parent)
    f.require(f.sha(w.plain(parent / 'SHA256SUMS')) == PARENT_SUM, 'parent pin differs')
    out = previous.sources()
    f.require(out == w.load(parent / 'closeout.json')['source_hashes'] and len(out) == 562, 'prior562 drift')
    for name in NEW:
        key = BASE + name
        f.require(key not in out, 'source overlap')
        out[key] = f.sha(w.plain(w.ROOT / name))
    return dict(sorted(out.items()))


def args_at(directory):
    return previous.previous.previous.args_at(directory)


def semantic(row):
    def normalize(state):
        out = {k: v for k, v in state.items() if k not in ('elapsed_seconds', 'response_size', 'response_sha256')}
        if type(out.get('returncode')) is int and out['returncode'] < 0:
            out['returncode'] = 'terminated_by_signal'
        return out
    out = {**row, 'lifecycle': normalize(row['lifecycle'])}
    if 'pre_finish' in out:
        out['pre_finish'] = normalize(out['pre_finish'])
    return out


def exercise_case(name, directory, args):
    owner = candidate.SamplerOwner()
    primary = SystemExit(23) if name == 'interrupt/system-exit' else KeyboardInterrupt('primary')
    secondary = KeyboardInterrupt('secondary')
    injected = []
    caught = None
    phase = name.removeprefix('interrupt/')
    points = {phase: primary} if phase in INTERRUPT_POINTS else {}
    points.update({'before_terminate': primary} if phase == 'cleanup-terminate' else {})
    points.update({'before_wait_terminate': primary} if phase == 'cleanup-wait' else {})
    points.update({'before_close_1': primary} if phase == 'cleanup-close' else {})
    points.update({'after_spawn': primary, 'before_terminate': secondary} if phase == 'double' else {})
    points.update({'after_spawn': primary} if phase == 'system-exit' else {})
    def checkpoint(point):
        if point in points and point not in injected:
            injected.append(point)
            raise points[point]
        if phase == 'timer' and point == 'exchange':
            signal.setitimer(signal.ITIMER_REAL, 0.1)
    fixture = Path(__file__).resolve().parents[1] / 'tests/a23_terminal_deadline_fixture.py'
    command = [sys.executable, '-B', str(fixture), 'blocked-read'] if phase in ('timer', 'cleanup-terminate', 'cleanup-wait') or name.startswith('handoff/') else None
    timeout = 0.8 if phase.startswith('cleanup-') else 4.0
    timer = signal.getsignal(signal.SIGALRM)
    f.require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'audit requires no existing interval timer')
    if phase == 'timer':
        signal.signal(signal.SIGALRM, signal.default_int_handler)
    try:
        if name.startswith('handoff/'):
            # A trusted wrapper skips real TERM/KILL once and makes wait report EIO.
            # The process is real and remains running; this is not an OS inability to wait.
            real_popen = subprocess.Popen
            def spawn(*values, **kw):
                child = real_popen(*values, **kw)
                original = (child.terminate, child.kill, child.wait)
                child.terminate = lambda: None
                child.kill = lambda: None
                def wait(*args, **kwargs):
                    raise OSError('injected unconfirmed wait')
                child.wait = wait
                child._audit_original = original
                return child
            with patch.object(subprocess, 'Popen', side_effect=spawn):
                result = owner.capture(directory, *args[:2], timeout=0.8, _command=command)
            f.require(result.cache is None and owner.observation()['pending_handle_retained'], 'handoff fixture not pending')
        else:
            try:
                result = owner.capture(directory, *args[:2], timeout=timeout, _command=command, _checkpoint=checkpoint)
            except (KeyboardInterrupt, SystemExit) as exc:
                caught = exc
            f.require(caught is not None, 'expected caller interruption missing ' + name)
            if phase != 'timer':
                f.require(caught is primary, 'primary interruption identity changed')
            else:
                f.require(type(caught) is KeyboardInterrupt, 'timer did not interrupt caller')
    finally:
        if phase == 'timer':
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, timer)
    before = owner.observation()
    same_handle = None
    revoked_rejected = None
    before_commit_owner_kept = None
    after_commit_successor_reachable = None
    if name.startswith('handoff/'):
        original_child = owner._slot.child
        actual = original_child._audit_original
        original_child.terminate, original_child.kill, original_child.wait = actual
        def transfer_hook(point):
            if point == ('handoff_prepared' if name.endswith('prepared-interrupt') else 'handoff_committed') and not name.endswith('/normal'):
                raise primary
        try:
            successor = owner.handoff(_checkpoint=transfer_hook)
        except KeyboardInterrupt as exc:
            f.require(exc is primary, 'handoff interruption identity changed')
            if name.endswith('prepared-interrupt'):
                before_commit_owner_kept = owner._slot.holder is owner
                f.require(before_commit_owner_kept and owner.successor._slot.holder is not owner.successor, 'precommit authority moved')
                successor = owner.handoff()
            else:
                successor = owner.successor
                after_commit_successor_reachable = successor is not None and owner._slot.holder is successor
                f.require(after_commit_successor_reachable, 'committed successor lost')
        same_handle = successor._slot.child is original_child
        try:
            owner.finish()
        except ValueError:
            revoked_rejected = True
        f.require(same_handle and revoked_rejected is True, 'handoff replaced handle or old owner allowed cleanup')
        before = successor.observation()
        final = successor.finish()
    else:
        # Explicit cleanup may be needed if a close checkpoint was interrupted.
        final = owner.finish()
    f.require(final['owner_status'] == 'closed' and not final['pending_handle_retained'] and final['pending_streams'] == 0, 'owned resources still pending')
    f.require(final['accepted'] is False and final['task_complete'] is False and all(final[k] is False for k in candidate.prior.intake.recovery.FALSE), 'interruption promoted sample')
    f.require(final['direct_wait_verified'] is (name != 'interrupt/before_spawn'), 'wait evidence differs')
    return dict(lifecycle=final, pre_finish=before, caught_exception=None if caught is None else type(caught).__name__,
                primary_exception_preserved=(caught is primary) if phase != 'timer' and not name.startswith('handoff/') else None,
                injected_checkpoints=injected, same_runtime_handle_transferred=same_handle,
                revoked_owner_rejected=revoked_rejected, before_commit_owner_kept=before_commit_owner_kept,
                after_commit_successor_reachable=after_commit_successor_reachable)


def exercise(inputs, output):
    output.mkdir(mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix='a23-terminal-owner-', dir='/private/tmp'))
    rows = {}
    jobs = sorted((inputs / 'jobs').iterdir())
    for job in jobs:
        name = 'base/' + job.name
        args = args_at(job)
        directory = previous.previous.prepare(stage / name, args[2])
        owner = candidate.SamplerOwner()
        result = owner.capture(directory, *args[:2], timeout=4.0)
        f.require(result.lifecycle['accepted'] and result.cache == args[2] and result.lifecycle['direct_wait_verified'], 'normal owner sample differs')
        row = dict(lifecycle=result.lifecycle)
        target = output / 'cases' / name
        for filename, raw in result.cache.items():
            a.put(target, 'captured/' + filename, raw)
        a.put(target, 'report.json', f.encode(result.report))
        a.put(target, 'classification.json', f.encode(result.classification))
        a.put(target, 'observation.json', f.encode(row))
        rows[name] = semantic(row)
    args = args_at(inputs / 'jobs/normal')
    for name in CASES:
        directory = previous.previous.prepare(stage / name, args[2])
        row = exercise_case(name, directory, args)
        a.put(output / 'cases' / name, 'observation.json', f.encode(row))
        rows[name] = semantic(row)
    f.require(len(jobs) == 58 and len(CASES) == 16 and len(rows) == 74, 'owner case inventory differs')
    return dict(passed=True, model_cases=74, historical_snapshots=58, interruption_and_handoff_cases=16,
        sampler_child_processes=73, directly_waited_sampler_children=73, semantic=rows,
        staging_directory=str(stage), usb_requests=0, sd_accesses=0, formal_records=0,
        formal_reservations=0, authorization_consumptions=0, permit_claim_invocations=0,
        task_complete=False, **candidate.prior.intake.recovery.FALSE)


def verify(root, pin):
    root = a.canonical(root)
    _, _, digest = sealed(root)
    f.require(f.hex64(pin) and pin == digest, 'external owner review pin differs')
    audit = f.load(root / 'audit.json')
    r = f.load(root / 'results.json')
    f.require(audit['source_count'] == 565 and audit['prior_sources_unchanged'] == 562 and len(audit['source_hashes']) == 565, 'owner source inventory differs')
    for n, expected in audit['source_hashes'].items():
        f.require(f.sha(a.read(root / 'source' / n)) == expected, 'frozen owner source differs')
    expected_names = {'base/' + p.name for p in (root / 'inputs/jobs').iterdir()} | set(CASES)
    f.require(set(r['semantic']) == expected_names and len(expected_names) == 74, 'saved owner inventory differs')
    for name in expected_names:
        target = root / 'work/cases' / name
        row = f.load(target / 'observation.json')
        f.require(semantic(row) == r['semantic'][name], 'saved owner semantic differs')
        state = row['lifecycle']
        f.require(state['owner_status'] == 'closed' and state['pending_streams'] == 0 and not state['pending_handle_retained'] and all(state[k] is False for k in candidate.prior.intake.recovery.FALSE), 'saved owner resource or authority claim differs')
        f.require(state['direct_wait_verified'] is (name != 'interrupt/before_spawn'), 'saved owner wait differs')
        if name.startswith('base/'):
            args = args_at(root / 'inputs/jobs' / name.removeprefix('base/'))
            files = previous.previous.cache(target / 'captured')
            report = f.load(target / 'report.json')
            wire = candidate.prior.encode(dict(schema='A23-terminal-deadline-wire-1',files={n:candidate.prior.base64.b64encode(v).decode() for n,v in files.items()},report=report))
            _, _, classified = candidate.prior.decode_response(wire, *args[:2])
            f.require(files == args[2] and classified == f.load(target / 'classification.json') and f.sha(wire) == state['response_sha256'] and len(wire) == state['response_size'] and state['accepted'], 'saved owner cache differs')
        else:
            f.require(not state['accepted'] and not any((target / n).exists() for n in ('captured','report.json','classification.json')), 'failed owner artifacts present')
            if name.startswith('handoff/'):
                f.require(row['same_runtime_handle_transferred'] is True and row['revoked_owner_rejected'] is True and state['handoffs'] == 1, 'saved transfer claim differs')
            else:
                f.require(state['caller_interrupted'] and row['caught_exception'] in ('KeyboardInterrupt','SystemExit'), 'saved interruption missing')
    f.require(r['sampler_child_processes'] == r['directly_waited_sampler_children'] == 73 and all(r[k] is False for k in candidate.prior.intake.recovery.FALSE), 'owner aggregate differs')
    return r


def run(output):
    import audit_a23_pinned_view as old
    w = old.w
    output = a.canonical(output)
    f.require(not output.exists(), 'new owner review required')
    frozen = sources()
    output.mkdir(mode=0o700)
    for n, expected in frozen.items():
        raw = w.plain(w.b.REPO / n)
        f.require(f.sha(raw) == expected, 'owner source drift')
        a.put(output, 'source/' + n, raw)
    parent = f.load(w.A / PARENT / 'closeout.json')
    review = Path(parent['references']['review']['directory'])
    previous.verify(review, REVIEW_SUM)
    shutil.copytree(review / 'inputs/jobs', output / 'inputs/jobs')
    a.put(output, 'inputs/provenance.json', f.encode(dict(source_review=parent['references']['review'], historical_anchors_and_bytes_reused=True, production_execution=False)))
    try:
        r = exercise(output / 'inputs', output / 'work')
    except BaseException as exc:
        a.put(output, 'failure.json', f.encode(dict(error=type(exc).__name__ + ': ' + str(exc), scope='offline-owner-interruption-only')))
        seal(output)
        raise
    f.require(sources() == frozen, 'owner source drift after trials')
    a.put(output, 'results.json', f.encode(r))
    a.put(output, 'audit.json', f.encode(dict(passed=True, source_count=565, prior_sources_unchanged=562, source_hashes=frozen)))
    seal(output)
    return dict(passed=True, review_sha256=f.sha(a.read(output / 'SHA256SUMS')), model_cases=74, sampler_child_processes=73)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--output', type=Path)
    g.add_argument('--check', type=Path)
    p.add_argument('--expected-sha256')
    args = p.parse_args()
    if args.check and not args.expected_sha256:
        p.error('--check requires --expected-sha256')
    try:
        value = run(args.output) if args.output else verify(args.check, args.expected_sha256)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps(dict(passed=False, error=str(exc))))
        raise SystemExit(2)
    print(json.dumps(value if args.output else dict(passed=True, model_cases=value['model_cases'], process_execution=False), indent=2))
