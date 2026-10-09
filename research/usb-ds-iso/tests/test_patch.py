"""Execute the real patched AArch64 binary, rather than a second ring model.

Requires the locally extracted module, built variants and Unicorn 2.1.4.
"""
import json
import struct
import sys
import unittest
import subprocess
import os
import tempfile
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm64_const import *

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = Path(os.environ.get('ISO_PATCH_PACKAGES', ROOT/'private/packages'))
sys.path.insert(0, str(ROOT / 'tools'))
from build_patch import validate_module, read_mapped, ips32, branch_eq, CAVE
from nso2elf import Nso

CTRL, RING, STACK, CTX, MMIO, MANAGER = (0x1000000, 0x2000000, 0x3000000, 0x4000000, 0x5000000, 0x6000000)
DMA, RING_DMA, EXIT, ENTRY = 0x8000000, 0x9000000, 0x999000, CTRL + 0x22270


class Machine:
    def __init__(self, variant):
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        u = self.uc
        self.meta = json.loads((PACKAGES / variant / 'manifest.json').read_text())
        self.symbols = self.meta['symbols']
        self.raw = (ROOT / 'private/module/exefs/main').read_bytes()
        nso = Nso(self.raw)
        u.mem_map(0, 0x370000)
        for s in nso.sections: u.mem_write(s['vaddr'], s['content'])
        for e in self.meta['edits']: u.mem_write(int(e['address'], 16), bytes.fromhex(e['after']))
        for p, size in [(CTRL, 0x30000), (RING, 0x1000), (STACK, 0x10000), (CTX, 0x1000), (MMIO, 0x1000), (MANAGER, 0x1000)]:
            u.mem_map(p, size)
        u.reg_write(UC_ARM64_REG_CPACR_EL1, 3 << 20)
        u.reg_write(UC_ARM64_REG_SP, STACK + 0xf000)
        u.reg_write(UC_ARM64_REG_X30, EXIT)
        self.write(CTRL + 0x22008, '<Q', MMIO)
        self.write(CTRL + 0x22050, '<Q', CTX)
        self.write(CTRL + 0x229b8, '<Q', MANAGER)
        self.write(CTRL + 0x22a58, '<I', 3)
        u.mem_write(ENTRY + 2, bytes([0x83, 1, 192, 0, 4, 0]))
        self.write(ENTRY + 4, '<H', self.meta.get('mps',192))
        self.write(ENTRY + 6, '<B', self.meta.get('interval',4))
        for off in (0x10, 0x18, 0x20, 0x30): self.write(ENTRY + off, '<Q', RING)
        self.write(ENTRY + 0x28, '<Q', RING + 0xff0)
        self.write(ENTRY + 0x38, '<Q', RING_DMA)
        u.mem_write(ENTRY + 0x40, bytes([1, 0, 7]))
        self.write(RING + 0xff0, '<QII', RING_DMA, 0, 0x1802)
        self.write(CTX + 0x1c0, '<IIII', 0x40001, 0xc0002e, RING_DMA | 1, 0)
        self.write(MANAGER + 0x60, '<Q', CTRL)
        u.mem_write(MANAGER + 0x70, bytes([0x83]))

    def write(self, address, fmt, *values): self.uc.mem_write(address, struct.pack(fmt, *values))
    def read(self, address, fmt): return struct.unpack(fmt, self.uc.mem_read(address, struct.calcsize(fmt)))
    def submit(self, size=192, endpoint=0x83, dma=DMA):
        u = self.uc
        for reg, value in [(UC_ARM64_REG_X0, CTRL), (UC_ARM64_REG_X1, endpoint), (UC_ARM64_REG_X2, dma), (UC_ARM64_REG_X3, size), (UC_ARM64_REG_X30, EXIT)]: u.reg_write(reg, value)
        u.emu_start(0x302e0, EXIT, count=10000)
        assert u.reg_read(UC_ARM64_REG_PC) == EXIT
        return u.reg_read(UC_ARM64_REG_X0)

    def event(self, pointer, ed, cc=1, count=192, endpoint=7):
        u = self.uc
        event = CTX + 0x800
        self.write(event, '<QII', pointer, (cc << 24) | count, (endpoint << 16) | (32 << 10) | (4 if ed else 0) | 1)
        for r, v in [(UC_ARM64_REG_X0, CTRL), (UC_ARM64_REG_X1, event), (UC_ARM64_REG_X30, EXIT)]: u.reg_write(r, v)
        calls = []
        def stop(uc, address, size, data):
            if address in (0x2a980, 0x30f70):
                calls.append((address, [uc.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5)]))
                uc.emu_stop()
        hook = u.hook_add(UC_HOOK_CODE, stop)
        u.emu_start(self.symbols['iso_event'], EXIT, count=10000)
        u.hook_del(hook)
        return calls


