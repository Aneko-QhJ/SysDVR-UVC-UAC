from pathlib import Path
import copy,os,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_worker_failure_model as audit
m=audit.materials


class WorkerFailureModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        saved=os.environ.get('A23_WORKER_FAILURE_REVIEW')
        if saved:cls.root=Path(saved)
        else:cls.root=Path(tempfile.mkdtemp(prefix='a23-worker-test-'))/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'));cls.report=audit.verify(cls.root,cls.pin)
    def row(self,name):return next(r for r in self.report['fixture']['cases'] if r['case']==name)
    def cache(self,name):return audit.previous.cache(self.root/'work/materials-optimized'/name)
    def test_native_thirteen_schedules(self):self.assertEqual(len(self.report['fixture']['cases']),13);audit.validate(self.report['fixture'])
    def test_positive_readonly_completes(self):self.assertTrue(self.report['admission']['normal-readonly']['completion_eligible'])
    def test_worker_error_rejects_even_valid_clock(self):
        for n in ('error-before-begin','exit-before-begin'):
            r=self.report['admission'][n];self.assertTrue(r['clock_eligible']);self.assertFalse(r['worker_success']);self.assertFalse(r['completion_eligible'])
    def test_odd_store_stays_busy(self):
        for n in ('unfinished-return','unfinished-exit','wrong-ticket'):
            r=self.row(n);self.assertEqual((r['clock']['generation'],r['clock']['end_status'],r['clock']['reader_calls']),(3,3,1));self.assertTrue(r['clock']['end_zeroed'])
    def test_explicit_abort_does_not_restore_old_version(self):
        r=self.row('explicit-abort-after-join');self.assertEqual((r['clock']['recovery_status'],r['clock']['generation'],r['clock']['evaluate']),(0,4,4));self.assertFalse(self.report['admission'][r['case']]['completion_eligible'])
    def test_invalid_finish_poisons(self):self.assertEqual((self.row('invalid-finish')['worker']['finish_status'],self.row('invalid-finish')['clock']['end_status']),(2,5))
    def test_exhaustion_no_wrap(self):
        for n in ('exhausted-begin','last-finish-exhausted'):
            r=self.row(n);self.assertEqual(r['clock']['generation'],m.U64-1);self.assertTrue(r['clock']['poisoned']);self.assertEqual(r['clock']['end_status'],5)
    def test_replacement_same_declared_incarnation_rejected(self):
        r=self.row('replacement-store');self.assertEqual((r['clock']['pre_generation'],r['clock']['end_generation'],r['clock']['evaluate']),(2,2,4));self.assertFalse(r['clock']['same_store'])
    def test_every_material_is_required(self):
        for n in m.NAMES:
            for path in self.cache(n):
                c=self.cache(n);del c[path]
                with self.assertRaises(ValueError):m.admit(n,c)
    def test_every_truncated_material_rejected(self):
        for path in self.cache('normal-readonly'):
            c=self.cache('normal-readonly');c[path]=c[path][:-1]
            with self.assertRaises(ValueError):m.admit('normal-readonly',c)
    def test_extra_material_rejected(self):
        c=self.cache('normal-readonly');c['worker-extra.json']=b'{}'
        with self.assertRaises(ValueError):m.admit('normal-readonly',c)
    def test_all_worker_and_clock_fields_rejected_after_reseal(self):
        count=0
        for n in m.NAMES:
            for section in ('worker','clock'):
                for key,value in self.row(n)[section].items():
                    row=copy.deepcopy(self.row(n));row[section][key]=not value if type(value) is bool else value+1
                    with self.assertRaises(ValueError):m.admit(n,m.package(row))
                    count+=1
        self.assertEqual(count,299)
    def test_cross_case_material_rejected(self):
        with self.assertRaises(ValueError):m.admit('normal-readonly',self.cache('error-before-begin'))
    def test_boolean_integer_substitution_rejected(self):
        row=copy.deepcopy(self.row('normal-readonly'));row['worker']['join_status']=False
        with self.assertRaises(ValueError):m.admit(row['case'],m.package(row))
    def test_duplicate_nonfinite_and_nonbytes_rejected(self):
        for bad in (b'{"a":0,"a":1}',b'{"a":NaN}'):
            with self.assertRaises(ValueError):m.parse(bad)
        c=self.cache('normal-readonly');c['worker.json']='{}'
        with self.assertRaises(ValueError):m.admit('normal-readonly',c)
    def test_oversize_json_rejected(self):
        with self.assertRaises(ValueError):m.parse(b' '* (2*1024*1024+1))
    def test_consumer_no_filesystem_calls(self):
        caches={n:self.cache(n) for n in m.NAMES}
        with patch('builtins.open',side_effect=AssertionError('consumer filesystem')),patch('io.open',side_effect=AssertionError('consumer filesystem')):
            for n,c in caches.items():self.assertEqual(m.admit(n,c)['consumer_filesystem_calls'],0)
    def test_source_inventory_and_scope(self):
        r=audit.f.load(self.root/'audit.json');self.assertEqual((r['source_count'],r['prior_sources_unchanged']),(483,479))
        for k in audit.FALSE:self.assertIs(self.report[k],False)
    def test_bad_pin_rejected(self):
        with self.assertRaises(ValueError):audit.verify(self.root,'0'*64)
    def test_only_readonly_schedule_eligible(self):self.assertEqual([n for n,r in self.report['admission'].items() if r['completion_eligible']],['normal-readonly'])


if __name__=='__main__':unittest.main()
