"""Dormant notification bindings and failure-preserving EXE3 collection."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_host_execution_link as audit
import collect_a23_execution_v3 as collection


class HostExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.base=Path(cls.tmp.name).resolve();cls.output=cls.base/'review'
        cls.result=audit.run(cls.output)
        cls.rows={(r['mode'],r['batch']):r for r in cls.result['notification_cases']}

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def row(self,mode='ok',batch=1):return self.rows[mode,batch]

    def cloned(self,name='normal'):
        directory=Path(tempfile.mkdtemp(dir=self.base))/'collection'
        shutil.copytree(self.output/'collections'/name,directory);return directory

    def reseal(self,directory):
        files=collection.tree(directory,maximum=256)
        files.pop('SHA256SUMS',None);files.pop('COMMITTED',None)
        sums=''.join(collection.sha(raw)+'  '+name+'\n' for name,raw in sorted(files.items())).encode()
        (directory/'SHA256SUMS').write_bytes(sums)
        (directory/'COMMITTED').write_text(collection.sha(sums)+'\n')

    def test_unique_arrival_is_retained_and_handed_only_once(self):
        row=self.row()
        self.assertTrue(row['taken']);self.assertEqual(row['handoffs'],1)
        self.assertEqual(row['destroy_count'],1);self.assertEqual(row['unreleased_refs'],0)
        self.assertEqual([r['event'] for r in row['events']],[1,2,3,4,5,6])
        self.assertTrue(all(r['injected_ack'] for r in row['events']))
        self.assertEqual(self.row('second-take')['handoffs'],1)

    def test_initial_existing_and_ambiguous_arrivals_never_handoff(self):
        self.assertFalse(self.row('existing')['taken'])
        for n in range(67):
            row=self.row('ok',n)
            self.assertEqual(row['taken'],n==1)
            self.assertEqual(row['unreleased_refs'],0)
        self.assertFalse(self.row('initial-flood')['taken'])

    def test_detach_close_reentrancy_and_stop_inside_callback_are_deferred(self):
        for mode in ('detach-during-watch','detach-before-take','close-before-take','extra-arrival',
                     'stop-waiting','stop-selected','stop-handoff','reentrant-poll'):
            row=self.row(mode);self.assertFalse(row['taken'],mode)
            self.assertEqual(row['destroy_count'],1);self.assertEqual(row['unreleased_refs'],0)
        self.assertTrue(self.row('detach-after-take')['taken'])
        self.assertEqual(self.row('detach-after-take')['reason'],7)

    def test_deadlines_and_backwards_clock_reject_before_handoff(self):
        for mode in ('timeout','deadline-in-drain','deadline-after-watch','deadline-before-take','clock-backwards'):
            self.assertFalse(self.row(mode)['taken'],mode)

    def test_iterator_identity_and_registration_failures_do_not_open_sdk(self):
        for mode in ('matching-error','early-callback','invalid-initial-before','invalid-initial-after',
                     'invalid-arrival-before','invalid-arrival-after','bad-identity','zero-identity','same-parent',
                     'wrong-speed','identity-changed-watch','identity-changed-take','interest-error','wrong-iterator'):
            row=self.row(mode);self.assertFalse(row['taken'],mode)
            self.assertEqual(row['unreleased_refs'],0)
        for row in self.rows.values():
            self.assertEqual((row['real_iokit_calls'],row['usb_requests']),(0,0))

    def test_journal_rejection_blocks_handoff_and_preserves_stop_failure(self):
        for mode in ('journal-begin','journal-registered','journal-waiting','journal-selected','journal-handoff'):
            row=self.row(mode);self.assertFalse(row['taken'],mode)
            self.assertTrue(row['journal_failed'])
            self.assertTrue(any(not r['injected_ack'] for r in row['events']))
        self.assertTrue(self.row('journal-stop')['journal_failed'])

    def test_pump_and_batch_are_bounded_and_release_errors_remain_visible(self):
        self.assertEqual(self.row('message-flood')['pump_count'],16)
        self.assertFalse(self.row('pump-error')['taken'])
        self.assertFalse(self.row('bad-pump-result')['taken'])
        for mode,n in (('release-service-error',1),('release-iterator-error',1),('release-interest-error',1),
                       ('release-all-error',3),('release-all-extra-arrival',5)):
            row=self.row(mode);self.assertEqual(row['failed_releases'],n)
            self.assertEqual(row['unreleased_refs'],n)
        self.assertEqual(self.row()['message_cases'],230)
        self.assertEqual(self.row('matching-error')['events'][-1]['native_result'],41)
        self.assertEqual(self.row('interest-error')['events'][-1]['native_result'],42)

    def test_collection_preserves_historical_failure_and_never_binds_physical_run(self):
        for row in self.result['collections'].values():
            self.assertTrue(row['collection_integrity_verified'])
            self.assertFalse(row['analysis']['supplied_comparison_consistent'])
            for flag in collection.POLICY:self.assertFalse(row[flag])
        row=self.result['collections']['normal']['analysis']
        self.assertTrue(row['host_audit_valid']);self.assertFalse(row['host_observation_complete'])
        self.assertTrue(row['execution_valid']);self.assertTrue(row['external_primary_matches_embedded'])

    def test_complete_commit_failed_and_partial_primary_receipts_not_promoted(self):
        row=self.result['collections']['primary-commit-failed']['analysis']
        self.assertTrue(row['external_primary_matches_embedded'])
        self.assertFalse(row['execution']['primary_receipt']['commit_acknowledged'])
        self.assertTrue(row['execution']['primary_receipt']['content_verified'])
        row=self.result['collections']['primary-partial']['analysis']
        self.assertFalse(row['external_primary_matches_embedded'])
        self.assertFalse(row['primary_commit_contradiction'])
        self.assertFalse(row['execution']['primary_receipt']['save_return_value'])

    def test_truncated_execution_partial_host_and_wrong_recipe_saved_as_errors(self):
        for name,component in (('execution-partial','execution'),('host-partial','host'),('wrong-recipe','execution')):
            row=self.result['collections'][name]
            self.assertTrue(row['collection_integrity_verified'])
            self.assertTrue(any(e['component']==component for e in row['analysis']['errors']))
        source=self.output/'incomplete-host/session.jsonl'
        copied=self.output/'collections/host-partial/host/session.jsonl'
        self.assertEqual(source.read_bytes(),copied.read_bytes())

    def test_success_receipt_with_different_supplied_primary_is_a_contradiction(self):
        file=self.base/'different-primary.bin';file.write_bytes(b'partial')
        row=collection.analyze_inputs(audit.HISTORICAL/'host',audit.SEALED/'normal-primary-ok-execution-ok.execution.bin',
                                      '03'+'00'*31,file)
        self.assertTrue(row['primary_commit_contradiction'])
        self.assertFalse(row['supplied_comparison_consistent'])

    def test_tampered_bytes_commit_and_repaired_policy_are_rejected(self):
        root=self.cloned();data=bytearray((root/'execution.bin').read_bytes());data[-1]^=1
        (root/'execution.bin').write_bytes(data)
        with self.assertRaises(ValueError):collection.analyze_collection(root)
        root=self.cloned();(root/'COMMITTED').write_text('0'*64+'\n')
        with self.assertRaises(ValueError):collection.analyze_collection(root)
        for name in ('analysis.json','collection.json'):
            root=self.cloned();value=json.loads((root/name).read_bytes());value['hardware_verified']=True
            (root/name).write_bytes(collection.canonical(value));self.reseal(root)
            with self.assertRaises(ValueError):collection.analyze_collection(root)

    def test_symlinks_existing_output_and_output_overlap_rejected(self):
        root=self.cloned();before=(root/'SHA256SUMS').read_bytes()
        with self.assertRaises(ValueError):collection.freeze(audit.HISTORICAL/'host',root/'execution.bin',root,'03'+'00'*31)
        self.assertEqual((root/'SHA256SUMS').read_bytes(),before)
        host=Path(tempfile.mkdtemp(dir=self.base));(host/'linked').symlink_to(root/'execution.bin')
        out=host.parent/('symlink-output-'+host.name)
        with self.assertRaises(ValueError):collection.freeze(host,root/'execution.bin',out,'03'+'00'*31)
        self.assertFalse(out.exists())
        with self.assertRaises(ValueError):collection.freeze(audit.HISTORICAL/'host',root/'execution.bin',audit.HISTORICAL/'host/new-output','03'+'00'*31)

    def test_source_change_leaves_uncommitted_failure_bytes(self):
        base=Path(tempfile.mkdtemp(dir=self.base));host=base/'host';shutil.copytree(audit.HISTORICAL/'host',host)
        output=base/'collection';original=(host/'session.jsonl').read_bytes()
        actual=collection.analyze_inputs
        def changing(*args,**kwargs):
            result=actual(*args,**kwargs);(host/'session.jsonl').write_bytes(original+b'changed');return result
        with patch.object(collection,'analyze_inputs',side_effect=changing):
            with self.assertRaises(ValueError):collection.freeze(host,audit.SEALED/'normal-primary-ok-execution-ok.execution.bin',output,'03'+'00'*31)
        self.assertFalse((output/'COMMITTED').exists())
        self.assertEqual((output/'host/session.jsonl').read_bytes(),original)

    def test_manifests_source_hashes_and_zero_use_tickets_preserved(self):
        self.assertTrue(audit.verify(self.output)['sha256_verified'])
        for group,base in ((self.result['source_hashes'],ROOT),(self.result['production_sources_sha256'],audit.REPO),
                           (self.result['tickets_sha256'],audit.SEALED.parent)):
            for name,expected in group.items():self.assertEqual(audit.sha(base/name),expected)
        self.assertTrue(self.result['native_iokit_bindings_compiled_and_linked'])
        self.assertFalse(self.result['native_iokit_bindings_executed'])
        with self.assertRaises(ValueError):audit.run(self.output)


if __name__=='__main__':unittest.main()
