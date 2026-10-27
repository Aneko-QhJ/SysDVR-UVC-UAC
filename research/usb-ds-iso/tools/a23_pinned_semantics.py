"""Pure, partial semantic inspection of six caller-pinned model byte strings.

No embedded path is opened. A matching manifest digest is an external byte
anchor, not live provenance or a complete journal/USB-chain certificate.
"""
from pathlib import PurePosixPath
import re
import uuid
import a23_pinned_view as view

ar = view.ar
a = ar.a
f = ar.f
SELECT = ('source-marker', 'journal/attempt.json', 'journal/SOURCE_ATTEMPT',
          'journal/events/00.json', 'journal/envelope/final/inputs/case-info.json',
          'journal/envelope/final/inputs/host/epoch-0/raw.bin')
FALSE = {**ar.FALSE, 'production_execution_authorized': False,
         'supplied_model_chain_complete': False, 'journal_commit_verified': False,
         'epoch_payload_verified': False, 'transactions_verified': False,
         'external_build_verified': False, 'job_id_bound_to_attempt': False,
         'physical_run_authenticated': False}


def manifest_entries(raw, digest):
    f.require(type(raw) is bytes and len(raw) <= 1024 * 1024 and
              f.hex64(digest) and f.sha(raw) == digest, 'external manifest pin differs')
    lines = raw.decode('ascii').splitlines()
    f.require(1 <= len(lines) <= 4096, 'manifest entry limit')
    entries = {}
    for line in lines:
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.\-/]+)', line)
        f.require(match is not None, 'manifest entry malformed')
        sha, name = match.groups()
        ar.valid_name(name)
        f.require(name not in entries, 'duplicate manifest name')
        entries[name] = sha
    canonical = ''.join(entries[n] + '  ' + n + '\n' for n in sorted(entries)).encode()
    f.require(raw == canonical, 'manifest is not canonical')
    return entries


def json_object(raw):
    f.require(len(raw) <= 16384, 'semantic JSON limit')
    value = f.parse(raw)
    f.require(type(value) is dict and f.encode(value) == raw, 'noncanonical JSON object')
    return value


def attempt_shape(raw):
    row = json_object(raw)
    keys = {'schema', 'nonce', 'source', 'journal', 'receiver_build',
            'supervisor_build', 'child_pid', 'control_delivery', 'model_only',
            'production_execution_authorized'}
    f.require(set(row) == keys and row['schema'] == 'A23-collection-attempt-1' and
              f.hex64(row['nonce']), 'attempt schema/nonce differs')
    f.require(row['model_only'] is True and row['production_execution_authorized'] is False
              and type(row['child_pid']) is int and 0 < row['child_pid'] < 2**31 and
              row['control_delivery'] in ('none', 'whole_written', 'partial_or_failed'),
              'attempt authority/identity differs')
    for key in ('source', 'journal'):
        name = row[key]
        f.require(type(name) is str and len(name) <= 4096, 'logical path type/size differs')
        path = PurePosixPath(name)  # Lexical only: never resolve/stat/open this string.
        f.require(str(path) == name and path.is_relative_to('/private/tmp') and
                  len(path.parts) > 3 and '..' not in path.parts, 'logical path differs')
    f.require(row['source'] != row['journal'], 'logical roots overlap')
    left, right = PurePosixPath(row['source']), PurePosixPath(row['journal'])
    f.require(not left.is_relative_to(right) and not right.is_relative_to(left),
              'logical roots overlap')
    for key, count, digests in (
        ('receiver_build', 'frozen_source_count',
         {'descriptor_sha256', 'manifest_sha256', 'receiver_sha256'}),
        ('supervisor_build', 'source_count', {'binary_sha256', 'manifest_sha256'})):
        record = row[key]
        f.require(type(record) is dict and set(record) == digests | {count} and
                  type(record[count]) is int and 1 <= record[count] <= 4096 and
                  all(f.hex64(record[n]) for n in digests), 'build reference shape differs')
    f.require(row['receiver_build']['receiver_sha256'] ==
              row['supervisor_build']['binary_sha256'] and
              row['receiver_build']['frozen_source_count'] ==
              row['supervisor_build']['source_count'], 'declared build references differ')
    return row


def consume(cache, expected, origin_manifest, origin_sha256):
    """Return partial findings; reject byte-scope failures before parsing content."""
    f.require(type(cache) is view.PinnedBytes, 'pinned byte cache required')
    expected = ar.contract(expected)
    f.require(set(expected['files']) == set(SELECT) and
              expected['directories'] == sorted(set(a.prefixes(SELECT)) | {'empty'}),
              'six-file semantic scope differs')
    f.require(cache.contract_sha256 == f.sha(f.encode(expected)) and
              cache.files == tuple(sorted(SELECT)), 'cached contract differs')
    entries = manifest_entries(origin_manifest, origin_sha256)
    f.require(expected['source_manifest_sha256'] == origin_sha256,
              'contract does not bind external manifest pin')
    raw = {n: cache.read(n) for n in SELECT}
    f.require(all(type(v) is bytes for v in raw.values()) and
              f.encode(a.inventory(raw)) == f.encode(expected['files']),
              'cached bytes differ from external contract')
    for name, value in raw.items():
        f.require(entries.get('raw/' + name) == f.sha(value),
                  'selected bytes not bound by external manifest')
    result = dict(schema='A23-pinned-partial-semantics-1', byte_scope_verified=True,
                  external_manifest_pin_verified=True, selected_files=6,
                  classification='inconsistent_selected_model_bytes',
                  selected_relations_consistent=False, errors=[],
                  raw_bytes=len(raw[SELECT[-1]]), raw_sha256=f.sha(raw[SELECT[-1]]),
                  raw_interpretation='opaque_without_transactions_or_status', **FALSE)

    def check(component, action):
        try:
            return action()
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
            result['errors'].append(component)
            return None

    attempt = check('attempt_shape', lambda: attempt_shape(raw['source-marker']))

    def copies():
        f.require(raw['source-marker'] == raw['journal/attempt.json'] ==
                  raw['journal/SOURCE_ATTEMPT'], 'attempt copies differ')
    check('attempt_copies', copies)

    def first_event():
        event = json_object(raw['journal/events/00.json'])
        wanted = dict(schema='A23-collection-event-1', index=0, phase='reserved',
                      attempt_sha256=f.sha(raw['source-marker']),
                      previous_sha256=f.sha(raw['source-marker']))
        f.require(f.encode(event) == f.encode(wanted), 'first event link differs')
    check('first_event_link', first_event)

    def job():
        row = json_object(raw[SELECT[-2]])
        f.require(set(row) == {'job_id'} and type(row['job_id']) is str and
                  str(uuid.UUID(row['job_id'])) == row['job_id'], 'job UUID differs')
        return row['job_id']
    job_id = check('job_id_shape', job)
    check('raw_size', lambda: f.require(len(raw[SELECT[-1]]) == 184320, 'raw size differs'))
    if not result['errors']:
        result.update(classification='consistent_partial_model_bytes',
                      selected_relations_consistent=True,
                      declared_child_pid=attempt['child_pid'], declared_job_id=job_id)
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
    args = parser.parse_args()
    try:
        contract = f.load(args.expected)
        origin = a.read(args.origin_manifest, 1024 * 1024)
        cached = view.PinnedBytes.load(args.view, contract)
        report = consume(cached, contract, origin, args.origin_sha256)
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, RecursionError) as error:
        print(json.dumps(dict(byte_scope_verified=False, error=type(error).__name__, **FALSE)))
        raise SystemExit(2)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['selected_relations_consistent'] else 3)
