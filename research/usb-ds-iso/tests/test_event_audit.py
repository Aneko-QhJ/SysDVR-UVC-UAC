"""Execute ISO3 machine code, including ignored/late events and reused slots."""
import unittest
from unicorn import UC_HOOK_MEM_WRITE
from test_patch import Machine, RING, RING_DMA, ENTRY, MMIO, MANAGER, DMA, CTRL, CTX
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_X29, UC_ARM64_REG_X30, UC_ARM64_REG_SP


class EventAuditTests(unittest.TestCase):
    def setUp(self):
        self.m = Machine('A')
        if self.m.meta.get('diagnostics_magic') != 'ISO3':
            self.skipTest('requires --event-audit package')

    def machine(self, slot=0):
        m = Machine('A')
        for off in (0x18, 0x20):
            m.write(ENTRY + off, '<Q', RING + slot * 16)
        self.assertEqual(m.submit(3072), 0)
        return m

    def ptr(self, slot, packet, ed=True):
        return (RING if ed else RING_DMA) + ((slot + 2 * packet + int(ed)) % 247) * 16

    def snapshot(self, m, offset):
        return bytes(m.uc.mem_read(RING + 0xf80 + offset, 20))

    def expect_event(self, m, offset, ptr, ed, mfi, cc=1, count=192):
        self.assertEqual(m.read(RING + 0xf80 + offset, '<QIII'),
                         (ptr, (cc << 24) | count, (7 << 16) | (32 << 10) | int(ed) * 4 | 1, mfi))

    def test_td_success_and_post_terminal_are_distinct_and_first_only(self):
        for slot in (0, 215, 216, 217, 230, 246):
            m = self.machine(slot)
            for p in range(16):
                m.write(MMIO + 0x48, '<I', (0x3ffc + 8 * p) & 0x3fff)
                expected = [] if p != 15 else [(0x2a980, [MANAGER, 0x83, 0, 1, 3072, 1])]
                self.assertEqual(m.event(self.ptr(slot, p), True), expected)
                if p < 2:
                    self.expect_event(m, 32 + p * 20, self.ptr(slot, p), True,
                                      (0x3ffc + 8 * p) & 0x3fff)
            first_two = bytes(m.uc.mem_read(RING + 0xfa0, 40))
            m.write(MMIO + 0x48, '<I', 42)
            self.assertEqual(m.event(0, False, cc=14, count=0), [])
            self.expect_event(m, 92, 0, False, 42, cc=14, count=0)
            late = self.snapshot(m, 92)
            m.event(self.ptr(slot, 1), True)
            self.assertEqual(self.snapshot(m, 92), late)
            self.assertEqual(bytes(m.uc.mem_read(RING + 0xfa0, 40)), first_two)
            self.assertEqual(m.read(RING + 0xf8c, '<III'), (1, 0xffff, 3072))

    def test_each_filtered_class_records_raw_without_releasing_dma(self):
        slot = 240
        candidates = [(0, False, 14, 0), (RING + 0xf70, True, 1, 192),
                      (RING + 100 * 16, True, 23, 0),
                      (self.ptr(slot, 0) + 1, True, 1, 192),
                      (self.ptr(slot, 0, False), True, 1, 192),
                      (self.ptr(slot, 0), False, 1, 192),
                      (self.ptr(slot, 0, False), False, 1, 192)]
        for ptr, ed, cc, count in candidates:
            m = self.machine(slot)
            m.write(MMIO + 0x48, '<I', 121)
            self.assertEqual(m.event(ptr, ed, cc=cc, count=count), [])
            self.expect_event(m, 72, ptr, ed, 121, cc, count)
            before = self.snapshot(m, 72)
            m.event(0, False, cc=14, count=0)
            self.assertEqual(self.snapshot(m, 72), before)
            self.assertEqual(m.read(RING + 0xf8c, '<III'), (0, 0, 0))
            self.assertEqual(m.read(ENTRY + 0x20, '<Q')[0], RING + slot * 16)
            self.assertEqual(m.submit(3072), 0x1908c)

    def test_error_replaces_td1_and_post_terminal_cannot_erase_it(self):
        for slot in (0, 230, 246):
            for packet in range(2, 16):
                for ed, cc, count in ((False, 23, 0), (True, 13, 192), (True, 1, 191), (True, 1, 193)):
                    m = self.machine(slot)
                    for p in (0, 1): m.event(self.ptr(slot, p), True)
                    td0 = self.snapshot(m, 32)
                    m.write(MMIO + 0x48, '<I', 0x3ffd)
                    ptr = self.ptr(slot, packet, ed)
                    self.assertEqual(m.event(ptr, ed, cc=cc, count=count), [])
                    self.expect_event(m, 52, ptr, ed, 0x3ffd, cc, count)
                    error = self.snapshot(m, 52)
                    m.write(MMIO + 0x48, '<I', 7)
                    m.event(0, False, cc=14, count=0)
                    self.expect_event(m, 92, 0, False, 7, 14, 0)
                    for p in range(16): self.assertEqual(m.event(self.ptr(slot, p), True), [])
                    self.assertEqual(self.snapshot(m, 32), td0)
                    self.assertEqual(self.snapshot(m, 52), error)
                    self.assertEqual(m.read(RING + 0xf84, '<I')[0], packet * 32 + int(ed) * 16)
                    self.assertEqual(m.read(RING + 0xf8c, '<III'), (0x80000000 | cc, 3, 384))
                    self.assertEqual(m.read(ENTRY + 0x20, '<Q')[0], RING + slot * 16)
                    self.assertEqual(m.submit(3072), 0x1908c)

    def test_new_submission_invalidates_all_previous_records(self):
        m = self.machine()
        for p in range(16): m.event(self.ptr(0, p), True)
        m.event(0, False, cc=14)
        # Fill every byte with a sentinel after completion. New submission
        # must reset header and all four control validity fields.
        m.uc.mem_write(RING + 0xf80, b'\xff' * 128)
        self.assertEqual(m.submit(3072), 0)
        self.assertEqual(m.read(RING + 0xf80, '<IIIIIIQ'),
                         (0x334f5349, 0, (32 << 20) | 0x1411, 0, 0, 0, RING + 32 * 16))
        for off in (32, 52, 72, 92):
            self.assertEqual(m.read(RING + 0xf80 + off + 12, '<I')[0], 0)

    def test_diagnostic_writes_are_bounded_and_other_endpoints_use_original(self):
        m = self.machine()
        writes = []
        hook = m.uc.hook_add(UC_HOOK_MEM_WRITE, lambda u, a, address, size, value, _: writes.append((address, size)))
        m.event(0, False, cc=14)
        m.event(self.ptr(0, 0), True)
        m.event(self.ptr(0, 3), True, cc=13)
        m.event(0, False, cc=14)
        m.uc.hook_del(hook)
        self.assertTrue(writes)
        self.assertTrue(all(RING + 0xf80 <= a and a + n <= RING + 0xff0 for a, n in writes))
        before = bytes(m.uc.mem_read(RING, 4096))
        self.assertEqual(m.event(0, False, endpoint=5)[0][0], 0x30f70)
        self.assertEqual(bytes(m.uc.mem_read(RING, 4096)), before)
        m.write(ENTRY + 0x10, '<Q', 0)
        self.assertEqual(m.event(0, False)[0][0], 0x30f70)

    def test_combined_validation_still_rejects_every_bad_input(self):
        changes = [(2, '<B', 0x82), (3, '<B', 5), (4, '<H', 192),
                   (6, '<B', 4 if Machine('A').meta.get('interval',4) == 1 else 1), (0x20, '<Q', RING + 16)]
        for offset, fmt, value in changes:
            m = Machine('A')
            m.write(ENTRY + offset, fmt, value)
            before = bytes(m.uc.mem_read(RING, 4096))
            self.assertEqual(m.submit(3072), 0x1908c)
            self.assertEqual(bytes(m.uc.mem_read(RING, 4096)), before)
        m = Machine('A')
        self.assertEqual(m.submit(3072, dma=0), 0x1908c)
        self.assertEqual(m.read(ENTRY + 0x28, '<Q')[0], RING + 0xff0)

    def test_rx_and_mailbox_bounds_in_manifest(self):
        self.assertEqual(self.m.meta['injection_bytes'], 684)
        self.assertEqual(self.m.symbols['iso_end'], 0x69000)
        self.assertLessEqual(max(int(e['address'], 16) + len(bytes.fromhex(e['after']))
                                 for e in self.m.meta['edits']), 0x69000)

    def test_frame_encoding_retains_microframe_phase_and_wrap(self):
        for raw in (0,1,7,8,9,15,16,0x3ff0,0x3ff7,0x3ff8,0x3fff,0x10000,0xffffffff):
            m = Machine('A')
            m.write(MMIO + 0x48, '<I', raw)
            self.assertEqual(m.submit(3072), 0)
            for p in range(16):
                self.assertEqual(m.read(RING + p * 32 + 12, '<I')[0],
                                 ((((raw >> 3) + 32 + p) & 2047) << 20) | 0x1411)

    def test_original_copy_and_report_epilogue_restore_saved_registers(self):
        for count in (0,1,2):
            m = self.machine()
            report = CTX + 0x900
            m.uc.mem_write(report, bytes(range(128)))
            m.write(report + 128, '<I', count)
            sp = m.uc.reg_read(UC_ARM64_REG_SP)
            m.write(sp, '<QQQQ', 0x29, 0x30, 0x20, 0x19)
            m.uc.reg_write(UC_ARM64_REG_X19, MANAGER)
            m.uc.reg_write(UC_ARM64_REG_X20, report)
            m.uc.emu_start(m.symbols['iso_report'], 0xbab0, count=1000)
            self.assertEqual(m.uc.reg_read(UC_ARM64_REG_X0), MANAGER + 0x10)
            for reg, value in ((UC_ARM64_REG_X19,0x19),(UC_ARM64_REG_X20,0x20),
                               (UC_ARM64_REG_X29,0x29),(UC_ARM64_REG_X30,0x30),
                               (UC_ARM64_REG_SP,sp+32)):
                self.assertEqual(m.uc.reg_read(reg), value)
            self.assertEqual(bytes(m.uc.mem_read(report,16)), bytes(range(16)))
            self.assertEqual(m.read(report+128,'<I')[0], count)
            self.assertEqual(bytes(m.uc.mem_read(report+16,112)),
                             bytes(m.uc.mem_read(RING+0xf80,112)) if count<=1 else bytes(range(16,128)))
