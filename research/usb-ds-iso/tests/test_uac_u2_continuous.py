"""Offline checks for the v15 sequential-burst candidate and the host re-arm.

The runtime payload is identical to v14 (only the app-side post count and the
host probe changed), so these checks pin the invariants that make the four
bursts safe: one ISO request pending at a time, a cancel on timeout, a 1..4
bound, and a 1 kHz phase that continues across buffers.  The host checks pin
the rolling re-arm window that keeps URBs queued for every cave TD.

No USB, SD, SDK or hardware access.
"""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
SOURCE = REPO / "source/uvc/uvc_device.c"
HOST = ROOT / "host/uac-raw-probe.c"
BINARY = ROOT / "host/uac-raw-probe"
WORK15 = ROOT / "private/analysis/UAC-u2-v15-continuous-20261101"
WORK16 = ROOT / "private/analysis/UAC-u2-v16-submit-state-20261101"
WORK17 = ROOT / "private/analysis/UAC-u2-v17-ring-advance-20261101"
WORK18 = ROOT / "private/analysis/UAC-u2-v18-event-mask-20261101"
WORK19 = ROOT / "private/analysis/UAC-u2-v19-event-code-20261101"
ASM19 = ROOT / "patches/iso_burst_uac84_dci9_eventcode.S"
WORK14 = ROOT / "private/analysis/UAC-u2-v14-dci9-20261031"
NM = Path("/opt/devkitpro/devkitA64/bin/aarch64-none-elf-nm")


def post_body(source):
    start = source.index("static void _postUacBurst(void)")
    return source[start:source.index("\n}\n", start)]


