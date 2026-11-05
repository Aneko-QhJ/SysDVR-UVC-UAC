"""v32 keep-ring recovery: resume the endpoint at the first pending set.

Code 23 (Missed Service) leaves the driver's ring untouched: 0x31274 only
halts the endpoint and completes one queued URB per event.  The v29t..v31
recovery made the app cancel, which resets the ring to base and pays the
cave's 32 ms lead again.

v32 keeps the ring.  iso_event counts code-23 events (one per completed URB)
at ring+0xc10; on the next post iso_enter calls resume_endpoint, which
rewrites the endpoint context's TR dequeue to base + cons_offset + count *
0x200, takes the DCS from that set's first TD, commits and clears the halt
through the driver's own 0x2ff90 tail (the 0x2feb0 frame), and clears the
counter.  The app skips its cancel under -DUAC_U2_KEEP_RING.

These tests decode the cave and check the app source, not the hardware.
"""
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
CAVE = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_resume.S"
APP = REPO / "source/uvc/uvc_device.c"
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")
CAVE_ADDR = 0x68D54
CAVE_LIMIT = 684
RESUME_TAIL = 0x2FF90

LINKER = (
    "SECTIONS { . = 0x68d54; .text : { *(.text.iso) } }\n"
    "doorbell_tail = 0x31c74; reject_original = 0x30394;\n"
    "event_original = 0x30f70; complete_original = 0x2a980; "
    "report_epilogue = 0x2cbe4; copy_original = 0x60e50;\n"
    "rearm_endpoint = 0x2feb0; resume_tail = 0x2ff90;\n"
)


def assemble():
    """Assemble the cave at its linker address; return (bytes, symbols)."""
    tmp = Path(tempfile.mkdtemp())
    (tmp / "inject.ld").write_text(LINKER)
    subprocess.run([str(TOOLCHAIN / "aarch64-none-elf-gcc"), "-c", str(CAVE),
                    "-o", str(tmp / "inject.o")], check=True)
    subprocess.run([str(TOOLCHAIN / "aarch64-none-elf-ld"), "-T",
                    str(tmp / "inject.ld"), str(tmp / "inject.o"),
                    "-o", str(tmp / "inject.elf")], check=True)
    subprocess.run([str(TOOLCHAIN / "aarch64-none-elf-objcopy"), "-O", "binary",
                    "--only-section=.text", str(tmp / "inject.elf"),
                    str(tmp / "inject.bin")], check=True)
    text = subprocess.check_output(
        [str(TOOLCHAIN / "aarch64-none-elf-objdump"), "-d",
         str(tmp / "inject.elf")], text=True)
    symbols = {}
    for line in subprocess.check_output(
            [str(TOOLCHAIN / "aarch64-none-elf-nm"), str(tmp / "inject.elf")],
            text=True).splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    return (tmp / "inject.bin").read_bytes(), symbols, text


def _word(data, address):
    return struct.unpack_from("<I", data, address - CAVE_ADDR)[0]


class UacU2KeepRingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CAVE.read_text()
        cls.app = APP.read_text()

    def test_event_counts_code23_only(self):
        body = self.text[self.text.index("iso_event:"):self.text.index("iso_end:")]
        self.assertIn("cmp w8, #23", body)
        self.assertIn("ring base", body)
        self.assertIn("[x10, #0xc10]", body)
        # code-23 must not be filtered out by the old "only errors" test
        self.assertNotIn("cmp w15, #1", body)

    def test_post_path_resumes_before_writing(self):
        body = self.text[self.text.index("pipe_nonempty:"):
                         self.text.index("installed:")]
        self.assertIn("[x10, #0xc10]", body)
        self.assertIn("bl resume_endpoint", body)
        # the resume must run before the TD write, i.e. before "installed:"
        self.assertLess(body.index("bl resume_endpoint"),
                        self.text.index("installed:"))

    def test_resume_rewrites_the_context_dequeue(self):
        body = self.text[self.text.index("resume_endpoint:"):
                         self.text.index("iso_end:")]
        # context array, dci stride, state=running
        self.assertIn("[x6, #0x50]", body)
        self.assertIn("[x1, #0x42]", body)
        self.assertIn("lsl w9, w9, #6", body)
        self.assertIn("orr w10, w10, #1", body)
        # dequeue = ring phys + (cons - base) + count * 0x200
        self.assertIn("[x1, #0x10]", body)
        self.assertIn("[x1, #0x20]", body)
        self.assertIn("[x1, #0x38]", body)
        self.assertIn("lsl w12, w12, #9", body)
        self.assertIn("sub x11, x11, #0xc00", body)
        # DCS comes from the first TD of that set, not a tracked cycle
        self.assertIn("ldr w14, [x14, #12]", body)
        self.assertIn("[x8, #8]", body)
        self.assertIn("[x8, #12]", body)
        # commit + unhalt are the driver's own tail
        self.assertIn("bl resume_tail", body)
        self.assertIn("str wzr, [x10, #0xc10]", body)

    def test_app_skips_the_cancel_behind_the_flag(self):
        self.assertIn("#if defined(UAC_U2_KEEP_RING)", self.app)
        self.assertIn("(void)halt_miss;", self.app)
        self.assertIn("#else", self.app)
        self.assertIn("usbDsEndpoint_Cancel(g_uacCtx.audioEndpointIn);",
                      self.app)

    def test_cave_fits_and_calls_the_tail(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        code, symbols, text = assemble()
        self.assertLessEqual(len(code), CAVE_LIMIT)
        self.assertIn("resume_endpoint", symbols)
        self.assertIn("iso_enter", symbols)
        self.assertIn("iso_event", symbols)
        # the resume routine must sit inside the 684-byte RX padding page
        self.assertGreaterEqual(symbols["resume_endpoint"], CAVE_ADDR)
        self.assertLess(symbols["resume_endpoint"] + 0x94,
                        CAVE_ADDR + CAVE_LIMIT + 1)
        self.assertIn("bl\t2ff90", text)


if __name__ == "__main__":
    unittest.main()
