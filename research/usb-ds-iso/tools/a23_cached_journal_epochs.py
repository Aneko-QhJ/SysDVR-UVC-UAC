"""Pure journal seals and two-epoch packet checks over caller-pinned bytes.

This verifies a defined subset of model relations, not the complete SDK chain,
external builds, process identity, callback drain, or physical provenance.
"""
import struct
import uuid
import a23_pinned_semantics as partial
import analyze_a23_two_epoch_sdk as sdk

view = partial.view
ar, a, f = partial.ar, partial.a, partial.f
HOST = 'journal/envelope/final/inputs/host/'
INPUTS = 'journal/envelope/final/inputs/'
PHASES = ('reserved', 'snapshotted', 'final_started', 'final_frozen',
          'envelope_prepared', 'revalidated', 'completed')
FALSE = {**ar.FALSE, 'supplied_model_chain_complete': False,
         'supplied_sdk_chain_complete': False, 'external_build_verified': False,
         'process_exit_authenticated': False, 'physical_run_authenticated': False,
         'callback_deadlines_verified': False, 'observation_window_verified': False,
         'device_trace_verified': False, 'continuous_streaming_verified': False,
         'production_execution_authorized': False}


def verify_scope(cache, expected, manifest, digest, worker_job):
    f.require(type(cache) is view.PinnedBytes and type(worker_job) is bytes,
              'cached bytes and immutable worker declaration required')
    expected = ar.contract(expected)
    entries = partial.manifest_entries(manifest, digest)
    names = {name[4:] for name in entries if name.startswith('raw/')}
    f.require(names and set(expected['files']) == names and
              expected['directories'] == sorted(set(a.prefixes(names)) | {'empty'}) and
              expected['source_manifest_sha256'] == digest and
              cache.contract_sha256 == f.sha(f.encode(expected)) and
              cache.files == tuple(sorted(names)), 'complete declared raw scope differs')
    raw = {name: cache.read(name) for name in cache.files}
    f.require(all(type(v) is bytes for v in raw.values()) and
              f.encode(a.inventory(raw)) == f.encode(expected['files']), 'cached inventory differs')
    f.require(all(entries['raw/' + n] == f.sha(v) for n, v in raw.items()) and
              entries.get('job.json') == f.sha(worker_job), 'manifest byte binding differs')
    top = {'source-marker', 'journal/attempt.json', 'journal/SOURCE_ATTEMPT',
           'journal/SHA256SUMS', 'journal/COMMITTED'} | {
               'journal/events/%02d.json' % i for i in range(7)}
    f.require(set(raw) == top | {n for n in raw if n.startswith('journal/envelope/')},
              'journal scope missing or unexpected')
    return raw


def sealed_bytes(raw, prefix):
    files = {n[len(prefix):]: v for n, v in raw.items() if n.startswith(prefix)}
    sums, commit = files.pop('SHA256SUMS'), files.pop('COMMITTED')
    f.require(sums == a.sums(files) and commit == (f.sha(sums) + '\n').encode(),
              'nested seal differs')
    return files


def native_metadata(raw):
    f.require(len(raw) <= 16384, 'native metadata size differs')
    row = f.parse(raw)
    # Frozen native JSON is sorted but omits the Python encoder's final newline.
    f.require(type(row) is dict and raw in (f.encode(row), f.encode(row)[:-1]),
              'native metadata encoding differs')
    return row


