"""One offline terminal wiring audit; no receiver build or hardware access."""
import argparse
import copy
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import build_a23_live126_interepoch as b
import audit_a23_live91_checked as old
import a23_terminal_observation_consumer as consumer

w = b.w
PARENT = w.A / 'A23-service-observation-closeout-20261025'
PARENT_SUM = '337b6ffb76241561aeef2a0b8a999e9704e9d7ad5820bab54b2b2b6f1a75bf18'
BUILD = w.A / 'A23-live126-interepoch-review-20261025-r1/build'
OLD_NEW = ('host/a23_service_observation.h', 'host/a23_service_observation.c',
           'tests/a23_service_observation_fixture.m')
NEW = ('host/a23_terminal_observation.h', 'host/a23_terminal_observation.m',
       'tests/a23_terminal_observation_fixture.m',
       'tools/a23_terminal_observation_consumer.py', 'tools/audit_a23_terminal_observation.py')
CASES = ('normal', 'bad-guard', 'worker-stop', 'duplicate', 'deadline', 'invalid-boundary',
         'guard-exception', 'recheck-fail', 'recheck-stop', 'poll-fail', 'poll-stop',
         'blocked-tail', 'final-fail', 'final-stop', 'postpass-stop')


def sources():
    old_sources = b.sources() | {'research/usb-ds-iso/' + n: b.sha(w.plain(w.ROOT / n))
                                 for n in OLD_NEW}
    b.require(old_sources == w.load(PARENT / 'source-hashes.json'), 'old654 drift')
    return dict(sorted((old_sources | {'research/usb-ds-iso/' + n: b.sha(w.plain(w.ROOT / n))
                                      for n in NEW}).items()))


def protected():
    paths = [w.A / 'A23-context65-pending.json', w.A / 'A23-live126-interepoch-once-20261025-r2.json']
    values = {str(p): b.sha(w.plain(p)) for p in paths}
    names = ('sequence-reservations32', 'sequence-reservations32-113', 'sequence-reservations32-145',
             'sequence-reservations48-177', 'sequence-reservations48-225', 'sequence-reservations48-273',
             'sequence-reservations48-321', 'sequence-reservations48-369', 'sequence-reservations48-417')
    for first, name in zip((81, 113, 145, 177, 225, 273, 321, 369, 417), names):
        root = w.ROOT / 'private' / name
        hashes = {p.relative_to(root).as_posix(): b.sha(w.plain(p))
                  for p in root.rglob('*') if p.is_file()}
        b.require(hashes == w.load(PARENT / f'namespace{first}-hashes.json'), 'namespace drift')
        values[str(root)] = b.sha(b.encode(hashes))
    return values


def tamper_cases(good, binding, native_rows):
    cases = {}

    def rejected(name, row, expected=binding):
        try:
            consumer.validate(row, expected)
        except ValueError as error:
            cases[name] = dict(rejected=True, reason=str(error))
        else:
            raise ValueError('consumer accepted ' + name)

    for name, row in native_rows.items():
        if name != 'normal':
            rejected('native-' + name, row)
    mutations = {
        'numeric-pass': lambda r: r.update(accepted=1),
        'numeric-busy': lambda r: r.update(busy=0),
        'wrong-binding': lambda r: r['binding'].update(run_id='other'),
        'numeric-model-binding': lambda r: r['binding'].update(model_only=1),
        'wrong-clock': lambda r: r.update(clock='mach_absolute_time'),
        'no-samples': lambda r: r.update(samples_ns=[]),
        'wrong-count': lambda r: r.update(sample_count=r['sample_count'] + 1),
        'missing-return': lambda r: r['events'].pop(1),
        'worker-not-returned': lambda r: r.update(worker_returns=0),
        'sample-not-poll': lambda r: r['samples_ns'].__setitem__(1, r['samples_ns'][1] + 1),
        'reverse-sample': lambda r: r['samples_ns'].__setitem__(1, r['samples_ns'][0] - 1),
        'clock-overflow': lambda r: r['samples_ns'].__setitem__(0, 1 << 64),
        'forged-max': lambda r: r.update(max_gap_ns=0),
        'widened-gap-policy': lambda r: r.update(gap_limit_ns=1_000_000_000),
        'worker-after-return': lambda r: r.update(worker_end_ns=r['events'][1]['ns'] + 1),
        'expired-guard': lambda r: r.update(guard_deadline_ns=r['events'][3]['ns']),
        'final-missing': lambda r: r.update(final_checks=0),
        'unsupported-drain': lambda r: r.update(callback_drain_verified=True),
    }
    for name, change in mutations.items():
        row = copy.deepcopy(good); change(row); rejected(name, row)
    # Internally consistent duration/max/count/event edits still must reject a
    # long final gap, and a too-short observation, independently of producer flags.
    row = copy.deepcopy(good); row['samples_ns'][-1] += 80_000_000
    row['max_gap_ns'] = max(b - a for a, b in zip(row['samples_ns'], row['samples_ns'][1:]))
    for event in row['events'][-4:]:
        event['ns'] += 80_000_000
    rejected('coherent-long-tail', row)
    row = copy.deepcopy(good); start = row['samples_ns'][0]
    span = row['samples_ns'][-1] - start
    def shorter(n):
        return start + (n - start) * 240_000_000 // span
    row['samples_ns'] = [shorter(n) for n in row['samples_ns']]
    for event in row['events']:
        if event['ns'] >= start:
            event['ns'] = shorter(event['ns'])
    row['max_gap_ns'] = max(b - a for a, b in zip(row['samples_ns'], row['samples_ns'][1:]))
    rejected('coherent-short-window', row)
    duplicate = '{"accepted":true,"accepted":false}'
    try:
        json.loads(duplicate, object_pairs_hook=consumer.unique_object)
    except ValueError:
        cases['duplicate-json-key'] = dict(rejected=True)
    else:
        raise ValueError('duplicate JSON accepted')
    return cases


