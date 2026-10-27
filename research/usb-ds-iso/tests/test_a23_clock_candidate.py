from fractions import Fraction
from pathlib import Path
import math,os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_clock_candidate as audit


class NativeClockCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_CLOCK_CANDIDATE_REVIEW'):cls.root=Path(os.environ['A23_CLOCK_CANDIDATE_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-clock-candidate-tests-',dir='/private/tmp')
            cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        cls.pin=audit.f.sha(audit.a.read(cls.root/'SHA256SUMS'))
        cls.report=audit.verify(cls.root,cls.pin)
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.report['results'][name]
    def test_fractional_shortfall_is_not_promoted_by_ceiling(self):
        row=self.row('fractional-shortfall')
        self.assertEqual(row['status'],0);self.assertEqual(row['rounded_up_ns'],250000000)
        self.assertFalse(row['minimum_met']);self.assertFalse(row['within_interval'])
        self.assertLess(Fraction(374999999*2,3),250000000)
    def test_fractional_equality_and_after_are_admitted(self):
        for case in ('fractional-equality','fractional-after'):
            self.assertTrue(self.row(case)['minimum_met']);self.assertTrue(self.row(case)['within_interval'])
    def test_existing_one_to_one_profile_keeps_exact_boundaries(self):
        self.assertFalse(self.row('current-profile-short')['minimum_met'])
        self.assertTrue(self.row('current-profile-equal')['minimum_met'])
        self.assertTrue(self.row('current-profile-after')['minimum_met'])
    def test_inclusive_maximum_matches_exact_fraction(self):
        self.assertTrue(self.row('maximum-equal')['maximum_met'])
        self.assertFalse(self.row('maximum-over')['maximum_met'])
    def test_zero_tick_and_zero_duration_are_arithmetic_values(self):
        self.assertTrue(self.row('zero-origin')['within_interval'])
        self.assertTrue(self.row('zero-interval')['within_interval'])
        self.assertFalse(self.row('zero-short')['minimum_met'])
    def test_domain_instance_and_profile_mismatches_are_refused(self):
        for case in ('cross-domain','different-instance','zero-instance','changed-numerator',
                     'changed-denominator','equivalent-but-different-timebase'):
            self.assertEqual(self.row(case)['status'],4)
    def test_unknown_domains_are_not_mapped_implicitly(self):
        for case in ('unknown-both','unknown-end-domain'):self.assertEqual(self.row(case)['status'],2)
    def test_unknown_owner_timebase_requires_explicit_data(self):
        self.assertEqual(self.row('unknown-owner-timebase')['status'],3)
        self.assertEqual(self.row('owner-declared-ratio')['status'],0)
        self.assertTrue(self.row('owner-declared-ratio')['within_interval'])
        self.assertFalse(self.report['actual_timebase_queried'])
    def test_supervisor_profile_requires_canonical_nanoseconds(self):
        self.assertTrue(self.row('supervisor-ns')['within_interval'])
        self.assertEqual(self.row('supervisor-scaled')['status'],3)
    def test_reversed_time_or_limits_do_not_underflow(self):
        self.assertEqual(self.row('reversed')['status'],5)
        self.assertEqual(self.row('limits-reversed')['status'],1)
    def test_maximum_width_products_do_not_wrap(self):
        self.assertEqual(self.row('limit-product-wide')['rounded_up_ns'],audit.U64)
        self.assertTrue(self.row('limit-product-wide')['within_interval'])
        self.assertTrue(self.row('duration-max')['within_interval'])
        self.assertEqual(self.row('duration-overflow')['status'],6)
    def test_fractional_ceiling_overflow_is_refused(self):
        v=self.report['cases']['ceil-only-overflow'];exact=Fraction((v[5]-v[0])*v[3],v[4])
        self.assertEqual(math.floor(exact),audit.U64);self.assertEqual(math.ceil(exact),audit.U64+1)
        self.assertEqual(self.row('ceil-only-overflow')['status'],6)
        self.assertFalse(self.row('large-denominator')['minimum_met'])
    def test_all_failures_clear_preseeded_output(self):
        for row in self.report['results'].values():
            if row['status']:
                self.assertEqual(row,dict(status=row['status'],rounded_up_ns=0,minimum_met=False,maximum_met=False,within_interval=False))
        self.assertEqual(set(self.report['status_counts']),set(map(str,range(7))))
        self.assertTrue(all(self.report['status_counts'][str(i)]>0 for i in range(7)))
    def test_optimized_and_ubsan_builds_have_clean_results(self):
        self.assertEqual(set(self.report['builds']),{'optimized','ubsan'})
        for mode,row in self.report['builds'].items():
            self.assertEqual(row['returncode'],0);self.assertEqual(row['compiler_stderr'],'')
            self.assertEqual(row['compiler_stdout'],'')
            if mode=='ubsan':self.assertIn('-fsanitize=undefined',row['command'])
        self.assertEqual(self.report['native_fixture_executions'],20)
    def test_malformed_wire_inputs_are_refused_in_both_builds(self):
        for rows in self.report['malformed_protocol'].values():
            self.assertEqual(len(rows),8)
            for row in rows.values():self.assertEqual(row['returncode'],2)
    def test_all_native_rows_match_independent_fraction_oracle(self):
        self.assertGreater(self.report['case_count'],2300)
        for name,v in self.report['cases'].items():self.assertEqual(self.row(name),audit.oracle(v),name)
    def test_python_oracle_rejects_non_native_integer_types_and_widths(self):
        for index,value in ((0,True),(0,-1),(0,2**64),(3,2**32),(6,2**31)):
            v=audit.row();v[index]=value
            with self.assertRaises(ValueError):audit.oracle(v)
    def test_pins_source442_and_hardware_boundary(self):
        row=audit.f.load(self.root/'audit.json')
        self.assertEqual((row['source_count'],row['prior_sources_unchanged']),(442,437))
        for flag in audit.FALSE:self.assertIs(self.report[flag],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.verify(self.root,'0'*64)


if __name__=='__main__':unittest.main()
