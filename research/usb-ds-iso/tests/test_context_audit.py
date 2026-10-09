"""Execute ISO6 and verify read-only context ordering, stale validity and ownership."""
import unittest
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from test_patch import Machine, RING, RING_DMA, ENTRY, MMIO, MANAGER, CTX
import test_event_audit
from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_X19, UC_ARM64_REG_X20, UC_ARM64_REG_X21, UC_ARM64_REG_X22, UC_ARM64_REG_X23, UC_ARM64_REG_X24, UC_ARM64_REG_X25, UC_ARM64_REG_X26, UC_ARM64_REG_X27, UC_ARM64_REG_X28, UC_ARM64_REG_X29, UC_ARM64_REG_X30
from test_patch import read_mapped, validate_module, EXIT


class ContextAuditTests(unittest.TestCase):
    def setUp(self):
        self.m = Machine('A')
        if self.m.meta.get('diagnostics_magic') not in ('ISO6', 'ISO7'):
            self.skipTest('requires --context-audit package')

    def machine(self, slot=0):
        m = Machine('A')
        for off in (0x18, 0x20): m.write(ENTRY + off, '<Q', RING + slot*16)
        return m

    def ptr(self, slot, packet, ed=True):
        return (RING if ed else RING_DMA) + ((slot + 2*packet + int(ed)) % 247)*16

    def test_actual_context_read_precedes_publication_and_never_modifies_context(self):
        for slot in (0,216,217,246):
            for selected in (0,7,0x3ffc):
                m=self.machine(slot)
                words=(0x40001,0x100002e,0x9000001,0x1234,0x1000c00,0x02000567,0xc0000,0x0400042)
                m.write(CTX+0x1c0,'<8I',*words)
                m.write(MMIO+0x48,'<I',selected)
                trace=[];writes=[]
                def instruction(uc,address,size,data):
                    if address==m.symbols['frame_select_read']:trace.append('select')
                    if address==m.symbols['context_read']:trace.append('context')
                def write(uc,access,address,size,value,data):
                    writes.append((address,size,value))
                    if address==RING+slot*16+12:trace.append('gate')
                    if address==RING+0xfcc:trace.append('valid'+str(value))
                    if address==MMIO+4:trace.append('doorbell')
                hooks=[m.uc.hook_add(UC_HOOK_CODE,instruction),m.uc.hook_add(UC_HOOK_MEM_WRITE,write)]
                self.assertEqual(m.submit(3072),0)
                for h in hooks:m.uc.hook_del(h)
                self.assertEqual(trace,['valid0','select','gate','context','valid1','gate','doorbell'])
                self.assertEqual(m.read(RING+0xfc8,'<II'),(selected,1))
                self.assertEqual(m.read(RING+0xfd0,'<8I'),words)
                self.assertEqual(m.read(CTX+0x1c0,'<8I'),words)
                self.assertFalse(any(CTX <= a < CTX+0x1000 for a,_,_ in writes))
                self.assertEqual([w for w in writes if MMIO <= w[0] < MMIO+0x1000],[(MMIO+4,4,0x700)])
                self.assertEqual(m.symbols['iso_end'],0x68ffc)

    def test_filtered_and_post_terminal_events_do_not_touch_phase_or_ownership(self):
        m = self.machine(240);self.assertEqual(m.submit(3072),0)
        phase = bytes(m.uc.mem_read(RING+0xfc8,40))
        for ptr,ed,cc,count in ((0,False,14,0),(RING+100*16,True,23,0),
                                (self.ptr(240,0)+1,True,1,192),
                                (self.ptr(240,0,False),False,1,192)):
            self.assertEqual(m.event(ptr,ed,cc,count),[])
            self.assertEqual(m.read(RING+0xf8c,'<III'),(0,0,0))
        for p in range(16):
            calls=m.event(self.ptr(240,p),True)
            self.assertEqual(calls,[] if p<15 else [(0x2a980,[MANAGER,0x83,0,1,3072,1])])
        self.assertEqual(m.event(0,False,14,0),[])
        self.assertEqual(bytes(m.uc.mem_read(RING+0xfc8,40)),phase)
        self.assertEqual(m.read(RING+0xf8c,'<III'),(1,0xffff,3072))

    def test_error_priority_and_first_two_success_records_still_hold(self):
        for slot in (0,230,246):
            for p in (0,1,2,15):
                m=self.machine(slot);self.assertEqual(m.submit(3072),0)
                for packet in (0,1):m.event(self.ptr(slot,packet),True)
                m.write(MMIO+0x48,'<I',0x3fff)
                error=self.ptr(slot,p,False)
                self.assertEqual(m.event(error,False,23,0),[])
                self.assertEqual(m.read(RING+0xfb4,'<QIII'),
                                 (error,23<<24,(7<<16)|(32<<10)|1,0x3fff))
                self.assertEqual(m.read(RING+0xf84,'<I')[0],p*32)
                self.assertEqual(m.read(RING+0xf8c,'<III'),(0x80000017,3,384))
                for packet in range(16):self.assertEqual(m.event(self.ptr(slot,packet),True),[])
                self.assertEqual(m.read(ENTRY+0x20,'<Q')[0],RING+slot*16)
                self.assertEqual(m.submit(3072),0x1908c)

    def test_reuse_clears_phase_sentinel_before_all_new_reads(self):
        m=self.machine()
        observed=[]
        def inspect(uc,address,size,data):
            if address==m.symbols['frame_select_read']:
                observed.append(m.read(RING+0xfac,'<I')[0])
                observed.append(m.read(RING+0xfc0,'<I')[0])
                observed.append(m.read(RING+0xfcc,'<I')[0])
        h=m.uc.hook_add(UC_HOOK_CODE,inspect)
        self.assertEqual(m.submit(3072),0)
        for p in range(16):m.event(self.ptr(0,p),True)
        m.uc.mem_write(RING+0xf80,b'\xff'*112)
        observed.clear()
        self.assertEqual(m.submit(3072),0);m.uc.hook_del(h)
        self.assertEqual(observed,[0,0,0])
        self.assertEqual(bytes(m.uc.mem_read(RING+0xfd0,32)),bytes(m.uc.mem_read(CTX+0x1c0,32)))

    def test_original_report_epilogue_and_input_rejection(self):
        # These checks exercise the shared real ABI against the ISO6 binary.
        helper=test_event_audit.EventAuditTests()
        helper.test_original_copy_and_report_epilogue_restore_saved_registers()
        helper.test_combined_validation_still_rejects_every_bad_input()
        m=self.machine();self.assertEqual(m.submit(3072),0)
        writes=[]
        h=m.uc.hook_add(UC_HOOK_MEM_WRITE,lambda u,a,address,size,value,_:writes.append((address,size)))
        m.event(self.ptr(0,0),True);m.event(self.ptr(0,1),True,13,192)
        m.uc.hook_del(h)
        self.assertTrue(writes)
        self.assertTrue(all(RING+0xf80 <= a and a+n <= RING+0xfc8 for a,n in writes))

    def test_tail_early_rejection_keeps_the_prepublication_snapshot_but_never_stores_mmio(self):
        m=self.machine()
        m.uc.mem_write(ENTRY+7,b'\x06');m.uc.mem_write(ENTRY+10,b'\x01')
        m.write(0x1000000+0x22a5c,'<I',1<<7)
        writes=[]
        h=m.uc.hook_add(UC_HOOK_MEM_WRITE,lambda u,a,address,size,value,_:writes.append((address,size,value)))
        self.assertEqual(m.submit(3072),0x1928c);m.uc.hook_del(h)
        self.assertEqual(m.read(RING+0xfcc,'<I')[0],1)
        self.assertFalse(any(MMIO <= address < MMIO+0x1000 for address,_,_ in writes))
        self.assertEqual(m.read(RING+12,'<I')[0]&1,1) # original publication already occurred

    def test_tail_bytes_and_caller_stack_lr_callee_saved_registers_are_preserved(self):
        for rejected in (False,True):
            m=self.machine()
            self.assertEqual(bytes(m.uc.mem_read(0x31c74,0x70)),read_mapped(validate_module(m.raw),0x31c74,0x70))
            saved=(UC_ARM64_REG_X19,UC_ARM64_REG_X20,UC_ARM64_REG_X21,UC_ARM64_REG_X22,
                   UC_ARM64_REG_X23,UC_ARM64_REG_X24,UC_ARM64_REG_X25,UC_ARM64_REG_X26,
                   UC_ARM64_REG_X27,UC_ARM64_REG_X28,UC_ARM64_REG_X29)
            for i,reg in enumerate(saved):m.uc.reg_write(reg,0xaabb0000+i)
            stack=m.uc.reg_read(UC_ARM64_REG_SP)
            if rejected:
                m.uc.mem_write(ENTRY+7,b'\x06');m.uc.mem_write(ENTRY+10,b'\x01')
                m.write(0x1000000+0x22a5c,'<I',1<<7)
            self.assertEqual(m.submit(3072),0x1928c if rejected else 0)
            self.assertEqual(m.uc.reg_read(UC_ARM64_REG_SP),stack)
            self.assertEqual(m.uc.reg_read(UC_ARM64_REG_X30),EXIT)
            for i,reg in enumerate(saved):self.assertEqual(m.uc.reg_read(reg),0xaabb0000+i)