class ProducerTests(unittest.TestCase):
    def test_receiver_requires_packet_evidence_and_saves_raw_buffer(self):
        if sys.platform != 'darwin': self.skipTest('native macOS diagnostic receiver')
        binary = ROOT/'private/receiver-diagnostics-test'
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                        '-I/opt/homebrew/include/libusb-1.0',str(ROOT/'tests/receiver_diagnostics_test.c'),
                        '-L/opt/homebrew/lib','-lusb-1.0','-o',str(binary)],check=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'private') as directory:
            subprocess.run([str(binary),str(Path(directory)/'callback.jsonl')],check=True)

    def test_runtime_installer_preflight_and_rollback(self):
        binary = ROOT / 'private/runtime-patch-test'
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-I'+str(ROOT/'private'), str(ROOT/'tests/runtime_patch_test.c'),
                        '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)

    def test_report_marker_before_submit(self):
        m = Machine('A')
        report = CTX + 0x800
        m.uc.reg_write(UC_ARM64_REG_X19, MANAGER)
        m.uc.reg_write(UC_ARM64_REG_X20, report)
        m.uc.emu_start(m.symbols['iso_report'], 0x2cbe4, count=1000)
        self.assertEqual(m.read(report + 16, '<I')[0], 0xd1)
        self.assertEqual(m.read(report + 128, '<I')[0], 0)

    def test_frame_probe_reads_device_mmio_only_before_td(self):
        m = Machine('B')
        if m.meta.get('frame_lead', 0): self.skipTest('frame probe is preserved in A6; explicit B uses production-time MMIO read')
        report = CTX + 0x800
        def poll():
            m.uc.reg_write(UC_ARM64_REG_X19, MANAGER)
            m.uc.reg_write(UC_ARM64_REG_X20, report)
            m.uc.emu_start(m.symbols['iso_report'], 0x2cbe4, count=1000)
        for counter in (0x3ffe, 0x17):
            m.write(MMIO + 0x48, '<I', counter)
            m.write(MMIO, '<I', 0x20000)
            m.write(MMIO + 0x3c, '<I', 0x1234)
            poll()
            self.assertEqual(m.read(report + 16, '<I')[0], 0xd1)
            self.assertEqual(m.read(report + 32, '<III'), (counter, 0x20000, 0x1234))
            self.assertEqual(m.read(report + 48, '<Q')[0], MMIO)
        self.assertEqual(m.submit(), 0)
        poll()
        self.assertEqual(m.read(report + 16, '<I')[0], 0x314f5349)
        self.assertEqual(m.read(report + 32, '<IIII'), m.read(CTX + 0x1c0, '<IIII'))
        self.assertEqual(m.read(report + 48, '<Q')[0], RING_DMA)

    def test_first_cycle_is_published_after_ed(self):
        m = Machine('C')
        writes = []
        def record(uc, access, address, size, value, data):
            if address in (RING + 12, RING + 16 + 12): writes.append((address, value))
        h = m.uc.hook_add(UC_HOOK_MEM_WRITE, record)
        m.submit(); m.uc.hook_del(h)
        control = (m.meta['frame_lead'] << 20 if m.meta.get('frame_lead') else 0x80000000) | 0x1430
        self.assertEqual(writes, [(RING + 12, control), (RING + 28, 0x1c21), (RING + 12, control | 1)])

    def test_superspeed_companion_entry_layout(self):
        m = Machine('A')
        m.write(CTRL + 0x22a58, '<I', 4)
        m.uc.mem_write(ENTRY + 7, bytes([6, 0x30, 0, 0, 192, 0]))
        self.assertEqual(m.submit(), 0)
        m = Machine('A')
        m.write(CTRL + 0x22a58, '<I', 4)
        m.uc.mem_write(ENTRY + 7, bytes([6, 0x30, 0, 0, 64, 0]))
        self.assertEqual(m.submit(), 0x1908c)

    def test_mps_experiment_keeps_one_192_byte_packet(self):
        for variant in 'ABC':
            m = Machine(variant)
            self.assertEqual(m.submit(), 0)
            self.assertEqual(m.read(RING + 8, '<I')[0],192)
            control = m.read(RING + 12, '<I')[0]
            self.assertEqual((control >> 7) & 3,0)
            self.assertEqual((control >> 16) & 15,0)
            wrong = Machine(variant)
            wrong.write(ENTRY + 4,'<H',256 if wrong.meta.get('mps',192)==192 else 192)
            before = wrong.uc.mem_read(RING,4096)
            self.assertEqual(wrong.submit(),0x1908c)
            self.assertEqual(wrong.uc.mem_read(RING,4096),before)

    def test_matrix_and_publication(self):
        for variant in 'ABC':
            with self.subTest(variant=variant):
                m = Machine(variant)
                self.assertEqual(m.submit(), 0)
                iso = m.read(RING, '<QII')
                self.assertEqual(iso[0], DMA)
                self.assertEqual(iso[1], 192)
                expected = {'A': 0x80001411, 'B': 0x80001421, 'C': 0x80001431}[variant]
                if m.meta.get('frame_lead', 0): expected = (expected & ~0x80000000) | m.meta['frame_lead'] << 20
                self.assertEqual(iso[2], expected)
                self.assertEqual(m.read(MMIO + 4, '<I')[0], 7 << 8)
                next_pointer = RING + (16 if variant == 'B' else 32)
                self.assertEqual(m.read(ENTRY + 0x18, '<Q')[0], next_pointer)
                self.assertEqual(m.read(RING + 0xf80, '<IIII'), (0x314f5349, 'ABC'.index(variant)+1, 0, 0))
                if variant != 'B': self.assertEqual(m.read(RING + 16, '<QII'), (RING + 16, 0, 0x1c21))
                self.assertEqual(m.uc.mem_read(RING + 0xfb0, 16), m.uc.mem_read(RING, 16))

    def test_explicit_frame_reads_live_counter_and_wraps(self):
        lead = Machine('B').meta.get('frame_lead', 0)
        if not lead: self.skipTest('SIA variant has no explicit frame scheduling')
        for speed in (3, 4):
            for raw in (0, 7, 8, 0x3ff8, 0x3fff):
                m = Machine('B')
                m.write(CTRL + 0x22a58, '<I', speed)
                if speed == 4: m.uc.mem_write(ENTRY + 7, bytes([6,0x30,0,0,192,0]))
                m.write(MMIO + 0x48, '<I', raw)
                self.assertEqual(m.submit(), 0)
                control = m.read(RING + 12, '<I')[0]
                self.assertEqual(control, ((((raw >> 3) + lead) & 0x7ff) << 20) | 0x1421)
                self.assertEqual(m.read(MMIO + 0x48, '<I')[0], raw)

    def test_wrap_first_and_last_trb(self):
        for variant in 'ABC':
            for slot in (245, 246):
                with self.subTest(variant=variant, slot=slot):
                    m = Machine(variant)
                    cursor = RING + slot * 16
                    m.write(ENTRY + 0x18, '<Q', cursor)
                    m.write(ENTRY + 0x20, '<Q', cursor)
                    self.assertEqual(m.submit(), 0)
                    n = 1 if variant == 'B' else 2
                    wrapped = slot + n >= 247
                    expected = RING + ((slot + n) % 247) * 16
                    self.assertEqual(m.read(ENTRY + 0x18, '<Q')[0], expected)
                    self.assertEqual(m.read(ENTRY + 0x40, '<B')[0], 0 if wrapped else 1)
                    if slot == 246 and variant != 'B':
                        self.assertEqual(m.read(RING, '<QII'), (RING, 0, 0x1c20))
                        self.assertEqual(m.read(RING + 0xf70 + 12, '<I')[0], 0x1813)
                    elif wrapped:
                        self.assertEqual(m.read(RING + 0xf70 + 12, '<I')[0], 0x1803)

    def test_reject_unsupported_and_busy_without_writing_ring(self):
        changes = [('size', 193), ('size', 0), ('dma', 0), ('speed', 2), ('mps', 64), ('burst', 1), ('busy', 1)]
        for what, value in changes:
            with self.subTest(what=what, value=value):
                m = Machine('A')
                if what == 'speed': m.write(CTRL + 0x22a58, '<I', value)
                if what == 'mps': m.write(ENTRY + 4, '<H', value)
                if what == 'burst': m.write(ENTRY + 9, '<B', value)
                if what == 'busy': m.write(ENTRY + 0x20, '<Q', RING + 16)
                before = m.uc.mem_read(RING, 4096)
                self.assertEqual(m.submit(value if what == 'size' else 192,
                                          dma=value if what == 'dma' else DMA), 0x1908c)
                self.assertEqual(m.uc.mem_read(RING, 4096), before)

    def test_bulk_route_is_unchanged(self):
        m = Machine('A')
        m.uc.mem_write(ENTRY + 3, b'\x02')
        self.assertEqual(m.submit(), 0)
        self.assertEqual(m.read(RING + 12, '<I')[0] >> 10 & 63, 1)
        self.assertEqual(m.read(RING + 16 + 12, '<I')[0] >> 10 & 63, 7)
        self.assertEqual(m.read(ENTRY + 0x28, '<Q')[0], RING + 0xff0)