def consume(cache, expected, manifest, digest, worker_job):
    raw = verify_scope(cache, expected, manifest, digest, worker_job)
    result = dict(schema='A23-cached-journal-epochs-1', byte_scope_verified=True,
                  raw_files=len(raw), classification='inconsistent_model_relations', errors=[],
                  nested_seals_verified=False, journal_commit_verified=False,
                  declared_worker_job_matches_attempt=False,
                  namespace_job_id_consistent=False, epoch_packet_relations_consistent=False,
                  total_effective_bytes=None, epochs=None, **FALSE)
    def check(component, action):
        try:
            return action()
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError, struct.error):
            result['errors'].append(component)
            return None

    def seals():
        prefixes = sorted(n[:-10] for n in raw if n.endswith('SHA256SUMS'))
        required = {'journal/', 'journal/envelope/', 'journal/envelope/final/',
                    HOST+'epoch-0/', HOST+'epoch-1/', HOST+'sdk-receipt/',
                    HOST+'entry-final/', 'journal/envelope/supervision/'}
        f.require(set(prefixes) == required, 'seal coverage differs')
        for prefix in prefixes: sealed_bytes(raw, prefix)
        result['nested_seals_verified'] = True
    check('nested_seals', seals)

    def journal():
        partial.attempt_shape(raw['source-marker'])
        f.require(raw['source-marker'] == raw['journal/attempt.json'] ==
                  raw['journal/SOURCE_ATTEMPT'], 'attempt copies differ')
        previous = f.sha(raw['source-marker'])
        for index, phase in enumerate(PHASES):
            name = 'journal/events/%02d.json' % index
            wanted = dict(schema='A23-collection-event-1', index=index, phase=phase,
                          attempt_sha256=f.sha(raw['source-marker']), previous_sha256=previous)
            f.require(raw[name] == f.encode(wanted), 'journal event link differs')
            previous = f.sha(raw[name])
        sealed_bytes(raw, 'journal/')
        result['journal_commit_verified'] = True
    check('journal', journal)

    def worker():
        job = partial.json_object(worker_job)
        marker = partial.attempt_shape(raw['source-marker'])
        f.require(set(job) == {'schema', 'child_pid', 'control_delivery', 'fault',
                  'forbidden_path', 'journal', 'receiver', 'root', 'supervisor'} and
                  job['schema'] == 'A23-collection-worker-job-1' and
                  type(job['child_pid']) is int and job['child_pid'] == marker['child_pid'] and
                  job['root'] == marker['source'] and job['journal'] == marker['journal'] and
                  job['control_delivery'] == marker['control_delivery'] and
                  job['fault'] == 'normal' and job['forbidden_path'] is None and
                  all(type(job[k]) is str for k in ('receiver', 'supervisor')),
                  'external worker declaration differs')
        result['declared_worker_job_matches_attempt'] = True
    check('worker_declaration', worker)

    def namespace_job():
        info = partial.json_object(raw[INPUTS+'case-info.json'])
        f.require(set(info) == {'job_id'} and type(info['job_id']) is str and
                  str(uuid.UUID(info['job_id'])) == info['job_id'], 'job UUID differs')
        job_prefix = INPUTS+'namespace/jobs/'+info['job_id']+'/'
        declared = partial.json_object(raw[job_prefix+'job.json'])
        all_jobs = {n for n in raw if n.startswith(INPUTS+'namespace/jobs/')}
        f.require(all(n.startswith(job_prefix) for n in all_jobs) and
                  declared.get('schema') == 'A23-shared32-job-1' and
                  declared.get('job_id') == info['job_id'], 'namespace job differs')
        result['namespace_job_id_consistent'] = True
    check('namespace_job', namespace_job)

    def epochs():
        old_after = None
        old_urb = None
        binding = None
        rows = []
        for epoch in (0, 1):
            prefix = HOST+'epoch-'+str(epoch)+'/'
            files = sealed_bytes(raw, prefix)
            f.require(set(files) == {'raw.bin', 'transactions.bin', 'before.bin',
                      'after.bin', 'metadata.json'}, 'epoch inventory differs')
            meta = native_metadata(files['metadata.json'])
            first = 81 + 16*epoch
            f.require(meta.get('schema') == 'A23-two-epoch-sdk-bundle-1' and
                      meta.get('execution_mode') == 'sdk_observation' and
                      type(meta.get('epoch')) is int and meta['epoch'] == epoch and
                      type(meta.get('first_sequence')) is int and meta['first_sequence'] == first and
                      all(meta.get(k) is False for k in ('hardware_verified', 'hardware_entry_enabled',
                                                        'device_trace_verified')) and
                      all(type(meta.get(k)) is int and meta[k] == value for k, value in
                          (('overall_u32', 0), ('callback_count', 1), ('control_count', 1))),
                      'epoch declaration differs')
            current = meta.get('binding')
            f.require(type(current) is dict and current.get('execution_mode') == 'sdk_observation' and
                      type(current.get('first_sequence')) is int and current['first_sequence'] == 81 and
                      type(current.get('session_id')) is str and
                      str(uuid.UUID(current['session_id'])).upper() == current['session_id'].upper(),
                      'epoch binding shape differs')
            if epoch:
                f.require(f.encode(current) == f.encode(binding) and files['before.bin'] == old_after,
                          'epoch continuity differs')
            else:
                sdk.status(files['before.bin'])
                binding = current
            status = sdk.status(files['after.bin'], first)
            f.require(status[5] != old_urb, 'URB ID reused')
            slots = sdk.payload(files['raw.bin'], files['transactions.bin'], first)
            rows.append(dict(epoch=epoch, first_sequence=first, urb_id=status[5],
                             effective_slots=slots, effective_bytes=16*192))
            old_after, old_urb = files['after.bin'], status[5]
        result.update(epoch_packet_relations_consistent=True, epochs=rows, total_effective_bytes=6144)
    check('epoch_packets', epochs)
    if not result['errors']:
        result['classification'] = 'consistent_journal_and_epoch_subset'
    return result


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('view', type=Path)
    parser.add_argument('--expected', type=Path, required=True)
    parser.add_argument('--origin-manifest', type=Path, required=True)
    parser.add_argument('--origin-sha256', required=True)
    parser.add_argument('--worker-job', type=Path, required=True)
    args = parser.parse_args()
    try:
        expected = f.load(args.expected)
        manifest = a.read(args.origin_manifest, 1024*1024)
        worker = a.read(args.worker_job, 16384)
        cache = view.PinnedBytes.load(args.view, expected)
        report = consume(cache, expected, manifest, args.origin_sha256, worker)
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, RecursionError) as error:
        print(json.dumps(dict(byte_scope_verified=False, error=type(error).__name__, **FALSE)))
        raise SystemExit(2)
    print(json.dumps(report, indent=2))
    raise SystemExit(3 if report['errors'] else 0)
