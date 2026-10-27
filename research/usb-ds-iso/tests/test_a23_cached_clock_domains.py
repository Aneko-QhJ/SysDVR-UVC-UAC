from pathlib import Path
from unittest.mock import patch
import os,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import audit_a23_cached_clock_domains as audit

class CachedClockDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=None
        if os.environ.get('A23_CLOCK_DOMAIN_REVIEW'):cls.root=Path(os.environ['A23_CLOCK_DOMAIN_REVIEW'])
        else:
            cls.tmp=tempfile.TemporaryDirectory(prefix='a23-clock-domain-tests-',dir='/private/tmp');cls.root=Path(cls.tmp.name)/'review';audit.run(cls.root)
        audit.a.sealed(cls.root);cls.results=audit.f.load(cls.root/'results.json')
        cls.builds,cls.journal,cls.roots=audit.factory.load_bundle(cls.root/'bundle')
    @classmethod
    def tearDownClass(cls):
        if cls.tmp:cls.tmp.cleanup()
    def row(self,name):return self.results['cases'][name]['result']
    def test_normal_driver_arithmetic_only(self):
        row=self.row('normal');self.assertEqual(row['errors'],[])
        self.assertTrue(row['model_driver_timing_arithmetic_consistent'])
        self.assertEqual(row['model_quiet_interval_ns'],250000101)
        self.assertEqual([(v['iso_arrival_ns'],v['control_arrival_ns']) for v in row['epochs']],[(800,200),(800,200)])
    def test_exact_callback_boundaries_are_inclusive(self):
        row=self.row('callback-limits');self.assertEqual(row['errors'],[])
        for e in row['epochs']:self.assertEqual((e['iso_arrival_ns'],e['control_arrival_ns']),(2000000000,16000000))
    def test_late_callbacks_are_rejected_after_coherent_rehash(self):
        for case in ('iso-late','control-late'):self.assertEqual(self.row(case)['errors'],['driver_timing'])
    def test_budget_boundaries_and_excess(self):
        self.assertEqual(self.row('budget-limits')['errors'],[])
        for e in self.row('budget-limits')['epochs']:self.assertEqual(e['trigger_age_ns'],32000000)
        for case in ('query-late','frame-old','enqueue-slow','trigger-late'):self.assertEqual(self.row(case)['errors'],['driver_timing'])
    def test_queue_delay_is_not_callback_arrival_delay(self):
        row=self.row('queued-delay');self.assertEqual(row['errors'],[])
        self.assertGreater(row['epochs'][0]['control_journal_delay_ns'],16000000)
        self.assertEqual(row['epochs'][0]['control_arrival_ns'],200)
    def test_owner_clock_is_excluded_from_arithmetic(self):
        normal=self.row('normal');shift=self.row('owner-clock-shift')
        self.assertEqual(shift['errors'],[])
        for before,after in zip(normal['epochs'],shift['epochs']):
            self.assertEqual(before['iso_arrival_ns'],after['iso_arrival_ns'])
            self.assertEqual(after['owner_arrival_ticks']-before['owner_arrival_ticks'],1000000)
            self.assertIsNone(before['owner_duration_ns'])
    def test_quiet_exact_threshold_and_short_or_incoherent_records(self):
        self.assertEqual(self.row('quiet-minimum')['model_quiet_interval_ns'],250000000)
        for case in ('quiet-short','quiet-reversed','quiet-before-saved','quiet-after-event'):
            self.assertEqual(self.row(case)['errors'],['quiet_timing'])
    def test_arithmetic_types_and_causality(self):
        for case in ('budget-arithmetic','trigger-arithmetic','callback-after-log','after-before-callback','save-before-observation-end','sample-reversed','check-bool'):
            self.assertEqual(self.row(case)['errors'],['driver_timing'])
    def test_profile_cannot_invent_mapping_or_claim_authority(self):
        for case,errors in audit.CASES.items():
            if errors==['clock_profile']:self.assertEqual(self.row(case)['errors'],errors)
    def test_cross_domain_and_unknown_timebase_refused(self):
        m=audit.model
        with self.assertRaisesRegex(ValueError,'cross-domain'):m.duration_ns(1,2,m.DRIVER,m.OWNER,m.DOMAINS)
        with self.assertRaisesRegex(ValueError,'unknown timebase'):m.duration_ns(1,2,m.OWNER,m.OWNER,m.DOMAINS)
    def test_exact_integer_ceiling_and_overflow(self):
        m=audit.model;domains={'test':dict(numerator=125,denominator=3)}
        self.assertEqual(m.duration_ns(0,1,'test','test',domains),42)
        self.assertEqual(m.duration_ns(0,3,'test','test',domains),125)
        with self.assertRaises(ValueError):m.duration_ns(0,2**64-1,'test','test',domains)
        with self.assertRaises(ValueError):m.duration_ns(False,1,'test','test',domains)
    def test_minimum_interval_does_not_round_a_fractional_shortfall_up(self):
        m=audit.model;domains={'fractional':dict(numerator=2,denominator=3)}
        self.assertEqual(m.duration_ns(0,374999999,'fractional','fractional',domains),250000000)
        self.assertFalse(m.minimum_elapsed(0,374999999,'fractional',domains,250000000))
        self.assertTrue(m.minimum_elapsed(0,375000000,'fractional',domains,250000000))
    def test_prior_failure_and_all_defined_cases(self):
        for case,errors in audit.CASES.items():self.assertEqual(self.row(case)['errors'],errors)
        self.assertEqual(self.row('prior-receipt')['errors'],['prior_subset'])
    def test_no_physical_timing_or_production_claims(self):
        for case in audit.CASES:
            for key in audit.model.FALSE:self.assertIs(self.row(case)[key],False)
        self.assertFalse((ROOT/'private/sequence-reservations32').exists())
    def test_consumer_no_file_opens_and_profile_anchor(self):
        r=self.builds['receiver'];s=self.builds['supervisor'];j=self.journal
        links=audit.factory.link_bytes(r,s,j,self.roots);profile=audit.f.encode(audit.model.profile(r,j))
        with patch('builtins.open',side_effect=AssertionError('open')),patch('os.open',side_effect=AssertionError('os.open')):
            row=audit.model.consume(r,s,j,links,audit.f.sha(links),profile,audit.f.sha(profile))
        self.assertEqual(row['errors'],[])
        with self.assertRaisesRegex(ValueError,'external clock profile pin'):
            audit.model.consume(r,s,j,links,audit.f.sha(links),profile,'0'*64)
    def test_source431_and_external_review_pin(self):
        row=audit.f.load(self.root/'audit.json');self.assertEqual((row['source_count'],row['prior_sources_unchanged']),(431,428))
        self.assertEqual(row['consumer_filesystem_opens'],0)
        with self.assertRaisesRegex(ValueError,'external review pin'):audit.replay(self.root,'0'*64)

if __name__=='__main__':unittest.main()
