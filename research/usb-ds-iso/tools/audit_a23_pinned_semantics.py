"""File-only semantic counterexamples, using historical or explicit model pins."""
from pathlib import Path
from types import MappingProxyType
import argparse
import json
import os
import shutil
import sys
import tempfile
import a23_pinned_semantics as model

view = model.view
ar = model.ar
a = model.a
f = model.f
PARENT_SUM = 'f0b7aef1687343aaf477098abaf612702aa9ea17d5fa278b31aa0b2111c8dfed'
NEW = ('tools/a23_pinned_semantics.py', 'tools/audit_a23_pinned_semantics.py',
       'tests/test_a23_pinned_semantics.py')
CASES = {
    'normal': None, 'marker-malformed': 'attempt_shape',
    'marker-duplicate': 'attempt_shape', 'marker-nonobject': 'attempt_shape',
    'marker-deep': 'attempt_shape', 'bool-pid': 'attempt_shape',
    'authority': 'attempt_shape', 'nonce': 'attempt_shape',
    'unknown-attempt-field': 'attempt_shape', 'overlapping-paths': 'attempt_shape',
    'volume-path': 'attempt_shape', 'bool-build-count': 'attempt_shape',
    'mismatched-build': 'attempt_shape', 'attempt-copy': 'attempt_copies',
    'bool-event-index': 'first_event_link', 'event-link': 'first_event_link',
    'unknown-event-field': 'first_event_link', 'job-id': 'job_id_shape',
    'unknown-job-field': 'job_id_shape', 'short-raw': 'raw_size',
    'opaque-raw-change': None, 'nonexistent-logical-roots': None,
}


def variant(base, case):
    raw = dict(base)
    marker = f.parse(raw['source-marker'])
    if case.startswith('marker-'):
        raw['source-marker'] = {
            'marker-malformed': b'{',
            'marker-duplicate': b'{"schema":1,"schema":2}\n',
            'marker-nonobject': b'[]\n',
            'marker-deep': b'[' * 1500 + b'0' + b']' * 1500,
        }[case]
    elif case in ('bool-pid', 'authority', 'nonce', 'unknown-attempt-field',
                  'overlapping-paths', 'volume-path', 'bool-build-count',
                  'mismatched-build', 'nonexistent-logical-roots'):
        if case == 'bool-pid': marker['child_pid'] = True
        if case == 'authority': marker['production_execution_authorized'] = True
        if case == 'nonce': marker['nonce'] = 'invalid'
        if case == 'unknown-attempt-field': marker['hardware_verified'] = True
        if case == 'overlapping-paths': marker['journal'] = marker['source'] + '/child'
        if case == 'volume-path': marker['source'] = '/Volumes/UNOPENED/secret'
        if case == 'bool-build-count': marker['receiver_build']['frozen_source_count'] = True
        if case == 'mismatched-build': marker['supervisor_build']['binary_sha256'] = '0' * 64
        if case == 'nonexistent-logical-roots':
            marker['source'] = '/private/tmp/A23-NOT-OPENED/source'
            marker['journal'] = '/private/tmp/A23-NOT-OPENED/journal'
        raw['source-marker'] = f.encode(marker)
    raw['journal/attempt.json'] = raw['journal/SOURCE_ATTEMPT'] = raw['source-marker']
    event = dict(schema='A23-collection-event-1', index=0, phase='reserved',
                 attempt_sha256=f.sha(raw['source-marker']),
                 previous_sha256=f.sha(raw['source-marker']))
    if case == 'attempt-copy': raw['journal/attempt.json'] = b'{}\n'
    if case == 'bool-event-index': event['index'] = False
    if case == 'event-link': event['previous_sha256'] = '0' * 64
    if case == 'unknown-event-field': event['complete'] = True
    raw['journal/events/00.json'] = f.encode(event)
    if case == 'job-id': raw[model.SELECT[-2]] = f.encode(dict(job_id=True))
    if case == 'unknown-job-field':
        job = f.parse(raw[model.SELECT[-2]]); job['hardware_verified'] = True
        raw[model.SELECT[-2]] = f.encode(job)
    if case == 'short-raw': raw[model.SELECT[-1]] = raw[model.SELECT[-1]][:-1]
    if case == 'opaque-raw-change':
        raw[model.SELECT[-1]] = b'X' + raw[model.SELECT[-1]][1:]
    return raw


