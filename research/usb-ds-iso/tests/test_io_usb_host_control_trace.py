import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from analyze_io_usb_host_no_td import control_trace


class InterfaceDispatchTests(unittest.TestCase):
    def setUp(self):
        self.lines=[]
        for interface in (0,1,0,1):
            self.lines.extend([f'EP0[{interface}]: reqType=0xc1 req=0x51 wVal=0x0000 wIdx=0x0002 wLen=168',
                               f'EP0[{interface}]: wIndex mismatch, ignoring'])

    def check(self,lines):
        return control_trace(('\n'.join(lines)+'\n').encode(),hardware=True)

    def test_complete_broadcast_shape_is_not_bus_request_count_proof(self):
        r=self.check(self.lines)
        self.assertTrue(r['matches_fixed_plan'])
        self.assertEqual(r['inferred_status_requests'],2)
        self.assertEqual([v[0] for v in r['vendor_records']],[0,1,0,1])
        self.assertFalse(r['request_count_verified']);self.assertFalse(r['bus_capture_verified'])

    def test_formats_are_explicit_and_cannot_be_inferred_from_duplicates(self):
        legacy=[self.lines[0],self.lines[2]]
        self.assertTrue(control_trace(('\n'.join(legacy)+'\n').encode())['matches_fixed_plan'])
        self.assertFalse(self.check(legacy)['matches_fixed_plan'])
        self.assertFalse(control_trace(('\n'.join(self.lines)+'\n').encode())['matches_fixed_plan'])

    def test_each_missing_duplicate_or_reordered_delivery_is_rejected(self):
        for i in range(len(self.lines)):
            with self.subTest(i=i):
                self.assertFalse(self.check(self.lines[:i]+self.lines[i+1:])['matches_fixed_plan'])
                self.assertFalse(self.check(self.lines[:i]+[self.lines[i]]+self.lines[i:])['matches_fixed_plan'])
        self.assertFalse(self.check(self.lines[2:4]+self.lines[:2]+self.lines[4:])['matches_fixed_plan'])
        self.assertFalse(self.check(self.lines+self.lines[:4])['matches_fixed_plan'])

    def test_wrong_owner_acknowledgement_and_orphan_markers_are_rejected(self):
        for i in (1,3,5,7):
            lines=self.lines.copy();lines[i]=lines[i].replace('mismatch, ignoring','unhandled request -> stall')
            self.assertFalse(self.check(lines)['matches_fixed_plan'])
            lines=self.lines.copy();lines[i]=lines[i].replace('[0]','[2]').replace('[1]','[2]')
            self.assertFalse(self.check(lines)['matches_fixed_plan'])
        self.assertFalse(self.check(['EP0[0]: wIndex mismatch, ignoring']+self.lines)['matches_fixed_plan'])

    def test_interleaved_control_disconnect_or_unknown_line_is_rejected(self):
        for line in ('USB host disconnected','USB host connected','GetSetupPacket failed: 0x1',
                     'EP0[0]: reqType=0x01 req=0x0b wVal=0x0000 wIdx=0x0001 wLen=0',
                     'EP0[0]: wIndex mismatch, ignoring'):
            for i in range(1,8):
                self.assertFalse(self.check(self.lines[:i]+[line]+self.lines[i:])['matches_fixed_plan'])

    def test_extra_vendor_controls_and_wrong_status_tuple_are_rejected(self):
        for value in ('50','52','53','54','55'):
            extra=self.lines[0].replace('req=0x51',f'req=0x{value}')
            self.assertFalse(self.check(self.lines+[extra])['matches_fixed_plan'])
        for old,new in (('reqType=0xc1','reqType=0x41'),('wVal=0x0000','wVal=0x0001'),
                        ('wIdx=0x0002','wIdx=0x0003'),('wLen=168','wLen=167'),
                        ('req=0x51','req=oops'),('EP0[0]','EP0[2]')):
            lines=self.lines.copy();lines[0]=lines[0].replace(old,new)
            self.assertFalse(self.check(lines)['matches_fixed_plan'])

    def test_standard_setup_broadcast_outside_status_block_is_allowed(self):
        standard=['EP0[0]: reqType=0x01 req=0x0b wVal=0x0000 wIdx=0x0001 wLen=0',
                  'EP0[0]: wIndex mismatch, ignoring',
                  'EP0[1]: reqType=0x01 req=0x0b wVal=0x0000 wIdx=0x0001 wLen=0']
        self.assertTrue(self.check(standard+self.lines+['USB host disconnected'])['matches_fixed_plan'])
        # Interface 1 owns SET_INTERFACE(1); an ignore marker contradicts it.
        self.assertFalse(self.check(standard+['EP0[1]: wIndex mismatch, ignoring']+self.lines)['matches_fixed_plan'])


if __name__=='__main__':unittest.main()
