from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch
import copy
import hashlib
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import a23_grouped_build_bytes as m


class GroupedBuildTests(unittest.TestCase):
    def setUp(self):
        self.raw = {'empty': b'', 'large': b'x'*(m.PIECE_BYTES*2+9),
                    **{'source/%03d' % i: str(i).encode() for i in range(130)}}
        self.manifest = m.a.sums(self.raw)
        self.digest = m.f.sha(self.manifest)
        self.catalog, self.groups = m.prepare(self.raw, self.manifest, self.digest)
        self.caches = self.make_caches()

    def make_caches(self):
        return tuple(m.view.PinnedBytes(MappingProxyType(dict(g)), m.f.sha(m.f.encode(c)))
                     for g,c in zip(self.groups, self.catalog['groups']))

    def consume(self, caches=None, catalog=None, pin=None, manifest=None, digest=None):
        catalog = self.catalog if catalog is None else catalog
        return m.consume(self.caches if caches is None else caches, catalog,
                         m.f.sha(m.f.encode(catalog)) if pin is None else pin,
                         self.manifest if manifest is None else manifest,
                         self.digest if digest is None else digest)

    def test_roundtrip_large_and_empty_and_multiple_groups(self):
        cache, result = self.consume()
        self.assertEqual(len(self.groups), 2)
        self.assertEqual(cache.files, tuple(sorted(self.raw)))
        for name, value in self.raw.items():
            self.assertEqual(b''.join(cache.chunks(name)), value)
        self.assertTrue(result['build_byte_inventory_verified'])
        self.assertEqual(cache.read_small('empty'), b'')
        with self.assertRaises(ValueError): cache.read_small('large')

    def test_exact_slice_boundaries(self):
        for size in (0,1,m.PIECE_BYTES,m.PIECE_BYTES+1,m.PIECE_BYTES*2):
            raw = {'file':b'x'*size}; manifest=m.a.sums(raw)
            catalog, groups=m.prepare(raw,manifest,m.f.sha(manifest))
            self.assertEqual(len(catalog['files']['file']['pieces']),max(1,(size+m.PIECE_BYTES-1)//m.PIECE_BYTES))
            self.assertEqual(sum(len(v) for g in groups for v in g.values()),size)

    def test_group_bounds_preserve_old_limits(self):
        for c in self.catalog['groups']:
            self.assertLessEqual(len(c['files']),128)
            self.assertLessEqual(max(v['bytes'] for v in c['files'].values()),m.PIECE_BYTES)
            self.assertLessEqual(sum(v['bytes'] for v in c['files'].values()),m.GROUP_BYTES)
            self.assertEqual(m.ar.contract(c),c)

    def test_byte_budget_splits_before_file_count_limit(self):
        raw={'a':b'x'*m.MAX_FILE_BYTES,'b':b'y'*m.MAX_FILE_BYTES}
        manifest=m.a.sums(raw)
        catalog,groups=m.prepare(raw,manifest,m.f.sha(manifest))
        self.assertEqual(len(groups),2)
        for group in groups:
            self.assertEqual(sum(map(len,group.values())),m.GROUP_BYTES)
            self.assertLess(len(group),128)

    def test_missing_extra_and_reordered_groups(self):
        for caches in (self.caches[:-1],self.caches+(self.caches[0],),self.caches[::-1]):
            with self.assertRaises(ValueError):self.consume(caches=caches)

    def test_catalog_and_source_need_independent_pins(self):
        for kwargs in ({'pin':'0'*64},{'digest':'0'*64},{'manifest':self.manifest+b'\n'}):
            with self.assertRaises(ValueError):self.consume(**kwargs)

    def test_catalog_coverage_size_types_order_and_authority(self):
        variants=[]
        c=copy.deepcopy(self.catalog);del c['files']['empty'];variants.append(c)
        c=copy.deepcopy(self.catalog);c['files']['empty']['bytes']=False;variants.append(c)
        c=copy.deepcopy(self.catalog);c['files']['large']['bytes']+=1;variants.append(c)
        c=copy.deepcopy(self.catalog);c['files']['large']['pieces'].reverse();variants.append(c)
        c=copy.deepcopy(self.catalog);c['files']['empty']['pieces'][0]['group']=False;variants.append(c)
        c=copy.deepcopy(self.catalog);c['files']['empty']['pieces'][0]['name']='../escape';variants.append(c)
        c=copy.deepcopy(self.catalog);c['groups'].append(c['groups'][0]);variants.append(c)
        c=copy.deepcopy(self.catalog);c['groups'][0]['source_manifest_sha256']='0'*64;variants.append(c)
        c=copy.deepcopy(self.catalog);c['groups'][0]['files']['extra']={'bytes':0,'sha256':m.f.sha(b'')};variants.append(c)
        c=copy.deepcopy(self.catalog);c['hardware_verified']=True;variants.append(c)
        for c in variants:
            with self.subTest(catalog=c),self.assertRaises(ValueError):self.consume(catalog=c)

    def test_piece_corruption_missing_and_mutable_bytes(self):
        for mode in ('corrupt','missing','mutable'):
            group=dict(self.groups[0]);key=next(iter(group))
            if mode=='missing':del group[key]
            elif mode=='mutable':group[key]=bytearray(group[key])
            else:group[key]=b'corrupted'
            cache=m.view.PinnedBytes(MappingProxyType(group),self.caches[0].contract_sha256)
            with self.assertRaises(ValueError):self.consume(caches=(cache,)+self.caches[1:])

    def test_rehashed_piece_and_catalog_still_need_original_whole_file_digest(self):
        part=self.catalog['files']['large']['pieces'][0]
        self.groups[part['group']][part['name']]=b'y'*m.PIECE_BYTES
        self.catalog['groups'][part['group']]['files'][part['name']]['sha256']=m.f.sha(b'y'*m.PIECE_BYTES)
        with self.assertRaisesRegex(ValueError,'reassembled file digest'):
            self.consume(caches=self.make_caches())

    def test_consumer_never_opens_declared_paths(self):
        with patch('builtins.open',side_effect=AssertionError('open')),patch('os.open',side_effect=AssertionError('os.open')):
            cache,_=self.consume()
            self.assertEqual(hashlib.sha256(b''.join(cache.chunks('large'))).hexdigest(),m.f.sha(self.raw['large']))

    def test_no_acquisition_or_full_semantic_claims(self):
        _,result=self.consume()
        for key in m.FALSE:self.assertIs(result[key],False)
        self.assertFalse(result['build_semantics_verified'])

    def test_prepare_rejects_missing_extra_bad_manifest_and_wrong_bytes(self):
        for raw in ({'empty':b''},{**self.raw,'extra':b''},{**self.raw,'empty':b'bad'}):
            with self.assertRaises(ValueError):m.prepare(raw,self.manifest,self.digest)
        duplicate=self.manifest+self.manifest.splitlines(keepends=True)[0]
        with self.assertRaises(ValueError):m.prepare(self.raw,duplicate,m.f.sha(duplicate))

    def test_aggregate_file_count_and_single_file_limits(self):
        for raw in ({'x':b'x'*(m.MAX_FILE_BYTES+1)},
                    {'a':b'x'*m.MAX_FILE_BYTES,'b':b'y'*m.MAX_FILE_BYTES,'c':b'z'},
                    {str(i):b'' for i in range(m.MAX_FILES+1)}):
            manifest=m.a.sums(raw)
            with self.assertRaises(ValueError):m.prepare(raw,manifest,m.f.sha(manifest))

    @unittest.skipUnless(os.environ.get('A23_GROUPED_BUILD_REVIEW'),'historical review path not supplied')
    def test_historical_build_review(self):
        import audit_a23_grouped_build_bytes as audit
        root=Path(os.environ['A23_GROUPED_BUILD_REVIEW'])
        result=audit.replay(root,os.environ['A23_GROUPED_BUILD_REVIEW_SHA256'])
        self.assertTrue(result['passed'])
        self.assertEqual([result['builds'][r]['files'] for r in ('receiver','supervisor')],[486,395])
        with self.assertRaisesRegex(ValueError,'external review manifest pin'):
            audit.replay(root,'0'*64)


if __name__=='__main__':unittest.main()
