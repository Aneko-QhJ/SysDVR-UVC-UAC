import copy,json,shutil,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import build_a23_lifecycle_receiver as b
import audit_a23_lifecycle_receiver as audit
import collect_a23_lifecycle_execution as c

class LifecycleReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-life-host-');cls.root=Path(cls.tmp.name)
        cls.review=cls.root/'review';cls.result=audit.run(cls.review);cls.record=cls.result['offline_record'];cls.build=Path(cls.record['build'])
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def row(self,name='matching'):return self.result['collection_cases'][name]['analysis']
    def native(self,*args):return subprocess.run([str(self.build/'receiver'),*map(str,args)],capture_output=True,text=True,timeout=15)
    def test_distinct_identity_and_zero_use_build(self):
        self.assertEqual(self.record['schema'],'A23-waiting-receiver-record-4');self.assertEqual(self.record['remaining'],0)
        self.assertFalse(self.record['acquisition_enabled']);self.assertEqual(len(self.result['source_hashes']),202)
        self.assertEqual(self.native('--check-build',self.build).returncode,0)
        self.assertEqual(json.loads(self.native('--describe').stdout),b.description(self.record['device_binding']))
    def test_old_schemas_and_device_rejected(self):
        import a23_quiet_device_binding as prior
        with self.assertRaises(ValueError):prior.identity(b.DEVICE/'candidate')
        with self.assertRaises(ValueError):b.device.identity(prior.DEVICE/'window-30s')
        for schema in ('A23-waiting-receiver-record-3','A23-waiting-receiver-record-2'):
            row={**self.record,'schema':schema}
            with self.assertRaises(ValueError):b.verify_build(row)
    def test_native_receipt_guard_matches_python(self):
        good=self.review/'mock-runs/matching';self.assertEqual(self.native('--check-consumed',good,self.build).returncode,0)
        for name in ('old-receipt','wrong-runtime','wrong-npdm','duplicate-receipt'):
            self.assertEqual(self.native('--check-consumed',self.review/'mock-runs'/name,self.build).returncode,2,name)
    def test_matching_software_chain_and_context(self):
        row=self.row();self.assertTrue(row['bound_execution_chain_complete']);self.assertTrue(row['supplied_chain_complete'])
        self.assertTrue(row['lifecycle']['supplied_context_associated'])
    def test_missing_execution_is_absent_and_does_not_inherit_complete(self):
        for name in ('missing-execution','missing-both-results'):
            row=self.row(name);self.assertTrue(row['binding']['supplied_binding_consistent']);self.assertFalse(row['execution_present'])
            self.assertFalse(row['supplied_chain_complete']);self.assertFalse(row['lifecycle']['supplied_context_associated'])
            self.assertFalse((self.review/'collections'/name/'execution.bin').exists())
    def test_partial_execution_bytes_preserved(self):
        row=self.row('partial-execution');self.assertTrue(row['execution_present']);self.assertFalse(row['supplied_chain_complete'])
        self.assertEqual((self.review/'collections/partial-execution/execution.bin').stat().st_size,100)
    def test_valid_prefix_survives_bad_or_partial_tail(self):
        for name in ('partial-after-context','bad-tail-crc'):
            life=self.row(name)['lifecycle'];self.assertTrue(life['supplied_context_associated']);self.assertFalse(life['associated_prefix_has_clean_tail'])
            self.assertEqual(life['files'][0]['prefix']['valid_prefix_records'],12)
            self.assertFalse(self.row(name)['supplied_chain_complete'])
    def test_missing_context_does_not_block_independent_execution_verdict(self):
        for name in ('missing-lifecycle','prepared','quiet','before-context','truncated-header','bad-header-crc'):
            row=self.row(name);self.assertTrue(row['bound_execution_chain_complete']);self.assertFalse(row['supplied_chain_complete'])
    def test_mismatching_recipe_nonce_context_writer_and_clock_rejected(self):
        for name in ('wrong-recipe','different-nonce','wrong-context','wrong-writer','wrong-frequency','old-quiet-lifecycle'):
            row=self.row(name);self.assertTrue(row['bound_execution_chain_complete']);self.assertFalse(row['lifecycle']['supplied_context_associated'],name)
            self.assertFalse(row['supplied_chain_complete'])
    def test_multiple_files_are_not_automatically_selected(self):
        row=self.row('multiple-lifecycle')['lifecycle'];self.assertTrue(row['selection_ambiguous']);self.assertEqual(row['file_count'],2)
        self.assertFalse(row['supplied_context_associated'])
    def test_failed_bindings_cannot_inherit_matching_execution(self):
        for name in ('old-receipt','wrong-runtime','wrong-npdm','missing-process','sdk-mismatch','duplicate-receipt'):
            row=self.row(name);self.assertFalse(row['binding']['supplied_binding_consistent'],name);self.assertFalse(row['supplied_chain_complete'])
    def test_primary_failure_and_mismatch_distinct(self):
        self.assertFalse(self.row('missing-primary')['bound_execution_chain_complete'])
        self.assertFalse(self.row('primary-receipt-failure')['bound_execution_chain_complete'])
        self.assertFalse(self.row('primary-mismatch')['bound_execution_chain_consistent'])
        for name in ('sequence-mismatch','shape-mismatch'):self.assertFalse(self.row(name)['bound_execution_chain_consistent'])
    def test_static_reanalysis_can_move_and_tampering_rejected(self):
        packet=self.root/'moved';shutil.copytree(self.review/'collections/matching',packet)
        self.assertTrue(c.analyze(packet)['analysis']['supplied_chain_complete'])
        path=packet/'lifecycle'/audit.NAME;path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ValueError):c.analyze(packet)
    def test_short_zero_tail_keeps_prefix_without_complete_file_claim(self):
        row=self.row('short-zero-tail');life=row['lifecycle'];self.assertTrue(life['supplied_context_associated'])
        self.assertEqual(life['files'][0]['prefix']['tail'],'zero_tail');self.assertFalse(life['files'][0]['full_sized'])
        self.assertFalse(row['supplied_chain_complete'])
    def test_native_and_python_reject_copied_source_or_device_drift(self):
        # Modify only a disposable clone; sealed/current inputs remain untouched.
        case=self.root/'drift';repo=case/'repo';repo.mkdir(parents=True)
        for n in b.source_hashes():
            path=repo/n;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(b.REPO/n,path)
        dev=case/'device';dev.mkdir()
        for n in b.device.FILES:
            path=dev/n;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(b.DEVICE/'candidate'/n,path)
        record=b.build(case/'build',repo,dev);build=Path(record['build'])
        for path in (repo/'research/usb-ds-iso/host/a23_lifecycle_device_guard.inc',dev/'full.elf',dev/'main.npdm',dev/'sysmodule.json'):
            before=path.read_bytes();path.write_bytes(before+b' ')
            try:
                with self.assertRaises(ValueError):b.verify_build(record,repo)
                result=subprocess.run([str(build/'receiver'),'--check-build',str(build)],capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,2,str(path))
            finally:path.write_bytes(before)
        self.assertEqual(b.verify_build(record,repo),build)
    def test_file_only_claim_handoff_rechecks_receipt_and_is_single_use(self):
        run=self.root/'claim-run';run.mkdir();receipt=b.device.receipt(self.record)
        b.write(run/'waiting-authorization.json',receipt)
        binary=self.review/'injected-loop'
        def claim(mode):return subprocess.run([str(binary),mode,str(run),str(self.build)],capture_output=True,text=True,timeout=15)
        self.assertEqual(claim('--claim-sdk-only').returncode,2)
        self.assertEqual(claim('--claim-process-only').returncode,0)
        self.assertEqual(claim('--claim-process-only').returncode,2)
        receipt['recipe_sha256']='00'*32;(run/'waiting-authorization.json').write_bytes(b.canonical(receipt))
        self.assertEqual(claim('--claim-sdk-only').returncode,2);self.assertFalse((run/'WAIT_RECEIVER_CLAIMED').exists())
    def test_new_collector_has_no_dependency_on_live_source_after_freeze(self):
        packet=self.root/'offline';shutil.copytree(self.review/'collections/matching',packet)
        with patch.object(b,'verify_build',side_effect=AssertionError('live read')):
            self.assertTrue(c.analyze(packet)['analysis']['supplied_chain_complete'])
        (packet/'unexpected').mkdir()
        with self.assertRaises(ValueError):c.analyze(packet)
    def test_resealed_generated_and_frozen_device_changes_reject(self):
        for index,name in enumerate(('generated/a23_waiting_burst_entry.m','device/main.npdm','device/full.elf')):
            folder=self.root/('resealed-'+str(index));shutil.copytree(self.build,folder)
            target=folder/name;target.write_bytes(target.read_bytes()+b' ')
            for seal in ('SHA256SUMS','COMMITTED'):(folder/seal).unlink()
            b.seal(folder)
            result=subprocess.run([str(folder/'receiver'),'--check-build',str(folder)],capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,2,name)
    def test_no_authority_flags_escalate(self):
        for packet in self.result['collection_cases'].values():
            for flag in c.POLICY:self.assertIs(packet[flag],False);self.assertIs(packet['analysis'][flag],False)
            life=packet['analysis']['lifecycle']
            for flag in ('own_commit_authenticated','physical_run_authenticated','join_results_authenticated','cleanup_authorized','last_stage_is_latest_execution_proof'):
                self.assertIs(life[flag],False)
        for flag in ('receiver_acquire_invoked','attempt_issued','device_rebuilt','device_executed','firmware_packaged','deployed','root_cause_confirmed'):
            self.assertIs(self.result[flag],False)

if __name__=='__main__':unittest.main()
