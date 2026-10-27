"""Capture historical build bytes for an offline grouped-cache review."""
from pathlib import Path
import argparse
import json
import shutil
import sys
import tempfile
import a23_grouped_build_bytes as model

view, ar, a, f = model.view, model.ar, model.a, model.f
PARENT = 'A23-cached-epochs-closeout-20261019'
NEW = ('tools/a23_grouped_build_bytes.py', 'tools/audit_a23_grouped_build_bytes.py',
       'tests/test_a23_grouped_build_bytes.py')


def sources():
    import audit_a23_cached_journal_epochs as previous
    import audit_a23_pinned_view as old
    w = old.w
    root = w.A/PARENT
    w.card.seal_verify(root)
    parent = w.load(root/'closeout.json')
    out = previous.sources()
    f.require(out == parent['source_hashes'] and len(out) == 416, 'prior416 drift')
    for name in NEW:
        key = 'research/usb-ds-iso/' + name
        f.require(key not in out, 'source overlap')
        out[key] = f.sha(w.plain(w.ROOT/name))
    return dict(sorted(out.items()))


def checked_consume(caches, catalog, manifest):
    # Audit hook covers only the pure consumer, after loading all bytes.
    gate = dict(active=True, opens=[])
    def hook(event, args):
        if gate['active'] and event == 'open':
            gate['opens'].append(str(args[0]))
            raise ValueError('consumer opened a file')
    sys.addaudithook(hook)
    try:
        result = model.consume(caches, catalog, f.sha(f.encode(catalog)), manifest, f.sha(manifest))
    finally:
        gate['active'] = False
    f.require(not gate['opens'], 'consumer opened paths')
    return result


def replay(root, expected_digest):
    """Load only this review's copies and compare freshly consumed results."""
    root = a.canonical(root)
    _, _, digest = a.sealed(root)
    f.require(f.hex64(expected_digest) and digest == expected_digest,
              'external review manifest pin differs')
    results = {}
    for role in ('receiver', 'supervisor'):
        folder = root/'builds'/role
        catalog = f.load(folder/'catalog.json')
        manifest = a.read(folder/'origin-SHA256SUMS')
        caches = tuple(view.PinnedBytes.load(folder/'views'/('%02d' % i), expected)
                       for i, expected in enumerate(catalog['groups']))
        cache, result = checked_consume(caches, catalog, manifest)
        f.require(f.encode(result) == a.read(folder/'analysis.json'), 'replay result differs')
        # Exact original bytes are retained independently of pieces for replay.
        original, _ = a.snapshot(folder/'original')
        f.require(set(original) == set(cache.files) and
                  all(hash_join(cache.chunks(n)) == f.sha(v) for n,v in original.items()),
                  'replay original digest differs')
        results[role] = result
    return dict(passed=True, builds=results, consumer_filesystem_opens=0, **model.FALSE)


def hash_join(chunks):
    import hashlib
    digest = hashlib.sha256()
    for chunk in chunks: digest.update(chunk)
    return digest.hexdigest()


def run(output):
    import audit_a23_pinned_view as old
    w = old.w
    output = a.canonical(output)
    f.require(not output.exists(), 'new grouped build review required')
    frozen = sources()
    parent = w.load(w.A/PARENT/'closeout.json')
    catalog_root = Path(parent['references']['review']['directory'])
    w.card.seal_verify(catalog_root)
    scope = w.load(catalog_root/'scope-catalog.json')
    output.mkdir(mode=0o700)
    for name, digest in frozen.items():
        value = w.plain(w.b.REPO/name)
        f.require(f.sha(value) == digest, 'source drift')
        a.put(output, 'source/'+name, value)
    rows, mutations = {}, {}
    with tempfile.TemporaryDirectory(prefix='a23-grouped-build-', dir='/private/tmp') as work:
        work = Path(work)
        for role in ('receiver', 'supervisor'):
            reference = scope['external_builds'][role]['reference']
            original_root = Path(reference['directory'])
            raw, _, digest = a.sealed(original_root)
            f.require(digest == reference['manifest_sha256'], 'historical build differs')
            manifest = a.read(original_root/'SHA256SUMS')
            catalog, pieces = model.prepare(raw, manifest, digest)
            folder = output/'builds'/role
            folder.mkdir(parents=True)
            for name, value in raw.items(): a.put(folder, 'original/'+name, value)
            a.put(folder, 'origin-SHA256SUMS', manifest)
            a.put(folder, 'origin-COMMITTED', a.read(original_root/'COMMITTED'))
            a.put(folder, 'catalog.json', f.encode(catalog))
            caches = []
            for i, group in enumerate(pieces):
                source = work/(role+'-source-%02d' % i)
                source.mkdir()
                for name, value in group.items(): a.put(source, name, value)
                disk = work/(role+'-view-%02d' % i)
                view.materialize(source, catalog['groups'][i], disk)
                saved = folder/'views'/('%02d' % i)
                shutil.copytree(disk, saved)
                caches.append(view.PinnedBytes.load(disk, catalog['groups'][i]))
            cache, result = checked_consume(tuple(caches), catalog, manifest)
            f.require(len(cache.files) == len(raw), 'file count differs')
            large = max(raw, key=lambda n:len(raw[n]))
            try: cache.read_small(large)
            except ValueError: pass
            else: raise ValueError('large file bypassed bounded accessor')
            a.put(folder, 'analysis.json', f.encode(result))
            rows[role] = result
            # Mutate only the disposable temporary view; retained views stay sealed.
            disk = work/(role+'-view-00')
            target = disk/'data'/next(iter(catalog['groups'][0]['files']))
            target.write_bytes(b'changed after cache load')
            _, again = checked_consume(tuple(caches), catalog, manifest)
            f.require(again == result, 'loaded cache changed')
            try: view.PinnedBytes.load(disk, catalog['groups'][0])
            except (ValueError, OSError): pass
            else: raise ValueError('modified disk accepted')
            mutations[role] = dict(cache_unchanged=True, fresh_load_refused=True)
    f.require(sources() == frozen, 'source drift after review')
    a.put(output, 'audit.json', f.encode(dict(schema='A23-grouped-build-byte-audit-1',
          passed=True, source_count=len(frozen), prior_sources_unchanged=416,
          source_hashes=frozen, builds=rows, storage_mutations=mutations,
          consumer_filesystem_opens=0, usb_requests=0, sd_accesses=0,
          real_sdk_objects=0, native_executions=0, formal_records=0,
          formal_reservations=0, **model.FALSE)))
    a.seal(output)
    return replay(output, f.sha(a.read(output/'SHA256SUMS')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output', type=Path)
    group.add_argument('--check', type=Path)
    parser.add_argument('--expected-sha256', help='external review SHA256SUMS digest for --check')
    args = parser.parse_args()
    if args.check and not args.expected_sha256: parser.error('--check requires --expected-sha256')
    try: result = run(args.output) if args.output else replay(args.check, args.expected_sha256)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps(dict(passed=False, error=str(exc))))
        raise SystemExit(2)
    print(json.dumps(result, indent=2))
