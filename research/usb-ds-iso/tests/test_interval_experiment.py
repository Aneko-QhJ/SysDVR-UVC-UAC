"""A23 service-interval contrast against confirmed A22, using real code."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_patch import Machine, ROOT, PACKAGES, RING, ENTRY, MMIO
from build_patch import build
from package_experiment import validate_revision


class IntervalExperimentTests(unittest.TestCase):
    def setUp(self):
        self.meta = json.loads((PACKAGES / 'A/manifest.json').read_text())
        if self.meta.get('diagnostics_magic') != 'ISO7':
            self.skipTest('requires A23 bInterval1 package')

    def test_only_interval1_is_accepted_by_producer(self):
        for interval in range(256):
            m = Machine('A')
            m.write(ENTRY + 6, '<B', interval)
            before = bytes(m.uc.mem_read(RING, 4096))
            self.assertEqual(m.submit(3072), 0 if interval == 1 else 0x1908c)
            if interval != 1:
                self.assertEqual(bytes(m.uc.mem_read(RING, 4096)), before)

    def test_only_interval_check_and_diagnostic_marker_change_in_controller(self):
        old = ROOT / 'private/packages-A22-followup-sia/A'
        before = (old / 'inject.bin').read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(),
                         '06b8b4b0438a1cec3e4569a9c0cdf972830bd92027f4e3281b95863bb2b86749')
        after = (PACKAGES / 'A/inject.bin').read_bytes()
        self.assertEqual(len(before), len(after))
        self.assertEqual(sum(before[i:i+4] != after[i:i+4] for i in range(0,len(before),4)), 2)
        baseline = json.loads((old / 'manifest.json').read_text())
        self.assertEqual(baseline['symbols'], self.meta['symbols'])
        self.assertEqual(baseline['edits'][1:], self.meta['edits'][1:])
        for key in ('frame_lead', 'mps', 'burst_packets', 'retain_success', 'followup_sia',
                    'prepublication_context_snapshot', 'publication_mfi_snapshot', 'doorbell_tail_mfi_snapshot'):
            self.assertEqual(baseline[key], self.meta[key])

    def test_first_frame_and_following_sia_survive_all_microframe_phases(self):
        for frame in (0,2015,2047):
            for phase in range(8):
                for cycle in (0,1):
                    m = Machine('A');m.write(ENTRY+0x40,'<B',cycle)
                    m.write(MMIO+0x48,'<I',frame*8+phase)
                    self.assertEqual(m.submit(3072),0)
                    for td in range(16):
                        control=m.read(RING+td*32+12,'<I')[0]
                        self.assertEqual(control, (0x80001410 if td else (((frame+32)&2047)<<20)|0x1410)|cycle)

    def test_incompatible_builds_and_revision_pairings_fail_closed(self):
        for flags in ({'interval':1}, {'interval':1,'context_audit':True}, {'interval':2}):
            with self.assertRaises(ValueError):build(None,1,None,None,**flags)
        result=subprocess.run([sys.executable,str(ROOT/'tools/build_patch.py'),'--interval','1'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertIn('requires --context-audit and --followup-sia',result.stderr)
        self.assertEqual(validate_revision(self.meta,'A23',True),(True,False,False,True,True))
        for revision in ('A18','A19','A20','A21','A22'):
            with self.assertRaises(ValueError):validate_revision(self.meta,revision,True)
        for changed in (dict(self.meta,interval=4),dict(self.meta,followup_sia=False),dict(self.meta,diagnostics_magic='ISO6')):
            with self.assertRaises(ValueError):validate_revision(changed,'A23',True)

    def test_actual_descriptor_registration_changes_hs_only(self):
        source=(ROOT.parents[1]/'source/uvc/uvc_device.c').read_text()
        start=source.index('static Result _setupIsoProbe(void)')
        end=source.index('\nstatic void _pollIsoProbe(void)',start)
        body=source[start:end]
        prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "source/uvc/iso_probe_protocol.h"
typedef unsigned Result; typedef unsigned UsbDeviceSpeed;
typedef struct {unsigned interface_index;} UsbDsInterface;
typedef struct {unsigned unused;} UsbDsEndpoint;
struct __attribute__((packed)) usb_interface_descriptor {uint8_t bLength,bDescriptorType,bInterfaceNumber,bAlternateSetting,bNumEndpoints,bInterfaceClass,bInterfaceSubClass,bInterfaceProtocol,iInterface;};
struct __attribute__((packed)) usb_endpoint_descriptor {uint8_t bLength,bDescriptorType,bEndpointAddress,bmAttributes;uint16_t wMaxPacketSize;uint8_t bInterval;};
struct __attribute__((packed)) usb_ss_endpoint_companion_descriptor {uint8_t bLength,bDescriptorType,bMaxBurst,bmAttributes;uint16_t wBytesPerInterval;};
#define USB_DT_INTERFACE_SIZE 9
#define USB_DT_ENDPOINT_SIZE 7
#define USB_DT_INTERFACE 4
#define USB_DT_ENDPOINT 5
#define USB_DT_SS_ENDPOINT_COMPANION 48
#define USB_TRANSFER_TYPE_ISOCHRONOUS 1
#define UsbDeviceSpeed_High 3
#define UsbDeviceSpeed_Super 4
#define R_FAILED(x) ((x)!=0)
#define MAKERESULT(a,b) 1
static UsbDsInterface interface={2},*g_isoInterface;
static UsbDsEndpoint endpoint,*g_isoEndpoint;
static IsoProbeStatus g_isoStatus;
static struct usb_endpoint_descriptor registered[5];
static unsigned endpoints;
static bool _logIsoTarget(void){return true;}
static Result usbDsRegisterInterface(UsbDsInterface **p){*p=&interface;return 0;}
static Result usbDsInterface_AppendConfigurationData(UsbDsInterface *i,UsbDeviceSpeed s,const void *p,unsigned n){
 (void)i;const uint8_t *b=p;if(b[1]==USB_DT_ENDPOINT){assert(n==7);memcpy(&registered[s],p,n);endpoints++;}return 0;
}
static Result usbDsInterface_RegisterEndpoint(UsbDsInterface *i,UsbDsEndpoint **p,unsigned a){(void)i;assert(a==0x83);*p=&endpoint;return 0;}
static Result usbDsInterface_EnableInterface(UsbDsInterface *i){(void)i;return 0;}
'''
        suffix=r'''
int main(void){assert(_setupIsoProbe()==0);assert(endpoints==2);
 assert(registered[3].bInterval==ISO_PROBE_INTERVAL && registered[4].bInterval==4);
 assert(registered[3].wMaxPacketSize==256 && registered[4].wMaxPacketSize==256);
 assert(registered[3].bEndpointAddress==0x83 && registered[3].bmAttributes==1);
 assert(g_isoStatus.magic==ISO_PROBE_STATUS_MAGIC && g_isoStatus.endpoint==0x83);return 0;}
'''
        with tempfile.TemporaryDirectory() as directory:
            c=Path(directory)/'setup.c';binary=Path(directory)/'setup'
            c.write_text(prefix+body+suffix)
            for interval in (1,4):
                subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-DISO_PROBE_MPS=256',
                                '-DISO_PROBE_INTERVAL='+str(interval),'-I'+str(ROOT.parents[1]),str(c),'-o',str(binary)],check=True)
                subprocess.run([str(binary)],check=True)
