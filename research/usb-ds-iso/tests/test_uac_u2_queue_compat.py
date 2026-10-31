"""Queue-compatible U2 completion: static decode plus the real 0x2c690 replay.

The design is in docs/UAC_U2_QUEUE_COMPAT_DESIGN.md.  The static tests pin the
driver chain (0x2c520 enqueues before the vtable submit, 0x2c690 adds the
transferred size to entry+44, 0x2cbe0 is the report epilogue) and the cave's
completion arguments.  The replay class runs the real 0x2c690 under Unicorn
when it is installed; it skips otherwise.
"""
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_patch import CAVE, validate_module
from build_uac_descriptor_payload import load_elf_sections
from build_uac_u2_producer import (
    REPORT_HOOK, build_edits, endpoint_constants_ok, payload_ready, render,
)

ELF = ROOT / "private/module/usb.elf"
ASM_SAFE = ROOT / "patches/iso_burst_uac84_safe.S"
ASM_NOREPORT = ROOT / "patches/iso_burst_uac84_noreport.S"
NSO = ROOT / "private/module/exefs/main"
WORK_NOREPORT = ROOT / "private/analysis/UAC-u2-noreport-20261030"
WORK_V2 = ROOT / "private/analysis/UAC-u2-noreport2-20261030"
WORK_V3 = ROOT / "private/analysis/UAC-u2-v3-20261031"


def _word(data, sections, address):
    for sec in sections.values():
        if sec["type"] != 8 and sec["addr"] <= address < sec["addr"] + sec["size"]:
            off = sec["offset"] + address - sec["addr"]
            return int.from_bytes(data[off:off + 4], "little")
    raise ValueError(f"{address:#x} outside mapped sections")


class UacU2QueueCompatStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ELF.is_file():
            raise unittest.SkipTest(f"missing {ELF}")
        cls.data, cls.sections = load_elf_sections(ELF)

    def word(self, address):
        return _word(self.data, self.sections, address)

    def test_request_is_enqueued_before_the_vtable_submit(self):
        # 0x2c5dc stp w22,w22,[x9,#32]  requested/remaining
        # 0x2c5e0 str x11,[x9,#40]      status=1 (queued)
        # 0x2c5e4 stp x23,x10,[x9,#8]   buffer/mapped IOVA
        # 0x2c664 blr x8                controller vtable+136 == 0x302e0
        self.assertEqual(self.word(0x2C5CC), 0x5280002B)  # mov w11,#1
        self.assertEqual(self.word(0x2C5DC), 0x29045936)
        self.assertEqual(self.word(0x2C5E0), 0xF900152B)
        self.assertEqual(self.word(0x2C5E4), 0xA900A937)
        self.assertEqual(self.word(0x2C664), 0xD63F0100)
        self.assertLess(0x2C5E4, 0x2C664)

    def test_completion_adds_transferred_and_compares_requested(self):
        # 0x2c6fc ldr w8,[x25,#44]  previous transferred
        # 0x2c700 add w2,w8,w21     + the complete_original w4 argument
        # 0x2c704 ldr w8,[x25,#32]  requested
        # 0x2c708 str w2,[x25,#44]
        # 0x2c70c cmp w2,w8
        # 0x2c710 b.ne 0x2c754
        self.assertEqual(self.word(0x2C6FC), 0xB9402F28)
        self.assertEqual(self.word(0x2C700), 0x0B150102)
        self.assertEqual(self.word(0x2C704), 0xB9402328)
        self.assertEqual(self.word(0x2C708), 0xB9002F22)
        self.assertEqual(self.word(0x2C70C), 0x6B08005F)
        self.assertEqual(self.word(0x2C710), 0x54000221)

    def test_completion_uses_the_endpoint_queue_index_and_count(self):
        self.assertEqual(self.word(0x2C6D0), 0xB9400688)  # ldr w8,[x20,#4]
        self.assertEqual(self.word(0x2C6D8), 0x52800609)  # mov w9,#0x30
        self.assertEqual(self.word(0x2C6DC), 0x9BA96119)  # umaddl x25
        self.assertEqual(self.word(0x2C7F4), 0x11000508)  # add w8,w8,#1
        self.assertEqual(self.word(0x2C7F8), 0x51000529)  # sub w9,w9,#1
        self.assertEqual(self.word(0x2C800), 0x2900A688)  # stp w8,w9,[x20,#4]

    def test_report_epilogue_is_where_the_driver_built_the_report(self):
        self.assertEqual(self.word(0x2CBE0), 0x91004260)  # add x0,x19,#0x10
        self.assertEqual(REPORT_HOOK, 0x2CBE0)
        text = ASM_SAFE.read_text()
        self.assertIn("iso_report:", text)
        self.assertIn("ldr w8, [x20, #128]", text)   # report count
        self.assertIn("add x9, x20, #16", text)      # overwrite report data
        self.assertIn("str q0, [x9], #16", text)
        self.assertIn("b report_epilogue", text)

    def test_zlp_check_is_off_for_the_iso_attributes(self):
        # 0x2a910 ldrb w8,[x0,#3]  endpoint bmAttributes
        # 0x2a914 tbnz w8,#1       only bulk goes on to the ZLP test
        # 0x2a918 mov w0,wzr       ISO returns 0
        self.assertEqual(self.word(0x2A910), 0x39400C08)
        self.assertEqual(self.word(0x2A914), 0x37080108)
        self.assertEqual(self.word(0x2A918), 0x2A1F03E0)
        self.assertEqual(0x05 & 0x02, 0)  # UAC ISO attrs: no ZLP
        self.assertEqual(0x02 & 0x02, 2)  # bulk: ZLP check applies

    def test_cave_completion_passes_the_accumulated_3072(self):
        text = ASM_SAFE.read_text()
        load = text.index("ldr w4, [x5, #20]")
        add = text.index("add w4, w4, #192")
        store = text.index("str w4, [x5, #20]")
        compare = text.index("cmp w4, #3072")
        complete = text.index("b complete_original")
        self.assertLess(load, add)
        self.assertLess(add, store)
        self.assertLess(store, compare)
        self.assertLess(compare, complete)
        tail = text[compare:complete]
        self.assertIn("mov w2, #0", tail)
        self.assertIn("mov w3, #1", tail)
        self.assertIn("mov w5, #1", tail)