class CompletionTests(unittest.TestCase):
    def test_observed_ed_count_passes_once_to_urb_completion(self):
        for variant in 'AC':
            with self.subTest(variant=variant):
                m = Machine(variant); self.assertEqual(m.submit(), 0)
                if variant == 'C': self.assertEqual(m.event(RING_DMA, False, count=0), [])
                calls = m.event(RING + 16, True, count=192)
                retain = m.meta.get('retain_success', False)
                self.assertEqual(calls, [] if retain else [(0x2a980, [MANAGER, 0x83, 0, 1, 192, 1])])
                self.assertEqual(m.event(RING + 16, True, count=192), [])
                self.assertEqual(m.event(0, False, cc=14, count=0), [])
                self.assertEqual(m.read(ENTRY + 0x20, '<Q'), (RING,) if retain else m.read(ENTRY + 0x18, '<Q'))

    def test_terminal_and_duplicate_matrix(self):
        for variant in 'ABC':
            with self.subTest(variant=variant):
                m = Machine(variant); m.submit()
                if variant == 'B': self.assertEqual(m.event(0, True), [])
                if variant == 'C': self.assertEqual(m.event(RING_DMA, False), [])
                ptr, ed = (RING_DMA, False) if variant == 'B' else (RING + 16, True)
                calls = m.event(ptr, ed, count=0)
                retain = m.meta.get('retain_success', False)
                self.assertEqual(calls, [] if retain else [(0x2a980, [MANAGER, 0x83, 0, 1, 0, 1])])
                self.assertEqual(m.read(ENTRY + 0x20, '<Q'), (RING,) if retain else m.read(ENTRY + 0x18, '<Q'))
                self.assertEqual(m.event(ptr, ed), [])
                self.assertEqual(m.event(ptr, ed), [])
                self.assertEqual(m.read(RING + 0xf80 + 12, '<I')[0], 0x40000001 if retain else 1)
                self.assertGreaterEqual(m.read(RING + 0xf80 + 8, '<I')[0], 3)
                self.assertEqual(m.read(RING + 0xff0, '<QII')[0], RING_DMA) # bounded log

    def test_observed_success_does_not_release_or_allow_repost(self):
        m = Machine('B')
        if not m.meta.get('retain_success', False): self.skipTest('normal terminal completion variant')
        self.assertEqual(m.submit(), 0)
        self.assertEqual(m.event(RING_DMA, False, count=0), [])
        self.assertEqual(m.read(RING + 0xf8c, '<I')[0], 0x40000001)
        self.assertEqual(m.read(ENTRY + 0x20, '<Q')[0], RING)
        before = bytes(m.uc.mem_read(RING, 4096))
        self.assertEqual(m.submit(), 0x1908c)
        self.assertEqual(bytes(m.uc.mem_read(RING, 4096)), before)
        self.assertEqual(m.event(0, False, cc=14, count=0), [])
        self.assertEqual(m.read(RING + 0xf8c, '<I')[0], 0x40000001)

    def test_error_foreign_tag_and_count_retains_ownership(self):
        for cc, count, ptr in [(13, 192, RING + 16), (1, 193, RING + 16), (1, 192, RING + 48)]:
            m = Machine('A'); m.submit()
            self.assertEqual(m.event(ptr, True, cc, count), [])
            self.assertEqual(m.read(ENTRY + 0x20, '<Q')[0], RING)
            expected = 0 if ptr != RING + 16 else (0x80000000 | cc)
            self.assertEqual(m.read(RING + 0xf80 + 12, '<I')[0], expected)

    def test_iso_error_cannot_be_masked_by_successful_ed(self):
        for variant in 'ABC':
            m = Machine(variant); m.submit()
            self.assertEqual(m.event(RING_DMA, False, cc=23), [])
            self.assertEqual(m.event(RING + 16, True, cc=1, count=0), [])
            self.assertEqual(m.read(RING + 0xf80 + 12, '<I')[0], 0x80000017)
            self.assertEqual(m.read(ENTRY + 0x20, '<Q')[0], RING)
            self.assertEqual(m.event(RING_DMA + 32, False, cc=14), [])
            self.assertEqual(m.read(RING + 0xfc0, '<QII'),
                             (RING_DMA + 32, (14 << 24) | 192, (7 << 16) | (32 << 10) | 1))

    def test_nonexperiment_event_falls_through(self):
        m = Machine('A'); m.submit()
        self.assertEqual(m.event(RING_DMA, False, endpoint=5)[0][0], 0x30f70)

    def test_report_preserves_real_record_and_count(self):
        m = Machine('C'); m.submit(); m.event(RING_DMA, False)
        report = CTX + 0x900
        first = bytes(range(16))
        for count in (0, 1, 2):
            m.uc.mem_write(report, first + bytes(112) + struct.pack('<I', count))
            m.uc.reg_write(UC_ARM64_REG_X19, MANAGER)
            m.uc.reg_write(UC_ARM64_REG_X20, report)
            m.uc.emu_start(m.symbols['iso_report'], 0x2cbe4, count=1000)
            self.assertEqual(m.uc.mem_read(report, 16), first)
            self.assertEqual(m.read(report + 128, '<I')[0], count)
            expected = m.uc.mem_read(RING + 0xf80, 112) if count <= 1 else bytes(112)
            self.assertEqual(m.uc.mem_read(report + 16, 112), expected)


