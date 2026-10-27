import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
from analyze_io_usb_host_session import analyze


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"journal.jsonl"
        self.records = []
        self.event("prepare_begin", {"candidate_count":1})
        self.event("candidate_selected", {"device_id":101,"interface_id":102,"parent_device_id":101})
        self.event("resources_opened")
        self.event("ready", {"interface":2,"alternate":0,"endpoint":131,"mps":256,"interval":1,"connection_speed":3,
            "vendor_id":0x1209,"product_id":0xca57,"configuration_value":1,"source":"supplied_descriptor_bytes"})
        self.event("submit_begin", {"first_frame":100})
        self.event("submit_result", {"accepted":True})
        self.event("callback", {"count":1,"status_u32":0,"arrival_ticks":5,"pointer_mismatch":False,"owner_state_before":1})
        self.event("snapshot_ready", {"owner_state":4,"overall_u32":0})
        self.event("save_begin", {"callback_count":1})
        self.event("bundle_committed", {"callback_count":1,"manifest_sha256":"a"*64})
        self.event("resources_closing")
        self.event("resources_closed")

    def event(self, name, details=None):
        self.records.append({"schema":"A23-session-event-1","execution_mode":"simulation",
            "session_id":"test", "index":len(self.records)+1,"ticks":len(self.records)+10,
            "event":name,"details":details or {}})

    def save(self):
        self.path.write_text("".join(json.dumps(r)+"\n" for r in self.records))

    def result(self):
        self.save()
        return analyze(self.path)

    def test_prefix_without_bundle_is_not_pass(self):
        result = self.result()
        self.assertTrue(result["journal_prefix_verified"])
        self.assertFalse(result["simulation_session_pass"])
        self.assertFalse(result["callback_drain_verified"])
        self.assertFalse(result["usb_strict_pass"])

    def test_late_event_invalidates_even_without_stop_marker(self):
        self.event("callback", {"count":2,"status_u32":0,"arrival_ticks":20,
            "pointer_mismatch":False,"owner_state_before":4})
        result = self.result()
        self.assertTrue(result["late_callback_observed"])
        self.assertFalse(result["simulation_session_pass"])

    def test_pending_close_rejected(self):
        self.records = self.records[:6]
        self.event("resources_closing")
        with self.assertRaisesRegex(ValueError,"pending/retained"):
            self.result()

    def test_resubmit_rejected(self):
        self.records = self.records[:6]
        self.event("submit_begin", {"first_frame":101})
        with self.assertRaisesRegex(ValueError,"repeated submission"):
            self.result()

    def test_identity_mismatch_rejected(self):
        self.records[1]["details"]["parent_device_id"] = 103
        with self.assertRaisesRegex(ValueError,"registry relationship"):
            self.result()

    def test_indices_time_sessions_and_types_rejected(self):
        for field, value in (("index",False),("ticks",0),("session_id","other"),("execution_mode","hardware")):
            with self.subTest(field=field):
                old = self.records[2][field]; self.records[2][field] = value
                with self.assertRaises(ValueError):
                    self.result()
                self.records[2][field] = old

    def test_boolean_pointer_not_integer(self):
        self.records[6]["details"]["pointer_mismatch"] = 0
        with self.assertRaisesRegex(ValueError,"callback event"):
            self.result()

    def test_snapshot_status_not_boolean_and_ready_identity(self):
        self.records[7]["details"]["overall_u32"] = False
        with self.assertRaisesRegex(ValueError,"snapshot does not match"):
            self.result()
        self.records[7]["details"]["overall_u32"] = 0
        self.records[3]["details"]["vendor_id"] = 0
        with self.assertRaisesRegex(ValueError,"ready identity"):
            self.result()

    def test_partial_tail_and_duplicate_fields_rejected(self):
        self.save()
        self.path.write_bytes(self.path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError,"partial"):
            analyze(self.path)
        self.save()
        self.path.write_bytes(self.path.read_bytes().replace(b'"event": "prepare_begin"', b'"event": "prepare_begin", "event":"prepare_begin"',1))
        with self.assertRaisesRegex(ValueError,"duplicate JSON"):
            analyze(self.path)

    def test_abort_after_detach_rejected(self):
        self.records = self.records[:6]
        self.event("detach", {"registry_id":101})
        self.event("deadline")
        with self.assertRaisesRegex(ValueError,"deadline"):
            self.result()

    def test_detach_association_cannot_be_faked(self):
        self.event("unrelated_detach", {"registry_id":101})
        with self.assertRaisesRegex(ValueError,"detach association"):
            self.result()

    def test_exported_lifecycle_cases(self):
        fixture = os.environ.get("A23_SESSION_FIXTURES")
        if not fixture:
            self.skipTest("set A23_SESSION_FIXTURES for Objective-C integration")
        root = Path(fixture)
        names = [p.stem for p in sorted(root.glob("*.jsonl"))]
        self.assertEqual(len(names),16)
        for name in names:
            with self.subTest(case=name):
                if name == "journal-failed":
                    with self.assertRaisesRegex(ValueError,"partial journal tail"):
                        analyze(root/(name+".jsonl"))
                    continue
                bundle = root/name if (root/name/"COMMITTED").exists() else None
                result = analyze(root/(name+".jsonl"),bundle)
                self.assertEqual(result["simulation_session_pass"],name == "clean")
                self.assertFalse(result["usb_strict_pass"])
                if name == "late-after-close":
                    self.assertTrue(result["late_callback_observed"])
                    meta = json.loads((bundle/"metadata.json").read_text())
                    self.assertEqual(meta["callback_count_at_save"],1)
                    self.assertEqual(result["callbacks"],2)
                if name == "detach-missing-callback":
                    self.assertEqual(result["callbacks"],0)
                    self.assertFalse(result["resources_closed"])
                if name.startswith("detach-"):
                    self.assertEqual(result["abort_requests"],0)
        # Correct bundle bytes must still match their own journal.
        with self.assertRaisesRegex(ValueError,"hash mismatch"):
            analyze(root/"clean.jsonl",root/"late-after-close")


if __name__ == "__main__":
    unittest.main()