class UacU2NoReportPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK_NOREPORT / "manifest.json").is_file():
            raise unittest.SkipTest(f"missing {WORK_NOREPORT}")
        if not NSO.is_file():
            raise unittest.SkipTest(f"missing {NSO}")
        cls.doc = payload_ready(WORK_NOREPORT)
        cls.nso = validate_module(NSO.read_bytes())
        cls.cave = bytes.fromhex(
            next(e["after"] for e in cls.doc["edits"]
                 if int(e["address"], 16) == CAVE)
        )
        cls.symbols = {k: int(v, 16) for k, v in cls.doc["symbols"].items()}

    def test_payload_drops_only_the_report_hook(self):
        self.assertFalse(self.doc["report_hook"])
        self.assertEqual(self.doc["edit_count"], 29)
        self.assertEqual(self.doc["counts"],
                         {"cave": 1, "branch": 2, "descriptor": 18, "nop": 8})
        addresses = {int(e["address"], 16) for e in self.doc["edits"]}
        self.assertNotIn(REPORT_HOOK, addresses)
        self.assertNotIn("iso_report", self.doc["symbols"])
        self.assertLess(self.doc["cave_bytes"], 684)
        self.assertTrue(endpoint_constants_ok(self.cave, require_report=False))

    def test_assembly_has_no_report_function(self):
        text = ASM_NOREPORT.read_text()
        self.assertNotIn("\niso_report:", text)
        self.assertNotIn("b report_epilogue", text)
        self.assertIn("iso_enter:", text)
        self.assertIn("iso_event:", text)

    def test_edits_match_the_elf_and_render(self):
        edits = build_edits(self.nso, self.cave, self.symbols, report=False)
        self.assertEqual(render(edits), (WORK_NOREPORT / "uac_u2_payload.h").read_text())
        self.assertEqual(
            [(e["address"], e["before"], e["after"]) for e in self.doc["edits"]],
            [(hex(a), b.hex(), c.hex()) for a, b, c, _r in edits],
        )

    def test_build_result_matches_the_payload(self):
        build = json.loads((WORK_NOREPORT / "build-result.json").read_text())
        self.assertEqual(build["payload"]["edit_count"], 29)
        self.assertEqual(build["payload"]["cave_bytes"], 592)
        self.assertEqual(build["payload"]["cave_sha256"], self.doc["cave_sha256"])
        nsp = Path(build["output"]["nsp"])
        if nsp.is_file():
            self.assertEqual(hashlib.sha256(nsp.read_bytes()).hexdigest(),
                             build["output"]["sha256"])

    def test_app_has_one_shot_and_queue_diagnostics(self):
        source = (ROOT.parents[1] / "source/uvc/uvc_device.c").read_text()
        self.assertIn("u32 postSeq;", source)
        self.assertIn('g_uacCtx.burstPosted = true;\n    LOG("UAC U2 train begin', source)
        self.assertIn('LOG("UAC U2 post begin seq=%u/%u\\n", seq, UAC_U2_TRAIN_POSTS);', source)
        self.assertIn("for (u32 n = 0; n < UAC_U2_TRAIN_POSTS; ++n)", source)
        self.assertIn("g_u2BurstBuffers[n]", source)
        self.assertIn("usbDsEndpoint_Cancel", source)
        self.assertIn("UAC_U2_ONE_SHOT", source)
        self.assertIn('LOG("UAC U2 install obj=0x%llx table=0x%llx', source)
        self.assertIn('LOG("UAC U2 entry %s addr=0x%llx', source)
        self.assertIn('LOG("UAC U2 report data count=%u urb=%u', source)
        self.assertIn('LOG("UAC U2 report[%u] id=%u req=%u xfer=%u status=%u', source)
        self.assertIn('LOG("UAC U2 ring dci=%u cycle=%u', source)
        self.assertIn('mfi=0x%x frame=%u regs=0x%llx', source)
        self.assertIn('LOG("UAC U2 trb0 addr=0x%llx len=%u ctl=0x%08x', source)
        self.assertIn("ep.installed != 1 || ep.table_ptr == 0", source)
        self.assertIn("install object not ready", source)
        self.assertIn("UAC U2 pattern 1kHz 16ms", source)
        self.assertIn("samples[i] = ((frame / 24) & 1)", source)
        self.assertIn("UAC_U2_INSTALL_OBJ_PTR_OFFSET 0xFC9B8ULL", source)
        self.assertIn("UAC_U2_INSTALL_FLAG_OFF 0x1610ULL", source)
        self.assertIn("UAC_U2_INSTALL_TABLE_OFF 0x1608ULL", source)
        self.assertNotIn("dev_installed", source)