class PackageTests(unittest.TestCase):
    def test_descriptor_assembly_above_255_and_get_descriptor(self):
        # Execute the restored assembler and reader, including u16 offsets.
        m = Machine('A'); u = m.uc
        cd = 0x7000000
        u.mem_map(cd, 0x2000)
        u.mem_write(cd + 0x5e, bytes([9, 2, 0, 0, 0, 1, 0, 0x80, 0x32]))
        u.mem_write(cd + 0x67, bytes([1, 1, 1, 0]))
        sizes = [80, 128, 64]
        for i, size in enumerate(sizes):
            m.write(cd + 0xfa4 + i*4, '<I', size)
            u.mem_write(cd + 0xb94 + i*128, bytes([0xa1+i])*size)
        def utilities(uc, address, size, data):
            if address in (0xba60, 0xbab0, 0x60e40):
                if address == 0x60e40:
                    dest, src, n = [uc.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
                    uc.mem_write(dest, bytes(uc.mem_read(src, n)))
                uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_X30))
        hook = u.hook_add(UC_HOOK_CODE, utilities)
        u.reg_write(UC_ARM64_REG_X0, cd); u.reg_write(UC_ARM64_REG_X1, 3); u.reg_write(UC_ARM64_REG_X30, EXIT)
        u.emu_start(0x2bee0, EXIT, count=10000)
        self.assertEqual(u.reg_read(UC_ARM64_REG_PC), EXIT)
        self.assertEqual(m.read(cd + 0x1454, '<H')[0], 281)
        self.assertEqual(m.read(cd + 0x1056, '<H')[0], 281)
        self.assertEqual(u.mem_read(cd + 0x1054 + 9, 272), bytes([0xa1])*80 + bytes([0xa2])*128 + bytes([0xa3])*64)
        dest = CTX + 0x800
        for r, v in [(UC_ARM64_REG_X0, cd), (UC_ARM64_REG_X1, dest), (UC_ARM64_REG_X2, 0), (UC_ARM64_REG_X3, 1024), (UC_ARM64_REG_X30, EXIT)]: u.reg_write(r, v)
        u.emu_start(0x2bd80, EXIT, count=10000)
        u.hook_del(hook)
        self.assertEqual(u.reg_read(UC_ARM64_REG_X0), 281)
        self.assertEqual(u.mem_read(dest, 281), u.mem_read(cd + 0x1054, 281))

    def test_id_and_hash_mismatch(self):
        raw = bytearray((ROOT / 'private/module/exefs/main').read_bytes())
        self.assertTrue(validate_module(raw))
        raw[0x40] ^= 1
        with self.assertRaisesRegex(ValueError, 'Build ID'): validate_module(raw)
        raw[0x40] ^= 1; raw[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'hash'): validate_module(raw)

    def test_protected_offset_and_overlap(self):
        patch = ips32([(0x30364, b'1234')])
        self.assertEqual(struct.unpack_from('>I', patch, 5)[0], 0x30464)
        with self.assertRaises(ValueError): ips32([(0x10, b'1234'), (0x12, b'abc')])
        self.assertEqual(struct.unpack('<I', branch_eq(0x30364, CAVE))[0] & 15, 0)


if __name__ == '__main__': unittest.main()