def audit(out):
    b.require(not out.exists(), 'fresh audit output required')
    out.mkdir(mode=0o700)

    def process(command, name, timeout=30):
        p = subprocess.run(command, capture_output=True, timeout=timeout)
        w.card.put(out, name + '.stdout', p.stdout)
        w.card.put(out, name + '.stderr', p.stderr)
        w.write(out / (name + '.process.json'), dict(command=command, returncode=p.returncode,
                                                    creator_wait_verified=True))
        b.require(p.returncode == 0, 'process failed ' + name)
        return p

    try:
        b.require(b.core.verify_seal(PARENT) == PARENT_SUM, 'parent seal drift')
        b.verify(BUILD, current=False)
        b.require(w.plain(w.A / 'A23-context65-pending.json') == w.plain(PARENT / 'ticket.json'), 'ticket drift')
        hashes = sources(); before = protected(); b.require(len(hashes) == 659, 'source count')
        w.write(out / 'source-hashes.json', hashes); w.write(out / 'protected-before.json', before)
        for n in NEW + OLD_NEW[:2]:
            w.card.put(out, 'source/' + n, w.plain(w.ROOT / n))
        raw = w.plain(BUILD / 'generated/live_scope.m').decode()
        w.card.put(out, 'scope_core.m', raw[:raw.index('@implementation A23VerifiedEntryCoordinator')].encode())
        binding = dict(schema='A23-offline-terminal-binding-1', run_id=str(uuid.uuid4()),
                       source_closure_sha256=b.sha(b.encode(hashes)),
                       archived_build_sha256=b.sha(w.plain(BUILD / 'SHA256SUMS')), model_only=True)
        w.write(out / 'expected-binding.json', binding)
        rows = {}
        with tempfile.TemporaryDirectory(prefix='a23-terminal-wiring-', dir='/private/tmp') as temp:
            scratch = Path(temp); template = scratch / 'template'; old.template(BUILD, template)
            for n in (145, 177, 225, 273, 321, 369):
                shutil.copytree(BUILD / f'history/spent{n}', template / f'spent{n}')
            b.require(len(list(template.iterdir())) == 12, 'archival roots differ')
            exe = scratch / 'fixture'
            command = ['clang', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                       '-fobjc-arc', '-fblocks', '-Wall', '-Wextra', '-Werror',
                       '-I' + str(out / 'source/host'), '-I' + str(BUILD),
                       '-I' + str(BUILD / 'source/research/usb-ds-iso/host'), '-framework', 'Foundation',
                       str(out / 'source/host/a23_service_observation.c'),
                       str(out / 'source/host/a23_terminal_observation.m'),
                       str(out / 'source/tests/a23_terminal_observation_fixture.m'),
                       str(out / 'scope_core.m'), '-o', str(exe)]
            process(command, 'compile', 60); w.card.put(out, 'executable', exe.read_bytes())
            link = process(['otool', '-L', str(exe)], 'libraries', 10)
            b.require(b'IOKit.framework' not in link.stdout and b'IOUSBHost' not in link.stdout, 'USB dependency')
            for name in CASES:
                model = scratch / name; shutil.copytree(template, model)
                if name == 'bad-guard':
                    (model / 'repository/research/usb-ds-iso/tools/build_a23_live126_interepoch.py').write_text('changed')
                p = process([str(exe), str(BUILD), str(model), name, str(out / 'expected-binding.json')], name)
                b.require(not p.stderr, 'native stderr ' + name)
                rows[name] = json.loads(p.stdout)
        acceptance = consumer.validate(rows['normal'], binding)
        rejected = tamper_cases(rows['normal'], binding, rows)
        b.require(sources() == hashes and protected() == before, 'protected inputs changed')
        b.guards(); b.require(b.core.verify_seal(PARENT) == PARENT_SUM, 'final parent seal')
        report = dict(schema='A23-terminal-observation-offline-audit-1', parent_manifest_sha256=PARENT_SUM,
                      source_count=659, old654_unchanged=True, native_compiler_jobs=1,
                      native_fixture_processes=len(rows), creator_wait_verified=True,
                      acceptance=acceptance, cases=rows, consumer_rejections=rejected,
                      file_guard_calls=len(CASES)-2, archived126_not_current132=True,
                      model_health_poll_only=True, receiver_integrated=False, usb_requests=0,
                      sd_accesses=0, real_sdk_objects=0, formal_ranges=0, formal_authorizations=0,
                      remaining=0, callback_drain_verified=False, buffer_reuse_verified=False)
        w.write(out / 'report.json', report); w.b.seal(out)
        return dict(seal=b.core.verify_seal(out), cases=len(rows), rejections=len(rejected),
                    max_gap_ns=acceptance['max_gap_ns'])
    except BaseException as error:
        if not (out / 'COMMITTED').exists():
            w.write(out / 'failure.json', dict(type=type(error).__name__, error=str(error)))
            w.b.seal(out)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.output.resolve()), sort_keys=True))