class UacU2QueueObjectBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK_V2 / "build-result.json").is_file():
            raise unittest.SkipTest(f"missing {WORK_V2}")
        cls.doc = payload_ready(WORK_V2)
        cls.build = json.loads((WORK_V2 / "build-result.json").read_text())

    def test_build_uses_the_same_no_report_payload(self):
        self.assertEqual(self.build["payload"]["edit_count"], 29)
        self.assertEqual(self.build["payload"]["cave_bytes"], 592)
        self.assertEqual(self.build["payload"]["cave_sha256"],
                         self.doc["cave_sha256"])
        nsp = Path(self.build["output"]["nsp"])
        if nsp.is_file():
            self.assertEqual(hashlib.sha256(nsp.read_bytes()).hexdigest(),
                             self.build["output"]["sha256"])



class UacU2InstalledGateBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK_V3 / "build-result.json").is_file():
            raise unittest.SkipTest(f"missing {WORK_V3}")
        cls.doc = payload_ready(WORK_V3)
        cls.build = json.loads((WORK_V3 / "build-result.json").read_text())

    def test_build_uses_the_gated_no_report_payload(self):
        self.assertEqual(self.build["payload"]["edit_count"], 29)
        self.assertEqual(self.build["payload"]["cave_bytes"], 592)
        self.assertEqual(self.build["payload"]["cave_sha256"],
                         self.doc["cave_sha256"])
        nsp = Path(self.build["output"]["nsp"])
        if nsp.is_file():
            self.assertEqual(hashlib.sha256(nsp.read_bytes()).hexdigest(),
                             self.build["output"]["sha256"])



class UacU2CompletionReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("unicorn not installed")
        if not ELF.is_file():
            raise unittest.SkipTest(f"missing {ELF}")
        from replay_uac_u2_completion import (
            CASES, check, check_report, load_elf_sections as load,
            load_unicorn, run_case, run_report_case,
        )
        data, sections = load(ELF)
        uni = load_unicorn()
        cls.results = {
            name: run_case(uni, data, sections, name, CASES[name])
            for name in sorted(CASES)
        }
        cls.report = run_report_case(uni, data, sections)
        cls.check = staticmethod(check)
        cls.check_report = staticmethod(check_report)

    def test_all_cases_match_the_expected_completion(self):
        for name, result in self.results.items():
            self.assertEqual(self.check(result), [], name)

    def test_full_completion_unmaps_once_and_clears_the_queue(self):
        result = self.results["full_force"]
        self.assertEqual(result["transferred"], 3072)
        self.assertEqual(result["status"], 3)
        self.assertEqual(result["count"], 0)
        self.assertEqual(len(result["unmaps"]), 1)
        self.assertEqual(result["unmaps"][0]["iova"], "0x70000000")
        self.assertEqual(result["submits"], [])

    def test_partial_retry_resubmits_without_unmapping(self):
        result = self.results["partial_retry"]
        self.assertEqual(result["transferred"], 192)
        self.assertEqual(result["status"], 2)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["unmaps"], [])
        self.assertEqual(len(result["submits"]), 1)
        self.assertEqual(result["submits"][0]["w3"], "0xb40")

    def test_driver_report_has_one_completed_entry(self):
        self.assertEqual(self.check_report(self.report), [])
        self.assertEqual(self.report["count"], 1)
        self.assertEqual(self.report["id"], 388)
        self.assertEqual(self.report["requested"], 3072)
        self.assertEqual(self.report["transferred"], 3072)
        self.assertEqual(self.report["status"], 3)
        self.assertEqual(self.report["entry_status_after"], 0)


if __name__ == "__main__":
    unittest.main()
