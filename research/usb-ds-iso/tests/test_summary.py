import importlib.util
from pathlib import Path
import unittest
import struct

spec = importlib.util.spec_from_file_location('run_summary', Path(__file__).resolve().parents[1]/'tools/summarize_run.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SummaryTests(unittest.TestCase):
    def test_initial_previous_td_status_is_not_a_new_attempt(self):
        rows = [{'kind':'device_status','sequence':100,'diagnostics_hex':'d1000000'+'00'*108},
                {'kind':'iso_transfer','sequence':1,'status':0,'packets':[]},
                {'kind':'result','sequence':1,'iso_payload_verified':False,'completion_verified':True}]
        summary = module.summarize(rows)
        self.assertEqual(summary['attempts'],1)
        self.assertEqual(summary['runs'][0]['sequence'],1)
        self.assertEqual(summary['terminal_report_passes'],1)

    def test_failed_current_attempt_is_kept(self):
        summary = module.summarize([{'kind':'result','sequence':1,
                                    'iso_payload_verified':False,'completion_verified':False}])
        self.assertEqual(summary['attempts'],1)
        self.assertEqual(summary['payload_passes'],0)


class IntervalSummaryTests(unittest.TestCase):
    def make(self, interval=1, valid=1):
        b=ContextAuditSummaryTests().make(valid=valid)
        struct.pack_into('<I',b,0,0x374f5349)
        struct.pack_into('<I',b,80,(interval<<16)|1)
        return b

    def test_iso7_expects_interval1_without_reinterpreting_iso6(self):
        d=module.decode_diag(self.make().hex())
        self.assertEqual(d['diagnostics_layout'],'ISO7')
        self.assertTrue(d['context_snapshot']['configured_fields_match'])
        self.assertEqual(d['nominal_host_slots_per_frame'],8)
        self.assertEqual(d['service_interval_microframes'],1)
        d=module.decode_diag(self.make(interval=4).hex())
        self.assertTrue(d['context_snapshot']['valid']);self.assertFalse(d['context_snapshot']['configured_fields_match'])
        old=ContextAuditSummaryTests().make();self.assertTrue(module.decode_diag(old.hex())['context_snapshot']['configured_fields_match'])

    def test_iso7_invalid_snapshot_and_error_priority_keep_raw_evidence_rules(self):
        b=self.make(valid=0);b[80:]=b'\xff'*32
        d=module.decode_diag(b.hex());self.assertFalse(d['context_snapshot_available'])
        self.assertNotIn('context_dwords',d['context_snapshot'])
        b=self.make();struct.pack_into('<II',b,4,448,struct.unpack_from('<I',b,8)[0]);struct.pack_into('<I',b,12,0x80000017)
        EventAuditSummaryTests().event(b,52,0x9000040,12,ed=False,cc=23,count=0)
        d=module.decode_diag(b.hex());self.assertTrue(d['error_record_matches_terminal'])
        self.assertEqual(d['error_td_index'],14);self.assertFalse(d['wire_trace_verified'])


class BurstSummaryTests(unittest.TestCase):
    def test_iso2_bitmap_does_not_masquerade_as_context_or_events(self):
        b=bytearray(112)
        struct.pack_into('<IIIIIIQ',b,0,0x324f5349,0,0,0,0xff,1536,0x2000000)
        diag=module.decode_diag(b.hex())
        self.assertEqual(diag['completed_packets'],8)
        self.assertEqual(diag['actual_sum'],1536)
        self.assertFalse(diag['terminal_success'])
        self.assertFalse(diag['raw_event_capture_available'])
        self.assertNotIn('context_dwords',diag)

    def test_burst_payload_evidence_includes_packet_sequence_rollover(self):
        packets=[]
        for i in range(16):
            seq=(65530+i)&65535
            raw=b'ISO1'+seq.to_bytes(2,'little')+bytes((j ^ seq ^ (seq>>8))&255 for j in range(6,192))
            packets.append({'index':i+1,'status':0,'length':192,'data_hex':raw.hex()})
        rows=[{'kind':'experiment','burst_packets':16},
              {'kind':'iso_transfer','sequence':65530,'status':0,'packets':packets}]
        summary=module.summarize(rows)
        self.assertEqual(summary['exact_payload_observations'],16)
        self.assertEqual(summary['payload_passes'],0) # observations alone never claim acceptance


class ErrorSnapshotSummaryTests(unittest.TestCase):
    def test_iso2_error_keeps_code_td_offset_and_raw_mfi(self):
        b=bytearray(112)
        struct.pack_into('<IIIIIIQ',b,0,0x324f5349,448,0x3ffd,0x80000017,0x3fff,2688,0x2000600)
        struct.pack_into('<I',b,60,(311<<20)|0x1411)
        struct.pack_into('<QII',b,64,0x90007c0,23<<24,(7<<16)|(32<<10)|1)
        diag=module.decode_diag(b.hex())
        self.assertTrue(diag['first_trb_control_only'])
        self.assertEqual(diag['frame_id'],311)
        self.assertTrue(diag['raw_event_capture_available'])
        self.assertEqual(diag['error_td_index'],14)
        self.assertEqual(diag['error_mfi'],0x3ffd)
        self.assertEqual(diag['latched_completion_code'],23)
        self.assertFalse(diag['terminal_success'])


class EventAuditSummaryTests(unittest.TestCase):
    def make(self, terminal=1):
        b = bytearray(112)
        struct.pack_into('<IIIIIIQ', b, 0, 0x334f5349, 80, (375 << 20) | 0x1411,
                         terminal, 0xffff, 3072, 0x2000f60)
        return b

    def event(self, b, offset, ptr, mfi, ed=True, cc=1, count=192):
        struct.pack_into('<QIII', b, offset, ptr, (cc << 24) | count,
                         (7 << 16) | (32 << 10) | int(ed) * 4 | 1, mfi)

    def test_success_mfi_wrap_and_filtered_does_not_claim_fault(self):
        b = self.make()
        self.event(b, 32, 0x2000000, 0x3ffc)
        self.event(b, 52, 0x2000020, 4)
        self.event(b, 72, 0, 0x3ffa, ed=False, cc=14, count=0)
        self.event(b, 92, 0, 14, ed=False, cc=14, count=0)
        diag = module.decode_diag(b.hex())
        self.assertEqual(diag['frame_id'], 375)
        self.assertEqual(diag['completed_packets'], 16)
        self.assertEqual(diag['first_two_ed_mfi_delta'], 8)
        self.assertFalse(diag['error_event_snapshot_available'])
        self.assertEqual([r['role'] for r in diag['audit_records']],
                         ['td0_success','td1_success','first_filtered','first_post_terminal'])
        self.assertFalse(diag['wire_trace_verified'])
        self.assertFalse(diag['total_event_count_available'])
        self.assertFalse(diag['filtered_reason_recorded'])

    def test_error_replacement_has_full_raw_and_no_success_delta(self):
        b = self.make(0x80000017)
        self.event(b, 52, 0x9000040, 97, ed=False, cc=23, count=0)
        diag = module.decode_diag(b.hex())
        self.assertTrue(diag['retained_after_error'])
        self.assertEqual(diag['error_mfi'], 97)
        self.assertEqual(diag['error_td_index'], 2)
        self.assertTrue(diag['td1_snapshot_replaced_by_error'])
        self.assertIsNone(diag['first_two_ed_mfi_delta'])
        self.assertEqual(diag['audit_records'][1]['role'], 'first_matched_error')

    def test_invalid_stale_raw_and_mfi_are_excluded(self):
        b = self.make()
        b[32:] = b'\xff' * 80
        for off in (32,52,72,92): struct.pack_into('<I',b,off+12,0)
        diag = module.decode_diag(b.hex())
        self.assertFalse(diag['raw_event_capture_available'])
        self.assertTrue(all(list(r) == ['role','valid'] and not r['valid'] for r in diag['audit_records']))
        self.assertIsNone(diag['first_two_ed_mfi_delta'])

    def test_terminal_before_error_replacement_is_not_error_evidence(self):
        b = self.make(0x80000017)
        self.event(b, 52, 0x2000020, 4)
        diag = module.decode_diag(b.hex())
        self.assertFalse(diag['error_event_snapshot_available'])
        self.assertFalse(diag['error_record_matches_terminal'])
        self.assertEqual(diag['audit_records'][1]['role'], 'td1_or_error_transition')
        self.assertFalse(diag['td1_snapshot_replaced_by_error'])
        self.assertIsNone(diag['error_mfi'])
        self.assertFalse(diag['multi_field_snapshot_atomic'])


class DoorbellAuditSummaryTests(unittest.TestCase):
    def make(self, selected=0x3ffc, before=0x3ffe, after=1, marker=0x700):
        b=PublicationAuditSummaryTests().make(selected,before,after,marker)
        struct.pack_into('<I',b,0,0x354f5349)
        return b

    def test_wrap_and_tail_bracket_do_not_reuse_publication_field_names(self):
        diag=module.decode_diag(self.make().hex())
        self.assertEqual(diag['diagnostics_layout'],'ISO5')
        anchors=diag['doorbell_anchors']
        self.assertTrue(anchors['valid'] and anchors['original_tail_store_executed'])
        self.assertEqual(anchors['select_to_before_tail_mfi_delta'],2)
        self.assertEqual(anchors['original_tail_bracket_mfi_delta'],3)
        self.assertEqual(anchors['select_to_after_tail_mfi_delta'],5)
        self.assertNotIn('publication_anchors',diag)
        self.assertFalse(anchors['controller_doorbell_acceptance_verified'])
        self.assertFalse(anchors['doorbell_write_timestamped'])
        self.assertFalse(diag['reserved_bytes_interpreted'])

    def test_incomplete_or_rejected_tail_does_not_expose_stale_anchors(self):
        for marker in (0,1,7,0x600,0xffffffff):
            anchors=module.decode_diag(self.make(before=0xffffffff,after=0xffffffff,marker=marker).hex())['doorbell_anchors']
            self.assertFalse(anchors['valid'] or anchors['capture_complete'] or anchors['original_tail_store_executed'])
            self.assertNotIn('before_tail_mfi',anchors)

    def test_inconsistent_header_does_not_claim_a_valid_original_store(self):
        bad=self.make();struct.pack_into('<I',bad,8,(32<<20)|0x1411)
        for data in (bad,self.make(selected=0xffffffff),self.make(before=0xffffffff),self.make(after=0xffffffff)):
            anchors=module.decode_diag(data.hex())['doorbell_anchors']
            self.assertTrue(anchors['capture_complete'])
            self.assertFalse(anchors['valid'] or anchors['original_tail_store_executed'])

    def test_error_replacement_and_nonatomic_transition_still_have_priority(self):
        for replaced in (False,True):
            b=self.make();struct.pack_into('<II',b,4,448,struct.unpack_from('<I',b,8)[0])
            struct.pack_into('<I',b,12,0x80000017)
            EventAuditSummaryTests().event(b,52,0x9000040 if replaced else 0x2000020,12,ed=not replaced,cc=23 if replaced else 1,count=0 if replaced else 192)
            diag=module.decode_diag(b.hex())
            self.assertEqual(diag['error_event_snapshot_available'],replaced)
            self.assertIsNone(diag['first_two_ed_mfi_delta'])
            self.assertTrue(diag['doorbell_anchors']['valid'])
            self.assertFalse(diag['multi_field_snapshot_atomic'])


class PublicationAuditSummaryTests(unittest.TestCase):
    def make(self, selected=0x3ffc, before=0x3ffe, after=1, valid=1):
        b=bytearray(b'\xff'*112)
        control=((((selected>>3)+32)&2047)<<20)|0x1411
        struct.pack_into('<IIIIIIQ',b,0,0x344f5349,0,control,1,0xffff,3072,0x2000000)
        struct.pack_into('<I',b,44,0);struct.pack_into('<I',b,64,0)
        struct.pack_into('<IIII',b,72,selected,before,after,valid)
        return b

    def test_three_anchors_wrap_without_decoding_reserved_bytes(self):
        diag=module.decode_diag(self.make().hex())
        self.assertEqual(diag['diagnostics_layout'],'ISO4')
        self.assertEqual(len(diag['audit_records']),2)
        anchors=diag['publication_anchors']
        self.assertTrue(anchors['valid'])
        self.assertEqual(anchors['select_to_before_publish_mfi_delta'],2)
        self.assertEqual(anchors['publish_bracket_mfi_delta'],3)
        self.assertEqual(anchors['select_to_before_doorbell_mfi_delta'],5)
        self.assertEqual(anchors['target_minus_before_doorbell_mfi_mod16384'],247)
        self.assertFalse(anchors['doorbell_write_timestamped'])
        self.assertFalse(diag['filtered_event_sampling_available'])
        self.assertFalse(diag['post_terminal_event_sampling_available'])
        self.assertFalse(diag['reserved_bytes_interpreted'])
        self.assertNotIn('first_post_terminal',str(diag))

    def test_incomplete_or_unknown_phase_flags_never_expose_stale_mfi(self):
        for flag in (0,2,0xffffffff):
            diag=module.decode_diag(self.make(0x3ffc,0xffffffff,0xffffffff,flag).hex())
            anchors=diag['publication_anchors']
            self.assertFalse(anchors['valid'])
            self.assertNotIn('frame_select_mfi',anchors)
            self.assertNotIn('before_publish_mfi',anchors)
            self.assertNotIn('before_doorbell_mfi',anchors)

    def test_wrong_header_or_out_of_range_samples_do_not_claim_consistency(self):
        b=self.make();struct.pack_into('<I',b,8,(32<<20)|0x1411)
        for data in (b,self.make(0xffffffff),self.make(before=0xffffffff),self.make(after=0xffffffff)):
            anchors=module.decode_diag(data.hex())['publication_anchors']
            self.assertTrue(anchors['capture_complete'])
            self.assertFalse(anchors['valid'])
            self.assertNotIn('select_to_before_doorbell_mfi_delta',anchors)

    def test_matched_error_priority_and_nonatomic_transition_still_apply(self):
        for replaced in (False,True):
            b=self.make();struct.pack_into('<I',b,12,0x80000017)
            struct.pack_into('<I',b,4,448)
            EventAuditSummaryTests().event(b,52,0x90001c0,41,ed=not replaced,
                                          cc=23 if replaced else 1,count=0 if replaced else 192)
            diag=module.decode_diag(b.hex())
            self.assertEqual(diag['error_event_snapshot_available'],replaced)
            self.assertEqual(diag['td1_snapshot_replaced_by_error'],replaced)
            self.assertIsNone(diag['first_two_ed_mfi_delta'])
            self.assertEqual(diag['error_td_index'],14 if replaced else None)
            self.assertTrue(diag['publication_anchors']['valid'])
            self.assertFalse(diag['multi_field_snapshot_atomic'])


class ContextAuditSummaryTests(unittest.TestCase):
    def make(self, selected=0x3ffc, valid=1):
        b=bytearray(b'\xff'*112)
        struct.pack_into('<IIIIIIQ',b,0,0x364f5349,0,((((selected>>3)+32)&2047)<<20)|0x1411,1,0xffff,3072,0x2000000)
        struct.pack_into('<I',b,44,0);struct.pack_into('<I',b,64,0)
        struct.pack_into('<II8I',b,72,selected,valid,0x40001,0x100002e,0x9000001,0x1234,0x1000c00,0x02000567,0xc0000,0x0400042)
        return b

    def test_context_fields_and_64bit_dequeue_decode_without_pid_or_atomicity_claims(self):
        diag=module.decode_diag(self.make().hex());c=diag['context_snapshot']
        self.assertEqual(diag['diagnostics_layout'],'ISO6');self.assertTrue(c['valid'])
        self.assertTrue(c['configured_fields_match']);self.assertEqual(len(c['context_dwords']),8)
        self.assertEqual((c['state'],c['interval'],c['endpoint_type'],c['max_packet_size'],c['max_esit_payload']),(1,4,5,256,256))
        self.assertEqual(c['dequeue_pointer'],'0000123409000000');self.assertEqual(c['dcs'],1)
        self.assertEqual(c['sequence_byte'],2);self.assertTrue(c['partial_td']);self.assertEqual(c['edtla'],0x567)
        self.assertEqual(c['cerr_count'],3);self.assertEqual(c['data_offset'],0x42);self.assertEqual(c['num_trbs'],1)
        self.assertFalse(c['snapshot_atomic'] or c['hardware_context_modified'] or c['data_pid_verified'])
        self.assertNotIn('doorbell_anchors',diag);self.assertNotIn('publication_anchors',diag)
        self.assertEqual(len(diag['audit_records']),2)

    def test_stale_context_is_excluded_for_invalid_sentinel_or_frame_relation(self):
        for flag in (0,2,7,0xffffffff):
            b=self.make(valid=flag);b[80:]=b'\xff'*32
            d=module.decode_diag(b.hex());self.assertFalse(d['context_snapshot_available'])
            self.assertNotIn('context_dwords',d['context_snapshot'])
        b=self.make();struct.pack_into('<I',b,8,0x1411)
        for data in (b,self.make(selected=0x4000)):
            d=module.decode_diag(data.hex());self.assertFalse(d['context_snapshot']['valid'])
            self.assertNotIn('context_dwords',d['context_snapshot'])

    def test_mismatching_configuration_is_preserved_as_evidence(self):
        b=self.make();struct.pack_into('<I',b,84,0xc0002e)
        c=module.decode_diag(b.hex())['context_snapshot']
        self.assertTrue(c['valid']);self.assertFalse(c['configured_fields_match'])
        self.assertEqual(c['max_packet_size'],192);self.assertEqual(c['context_dwords'][1],'00C0002E')

    def test_error_priority_and_nonatomic_transition_remain_intact(self):
        for replaced in (False,True):
            b=self.make();struct.pack_into('<I',b,12,0x80000017)
            EventAuditSummaryTests().event(b,52,0x9000040 if replaced else 0x2000020,12,ed=not replaced,cc=23 if replaced else 1,count=0 if replaced else 192)
            d=module.decode_diag(b.hex());self.assertEqual(d['error_event_snapshot_available'],replaced)
            self.assertTrue(d['context_snapshot']['valid']);self.assertIsNone(d['first_two_ed_mfi_delta'])
            self.assertFalse(d['multi_field_snapshot_atomic'])