def exercise(bundle, scratch, output):
    output.mkdir()
    original = ar.contract(f.load(bundle / 'expected.json'))
    origin = a.read(bundle / 'origin-SHA256SUMS')
    base, _ = a.snapshot(bundle / 'selection')
    rows = {}
    gate = dict(active=False, opens=[], reads=0)
    def audit(event, args):
        if gate['active'] and event == 'open':
            gate['opens'].append(repr(args[0])); raise PermissionError('semantic consumer opened a file')
    sys.addaudithook(audit)
    original_read = view.PinnedBytes.read
    def counted(cache, name):
        if gate['active']: gate['reads'] += 1
        return original_read(cache, name)
    view.PinnedBytes.read = counted
    def consume(cache, expected, manifest, digest):
        gate['active'] = True
        try: return model.consume(cache, expected, manifest, digest)
        finally: gate['active'] = False
    try:
        for case, failure in CASES.items():
            raw = variant(base, case)
            manifest = origin if case == 'normal' else a.sums({'raw/' + n: v for n, v in raw.items()})
            expected = f.parse(f.encode(original))
            expected['source_manifest_sha256'] = f.sha(manifest)
            expected['files'] = a.inventory(raw)
            source = scratch / (case + '-source'); source.mkdir()
            for n, value in raw.items(): a.put(source, n, value)
            (source / 'empty').mkdir()
            disk = scratch / (case + '-view')
            view.materialize(source, expected, disk)
            cached = view.PinnedBytes.load(disk, expected)
            result = consume(cached, expected, manifest, f.sha(manifest))
            f.require(result['errors'] == ([] if failure is None else [failure]),
                      'semantic failure differs: ' + case)
            f.require(result['selected_relations_consistent'] is (failure is None) and
                      all(result[k] is False for k in model.FALSE), 'semantic authority differs')
            dest = output / case; dest.mkdir()
            shutil.copytree(disk, dest / 'view')
            a.put(dest, 'origin-SHA256SUMS', manifest)
            a.put(dest, 'expected.json', f.encode(expected))
            a.put(dest, 'analysis.json', f.encode(result))
            rows[case] = dict(classification=result['classification'], errors=result['errors'],
                              byte_scope_verified=True, disk_view_verified=True,
                              manifest_kind='historical_sealed' if case == 'normal' else 'constructed_model')
            if case == 'normal': normal = (cached, expected, manifest, disk)
        cached, expected, manifest, disk = normal
        baseline = consume(cached, expected, manifest, f.sha(manifest))
        mutations = {}
        for mode in ('rewrite', 'alias-write', 'path-replacement'):
            target = disk / 'data/source-marker'
            if mode == 'alias-write':
                alias = scratch / 'cached-alias'; os.link(target, alias); alias.write_bytes(b'{')
            elif mode == 'path-replacement': target.unlink(); target.write_bytes(b'changed')
            else: target.write_bytes(b'{')
            again = consume(cached, expected, manifest, f.sha(manifest))
            f.require(f.encode(again) == f.encode(baseline), 'cached semantics changed')
            try: view.PinnedBytes.load(disk, expected)
            except (ValueError, OSError): pass
            else: raise ValueError('changed disk accepted')
            mutations[mode] = dict(cached_analysis_unchanged=True, fresh_load_refused=True)
        negative = {}
        changed_data = dict(base); changed_data['source-marker'] = b'{'
        bad_caches = {
            'cache-bytes': view.PinnedBytes(MappingProxyType(changed_data), cached.contract_sha256),
            'cache-missing': view.PinnedBytes(MappingProxyType({n:v for n,v in base.items() if n!='source-marker'}), cached.contract_sha256),
            'cache-extra': view.PinnedBytes(MappingProxyType(dict(base, extra=b'x')), cached.contract_sha256),
            'cache-contract': view.PinnedBytes(MappingProxyType(base), '0' * 64),
        }
        trials = [(name, cache, expected, manifest, f.sha(manifest)) for name, cache in bad_caches.items()]
        trials += [('external-pin', cached, expected, manifest, '0' * 64),
                   ('external-manifest', cached, expected, manifest+b'\n', f.sha(manifest)),
                   ('duplicate-manifest', cached, expected, manifest+manifest.splitlines(keepends=True)[0],
                    f.sha(manifest+manifest.splitlines(keepends=True)[0]))]
        for name, cache, contract, supplied, digest in trials:
            try: consume(cache, contract, supplied, digest)
            except (ValueError, KeyError, TypeError, UnicodeError): negative[name] = True
            else: raise ValueError('bad external/cache scope accepted: ' + name)
        f.require(gate['opens'] == [], 'consumer opened files')
    finally:
        view.PinnedBytes.read = original_read
        gate['active'] = False
    return dict(passed=True, model_cases=len(rows), cases=rows, storage_mutations=mutations,
                scope_rejections=negative, semantic_consumer_read_calls=gate['reads'],
                semantic_consumer_filesystem_opens=gate['opens'], **model.FALSE)


