"""Transactional card file tests on disposable directory models only."""
import copy,json,os,plistlib,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import path_span_card_workflow as w
b=w.b


def model_card(root):
    root.mkdir(parents=True)
    for name in w.pkg.PATHS:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(w.once.PACKAGE/'rollback-review'/name,path)
    (root/'logfile.txt').write_bytes(b'original log\n')
    (root/'ep0-old.partial.bin').write_bytes(b'partial original')
    report=root/'atmosphere/crash_reports/original.log';report.parent.mkdir(parents=True);report.write_bytes(b'report\x00\xff')
    return w.DirectoryCard(root)


class CardWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-card-files-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.card=model_card(self.root/'card');self.snap=self.root/'snapshot';self.out=self.root/'deployment'
        self.original=w.selected(self.card.root)
    def backup(self):return w.snapshot(self.card,self.snap)
    def deploy(self):self.backup();return w.deploy(self.card,self.snap,self.out)
    def failure(self):
        files=w.seal_verify(self.out);self.assertIn('failure.json',files)
        self.assertFalse(json.loads(files['failure.json'])['automatic_retry']);self.assertFalse(json.loads(files['failure.json'])['automatic_rollback'])
        return json.loads(files['failure.json'])
    def test_predeployment_copy_preserves_every_original_and_does_not_write_card(self):
        row=self.backup();self.assertEqual(w.selected(self.card.root),self.original);self.assertTrue(row['deployment_files_match'])
        saved=w.seal_verify(self.snap);self.assertEqual({n[5:]:raw for n,raw in saved.items() if n.startswith('card/')},self.original)
        self.assertFalse(row['card_files_written']);self.assertEqual(row['remaining'],0)
    def test_wrong_uuid_and_internal_media_reject_before_output(self):
        for key,value in [('VolumeUUID','wrong'),('Internal',True),('FilesystemType','apfs')]:
            original=self.card.info[key];self.card.info[key]=value
            with self.assertRaises(ValueError):self.backup()
            self.card.info[key]=original;self.assertFalse(self.snap.exists())
        self.assertEqual(w.selected(self.card.root),self.original)
    def test_disk_partition_and_mount_mismatch_reject(self):
        for key,value in [('ParentWholeDisk','disk43'),('MountPoint','/wrong'),('WritableVolume',1)]:
            before=self.card.info[key];self.card.info[key]=value
            with self.assertRaises(ValueError):self.backup()
            self.card.info[key]=before
    def test_old_a23_and_already_new_candidate_do_not_overwrite(self):
        target=self.card.root/w.pkg.PATHS[0];before=target.read_bytes()
        for raw in (b'old A23',b.plain(w.once.PACKAGE/'exefs.nsp')):
            target.write_bytes(raw)
            with self.assertRaises(ValueError):self.backup()
            self.assertFalse(self.snap.exists());self.assertEqual(target.read_bytes(),raw)
        target.write_bytes(before)
    def test_missing_baseline_file_and_symlink_reject(self):
        target=self.card.root/w.pkg.PATHS[1];raw=target.read_bytes();target.unlink()
        with self.assertRaises(ValueError):self.backup()
        target.write_bytes(raw);link=self.card.root/'ep0-link.bin';link.symlink_to(self.card.root/'logfile.txt')
        with self.assertRaises(ValueError):self.backup()
        self.assertFalse(self.snap.exists())
    def test_oversized_original_is_never_silently_truncated(self):
        with patch.object(w,'MAX_FILE',1024):
            with self.assertRaises(ValueError):self.backup()
        self.assertFalse(self.snap.exists());self.assertEqual(w.selected(self.card.root),self.original)
    def test_changed_during_snapshot_leaves_unsealed_copy(self):
        original=w.selected;calls=0
        def changed(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:(self.card.root/'logfile.txt').write_bytes(b'changed')
            return original(*args,**kwargs)
        with patch.object(w,'selected',side_effect=changed),self.assertRaises(ValueError):self.backup()
        self.assertFalse((self.snap/'COMMITTED').exists());self.assertEqual((self.snap/'card/logfile.txt').read_bytes(),b'original log\n')
    def test_success_changes_only_nsp_and_keeps_originals(self):
        row=self.deploy();expected={**self.original,w.pkg.PATHS[0]:b.plain(w.once.PACKAGE/'exefs.nsp')}
        self.assertEqual(w.selected(self.card.root),expected);self.assertEqual(row['changed_files'],[w.pkg.PATHS[0]])
        self.assertFalse(self.card.attached);self.assertEqual(row['remaining'],0)
        for name in w.pkg.PATHS:self.assertEqual((self.out/'backup'/name).read_bytes(),self.original[name])
        self.assertTrue(w.seal_verify(self.out));self.assertEqual(row['schema'],'A23-path-span-card-deployment-model-1')
    def test_model_receipt_cannot_be_used_by_formal_issuer(self):
        self.deploy();source,scope=w.once.materials()
        with self.assertRaises(ValueError):w.once.gate.verify_deployment(self.out,scope)
        path=self.root/'A23-path-span-once-model.json'
        with self.assertRaises(ValueError):w.once.prepare(path,issue=True,deployment=self.out)
        self.assertFalse(path.exists())
    def test_drift_after_backup_rejects_before_output_or_write(self):
        self.backup();(self.card.root/'logfile.txt').write_bytes(b'new original')
        with self.assertRaises(ValueError):w.deploy(self.card,self.snap,self.out)
        self.assertFalse(self.out.exists());self.assertEqual((self.card.root/w.pkg.PATHS[0]).read_bytes(),self.original[w.pkg.PATHS[0]])
    def test_identity_change_after_backup_rejects(self):
        self.backup();self.card.info['ParentWholeDisk']='disk43';self.card.info['DeviceIdentifier']='disk43s1'
        with self.assertRaises(ValueError):w.deploy(self.card,self.snap,self.out)
        self.assertFalse(self.out.exists())
    def test_tampered_snapshot_even_resealed_inventory_rejects(self):
        self.backup();path=self.snap/'card/logfile.txt';path.write_bytes(b'fake')
        with self.assertRaises(ValueError):w.deploy(self.card,self.snap,self.out)
        for name in ('SHA256SUMS','COMMITTED'):(self.snap/name).unlink()
        b.seal(self.snap)
        with self.assertRaises(ValueError):w.deploy(self.card,self.snap,self.out)
        self.assertFalse(self.out.exists())
    def test_readonly_model_cannot_deploy(self):
        self.backup();self.card.info['WritableVolume']=False
        with self.assertRaises(ValueError):w.deploy(self.card,self.snap,self.out)
        self.assertFalse(self.out.exists())
    def test_partial_temporary_write_keeps_target_backup_and_failure(self):
        self.backup();original=b.old.durable_write
        def partial(path,data):
            if '.a23-path-span-' in str(path) and self.card.root in path.parents:
                path.write_bytes(data[:37]);raise OSError('injected partial write')
            return original(path,data)
        with patch.object(b.old,'durable_write',side_effect=partial),self.assertRaises(OSError):w.deploy(self.card,self.snap,self.out)
        row=self.failure();self.assertEqual(row['phase'],'temporary_write');self.assertFalse(row['replacement_return_observed'])
        self.assertEqual((self.card.root/w.pkg.PATHS[0]).read_bytes(),self.original[w.pkg.PATHS[0]])
        self.assertEqual((self.card.root/row['temporary_card_path']).read_bytes(),b.plain(w.once.PACKAGE/'exefs.nsp')[:37])
    def test_temporary_readback_error_never_replaces_target(self):
        self.backup();original=w.read_file
        def corrupt(path,*args):
            raw=original(path,*args);return raw[:-1] if '.a23-path-span-' in str(path) and self.card.root in Path(path).parents else raw
        with patch.object(w,'read_file',side_effect=corrupt),self.assertRaises(ValueError):w.deploy(self.card,self.snap,self.out)
        self.assertEqual(self.failure()['phase'],'temporary_readback');self.assertEqual((self.card.root/w.pkg.PATHS[0]).read_bytes(),self.original[w.pkg.PATHS[0]])
    def test_replace_error_does_not_eject_or_make_success_receipt(self):
        self.backup()
        with patch.object(w.os,'replace',side_effect=OSError('injected replacement error')),self.assertRaises(OSError):w.deploy(self.card,self.snap,self.out)
        self.assertEqual(self.failure()['phase'],'replace');self.assertTrue(self.card.attached);self.assertFalse((self.out/'deployment.json').exists())
    def test_failed_postreplace_sync_retains_new_state_without_rollback(self):
        self.backup()
        with patch.object(self.card,'sync',side_effect=OSError('injected sync failure')),self.assertRaises(OSError):w.deploy(self.card,self.snap,self.out)
        row=self.failure();self.assertTrue(row['replacement_return_observed']);self.assertEqual(row['phase'],'sync')
        self.assertEqual((self.card.root/w.pkg.PATHS[0]).read_bytes(),b.plain(w.once.PACKAGE/'exefs.nsp'));self.assertTrue(self.card.attached)
    def test_changed_preserved_file_after_replace_is_not_success(self):
        self.backup()
        def changed():(self.card.root/'logfile.txt').write_bytes(b'changed')
        with patch.object(self.card,'sync',side_effect=changed),self.assertRaises(ValueError):w.deploy(self.card,self.snap,self.out)
        self.assertEqual(self.failure()['phase'],'readback');self.assertFalse((self.out/'deployment.json').exists())
    def test_eject_failure_and_wrong_disk_ejection_not_accepted(self):
        self.backup()
        with patch.object(self.card,'eject',return_value=dict(ejected=True,mount_absent=True,device='disk43')),self.assertRaises(ValueError):w.deploy(self.card,self.snap,self.out)
        self.assertEqual(self.failure()['phase'],'eject');self.assertFalse((self.out/'deployment.json').exists())
    def test_retry_or_reuse_outputs_is_refused(self):
        self.backup();self.out.mkdir()
        with self.assertRaises(ValueError):w.deploy(self.card,self.snap,self.out)
        with self.assertRaises(ValueError):w.snapshot(self.card,self.snap)
        self.assertEqual(w.selected(self.card.root),self.original)
    def test_recovery_requires_readonly_and_preserves_partial_originals(self):
        with self.assertRaises(ValueError):w.recover(self.card,self.snap)
        self.assertFalse(self.snap.exists());self.card.info['WritableVolume']=False
        (self.card.root/'ep0-life-broken.bin').write_bytes(b'EP0LCP1\0partial')
        (self.card.root/'ep0-abc.execution.bin').write_bytes(b'EXE3partial')
        (self.card.root/w.pkg.PATHS[0]).write_bytes(b'partial NSP')
        before=w.selected(self.card.root);row=w.recover(self.card,self.snap)
        self.assertFalse(row['deployment_files_match']);self.assertFalse(row['lifecycle'][0]['header_valid'])
        self.assertEqual(w.selected(self.card.root),before);self.assertEqual((self.snap/'card/ep0-abc.execution.bin').read_bytes(),b'EXE3partial')
        self.assertTrue(row['read_only_mount_verified']);self.assertFalse(row['hardware_verified'])
    def test_recovery_preserves_missing_and_multiple_lifecycle_without_selection(self):
        self.card.info['WritableVolume']=False
        first=w.recover(self.card,self.snap);self.assertEqual(first['lifecycle'],[])
        host=b.ROOT/'private/analysis/A23-path-span-receiver-review-20261016/collections/matching/lifecycle'
        raw=next(host.iterdir()).read_bytes()
        for name in ('ep0-life-first.bin','ep0-life-second.bin'):(self.card.root/name).write_bytes(raw)
        row=w.recover(self.card,self.root/'second-snapshot');self.assertEqual(len(row['lifecycle']),2)
        self.assertTrue(all(r['header_valid'] for r in row['lifecycle']));self.assertTrue(all(not r['filename_matches_nonce'] for r in row['lifecycle']))
        for r in row['lifecycle']:self.assertFalse(r['prefix']['own_commit_authenticated'])
    def test_snapshot_can_move_and_unlisted_files_in_seal_are_rejected(self):
        self.backup();moved=self.root/'moved';shutil.copytree(self.snap,moved);self.assertTrue(w.verify_snapshot(moved))
        (moved/'extra').write_bytes(b'new')
        with self.assertRaises(ValueError):w.seal_verify(moved)
    def test_output_locations_refuse_card_sealed_trees_and_symlinks(self):
        for path in (self.card.root/'backup',w.once.PACKAGE/'new',Path('/Volumes/new'),Path('/tmp/new')):
            with self.assertRaises(ValueError):w.new_output(path,self.card,'card-cycles')
        with self.assertRaises(ValueError):w.DirectoryCard(w.pkg.BASE)
    def test_native_identity_validation_uses_saved_fields_only(self):
        value=dict(self.card.info)
        self.assertEqual(w.identity(value,self.card.root)['ParentWholeDisk'],'disk42')
        value['Internal']=True
        with self.assertRaises(ValueError):w.identity(value,self.card.root)
    def test_computer_copy_corruption_is_detected_before_eject(self):
        self.card.info['WritableVolume']=False;original=w.put
        def corrupt(root,name,data):return original(root,name,data+b'x' if name=='card/logfile.txt' else data)
        with patch.object(w,'put',side_effect=corrupt),patch.object(self.card,'eject') as eject,self.assertRaises(ValueError):
            w.recover(self.card,self.snap,eject_after=True)
        eject.assert_not_called();self.assertFalse((self.snap/'COMMITTED').exists())
    def test_optional_recovery_eject_and_failure_preserve_rawcopy(self):
        self.card.info['WritableVolume']=False;row=w.recover(self.card,self.snap,eject_after=True)
        self.assertTrue(row['ejection_requested']);self.assertFalse(self.card.attached)
        self.assertIn('eject.json',w.verify_snapshot(self.snap))
        card=model_card(self.root/'card2');card.info['WritableVolume']=False
        with patch.object(card,'eject',side_effect=OSError('injected eject failure')),self.assertRaises(OSError):
            w.recover(card,self.root/'failed-recovery',eject_after=True)
        self.assertEqual((self.root/'failed-recovery/card/logfile.txt').read_bytes(),b'original log\n')
        self.assertFalse((self.root/'failed-recovery/COMMITTED').exists())
    def test_mac_adapter_checks_only_explicit_partition_with_mocked_diskutil(self):
        card=object.__new__(w.MacCard);card.root=Path('/Volumes/SWITCH SD');card.device='disk4s1'
        info={**self.card.info,'MountPoint':str(card.root),'DeviceIdentifier':'disk4s1','ParentWholeDisk':'disk4'}
        with patch.object(w.subprocess,'check_output',return_value=plistlib.dumps(info)) as command:
            self.assertEqual(card.check(writable=True)['ParentWholeDisk'],'disk4')
            command.assert_called_once_with(['diskutil','info','-plist','/dev/disk4s1'])
        info['VolumeUUID']='wrong'
        with patch.object(w.subprocess,'check_output',return_value=plistlib.dumps(info)),self.assertRaises(ValueError):card.check()
    def test_mac_eject_adapter_uses_same_whole_disk_and_requires_absent_mount(self):
        card=object.__new__(w.MacCard);card.root=Path('/Volumes/SWITCH SD');card.device='disk4s1'
        info={**self.card.info,'MountPoint':str(card.root),'DeviceIdentifier':'disk4s1','ParentWholeDisk':'disk4'}
        with patch.object(card,'check',return_value=info),patch.object(w.subprocess,'run',return_value=Mock(stdout='ejected')) as command,patch.object(Path,'exists',return_value=False):
            result=card.eject(info);self.assertEqual(result['device'],'disk4')
            self.assertEqual(command.call_args_list[0].args[0],['sync']);self.assertEqual(command.call_args_list[1].args[0],['diskutil','eject','/dev/disk4'])
        with patch.object(card,'check',return_value=info),patch.object(w.subprocess,'run',return_value=Mock(stdout='ejected')),patch.object(Path,'exists',return_value=True),self.assertRaises(ValueError):card.eject(info)
    def test_computer_deployment_backup_corruption_prevents_card_write(self):
        self.backup();original=w.put
        def corrupt(root,name,data):return original(root,name,data+b'x' if name=='backup/'+w.pkg.PATHS[0] else data)
        with patch.object(w,'put',side_effect=corrupt),self.assertRaises(ValueError):w.deploy(self.card,self.snap,self.out)
        self.assertEqual(w.selected(self.card.root),self.original);self.assertFalse((self.out/'intent.json').exists())
    def test_resealed_snapshot_cannot_claim_wrong_readonly_or_hardware_state(self):
        self.backup();path=self.snap/'snapshot.json';original=json.loads(path.read_text())
        for key,value in [('read_only_mount_verified',True),('hardware_verified',True),('deployment_files_match',False)]:
            changed={**original,key:value};path.write_bytes(b.canonical(changed))
            for name in ('SHA256SUMS','COMMITTED'):(self.snap/name).unlink()
            b.seal(self.snap)
            with self.assertRaises(ValueError):w.verify_snapshot(self.snap)
    def test_cli_help_never_probes_any_card(self):
        result=subprocess.run([sys.executable,str(Path(w.__file__)),'--help'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0);self.assertIn('--execute',result.stdout)

if __name__=='__main__':unittest.main()