def buffer_symbol_size(elf):
    if not NM.is_file():
        return None
    out = subprocess.run([str(NM), "-S", str(elf)], capture_output=True,
                         text=True, check=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[3] == "g_u2BurstBuffers":
            return int(parts[1], 16)
    return None


class UacU2SequentialTrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.source = SOURCE.read_text()
        cls.body = post_body(cls.source)

    def test_burst_count_is_bounded_and_defaults_to_one(self):
        self.assertIn("#elif defined(UAC_U2_BURSTS)\n"
                      "#define UAC_U2_TRAIN_POSTS UAC_U2_BURSTS", self.source)
        self.assertIn("#else\n#define UAC_U2_TRAIN_POSTS 1\n#endif", self.source)
        self.assertIn("#if UAC_U2_TRAIN_POSTS < 1 || UAC_U2_TRAIN_POSTS > 4",
                      self.source)
        self.assertIn('must be 1..4: only one request may be pending', self.source)

    def test_exactly_one_request_is_submitted_at_a_time(self):
        self.assertEqual(self.body.count("usbDsEndpoint_PostBufferAsync("), 1)
        post = self.body.index("usbDsEndpoint_PostBufferAsync(")
        wait = self.body.index("eventWait(&g_uacCtx.audioEndpointIn->CompletionEvent")
        report = self.body.index("usbDsEndpoint_GetReportData(")
        self.assertLess(post, wait)
        self.assertLess(wait, report)
        # The loop only advances after a completion; the single break path
        # cancels before leaving, so no second request can be pending.
        self.assertIn("for (u32 n = 0; n < UAC_U2_TRAIN_POSTS; ++n)", self.body)
        self.assertEqual(self.body.count("usbDsEndpoint_Cancel("), 1)
        cancel = self.body.index("usbDsEndpoint_Cancel(")
        timeout = self.body.index("no completion within 100ms")
        leave = self.body.index("break;", timeout)
        self.assertLess(cancel, timeout)
        self.assertLess(timeout, leave)

    def test_waveform_phase_continues_across_bursts(self):
        self.assertIn("u32 patternFrame;", self.source)
        self.assertIn("const u32 base = g_uacCtx.patternFrame;", self.body)
        self.assertIn("const u32 frame = base + (i / 2);", self.body)
        self.assertIn("g_uacCtx.patternFrame = base + UAC_U2_BURST_BYTES / "
                      "sizeof(s16) / 2;", self.body)

    def test_train_reports_its_outcome(self):
        for token in ('LOG("UAC U2 train begin count=%u pattern=%u',
                      'LOG("UAC U2 train end posted=%u completed=%u pattern=%u',
                      'LOG("UAC U2 short seq=%u requested=%u transferred=%u'):
            self.assertIn(token, self.body)


class UacU2SubmitStateTests(unittest.TestCase):
    """v16: the second post must show whether the cave gate would accept."""

    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.source = SOURCE.read_text()
        cls.body = post_body(cls.source)

    def test_accept_state_is_logged_around_every_post(self):
        for tag in ('_uacLogSubmitState("pre", seq);',
                    '_uacLogSubmitState("post", seq);',
                    '_uacLogSubmitState("done", seq);',
                    '_uacLogSubmitState("timeout", seq);'):
            self.assertIn(tag, self.body)
        for token in ('UAC U2 state %s seq=%u word=0x%08x int=%u dci=%u cycle=%u speed=%u',
                      'ring=0x%llx prod=0x%llx cons=0x%llx copy=0x%llx empty=%u',
                      '(ring && prod == cons) ? 1u : 0u'):
            self.assertIn(token, self.source)

    def test_pre_state_is_read_before_the_submit(self):
        pre = self.body.index('_uacLogSubmitState("pre", seq);')
        submit = self.body.index("usbDsEndpoint_PostBufferAsync(")
        post = self.body.index('_uacLogSubmitState("post", seq);')
        complete = self.body.index("UAC U2 complete rc=0x%x")
        done = self.body.index('_uacLogSubmitState("done", seq);')
        self.assertLess(pre, submit)
        self.assertLess(submit, post)
        self.assertLess(complete, done)

    def test_ring_is_dumped_after_every_post(self):
        self.assertNotIn("if (n == 0) _uacLogRingState();", self.body)
        self.assertGreaterEqual(self.body.count("_uacLogRingState();"), 3)


class UacU2RingAdvanceTests(unittest.TestCase):
    """v17: move the cave window to the controller's next 0x200 slot."""

    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.source = SOURCE.read_text()
        cls.body = post_body(cls.source)

    def test_advance_moves_both_ring_pointers_one_slot(self):
        for token in ("#ifdef UAC_U2_RING_ADVANCE",
                      "#define UAC_U2_TD_BYTES 0x200ULL",
                      "static bool _uacAdvanceRing(u32 seq, u32 slots)",
                      "const u64 next = ring + (u64)slots * UAC_U2_TD_BYTES;",
                      "UAC_U2_EP_OBJ + 0x18",
                      "UAC_U2_EP_OBJ + 0x20",
                      "UAC U2 ring advance seq=%u slots=%u from=0x%llx"):
            self.assertIn(token, self.source)

    def test_advance_only_runs_for_later_bursts_before_the_pre_log(self):
        anchor = ('#ifdef UAC_U2_RING_ADVANCE\n'
                  '        if (seq > 1) _uacAdvanceRing(seq, seq - 1);\n'
                  '#endif\n'
                  '        _uacLogSubmitState("pre", seq);')
        self.assertIn(anchor, self.body)


class UacU2EventMaskTests(unittest.TestCase):
    """v18: read the per-DCI pending mask and dump the TD set at cons."""

    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file():
            raise unittest.SkipTest(f"missing {SOURCE}")
        cls.source = SOURCE.read_text()
        cls.body = post_body(cls.source)

    def test_state_line_reads_the_pending_mask(self):
        for token in ("#define UAC_U2_PENDING_MASK_OFFSET 0xFCA5CULL",
                      "mask=0x%08x bit9=%u ep10=0x%02x",
                      "ep.mask_ok ? ep.pending_mask : 0u",
                      "(ep.mask_ok ? (ep.pending_mask >> 9) & 1u : 0u)",
                      "ep.state[0x0A]",
                      "out->mask_ok = false;"):
            self.assertIn(token, self.source)

    def test_td_set_is_dumped_at_cons(self):
        for token in ("UAC U2 td@cons addr=0x%llx trb0 addr=0x%llx",
                      "svcReadDebugProcessMemory(td, h, cons, sizeof(td))"):
            self.assertIn(token, self.source)


class UacU2EventMaskBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK18 / "manifest.json").is_file():
            raise unittest.SkipTest(f"missing {WORK18}; run the offline build")
        cls.doc = json.loads((WORK18 / "manifest.json").read_text())

    def test_payload_is_still_the_v14_cave(self):
        if not (WORK14 / "manifest.json").is_file():
            self.skipTest(f"missing {WORK14}")
        old = json.loads((WORK14 / "manifest.json").read_text())
        self.assertEqual(self.doc["cave_sha256"], old["cave_sha256"])

    def test_build_is_v16_plus_the_mask_log(self):
        build = json.loads((WORK18 / "build-result.json").read_text())
        self.assertIn("-DUAC_U2_BURSTS=4", build["defines"])
        self.assertNotIn("-DUAC_U2_RING_ADVANCE", build["defines"])
        nsp = Path(build["output"]["nsp"])
        if nsp.is_file():
            import hashlib
            self.assertEqual(hashlib.sha256(nsp.read_bytes()).hexdigest(),
                             build["output"]["sha256"])
            elf = nsp.parent / "exefs.elf"
            if elf.is_file():
                self.assertIn(b"mask=0x%08x bit9=%u ep10=0x%02x",
                              elf.read_bytes())


