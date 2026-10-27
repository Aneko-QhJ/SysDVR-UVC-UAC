"""Finite budget, identity and stop tests. No native lease or protocol adapter."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import unittest
from a23_q2_epoch_lease_model import Binding,Watermark,Conditions,EpochGate,Lease,SHAPE_SHA256

RESULTS={}
STEPS=[('before',0,3,0),('before',1,3,0),('before',2,17,2),
       ('burst',0,3,0),('burst',1,3,0),('burst',2,17,2),
       ('after',0,3,0),('after',1,3,0),('after',2,17,2)]


def binding():
    return Binding('one-model-segment','a'*64,'b'*64,'c'*64)


def conditions(**changes):
    base=Conditions(0,0,1,1,50,2,True,True,True,True)
    return replace(base,**changes)


def report(gate,base,*,tick=None,**changes):
    view=gate.view()
    value=replace(base,trace_used=view['last_accepted_trace'],identities_used=view['last_accepted_identities'],
                  tick=view['last_model_tick']+1 if tick is None else tick)
    return replace(value,**changes)


def started(*,trace=0,identities=0,cond=None,deadline=100,tick=0):
    base=Watermark(binding(),1,trace,identities,tick,deadline)
    gate=EpochGate(base.binding);lease=gate.reserve(base,cond or conditions())
    if lease is None or not gate.claim(lease,base):
        raise AssertionError('test setup requires a conditional model claim')
    return gate,lease,base


def before_and_arm(gate,lease,base):
    for step in STEPS[:3]:
        if not gate.observe_ready(lease,*step,report(gate,base)):
            raise AssertionError('expected before group')
    if not gate.arm_iso(lease,report(gate,base)):
        raise AssertionError('expected symbolic ISO arm')


def complete(gate,lease,base,*,extra_position=None):
    for index in range(10):
        if index==extra_position:
            if not gate.observe_nonrequest(lease,1,0,report(gate,base)):
                raise AssertionError('declared bounded nonrequest did not fit')
        if index==9:
            break
        if index==3 and not gate.arm_iso(lease,report(gate,base)):
            raise AssertionError('symbolic ISO arm refused')
        if not gate.observe_ready(lease,*STEPS[index],report(gate,base)):
            raise AssertionError('declared ready group refused')
    return gate.finish_shape(lease,report(gate,base))


class EpochLeaseTests(unittest.TestCase):
    def test_conditional_complete_shape_retains_credit(self):
        gate,lease,base=started(trace=100,identities=10)
        receipt=complete(gate,lease,base)
        self.assertEqual(9,receipt['shape_groups'])
        self.assertEqual(169,gate.view()['last_accepted_trace'])
        self.assertEqual(16,gate.view()['last_accepted_identities'])
        self.assertEqual((70,7),(gate.view()['reserved_trace'],gate.view()['reserved_identities']))
        self.assertFalse(receipt['native_IO_complete'])
        self.assertFalse(receipt['credit_reclaim_authorized'])
        self.assertFalse(gate.view()['credit_refunded'])

    def test_current216_refused_before_any_ISO(self):
        base=Watermark(binding(),1,216,19,0,100)
        gate=EpochGate(base.binding);lease=gate.reserve(base,conditions())
        self.assertIsNone(lease)
        self.assertFalse(gate.arm_iso(lease,base))
        self.assertFalse(gate.view()['ISO_symbolically_armed'])
        self.assertEqual(0,gate.view()['shape_groups'])
        RESULTS['old_local_midround_counterexample_prevented_in_model']=dict(
            initial_trace=216,conditional_request_reserve=69,stop_trace_reserve=1,
            initial_identities=19,refused_before_symbolic_ISO=True,actual_protocol_verified=False)

    def test_unknown_conditions_cannot_reserve(self):
        names=('extra_trace','extra_identities','stop_trace','stop_identities','epoch_ticks','stop_ticks',
               'shape_bound_assumed','bounded_external_traffic_assumed','duration_bound_assumed','ownership_ready_assumed')
        for name in names:
            gate=EpochGate(binding());base=Watermark(binding(),1,0,0,0,100)
            self.assertIsNone(gate.reserve(base,conditions(**{name:None})),name)
            self.assertTrue(gate.view()['attempt_consumed'])
            self.assertIsNone(gate.reserve(base,conditions()),name)

    def test_false_assumptions_do_not_become_real_grants(self):
        for name in ('shape_bound_assumed','bounded_external_traffic_assumed','duration_bound_assumed','ownership_ready_assumed'):
            gate=EpochGate(binding());base=Watermark(binding(),1,0,0,0,100)
            self.assertIsNone(gate.reserve(base,conditions(**{name:False})))

    def test_stop_margin_is_reserved_upfront(self):
        for trace,expected in ((186,True),(187,False)):
            gate=EpochGate(binding());base=Watermark(binding(),1,trace,25,0,100)
            self.assertEqual(expected,gate.reserve(base,conditions()) is not None)
        gate=EpochGate(binding());base=Watermark(binding(),1,0,26,0,100)
        self.assertIsNone(gate.reserve(base,conditions()))

    def test_zero_stop_trace_is_not_a_valid_margin(self):
        gate=EpochGate(binding());base=Watermark(binding(),1,0,0,0,100)
        self.assertIsNone(gate.reserve(base,conditions(stop_trace=0)))

    def test_snapshot_source_recipe_and_shape_bound(self):
        for name in ('segment','snapshot_sha256','source_sha256','recipe_sha256','shape_sha256'):
            changed=replace(binding(),**{name:'another' if name=='segment' else 'd'*64})
            gate=EpochGate(binding());base=Watermark(changed,1,0,0,0,100)
            self.assertIsNone(gate.reserve(base,conditions()),name)
        wrong=replace(binding(),shape_sha256='d'*64);gate=EpochGate(wrong)
        self.assertIsNone(gate.reserve(Watermark(wrong,1,0,0,0,100),conditions()))

    def test_watermark_counter_drift_before_claim(self):
        for field in ('trace_used','identities_used','generation'):
            base=Watermark(binding(),1,0,0,0,100);gate=EpochGate(binding())
            lease=gate.reserve(base,conditions())
            self.assertFalse(gate.claim(lease,replace(base,**{field:getattr(base,field)+1})))
            self.assertFalse(gate.view()['counters_trusted_in_model'])
            self.assertFalse(gate.view()['ISO_symbolically_armed'])

    def test_expired_lease_before_claim(self):
        base=Watermark(binding(),1,0,0,0,100);gate=EpochGate(binding())
        lease=gate.reserve(base,conditions(epoch_ticks=10))
        self.assertFalse(gate.claim(lease,replace(base,tick=89)))
        self.assertFalse(gate.view()['ISO_symbolically_armed'])

    def test_claim_is_once(self):
        gate,lease,base=started()
        self.assertFalse(gate.claim(lease,base))
        self.assertTrue(gate.view()['reservation_retained'])
        self.assertFalse(gate.view()['credit_refunded'])

    def test_ready_before_claim_is_refused(self):
        base=Watermark(binding(),1,0,0,0,100);gate=EpochGate(binding());lease=gate.reserve(base,conditions())
        self.assertFalse(gate.observe_ready(lease,*STEPS[0],base))

    def test_ISO_cannot_arm_before_before_STATUS(self):
        gate,lease,base=started()
        self.assertFalse(gate.arm_iso(lease,report(gate,base)))
        self.assertFalse(gate.view()['ISO_symbolically_armed'])

    def test_ISO_arm_rechecks_current_counters(self):
        gate,lease,base=started()
        for step in STEPS[:3]:self.assertTrue(gate.observe_ready(lease,*step,report(gate,base)))
        self.assertFalse(gate.arm_iso(lease,report(gate,base,trace_used=24)))
        self.assertFalse(gate.view()['counters_trusted_in_model'])
        self.assertFalse(gate.view()['ISO_symbolically_armed'])

    def test_duplicate_ISO_arm_stops(self):
        gate,lease,base=started();before_and_arm(gate,lease,base)
        self.assertFalse(gate.arm_iso(lease,report(gate,base)))
        self.assertTrue(gate.view()['ISO_symbolically_armed'])
        self.assertTrue(gate.view()['reservation_retained'])

    def test_burst_without_ISO_invalidates(self):
        gate,lease,base=started()
        for step in STEPS[:3]:self.assertTrue(gate.observe_ready(lease,*step,report(gate,base)))
        self.assertFalse(gate.observe_ready(lease,*STEPS[3],report(gate,base)))
        self.assertFalse(gate.view()['counters_trusted_in_model'])

    def test_wrong_ready_shape_invalidates(self):
        for phase,interface in (('burst',0),('before',2),('handshake',0)):
            gate,lease,base=started()
            self.assertFalse(gate.observe_ready(lease,phase,interface,3,0,report(gate,base)))
            self.assertFalse(gate.view()['counters_trusted_in_model'])

    def test_ready_overrun_is_not_silently_rolled_back(self):
        gate,lease,base=started()
        self.assertFalse(gate.observe_ready(lease,'before',0,4,0,report(gate,base)))
        view=gate.view();self.assertFalse(view['counters_trusted_in_model'])
        self.assertEqual(0,view['last_accepted_trace'])
        self.assertEqual(4,view['last_report']['reported_trace_delta'])
        self.assertFalse(gate.record_stop(lease,1,0,report(gate,base)))

    def test_missing_mandatory_ready_records_invalidates(self):
        gate,lease,base=started()
        self.assertFalse(gate.observe_ready(lease,'before',0,0,0,report(gate,base)))
        self.assertFalse(gate.view()['counters_trusted_in_model'])

    def test_non_target_identity_post_invalidates(self):
        gate,lease,base=started()
        self.assertFalse(gate.observe_ready(lease,'before',0,3,1,report(gate,base)))
        self.assertFalse(gate.view()['counters_trusted_in_model'])

    def test_unbudgeted_nonrequest_invalidates(self):
        gate,lease,base=started()
        self.assertFalse(gate.observe_nonrequest(lease,1,0,report(gate,base)))
        self.assertFalse(gate.view()['counters_trusted_in_model'])
        self.assertTrue(gate.view()['reservation_retained'])

    def test_zero_cost_nonrequest_cannot_spin(self):
        gate,lease,base=started(cond=conditions(extra_trace=2))
        self.assertFalse(gate.observe_nonrequest(lease,0,0,report(gate,base)))

    def test_nonrequest_budget_exhaustion_stops(self):
        gate,lease,base=started(cond=conditions(extra_trace=1))
        self.assertTrue(gate.observe_nonrequest(lease,1,0,report(gate,base)))
        self.assertFalse(gate.observe_nonrequest(lease,1,0,report(gate,base)))
        self.assertEqual(1,gate.view()['last_accepted_trace'])
        self.assertFalse(gate.view()['counters_trusted_in_model'])

    def test_epoch_time_overrun_retains_and_marks_observation_unknown(self):
        gate,lease,base=started();before_and_arm(gate,lease,base)
        self.assertFalse(gate.observe_ready(lease,*STEPS[3],report(gate,base,tick=60)))
        self.assertTrue(gate.view()['ISO_symbolically_armed'])
        self.assertTrue(gate.view()['reservation_retained'])
        self.assertFalse(gate.view()['counters_trusted_in_model'])
        self.assertFalse(gate.view()['hard_deadline_proven'])

    def test_backwards_clock_does_not_extend_lease(self):
        gate,lease,base=started(tick=10)
        self.assertFalse(gate.arm_iso(lease,report(gate,base,tick=9)))
        self.assertEqual(10,gate.view()['last_model_tick'])

    def test_clock_domain_cannot_be_promoted_to_device(self):
        gate=EpochGate(binding());base=Watermark(binding(),1,0,0,0,100,domain='DEVICE_CLOCK')
        self.assertIsNone(gate.reserve(base,conditions()))

    def test_wrong_or_relabelled_token_refused(self):
        for field,value in (('digest','d'*64),('generation',2),('schema','DEVICE_GRANT')):
            gate,lease,base=started()
            self.assertFalse(gate.arm_iso(replace(lease,**{field:value}),report(gate,base)))
            self.assertTrue(gate.view()['reservation_retained'])

    def test_finish_requires_all_groups(self):
        gate,lease,base=started();before_and_arm(gate,lease,base)
        self.assertIsNone(gate.finish_shape(lease,report(gate,base)))

    def test_observed_extra_ready_after_shape_is_not_ignored(self):
        gate,lease,base=started();self.assertIsNotNone(complete(gate,lease,base))
        self.assertFalse(gate.observe_ready(lease,*STEPS[0],report(gate,base)))
        self.assertFalse(gate.view()['counters_trusted_in_model'])
        self.assertFalse(gate.record_stop(lease,1,0,report(gate,base)))

    def test_no_second_segment_or_refund_after_shape(self):
        gate,lease,base=started();self.assertIsNotNone(complete(gate,lease,base))
        self.assertIsNone(gate.reserve(base,conditions()))
        self.assertFalse(gate.view()['credit_refunded'])
        self.assertTrue(gate.view()['reservation_retained'])

    def test_stop_record_uses_reserved_credit_once(self):
        gate,lease,base=started();self.assertTrue(gate.stop(lease))
        self.assertTrue(gate.record_stop(lease,1,1,report(gate,base)))
        self.assertEqual((1,1),(gate.view()['last_accepted_trace'],gate.view()['last_accepted_identities']))
        self.assertFalse(gate.record_stop(lease,1,0,report(gate,base)))
        self.assertFalse(gate.view()['credit_refunded'])

    def test_stop_record_cannot_exceed_reserve(self):
        gate,lease,base=started();gate.stop(lease)
        self.assertFalse(gate.record_stop(lease,2,0,report(gate,base)))
        self.assertFalse(gate.view()['counters_trusted_in_model'])

    def test_stop_time_overrun_does_not_authorize_cleanup(self):
        gate,lease,base=started();gate.stop(lease)
        self.assertFalse(gate.record_stop(lease,1,0,report(gate,base,tick=3)))
        self.assertTrue(gate.view()['reservation_retained'])

    def test_strict_types_and_export_copy(self):
        with self.assertRaises(ValueError):Conditions(extra_trace=True)
        with self.assertRaises(ValueError):Conditions(ownership_ready_assumed=1)
        with self.assertRaises(ValueError):Watermark(binding(),True,0,0,0,100)
        base=Watermark(binding(),1,0,0,0,100)
        with self.assertRaises(FrozenInstanceError):base.trace_used=1
        gate,lease,_=started();view=gate.view();view['lease']['digest']='changed'
        self.assertEqual(lease.digest,gate.view()['lease']['digest'])

    def test_separate_controllers_are_not_global_device_authority(self):
        base=Watermark(binding(),1,0,0,0,100)
        one=EpochGate(binding());two=EpochGate(binding())
        self.assertIsNotNone(one.reserve(base,conditions()))
        self.assertIsNotNone(two.reserve(base,conditions()))
        self.assertFalse(one.view()['global_cross_controller_serialization'])
        self.assertFalse(two.view()['actual_device_grant_authenticated'])

    def test_no_exported_state_claims_real_authority(self):
        gate,lease,base=started();receipt=complete(gate,lease,base)
        for flag in ('actual_device_grant_authenticated','global_cross_controller_serialization',
                     'native_handoff_proven','hard_deadline_proven','lossless_rollover_verified',
                     'hardware_entry_enabled','formal_issuance_available'):
            self.assertIs(gate.view()[flag],False)
        self.assertFalse(receipt['real_evidence_committed'])
        self.assertFalse(receipt['next_segment_authorized'])

    def test_capacity_cross_product_against_source_thresholds(self):
        accepted=0;digest=hashlib.sha256()
        for trace in range(257):
            for identities in range(33):
                base=Watermark(binding(),1,trace,identities,0,100)
                gate=EpochGate(binding());lease=gate.reserve(base,conditions())
                # Independent thresholds: Q2c source shape69+stop1; identities6+stop1.
                expected=trace<=186 and identities<=25
                self.assertEqual(expected,lease is not None,(trace,identities))
                self.assertFalse(gate.view()['ISO_symbolically_armed'])
                accepted+=int(lease is not None)
                digest.update(json.dumps([trace,identities,expected,lease is not None],separators=(',',':')).encode()+b'\n')
        self.assertEqual(4862,accepted)
        RESULTS['capacity_grid']=dict(cases=8481,conditional_model_reservations=accepted,
            oracle='independent_source_thresholds_186_25',sha256=digest.hexdigest(),device_grants=0)

    def test_delayed_claim_time_grid(self):
        accepted=0;digest=hashlib.sha256()
        for tick in range(121):
            base=Watermark(binding(),1,0,0,0,100);gate=EpochGate(binding())
            lease=gate.reserve(base,conditions(epoch_ticks=10,stop_ticks=2))
            result=gate.claim(lease,replace(base,tick=tick))
            self.assertEqual(tick<=88,result,tick)
            self.assertFalse(gate.view()['ISO_symbolically_armed'])
            accepted+=int(result);digest.update(json.dumps([tick,result]).encode()+b'\n')
        self.assertEqual(89,accepted)
        RESULTS['delayed_claim_grid']=dict(cases=121,conditional_model_claims=accepted,
            oracle='claim_tick_at_most88_of_deadline100_with10plus2',sha256=digest.hexdigest(),hard_deadline_proven=False)

    def test_one_bounded_nonrequest_at_every_shape_cut(self):
        results=[]
        for position in range(10):
            gate,lease,base=started(cond=conditions(extra_trace=1))
            receipt=complete(gate,lease,base,extra_position=position)
            self.assertIsNotNone(receipt,position)
            self.assertEqual(70,gate.view()['last_accepted_trace'])
            self.assertEqual(71,gate.view()['reserved_trace'])
            results.append(dict(cut=position,shape_complete=True,credit_refunded=False))
        RESULTS['bounded_nonrequest_cuts']=dict(cases=10,results=results,actual_request_scheduling_verified=False)