def sources():
    import audit_a23_pinned_view as prior
    w = prior.w
    parent = w.A / 'A23-pinned-view-closeout-20261019'
    w.card.seal_verify(parent)
    f.require(f.sha(w.plain(parent / 'SHA256SUMS')) == PARENT_SUM, 'semantic parent differs')
    old = w.load(parent / 'closeout.json')
    out = prior.sources()
    f.require(out == old['source_hashes'] and len(out) == 410, 'prior410 drift')
    for name in NEW:
        key = 'research/usb-ds-iso/' + name
        f.require(key not in out, 'new source overlap')
        out[key] = f.sha(w.plain(w.ROOT / name))
    return dict(sorted(out.items()))


def run(output):
    import audit_a23_pinned_view as prior
    w = prior.w
    output = w.canonical(output)
    f.require(not output.exists(), 'new semantic review required')
    frozen = sources()
    parent = w.A / 'A23-pinned-view-closeout-20261019'
    close = w.load(parent / 'closeout.json')
    saved = Path(close['references']['review']['directory'])
    w.card.seal_verify(saved)
    prior.source_proof(saved / 'bundle')
    output.mkdir(mode=0o700)
    for name, digest in frozen.items():
        raw = w.plain(w.b.REPO / name, 2*1024*1024)
        f.require(f.sha(raw) == digest, 'source drift')
        w.card.put(output, 'source/' + name, raw)
    shutil.copytree(saved / 'bundle', output / 'bundle')
    scratch = Path(tempfile.mkdtemp(prefix='a23-semantics-', dir='/private/tmp'))
    result = exercise(output / 'bundle', scratch, output / 'models')
    f.require(sources() == frozen, 'source drift after semantic models')
    report = dict(result, schema='A23-pinned-semantics-audit-1', source_hashes=frozen,
                  source_count=len(frozen), prior_sources_unchanged=410,
                  usb_requests=0, sd_accesses=0, real_sdk_objects=0,
                  formal_records=0, formal_reservations=0,
                  native_build_used=False, scratch_retained=str(scratch))
    w.write(output / 'audit.json', report)
    w.b.seal(output); w.card.seal_verify(output)
    return dict(reference=w.reference(output), passed=True, model_cases=result['model_cases'],
                source_count=len(frozen), scope_rejections=len(result['scope_rejections']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
