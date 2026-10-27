import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from analyze_io_usb_host_collection import analyze, freeze, LIMITS
from analyze_io_usb_host_session import analyze as analyze_session


class CollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        value = os.environ.get("A23_SDK_FIXTURES")
        if not value:
            raise unittest.SkipTest("set A23_SDK_FIXTURES for SDK adapter integration")
        cls.fixture = Path(value)
        cls.sessions = cls.fixture/"final-sessions"
        cls.log = cls.fixture/"inputs/device-log.txt"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/"collection"
        self.make("clean")

    def make(self,name,root=None):
        return freeze(self.sessions/(name+".jsonl"),self.sessions/name,self.log,root or self.root)

    def reseal(self):
        raw = ''.join(f'{hashlib.sha256((self.root/k).read_bytes()).hexdigest()}  {k}\n' for k in sorted(LIMITS)).encode()
        (self.root/"SHA256SUMS").write_bytes(raw)
        (self.root/"COMMITTED").write_text(hashlib.sha256(raw).hexdigest()+'\n')

    def journal_change(self,change):
        path = self.root/"session.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        change(rows)
        raw = ''.join(json.dumps(row)+'\n' for row in rows).encode(); path.write_bytes(raw)
        self.meta_change("journal_sha256",hashlib.sha256(raw).hexdigest()); self.reseal()

    def meta_change(self,key,value):
        path = self.root/"collection.json"; meta = json.loads(path.read_text()); meta[key] = value
        path.write_text(json.dumps(meta)+'\n')

    def status_detail(self,rows,phase="before"):
        return next(r["details"] for r in rows if r["event"] == "status_observed" and r["details"]["phase"] == phase)

    def test_clean_collection_preserves_hardware_boundary(self):
        result = analyze(self.root)
        self.assertTrue(result["simulation_collection_pass"])
        self.assertTrue(result["simulation_byte_binding_verified"])
        for key in ("hardware_verified","usb_strict_pass","capture_binding_verified","callback_drain_verified","firmware_bytes_verified"):
            self.assertIs(result[key],False)

    def test_all_ten_exported_status_scenarios(self):
        paths = list(self.sessions.glob('*.jsonl')); self.assertEqual(len(paths),10)
        for path in paths:
            bundle = self.sessions/path.stem
            result = analyze_session(path,bundle if bundle.is_dir() else None)
            self.assertEqual(result["simulation_session_pass"],path.stem == "clean")
            self.assertTrue(result["requires_status_binding"])
            self.assertFalse(result["hardware_verified"])
        for name in ("clean","short-after","error-after","overflow-after","native-error","late-after-close"):
            result = self.make(name,Path(self.temp.name)/name)
            self.assertEqual(result["simulation_collection_pass"],name == "clean")
            self.assertTrue(result["collection_integrity_verified"])
        for name in ("short-before","stale-before","missing-before","missing-after"):
            result = analyze_session(self.sessions/(name+'.jsonl'))
            self.assertFalse(result["simulation_session_pass"])

    def test_short_reply_is_original_not_padded(self):
        root = Path(self.temp.name)/"short"; result = self.make("short-after",root)
        self.assertEqual(result["status_after_length"],167)
        self.assertEqual((root/"status-after.bin").read_bytes(),(self.fixture/"inputs/after.bin").read_bytes()[:-1])
        self.assertIn("168",result["device_error"])

    def test_correct_device_relation_does_not_override_native_or_status_errors(self):
        for name in ("native-error","error-after","overflow-after"):
            result = self.make(name,Path(self.temp.name)/name)
            self.assertTrue(result["device"]["device_status_and_log_relation_matches"])
            self.assertFalse(result["simulation_collection_pass"])

    def test_late_callback_invalidates_frozen_native_count_one(self):
        result = self.make("late-after-close",Path(self.temp.name)/"late")
        self.assertEqual(result["session"]["callbacks"],2)
        self.assertTrue(result["session"]["late_callback_observed"])
        self.assertFalse(result["simulation_collection_pass"])

    def test_rehashed_binary_still_must_equal_journal(self):
        p = self.root/"status-after.bin"; raw = bytearray(p.read_bytes()); raw[-1] ^= 1; p.write_bytes(raw); self.reseal()
        with self.assertRaisesRegex(ValueError,"original journal"):
            analyze(self.root)

    def test_rehashed_source_cannot_be_sdk_or_reconstructed(self):
        for source in ("sdk_control_reply","historical_json"):
            with self.subTest(source=source):
                original = (self.root/"session.jsonl").read_bytes()
                self.journal_change(lambda rows:self.status_detail(rows)["observation"].update(source=source))
                with self.assertRaisesRegex(ValueError,"source"):
                    analyze(self.root)
                (self.root/"session.jsonl").write_bytes(original)

    def test_rehashed_time_cannot_predate_ready_or_completion(self):
        original = (self.root/"session.jsonl").read_bytes()
        for phase in ("before","after"):
            (self.root/"session.jsonl").write_bytes(original)
            self.journal_change(lambda rows:self.status_detail(rows,phase)["observation"].update(begin_ticks=1))
            with self.assertRaisesRegex(ValueError,"outside"):
                analyze(self.root)

    def test_control_boolean_and_error_schema_rejected(self):
        original = (self.root/"session.jsonl").read_bytes()
        changes = (lambda d:d["observation"]["control"].update(value=False),
                   lambda d:d["observation"].update(error={"domain":"mock","code":False}),
                   lambda d:d["observation"].update(bytes_transferred=True))
        for change in changes:
            (self.root/"session.jsonl").write_bytes(original)
            self.journal_change(lambda rows:change(self.status_detail(rows)))
            with self.assertRaises(ValueError):
                analyze(self.root)

    def test_base64_sha_and_duplicate_phase_rejected(self):
        original = (self.root/"session.jsonl").read_bytes()
        for change in (lambda d:d.update(raw_base64=d["raw_base64"]+' '),
                       lambda d:d.update(raw_sha256='0'*64),lambda d:d.update(phase="after")):
            (self.root/"session.jsonl").write_bytes(original)
            self.journal_change(lambda rows:change(self.status_detail(rows)))
            with self.assertRaises(ValueError):
                analyze(self.root)

    def test_missing_or_mixed_session_status_is_rejected(self):
        original = (self.root/"session.jsonl").read_bytes()
        self.journal_change(lambda rows:self.status_detail(rows).clear())
        with self.assertRaises(ValueError): analyze(self.root)
        (self.root/"session.jsonl").write_bytes(original)
        self.journal_change(lambda rows:next(r for r in rows if r["event"] == "status_observed").update(session_id="other"))
        with self.assertRaisesRegex(ValueError,"mixed sessions"): analyze(self.root)

    def test_cross_bundle_rejected_even_when_outer_manifest_rehashed(self):
        shutil.rmtree(self.root/"transfer")
        shutil.copytree(self.sessions/"late-after-close",self.root/"transfer"); self.reseal()
        with self.assertRaisesRegex(ValueError,"hash mismatch"): analyze(self.root)

    def test_identity_scenario_and_log_hash_rejected(self):
        original = (self.root/"collection.json").read_bytes()
        for key,value in (("session_id","other"),("scenario",{"kind":"no_td"}),("first_frame",True),("device_log_sha256",'0'*64)):
            (self.root/"collection.json").write_bytes(original); self.meta_change(key,value); self.reseal()
            with self.assertRaises(ValueError): analyze(self.root)

    def test_extra_file_symlink_and_uncommitted_rejected(self):
        p = self.root/"extra"; p.write_text('');
        with self.assertRaises(ValueError): analyze(self.root)
        p.unlink(); commit = self.root/"COMMITTED"; raw = commit.read_bytes(); commit.unlink()
        with self.assertRaises(ValueError): analyze(self.root)
        commit.symlink_to(self.root/"SHA256SUMS")
        with self.assertRaises(ValueError): analyze(self.root)
        commit.unlink(); commit.write_bytes(raw)

    def test_exclusive_freeze_never_overwrites_existing_output(self):
        original = (self.root/"SHA256SUMS").read_bytes()
        with self.assertRaises(FileExistsError): self.make("clean")
        self.assertEqual((self.root/"SHA256SUMS").read_bytes(),original)
        self.assertTrue(analyze(self.root)["simulation_collection_pass"])

    def test_write_failure_preserves_partial_output_without_commit(self):
        root = Path(self.temp.name)/"partial"
        from analyze_io_usb_host_collection import durable_write
        count = 0
        def fail(path,raw):
            nonlocal count
            count += 1
            if count == 3: raise OSError("injected write failure")
            durable_write(path,raw)
        with patch("analyze_io_usb_host_collection.durable_write",fail):
            with self.assertRaisesRegex(OSError,"injected"): self.make("clean",root)
        self.assertTrue(root.is_dir()); self.assertFalse((root/"COMMITTED").exists())
        with self.assertRaises(ValueError): analyze(root)
        with self.assertRaises(FileExistsError): self.make("clean",root)


if __name__ == "__main__":
    unittest.main()
