"""v35 short re-arm lead after a miss.

v34 measured the host underrun tolerance: macOS sends SET_INTERFACE(0) only
after the stream has been silent for 42-75 ms.  The 32 ms first-set lead is
the largest single piece of that silence.  The driver's halt bit at
regs+0x50 is still set when the app has just cancelled the endpoint (a fresh
arm has it cleared by the previous 0x2feb0), so the cave's empty-ring path
uses 16 ms only for the post-miss post and keeps 32 ms everywhere else.
"""
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN = Path("/opt/devkitpro/devkitA64/bin")
CAVE = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_slead.S"
BASE = ROOT / "patches/iso_burst_uac84_dci9_pipe_quad_log.S"
CAVE_ADDR = 0x68D54
CAVE_LIMIT = 684

LINKER = (
    "SECTIONS { . = 0x68d54; .text : { *(.text.iso) } }\n"
    "doorbell_tail = 0x31c74; reject_original = 0x30394;\n"
    "event_original = 0x30f70; complete_original = 0x2a980; "
    "report_epilogue = 0x2cbe4; copy_original = 0x60e50;\n"
    "rearm_endpoint = 0x2feb0; resume_tail = 0x2ff90;\n"
)


def assemble(path):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "inject.ld").write_text(LINKER)
        subprocess.run([str(TOOLCHAIN / "aarch64-none-elf-gcc"), "-c", str(path),
                        "-o", str(tmp / "inject.o")], check=True)
        subprocess.run([str(TOOLCHAIN / "aarch64-none-elf-ld"), "-T",
                        str(tmp / "inject.ld"), str(tmp / "inject.o"),
                        "-o", str(tmp / "inject.elf")], check=True)
        subprocess.run([str(TOOLCHAIN / "aarch64-none-elf-objcopy"), "-O", "binary",
                        "--only-section=.text", str(tmp / "inject.elf"),
                        str(tmp / "inject.bin")], check=True)
        code = (tmp / "inject.bin").read_bytes()
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
        return code, symbols, text


class UacU2ShortLeadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CAVE.read_text()

    def test_source_chooses_the_lead_from_the_halt_bit(self):
        self.assertIn("[x9, #8]", self.text)     # register base
        self.assertIn("[x9, #0x50]", self.text)  # halt bits
        self.assertIn("mov w14, #32", self.text)
        self.assertIn("mov w14, #16", self.text)
        self.assertIn("add w9, w9, w14", self.text)
        self.assertNotIn("add w9, w9, #32", self.text)
        # the non-empty path must also provide a lead
        body = self.text[self.text.index("pipe_nonempty:"):]
        self.assertIn("mov w14, #32", body)

    def test_assembles_and_fits(self):
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        code, symbols, text = assemble(CAVE)
        self.assertLessEqual(len(code), CAVE_LIMIT)
        self.assertEqual(symbols["iso_enter"], CAVE_ADDR)
        # 0x68d98.. selects 32/16, 0x68e44 consumes it
        self.assertIn("mov\tw14, #0x20", text)
        self.assertIn("mov\tw14, #0x10", text)
        self.assertIn("ldr\tw10, [x9, #80]", text)
        self.assertIn("add\tw9, w9, w14", text)
        # the base cave uses the fixed 32 ms lead
        base, _, _ = assemble(BASE)
        self.assertEqual(len(code), len(base) + 52)

    def test_the_lead_value_is_consumed_before_the_packet_counter(self):
        # w14 is reused as the packet counter inside the packet loop; the lead
        # must be read before that reinitialisation (it is, at `add w9,w9,w14`)
        if not TOOLCHAIN.is_dir():
            self.skipTest("missing devkitA64 toolchain")
        _, _, text = assemble(CAVE)
        lead = text.index("add\tw9, w9, w14")
        packets = text.index("mov\tw14, #0x10", lead)
        self.assertLess(lead, packets)


if __name__ == "__main__":
    unittest.main()
