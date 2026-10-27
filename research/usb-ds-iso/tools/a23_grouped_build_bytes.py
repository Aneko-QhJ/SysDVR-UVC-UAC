"""Offline build byte groups, externally pinned and consumed without file IO.

The caller supplies captured bytes. This module does not capture a live build,
execute it, authenticate its compiler, or grant acquisition permission.
"""
from dataclasses import dataclass
import hashlib
from types import MappingProxyType
import a23_cached_journal_epochs as prior

view, ar, a, f = prior.view, prior.ar, prior.a, prior.f
FALSE = dict(prior.FALSE)
PIECE_BYTES = 512 * 1024
GROUP_BYTES = 8 * 1024 * 1024
MAX_FILES = 1024
MAX_BYTES = 16 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PIECES = MAX_FILES + MAX_BYTES // PIECE_BYTES
MAX_GROUPS = (MAX_PIECES + 127) // 128 + MAX_BYTES // GROUP_BYTES + 1


def manifest(raw, digest):
    entries = prior.partial.manifest_entries(raw, digest)
    f.require(len(entries) <= MAX_FILES, 'build file count limit')
    return entries


def group_contract(files, digest):
    return ar.contract(dict(schema='A23-pinned-byte-contract-1',
                            source_manifest_sha256=digest, source_prefix='raw/',
                            files=files, directories=[], **ar.FALSE))


def prepare(raw, source_manifest, source_digest):
    """Split a bounded, caller-captured build into deterministic byte groups."""
    entries = manifest(source_manifest, source_digest)
    f.require(type(raw) is dict and set(raw) == set(entries), 'build inventory differs')
    f.require(all(type(v) is bytes and len(v) <= MAX_FILE_BYTES for v in raw.values())
              and sum(map(len, raw.values())) <= MAX_BYTES, 'build byte limit')
    groups, files, ordinal = [], {}, 0
    group = count = group_bytes = 0
    for name in sorted(entries):
        value = raw[name]
        f.require(f.sha(value) == entries[name], 'build file digest differs')
        pieces = []
        for offset in range(0, max(1, len(value)), PIECE_BYTES):
            piece = value[offset:offset + PIECE_BYTES]
            if count == 128 or group_bytes + len(piece) > GROUP_BYTES:
                group += 1; count = group_bytes = 0
            if group == len(groups): groups.append({})
            key = 'piece-%06d.bin' % ordinal
            groups[group][key] = piece
            pieces.append(dict(group=group, name=key))
            ordinal += 1
            count += 1; group_bytes += len(piece)
        files[name] = dict(bytes=len(value), sha256=entries[name], pieces=pieces)
    catalog = dict(schema='A23-grouped-build-bytes-1',
                   source_manifest_sha256=source_digest, piece_bytes=PIECE_BYTES,
                   files=files,
                   groups=[group_contract(a.inventory(g), source_digest) for g in groups],
                   **FALSE)
    validate(catalog, f.sha(f.encode(catalog)), source_manifest, source_digest)
    return catalog, groups


