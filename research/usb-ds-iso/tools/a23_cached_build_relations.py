"""Pure structural build and journal-reference checks on pinned model bytes.

Compiler provenance, executable semantics, full SDK receipts and live process
identity are outside this subset. Embedded paths are compared lexically only.
"""
import hashlib
from pathlib import PurePosixPath
import a23_grouped_build_bytes as grouped

prior = grouped.prior
view, ar, a, f = grouped.view, grouped.ar, grouped.a, grouped.f
FALSE = {**grouped.FALSE, 'compiler_provenance_verified': False,
         'executable_semantics_verified': False, 'full_descriptor_semantics_verified': False}
DESCRIPTOR_KEYS = {'schema', 'description', 'source_hashes', 'workflow_source_sha256',
                   'baseline_directory', 'baseline_files', 'baseline_manifest_sha256',
                   'baseline_inventory_sha256', 'history_files', 'history_sha256',
                   'recovery_index', 'device_binding_sha256', 'recipe_sha256',
                   'live_roots', 'parent_manifest_sha256'}
DESCRIPTION = dict(schema='A23-broker-failure-model-description-1', model_only=True,
                   modes=['--model'], acquisition_mode_implemented=False,
                   formal_issuance_available=False, hardware_entry_enabled=False)


def json_object(raw):
    f.require(type(raw) is bytes and len(raw) <= 1024*1024, 'JSON byte limit/type differs')
    value = f.parse(raw)
    f.require(type(value) is dict and raw == f.encode(value), 'canonical JSON object required')
    return value


def logical_path(value):
    f.require(type(value) is str and 1 <= len(value) <= 4096, 'logical path type/length differs')
    path = PurePosixPath(value)
    f.require(path.is_absolute() and str(path) == value and '..' not in path.parts,
              'logical path is not canonical')
    return path


def digest_file(cache, name):
    digest = hashlib.sha256()
    for piece in cache.chunks(name): digest.update(piece)
    return digest.hexdigest()


def hash_table(value):
    f.require(type(value) is dict and 1 <= len(value) <= 1024, 'hash table size/type differs')
    for name, digest in value.items():
        ar.valid_name(name)
        f.require(f.hex64(digest), 'member digest type differs')
    return value


