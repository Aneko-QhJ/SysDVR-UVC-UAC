"""Offline exact material scope, cached journal/epoch checks and counterexamples."""
from pathlib import Path
from types import MappingProxyType
import argparse
import json
import os
import shutil
import struct
import sys
import tempfile
import a23_cached_journal_epochs as model

view, ar, a, f = model.view, model.ar, model.a, model.f
PARENT_SUM = '0e8b846096542aeace25fb1909e321924d26132239d68c7f58dd86b40f5a10ab'
NEW = ('tools/a23_cached_journal_epochs.py', 'tools/audit_a23_cached_journal_epochs.py',
       'tests/test_a23_cached_journal_epochs.py')
CASES = {'normal': [], 'late-event-link': ['journal'], 'event-bool-index': ['journal'],
         'copy-mismatch': ['journal'], 'worker-pid-bool': ['worker_declaration'],
         'namespace-job': ['namespace_job'], 'payload': ['epoch_packets'],
         'transaction-count': ['epoch_packets'], 'transaction-offset': ['epoch_packets'],
         'transaction-return': ['epoch_packets'], 'iso7': ['epoch_packets'],
         'before-continuity': ['epoch_packets'], 'urb-reuse': ['epoch_packets'],
         'binding-mismatch': ['epoch_packets'], 'bool-epoch': ['epoch_packets'],
         'missing-epoch-commit': ['nested_seals', 'epoch_packets'],
         'journal-commit': ['nested_seals', 'journal'], 'padding': []}


def rebuild_seals(raw):
    prefixes = sorted((n[:-10] for n in raw if n.endswith('SHA256SUMS')),
                      key=lambda n: len(n.split('/')), reverse=True)
    for prefix in prefixes:
        files = {n[len(prefix):]:v for n,v in raw.items() if n.startswith(prefix) and
                 n not in (prefix+'SHA256SUMS', prefix+'COMMITTED')}
        sums = a.sums(files)
        raw[prefix+'SHA256SUMS'] = sums
        if prefix+'COMMITTED' in raw: raw[prefix+'COMMITTED'] = (f.sha(sums)+'\n').encode()


def variant(base, worker, case):
    raw = dict(base)
    first = model.HOST+'epoch-0/'
    second = model.HOST+'epoch-1/'
    def json_change(name, action):
        row = f.parse(raw[name]); action(row); raw[name] = f.encode(row)
    def word(name, offset, value):
        buf = bytearray(raw[name]); struct.pack_into('<I', buf, offset, value); raw[name] = bytes(buf)
    if case == 'late-event-link': json_change('journal/events/03.json', lambda r: r.update(previous_sha256='0'*64))
    if case == 'event-bool-index': json_change('journal/events/06.json', lambda r: r.update(index=True))
    if case == 'copy-mismatch': raw['journal/attempt.json'] = b'{}\n'
    if case == 'worker-pid-bool':
        row = f.parse(worker); row['child_pid'] = True; worker = f.encode(row)
    if case == 'namespace-job': json_change(model.INPUTS+'case-info.json', lambda r: r.update(job_id='00000000-0000-0000-0000-000000000001'))
    if case == 'payload':
        slots = model.sdk.payload(raw[first+'raw.bin'], raw[first+'transactions.bin'], 81)
        buf = bytearray(raw[first+'raw.bin']); buf[slots[0]*192+6] ^= 1; raw[first+'raw.bin'] = bytes(buf)
    if case == 'padding':
        used = set(model.sdk.payload(raw[first+'raw.bin'], raw[first+'transactions.bin'], 81))
        unused = next(i for i in range(960) if i not in used)
        buf = bytearray(raw[first+'raw.bin']); buf[unused*192] ^= 1; raw[first+'raw.bin'] = bytes(buf)
    if case == 'transaction-count': word(first+'transactions.bin', 12, 191)
    if case == 'transaction-offset': word(first+'transactions.bin', 8, 1)
    if case == 'transaction-return': word(first+'transactions.bin', 0, 1)
    if case == 'iso7': word(first+'after.bin', 56, 0)
    if case == 'before-continuity': raw[second+'before.bin'] = bytes(168)
    if case == 'urb-reuse':
        urb = struct.unpack_from('<I', raw[first+'after.bin'], 20)[0]
        word(second+'after.bin', 20, urb); word(second+'after.bin', 24, urb)
    if case == 'binding-mismatch':
        json_change(second+'metadata.json', lambda r: r['binding'].update(session_id='00000000-0000-0000-0000-000000000001'))
    if case == 'bool-epoch': json_change(second+'metadata.json', lambda r: r.update(epoch=True))
    if case == 'missing-epoch-commit': raw.pop(second+'COMMITTED')
    if case != 'normal': rebuild_seals(raw)
    if case == 'journal-commit': raw['journal/COMMITTED'] = b'0'*64+b'\n'
    return raw, worker


