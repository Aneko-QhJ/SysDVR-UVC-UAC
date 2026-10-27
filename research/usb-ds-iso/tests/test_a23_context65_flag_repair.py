"""A single empty create on disposable directory models; no physical media."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import context65_flag_repair as repair
w=repair.w


def case(root):
    root.mkdir();card_root=root/'card';shutil.copytree(w.ANCHOR/'card',card_root)
    before=root/'before';w.card.recover(w.card.DirectoryCard(card_root,readonly=True),before,eject_after=True)
    return w.card.DirectoryCard(card_root),before,root/'repair',root/'after'


def reseal(folder):
    for name in ('SHA256SUMS','COMMITTED'):(folder/name).unlink()
    w.b.seal(folder)


class FlagRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-flag-tests-');cls.root=Path(cls.temp.name).resolve()
        cls.plan=cls.root/'plan';cls.prepared=repair.prepare(cls.plan);cls.original=repair.materials()[0]
        cls.protected=w.load(repair.PARENT/'closeout.json')['protected_sha256'];cls.sources=repair.source_hashes()
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.work=self.root/next(tempfile._get_candidate_names());self.card,self.before,self.output,self.after=case(self.work)
    def tearDown(self):
        self.assertEqual(repair.source_hashes(),self.sources)
        for name,h in self.protected.items():self.assertEqual(w.sha(w.plain(Path(name))),h,name)
        self.assertFalse((w.LEDGER/'block-00065.json').exists())
        self.assertFalse(list(w.A.glob('A23-context65-once-*.json')))
    def execute(self,**kw):
        return repair.model_repair(kw.get('plan',self.plan),kw.get('card',self.card),kw.get('before',self.before),kw.get('output',self.output),kw.get('after',self.after))
    def rejected(self,**kw):
        with self.assertRaises((ValueError,OSError)):self.execute(**kw)
        self.assertFalse(self.output.exists());self.assertFalse(self.after.exists())
    def failure(self):
        w.card.seal_verify(self.output);value=w.load(self.output/'failure.json')
        self.assertFalse(value['automatic_retry']);self.assertFalse(value['automatic_rollback']);self.assertEqual(value['remaining'],0)
        return value
    def test_prepare_and_analyze_never_probe_disk(self):
        with patch.object(w.card.subprocess,'check_output',side_effect=AssertionError('disk probe')):
            value=repair.prepare(self.work/'another-plan');repair.verify_plan(self.work/'another-plan')
        self.assertFalse(value['physical_card_execution_supported']);self.assertFalse(value['actual_card_write_authorized'])
        self.assertEqual(w.card.selected(self.card.root),self.original)
    def test_only_target_added_all59_and_companion_preserved(self):
        value=self.execute();self.assertTrue(value['passed']);self.assertEqual(value['preserved_originals'],59)
        self.assertEqual(w.card.selected(self.card.root),{**self.original,repair.FLAG:b''})
        self.assertEqual(value['changed_files'],[repair.FLAG]);self.assertEqual(value['post_files'],60)
        self.assertFalse(value['actual_card_repaired']);self.assertFalse(value['formal_baseline_accepted'])
        self.assertFalse(self.card.attached);self.assertTrue(repair.analyze_model(self.output)['supplied_model_consistent'])
    def test_model_recovery_matches_only_simulated_baseline(self):
        value=self.execute();scope=w.materials()[1]
        self.assertTrue(w.verify_recovery(self.after,scope,simulation=True)['simulation'])
        with self.assertRaises(ValueError):w.verify_recovery(self.after,scope,simulation=False)
        import prepare_a23_context65_once as once
        preview=once.prepare(w.A/'A23-context65-once-flag-model-preview.json',
            deployment=w.ROOT/'private/deployments/20261016-191203-path-span-window-30s',recovery=self.after)
        self.assertFalse(preview['issuance_available']);self.assertFalse(preview['record_written'])
        self.assertEqual(value['remaining'],0)
    def test_physical_card_object_rejected_before_any_probe(self):
        actual=object.__new__(w.card.MacCard)
        with patch.object(w.card.MacCard,'check',side_effect=AssertionError('physical probe')):self.rejected(card=actual)
    def test_subclass_and_noncard_rejected(self):
        class Other(w.card.DirectoryCard):pass
        for device in (Other(self.card.root),object()):self.rejected(card=device)
    def test_existing_empty_or_nonempty_flag_never_overwritten(self):
        target=self.card.root/repair.FLAG
        for raw in (b'',b'KEEP'):
            target.write_bytes(raw);self.rejected();self.assertEqual(target.read_bytes(),raw);target.unlink()
    def test_any_changed_original_or_deployment_file_rejected(self):
        names=['logfile.txt',*[n for n in self.original if n.endswith(('exefs.nsp','toolbox.json','.ips'))],repair.FLAG.rsplit('/',1)[0]+'/._boot2.flag']
        for name in names:
            target=self.card.root/name;raw=target.read_bytes();target.write_bytes(raw+b'drift')
            self.rejected();self.assertEqual(target.read_bytes(),raw+b'drift');target.write_bytes(raw)
    def test_removed_original_and_additional_original_rejected(self):
        target=self.card.root/'logfile.txt';raw=target.read_bytes();target.unlink();self.rejected();target.write_bytes(raw)
        extra=self.card.root/'ep0-unexpected.bin';extra.write_bytes(b'new');self.rejected();self.assertEqual(extra.read_bytes(),b'new')
    def test_symlinked_target_and_parent_rejected(self):
        target=self.card.root/repair.FLAG;target.symlink_to(self.card.root/'logfile.txt');self.rejected();target.unlink()
        parent=target.parent;shutil.move(parent,self.work/'saved-flags');parent.symlink_to(self.work/'saved-flags',target_is_directory=True)
        self.rejected();self.assertFalse((self.work/'saved-flags/boot2.flag').exists())
    def test_wrong_identity_and_readonly_mount_rejected(self):
        for key,bad in [('VolumeUUID','wrong'),('Internal',True),('FilesystemType','apfs'),('WritableVolume',False),('ParentWholeDisk','disk43')]:
            old=self.card.info[key];self.card.info[key]=bad;self.rejected();self.card.info[key]=old
    def test_unsealed_prewrite_snapshot_rejected(self):
        (self.before/'COMMITTED').unlink();self.rejected()
    def test_real_old_or_unejected_receipt_not_a_model_baseline(self):
        self.rejected(before=w.ANCHOR)
        value=w.load(self.before/'eject.json');value['ejected']=False;(self.before/'eject.json').write_bytes(w.b.canonical(value));reseal(self.before);self.rejected()
    def test_stale_receipt_timestamp_rejected(self):
        value=w.load(self.before/'snapshot.json');value['collected_at']=w.load(w.ANCHOR/'snapshot.json')['collected_at']
        (self.before/'snapshot.json').write_bytes(w.b.canonical(value));reseal(self.before);self.rejected()
    def test_tampered_plan_never_reaches_create(self):
        for key in ('target','source','preserved','allowed','support','remaining'):
            plan=self.work/('plan-'+key);shutil.copytree(self.plan,plan);value=w.load(plan/'plan.json')
            if key=='target':value['scope']['target']['bytes']=1
            elif key=='source':value['scope']['source_hashes'][next(iter(value['scope']['source_hashes']))]='0'*64
            elif key=='preserved':value['scope']['preserved_files']['logfile.txt']['sha256']='0'*64
            elif key=='allowed':value['scope']['allowed_changed_files'].append('logfile.txt')
            elif key=='support':value['physical_card_execution_supported']=True
            else:value['remaining']=False
            (plan/'plan.json').write_bytes(w.b.canonical(value));reseal(plan);self.rejected(plan=plan)
    def test_unexpected_plan_file_rejected(self):
        plan=self.work/'bad-plan';shutil.copytree(self.plan,plan);(plan/'extra').write_bytes(b'extra');reseal(plan);self.rejected(plan=plan)
    def test_latest_baseline_and_foreign_history_drift_stop_plan(self):
        with patch.object(w,'latest_snapshot',return_value=self.before):
            with self.assertRaises(ValueError):repair.verify_plan(self.plan)
        with patch.object(w,'transition',side_effect=ValueError('foreign history')):
            with self.assertRaises(ValueError):repair.prepare(self.work/'blocked-plan')
        self.assertFalse((self.work/'blocked-plan').exists())
    def test_overlapping_or_existing_outputs_rejected(self):
        for output,after in [(self.card.root/'output',self.after),(self.output,self.output),(self.plan/'child',self.after),(self.output,self.before/'child')]:
            self.rejected(output=output,after=after)
        self.output.mkdir()
        with self.assertRaises(ValueError):self.execute()
        self.assertEqual(list(self.output.iterdir()),[])
    def test_changed_after_intent_saved_without_mutation_or_rollback(self):
        check=self.card.check;count=0
        def changed(**mode):
            nonlocal count
            count+=1
            if count==2:(self.card.root/'logfile.txt').write_bytes(b'concurrent change')
            return check(**mode)
        with patch.object(self.card,'check',side_effect=changed),self.assertRaises(ValueError):self.execute()
        self.assertFalse(self.failure()['model_flag_created']);self.assertFalse((self.card.root/repair.FLAG).exists())
        self.assertEqual((self.card.root/'logfile.txt').read_bytes(),b'concurrent change')
    def test_exclusive_create_race_does_not_replace_new_file(self):
        original_open=os.open
        def race(path,*args,**kwargs):
            if path=='boot2.flag' and 'dir_fd' in kwargs:(self.card.root/repair.FLAG).write_bytes(b'RACE')
            return original_open(path,*args,**kwargs)
        with patch.object(repair.os,'open',side_effect=race),self.assertRaises(FileExistsError):self.execute()
        self.assertFalse(self.failure()['model_flag_created']);self.assertEqual((self.card.root/repair.FLAG).read_bytes(),b'RACE')
    def test_failed_create_leaves_no_flag_and_sealed_failure(self):
        original_open=os.open
        def denied(path,*args,**kwargs):
            if path=='boot2.flag' and 'dir_fd' in kwargs:raise OSError('injected create failure')
            return original_open(path,*args,**kwargs)
        with patch.object(repair.os,'open',side_effect=denied),self.assertRaises(OSError):self.execute()
        self.assertFalse(self.failure()['model_flag_created']);self.assertEqual(w.card.selected(self.card.root),self.original)
    def test_failed_flag_fsync_keeps_created_bytes_and_never_rolls_back(self):
        original_open=os.open;original_sync=os.fsync;flag_fd=None;failed=False
        def opened(path,*args,**kwargs):
            nonlocal flag_fd
            fd=original_open(path,*args,**kwargs)
            if path=='boot2.flag' and 'dir_fd' in kwargs:flag_fd=fd
            return fd
        def synced(fd):
            nonlocal failed
            if fd==flag_fd and not failed:failed=True;raise OSError('injected flag fsync failure')
            return original_sync(fd)
        with patch.object(repair.os,'open',side_effect=opened),patch.object(repair.os,'fsync',side_effect=synced),self.assertRaises(OSError):self.execute()
        self.assertTrue(self.failure()['model_flag_created']);self.assertEqual((self.card.root/repair.FLAG).read_bytes(),b'')
        self.assertFalse(self.after.exists())
    def test_failed_sync_does_not_retry_or_remove_created_flag(self):
        with patch.object(self.card,'sync',side_effect=OSError('injected sync failure')),self.assertRaises(OSError):self.execute()
        self.assertTrue(self.failure()['model_flag_created']);self.assertEqual(w.card.selected(self.card.root),{**self.original,repair.FLAG:b''})
        self.assertTrue(self.card.attached)
    def test_failure_after_readback_preserves_flag_and_raw_evidence(self):
        with patch.object(w.card,'recover',side_effect=OSError('injected readonly recovery failure')),self.assertRaises(OSError):self.execute()
        failure=self.failure();self.assertEqual(failure['phase'],'readonly_recovery_and_eject');self.assertTrue(failure['model_flag_created'])
        self.assertFalse(failure['readonly_recovery_and_eject_verified']);self.assertEqual((self.output/'observed-card'/repair.FLAG).read_bytes(),b'')
    def test_replay_after_success_never_creates_or_overwrites(self):
        self.execute();self.card=w.card.DirectoryCard(self.card.root)
        with self.assertRaises(ValueError):self.execute(output=self.work/'replay',after=self.work/'replay-after')
        self.assertFalse((self.work/'replay').exists());self.assertEqual((self.card.root/repair.FLAG).read_bytes(),b'')
    def test_moved_archive_and_cli_reanalyze_without_live_card(self):
        self.execute();moved=self.work/'moved';shutil.copytree(self.output,moved);shutil.rmtree(self.card.root);shutil.rmtree(self.before);shutil.rmtree(self.after)
        with patch.object(w,'latest_snapshot',side_effect=AssertionError('live baseline')),patch.object(w,'transition',side_effect=AssertionError('live history')):
            self.assertTrue(repair.analyze_model(moved)['supplied_model_consistent'])
        cli=subprocess.run([sys.executable,str(w.ROOT/'tools/context65_flag_repair.py'),'analyze-model',str(moved)],capture_output=True,check=True)
        self.assertTrue(json.loads(cli.stdout)['supplied_model_consistent'])
    def test_archive_byte_corruption_and_forged_result_refused(self):
        self.execute();(self.output/'after/card'/repair.FLAG).write_bytes(b'bad')
        with self.assertRaises(ValueError):repair.analyze_model(self.output)
        (self.output/'after/card'/repair.FLAG).write_bytes(b'');value=w.load(self.output/'result.json');value['actual_card_repaired']=True
        (self.output/'result.json').write_bytes(w.b.canonical(value));reseal(self.output)
        with self.assertRaises(ValueError):repair.analyze_model(self.output)


if __name__=='__main__':unittest.main()
