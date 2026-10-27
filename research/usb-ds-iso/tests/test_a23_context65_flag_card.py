"""Disk commands are fake plist transports; filesystem changes stay in /private/tmp."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import context65_flag_card as adapter
w=adapter.w


class FakeBackend(adapter.MacBackend):
    simulated=True
    def __init__(self,root,*,number=42,fault=None):
        self.root=root;self.whole=f'disk{number}';self.part=self.whole+'s1';self.mounted_now=True;self.writable=True
        self.events=[];self.fault=fault;self.uuid=w.card.UUID;self.internal=False;self.fs='msdos';self.duplicate=False
        self.ignore_readonly=False;self.keep_mount_on_eject=False;self.on_sync=None
    def launch(self,command,out,err):
        self.events.append(command);out.write_bytes(b'');err.write_bytes(b'')
        if self.fault is not None:
            code=self.fault(command,self)
            if code is not None:return code
        args=command[1:];value=b'OK\n'
        if args==['list','-plist','external','physical']:
            part=dict(DeviceIdentifier=self.part,VolumeUUID=self.uuid)
            value=plistlib.dumps(dict(AllDisksAndPartitions=[dict(DeviceIdentifier=self.whole,Partitions=[part]*(2 if self.duplicate else 1))]))
        elif args[:2]==['info','-plist']:
            info=dict(VolumeUUID=self.uuid,Internal=self.internal,FilesystemType=self.fs,DeviceIdentifier=self.part,
                ParentWholeDisk=self.whole,WritableVolume=self.writable if self.mounted_now else False)
            if self.mounted_now:info['MountPoint']=str(self.root)
            value=plistlib.dumps(info)
        elif args[:1]==['unmount']:self.mounted_now=False
        elif args[:1]==['mount']:
            self.mounted_now=True;self.writable=self.ignore_readonly or 'readOnly' not in args
        elif args[:1]==['eject']:self.mounted_now=self.keep_mount_on_eject
        elif command==['/bin/sync']:
            if self.on_sync:self.on_sync(self)
        else:raise AssertionError('unexpected command '+str(command))
        out.write_bytes(value);return 0
    def mount_absent(self,root):return not self.mounted_now


def case(root):
    root.mkdir();card=root/'card';shutil.copytree(w.ANCHOR/'card',card)
    job=root/'job';adapter.prepare(job,root/'before',root/'after');return card,job,FakeBackend(card)


class CardAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-flag-card-tests-');cls.root=Path(cls.temp.name).resolve()
        cls.sources=adapter.source_hashes();cls.protected=w.load(adapter.PARENT/'closeout.json')['protected_sha256']
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.work=self.root/str(len(list(self.root.iterdir())));self.card,self.job,self.backend=case(self.work)
    def tearDown(self):
        self.assertEqual(adapter.source_hashes(),self.sources)
        for name,h in self.protected.items():self.assertEqual(w.sha(w.plain(Path(name))),h,name)
        self.assertFalse((w.LEDGER/'block-00065.json').exists());self.assertFalse(list(w.A.glob('A23-context65-once-*.json')))
    def backup(self):return adapter.backup(self.job,repair_authorized=True,shutdown_card_connected=True,_backend=self.backend)
    def repair(self,backend=None):return adapter.execute(self.job,repair_authorized=True,shutdown_card_reinserted=True,_backend=backend or FakeBackend(self.card))
    def state(self):return w.load(self.job/'state.json')
    def no_flag(self):self.assertFalse((self.card/adapter.repair.FLAG).exists())
    def test_prepare_check_and_import_are_file_only(self):
        with patch.object(adapter.MacBackend,'command',side_effect=AssertionError('disk access')):
            adapter.verify_job(self.job);adapter.prepare(self.work/'another',self.work/'another-before',self.work/'another-after')
        self.assertEqual(self.backend.events,[]);self.no_flag()
    def test_explicit_confirmation_required_before_any_disk_access(self):
        for fn,kwargs in [(adapter.backup,dict(repair_authorized=True)),(adapter.backup,dict(shutdown_card_connected=True)),
            (adapter.execute,dict(repair_authorized=True)),(adapter.execute,dict(shutdown_card_reinserted=True))]:
            with self.assertRaises(ValueError):fn(self.job,_backend=self.backend,**kwargs)
        self.assertEqual(self.backend.events,[]);self.assertEqual(self.state()['stage'],'planned')
    def test_repair_cannot_skip_backup_or_reinsert_phase(self):
        with self.assertRaises(ValueError):self.repair(self.backend)
        self.assertEqual(self.backend.events,[]);self.no_flag()
    def test_model_never_constructs_physical_backend(self):
        with patch.object(adapter,'MacBackend',side_effect=AssertionError('physical backend')):
            with self.assertRaises(ValueError):adapter.backup(self.job,repair_authorized=True,shutdown_card_connected=True)
        self.assertEqual(self.state()['stage'],'planned')
    def test_formal_job_refuses_injected_backend_and_missing_proof(self):
        with self.assertRaises(ValueError):adapter.backend_for(dict(simulation=False),self.backend)
        path=w.A/'A23-context65-flag-card-proof-missing-test'
        with patch.object(adapter,'proof',return_value=None):
            with self.assertRaises(ValueError):adapter.prepare(path,w.ROOT/'private/card-cycles/flag-card-test-before',w.ROOT/'private/card-cycles/flag-card-test-after')
        self.assertFalse(path.exists());self.assertEqual(self.backend.events,[])
    def test_backup_is_readonly_and_ejected_then_stops(self):
        state=self.backup();self.assertEqual(state['stage'],'awaiting_reinsert');self.assertTrue(state['backup_ejected'])
        self.assertFalse(self.backend.mounted_now);self.assertEqual(state['backup_remaining'],0);self.assertEqual(state['repair_remaining'],1)
        self.assertFalse(any(c[1:-1]==['mount','nobrowse'] for c in self.backend.events));self.no_flag()
        meta=w.load(self.work/'before/snapshot.json');self.assertTrue(meta['read_only_mount_verified']);self.assertEqual(len(meta['raw_files']),59)
        self.assertTrue((self.job/'.backup.lock').exists());self.assertFalse((self.job/'COMMITTED').exists())
    def test_reinsert_renumbered_disk_and_one_file_success(self):
        self.backup();second=FakeBackend(self.card,number=99);state=self.repair(second)
        self.assertEqual(state['stage'],'complete');self.assertFalse(state['actual_card_repaired']);self.assertFalse(state['formal_baseline_accepted'])
        self.assertTrue(all('/dev/disk42' not in str(c) for c in second.events));self.assertFalse(second.mounted_now)
        self.assertEqual(w.card.selected(self.card),{**adapter.repair.materials(live=False)[0],adapter.repair.FLAG:b''})
        self.assertEqual(sum(c[1:-1]==['mount','nobrowse'] for c in second.events),1)
        self.assertTrue(adapter.analyze(self.job)['supplied_chain_consistent'])
    def test_wrong_uuid_internal_or_filesystem_stops_before_mount(self):
        for key,value in [('uuid','wrong'),('internal',True),('fs','apfs')]:
            root=self.work/key;card,job,backend=case(root);setattr(backend,key,value)
            with self.assertRaises(ValueError):adapter.backup(job,repair_authorized=True,shutdown_card_connected=True,_backend=backend)
            self.assertFalse(any(c[1:2] in (['mount'],['unmount'],['eject']) for c in backend.events))
            self.assertFalse((card/adapter.repair.FLAG).exists())
    def test_duplicate_uuid_and_unsafe_identifier_refused(self):
        self.backend.duplicate=True
        with self.assertRaises(ValueError):self.backup()
        self.assertEqual(len(self.backend.events),1);self.no_flag()
        card,job,backend=case(self.work/'unsafe');backend.whole='disk42/../disk0';backend.part=backend.whole+'s1'
        with self.assertRaises(ValueError):adapter.backup(job,repair_authorized=True,shutdown_card_connected=True,_backend=backend)
        self.assertEqual(len(backend.events),1)
    def test_readonly_mount_not_honored_refuses_backup(self):
        self.backend.ignore_readonly=True
        with self.assertRaises(ValueError):self.backup()
        self.assertEqual(self.state()['stage'],'failed_no_retry');self.no_flag();self.assertFalse((self.work/'before').exists())
    def test_unmount_and_readonly_mount_command_failures_stop(self):
        for action in ('unmount','mount'):
            card,job,backend=case(self.work/action);backend.fault=lambda c,b:1 if c[1:2]==[action] else None
            with self.assertRaises(ValueError):adapter.backup(job,repair_authorized=True,shutdown_card_connected=True,_backend=backend)
            self.assertEqual(backend.events[-1][1],action);self.assertFalse((card/adapter.repair.FLAG).exists())
            self.assertTrue((job/'COMMITTED').exists())
    def test_eject_failure_is_not_a_successful_backup_receipt(self):
        self.backend.keep_mount_on_eject=True
        with self.assertRaises(ValueError):self.backup()
        self.assertEqual(self.state()['stage'],'failed_no_retry');self.assertFalse((self.work/'before/COMMITTED').exists());self.no_flag()
        with self.assertRaises(ValueError):self.repair()
    def test_changed_original_before_backup_never_writes(self):
        (self.card/'logfile.txt').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.backup()
        self.assertFalse(any(c[1:-1]==['mount','nobrowse'] for c in self.backend.events));self.no_flag()
    def test_changed_or_existing_target_on_reinsert_never_mounts_writable(self):
        for mode in ('original','extra','flag-empty','flag-nonempty'):
            card,job,backend=case(self.work/mode);adapter.backup(job,repair_authorized=True,shutdown_card_connected=True,_backend=backend)
            if mode=='original':(card/'logfile.txt').write_bytes(b'changed')
            elif mode=='extra':(card/'ep0-new.bin').write_bytes(b'new')
            else:(card/adapter.repair.FLAG).write_bytes(b'' if mode=='flag-empty' else b'KEEP')
            second=FakeBackend(card)
            with self.assertRaises(ValueError):adapter.execute(job,repair_authorized=True,shutdown_card_reinserted=True,_backend=second)
            self.assertFalse(any(c[1:-1]==['mount','nobrowse'] for c in second.events))
            if mode=='flag-nonempty':self.assertEqual((card/adapter.repair.FLAG).read_bytes(),b'KEEP')
    def test_missing_readonly_eject_receipt_prevents_repair(self):
        self.backup();(self.work/'before/COMMITTED').unlink();second=FakeBackend(self.card)
        with self.assertRaises((ValueError,OSError)):self.repair(second)
        self.assertEqual(second.events,[]);self.assertEqual(self.state()['repair_remaining'],1)
    def test_newer_saved_baseline_prevents_any_new_phase(self):
        with patch.object(w,'latest_snapshot',return_value=self.work/'other'):
            with self.assertRaises(ValueError):self.backup()
        self.assertEqual(self.backend.events,[]);self.backup();second=FakeBackend(self.card)
        with patch.object(w,'latest_snapshot',return_value=self.work/'other'):
            with self.assertRaises(ValueError):self.repair(second)
        self.assertEqual(second.events,[])
    def test_plan_copy_changes_and_unexpected_artifacts_refused(self):
        path=self.job/'plan.json';original=path.read_bytes();value=w.load(path);value['preparation_id']='00000000-0000-0000-0000-000000000000';path.write_bytes(w.b.canonical(value))
        with self.assertRaises(ValueError):self.backup()
        path.write_bytes(original);(self.job/'unexpected').write_bytes(b'x')
        with self.assertRaises(ValueError):self.backup()
        self.assertEqual(self.backend.events,[])
    def test_permanent_phase_claims_block_replay(self):
        self.backup();count=len(self.backend.events)
        with self.assertRaises(ValueError):self.backup()
        self.assertEqual(len(self.backend.events),count);second=FakeBackend(self.card);self.repair(second);count=len(second.events)
        with self.assertRaises(ValueError):self.repair(second)
        self.assertEqual(len(second.events),count);self.assertTrue((self.job/'.repair.lock').exists())
    def test_state_write_failure_retains_claim_and_never_probes(self):
        with patch.object(w,'replace',side_effect=OSError('injected durable state failure')):
            with self.assertRaises(OSError):self.backup()
        self.assertTrue((self.job/'.backup.lock').exists());self.assertEqual(self.backend.events,[])
        with self.assertRaises(ValueError):self.backup()
    def test_writable_mount_failure_stops_before_create(self):
        self.backup();second=FakeBackend(self.card,fault=lambda c,b:1 if c[1:-1]==['mount','nobrowse'] else None)
        with self.assertRaises(ValueError):self.repair(second)
        self.no_flag();self.assertEqual(self.state()['repair_remaining'],0);self.assertEqual(self.state()['stage'],'failed_no_retry')
    def test_identity_change_after_writable_mount_stops_before_create(self):
        self.backup()
        def changed(c,b):
            if c[1:-1]==['mount','nobrowse']:b.uuid='wrong'
        second=FakeBackend(self.card,fault=changed)
        with self.assertRaises(ValueError):self.repair(second)
        self.no_flag();self.assertFalse((self.job/'create-intent.json').exists())
    def test_exclusive_create_failure_never_overwrites(self):
        self.backup();original_open=os.open
        def race(path,*args,**kwargs):
            if path=='boot2.flag' and 'dir_fd' in kwargs:(self.card/adapter.repair.FLAG).write_bytes(b'RACE')
            return original_open(path,*args,**kwargs)
        with patch.object(adapter.os,'open',side_effect=race),self.assertRaises(FileExistsError):self.repair()
        self.assertEqual((self.card/adapter.repair.FLAG).read_bytes(),b'RACE');self.assertFalse(self.state()['flag_create_returned_fd'])
    def test_flag_fsync_failure_retains_empty_flag_and_evidence(self):
        self.backup();original_open=os.open;original_sync=os.fsync;target_fd=None;failed=False
        def opened(path,*args,**kwargs):
            nonlocal target_fd
            fd=original_open(path,*args,**kwargs)
            if path=='boot2.flag' and 'dir_fd' in kwargs:target_fd=fd
            return fd
        def synced(fd):
            nonlocal failed
            if fd==target_fd and not failed:failed=True;raise OSError('injected flag fsync failure')
            return original_sync(fd)
        with patch.object(adapter.os,'open',side_effect=opened),patch.object(adapter.os,'fsync',side_effect=synced),self.assertRaises(OSError):self.repair()
        self.assertTrue(self.state()['flag_create_returned_fd']);self.assertEqual((self.card/adapter.repair.FLAG).read_bytes(),b'')
        self.assertFalse(self.state()['actual_card_repaired']);self.assertFalse((self.work/'after').exists())
    def test_postcreate_readback_corruption_stops_without_cleanup(self):
        self.backup();second=FakeBackend(self.card)
        second.on_sync=lambda b:(self.card/adapter.repair.FLAG).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.repair(second)
        self.assertEqual((self.card/adapter.repair.FLAG).read_bytes(),b'corrupt');self.assertTrue(self.state()['flag_create_returned_fd'])
        sync=second.events.index(['/bin/sync'])
        self.assertTrue(all(c[1:3]==['info','-plist'] for c in second.events[sync+1:]));self.assertTrue(second.mounted_now)
    def test_timeout_leaves_job_mutable_and_stops_further_commands(self):
        def unresolved(c,b):raise adapter.UnresolvedCommand(1777)
        self.backend.fault=unresolved
        with self.assertRaises(adapter.UnresolvedCommand):self.backup()
        state=self.state();self.assertEqual(state['stage'],'unresolved_no_retry');self.assertTrue(state['command_left_running']);self.assertFalse(state['forced_exit'])
        self.assertEqual(len(self.backend.events),1);self.assertFalse((self.job/'COMMITTED').exists());self.no_flag()
    def test_timeout_after_create_never_kills_or_rolls_back(self):
        self.backup()
        def unresolved(c,b):
            if c==['/bin/sync']:raise adapter.UnresolvedCommand(1888)
        second=FakeBackend(self.card,fault=unresolved)
        with self.assertRaises(adapter.UnresolvedCommand):self.repair(second)
        self.assertEqual(self.state()['stage'],'unresolved_no_retry');self.assertTrue(self.state()['flag_create_returned_fd'])
        self.assertEqual((self.card/adapter.repair.FLAG).read_bytes(),b'');self.assertFalse((self.job/'COMMITTED').exists())
        self.assertEqual(second.events[-1],['/bin/sync'])
    def test_post_recovery_failure_preserves_saved60_and_eject(self):
        self.backup()
        with patch.object(w,'verify_recovery',side_effect=ValueError('injected post acceptance failure')):
            with self.assertRaises(ValueError):self.repair()
        w.card.verify_snapshot(self.work/'after');self.assertEqual(len(w.load(self.work/'after/snapshot.json')['raw_files']),60)
        self.assertFalse(self.state()['actual_card_repaired']);self.assertTrue(self.state()['flag_create_returned_fd'])
    def test_physical_transport_timeout_does_not_kill_process(self):
        process=Mock(pid=1999);process.wait.side_effect=subprocess.TimeoutExpired('diskutil',30)
        with patch.object(adapter.subprocess,'Popen',return_value=process),self.assertRaises(adapter.UnresolvedCommand):
            adapter.MacBackend().launch(['fake-only'],self.work/'stdout',self.work/'stderr')
        process.kill.assert_not_called();process.terminate.assert_not_called()
    def test_wait_error_keeps_unknown_process_and_logs_unresolved(self):
        process=Mock(pid=2001);process.wait.side_effect=OSError('injected wait state unknown')
        with patch.object(adapter.subprocess,'Popen',return_value=process),self.assertRaises(adapter.UnresolvedCommand):
            adapter.MacBackend().launch(['fake-only'],self.work/'stdout',self.work/'stderr')
        process.kill.assert_not_called();process.terminate.assert_not_called()
    def test_malformed_disk_plists_stop_before_mount(self):
        for name,value,kind in [('root',[], 'list'),('partitions',dict(AllDisksAndPartitions=[dict(DeviceIdentifier='disk42',Partitions=['invalid'])]),'list'),
                              ('info',[], 'info')]:
            card,job,backend=case(self.work/name);original_launch=backend.launch
            def malformed(command,out,err,*,saved=original_launch,data=value,selected=kind):
                result=saved(command,out,err)
                if command[1:2]==[selected]:out.write_bytes(plistlib.dumps(data))
                return result
            backend.launch=malformed
            with self.assertRaises(ValueError):adapter.backup(job,repair_authorized=True,shutdown_card_connected=True,_backend=backend)
            self.assertFalse(any(c[1:2] in (['mount'],['unmount'],['eject']) for c in backend.events))
            self.assertFalse((card/adapter.repair.FLAG).exists())
    def test_volume_process_lock_blocks_other_jobs_before_io(self):
        fd=os.open(self.work/'A23-context65-flag-card-volume.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            adapter.fcntl.flock(fd,adapter.fcntl.LOCK_EX|adapter.fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.backup()
            self.assertEqual(self.backend.events,[])
        finally:os.close(fd)
        self.assertEqual(self.state()['stage'],'failed_no_retry')
    def test_pending_volume_owner_blocks_new_job_after_timeout(self):
        def unresolved(c,b):raise adapter.UnresolvedCommand(2111)
        self.backend.fault=unresolved
        with self.assertRaises(adapter.UnresolvedCommand):self.backup()
        active=self.work/'A23-context65-flag-card-volume-owner.json';original=active.read_bytes()
        another=self.work/'another-job';adapter.prepare(another,self.work/'another-before',self.work/'another-after')
        second=FakeBackend(self.card)
        with self.assertRaises(ValueError):adapter.backup(another,repair_authorized=True,shutdown_card_connected=True,_backend=second)
        self.assertEqual(second.events,[]);self.assertEqual(active.read_bytes(),original)
        self.assertEqual(w.load(active)['job'],str(self.job))
    def test_physical_session_rejects_temporary_mount(self):
        with self.assertRaises(ValueError):adapter.SessionCard(adapter.MacBackend(),'disk42s1','disk42',self.card)
    def test_model_postreceipt_never_passes_formal_baseline(self):
        self.backup();self.repair()
        with self.assertRaises(ValueError):w.verify_recovery(self.work/'after',w.materials()[1],simulation=False)
        import prepare_a23_context65_once as once
        preview=once.prepare(w.A/'A23-context65-once-card-model-preview.json',deployment=w.ROOT/'private/deployments/20261016-191203-path-span-window-30s',recovery=self.work/'after')
        self.assertFalse(preview['issuance_available']);self.assertFalse(preview['sequence_reserved'])
    def test_moved_archive_analyzes_without_live_card_history_or_latest(self):
        self.backup();self.repair();moved=self.work/'moved';shutil.copytree(self.job,moved)
        shutil.rmtree(self.card);shutil.rmtree(self.work/'before');shutil.rmtree(self.work/'after')
        with patch.object(w,'transition',side_effect=AssertionError('live history')),patch.object(w,'latest_snapshot',side_effect=AssertionError('live latest')):
            self.assertTrue(adapter.analyze(moved)['supplied_chain_consistent'])
        cli=subprocess.run([sys.executable,str(w.ROOT/'tools/context65_flag_card.py'),'analyze',str(moved)],capture_output=True,check=True)
        self.assertTrue(json.loads(cli.stdout)['supplied_chain_consistent'])
    def test_corrupt_or_forged_archive_is_rejected(self):
        self.backup();self.repair();state=w.load(self.job/'state.json');state['actual_card_repaired']=True
        (self.job/'state.json').write_bytes(w.b.canonical(state))
        for name in ('SHA256SUMS','COMMITTED'):(self.job/name).unlink()
        w.b.seal(self.job)
        with self.assertRaises(ValueError):adapter.analyze(self.job)


if __name__=='__main__':unittest.main()