def verify_receiver(cache):
    descriptor_raw = cache.read_small('descriptor.json')
    d = json_object(descriptor_raw)
    f.require(set(d) == DESCRIPTOR_KEYS and d['schema'] == 'A23-verified-entry-descriptor-1',
              'descriptor shape differs')
    f.require(f.encode(d['description']) == f.encode(DESCRIPTION), 'descriptor model authority differs')
    for key in ('workflow_source_sha256', 'baseline_manifest_sha256', 'baseline_inventory_sha256',
                'history_sha256', 'device_binding_sha256', 'recipe_sha256', 'parent_manifest_sha256'):
        f.require(f.hex64(d[key]), 'descriptor digest type differs')
    ar.valid_name(d['baseline_directory'])
    f.require('/' not in d['baseline_directory'], 'baseline directory is not a single name')
    f.require(type(d['live_roots']) is dict and
              set(d['live_roots']) == {'repository', 'cards', 'ledger', 'records'}, 'live root declaration differs')
    for value in d['live_roots'].values(): logical_path(value)
    expected = {'descriptor.json', 'a23_verified_binding.h', 'verified-entry',
                'binary.json', 'compile.log', 'build-command.json'}
    for prefix, key in (('source', 'source_hashes'), ('baseline', 'baseline_files'),
                        ('history', 'history_files'), ('recovery-index', 'recovery_index')):
        for name, digest in hash_table(d[key]).items():
            member = prefix+'/'+name
            f.require(digest_file(cache, member) == digest, 'frozen '+prefix+' member differs')
            expected.add(member)
    f.require(set(cache.files) == expected, 'receiver file coverage differs')
    header = hashlib.sha256(b'static const unsigned char A23VerifiedDescriptor[]={')
    for index, value in enumerate(descriptor_raw):
        header.update((b',' if index else b'') + str(value).encode())
    header.update(b'};\n')
    f.require(digest_file(cache, 'a23_verified_binding.h') == header.hexdigest(), 'descriptor header differs')
    binary = json_object(cache.read_small('binary.json'))
    wanted = dict(schema='A23-verified-entry-binary-1',
                  receiver_sha256=digest_file(cache, 'verified-entry'),
                  descriptor_sha256=f.sha(descriptor_raw))
    f.require(f.encode(binary) == f.encode(wanted), 'receiver binary record differs')
    f.require(d['workflow_source_sha256'] == f.sha(f.encode(d['source_hashes'])), 'workflow source digest differs')
    baseline_sums = ''.join(h+'  '+n+'\n' for n,h in sorted(d['baseline_files'].items())).encode()
    f.require(f.sha(baseline_sums) == d['baseline_manifest_sha256'], 'baseline manifest differs')
    inventory = {}
    for name in d['baseline_files']:
        if name.startswith('card/'):
            member = 'baseline/'+name
            inventory[name[5:]] = dict(bytes=sum(map(len, cache.chunks(member))),
                                       sha256=d['baseline_files'][name])
    f.require(len(inventory) == 69 and f.sha(f.encode(inventory)) == d['baseline_inventory_sha256'],
              'baseline69 inventory differs')
    scope = dict(schema='A23-shared32-scope-1',
                 **{k:d[k] for k in ('baseline_manifest_sha256', 'baseline_inventory_sha256',
                                    'workflow_source_sha256', 'device_binding_sha256',
                                    'recipe_sha256', 'history_sha256')},
                 build_manifest_sha256=cache.source_manifest_sha256,
                 receiver_sha256=wanted['receiver_sha256'], first_sequence=81, last_sequence=112,
                 formal_issuance_available=False, acquisition_mode_implemented=False,
                 hardware_entry_enabled=False)
    reference = dict(manifest_sha256=cache.source_manifest_sha256,
                     descriptor_sha256=wanted['descriptor_sha256'],
                     receiver_sha256=wanted['receiver_sha256'],
                     frozen_source_count=len(d['source_hashes']))
    return dict(scope=scope, reference=reference, sources=d['source_hashes'],
                member_counts={k:len(d[k]) for k in ('source_hashes', 'baseline_files', 'history_files', 'recovery_index')})


def verify_supervisor(cache):
    row = json_object(cache.read_small('build.json'))
    f.require(set(row) == {'schema', 'source_hashes', 'binary_sha256', 'model_only'} and
              row['schema'] == 'A23-supervisor-model-build-1' and row['model_only'] is True,
              'supervisor model shape/authority differs')
    sources = hash_table(row['source_hashes'])
    expected = {'build.json', 'compile.log', 'model-child'} | {'source/'+n for n in sources}
    f.require(set(cache.files) == expected, 'supervisor file coverage differs')
    for name, digest in sources.items():
        f.require(digest_file(cache, 'source/'+name) == digest, 'supervisor source member differs')
    f.require(f.hex64(row['binary_sha256']) and digest_file(cache, 'model-child') == row['binary_sha256'],
              'supervisor binary record differs')
    return dict(reference=dict(manifest_sha256=cache.source_manifest_sha256,
                               binary_sha256=row['binary_sha256'], source_count=len(sources)), sources=sources)


