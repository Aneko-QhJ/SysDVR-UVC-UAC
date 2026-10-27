#!/usr/bin/env python3
"""Compile the SDK capability; execute injected native I/O and C wire fixtures."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from build_a23_short24_candidate import verify_tree
from analyze_a23_short24_session import analyze, host_observation
from analyze_a23_short24 import require


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "private/analysis/A23-short24-candidate-20261027-r2"
MODELS = ROOT / "private/analysis/A23-short24-audit-20261027-r4"
NEW = ("host/a23_short24_capture.h", "host/a23_short24_capture.m", "tests/a23_short24_capture_fixture.m",
       "tests/a23_short24_execution_fixture.c", "tools/analyze_a23_short24_session.py", "tools/audit_a23_short24_sdk.py")


def run(output):
    output = output.resolve()
    require(not output.exists(), "fresh output required")
    seals = {str(p): verify_tree(p) for p in (BUILD, MODELS)}
    recipe = json.loads((BUILD / "device/recipe.json").read_text())["runtime_recipe_sha256"]
    output.mkdir(parents=True)
    commands = []

    def command(args):
        commands.append([str(x) for x in args])
        result = subprocess.run(commands[-1], capture_output=True, text=True)
        with (output / "commands.log").open("a") as handle:
            handle.write(result.stdout + result.stderr)
        require(result.returncode == 0, "native command failed; see commands.log")

    flags = ["-std=gnu11", "-fobjc-arc", "-fblocks", "-Wall", "-Wextra", "-Werror",
             "-Wno-deprecated-declarations", "-mmacosx-version-min=26.4"]
    command(["clang", *flags, "-c", ROOT / "host/a23_short24_capture.m", "-o", output / "capture.o"])
    command(["clang", *flags, "-fsanitize=address,undefined", ROOT / "host/a23_short24_capture.m",
             ROOT / "tests/a23_short24_capture_fixture.m", "-framework", "Foundation", "-framework", "IOKit",
             "-framework", "IOUSBHost", "-o", output / "capture-fixture"])
    (output / "cases").mkdir()
    command([output / "capture-fixture", MODELS, output / "cases", recipe])
    command(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-fsanitize=address,undefined",
             "-I" + str(BUILD / "device/source/uvc"), ROOT / "tests/a23_short24_execution_fixture.c",
             "-o", output / "execution-fixture"])
    command([output / "execution-fixture", output / "MODEL-execution.bin", output / "MODEL-primary.bin"])
    execution, primary = (output / "MODEL-execution.bin").read_bytes(), (output / "MODEL-primary.bin").read_bytes()
    cases = output / "cases"
    accepted, rejected = {}, {}
    for folder in sorted(cases.iterdir()):
        if not folder.is_dir():
            continue
        try:
            accepted[folder.name] = analyze(folder, execution, primary, recipe)
        except (ValueError, KeyError, TypeError, struct.error) as error:
            rejected[folder.name] = str(error)
    require(set(accepted) == {"iso-first", "control-first", "inline-control", "queue-delay"},
            "unexpected native host acceptances: " + str(set(accepted)))
    require(len(rejected) == 17 and "native short24 transaction" in rejected["native-empty-error"],
            "empty-slot error was lost")

    def changed_wire(stage, field, value):
        """Recompute all CRCs so deep relation tests do not stop at framing."""
        p = bytearray(primary)
        trace_at = 112 + struct.unpack_from("<I", p, 20)[0] * 16
        count = struct.unpack_from("<I", p, trace_at + 20)[0]
        matches = [trace_at + 128 + i * 48 for i in range(count)
                   if struct.unpack_from("<H", p, trace_at + 128 + i * 48 + 36)[0] == stage]
        require(matches, "wire stage not found")
        struct.pack_into("<I", p, matches[-1] + field, value)
        struct.pack_into("<I", p, trace_at + 96, zlib.crc32(p[trace_at + 128:]))
        struct.pack_into("<I", p, trace_at + 100, 0)
        struct.pack_into("<I", p, trace_at + 100, zlib.crc32(p[trace_at:trace_at + 128]))
        struct.pack_into("<I", p, 88, zlib.crc32(p[trace_at:]))
        struct.pack_into("<I", p, 92, 0)
        struct.pack_into("<I", p, 92, zlib.crc32(p[:112]))
        e = bytearray(execution)
        ini = struct.unpack_from("<I", e, 24)[0]
        e[256 + ini:] = p
        struct.pack_into("<I", e, 180, zlib.crc32(p))
        struct.pack_into("<I", e, 184, 0)
        struct.pack_into("<I", e, 184, zlib.crc32(e[:256]))
        return e, p

    class RelationTests(unittest.TestCase):
        def test_native_model_chain_is_consistent_without_hardware_claims(self):
            for result in accepted.values():
                self.assertTrue(result["supplied_device_relation_consistent"])
                self.assertEqual(result["payload_bytes"], 384)
                self.assertEqual(result["host_execution_mode"], "injected_model")
                self.assertFalse(result["hardware_verified"])
                self.assertFalse(result["process_exit_authorized"])

        def test_empty_slot_error_survives_successful_callbacks(self):
            m = json.loads((cases / "native-empty-error/metadata.json").read_text())
            self.assertTrue(m["observation_complete"])
            with self.assertRaisesRegex(ValueError, "native short24 transaction"):
                host_observation(cases / "native-empty-error", recipe)

        def test_deep_device_length_sequence_and_status_mismatches(self):
            for stage, field, value, reason in [(7, 28, 3072, "device ISO"), (6, 28, 2, "device ISO"),
                                                 (15, 28, 3, "device STATUS")]:
                e, p = changed_wire(stage, field, value)
                with self.assertRaisesRegex(ValueError, reason):
                    analyze(cases / "iso-first", e, p, recipe)

        def test_recipe_crc_and_external_primary_mismatch(self):
            with self.assertRaises(ValueError):
                analyze(cases / "iso-first", execution, primary, "00" * 32)
            bad = bytearray(execution)
            bad[-1] ^= 1
            with self.assertRaisesRegex(ValueError, "CRC"):
                analyze(cases / "iso-first", bad, primary, recipe)
            with self.assertRaisesRegex(ValueError, "external primary"):
                analyze(cases / "iso-first", execution, primary + b"x", recipe)

        def test_deadline_and_duplicate_facts_survive_erased_summary(self):
            for name, reason in [("late-control", "native ingress deadline"), ("duplicate-iso", "event count")]:
                with tempfile.TemporaryDirectory() as temp:
                    folder = Path(temp) / "host"
                    shutil.copytree(cases / name, folder)
                    path = folder / "metadata.json"
                    m = json.loads(path.read_text())
                    m.update(stopped=False, observation_complete=True, io_unresolved=False, failure_reasons=[],
                             iso_callbacks=1, control_callbacks=1)
                    # Include a valid post-STATUS to reach the independent fact check.
                    (folder / "after.bin").write_bytes((cases / "iso-first/after.bin").read_bytes())
                    m["after_reads"] = 1
                    path.write_text(json.dumps(m))
                    with self.assertRaisesRegex(ValueError, reason):
                        analyze(folder, execution, primary, recipe)

        def test_enqueue_error_details_and_unknown_ownership_are_retained(self):
            for name in ("iso-rejected", "burst-rejected", "foreign-pointer"):
                m = json.loads((cases / name / "metadata.json").read_text())
                self.assertTrue(m["resources_retained"])
                self.assertTrue(m["io_unresolved"])
                self.assertFalse(m["process_exit_authorized"])
            m = json.loads((cases / "iso-rejected/metadata.json").read_text())
            failure = next(e for e in m["events"] if e["event"] == "iso_return")
            self.assertEqual(failure["details"]["error_info"], {"domain": "injected", "code": 7})

        def test_final_trigger_gate_rechecks_arrival_and_elapsed_budget(self):
            for name in ("arrival-during-intent", "gap-during-intent"):
                m = json.loads((cases / name / "metadata.json").read_text())
                self.assertEqual(m["iso_attempts"], 1)
                self.assertEqual(m["burst_attempts"], 0)
                self.assertIn("trigger_admission", m["failure_reasons"])
                self.assertTrue(m["resources_retained"])

    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RelationTests))
    (output / "tests.log").write_text(stream.getvalue())
    require(result.wasSuccessful() and not result.skipped, "relation checks failed; see tests.log")
    report = dict(schema="A23-short24-sdk-offline-audit-1", source_hashes={n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in NEW},
        parent_seals=seals, recipe=recipe, compiler_commands=commands, native_injected_scenarios=21,
        related_models_accepted=accepted, rejected_models=rejected, relation_checks_passed=result.testsRun,
        host_sdk_capability_compiled=True, native_sanitizers="ASan/UBSan", device_sidecar_from_actual_serializers=True,
        sdk_objects_created=0, sdk_io_calls=0, usb_operations=0, sd_accesses=0, deployment_performed=False,
        automatic_capture_entry_enabled=False, hardware_verified=False, process_exit_authorized=False)
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = run(parser.parse_args().output)
    print(json.dumps({k: result[k] for k in ("native_injected_scenarios", "relation_checks_passed", "hardware_verified")}))
