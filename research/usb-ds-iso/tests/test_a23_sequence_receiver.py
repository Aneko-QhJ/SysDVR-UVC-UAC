import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import a23_sequence_history as h
import a23_sequence_binding as d
import build_a23_sequence_receiver as b


class SequenceReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/private/tmp',prefix='a23-sequence-ledger-')
        self.root=Path(self.temp.name).resolve()
    def tearDown(self):self.temp.cleanup()
    def reserve(self,head=None,scope='ab'*32):return h.reserve_model(self.root,scope,[*range(32)],head)
    def test_history_includes_earlier_sequences(self):
        scope,digest=h.verify_scope();self.assertEqual(scope['proposed'],49);self.assertEqual(scope['observed_values'],list(range(32)))
        self.assertEqual(len(digest),64);self.assertFalse(scope['reserved'])
    def test_reserved_block_is_burned_and_not_issued(self):
        first=self.reserve();second=self.reserve(first['head'])
        self.assertEqual((first['first'],second['first']),(49,65));self.assertEqual(first['remaining'],0)
        self.assertFalse(first['acquisition_enabled'])
    def test_stale_expected_head_rejected(self):
        self.reserve()
        with self.assertRaises(ValueError):self.reserve()
        self.assertEqual(len(list(self.root.glob('burn-*'))),1)
    def test_scope_mismatch_rejected(self):
        first=self.reserve()
        with self.assertRaises(ValueError):self.reserve(first['head'],'cd'*32)
    def test_head_failure_leaves_burn_and_blocks_reuse(self):
        with patch.object(h.os,'replace',side_effect=OSError('injected head failure')):
            with self.assertRaises(OSError):self.reserve()
        self.assertEqual(len(list(self.root.glob('burn-*'))),1)
        with self.assertRaises(ValueError):self.reserve()
    def test_truncated_burn_blocks_reuse(self):
        first=self.reserve();next(self.root.glob('burn-*')).write_bytes(b'{')
        with self.assertRaises(ValueError):self.reserve(first['head'])
    def test_anchor_rejects_deleted_tail(self):
        first=self.reserve();(self.root/'burn-0000.json').unlink();(self.root/'HEAD').unlink()
        with self.assertRaises(ValueError):self.reserve(first['head'])
    def test_lock_contention_rejected(self):
        import fcntl
        with (self.root/'.lock').open('w') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.reserve()
    def test_symlink_or_non_temporary_ledger_rejected(self):
        (self.root/'alias').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):h.reserve_model(self.root/'alias','ab'*32,[1],None)
        with self.assertRaises(ValueError):h.reserve_model(b.ROOT,'ab'*32,[1],None)
    def test_new_plan_binds_sequence_and_unchanged_budget(self):
        self.assertEqual(d.WAIT_PLAN['sdk_plan']['scenario']['first_sequence'],49)
        self.assertEqual(d.WAIT_PLAN['sdk_plan']['first_frame_lead'],32)
        self.assertEqual(d.WAIT_PLAN['sdk_plan']['runtime_budget'],d.parent.WAIT_PLAN['sdk_plan']['runtime_budget'])
        self.assertEqual(d.parent.WAIT_PLAN['sdk_plan']['scenario']['first_sequence'],1)


if __name__=='__main__':unittest.main()