def consume(receiver, supervisor, journal, link_bytes, link_digest):
    """Inputs are grouped-cache tuples, a journal tuple and external link pin."""
    f.require(type(link_bytes) is bytes and len(link_bytes) <= 16384 and
              f.hex64(link_digest) and f.sha(link_bytes) == link_digest, 'external link pin differs')
    links = json_object(link_bytes)
    f.require(set(links) == {'schema', 'builds', 'journal_manifest_sha256', *FALSE} and
              links['schema'] == 'A23-cached-build-links-1' and
              all(links[k] is False for k in FALSE) and type(links['builds']) is dict and
              set(links['builds']) == {'receiver', 'supervisor'}, 'external link shape/authority differs')
    caches = {}
    for role, spec in (('receiver', receiver), ('supervisor', supervisor)):
        cache, _ = grouped.consume(*spec)
        link = links['builds'][role]
        f.require(type(link) is dict and set(link) == {'logical_root', 'manifest_sha256', 'catalog_sha256'} and
                  link['manifest_sha256'] == cache.source_manifest_sha256 and
                  link['catalog_sha256'] == cache.catalog_sha256, 'external build role differs')
        logical_path(link['logical_root'])
        caches[role] = cache
    f.require(links['builds']['receiver']['logical_root'] != links['builds']['supervisor']['logical_root'],
              'logical build roles overlap')
    f.require(type(journal) is tuple and len(journal) == 5 and
              journal[3] == links['journal_manifest_sha256'], 'external journal role differs')
    raw = prior.verify_scope(*journal)
    subset = prior.consume(*journal)
    result = dict(schema='A23-cached-build-relations-1', classification='inconsistent_build_subset',
                  errors=[], reasons={}, receiver_structure_consistent=False,
                  supervisor_structure_consistent=False, role_pair_consistent=False,
                  journal_subset_consistent=not subset['errors'], build_references_consistent=False,
                  references={}, **FALSE)
    def check(component, action):
        try: return action()
        except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
            result['errors'].append(component)
            result['reasons'][component] = str(exc)
            return None
    r = check('receiver', lambda:verify_receiver(caches['receiver']))
    s = check('supervisor', lambda:verify_supervisor(caches['supervisor']))
    result['receiver_structure_consistent'] = r is not None
    result['supervisor_structure_consistent'] = s is not None
    if subset['errors']:
        result['errors'].append('journal_subset'); result['reasons']['journal_subset'] = ','.join(subset['errors'])
    def pair():
        f.require(f.encode(r['sources']) == f.encode(s['sources']) and
                  r['reference']['receiver_sha256'] == s['reference']['binary_sha256'],
                  'model build source/binary roles differ')
        return True
    if r and s: result['role_pair_consistent'] = bool(check('role_pair', pair))
    def joined():
        def obj(name): return json_object(raw[name])
        marker = prior.partial.attempt_shape(raw['source-marker'])
        worker = json_object(journal[4])
        for role in ('receiver', 'supervisor'):
            f.require(worker[role] == links['builds'][role]['logical_root'], 'worker logical build differs')
        envelope = obj('journal/envelope/envelope.json')
        for record in (marker, envelope):
            f.require(f.encode(record['receiver_build']) == f.encode(r['reference']) and
                      f.encode(record['supervisor_build']) == f.encode(s['reference']), 'declared build reference differs')
        final = obj('journal/envelope/final/collection.json')
        f.require(f.encode(final['build_reference']) == f.encode(r['reference']), 'final build reference differs')
        for name in ('handoff.json', 'handoff-original.json'):
            f.require(f.encode(obj('journal/envelope/supervision/'+name)['build']) == f.encode(s['reference']),
                      'supervision build reference differs')
        scope = obj(prior.INPUTS+'namespace/scope.json')
        f.require(f.encode(scope) == f.encode(r['scope']), 'namespace build scope differs')
        configs = [obj(prior.INPUTS+'config.json')['binding'],
                   prior.native_metadata(raw[prior.HOST+'entry-current.json'])['binding'],
                   prior.native_metadata(raw[prior.HOST+'entry-final/entry.json'])['binding']]
        for binding in configs:
            f.require(type(binding) is dict and set(binding) == {'schema', 'authorization_receipt_sha256',
                      'build_manifest_sha256', 'receiver_sha256', 'first_sequence', 'last_sequence'} and
                      binding['schema'] == 'A23-two-epoch-entry-binding-1' and
                      f.integer(binding['first_sequence'],81,81) and f.integer(binding['last_sequence'],112,112) and
                      f.hex64(binding['authorization_receipt_sha256']), 'entry binding shape differs')
            f.require(binding['build_manifest_sha256'] == r['reference']['manifest_sha256'] and
                      binding['receiver_sha256'] == r['reference']['receiver_sha256'] and
                      f.encode(binding) == f.encode(configs[0]), 'entry build binding differs')
        return True
    if r and s and result['role_pair_consistent'] and result['journal_subset_consistent']:
        result['build_references_consistent'] = bool(check('build_links', joined))
    if not result['errors']:
        result['classification'] = 'consistent_cached_build_subset'
        result['references'] = dict(receiver=r['reference'], supervisor=s['reference'],
                                    receiver_member_counts=r['member_counts'])
    return result