class UacU2EventCodeTests(unittest.TestCase):
    """v19: record the last transfer-event completion code in mailbox +4."""

    @classmethod
    def setUpClass(cls):
        if not SOURCE.is_file() or not ASM19.is_file():
            raise unittest.SkipTest(f"missing {SOURCE} or {ASM19}")
        cls.source = SOURCE.read_text()
        cls.body = post_body(cls.source)
        cls.asm = ASM19.read_text()

    def test_cave_stores_the_completion_code(self):
        for token in ("ldr w6, [x1, #8]", "lsr w6, w6, #24",
                      "str w6, [x5, #4]", "v19: record the last transfer-event"):
            self.assertIn(token, self.asm)

    def test_ring_box_is_dumped_after_the_completion(self):
        wait = self.body.index(
            "eventWait(&g_uacCtx.audioEndpointIn->CompletionEvent")
        ring = self.body.index("_uacLogRingState();", wait)
        report = self.body.index("usbDsEndpoint_GetReportData(", wait)
        self.assertLess(ring, report)

    def test_box_fields_use_the_real_offsets(self):
        for token in ("event=0x%08x done=%u completed=0x%08x actual=%u first=0x%llx",
                      "memcpy(&first, (const u8 *)box + 0x18, sizeof(first))",
                      "box[4], box[5]"):
            self.assertIn(token, self.source)


class UacU2EventCodeBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK19 / "manifest.json").is_file():
            raise unittest.SkipTest(f"missing {WORK19}; run the offline build")
        cls.doc = json.loads((WORK19 / "manifest.json").read_text())

    def test_cave_is_the_v14_cave_plus_the_event_code_insert(self):
        if not (WORK14 / "manifest.json").is_file():
            self.skipTest(f"missing {WORK14}")
        old = json.loads((WORK14 / "manifest.json").read_text())
        c_old = bytes.fromhex(next(e["after"] for e in old["edits"]
                                   if e["address"] == "0x68d54"))
        c_new = bytes.fromhex(next(e["after"] for e in self.doc["edits"]
                                   if e["address"] == "0x68d54"))
        inserted = bytes.fromhex("260840b9c67c1853a60400b9")
        at = c_new.find(inserted)
        self.assertNotEqual(at, -1)
        self.assertEqual(len(c_new), len(c_old) + len(inserted))
        # Code before the insert keeps its encoding; code after it may differ
        # only in the relative branches that the 12-byte shift moved.
        self.assertEqual(c_new[:at], c_old[:at])
        self.assertEqual(len(c_new[at + len(inserted):]), len(c_old[at:]))

    def test_build_wires_the_new_cave(self):
        build = json.loads((WORK19 / "build-result.json").read_text())
        self.assertIn("-DUAC_U2_BURSTS=4", build["defines"])
        self.assertEqual(build["payload"]["cave_bytes"], 604)
        nsp = Path(build["output"]["nsp"])
        if nsp.is_file():
            import hashlib
            self.assertEqual(hashlib.sha256(nsp.read_bytes()).hexdigest(),
                             build["output"]["sha256"])
            elf = nsp.parent / "exefs.elf"
            if elf.is_file():
                self.assertIn(b"UAC U2 ring box magic=0x%08x event=0x%08x",
                              elf.read_bytes())


class UacU2RingAdvanceBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK17 / "manifest.json").is_file():
            raise unittest.SkipTest(f"missing {WORK17}; run the offline build")
        cls.doc = json.loads((WORK17 / "manifest.json").read_text())

    def test_payload_is_still_the_v14_cave(self):
        if not (WORK14 / "manifest.json").is_file():
            self.skipTest(f"missing {WORK14}")
        old = json.loads((WORK14 / "manifest.json").read_text())
        self.assertEqual(self.doc["cave_sha256"], old["cave_sha256"])

    def test_build_enables_the_advance_alongside_four_bursts(self):
        build = json.loads((WORK17 / "build-result.json").read_text())
        self.assertIn("-DUAC_U2_BURSTS=4", build["defines"])
        self.assertIn("-DUAC_U2_RING_ADVANCE", build["defines"])
        nsp = Path(build["output"]["nsp"])
        if nsp.is_file():
            import hashlib
            self.assertEqual(hashlib.sha256(nsp.read_bytes()).hexdigest(),
                             build["output"]["sha256"])
            elf = nsp.parent / "exefs.elf"
            if elf.is_file():
                self.assertIn(b"UAC U2 ring advance seq=%u slots=%u", elf.read_bytes())


