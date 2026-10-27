import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import a23_context65_history as history
import a23_context65_binding as binding
import a23_execution_context as context
import build_a23_context65_receiver as build

class Context65Tests(unittest.TestCase):
    def test_history_includes_failed49_and_permanent_burn(self):
        value,_=history.verify_scope();self.assertEqual(value['proposed'],65)
        self.assertIn(49,value['observed_values']);self.assertEqual(value['reserved_blocks']['49']['last'],64)
        self.assertFalse(value['reserved']);self.assertEqual(len(value['files']),378)
    def test_budget_and_device_unchanged(self):
        self.assertEqual(binding.SDK_PLAN['scenario']['first_sequence'],65)
        for key in binding.parent.SDK_PLAN:
            if key not in ('scenario','schema'):self.assertEqual(binding.SDK_PLAN[key],binding.parent.SDK_PLAN[key])
        self.assertEqual(binding.parent.FIRST,49)
    def test_context_rejects_unknown_sandbox_and_authority(self):
        base=context.model('ab'*32,'/private/tmp/receiver');context.validate(base,'ab'*32)
        for field,value in [('sandbox_query_result',1),('sandbox_query_result',-1),('sandbox_query_result',False),
            ('sandbox_query_errno',1),('sandbox_query_available',False),('usb_open_permission_proven',True),
            ('automatic_privilege_change',True),('os_build','bad'),('framework_uuid','bad'),('pid',True)]:
            with self.subTest(field=field,value=value):
                bad={**base,field:value}
                with self.assertRaises(ValueError):context.validate(bad,'ab'*32)
    def test_context_rejects_every_missing_field_and_extras(self):
        base=context.model('ab'*32,'/private/tmp/receiver')
        for key in base:
            bad=dict(base);del bad[key]
            with self.assertRaises(ValueError):context.validate(bad,'ab'*32)
        with self.assertRaises(ValueError):context.validate({**base,'extra':1},'ab'*32)
    def test_context_rejects_bad_code_hash_and_time(self):
        base=context.model('ab'*32,'/private/tmp/receiver')
        with self.assertRaises(ValueError):context.validate(base,'cd'*32)
        for value in ({**base,'sample_end_ticks':0},{**base,'receiver_path':'relative'},{**base,'receiver_sha256':'z'*64}):
            with self.assertRaises(ValueError):context.validate(value,value['receiver_sha256'])
    def test_context_never_authenticates_origin(self):
        result=context.validate(context.model('ab'*32,'/private/tmp/receiver'),'ab'*32)
        self.assertTrue(result['supplied_context_consistent']);self.assertFalse(result['process_origin_authenticated'])
        self.assertFalse(result['usb_open_permission_proven'])
    def test_old_record_rejected_before_build_or_device(self):
        old=build.load(build.ROOT/'private/analysis/A23-sequence-receiver-review-20261017-r5/offline-record.json')
        with self.assertRaises(ValueError):build.verify_build(old)
    def test_no_production_reservation65(self):
        self.assertFalse((build.ROOT/'private/sequence-reservations/block-00065.json').exists())

if __name__=='__main__':unittest.main()
