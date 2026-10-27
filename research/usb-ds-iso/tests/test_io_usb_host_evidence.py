"""Offline bundle corruption, schema, native-error, and payload checks."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("a23_transaction_evidence",
    Path(__file__).resolve().parents[1] / "tools/analyze_io_usb_host_evidence.py")
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "bundle"
        self.root.mkdir()
        raw = bytearray(184320)
        rows = []
        for i in range(960):
            active = 522 <= i < 538
            rows.append(struct.pack("<IIIIQI", 0 if active else 0xe00002e7,
                                    192, i*192, 192 if active else 0, 1000+i, 0))
            if active:
                sequence = (65530 + i - 522) & 65535
                raw[i*192:(i+1)*192] = b"ISO1" + struct.pack("<H", sequence) + bytes(
                    (j ^ sequence ^ (sequence >> 8)) & 255 for j in range(6, 192))
        (self.root / "raw.bin").write_bytes(raw)
        (self.root / "transactions.bin").write_bytes(b"".join(rows))
        self.meta = {"schema":"A23-transaction-owner-1", "bundle_schema":"A23-transaction-bundle-1",
            "backend":"iousbhost-transaction-prototype-1", "execution_mode":"simulation",
            "hardware_verified":False, "scenario":{"kind":"single_burst", "first_sequence":65530},
            "transaction_count":960, "request_bytes_per_transaction":192, "transfer_options":0,
            "first_frame":100, "submit_begin_ticks":10, "submit_return_ticks":20,
            "callback_arrival_ticks":30, "overall_u32":0, "owner_state":4,
            "callback_count_at_save":1, "timed_out":False, "callback_pointer_mismatch":False}
        self.save_meta()

    def seal(self):
        sums = "".join(f"{hashlib.sha256((self.root/name).read_bytes()).hexdigest()}  {name}\n"
                       for name in ("raw.bin", "transactions.bin", "metadata.json"))
        (self.root / "SHA256SUMS").write_text(sums)
        (self.root / "COMMITTED").write_text(hashlib.sha256(sums.encode()).hexdigest() + "\n")

    def save_meta(self):
        (self.root / "metadata.json").write_text(json.dumps(self.meta))
        self.seal()

    def result(self):
        return analyzer.analyze(self.root)

    def test_clean_wraparound_and_simulation_boundary(self):
        result = self.result()
        self.assertTrue(result["simulation_logic_pass"])
        self.assertEqual(result["active_indices"], list(range(522, 538)))
        self.assertFalse(result["hardware_verified"])
        self.assertFalse(result["usb_strict_pass"])
        self.assertFalse(result["device_evidence_verified"])

    def test_raw_correct_native_errors_still_fail(self):
        self.meta["overall_u32"] = 0xe00002be
        blob = bytearray((self.root / "transactions.bin").read_bytes())
        struct.pack_into("<I", blob, 522*28, 0xe00002ed)
        (self.root / "transactions.bin").write_bytes(blob)
        self.save_meta()
        result = self.result()
        self.assertTrue(result["payload_matches"])
        self.assertFalse(result["simulation_logic_pass"])
        self.assertEqual(result["overall_u32"], 0xe00002be)
        self.assertEqual(result["status_counts"]["0xe00002ed"], 1)

    def test_timeout_duplicate_and_pointer_mismatch_fail(self):
        for field, value in (("timed_out", True), ("callback_count_at_save", 2),
                             ("callback_pointer_mismatch", True), ("abort_error", {"code":-18})):
            with self.subTest(field=field):
                original = dict(self.meta)
                self.meta[field] = value
                self.save_meta()
                self.assertTrue(self.result()["payload_matches"])
                self.assertFalse(self.result()["simulation_logic_pass"])
                self.meta = original

    def test_inline_callback_may_arrive_before_return(self):
        self.meta["callback_arrival_ticks"] = 15
        self.save_meta()
        self.assertTrue(self.result()["simulation_logic_pass"])

    def test_unchanged_hash_detects_corruption(self):
        (self.root / "raw.bin").write_bytes(bytes(184320))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.result()

    def test_commit_corruption(self):
        (self.root / "COMMITTED").write_text("0"*64 + "\n")
        with self.assertRaisesRegex(ValueError, "commit hash"):
            self.result()

    def test_partial_missing_and_extra_files(self):
        marker = (self.root / "COMMITTED").read_bytes()
        (self.root / "COMMITTED").unlink()
        with self.assertRaisesRegex(ValueError, "missing/extra"):
            self.result()
        (self.root / "COMMITTED").write_bytes(marker)
        (self.root / "unexpected").touch()
        with self.assertRaisesRegex(ValueError, "missing/extra"):
            self.result()

    def test_symlink_rejected(self):
        (self.root / "raw.bin").rename(self.root.parent / "external.bin")
        (self.root / "raw.bin").symlink_to(self.root.parent / "external.bin")
        with self.assertRaisesRegex(ValueError, "plain file"):
            self.result()

    def test_duplicate_json_keys_rejected(self):
        path = self.root / "metadata.json"
        path.write_text(path.read_text()[:-1] + ', "overall_u32": 0}')
        self.seal()
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            self.result()

    def test_duplicate_manifest_rejected(self):
        path = self.root / "SHA256SUMS"
        path.write_bytes(path.read_bytes() + path.read_bytes().splitlines(keepends=True)[0])
        (self.root / "COMMITTED").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
        with self.assertRaisesRegex(ValueError, "duplicate manifest"):
            self.result()

    def test_semantic_layout_corruption_even_with_valid_hash(self):
        for offset, value in ((4, 193), (8, 1000000), (12, 193), (24, 1)):
            with self.subTest(offset=offset):
                old = (self.root / "transactions.bin").read_bytes()
                bad = bytearray(old)
                struct.pack_into("<I", bad, offset, value)
                (self.root / "transactions.bin").write_bytes(bad)
                self.seal()
                with self.assertRaisesRegex(ValueError, "transaction layout"):
                    self.result()
                (self.root / "transactions.bin").write_bytes(old)

    def test_raw_stray_bytes_and_sequence_fail_with_valid_hash(self):
        for offset in (0, 522*192 + 4, 537*192 + 191):
            with self.subTest(offset=offset):
                old = (self.root / "raw.bin").read_bytes()
                bad = bytearray(old); bad[offset] ^= 1
                (self.root / "raw.bin").write_bytes(bad)
                self.seal()
                self.assertFalse(self.result()["payload_matches"])
                (self.root / "raw.bin").write_bytes(old)

    def test_invalid_unfinished_status_is_not_success(self):
        blob = bytearray((self.root / "transactions.bin").read_bytes())
        struct.pack_into("<I", blob, 0, 0xe0000001)
        (self.root / "transactions.bin").write_bytes(blob)
        self.seal()
        self.assertFalse(self.result()["simulation_logic_pass"])

    def test_cannot_upgrade_simulation_or_fake_numeric_types(self):
        for field, value in (("hardware_verified", True), ("execution_mode", "hardware"),
                             ("transaction_count", "960"), ("overall_u32", False),
                             ("submit_begin_ticks", -1), ("owner_state", True)):
            with self.subTest(field=field):
                original = dict(self.meta)
                self.meta[field] = value
                self.save_meta()
                with self.assertRaises(ValueError):
                    self.result()
                self.meta = original

    def test_exported_objc_bundles(self):
        fixture = os.environ.get("A23_SIMULATION_BUNDLES")
        if not fixture:
            self.skipTest("set A23_SIMULATION_BUNDLES for Objective-C integration")
        for name, expected in (("clean", True), ("native-error", False), ("timeout", False),
                               ("rejected", False), ("duplicate", False), ("no-td", True)):
            with self.subTest(bundle=name):
                result = analyzer.analyze(Path(fixture)/name)
                self.assertEqual(result["simulation_logic_pass"], expected)
                self.assertFalse(result["usb_strict_pass"])
        with self.assertRaisesRegex(ValueError, "missing/extra"):
            analyzer.analyze(Path(fixture)/"partial-write")


if __name__ == "__main__":
    unittest.main()
