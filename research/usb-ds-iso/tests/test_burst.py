"""A13 real-instruction tests; run with ISO_PATCH_PACKAGES=.../packages-A13-burst."""
import unittest
from unicorn import UC_HOOK_MEM_WRITE
from test_patch import Machine, RING, RING_DMA, DMA, ENTRY, MMIO, CTRL, MANAGER


class BurstTests(unittest.TestCase):
    def setUp(self):
        self.m = Machine('A')
        if self.m.meta.get('burst_packets') != 16:
            self.skipTest('requires A13 burst package')

    def machine(self, slot=0, cycle=1, raw=0):
        m = Machine('A')
        for offset in (0x18, 0x20): m.write(ENTRY + offset, '<Q', RING + slot * 16)
        m.write(ENTRY + 0x40, '<B', cycle)
        m.write(MMIO + 0x48, '<I', raw)
        return m

    def tags(self, slot):
        return [RING + ((slot + i * 2 + 1) % 247) * 16 for i in range(16)]

    def test_all_start_slots_cycles_and_frame_rollover(self):
        for slot in range(247):
            for cycle in (0, 1):
                m = self.machine(slot, cycle, 0x3ff8)
                self.assertEqual(m.submit(3072), 0)
                for i in range(16):
                    logical = slot + i * 2
                    cursor = RING + logical % 247 * 16
                    c = cycle ^ (logical >= 247)
                    control = (0x80001410 if i and m.meta.get('followup_sia') else
                               (((2047 + 32 + i) & 2047) << 20) | 0x1410)
                    self.assertEqual(m.read(cursor, '<QII'),
                        (DMA + i * 192, 192, control | c))
                    logical += 1
                    cursor = RING + logical % 247 * 16
                    c = cycle ^ (logical >= 247)
                    self.assertEqual(m.read(cursor, '<QII'), (cursor, 0, 0x1c20 | c))
                next_pointer = RING + (slot + 32) % 247 * 16
                self.assertEqual(m.read(ENTRY + 0x18, '<Q')[0], next_pointer)
                self.assertEqual(m.read(MMIO + 4, '<I')[0], 0x700)
                if m.meta.get('first_trb_snapshot'):
                    if m.meta.get('first_trb_control_only'):
                        control_offset = 8 if m.meta.get('bounded_event_audit') else 60
                        self.assertEqual(m.read(RING+0xf80+control_offset,'<I'),m.read(RING+slot*16+12,'<I'))
                    else:
                        self.assertEqual(bytes(m.uc.mem_read(RING+0xfb0,16)),
                                         bytes(m.uc.mem_read(RING+slot*16,16)))
                # Every distinct ED is needed, irrespective of arrival order.
                for i, tag in enumerate(reversed(self.tags(slot))):
                    calls = m.event(tag, True)
                    self.assertEqual(calls, [] if i < 15 else
                        [(0x2a980, [MANAGER, 0x83, 0, 1, 3072, 1])])
                self.assertEqual(m.read(RING + 0xf90, '<II'), (0xffff, 3072))
                self.assertEqual(m.read(ENTRY + 0x20, '<Q')[0], next_pointer)
                self.assertEqual(m.event(self.tags(slot)[0], True), [])
                self.assertEqual(m.event(0, False, cc=14), [])

    def test_first_cycle_is_final_ring_publication(self):
        for slot in (0, 216, 217, 246):
            m = self.machine(slot)
            writes = []
            def record(uc, access, address, size, value, data):
                if RING <= address < RING + 0xf80: writes.append((address, size, value))
            hook = m.uc.hook_add(UC_HOOK_MEM_WRITE, record)
            self.assertEqual(m.submit(3072), 0)
            m.uc.hook_del(hook)
            self.assertEqual(writes[-1][0], RING + slot * 16 + 12)
            # Prior write of first control has inverse cycle.
            first = [v for a, n, v in writes if a == RING + slot * 16 + 12]
            self.assertEqual(len(first), 2)
            self.assertEqual(first[0] ^ first[1], 1)

    def test_duplicate_partial_and_foreign_events_cannot_release(self):
        m = self.machine(240); m.submit(3072)
        tags = self.tags(240)
        for tag in tags[:-1]:
            self.assertEqual(m.event(tag, True), [])
            self.assertEqual(m.event(tag, True), [])
        self.assertEqual(m.read(RING + 0xf94, '<I')[0], 2880)
        self.assertEqual(m.read(ENTRY + 0x20, '<Q')[0], RING + 240 * 16)
        for ptr, ed in ((tags[-1] + 1, True), (RING + 1000, True), (0, False), (RING_DMA + 16, False)):
            self.assertEqual(m.event(ptr, ed), [])
        self.assertEqual(m.event(tags[-1], True), [(0x2a980,[MANAGER,0x83,0,1,3072,1])])

    def test_error_on_any_packet_retains_and_blocks_repost(self):
        for slot in (0, 230, 246):
            for packet in range(16):
                for ed, cc, count in ((False, 23, 0), (True, 13, 192), (True, 1, 191), (True, 1, 193)):
                    m = self.machine(slot); m.submit(3072)
                    ptr = self.tags(slot)[packet] if ed else RING_DMA + ((slot + packet * 2) % 247) * 16
                    m.write(MMIO+0x48,'<I',0x3ffd)
                    self.assertEqual(m.event(ptr, ed, cc=cc, count=count), [])
                    if m.meta.get('error_event_and_mfi_snapshot'):
                        audit = m.meta.get('bounded_event_audit')
                        error_offset, mfi_offset = (52,68) if audit else (64,8)
                        self.assertEqual(m.read(RING+0xf80+mfi_offset,'<I')[0],0x3ffd)
                        self.assertEqual(m.read(RING+0xf84,'<I')[0],packet*32+(16 if ed else 0))
                        self.assertEqual(m.read(RING+0xf80+error_offset,'<QII'),
                            (ptr,(cc<<24)|count,(7<<16)|(32<<10)|(4 if ed else 0)|1))
                        error = bytes(m.uc.mem_read(RING+0xf80+error_offset,20 if audit else 16))
                    for tag in self.tags(slot): self.assertEqual(m.event(tag, True), [])
                    if m.meta.get('error_event_and_mfi_snapshot'):
                        self.assertEqual(bytes(m.uc.mem_read(RING+0xf80+error_offset,len(error))),error)
                    self.assertEqual(m.read(ENTRY + 0x20, '<Q')[0], RING + slot * 16)
                    self.assertTrue(m.read(RING + 0xf8c, '<I')[0] & 0x80000000)
                    self.assertEqual(m.submit(3072), 0x1908c)

    def test_bulk_and_report_abi_remain_intact(self):
        m = self.machine(); m.uc.mem_write(ENTRY + 3,b'\x02')
        self.assertEqual(m.submit(),0)
        self.assertEqual(m.read(RING+12,'<I')[0] >> 10 & 63,1)
        self.assertEqual(m.read(ENTRY+0x28,'<Q')[0],RING+0xff0)
        from test_patch import CTX, UC_ARM64_REG_X19, UC_ARM64_REG_X20
        m = self.machine(); m.submit(3072)
        report = CTX+0x900
        import struct
        for count in (0,1,2):
            first = bytes(range(16))
            m.uc.mem_write(report, first+bytes(112)+struct.pack('<I',count))
            m.uc.reg_write(UC_ARM64_REG_X19,MANAGER)
            m.uc.reg_write(UC_ARM64_REG_X20,report)
            m.uc.emu_start(m.symbols['iso_report'],0x2cbe4,count=1000)
            self.assertEqual(bytes(m.uc.mem_read(report,16)),first)
            self.assertEqual(m.read(report+128,'<I')[0],count)
            self.assertEqual(bytes(m.uc.mem_read(report+16,112)),
                bytes(m.uc.mem_read(RING+0xf80,112)) if count<=1 else bytes(112))

    def test_unsupported_input_and_ss_do_not_modify_ring(self):
        for size in (0,192,3071,3073,4096):
            m = self.machine(); before = bytes(m.uc.mem_read(RING,4096))
            self.assertEqual(m.submit(size),0x1908c)
            self.assertEqual(bytes(m.uc.mem_read(RING,4096)),before)
        m = self.machine(); m.write(CTRL + 0x22a58,'<I',4)
        before = bytes(m.uc.mem_read(RING,4096))
        self.assertEqual(m.submit(3072),0x1908c)
        self.assertEqual(bytes(m.uc.mem_read(RING,4096)),before)