def validate(catalog, catalog_digest, source_manifest, source_digest):
    """Require caller-pinned catalog, exact coverage, order, sizes and limits."""
    f.require(type(catalog) is dict and f.hex64(catalog_digest), 'catalog pin required')
    f.require(set(catalog) == {'schema', 'source_manifest_sha256', 'piece_bytes',
                              'files', 'groups', *FALSE}, 'catalog shape differs')
    f.require(f.sha(f.encode(catalog)) == catalog_digest, 'catalog pin differs')
    f.require(catalog['schema'] == 'A23-grouped-build-bytes-1' and
              all(catalog[k] is False for k in FALSE) and
              type(catalog['piece_bytes']) is int and catalog['piece_bytes'] == PIECE_BYTES and
              catalog['source_manifest_sha256'] == source_digest, 'catalog authority differs')
    entries = manifest(source_manifest, source_digest)
    files, groups = catalog['files'], catalog['groups']
    f.require(type(files) is dict and set(files) == set(entries) and
              type(groups) is list and 1 <= len(groups) <= MAX_GROUPS,
              'catalog coverage/group limit differs')
    groups = [ar.contract(g) for g in groups]
    used = [{} for _ in groups]
    total = ordinal = group = count = group_bytes = 0
    for name in sorted(entries):
        row = files[name]
        f.require(type(row) is dict and set(row) == {'bytes', 'sha256', 'pieces'} and
                  type(row['bytes']) is int and 0 <= row['bytes'] <= MAX_FILE_BYTES and
                  row['sha256'] == entries[name] and type(row['pieces']) is list,
                  'catalog file metadata differs')
        size = row['bytes']; total += size
        f.require(total <= MAX_BYTES and
                  len(row['pieces']) == max(1, (size + PIECE_BYTES - 1) // PIECE_BYTES),
                  'catalog byte/piece count limit differs')
        for index, part in enumerate(row['pieces']):
            length = min(PIECE_BYTES, size-index*PIECE_BYTES)
            if count == 128 or group_bytes + length > GROUP_BYTES:
                group += 1; count = group_bytes = 0
            key = 'piece-%06d.bin' % ordinal
            f.require(type(part) is dict and set(part) == {'group', 'name'} and
                      type(part['group']) is int and part['group'] == group and
                      part['name'] == key and group < len(groups),
                      'piece position/coverage differs')
            entry = groups[group]['files'].get(key)
            f.require(entry is not None and entry['bytes'] == length,
                      'piece length differs')
            used[group][key] = entry
            ordinal += 1
            count += 1; group_bytes += length
    f.require(len(groups) == group + 1 and ordinal <= MAX_PIECES,
              'unused/too many build groups')
    for g, wanted in zip(groups, used):
        f.require(f.encode(g) == f.encode(group_contract(wanted, source_digest)),
                  'group contract has unreferenced or mismatched pieces')
    return entries


@dataclass(frozen=True, slots=True)
class BuildBytes:
    _files: object
    source_manifest_sha256: str
    catalog_sha256: str

    @property
    def files(self): return tuple(sorted(self._files))

    def chunks(self, name): return iter(self._files[name])

    def read_small(self, name):
        chunks = self._files[name]
        f.require(sum(map(len, chunks)) <= 1024 * 1024, 'large build file requires chunks')
        return b''.join(chunks)


def consume(caches, catalog, catalog_digest, source_manifest, source_digest):
    """Verify all pieces and original file hashes; never open source paths."""
    entries = validate(catalog, catalog_digest, source_manifest, source_digest)
    f.require(type(caches) is tuple and len(caches) == len(catalog['groups']),
              'cached group count differs')
    for cache, expected in zip(caches, catalog['groups']):
        f.require(type(cache) is view.PinnedBytes and
                  cache.contract_sha256 == f.sha(f.encode(expected)) and
                  cache.files == tuple(sorted(expected['files'])), 'cached group binding differs')
    files = {}
    for name in sorted(entries):
        row = catalog['files'][name]; chunks = []; digest = hashlib.sha256()
        for part in row['pieces']:
            value = caches[part['group']].read(part['name'])
            entry = catalog['groups'][part['group']]['files'][part['name']]
            f.require(type(value) is bytes and len(value) == entry['bytes'] and
                      f.sha(value) == entry['sha256'], 'cached piece bytes differ')
            digest.update(value); chunks.append(value)
        f.require(digest.hexdigest() == entries[name], 'reassembled file digest differs')
        files[name] = tuple(chunks)
    cache = BuildBytes(MappingProxyType(files), source_digest, catalog_digest)
    result = dict(schema='A23-grouped-build-byte-analysis-1',
                  classification='pinned_build_bytes_match_manifest',
                  build_byte_inventory_verified=True, files=len(files),
                  bytes=sum(row['bytes'] for row in catalog['files'].values()),
                  groups=len(caches), pieces=sum(len(v) for v in files.values()),
                  catalog_sha256=catalog_digest, source_manifest_sha256=source_digest,
                  build_semantics_verified=False, **FALSE)
    return cache, result
