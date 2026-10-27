import base64
import copy
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
from analyze_io_usb_host_burst_collection import analyze,freeze,control_trace,LIMITS
from analyze_io_usb_host_collection import durable_write
from io_usb_host_burst_mock_log import synthetic_log,group


class BurstControlTests(unittest.TestCase):
    def check(self,log):return control_trace(log)['matches_fixed_plan']

    def test_three_pairs_preserved_without_bus_inference(self):
        r=control_trace(synthetic_log());self.assertTrue(r['matches_fixed_plan'])
        self.assertEqual([v[0] for v in r['vendor_records']],[0,1,0,1,0,1])
        self.assertEqual(r['inferred_request_phases'],['before','trigger','after'])
        self.assertFalse(r['request_count_verified']);self.assertFalse(r['bus_capture_verified'])

    def test_each_missing_duplicate_or_reordered_delivery_rejected(self):
        lines=synthetic_log().decode().splitlines()
        for i,line in enumerate(lines):
            if line.startswith('EP0['):
                with self.subTest(index=i):
                    self.assertFalse(self.check(('\n'.join(lines[:i]+lines[i+1:])+'\n').encode()))
                    self.assertFalse(self.check(('\n'.join(lines[:i]+[line]+lines[i:])+'\n').encode()))
        first=group(0xc1,0x51,0,168).encode();trigger=group(0x41,0x54,1,0).encode()
        self.assertFalse(self.check(synthetic_log().replace(first+trigger,trigger+first)))

    def test_broadcast_labels_not_request_ids_or_deduplicated(self):
        lines=[l for l in synthetic_log().decode().splitlines() if not l.startswith('EP0[1]')]
        self.assertFalse(self.check(('\n'.join(lines)+'\n').encode()))
        self.assertFalse(self.check(synthetic_log().replace(b'EP0[1]',b'EP0[2]')))
        self.assertFalse(self.check(synthetic_log().replace(b'wIndex mismatch, ignoring',b'unhandled request -> stall')))
        self.assertFalse(self.check(b'EP0[0]: wIndex mismatch, ignoring\n'+synthetic_log()))

    def test_extra_vendor_or_wrong_tuple_rejected(self):
        for request in [0x50,0x52,0x53,0x54,0x55]:
            self.assertFalse(self.check(synthetic_log()+group(0x41,request,1,0).encode()))
        for old,new in [(b'wVal=0x0001',b'wVal=0x0002'),(b'req=0x54',b'req=0x50'),
                        (b'wLen=168',b'wLen=167'),(b'wIdx=0x0002',b'wIdx=0x0003'),
                        (b'reqType=0xc1',b'reqType=0x41')]:
            self.assertFalse(self.check(synthetic_log().replace(old,new)))

    def test_disconnect_setup_error_and_enumeration_inside_window_rejected(self):
        marker=group(0x41,0x54,1,0).encode()
        for extra in [b'USB host disconnected\n',b'USB host connected\n',b'GetSetupPacket failed: 0x1\n',
                      b'ISO EP0: request for interface 1, ignoring\n',
                      b'EP0[0]: reqType=0x01 req=0x0b wVal=0x0000 wIdx=0x0001 wLen=0\nEP0[0]: wIndex mismatch, ignoring\n']:
            self.assertFalse(self.check(synthetic_log().replace(marker,extra+marker)))
        self.assertFalse(self.check(synthetic_log().replace(b'ISO seq=1',b'USB host disconnected\nISO seq=1')))
        # Legitimate standard dispatch during initial enumeration is outside the window.
        standard=b'EP0[0]: reqType=0x01 req=0x0b wVal=0x0000 wIdx=0x0001 wLen=0\nEP0[0]: wIndex mismatch, ignoring\n'
        self.assertTrue(self.check(standard+synthetic_log()))

    def test_submit_timing_and_completion_must_bind_trigger_phase(self):
        lines=synthetic_log().decode().splitlines()
        for prefix in ['ISO submit ','ISO timing ','ISO seq=']:
            self.assertFalse(self.check(('\n'.join(l for l in lines if not l.startswith(prefix))+'\n').encode()))
            extra=next(l for l in lines if l.startswith(prefix))
            self.assertFalse(self.check(synthetic_log()+extra.encode()+b'\n'))
        sp=next(i for i,l in enumerate(lines) if l.startswith('ISO submit '));tp=sp+1
        lines[sp],lines[tp]=lines[tp],lines[sp]
        self.assertFalse(self.check(('\n'.join(lines)+'\n').encode()))
        # Completion may be polled before the after-STATUS delivery.
        lines=synthetic_log().decode().splitlines();terminal=lines.pop(-2)
        lines.insert(next(i for i,l in enumerate(lines) if l.startswith('ISO timing '))+1,terminal)
        self.assertTrue(self.check(('\n'.join(lines)+'\n').encode()))


class BurstCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value=os.environ.get('A23_BURST_EXECUTOR_FIXTURES')
        if not value:raise unittest.SkipTest('set A23_BURST_EXECUTOR_FIXTURES to new native ISO7 mocks')
        cls.fixtures=Path(value)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.root=self.home/'collection';self.log=self.home/'synthetic-log.txt'
        self.log.write_bytes(synthetic_log())
        freeze(self.fixtures/'iso-first',self.log,self.root)

    def reseal(self):
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        raw=''.join(f'{digest(self.root/k)}  {k}\n' for k in sorted(LIMITS)).encode()
        (self.root/'SHA256SUMS').write_bytes(raw)
        (self.root/'COMMITTED').write_text(hashlib.sha256(raw).hexdigest()+'\n')

    def refresh_meta(self):
        from analyze_io_usb_host_burst_collection import metadata
        files={k:(self.root/k).read_bytes() for k in LIMITS if k!='collection.json'}
        (self.root/'collection.json').write_text(json.dumps(metadata(files)))
        self.reseal()

    def edit_status(self,change):
        p=self.root/'status-after.bin';raw=bytearray(p.read_bytes());change(raw);p.write_bytes(raw)
        j=self.root/'host/journal.jsonl';rows=[json.loads(s) for s in j.read_text().splitlines()]
        d=next(r['details'] for r in rows if r['event']=='status_after')
        d.update(raw_base64=base64.b64encode(raw).decode(),sha256=hashlib.sha256(raw).hexdigest())
        j.write_text(''.join(json.dumps(r)+'\n' for r in rows));self.refresh_meta()

    def test_clean_byte_binding_never_grants_hardware_policy(self):
        r=analyze(self.root);self.assertTrue(r['simulation_collection_pass'])
        self.assertTrue(r['simulation_device_relation_matches'])
        self.assertTrue(r['device']['diagnostics']['completion_matches'])
        self.assertEqual(r['device']['after_status']['report_count'],1)
        for key in ['hardware_verified','hardware_trigger_binding_verified','device_log_bound','bus_phase_verified',
                    'cross_clock_alignment_verified','callback_drain_verified','firmware_bytes_verified','allow_next_burst']:
            self.assertIs(r[key],False)

    def test_three_native_orders_and_late_or_duplicate_callbacks(self):
        for name in ['control-first','inline-control','control-late','duplicate-iso','duplicate-control','control-error','control-bytes','short-after']:
            r=freeze(self.fixtures/name,self.log,self.home/name)
            self.assertTrue(r['collection_integrity_verified'])
            self.assertEqual(r['simulation_collection_pass'],name in ['control-first','inline-control'])
            if name not in ['short-after']:self.assertTrue(r['simulation_device_relation_matches'])

    def test_report_count_zero_or_one_valid_two_ambiguous(self):
        self.edit_status(lambda b:struct.pack_into('<I',b,48,0))
        self.assertTrue(analyze(self.root)['simulation_collection_pass'])
        self.edit_status(lambda b:struct.pack_into('<I',b,48,2))
        r=analyze(self.root);self.assertFalse(r['simulation_collection_pass'])
        self.assertIn('ambiguous_report_count',r['failure_reasons'])

    def test_outer_rehash_cannot_change_original_status_or_core(self):
        p=self.root/'status-after.bin';raw=bytearray(p.read_bytes());raw[-1]^=1;p.write_bytes(raw);self.reseal()
        with self.assertRaisesRegex(ValueError,'original journal'):analyze(self.root)
        p.write_bytes(base64.b64decode(next(json.loads(s)['details']['raw_base64'] for s in
                     (self.root/'host/journal.jsonl').read_text().splitlines() if json.loads(s)['event']=='status_after')))
        p=self.root/'host/transfer/raw.bin';raw=bytearray(p.read_bytes());raw[512*192]^=1;p.write_bytes(raw);self.reseal()
        with self.assertRaisesRegex(ValueError,'hash mismatch'):analyze(self.root)

    def test_device_identity_wrong_urb_or_ticks_is_preserved_failure(self):
        original=synthetic_log()
        for old,new in [(b'URB=42',b'URB=43'),(b'urb=42',b'urb=43'),(b'ack-after=14',b'ack-after=9'),
                        (b'frequency=19200000',b'frequency=1000000000'),(b'seq=1 speed=3',b'seq=2 speed=3'),
                        (b'22.5.0',b'22.6.0'),(b'result=0 record=21',b'result=1 record=21')]:
            (self.root/'device-log.txt').write_bytes(original.replace(old,new));self.refresh_meta()
            r=analyze(self.root);self.assertTrue(r['collection_integrity_verified']);self.assertFalse(r['simulation_collection_pass'])
        (self.root/'device-log.txt').write_bytes(original[:-1]);self.refresh_meta()
        self.assertFalse(analyze(self.root)['simulation_collection_pass'])

    def test_iso7_bitmap_error_tags_context_and_terminal_independently_fail(self):
        original_status=(self.root/'status-after.bin').read_bytes();original_journal=(self.root/'host/journal.jsonl').read_bytes()
        for offset,value in [(4,1),(12,0x80000000),(16,0xff),(20,768),(32,0),(40,0x170000c0),
                             (44,0),(72,16384),(76,0),(80,0x40001),(84,0x1000026),(96,0xc00)]:
            (self.root/'status-after.bin').write_bytes(original_status);(self.root/'host/journal.jsonl').write_bytes(original_journal)
            self.edit_status(lambda b:struct.pack_into('<I',b,56+offset,value))
            r=analyze(self.root);self.assertTrue(r['host']['simulation_execution_complete'])
            self.assertFalse(r['simulation_collection_pass'])

    def test_correct_device_fields_cannot_mask_native_overall_failure(self):
        # Independent host audit binds overall and callback; alter a self-consistent
        # mock error transcript, not its result boolean alone.
        p=self.root/'host/transfer/metadata.json';meta=json.loads(p.read_text());meta['overall_u32']=0xe00002e7;p.write_text(json.dumps(meta))
        transfer=self.root/'host/transfer';raw=''.join(f'{hashlib.sha256((transfer/k).read_bytes()).hexdigest()}  {k}\n' for k in ['metadata.json','raw.bin','transactions.bin']).encode()
        (transfer/'SHA256SUMS').write_bytes(raw);(transfer/'COMMITTED').write_text(hashlib.sha256(raw).hexdigest()+'\n')
        j=self.root/'host/journal.jsonl';rows=[json.loads(s) for s in j.read_text().splitlines()]
        for row in rows:
            if row['event']=='iso_callback':row['details']['status_u32']=meta['overall_u32']
            if row['event']=='iso_snapshot':row['details']['overall_u32']=meta['overall_u32']
            if row['event']=='bundle_committed':row['details']['manifest_sha256']=hashlib.sha256(raw).hexdigest()
        j.write_text(''.join(json.dumps(r)+'\n' for r in rows));self.refresh_meta()
        r=analyze(self.root);self.assertTrue(r['simulation_device_relation_matches']);self.assertFalse(r['simulation_collection_pass'])

    def test_status_or_log_hash_and_source_relabel_rejected(self):
        p=self.root/'collection.json';original=p.read_bytes()
        for key,value in [('execution_mode','hardware'),('status_source','journal_raw_sdk_reply'),
                          ('device_log_source','supplied_device_log'),('hardware_verified',True),
                          ('journal_sha256','0'*64),('result_sha256','0'*64),('device_log_sha256','0'*64),
                          ('scenario',dict(kind='single_burst',first_sequence=True))]:
            meta=json.loads(original);meta[key]=value;p.write_text(json.dumps(meta));self.reseal()
            with self.assertRaisesRegex(ValueError,'mode/source/hash'):analyze(self.root)

    def test_cross_host_bundle_and_policy_relabel_rejected(self):
        shutil.rmtree(self.root/'host/transfer');shutil.copytree(self.fixtures/'control-first/transfer',self.root/'host/transfer')
        self.refresh_meta()
        with self.assertRaisesRegex(ValueError,'binding mismatch'):analyze(self.root)

    def test_exclusive_and_partial_freeze_never_replaces_or_commits(self):
        original=(self.root/'SHA256SUMS').read_bytes()
        with self.assertRaises(FileExistsError):freeze(self.fixtures/'iso-first',self.log,self.root)
        self.assertEqual((self.root/'SHA256SUMS').read_bytes(),original)
        out=self.home/'partial';count=0
        def fail(path,raw):
            nonlocal count
            count+=1
            if count==4:raise OSError('injected write failure')
            durable_write(path,raw)
        with patch('analyze_io_usb_host_burst_collection.durable_write',fail):
            with self.assertRaises(OSError):freeze(self.fixtures/'iso-first',self.log,out)
        self.assertFalse((out/'COMMITTED').exists())
        with self.assertRaises(ValueError):analyze(out)

    def test_missing_core_or_after_is_not_fabricated(self):
        for name in ['short-before','iso-rejected','journal-trigger-failed','iso-pending']:
            out=self.home/name
            with self.assertRaises(ValueError):freeze(self.fixtures/name,self.log,out)
            self.assertFalse(out.exists())

    def test_symlink_extra_missing_or_duplicate_schema_not_accepted(self):
        p=self.root/'device-log.txt';raw=p.read_bytes();p.unlink();p.symlink_to(self.log)
        with self.assertRaises(ValueError):analyze(self.root)
        p.unlink();p.write_bytes(raw);(self.root/'extra').write_text('')
        with self.assertRaises(ValueError):analyze(self.root)
        (self.root/'extra').unlink();p=self.root/'collection.json';raw=p.read_bytes();p.write_bytes(b'{"schema":"forged",'+raw[1:]);self.reseal()
        with self.assertRaisesRegex(ValueError,'duplicate'):analyze(self.root)


if __name__=='__main__':unittest.main()
