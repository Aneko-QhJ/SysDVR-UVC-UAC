"""Execution timing and supplied-file comparison cannot grant hardware acceptance."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import audit_a23_execution_readiness as audit
import analyze_a23_v2_association as association
from workflows.artifacts import verify


class ExecutionReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.tmp.name)/'audit'
        cls.result = audit.run(cls.output)
        cls.associations = json.loads((cls.output/'associations.json').read_text())
        cls.recipe = json.loads((audit.CANDIDATE/'window-30s/recipe.json').read_text())['input_digest']
        cls.own = audit.CANDIDATE/'window-30s-candidate-prelude0-healthy.ownership.bin'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_expiry_after_wait_ready_suppresses_processing(self):
        rows = self.result['window_cases']
        self.assertEqual(rows['ready_at_expiry']['elapsed_ms'], 30000)
        self.assertEqual(rows['ready_returns_late']['elapsed_ms'], 45000)
        self.assertEqual(rows['ready_returns_late']['process_calls'], 0)

    def test_synchronous_process_has_no_hard_window_bound(self):
        rows = self.result['window_cases']
        self.assertEqual(rows['process_returns_late']['elapsed_ms'], 46000)
        self.assertEqual(rows['process_crosses_deadline']['elapsed_ms'], 30004)
        self.assertEqual(rows['very_late_process_return']['elapsed_ms'], 86401000)

    def test_sleep_crossing_deadline_allows_one_late_process_call(self):
        row = self.result['window_cases']['idle_sleep_crosses_deadline']
        self.assertEqual((row['elapsed_ms'],row['process_calls'],row['process_calls_started_after_expiry']),
                         (30042, 2, 1))

    def test_capture_return_can_delay_stop_until_next_process(self):
        row = self.result['window_cases']['capture_returns_late']
        self.assertEqual(row['elapsed_ms'], 46018)
        self.assertEqual(row['process_calls_started_after_expiry'], 1)

    def test_trace_start_is_distinct_from_window_start(self):
        row = self.result['window_cases']['separate_trace_start']
        self.assertEqual(row['window_start']-row['trace_start'], 321)
        self.assertGreaterEqual(row['elapsed_ms'], 30000)

    def test_single_discovery_and_normal_session_save_gap(self):
        result = self.result['source_contract']
        self.assertFalse(result['current_host_has_hotplug_wait'])
        self.assertFalse(result['current_host_can_be_prearmed_without_device'])
        self.assertFalse(result['normal_exit_writes_session_file'])
        self.assertTrue(result['diagnostic_exit_session_save_requires_diagnostic_save'])
        self.assertFalse(result['wrapper_wait_is_force_kill_deadline'])

    def test_source_drift_fails_closed(self):
        main = (audit.CANDIDATE/'window-30s/source/sysmodule/main.c').read_text()
        host = (ROOT/'host/io_usb_host_burst_main.m').read_text()
        wrapper = (ROOT/'tools/workflows/capture_io_usb_host_burst.py').read_text()
        session_file = (audit.CANDIDATE/'window-30s/source/uvc/ep0_session_file.c').read_text()
        for altered in (host.replace('IOServiceGetMatchingServices(', 'other('),
                        host+'\nIOServiceAddMatchingNotification'):
            with self.assertRaises(ValueError):audit.source_contract(main,altered,wrapper,session_file)
        with self.assertRaises(ValueError):
            audit.source_contract(main+'\nEp0SessionSaveJoined(0,0);',host,wrapper,session_file)

    def test_matching_request_bytes_do_not_match_historical_state(self):
        row = self.associations['healthy']
        self.assertTrue(row['host_audit_valid'])
        self.assertTrue(row['device_files_valid'])
        self.assertTrue(row['comparison']['exact_target_setup_order_matches'])
        self.assertFalse(row['comparison']['status_state_sequence_matches'])
        self.assertFalse(row['supplied_comparison_consistent'])
        self.assertFalse(row['host_observation_complete'])

    def test_even_matching_state_cannot_bind_physical_run_or_clocks(self):
        row = self.associations['healthy']
        trace = row['device_decoded']['ownership']['trace']
        status = copy.deepcopy(row['host_status'])
        status['after'].update(state=2, sequence=1)
        result = association.compare(row['host_requests'], status, trace)
        self.assertTrue(result['status_state_sequence_matches'])
        self.assertFalse(result['full_status_payload_binding_verified'])
        shifted = copy.deepcopy(trace)
        shifted['start_tick'] += 10**15
        shifted['freeze_tick'] += 10**15
        for q in shifted['requests']:
            for r in q['records']:
                r['begin_ticks'] += 10**15;r['end_ticks'] += 10**15
        self.assertEqual(result, association.compare(row['host_requests'],status,shifted))
        self.assertFalse(result['cross_clock_alignment_verified'])

    def test_missing_or_duplicate_target_is_inconclusive(self):
        row = self.associations['healthy']
        for change in ('missing','duplicate'):
            trace = copy.deepcopy(row['device_decoded']['ownership']['trace'])
            index = next(i for i,q in enumerate(trace['requests']) if q['interface']==2)
            if change=='missing':trace['requests'].pop(index)
            else:trace['requests'].append(trace['requests'][index])
            result=association.compare(row['host_requests'],row['host_status'],trace)
            self.assertFalse(result['exact_target_setup_order_matches'])
            self.assertFalse(result['missing_interface2_records_prove_event_absence'])

    def test_corrupt_or_wrong_recipe_preserves_error_and_hash(self):
        file = Path(self.tmp.name)/'corrupt.bin'
        data=bytearray(self.own.read_bytes());data[-1]^=1;file.write_bytes(data)
        for path, recipe in ((file,self.recipe),(self.own,'00'*32)):
            row=association.analyze(audit.HISTORICAL/'host',{'ownership':path},recipe)
            self.assertFalse(row['device_files_valid'])
            self.assertEqual(row['files']['ownership']['sha256'],association.sha(path.read_bytes()))
            self.assertEqual(row['errors'][0]['component'],'ownership')

    def test_mixed_exit_paths_and_distinct_device_trace_rejected(self):
        artifacts={'ownership':self.own,'diagnostic':audit.CANDIDATE/
                   'window-30s-candidate-prelude0-iso-pending.diagnostic.bin'}
        row=association.analyze(audit.HISTORICAL/'host',artifacts,self.recipe)
        self.assertIn('device_trace_disagreement',row['device_conflicts'])
        self.assertIn('normal_and_diagnostic_exit_paths_mixed',row['device_conflicts'])
        self.assertFalse(row['device_files_valid'])

    def test_missing_host_preserves_device_and_stays_inconclusive(self):
        row=association.analyze(Path(self.tmp.name)/'absent',{'ownership':self.own},self.recipe)
        self.assertTrue(row['device_files_valid'])
        self.assertFalse(row['host_audit_valid'])
        self.assertFalse(row['supplied_comparison_consistent'])
        self.assertEqual(row['errors'][0]['component'],'host')

    def test_session_and_embedded_diagnostic_match_without_authenticating_commit(self):
        artifacts={'session':audit.CANDIDATE/'maximum.session.bin',
                   'diagnostic':audit.CANDIDATE/'maximum.diagnostic.bin'}
        recipe='03'+'00'*31
        row=association.analyze(audit.HISTORICAL/'host',artifacts,recipe)
        self.assertTrue(row['device_files_valid'])
        self.assertFalse(row['device_conflicts'])
        self.assertEqual(len(row['device_trace_sha256']),1)
        self.assertTrue(row['device_decoded']['session']['sink']['commit_acknowledged'])
        self.assertFalse(row['session_envelope_own_commit_authenticated'])
        self.assertFalse(row['same_physical_run_verified'])
        self.assertFalse(row['cleanup_authorized'])

    def test_passive_wait_design_is_one_selection_and_not_implemented(self):
        start=[{'kind':'notification_registered'},{'kind':'initial_iterator_drained','existing_ids':[]}]
        selected=audit.arm_policy(start+[{'kind':'arrival','fresh_ids':[42]},
                                         {'kind':'arrival','fresh_ids':[43]}])
        self.assertEqual((selected['state'],selected['selected_registry_id']),('selected',42))
        self.assertFalse(selected['receiver_implemented'])
        self.assertEqual(selected['usb_requests'],0)
        for events in ([{'kind':'arrival','fresh_ids':[42]}],
                       start+[{'kind':'arrival','fresh_ids':[42,43]}],
                       start+[{'kind':'timeout'},{'kind':'arrival','fresh_ids':[42]}],
                       start+[{'kind':'arrival','fresh_ids':[42]},{'kind':'detach'},
                              {'kind':'arrival','fresh_ids':[43]}],
                       [{'kind':'notification_registered'},
                        {'kind':'initial_iterator_drained','existing_ids':[42]}]):
            row=audit.arm_policy(events)
            self.assertEqual(row['state'],'stopped')
            self.assertFalse(row['attempt_issued'])

    def test_sealed_inputs_and_authorization_remain_unchanged(self):
        self.assertTrue(verify(self.output)['sha256_verified'])
        for name, old in self.result['tickets_sha256'].items():
            self.assertEqual(audit.ready.sha(audit.CANDIDATE.parent/name),old)
        for row in self.associations.values():
            for flag in ('usb_strict_pass','same_physical_run_verified','hardware_verified',
                         'root_cause_confirmed','cleanup_authorized','allow_next_burst'):
                self.assertFalse(row[flag])
        with self.assertRaises(ValueError):audit.run(self.output)


if __name__=='__main__':unittest.main()
