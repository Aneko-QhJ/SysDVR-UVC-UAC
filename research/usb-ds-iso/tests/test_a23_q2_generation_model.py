"""Adversarial sequential-event checks; not an SDK or concurrency test."""
import hashlib
import itertools
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from a23_q2_generation_model import Pool, Token, Evidence, AssumedHandoff

RESULTS = {}


def ready(pool, token=None, *, handoff=True):
    token = token or pool.admit()
    assert pool.submit(token)
    address = pool.view()['slots'][token.slot]['symbolic_address']
    for domain in ('iso', 'control'):
        assert pool.callback(token, domain, address)
        assert pool.handle(token, domain)
    evidence = pool.snapshot(token)
    assert evidence is not None and pool.commit(token, evidence)
    if handoff:
        assert pool.assume_handoff(token, AssumedHandoff(token))
    return token, evidence


def record(pool, token):
    return next(row for row in pool.view()['records'] if row['token']['request'] == token.request)


class GenerationModelTests(unittest.TestCase):
    def test_conditional_positive(self):
        pool = Pool('s', slots=1)
        old, _ = ready(pool)
        self.assertTrue(pool.recycle(old))
        new = pool.admit()
        self.assertEqual((old.slot, old.generation+1), (new.slot, new.generation))
        self.assertEqual(2, len(pool.view()['records']))
        self.assertFalse(pool.view()['native_handoff_proven'])

    def test_unknown_handoff_retains_and_stops(self):
        pool = Pool('s', slots=1)
        token, _ = ready(pool, handoff=False)
        self.assertFalse(pool.recycle(token))
        self.assertEqual(token.request, pool.view()['slots'][0]['token']['request'])
        self.assertTrue(pool.view()['stopped'])
        self.assertIsNone(pool.admit())

    def test_bool_or_dictionary_is_not_handoff(self):
        for injected in (True, {'native_handoff_proven': True}, None):
            pool = Pool('s')
            token, _ = ready(pool, handoff=False)
            self.assertFalse(pool.assume_handoff(token, injected))
            self.assertFalse(pool.recycle(token))

    def reused(self):
        pool = Pool('s', slots=1)
        old, evidence = ready(pool)
        self.assertTrue(pool.recycle(old))
        new = pool.admit()
        self.assertTrue(pool.submit(new))
        address = pool.view()['slots'][0]['symbolic_address']
        self.assertTrue(pool.callback(new, 'iso', address))
        return pool, old, new, evidence, address

    def test_old_iso_callback_cannot_touch_new_pending(self):
        pool, old, new, _, address = self.reused()
        before = record(pool, new)
        self.assertFalse(pool.callback(old, 'iso', address))
        self.assertEqual(before, record(pool, new))
        self.assertEqual(0, record(pool, new)['snapshot_reads'])
        self.assertTrue(pool.view()['stopped'])

    def test_old_control_callback_cannot_touch_new_pending(self):
        pool, old, new, _, address = self.reused()
        before = record(pool, new)
        self.assertFalse(pool.callback(old, 'control', address))
        self.assertEqual(before, record(pool, new))

    def test_old_queued_handler_cannot_touch_new_pending(self):
        pool, old, new, _, _ = self.reused()
        before = record(pool, new)
        self.assertFalse(pool.handle(old, 'iso'))
        self.assertEqual(before, record(pool, new))

    def test_old_handoff_cannot_authorize_new_request(self):
        pool, old, new, _, _ = self.reused()
        before = record(pool, new)
        self.assertFalse(pool.assume_handoff(old, AssumedHandoff(old)))
        self.assertEqual(before, record(pool, new))
        self.assertFalse(record(pool, new)['model_handoff_assumed'])

    def test_old_handoff_input_cannot_be_relabelled_with_new_argument(self):
        pool, old, new, _, _ = self.reused()
        self.assertFalse(pool.assume_handoff(new, AssumedHandoff(old)))
        self.assertFalse(record(pool, new)['model_handoff_assumed'])
        self.assertFalse(pool.recycle(new))
        self.assertEqual(new.request, pool.view()['slots'][0]['token']['request'])

    def test_same_pointer_is_not_request_identity(self):
        pool, old, new, _, address = self.reused()
        old_record = record(pool, old)
        self.assertEqual(old_record['address'], address)
        self.assertNotEqual(old.generation, new.generation)
        # A pointer-only reference policy would call this event current.
        pointer_only_accepts = old_record['address'] == address
        self.assertTrue(pointer_only_accepts)
        self.assertFalse(pool.callback(old, 'iso', address))
        RESULTS['pointer_only_counterexample'] = dict(old_token=old_record['token'],
            new_token=record(pool, new)['token'],same_symbolic_pointer=address,
            pointer_only_accepts=True,model_rejects_old_event=True,new_pending_preserved=True,
            native_DMA_safety_demonstrated=False)

    def test_duplicate_current_callback_stops_without_snapshot(self):
        pool = Pool('s');token = pool.admit();pool.submit(token)
        address = pool.view()['slots'][0]['symbolic_address']
        self.assertTrue(pool.callback(token, 'iso', address))
        self.assertFalse(pool.callback(token, 'iso', address))
        self.assertFalse(pool.recycle(token))
        self.assertEqual(0, record(pool, token)['snapshot_reads'])

    def test_pointer_mismatch_does_not_snapshot(self):
        pool = Pool('s');token = pool.admit();pool.submit(token)
        self.assertFalse(pool.callback(token, 'iso', 0xdead))
        self.assertIsNone(pool.snapshot(token))
        self.assertEqual(0, record(pool, token)['snapshot_reads'])

    def test_failed_callback_retains(self):
        pool = Pool('s');token = pool.admit();pool.submit(token)
        address = pool.view()['slots'][0]['symbolic_address']
        self.assertFalse(pool.callback(token, 'control', address, succeeded=False))
        self.assertFalse(pool.recycle(token))
        self.assertIsNotNone(pool.view()['slots'][0]['token'])

    def test_pending_handler_prevents_snapshot(self):
        pool = Pool('s');token = pool.admit();pool.submit(token)
        address = pool.view()['slots'][0]['symbolic_address']
        pool.callback(token, 'iso', address);pool.callback(token, 'control', address)
        pool.handle(token, 'iso')
        self.assertIsNone(pool.snapshot(token))
        self.assertFalse(pool.recycle(token))

    def test_save_failure_cannot_retry_to_pass(self):
        pool = Pool('s');token = pool.admit();pool.submit(token)
        address = pool.view()['slots'][0]['symbolic_address']
        for domain in ('iso', 'control'):
            pool.callback(token, domain, address);pool.handle(token, domain)
        evidence = pool.snapshot(token)
        self.assertFalse(pool.commit(token, evidence, succeeded=False))
        self.assertFalse(pool.commit(token, evidence, succeeded=True))
        self.assertFalse(record(pool, token)['evidence_committed'])
        self.assertFalse(pool.recycle(token))

    def test_old_receipt_cannot_commit_new_generation(self):
        pool, _, new, old_evidence, address = self.reused()
        pool.handle(new, 'iso');pool.callback(new, 'control', address);pool.handle(new, 'control')
        current = pool.snapshot(new)
        self.assertNotEqual(current, old_evidence)
        self.assertFalse(pool.commit(new, old_evidence))
        self.assertFalse(record(pool, new)['evidence_committed'])

    def test_evidence_version_mismatch_retains(self):
        pool = Pool('s');token = pool.admit();pool.submit(token)
        address = pool.view()['slots'][0]['symbolic_address']
        for domain in ('iso', 'control'):
            pool.callback(token, domain, address);pool.handle(token, domain)
        evidence = pool.snapshot(token)
        self.assertFalse(pool.commit(token, replace(evidence, version=evidence.version+1)))
        self.assertFalse(record(pool, token)['evidence_committed'])
        self.assertEqual('evidence_save_failed_or_binding_mismatch', pool.view()['stop_reason'])
        self.assertFalse(pool.recycle(token))

    def test_local_reader_prevents_recycle(self):
        pool = Pool('s');token, _ = ready(pool)
        self.assertTrue(pool.begin_local_read(token))
        self.assertFalse(pool.recycle(token))
        self.assertIsNotNone(pool.view()['slots'][token.slot]['token'])

    def test_local_reader_return_can_satisfy_conditional_gate(self):
        pool = Pool('s');token, _ = ready(pool)
        pool.begin_local_read(token);self.assertTrue(pool.end_local_read(token))
        self.assertTrue(pool.recycle(token))

    def test_pool_exhaustion_retains_active_records(self):
        pool = Pool('s', slots=2)
        one = pool.admit();two = pool.admit()
        before = pool.view()['slots']
        self.assertIsNone(pool.admit())
        self.assertEqual(before, pool.view()['slots'])
        self.assertEqual([one.request, two.request], [s['token']['request'] for s in before])
        self.assertEqual('pool_exhausted', pool.view()['stop_reason'])

    def test_retired_metadata_is_not_evicted(self):
        pool = Pool('s', slots=1, metadata_limit=2, evidence_credits=4)
        for _ in range(2):
            token, _ = ready(pool);self.assertTrue(pool.recycle(token))
        before = pool.view()['records']
        self.assertIsNone(pool.admit())
        self.assertEqual('metadata_exhausted', pool.view()['stop_reason'])
        self.assertEqual(before, pool.view()['records'])

    def test_evidence_credit_is_not_refunded_by_recycle(self):
        pool = Pool('s', slots=1, metadata_limit=4, evidence_credits=1)
        token, _ = ready(pool);self.assertTrue(pool.recycle(token))
        self.assertIsNone(pool.admit())
        self.assertEqual('evidence_credit_exhausted', pool.view()['stop_reason'])
        self.assertEqual(1, len(pool.view()['records']))

    def test_zero_credit_never_admits(self):
        pool = Pool('s', evidence_credits=0)
        self.assertIsNone(pool.admit())
        self.assertEqual([], pool.view()['records'])

    def test_interest_stops_without_freeing_active(self):
        pool = Pool('s');token, _ = ready(pool)
        before = pool.view()['slots'];pool.interest()
        self.assertFalse(pool.recycle(token))
        self.assertEqual(before, pool.view()['slots'])
        self.assertIsNone(pool.admit())

    def test_operator_stop_is_not_release(self):
        pool = Pool('s');token, _ = ready(pool);pool.stop()
        self.assertFalse(pool.recycle(token))
        self.assertIsNone(pool.admit())
        self.assertIsNotNone(pool.view()['slots'][token.slot]['token'])

    def test_callback_before_submission_stops(self):
        pool = Pool('s');token = pool.admit()
        self.assertFalse(pool.callback(token, 'iso', 0x1000))
        self.assertEqual(0, record(pool, token)['snapshot_reads'])

    def test_unknown_session_cannot_create_metadata(self):
        pool = Pool('s');token = pool.admit();before = pool.view()['records']
        wrong = replace(token, session='another')
        self.assertFalse(pool.callback(wrong, 'iso', 0x1000))
        self.assertEqual(before, pool.view()['records'])

    def test_strict_types_and_frozen_input(self):
        for kwargs in (dict(simulation=False),dict(simulation=1),dict(slots=True),dict(metadata_limit=33)):
            with self.assertRaises(ValueError):Pool('s', **kwargs)
        with self.assertRaises(ValueError):Token('s', False, 1, 1)
        token = Token('s', 0, 1, 1)
        with self.assertRaises(ValueError):Evidence(token, 0x1000, True)
        with self.assertRaises(FrozenInstanceError):token.generation = 2

    def test_view_does_not_grant_mutation(self):
        pool = Pool('s');token = pool.admit();view = pool.view()
        view['slots'][0]['token']['generation'] = 999
        view['records'][0]['model_handoff_assumed'] = True
        self.assertEqual(1, record(pool, token)['token']['generation'])
        self.assertFalse(record(pool, token)['model_handoff_assumed'])

    def test_handoff_cannot_be_replayed_or_relabelled(self):
        for schema in ('SDK_VERIFIED', 'Q2b-MODEL-ASSUMPTION-ONLY'):
            pool = Pool('s');token, _ = ready(pool, handoff=False)
            if schema == 'SDK_VERIFIED':
                self.assertFalse(pool.assume_handoff(token, AssumedHandoff(token, schema)))
            else:
                self.assertTrue(pool.assume_handoff(token, AssumedHandoff(token)))
                self.assertFalse(pool.assume_handoff(token, AssumedHandoff(token)))
            self.assertFalse(pool.recycle(token))

    def test_unsubmitted_slot_cannot_recycle(self):
        pool = Pool('s');token = pool.admit()
        self.assertFalse(pool.recycle(token))
        self.assertIsNotNone(pool.view()['slots'][0]['token'])

    def test_late_ingress_metadata_is_bounded(self):
        pool, old, new, _, address = self.reused()
        before = record(pool, new)
        for _ in range(1000):pool.callback(old, 'iso', address)
        self.assertEqual(255, record(pool, old)['late_events'])
        self.assertEqual(2, len(pool.view()['records']))
        self.assertEqual(before, record(pool, new))

    def test_no_state_claims_native_authority(self):
        pool = Pool('s');token, _ = ready(pool);pool.recycle(token)
        for flag in ('actual_backing_allocated','real_evidence_commit_verified','native_handoff_proven',
                     'all_callback_drain_proven','hardware_entry_enabled','formal_issuance_available',
                     'physical_buffer_reuse_enabled'):
            self.assertIs(pool.view()[flag], False)

    def permutations(self, *, handoff):
        events = ['iso','control','handle_iso','handle_control','snapshot','commit']
        if handoff:events.append('handoff')
        digest = hashlib.sha256();accepted = 0;cases = 0
        dependencies = [('iso','handle_iso'),('control','handle_control'),
                        ('handle_iso','snapshot'),('handle_control','snapshot'),('snapshot','commit')]
        for order in itertools.permutations(events):
            pool = Pool('s', slots=1);token = pool.admit();pool.submit(token)
            address = pool.view()['slots'][0]['symbolic_address'];evidence = None
            for event in order:
                if event in ('iso','control'):pool.callback(token, event, address)
                elif event.startswith('handle_'):pool.handle(token, event[7:])
                elif event=='snapshot':evidence=pool.snapshot(token)
                elif event=='commit':pool.commit(token, evidence)
                else:pool.assume_handoff(token, AssumedHandoff(token))
            # Independent order oracle uses only the event dependency DAG.
            position={name:i for i,name in enumerate(order)}
            expected=handoff and all(position[a]<position[z] for a,z in dependencies)
            result=pool.recycle(token)
            self.assertEqual(expected,result,order)
            if not result:self.assertIsNotNone(pool.view()['slots'][0]['token'],order)
            accepted+=int(result);cases+=1
            digest.update(json.dumps(dict(order=order,expected=expected,accepted=result,
                state=pool.view()),sort_keys=True,separators=(',',':')).encode()+b'\n')
        RESULTS['orders_assumed_handoff' if handoff else 'orders_unknown_handoff']=dict(
            schedules=cases,conditional_recycles=accepted,result_sha256=digest.hexdigest(),
            oracle='dependency_DAG_order_only',native_safety_proven=False)
        self.assertEqual((5040,42) if handoff else (720,0),(cases,accepted))

    def test_exhaustive_orders_under_explicit_assumption(self):
        self.permutations(handoff=True)

    def test_exhaustive_orders_without_handoff(self):
        self.permutations(handoff=False)
