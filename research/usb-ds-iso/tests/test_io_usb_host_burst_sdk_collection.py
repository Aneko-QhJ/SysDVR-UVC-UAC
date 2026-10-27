"""SDK collection byte binding, device relations, origin and failure preservation."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_io_usb_host_burst_sdk_collection import analyze, freeze, metadata, limits_for, POLICY
from analyze_io_usb_host_burst_collection import analyze as simulation_collection
from analyze_io_usb_host_collection import analyze as no_td_collection, durable_write
from io_usb_host_burst_mock_log import synthetic_log, group


def load(path):return json.loads(path.read_bytes())
def seal(directory,names):
    raw=''.join(f'{hashlib.sha256((directory/k).read_bytes()).hexdigest()}  {k}\n' for k in sorted(names)).encode()
    (directory/'SHA256SUMS').write_bytes(raw);(directory/'COMMITTED').write_text(hashlib.sha256(raw).hexdigest()+'\n')


class SDKCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('A23_BURST_COORDINATOR_FIXTURES')
        if not value:raise unittest.SkipTest('set A23_BURST_COORDINATOR_FIXTURES to injected ISO7 coordinator fixtures')
        cls.fixtures=Path(value)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.root=self.home/'collection';self.log=self.home/'synthetic-log.txt'
        self.log.write_bytes(synthetic_log());freeze(self.fixtures/'iso-first',self.log,self.root,origin='injected_sdk_fixture')

    def paths(self):
        meta=load(self.root/'collection.json');return limits_for(meta['artifact_origin'],meta['has_retained_checkpoint'])

    def refresh(self):
        meta=load(self.root/'collection.json');files={k:(self.root/k).read_bytes() for k in self.paths()}
        (self.root/'collection.json').write_text(json.dumps(metadata(files,meta['artifact_origin'],meta['has_retained_checkpoint'])))
        seal(self.root,self.paths())

    def rows(self):return [json.loads(s) for s in (self.root/'host/session.jsonl').read_text().splitlines()]
    def save_rows(self,rows):
        (self.root/'host/session.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows));self.refresh()

    def change_status(self,change):
        raw=bytearray((self.root/'status-after.bin').read_bytes());change(raw);raw=bytes(raw)
        (self.root/'status-after.bin').write_bytes(raw);rows=self.rows()
        detail=next(r['details']['details'] for r in rows if r['event']=='adapter' and r['details']['event']=='status_after')
        detail.update(raw_base64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest())
        self.save_rows(rows)

    def change_checkpoint(self,directory,change):
        p=directory/'checkpoint.json';value=load(p);change(value);p.write_text(json.dumps(value));seal(directory,['checkpoint.json'])

    def test_clean_collection_preserves_sdk_shape_and_injected_origin(self):
        r=analyze(self.root)
        self.assertTrue(r['collection_integrity_verified']);self.assertTrue(r['supplied_artifact_relation_complete'])
        self.assertTrue(r['sdk_status_byte_binding_verified']);self.assertTrue(r['device_log_byte_binding_verified'])
        self.assertIs(r['injected_fixture'],True);self.assertEqual(r['artifact_origin'],'injected_sdk_fixture')
        self.assertTrue(r['device']['diagnostics']['completion_matches']);self.assertEqual(r['device']['runtime_record'],21)
        self.assertEqual(r['native_candidate']['empty_status_counts'],{'0x00000000':944})
        self.assertEqual([v[0] for v in r['control_trace']['vendor_records']],[0,1,0,1,0,1])
        for key in POLICY+('host_origin_verified','device_log_origin_verified'):self.assertIs(r[key],False)
        self.assertFalse(r['control_trace']['request_count_verified']);self.assertFalse(r['control_trace']['bus_capture_verified'])

    def test_all_five_native_orders_complete_and_failures_stay_failed(self):
        cases=['control-first','inline-control','queue-delayed-control','queue-delayed-iso','control-late','iso-late',
               'native-control-late','native-iso-late','control-error','control-bytes','accepted-control-error',
               'duplicate-control','trigger-rejected','short-after','error-after','overflow-after']
        for name in cases:
            r=freeze(self.fixtures/name,self.log,self.home/name,origin='injected_sdk_fixture')
            self.assertTrue(r['collection_integrity_verified'])
            self.assertEqual(r['supplied_artifact_relation_complete'],name in cases[:4],name)
            self.assertFalse(r['hardware_verified'])
            if name=='short-after':self.assertIsNone(r['device']);self.assertTrue(r['control_trace']['matches_fixed_plan'])

    def test_incomplete_pending_foreign_or_missing_core_refused_before_output(self):
        for name in ['control-pending','iso-pending','foreign-pointer','duplicate-iso','short-before','iso-rejected',
                     'detach-completed','detach-pending','save-failed','final-save-failed','retained-save-failed','journal-save-failed','journal-trigger-failed']:
            out=self.home/name
            with self.assertRaises((ValueError,OSError)):freeze(self.fixtures/name,self.log,out,origin='injected_sdk_fixture')
            self.assertFalse(out.exists(),name)

    def test_source_markers_cannot_be_relabelled_as_unverified_sdk_input(self):
        out=self.home/'unverified'
        with self.assertRaisesRegex(ValueError,'source files'):freeze(self.fixtures/'iso-first',self.log,out,origin='supplied_sdk_artifacts_unverified')
        self.assertFalse(out.exists())
        # A source without injection declarations is still explicitly
        # unverified. Removing a marker never creates origin authentication.
        supplied=self.home/'supplied';shutil.copytree(self.fixtures/'iso-first',supplied)
        for name in ['MOCK_ONLY.txt','fixture-calls.json','result.json']:(supplied/name).unlink()
        r=freeze(supplied,self.log,out,origin='supplied_sdk_artifacts_unverified')
        self.assertFalse(r['host_origin_verified']);self.assertFalse(r['device_log_origin_verified']);self.assertFalse(r['hardware_verified'])

    def test_legacy_simulation_and_no_td_collection_readers_reject_new_schema(self):
        with self.assertRaises(ValueError):simulation_collection(self.root)
        with self.assertRaises(ValueError):no_td_collection(self.root,hardware=True)

    def test_report_count_zero_one_valid_two_is_ambiguous(self):
        self.change_status(lambda b:struct.pack_into('<I',b,48,0));self.assertTrue(analyze(self.root)['supplied_artifact_relation_complete'])
        self.change_status(lambda b:struct.pack_into('<I',b,48,2));r=analyze(self.root)
        self.assertFalse(r['supplied_artifact_relation_complete']);self.assertIn('report_count_invalid',r['failure_reasons'])

    def test_iso7_context_terminal_bitmap_tags_and_pointer_fail_independently(self):
        raw=(self.root/'status-after.bin').read_bytes();journal=(self.root/'host/session.jsonl').read_bytes()
        for offset,value in [(4,1),(8,0x47d01411),(12,0x80000017),(16,0xff),(20,768),(24,1),
                             (32,0),(40,0x170000c0),(44,0),(72,16384),(76,0),(80,0x40001),(84,0x1000026),(96,0xc00)]:
            (self.root/'status-after.bin').write_bytes(raw);(self.root/'host/session.jsonl').write_bytes(journal)
            self.change_status(lambda b:struct.pack_into('<I',b,56+offset,value));r=analyze(self.root)
            self.assertTrue(r['host']['host_observation_complete']);self.assertFalse(r['supplied_artifact_relation_complete'],offset)

    def test_device_boot_install_build_urb_and_clock_mismatches_preserved(self):
        raw=synthetic_log()
        for old,new in [(b'URB=42',b'URB=43'),(b'urb=42',b'urb=43'),(b'ack-after=14',b'ack-after=9'),
                        (b'frequency=19200000',b'frequency=1000000000'),(b'22.5.0',b'22.6.0'),
                        (b'record=21',b'record=22'),(b'result=0 record=21',b'result=1 record=21'),
                        (b'BuildID=AD8D',b'BuildID=AA8D'),(b'seq=1 speed=3',b'seq=2 speed=3')]:
            (self.root/'device-log.txt').write_bytes(raw.replace(old,new));self.refresh();r=analyze(self.root)
            self.assertTrue(r['collection_integrity_verified']);self.assertFalse(r['supplied_artifact_relation_complete'],old)
        (self.root/'device-log.txt').write_bytes(raw[:-1]);self.refresh();self.assertFalse(analyze(self.root)['supplied_artifact_relation_complete'])
        (self.root/'device-log.txt').write_bytes(b'\xff\n');self.refresh();self.assertFalse(analyze(self.root)['supplied_artifact_relation_complete'])

    def test_control_broadcast_duplicate_missing_wrong_tuple_and_disconnect_rejected(self):
        raw=synthetic_log();marker=group(0x41,0x54,1,0).encode()
        mutations=[raw.replace(b'EP0[1]',b'EP0[2]'),raw.replace(b'req=0x54',b'req=0x50'),raw+marker,
                   raw.replace(marker,b'USB host disconnected\n'+marker),raw.replace(b'wLen=168',b'wLen=167'),
                   b'\n'.join(l for l in raw.splitlines() if not l.startswith(b'EP0[1]'))+b'\n']
        for log in mutations:
            (self.root/'device-log.txt').write_bytes(log);self.refresh();r=analyze(self.root)
            self.assertFalse(r['supplied_artifact_relation_complete']);self.assertIn('control_dispatch_failed',r['failure_reasons'])

    def test_original_status_core_and_checkpoint_survive_outer_rehash(self):
        p=self.root/'status-after.bin';original=p.read_bytes();bad=bytearray(original);bad[-1]^=1;p.write_bytes(bad);self.refresh()
        with self.assertRaisesRegex(ValueError,'original SDK journal'):analyze(self.root)
        p.write_bytes(original);p=self.root/'host/transfer/raw.bin';bad=bytearray(p.read_bytes());bad[512*192]^=1;p.write_bytes(bad);self.refresh()
        with self.assertRaisesRegex(ValueError,'hash mismatch'):analyze(self.root)

    def test_rehashed_origin_identity_flags_and_fixed_scenario_cannot_grant_policy(self):
        p=self.root/'collection.json';original=p.read_bytes()
        for key,value in [('artifact_origin','supplied_sdk_artifacts_unverified'),('execution_mode','simulation'),
                          ('status_source','journal_raw_mock_reply'),('device_log_source','verified_device_log'),
                          ('hardware_verified',True),('capture_binding_verified',True),('injected_fixture',False),
                          ('expected_runtime_record',22),('first_frame',101),('scenario',dict(kind='single_burst',first_sequence=True)),
                          ('binding',dict(session_id='wrong')),('journal_sha256','0'*64)]:
            meta=json.loads(original);meta[key]=value;p.write_text(json.dumps(meta));seal(self.root,self.paths())
            with self.assertRaises(ValueError):analyze(self.root)
            p.write_bytes(original)

    def test_frozen_late_recovery_keeps_retained_checkpoint(self):
        for name in ['control-late','iso-late']:
            root=self.home/name;freeze(self.fixtures/name,self.log,root,origin='injected_sdk_fixture')
            self.assertTrue(load(root/'collection.json')['has_retained_checkpoint'])
            self.assertEqual((root/'host/retained/checkpoint.json').read_bytes(),(self.fixtures/name/'retained/checkpoint.json').read_bytes())
            shutil.rmtree(root/'host/retained')
            with self.assertRaisesRegex(ValueError,'source files'):analyze(root)

    def test_rehashed_retained_identity_failure_counter_or_policy_conflicts_rejected(self):
        source=self.fixtures/'control-late'
        for change in [lambda v:v['binding'].__setitem__('session_id','wrong'),lambda v:v.__setitem__('hardware_verified',True),
                       lambda v:v['transport'].__setitem__('iso_callbacks',3),lambda v:v['failure_reasons'].append('erased'),
                       lambda v:v.__setitem__('ticks',v['exit_at_ticks']),lambda v:v.__setitem__('submitted_at_ticks',1),
                       lambda v:v.__setitem__('core_saved',1),lambda v:v.pop('hardware_verified')]:
            out=self.home/f'case-{len(list(self.home.iterdir()))}';shutil.copytree(source,out)
            self.change_checkpoint(out/'retained',change)
            target=self.home/f'frozen-{len(list(self.home.iterdir()))}'
            with self.assertRaises(ValueError):freeze(out,self.log,target,origin='injected_sdk_fixture')
            self.assertFalse(target.exists())

    def test_native_overall_and_empty_slot_errors_not_masked_by_device_payload(self):
        transfer=self.root/'host/transfer';meta=load(transfer/'metadata.json');meta['overall_u32']=0xe00002e7
        (transfer/'metadata.json').write_text(json.dumps(meta));seal(transfer,['raw.bin','transactions.bin','metadata.json'])
        rows=self.rows()
        for r in rows:
            if r['event']=='adapter' and r['details']['event']=='iso_callback':r['details']['details']['status_u32']=meta['overall_u32']
            if r['event']=='adapter' and r['details']['event']=='iso_snapshot':r['details']['details']['overall_u32']=meta['overall_u32']
        self.save_rows(rows);r=analyze(self.root)
        self.assertTrue(r['supplied_device_relation_matches']);self.assertFalse(r['supplied_artifact_relation_complete'])
        # A separate clean collection with a nonzero native empty-slot status.
        other=self.home/'empty-error';freeze(self.fixtures/'iso-first',self.log,other,origin='injected_sdk_fixture')
        self.root=other;transfer=other/'host/transfer';raw=bytearray((transfer/'transactions.bin').read_bytes());struct.pack_into('<I',raw,0,0xe00002e7)
        (transfer/'transactions.bin').write_bytes(raw);seal(transfer,['raw.bin','transactions.bin','metadata.json'])
        rows=self.rows();snap=next(r['details']['details'] for r in rows if r['event']=='adapter' and r['details']['event']=='iso_snapshot')
        snap['transactions_sha256']=hashlib.sha256(raw).hexdigest();self.save_rows(rows);r=analyze(self.root)
        self.assertTrue(r['host']['host_observation_complete']);self.assertTrue(r['supplied_device_relation_matches'])
        self.assertFalse(r['native_candidate']['candidate_rule_matches']);self.assertFalse(r['supplied_artifact_relation_complete'])

    def test_fixture_zero_call_claims_and_result_counts_bound(self):
        p=self.root/'host/fixture-calls.json';original=p.read_bytes()
        for key,value in [('usb_requests',1),('real_sdk_calls',False),('status_reads',3),('destroys',0)]:
            calls=json.loads(original);calls[key]=value;p.write_text(json.dumps(calls));self.refresh()
            with self.assertRaises(ValueError):analyze(self.root)
        p.write_bytes(original);p=self.root/'host/result.json';value=load(p);value['transport']['control_callbacks']=2;p.write_text(json.dumps(value));self.refresh()
        with self.assertRaises(ValueError):analyze(self.root)

    def test_write_failure_preserves_partial_without_commit_or_overwrite(self):
        out=self.home/'partial'
        with patch('analyze_io_usb_host_burst_sdk_collection.durable_write',side_effect=OSError('write failure')):
            with self.assertRaises(OSError):freeze(self.fixtures/'iso-first',self.log,out,origin='injected_sdk_fixture')
        self.assertFalse((out/'COMMITTED').exists())
        with self.assertRaises(FileExistsError):freeze(self.fixtures/'iso-first',self.log,out,origin='injected_sdk_fixture')

    def test_copied_core_is_validated_before_outer_commit(self):
        out=self.home/'damaged'
        def corrupt(path,raw):
            if path.name=='raw.bin':raw=bytes(len(raw))
            durable_write(path,raw)
        with patch('analyze_io_usb_host_burst_sdk_collection.durable_write',side_effect=corrupt):
            with self.assertRaises(ValueError):freeze(self.fixtures/'iso-first',self.log,out,origin='injected_sdk_fixture')
        self.assertFalse((out/'COMMITTED').exists())

    def test_copied_log_mutation_refused_before_outer_commit(self):
        out=self.home/'log-damaged'
        def corrupt(path,raw):
            if path.name=='device-log.txt':raw=raw.replace(b'URB=42',b'URB=43')
            durable_write(path,raw)
        with patch('analyze_io_usb_host_burst_sdk_collection.durable_write',side_effect=corrupt):
            with self.assertRaisesRegex(ValueError,'before collection commit'):freeze(self.fixtures/'iso-first',self.log,out,origin='injected_sdk_fixture')
        self.assertFalse((out/'COMMITTED').exists())

    def test_source_changes_during_freeze_are_refused_before_output(self):
        from analyze_io_usb_host_burst_sdk_collection import audit_host
        source=self.home/'changing';shutil.copytree(self.fixtures/'iso-first',source);out=self.home/'race'
        def change_after_audit(host):
            result=audit_host(host);(host/'MOCK_ONLY.txt').write_text('changed');return result
        with patch('analyze_io_usb_host_burst_sdk_collection.audit_host',side_effect=change_after_audit):
            with self.assertRaisesRegex(ValueError,'changed while freezing'):freeze(source,self.log,out,origin='injected_sdk_fixture')
        self.assertFalse(out.exists())

    def test_partial_commit_symlink_extra_duplicate_json_and_limits_rejected(self):
        p=self.root/'COMMITTED';original=p.read_bytes();p.write_text('0'*64+'\n')
        with self.assertRaises(ValueError):analyze(self.root)
        p.write_bytes(original);p=self.root/'host/final';p.rename(self.root/'external-final');p.symlink_to(self.root/'external-final')
        with self.assertRaises(ValueError):analyze(self.root)
        p.unlink();(self.root/'external-final').rename(p)
        (self.root/'host/extra').touch()
        with self.assertRaises(ValueError):analyze(self.root)
        (self.root/'host/extra').unlink();p=self.root/'collection.json';raw=p.read_bytes();p.write_bytes(b'{"schema":"forged",'+raw[1:]);seal(self.root,self.paths())
        with self.assertRaises(ValueError):analyze(self.root)


if __name__=='__main__':unittest.main()