def exercise(bundle, scratch, output):
    output.mkdir()
    base, _ = a.snapshot(bundle/'selection')
    worker = a.read(bundle/'worker-job.json')
    original_manifest = a.read(bundle/'origin-SHA256SUMS')
    rows = {}
    gate = dict(active=False, opens=[], reads=0)
    def guard(event, args):
        if gate['active'] and event == 'open':
            gate['opens'].append(repr(args[0])); raise PermissionError('cache consumer opened a file')
    sys.addaudithook(guard)
    old_read = view.PinnedBytes.read
    def counted(cache, name):
        if gate['active']: gate['reads'] += 1
        return old_read(cache, name)
    view.PinnedBytes.read = counted
    def consume(cache, expected, manifest, digest, declaration):
        gate['active'] = True
        try: return model.consume(cache, expected, manifest, digest, declaration)
        finally: gate['active'] = False
    try:
        for case, errors in CASES.items():
            raw, declaration = variant(base, worker, case)
            manifest = original_manifest if case == 'normal' else a.sums(dict(
                {'raw/'+n:v for n,v in raw.items()}, **{'job.json':declaration}))
            expected = dict(schema='A23-pinned-byte-contract-1', source_manifest_sha256=f.sha(manifest),
                            source_prefix='raw/', files=a.inventory(raw),
                            directories=sorted(set(a.prefixes(raw))|{'empty'}), **ar.FALSE)
            source = scratch/(case+'-source'); source.mkdir()
            for name, value in raw.items(): a.put(source, name, value)
            (source/'empty').mkdir()
            disk = scratch/(case+'-view')
            view.materialize(source, expected, disk)
            cache = view.PinnedBytes.load(disk, expected)
            result = consume(cache, expected, manifest, f.sha(manifest), declaration)
            f.require(result['errors'] == errors, 'case errors differ '+case+': '+str(result['errors']))
            f.require(all(result[k] is False for k in model.FALSE), 'authority promoted')
            dest = output/case; dest.mkdir(); shutil.copytree(disk, dest/'view')
            for name, value in (('expected.json', f.encode(expected)), ('origin-SHA256SUMS', manifest),
                                ('worker-job.json', declaration), ('analysis.json', f.encode(result))):
                a.put(dest, name, value)
            rows[case] = dict(errors=errors, classification=result['classification'],
                              byte_scope_verified=True, disk_view_verified=True,
                              manifest_kind='historical_sealed' if case == 'normal' else 'constructed_model')
            if case == 'normal': normal = cache, expected, manifest, disk, result
        cache, expected, manifest, disk, baseline = normal
        mutations = {}
        for mode in ('rewrite', 'alias-write', 'path-replacement'):
            target = disk/'data'/model.HOST/'epoch-0/raw.bin'
            if mode == 'alias-write':
                alias = scratch/'alias'; os.link(target, alias); alias.write_bytes(b'changed')
            elif mode == 'path-replacement': target.unlink(); target.write_bytes(b'changed')
            else: target.write_bytes(b'changed')
            again = consume(cache, expected, manifest, f.sha(manifest), worker)
            f.require(f.encode(again) == f.encode(baseline), 'cached analysis changed')
            try: view.PinnedBytes.load(disk, expected)
            except (ValueError, OSError): pass
            else: raise ValueError('changed disk accepted')
            mutations[mode] = dict(cached_analysis_unchanged=True, fresh_load_refused=True)
        negative = {}
        altered = dict(base); altered['source-marker'] = b'{'
        wrong_cache = view.PinnedBytes(MappingProxyType(altered), cache.contract_sha256)
        for name, selected, contract, pin, job in (
            ('pin', cache, expected, '0'*64, worker),
            ('worker-bytes', cache, expected, f.sha(manifest), b'{}\n'),
            ('cache-bytes', wrong_cache, expected, f.sha(manifest), worker),
            ('missing-cache-file', view.PinnedBytes(MappingProxyType({n:v for n,v in base.items() if n!='source-marker'}), cache.contract_sha256), expected, f.sha(manifest), worker),
        ):
            try: consume(selected, contract, manifest, pin, job)
            except (ValueError, KeyError, TypeError, UnicodeError): negative[name] = True
            else: raise ValueError('invalid scope accepted '+name)
        f.require(not gate['opens'], 'consumer reopened files')
    finally:
        gate['active'] = False; view.PinnedBytes.read = old_read
    return dict(passed=True, model_cases=len(rows), cases=rows, storage_mutations=mutations,
                scope_rejections=negative, consumer_read_calls=gate['reads'],
                consumer_filesystem_opens=gate['opens'], **model.FALSE)


