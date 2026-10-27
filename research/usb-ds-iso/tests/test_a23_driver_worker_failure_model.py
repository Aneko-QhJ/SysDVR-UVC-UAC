from pathlib import Path
import copy,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_driver_worker_failure_model as audit
d=audit.diagnostics


class DriverWorkerFailureModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_DRIVER_WORKER_FAILURE_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-driver-worker-test-'))/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
        cls.native=audit.f.load(cls.root/'work/stdout-optimized.json')
    def row(self,name):return copy.deepcopy(self.native['cases'][name])
    def cache(self,name):return audit.cache(self.root/'work/models-optimized'/name)
    def test_all_eighty_seven_cases(self):self.assertEqual(len(self.report['semantic']),87)
    def test_worker_error_is_external_admission_counterexample(self):
        for n in d.GOOD:
            r=self.report['semantic'][n];self.assertTrue(r['driver_complete']);self.assertFalse(r['worker_success']);self.assertFalse(r['completion_admitted'])
    def test_all_fifteen_worker_admissions_rejected(self):
        for n in audit.model.CASES:self.assertFalse(self.report['semantic'][n]['completion_admitted'])
    def test_capture_failures_clear_outputs(self):
        for n in audit.model.CASES:
            if n.startswith('capture-worker-') and n not in d.GOOD:
                t=self.row(n)['worker_failure'];self.assertIn(t['capture_status'],(3,5));self.assertTrue(t['capture_output_zeroed']);self.assertEqual(self.row(n)['version']['end_generation'],0)
    def test_capture_return_failure_blocks_commit(self):
        for n in ('capture-return-worker-unfinished','capture-return-worker-exhausted'):
            r=self.row(n);self.assertEqual(r['worker_failure']['capture_status'],0);self.assertEqual((r['version']['end_generation'],r['version']['released_generation']),(2,0));self.assertIn('observation_version',r['result']['failure_reasons'])
    def test_gate_busy_worker_does_not_steal_ticket(self):
        for n in ('gate-worker-busy-error','gate-worker-object-replace'):
            r=self.row(n);self.assertEqual((r['worker_failure']['begin_status'],r['worker_failure']['ticket']),(3,0));self.assertEqual((r['version']['append_generation'],r['version']['released_generation'],r['version']['current_generation']),(3,4,4))
    def test_object_replace_releases_original_owner(self):
        r=self.row('gate-worker-object-replace');self.assertFalse(r['result']['complete']);self.assertTrue(r['version']['object_bound']);self.assertIn('observation_clock',r['result']['failure_reasons']);self.assertEqual(r['version']['released_generation'],4)
    def test_exhaustion_poisoned_without_wrap(self):
        for n in audit.model.CASES:
            if 'exhausted' in n:self.assertEqual(self.row(n)['worker_failure']['after_generation'],d.U64-1);self.assertTrue(self.row(n)['worker_failure']['poisoned'])
    def test_after_release_and_receipt_distinguish_snapshot(self):
        for suffix in ('unfinished','exhausted'):
            a=self.row('after-release-worker-'+suffix);b=self.row('after-receipt-worker-'+suffix)
            self.assertTrue(a['receipt_status']['saved']);self.assertFalse(a['receipt_status']['stale']);self.assertFalse(b['receipt_status']['saved']);self.assertTrue(b['receipt_status']['stale']);self.assertEqual(b['result']['quiet_end_ticks'],250000100)
    def test_every_missing_member_rejected(self):
        self.assertEqual(len(d.inventory()),24)
        for n in audit.model.CASES:
            original=self.cache(n);row=self.row(n)
            for path in original:
                c=dict(original);del c[path]
                with self.assertRaisesRegex(ValueError,'incomplete'):d.validate(n,row,c)
    def test_every_truncated_member_rejected(self):
        n='after-receipt-worker-unfinished';original=self.cache(n)
        for path in original:
            c=dict(original);c[path]=c[path][:-1]
            with self.assertRaises((ValueError,KeyError)):d.validate(n,self.row(n),c)
    def test_all_trace_fields_self_consistently_mutated(self):
        count=0
        for n in audit.model.CASES:
            original=self.row(n);cache=self.cache(n)
            for key,value in original['worker_failure'].items():
                row=copy.deepcopy(original);row['worker_failure'][key]=not value if type(value) is bool else value+1 if type(value) is int else value+'-changed'
                c=dict(cache);c['worker-failure.json']=d.encode(row['worker_failure']);c['worker-materials.json']=d.contract(n,c)
                with self.assertRaisesRegex(ValueError,'worker trace'):d.validate(n,row,c)
                count+=1
        self.assertEqual(count,270)
    def test_all_version_fields_self_consistently_mutated(self):
        count=0
        for n in audit.model.CASES:
            original=self.row(n);cache=self.cache(n)
            for key,value in original['version'].items():
                row=copy.deepcopy(original);row['version'][key]=not value if type(value) is bool else value+1 if type(value) is int else value+'-changed'
                c=dict(cache);c['version-profile.json']=d.encode(row['version']);c['worker-materials.json']=d.contract(n,c)
                with self.assertRaisesRegex(ValueError,'worker version'):d.validate(n,row,c)
                count+=1
        self.assertEqual(count,255)
    def test_every_fault_fact_mutation_rejected(self):
        for n in audit.model.CASES:
            original=self.row(n);cache=self.cache(n)
            for key,value in original['facts'].items():
                row=copy.deepcopy(original);row['facts'][key]=not value if type(value) is bool else value+1 if type(value) is int else value+'-changed' if type(value) is str else []
                c=dict(cache);c['fault-facts.json']=d.encode(row['facts']);c['worker-materials.json']=d.contract(n,c)
                with self.assertRaisesRegex(ValueError,'worker facts'):d.validate(n,row,c)
    def test_stale_receipt_rewritten_and_resealed_rejected(self):
        n='after-receipt-worker-unfinished';r=self.row(n);c=self.cache(n);c['sdk-receipt/snapshot.json']=d.encode(r['result'])
        receipt=d.parse(c['sdk-receipt/receipt.json']);receipt['snapshot']=r['result'];receipt['snapshot_sha256']=d.sha(c['sdk-receipt/snapshot.json']);c['sdk-receipt/receipt.json']=d.encode(receipt)
        sums=''.join(d.sha(c['sdk-receipt/'+k])+'  '+k+'\n' for k in ('receipt.json','snapshot.json')).encode();c['sdk-receipt/SHA256SUMS']=sums;c['sdk-receipt/COMMITTED']=(d.sha(sums)+'\n').encode();c['worker-materials.json']=d.contract(n,c)
        with self.assertRaisesRegex(ValueError,'stale snapshot'):d.validate(n,r,c)
    def test_extra_wrong_type_and_cross_case_material_rejected(self):
        n='capture-worker-error';r=self.row(n);c=self.cache(n);c['extra.json']=b'{}'
        with self.assertRaises(ValueError):d.validate(n,r,c)
        c=self.cache(n);c['worker-failure.json']='{}'
        with self.assertRaises(ValueError):d.validate(n,r,c)
        with self.assertRaises(ValueError):d.validate(n,r,self.cache('capture-worker-exit'))
    def test_pure_consumer_opens_no_files(self):
        materials={n:(self.row(n),self.cache(n)) for n in audit.model.CASES}
        with patch('builtins.open',side_effect=AssertionError('filesystem')),patch('io.open',side_effect=AssertionError('filesystem')):
            for n,(r,c) in materials.items():self.assertEqual(d.validate(n,r,c)['consumer_filesystem_calls'],0)
    def test_only_generated_main_changed(self):
        for key,value in audit.model.old_model.render(self.root/'source').items():
            if key!=audit.BASE+'tests/model_main.m':self.assertEqual(value,audit.a.read(self.root/'work/generated'/key))
    def test_source_inventory_scope_and_external_pin(self):
        r=audit.f.load(self.root/'audit.json');self.assertEqual((r['source_count'],r['prior_sources_unchanged']),(488,483))
        for k in audit.FALSE:self.assertIs(self.report[k],False)
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_original_bypass_and_normal_remain(self):
        self.assertTrue(self.report['semantic']['profile-end-bypass']['complete']);self.assertTrue(self.report['semantic']['normal']['complete'])


if __name__=='__main__':unittest.main()
