#!/usr/bin/env python3
"""Execute the isolated controller in Unicorn and compare native payload bytes.

Only CPU emulation and a C file fixture run here. No SDK objects, hardware,
permission issuers, acquisition workflows or mutable tickets are imported.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest

from analyze_a23_short24 import analyze, require


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_patch as harness
from unicorn import UC_HOOK_MEM_WRITE, __version__ as unicorn_version
from unicorn.arm64_const import UC_ARM64_REG_X19, UC_ARM64_REG_X20


def audit(build, output):
    build, output = build.resolve(), output.resolve()
    require((build / "build.json").is_file() and not output.exists(), "completed build and fresh audit required")
    require(unicorn_version == "2.1.4", "Unicorn2.1.4 required for this audit")
    output.mkdir(parents=True)
    harness.PACKAGES = build / "controller"
    RING, ENTRY, DMA = harness.RING, harness.ENTRY, harness.DMA

    def machine(slot=0):
        m = harness.Machine("A")
        for offset in (0x18, 0x20):
            m.write(ENTRY + offset, "<Q", RING + slot * 16)
        return m

    def pointer(slot, packet, ed=True):
        base = RING if ed else harness.RING_DMA
        return base + ((slot + 2 * packet + int(ed)) % 247) * 16

    compile_command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
        "-I" + str(build / "device/source/uvc"), str(ROOT / "tests/a23_short24_payload_fixture.c"),
        "-o", str(output / "payload-fixture")]
    subprocess.run(compile_command, check=True, capture_output=True)
    payload = subprocess.check_output([str(output / "payload-fixture"), "1"])
    require(len(payload) == 384, "native payload fixture size")

    def completed_model():
        m = machine()
        require(m.submit(384) == 0, "short24 submit")
        for p in range(16):
            calls = m.event(pointer(0, p), True, count=24)
            require(calls == ([] if p < 15 else [(0x2a980, [harness.MANAGER, 0x83, 0, 1, 384, 1])]),
                    "unexpected completion")
        raw = bytearray(128 * 24)
        transactions = bytearray(128 * 28)
        for i in range(128):
            count = 24 if 9 <= i < 25 else 0
            struct.pack_into("<iIIIQI", transactions, i * 28, 0, 24, i * 24, count, 17, 0)
            if count:
                raw[i * 24:(i + 1) * 24] = payload[(i - 9) * 24:(i - 8) * 24]
        # Synthetic usb:ds/host envelope around actual emulated diagnostics.
        after = bytearray(struct.pack("<14I", 0x31505349, 1, 1, 2, 0, 101, 101,
                                      384, 384, 3, 3, 0x83, 0, 0))
        after.extend(m.uc.mem_read(RING + 0xf80, 112))
        return raw, transactions, after

    positive = completed_model()

    class ControllerTests(unittest.TestCase):
        def test_linked_device_contains_new_controller_and_recipe(self):
            folder = build / "device"
            blob = (folder / "full.elf").read_bytes()
            self.assertEqual(blob[:6], b"\x7fELF\x02\x01")
            self.assertEqual(struct.unpack_from("<H", blob, 18)[0], 183)
            table = struct.unpack_from("<Q", blob, 40)[0]
            width, count = struct.unpack_from("<HH", blob, 58)
            self.assertEqual(width, 64)
            sections = [struct.unpack_from("<IIQQQQIIQQ", blob, table + i * width) for i in range(count)]

            def virtual_bytes(address, length):
                for section in sections:
                    if section[1] != 8 and section[3] <= address and address + length <= section[3] + section[5]:
                        offset = section[4] + address - section[3]
                        return blob[offset:offset + length]
                self.fail("ELF symbol is not file backed")

            symbols = []
            for line in (folder / "symbols.txt").read_text().splitlines():
                fields = line.split()
                if len(fields) == 8 and fields[0].endswith(":") and fields[3] == "OBJECT":
                    size = int(fields[2], 16) if fields[2].startswith("0x") else int(fields[2])
                    symbols.append((fields[-1], int(fields[1], 16), size))
            runtime = [s for s in symbols if s[0] == "isoRuntime_0_after"]
            self.assertEqual(len(runtime), 1)
            self.assertEqual(virtual_bytes(runtime[0][1], runtime[0][2]),
                             (build / "controller/A/inject.bin").read_bytes())
            recipe = bytes.fromhex(json.loads((folder / "recipe.json").read_text())["runtime_recipe_sha256"])
            constants = [s for s in symbols if s[0] == "ep0CandidateRecipe"]
            self.assertEqual(len(constants), 2)
            self.assertTrue(all(virtual_bytes(s[1], s[2]) == recipe for s in constants))
            self.assertEqual([s[2] for s in symbols if s[0] == "g_isoBuffer"], [4096])
            self.assertEqual(hashlib.sha256(blob).hexdigest(),
                             json.loads((build / "build.json").read_text())["device_elf_sha256"])

        def test_fixed_length_and_legacy_input_rejection(self):
            for size in (0, 24, 383, 385, 3072):
                m = machine()
                before = bytes(m.uc.mem_read(RING, 4096))
                self.assertEqual(m.submit(size), 0x1908c)
                self.assertEqual(bytes(m.uc.mem_read(RING, 4096)), before)
            self.assertEqual(machine().submit(384), 0)
            harness.PACKAGES = ROOT / "private/packages-A23-interval1"
            try:
                self.assertEqual(harness.Machine("A").submit(384), 0x1908c)
            finally:
                harness.PACKAGES = build / "controller"

        def test_packet_addresses_lengths_and_frame_wrap(self):
            for slot in (0, 230, 246):
                for mfi in (0, 0x3fff):
                    m = machine(slot)
                    m.write(harness.MMIO + 0x48, "<I", mfi)
                    self.assertEqual(m.submit(384), 0)
                    for p in range(16):
                        position = slot + 2 * p
                        address = RING + position % 247 * 16
                        pointer_value, length, control = m.read(address, "<QII")
                        self.assertEqual((pointer_value, length), (DMA + p * 24, 24))
                        cycle = 1 ^ (position // 247)
                        expected = (0x80001410 if p else (((mfi >> 3) + 32) & 2047) << 20 | 0x1410) | cycle
                        self.assertEqual(control, expected)
                        self.assertEqual(m.read(pointer(slot, p), "<Q")[0], pointer(slot, p))
                    self.assertEqual(m.read(ENTRY + 0x18, "<Q")[0], RING + (slot + 32) % 247 * 16)

        def test_publication_and_context_write_boundaries(self):
            m = machine(246)
            writes = []
            hook = m.uc.hook_add(UC_HOOK_MEM_WRITE,
                lambda u, access, address, size, value, _: writes.append((address, size, value)))
            self.assertEqual(m.submit(384), 0)
            m.uc.hook_del(hook)
            gate = [w for w in writes if w[0] == RING + 246 * 16 + 12]
            self.assertEqual([w[2] & 1 for w in gate], [0, 1])
            self.assertLess(writes.index(gate[0]), writes.index((RING + 0xfcc, 4, 1)))
            self.assertLess(writes.index((RING + 0xfcc, 4, 1)), writes.index(gate[1]))
            self.assertEqual([w for w in writes if harness.MMIO <= w[0] < harness.MMIO + 4096],
                             [(harness.MMIO + 4, 4, 0x700)])
            self.assertFalse(any(harness.CTX <= w[0] < harness.CTX + 4096 for w in writes))

        def test_unique_ed_completion_and_post_terminal(self):
            for slot in (0, 246):
                m = machine(slot)
                self.assertEqual(m.submit(384), 0)
                for p in range(16):
                    expected = [] if p < 15 else [(0x2a980, [harness.MANAGER, 0x83, 0, 1, 384, 1])]
                    self.assertEqual(m.event(pointer(slot, p), True, count=24), expected)
                    self.assertEqual(m.event(pointer(slot, p), True, count=24), [])
                self.assertEqual(m.read(RING + 0xf8c, "<III"), (1, 65535, 384))
                completed = bytes(m.uc.mem_read(RING + 0xf80, 112))
                m.event(0, False, cc=23, count=0)
                self.assertEqual(bytes(m.uc.mem_read(RING + 0xf80, 112)), completed)

        def test_missing_ed_retains_ownership(self):
            m = machine()
            self.assertEqual(m.submit(384), 0)
            for p in range(15):
                self.assertEqual(m.event(pointer(0, p), True, count=24), [])
            self.assertEqual(m.read(RING + 0xf8c, "<III"), (0, 32767, 360))
            self.assertEqual(m.read(ENTRY + 0x20, "<Q")[0], RING)
            self.assertEqual(m.submit(384), 0x1908c)

        def test_bad_completion_lengths_and_native_error_retain(self):
            for cc, count in ((1, 23), (1, 25), (1, 192), (13, 24)):
                m = machine()
                self.assertEqual(m.submit(384), 0)
                self.assertEqual(m.event(pointer(0, 0), True, cc=cc, count=count), [])
                self.assertEqual(m.read(RING + 0xf8c, "<III"), (0x80000000 | cc, 0, 0))
                for p in range(16):
                    self.assertEqual(m.event(pointer(0, p), True, count=24), [])
                self.assertEqual(m.read(ENTRY + 0x20, "<Q")[0], RING)
                self.assertEqual(m.submit(384), 0x1908c)

        def test_speed_interval_mps_and_filtered_events(self):
            for address, fmt, value in ((harness.CTRL + 0x22a58, "<I", 4),
                                        (ENTRY + 6, "<B", 4), (ENTRY + 4, "<H", 192)):
                m = machine()
                m.write(address, fmt, value)
                self.assertEqual(m.submit(384), 0x1908c)
            m = machine()
            self.assertEqual(m.submit(384), 0)
            for ptr, ed in ((0, False), (RING + 0xf70, True), (pointer(0, 0) + 1, True)):
                self.assertEqual(m.event(ptr, ed, cc=1, count=24), [])
                self.assertEqual(m.read(RING + 0xf8c, "<III"), (0, 0, 0))

        def test_original_report_copy_preserves_short24_diagnostics(self):
            m = machine()
            self.assertEqual(m.submit(384), 0)
            for p in range(16):
                m.event(pointer(0, p), True, count=24)
            report = harness.CTX + 0x800
            m.uc.reg_write(UC_ARM64_REG_X19, harness.MANAGER)
            m.uc.reg_write(UC_ARM64_REG_X20, report)
            m.uc.emu_start(m.symbols["iso_report"], 0x2cbe4, count=1000)
            self.assertEqual(bytes(m.uc.mem_read(report + 16, 112)), bytes(m.uc.mem_read(RING + 0xf80, 112)))

    class ConsumerTests(unittest.TestCase):
        def test_native_device_pattern_and_arm_terminal_roundtrip(self):
            result = analyze(*positive, 1, 0)
            self.assertEqual(result["payload_bytes"], 384)
            self.assertFalse(result["hardware_verified"])
            self.assertFalse(result["device_log_relation_verified"])

        def test_empty_slot_native_error_and_overall_are_not_hidden(self):
            raw, tx, status = map(bytearray, positive)
            struct.pack_into("<i", tx, 127 * 28, -1)
            with self.assertRaisesRegex(ValueError, "native short24 transaction"):
                analyze(raw, tx, status, 1, 0)
            with self.assertRaisesRegex(ValueError, "overall native result"):
                analyze(*positive, 1, 1)

        def test_old_marker_or_size_cannot_be_relabelled(self):
            raw, tx, status = map(bytearray, positive)
            struct.pack_into("<I", status, 56, 0x374f5349)
            with self.assertRaisesRegex(ValueError, "IS24 terminal identity"):
                analyze(raw, tx, status, 1, 0)
            raw, tx, status = map(bytearray, positive)
            raw[9 * 24:9 * 24 + 4] = b"ISO1"
            with self.assertRaisesRegex(ValueError, "payload sequence/body"):
                analyze(raw, tx, status, 1, 0)
            with self.assertRaisesRegex(ValueError, "snapshot sizes"):
                analyze(bytes(128 * 192), tx, positive[2], 1, 0)

        def test_wrong_lengths_partial_or_missing_packets_rejected(self):
            for count in (23, 25, 192):
                raw, tx, status = map(bytearray, positive)
                struct.pack_into("<I", tx, 9 * 28 + 12, count)
                with self.assertRaisesRegex(ValueError, "native short24 transaction"):
                    analyze(raw, tx, status, 1, 0)
            raw, tx, status = map(bytearray, positive)
            struct.pack_into("<I", tx, 24 * 28 + 12, 0)
            with self.assertRaisesRegex(ValueError, "16 consecutive"):
                analyze(raw, tx, status, 1, 0)

        def test_bad_bitmap_body_and_sequence_wrap_rejected(self):
            raw, tx, status = map(bytearray, positive)
            struct.pack_into("<I", status, 56 + 16, 32767)
            with self.assertRaisesRegex(ValueError, "IS24 terminal identity"):
                analyze(raw, tx, status, 1, 0)
            raw, tx, status = map(bytearray, positive)
            raw[9 * 24 + 20] ^= 1
            with self.assertRaisesRegex(ValueError, "payload sequence/body"):
                analyze(raw, tx, status, 1, 0)
            with self.assertRaisesRegex(ValueError, "sequence range"):
                analyze(*positive, 65521, 0)

        def test_extra_packet_wrong_request_and_legacy_total_rejected(self):
            raw, tx, status = map(bytearray, positive)
            struct.pack_into("<I", tx, 25 * 28 + 12, 24)
            with self.assertRaisesRegex(ValueError, "extra packet"):
                analyze(raw, tx, status, 1, 0)
            raw, tx, status = map(bytearray, positive)
            struct.pack_into("<I", tx, 9 * 28 + 4, 192)
            with self.assertRaisesRegex(ValueError, "native short24 transaction"):
                analyze(raw, tx, status, 1, 0)
            raw, tx, status = map(bytearray, positive)
            struct.pack_into("<I", status, 7 * 4, 3072)
            with self.assertRaisesRegex(ValueError, "completed short24 STATUS"):
                analyze(raw, tx, status, 1, 0)

    suite = unittest.TestSuite()
    for case in (ControllerTests, ConsumerTests):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (output / "tests.log").write_text(stream.getvalue())
    require(result.wasSuccessful() and not result.skipped, "short24 check failed; see tests.log")
    for name, raw in zip(("raw.bin", "transactions.bin", "after.bin"), positive):
        (output / ("MODEL-" + name)).write_bytes(raw)
    report = dict(schema="A23-short24-offline-audit-1", tests_passed=result.testsRun,
        cpu_emulator="Unicorn2.1.4", emulated_arm_controller=True, synthetic_host_envelope=True,
        native_device_header_payload=True, native_fixture_compile_command=compile_command,
        payload_analysis=analyze(*positive, 1, 0), new_usb_operations=0, sd_accesses=0,
        hardware_verified=False, host_sdk_receiver_ready=False, full_device_elf_built=True)
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.build, args.output)
    print(json.dumps(dict(tests_passed=result["tests_passed"], hardware_verified=False)))
