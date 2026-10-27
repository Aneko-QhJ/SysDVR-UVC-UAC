"""Isolated wait/prepare/start boundary and file-only receipt checks."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import analyze_a23_waiting_entry as analysis
import audit_a23_waiting_entry as audit
import collect_a23_execution_v3 as collection


def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()


class WaitingEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.base=Path(cls.temp.name).resolve()
        value=os.environ.get('A23_WAITING_ENTRY_REVIEW')
        cls.review=Path(value).resolve() if value else cls.base/'review'
        cls.audit=json.loads((cls.review/'audit.json').read_text()) if value else audit.run(cls.review)
        cls.binary=cls.review/'injected-entry'

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def case(self,name='ok'):return self.review/'fixtures'/name
    def load(self,name,file):return json.loads((self.case(name)/file).read_text())
    def clone(self):
        d=Path(tempfile.mkdtemp(dir=self.base))/'host';shutil.copytree(self.case(),d);return d

    def receipt(self):
        return dict(schema='A23-waiting-burst-consumed-receipt-1',backend='a23-waiting-burst-1',attempt_consumed=True,
            receiver_sha256=audit.sha(self.binary),build_manifest_sha256='0'*64,recipe_sha256='3'*64,
            plan=copy.deepcopy(analysis.WAIT_PLAN),preparation_id=str(uuid.uuid4()))

    def claim(self,directory,manifest='0'*64,recipe='3'*64):
        return subprocess.run([str(self.binary),'--claim-only',str(directory),str(self.binary),manifest,recipe],capture_output=True,text=True,timeout=10)

    def test_all_native_cases_are_injected_and_no_authority_is_raised(self):
        self.assertEqual(self.audit['native_case_count'],32)
        for name,result in self.audit['native_cases'].items():
            self.assertTrue(result['supplied_order_consistent']);self.assertFalse(result['same_physical_run_verified'])
            calls=self.load(name,'injected-calls.json');self.assertTrue(calls['injected_only'])
            for k in ('native_iokit_calls','real_sdk_objects','usb_requests','sd_accesses'):self.assertEqual(calls[k],0)
            for k in ('claims','sdk_opens','iso_submissions','burst_enqueues','aborts'):self.assertLessEqual(calls[k],1)
            for k in ('hardware_verified','usb_strict_pass','allow_next_burst'):self.assertIs(result[k],False)

    def test_prepare_owns_service_then_closes_waiter_before_first_control(self):
        r=self.load('ok','waiting-entry-result.json');calls=self.load('ok','injected-calls.json')
        self.assertTrue(r['prepared'] and r['started'] and r['waiter_closed']);self.assertEqual(r['handoffs'],1)
        self.assertEqual((calls['sdk_retains'],calls['sdk_releases'],calls['sdk_destroys'],calls['wait_destroys']),(1,1,1,1))
        result=analysis.analyze(self.case());self.assertTrue(result['sdk_analysis']['host_observation_complete'])
        self.assertTrue(result['sdk_analysis']['injected_fixture'])

    def test_refused_permit_or_interruption_before_open_never_prepares_sdk(self):
        for name in ('permit-denied','interrupt-claim','ambiguous','existing','waiting-only','sdk-journal-exists'):
            calls=self.load(name,'injected-calls.json');self.assertEqual(calls['sdk_opens'],0,name)
            self.assertEqual(calls['status_reads'],0,name);self.assertFalse(self.load(name,'waiting-entry-result.json')['started'])

    def test_exit_detach_and_interrupt_after_prepare_do_not_start_requests(self):
        for name in ('exit-prepared','detach-prepared','interrupt-start-intent','interrupt-open','extra-open'):
            calls=self.load(name,'injected-calls.json');self.assertEqual(calls['sdk_opens'],1,name)
            self.assertEqual((calls['status_reads'],calls['iso_submissions'],calls['burst_enqueues']),(0,0,0))
            self.assertEqual(calls['sdk_destroys'],1);self.assertEqual(calls['sdk_releases'],1)
        error=self.load('open-failed','waiting-entry-result.json')['preparation_error']
        self.assertEqual((error['domain'],error['code']),('injected-sdk-open',9))

    def test_close_failure_preserves_each_unreleased_reference_and_blocks_start(self):
        r=self.load('release-failed','waiting-entry-result.json')
        self.assertTrue(r['waiter_closed']);self.assertEqual(r['failed_releases'],3)
        self.assertEqual(r['unreleased_tokens'],[2,1,7]);self.assertFalse(r['started'])

    def test_every_wait_journal_rejection_blocks_start_even_if_bytes_exist(self):
        for name in self.audit['native_cases']:
            if not name.startswith('journal-'):continue
            r=self.load(name,'waiting-entry-result.json');self.assertTrue(r['wait_journal_failed'],name)
            self.assertFalse(r['started'],name);self.assertTrue((self.case(name)/'wait.jsonl').stat().st_size)
        self.assertFalse(self.load('journal-adapter-5','waiting-entry-result.json')['permit_claimed'])
        self.assertTrue(self.load('journal-claim_committed','waiting-entry-result.json')['permit_claimed'])

    def test_pending_io_keeps_sdk_resources_and_uses_no_more_wait_pumps(self):
        for name in ('iso-pending','control-pending','detach-running'):
            r=self.load(name,'waiting-entry-result.json');calls=self.load(name,'injected-calls.json')
            self.assertTrue(r['unresolved']);self.assertFalse(r['finished'])
            self.assertEqual((calls['sdk_destroys'],calls['sdk_releases'],calls['aborts']),(0,0,1 if name=='iso-pending' else 0),name)
        self.assertTrue(analysis.analyze(self.case('late-notification'))['sdk_analysis']['host_observation_complete'])

    def test_real_file_checker_is_connected_before_injected_sdk_open(self):
        d=self.case('file-permit');r=self.load('file-permit','waiting-entry-result.json')
        receipt=(d/'waiting-authorization.json').read_bytes();claim=json.loads((d/'WAIT_RECEIVER_CLAIMED').read_text())
        self.assertTrue(r['permit_claimed'] and r['started']);self.assertEqual(claim['receipt_sha256'],hashlib.sha256(receipt).hexdigest())
        self.assertEqual((claim['interface_id'],claim['device_id'],claim['speed']),(102,101,3))

    def test_file_receipt_claim_is_exclusive_durable_and_cannot_be_replayed(self):
        with tempfile.TemporaryDirectory(dir=self.base) as tmp:
            d=Path(tmp);raw=canonical(self.receipt());(d/'waiting-authorization.json').write_bytes(raw)
            p=self.claim(d);self.assertEqual(p.returncode,0,p.stderr)
            marker=(d/'WAIT_RECEIVER_CLAIMED').read_bytes();self.assertEqual(self.claim(d).returncode,2)
            self.assertEqual((d/'WAIT_RECEIVER_CLAIMED').read_bytes(),marker);self.assertEqual((d/'waiting-authorization.json').read_bytes(),raw)
            self.assertEqual(set(p.name for p in d.iterdir()),{'waiting-authorization.json','WAIT_RECEIVER_CLAIMED'})

    def test_old_or_changed_receipts_fail_before_claim(self):
        faults=('old-schema','old-backend','binary','manifest','recipe','uuid','extra','integer-flag','boolean-count','float-count','repeat','pump','missing','partial','duplicate','array','symlink','oversized')
        for fault in faults:
            with self.subTest(fault=fault),tempfile.TemporaryDirectory(dir=self.base) as tmp:
                d=Path(tmp);r=self.receipt()
                if fault=='old-schema':r['schema']='A23-burst-sdk-consumed-receipt-1'
                elif fault=='old-backend':r['backend']='iousbhost-single-burst-1'
                elif fault=='binary':r['receiver_sha256']='1'*64
                elif fault=='manifest':r['build_manifest_sha256']='1'*64
                elif fault=='recipe':r['recipe_sha256']='1'*64
                elif fault=='uuid':r['preparation_id']='bad'
                elif fault=='extra':r['allow_next_burst']=True
                elif fault=='integer-flag':r['attempt_consumed']=1
                elif fault=='boolean-count':r['plan']['max_handoffs']=True
                elif fault=='float-count':r['plan']['max_handoffs']=1.0
                elif fault=='repeat':r['plan']['repeat']=1
                elif fault=='pump':r['plan']['notification_pump_during_sdk_start']=True
                raw=canonical(r)
                if fault=='partial':raw=raw[:50]
                elif fault=='duplicate':raw=raw.replace(b'{',b'{"attempt_consumed":false,',1)
                elif fault=='array':raw=b'[]\n'
                elif fault=='oversized':raw=b' '*16385
                p=d/'waiting-authorization.json'
                if fault=='symlink':(d/'other').write_bytes(raw);p.symlink_to(d/'other')
                elif fault!='missing':p.write_bytes(raw)
                result=self.claim(d);self.assertEqual(result.returncode,2,result.stderr)
                self.assertFalse((d/'WAIT_RECEIVER_CLAIMED').exists())

    def test_preexisting_claim_and_wrong_expected_build_cannot_open_or_remove_files(self):
        with tempfile.TemporaryDirectory(dir=self.base) as tmp:
            d=Path(tmp);(d/'waiting-authorization.json').write_bytes(canonical(self.receipt()))
            self.assertEqual(self.claim(d,manifest='1'*64).returncode,2)
            self.assertFalse((d/'WAIT_RECEIVER_CLAIMED').exists())
            (d/'WAIT_RECEIVER_CLAIMED').write_text('retain failure marker')
            self.assertEqual(self.claim(d).returncode,2)
            self.assertEqual((d/'WAIT_RECEIVER_CLAIMED').read_text(),'retain failure marker')

    def test_analyzer_rejects_forged_order_identity_plan_types_and_partial_bytes(self):
        for fault in ('order','identity','binding','plan','clock','count','boolean-flag','partial','duplicate'):
            with self.subTest(fault=fault):
                d=self.clone();rows=analysis.lines(d/'wait.jsonl');result=json.loads((d/'waiting-entry-result.json').read_text())
                by={r['event']:r for r in rows}
                if fault=='order':by['claim_committed']['event'],by['sdk_open_intent']['event']='sdk_open_intent','claim_committed'
                elif fault=='identity':by['sdk_open_intent']['details']['interface_id']+=1
                elif fault=='binding':by['prepared']['details']['binding']['session_id']=str(uuid.uuid4())
                elif fault=='plan':by['begin']['details']['plan']['repeat']=1
                elif fault=='clock':by['begin']['details']['timebase_numerator']+=1
                elif fault=='count':by['waiter_closed']['details']['handoffs']=True
                elif fault=='boolean-flag':result['waiter_closed']=1
                raw=b''.join(canonical(r) for r in rows)
                if fault=='partial':raw=raw[:-2]
                elif fault=='duplicate':raw=raw.replace(b'{',b'{"index":999,',1)
                (d/'wait.jsonl').write_bytes(raw);(d/'waiting-entry-result.json').write_bytes(canonical(result))
                with self.assertRaises(ValueError):analysis.analyze(d)

    def test_explicit_source_closure_keeps_previous_inputs_and_live_tickets(self):
        old=json.loads((audit.PARENT/'audit.json').read_text());hashes=self.audit['source_hashes']
        for name,digest in old['source_hashes'].items():self.assertEqual(hashes[name],digest)
        for name in ('host/a23_passive_wait_adapter.c','host/a23_passive_wait_iokit.c','host/a23_waiting_burst_entry.h','host/io_usb_host_burst_sdk_driver.m','tests/io_usb_host_mock_adapter.h'):
            self.assertEqual(hashes[name],audit.sha(ROOT/name))
        for name,digest in self.audit['tickets_sha256'].items():self.assertEqual(audit.sha(audit.PARENT.parent/name),digest)
        self.assertFalse(self.audit['live_capture_launcher_integrated']);self.assertFalse(self.audit['build_gate_integrated'])

    def test_exe3_collector_preserves_wait_journal_without_claiming_device_provenance(self):
        exe=ROOT/'private/analysis/A23-execution-v3-candidate-review-20261015/normal-primary-ok-execution-ok.execution.bin'
        output=self.base/str(uuid.uuid4());r=collection.freeze(self.case(),exe,output,'03'+'00'*31)
        self.assertEqual((output/'host/wait.jsonl').read_bytes(),(self.case()/'wait.jsonl').read_bytes())
        self.assertTrue(analysis.analyze(output/'host')['supplied_order_consistent'])
        self.assertIs(r['same_physical_run_verified'],False);self.assertIs(r['hardware_verified'],False)


if __name__=='__main__':unittest.main()