def sources():
    import audit_a23_pinned_semantics as prior
    import audit_a23_pinned_view as old
    w = old.w; parent = w.A/'A23-pinned-semantics-closeout-20261019'
    w.card.seal_verify(parent)
    f.require(f.sha(w.plain(parent/'SHA256SUMS')) == PARENT_SUM, 'parent differs')
    out = prior.sources()
    f.require(out == w.load(parent/'closeout.json')['source_hashes'] and len(out) == 413, 'prior413 drift')
    for name in NEW:
        key = 'research/usb-ds-iso/'+name; f.require(key not in out, 'source overlap')
        out[key] = f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def run(output):
    import audit_a23_pinned_view as prior
    w = prior.w; output = w.canonical(output)
    f.require(not output.exists(), 'new cached journal review required')
    frozen = sources()
    old = w.load(prior.PARENT/'closeout.json')
    old_review = Path(old['references']['review']['directory'])
    w.card.seal_verify(old_review)
    origin = old_review/'models/normal/first'
    files, dirs, digest = a.sealed(origin)
    raw = {n[4:]:v for n,v in files.items() if n.startswith('raw/')}
    f.require(len(raw) == 92 and sum(map(len, raw.values())) == 516080, 'origin raw scope differs')
    builds = {}
    for role in ('receiver', 'supervisor'):
        root = old_review/'builds'/(role+'-build')
        values, folders, seal = a.sealed(root)
        builds[role] = dict(reference=w.reference(root), files=len(values), directories=len(folders),
                            total_bytes=sum(map(len,values.values())), maximum_file_bytes=max(map(len,values.values())),
                            fits_single_existing_view=len(values)<=128 and max(map(len,values.values()))<=1024*1024)
    output.mkdir(mode=0o700)
    for name, sha in frozen.items():
        value = w.plain(w.b.REPO/name, 2*1024*1024); f.require(f.sha(value)==sha, 'source drift')
        w.card.put(output, 'source/'+name, value)
    bundle = output/'bundle'; bundle.mkdir(); selection = bundle/'selection'; selection.mkdir()
    for name, value in raw.items(): a.put(selection, name, value)
    (selection/'empty').mkdir()
    a.put(bundle, 'worker-job.json', files['job.json'])
    a.put(bundle, 'origin-SHA256SUMS', a.read(origin/'SHA256SUMS'))
    a.put(bundle, 'origin-COMMITTED', a.read(origin/'COMMITTED'))
    catalog = dict(schema='A23-exact-cached-material-scope-1', origin=w.reference(origin),
                   raw_files=a.inventory(raw), raw_file_count=92, raw_total_bytes=516080,
                   raw_directories=len(a.prefixes(raw)), maximum_raw_file_bytes=max(map(len,raw.values())),
                   worker_declaration_origin_entry='job.json', worker_declaration_sha256=f.sha(files['job.json']),
                   full_raw_fits_existing_view=True, existing_limits=dict(files=128, nodes=512, per_file_bytes=1024*1024,total_bytes=16*1024*1024),
                   external_builds=builds, external_build_materials_cached=False,
                   full_sdk_chain_cached_verifier_implemented=False, **model.FALSE)
    w.write(output/'scope-catalog.json', catalog)
    scratch = Path(tempfile.mkdtemp(prefix='a23-cached-epochs-', dir='/private/tmp'))
    result = exercise(bundle, scratch, output/'models')
    f.require(sources()==frozen, 'source drift after review')
    w.write(output/'audit.json', dict(result, schema='A23-cached-journal-epochs-audit-1',
            source_hashes=frozen, source_count=len(frozen), prior_sources_unchanged=413,
            raw_source_files=92, raw_source_bytes=516080, nested_seals=8,
            usb_requests=0, sd_accesses=0, real_sdk_objects=0, formal_records=0,
            formal_reservations=0, native_build_used=False, scratch_retained=str(scratch)))
    w.b.seal(output); w.card.seal_verify(output)
    return dict(reference=w.reference(output), source_count=len(frozen), passed=True,
                model_cases=len(CASES), scope_rejections=4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