class UacU2SubmitStateBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK16 / "manifest.json").is_file():
            raise unittest.SkipTest(f"missing {WORK16}; run the offline build")
        cls.doc = json.loads((WORK16 / "manifest.json").read_text())

    def test_payload_is_still_the_v14_cave(self):
        if not (WORK14 / "manifest.json").is_file():
            self.skipTest(f"missing {WORK14}")
        old = json.loads((WORK14 / "manifest.json").read_text())
        self.assertEqual(self.doc["cave_sha256"], old["cave_sha256"])
        self.assertEqual(self.doc["edit_count"], old["edit_count"])

    def test_build_keeps_four_bursts_and_adds_the_state_log(self):
        build = json.loads((WORK16 / "build-result.json").read_text())
        self.assertIn("-DUAC_U2_BURSTS=4", build["defines"])
        self.assertEqual(build["payload"]["cave_sha256"],
                         self.doc["cave_sha256"])
        nsp = Path(build["output"]["nsp"])
        if nsp.is_file():
            import hashlib
            self.assertEqual(hashlib.sha256(nsp.read_bytes()).hexdigest(),
                             build["output"]["sha256"])
            elf = nsp.parent / "exefs.elf"
            if elf.is_file():
                data = elf.read_bytes()
                self.assertIn(b"UAC U2 state %s seq=%u word=0x%08x", data)
                self.assertIn(b"empty=%u", data)


class UacU2ContinuousBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (WORK15 / "manifest.json").is_file():
            raise unittest.SkipTest(f"missing {WORK15}; run the offline build")
        cls.doc = json.loads((WORK15 / "manifest.json").read_text())

    def test_payload_is_unchanged_from_v14(self):
        if not (WORK14 / "manifest.json").is_file():
            self.skipTest(f"missing {WORK14}")
        old = json.loads((WORK14 / "manifest.json").read_text())
        self.assertEqual(self.doc["cave_sha256"], old["cave_sha256"])
        self.assertEqual(self.doc["cave_bytes"], old["cave_bytes"])
        self.assertEqual([(e["address"], e["after"]) for e in self.doc["edits"]],
                         [(e["address"], e["after"]) for e in old["edits"]])

    def test_build_selects_four_sequential_bursts(self):
        build = json.loads((WORK15 / "build-result.json").read_text())
        self.assertIn("-DUAC_U2_BURSTS=4", build["defines"])
        self.assertEqual(build["payload"]["cave_sha256"],
                         self.doc["cave_sha256"])
        nsp = Path(build["output"]["nsp"])
        if nsp.is_file():
            import hashlib
            self.assertEqual(hashlib.sha256(nsp.read_bytes()).hexdigest(),
                             build["output"]["sha256"])

    def test_four_ring_buffers_are_linked(self):
        build = json.loads((WORK15 / "build-result.json").read_text())
        elf = Path(build["output"]["nsp"]).parent / "exefs.elf"
        if not elf.is_file():
            self.skipTest(f"missing {elf}")
        self.assertEqual(buffer_symbol_size(elf), 4 * 0x1000)
        old_elf = (WORK14 / "build/outputs/exefs.elf")
        if old_elf.is_file():
            self.assertEqual(buffer_symbol_size(old_elf), 1 * 0x1000)


class UacRawProbeRearmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HOST.is_file():
            raise unittest.SkipTest(f"missing {HOST}")
        cls.text = HOST.read_text()

    def test_options_and_bounds(self):
        for token in ("--rearm", "--max-urbs", "max-urbs must be 1..%d",
                      "max-urbs must be >= transfers (window)",
                      "rearm window=%u max_urbs=%u packets=%u timeout_ms=%d",
                      "urb[%u] t=%llums status=%d valid=%u bad=%u bytes=%u",
                      "resubmit[%u]=%d"):
            self.assertIn(token, self.text)

    def test_completions_are_replaced_to_keep_the_window_full(self):
        for token in ("unsigned in_flight = submitted;",
                      "if (!states[i].done) continue;",
                      "states[i].done = 0;",
                      "if (in_flight > 0) --in_flight;",
                      "submit_iso(t, h, endpoint, bufs[i], packets,",
                      "++in_flight;",
                      "unsigned remaining = 0;",
                      'printf("cancel remaining=%u/%u\\n", remaining, submitted);'):
            self.assertIn(token, self.text)

    def test_binary_rejects_bad_rearm_bounds(self):
        if not BINARY.is_file():
            self.skipTest(f"missing {BINARY}")
        for args, text in (
                (("--max-urbs", "0"), "max-urbs must be 1.."),
                (("--rearm", "--transfers", "8", "--max-urbs", "4"),
                 "max-urbs must be >= transfers")):
            result = subprocess.run([str(BINARY), *args], capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn(text, result.stderr)


if __name__ == "__main__":
    unittest.main()
