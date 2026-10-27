from pathlib import Path
from unittest.mock import patch
import copy
import os
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_cached_build_relations as audit


class CachedBuildRelationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_BUILD_RELATIONS_REVIEW'):
            cls.root=Path(os.environ['A23_BUILD_RELATIONS_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-build-relations-tests-',dir='/private/tmp')
            cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        audit.a.sealed(cls.root)
        cls.rows=audit.f.load(cls.root/'results.json')['cases']
        cls.builds,cls.journal,cls.roots=audit.load_bundle(cls.root/'bundle')

    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()

    def row(self,name):return self.rows[name]['result']

    def test_complete_defined_subset(self):
        row=self.row('normal')
        self.assertEqual(row['errors'],[])
        for key in ('receiver_structure_consistent','supervisor_structure_consistent',
                    'role_pair_consistent','journal_subset_consistent','build_references_consistent'):
            self.assertTrue(row[key])
        self.assertEqual(row['references']['receiver_member_counts'],
                         dict(source_hashes=392,baseline_files=71,history_files=5,recovery_index=12))

    def test_source_header_binary_and_coverage_refused(self):
        for case in ('receiver-source','receiver-table','receiver-header','receiver-binary','receiver-extra'):
            self.assertEqual(self.row(case)['errors'],['receiver'])
            self.assertTrue(self.row(case)['journal_subset_consistent'])

    def test_descriptor_shape_duplicate_path_types_and_authority(self):
        for case in ('descriptor-extra','descriptor-duplicate','descriptor-authority','descriptor-path','descriptor-digest-bool'):
            self.assertEqual(self.row(case)['errors'],['receiver'])
        self.assertIn('duplicate JSON key',self.row('descriptor-duplicate')['reasons']['receiver'])

    def test_baseline_manifest_and_inventory_recomputed(self):
        self.assertEqual(self.row('baseline-manifest')['reasons']['receiver'],'baseline manifest differs')
        self.assertEqual(self.row('baseline-inventory')['reasons']['receiver'],'baseline69 inventory differs')

    def test_supervisor_model_bytes_and_authority(self):
        for case in ('supervisor-source','supervisor-binary','supervisor-authority','supervisor-extra'):
            self.assertEqual(self.row(case)['errors'],['supervisor'])

    def test_individually_valid_models_cannot_be_spliced(self):
        for case in ('source-pair','binary-pair'):
            row=self.row(case)
            self.assertTrue(row['receiver_structure_consistent'])
            self.assertTrue(row['supervisor_structure_consistent'])
            self.assertEqual(row['errors'],['role_pair'])

    def test_worker_and_manifest_references_are_joined(self):
        for case in ('worker-root','marker-count','envelope-reference','final-reference','handoff-reference'):
            row=self.row(case)
            self.assertTrue(row['journal_subset_consistent'])
            self.assertEqual(row['errors'],['build_links'])

    def test_namespace_scope_and_entry_binding_are_joined(self):
        for case in ('namespace-scope','entry-binding','final-entry-binding','binding-range-bool'):
            self.assertEqual(self.row(case)['errors'],['build_links'])
            self.assertTrue(self.row(case)['journal_subset_consistent'])

    def test_bool_reference_count_never_equals_integer(self):
        self.assertEqual(self.row('marker-bool-count')['errors'],['journal_subset'])

    def test_rehashed_cases_pass_byte_layer_and_have_expected_semantic_result(self):
        self.assertEqual(len(self.rows),len(audit.CASES))
        for case,errors in audit.CASES.items():
            row=self.rows[case]
            self.assertEqual(row['result']['errors'],errors)
            self.assertIs(row['constructed_model'],case!='normal')
            for key in ('receiver_manifest_sha256','supervisor_manifest_sha256','journal_manifest_sha256','link_sha256'):
                self.assertTrue(audit.f.hex64(row[key]))

    def test_external_links_require_pins_and_exact_roles(self):
        m=audit.model;r=self.builds['receiver'];s=self.builds['supervisor'];j=self.journal
        links=audit.link_bytes(r,s,j,self.roots)
        with self.assertRaisesRegex(ValueError,'external link pin'):m.consume(r,s,j,links,'0'*64)
        base=audit.f.parse(links)
        variants=[]
        value=copy.deepcopy(base);value['hardware_verified']=True;variants.append(value)
        value=copy.deepcopy(base);value['builds']['receiver']['manifest_sha256']='0'*64;variants.append(value)
        value=copy.deepcopy(base);value['journal_manifest_sha256']='0'*64;variants.append(value)
        value=copy.deepcopy(base);value['builds']['receiver']['logical_root']='/private/tmp/../escape';variants.append(value)
        for value in variants:
            raw=audit.f.encode(value)
            with self.assertRaises(ValueError):m.consume(r,s,j,raw,audit.f.sha(raw))

    def test_pure_consumer_does_not_open_declared_paths(self):
        r=self.builds['receiver'];s=self.builds['supervisor'];j=self.journal
        links=audit.link_bytes(r,s,j,self.roots)
        with patch('builtins.open',side_effect=AssertionError('open')),patch('os.open',side_effect=AssertionError('os.open')):
            row=audit.model.consume(r,s,j,links,audit.f.sha(links))
        self.assertEqual(row['errors'],[])

    def test_no_compiler_full_chain_or_live_authority(self):
        for case in self.rows:
            for key in audit.model.FALSE:self.assertIs(self.row(case)[key],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())

    def test_compile_records_do_not_attest_binary_provenance(self):
        raw,_=audit.a.snapshot(self.root/'bundle/builds/receiver/original')
        raw['compile.log']=b'claimed compiler success\n'
        raw['build-command.json']=b'not a compiler invocation\n'
        cache,_=audit.grouped.consume(*audit.spec(raw))
        result=audit.model.verify_receiver(cache)
        self.assertEqual(result['reference']['receiver_sha256'],
                         self.row('normal')['references']['receiver']['receiver_sha256'])

    def test_source422_preserves419_and_replay_requires_external_pin(self):
        report=audit.f.load(self.root/'audit.json')
        self.assertEqual(report['source_count'],422)
        self.assertEqual(report['prior_sources_unchanged'],419)
        self.assertEqual(report['consumer_filesystem_opens'],0)
        with self.assertRaisesRegex(ValueError,'external review pin'):
            audit.replay(self.root,'0'*64)


if __name__=='__main__':unittest.main()
