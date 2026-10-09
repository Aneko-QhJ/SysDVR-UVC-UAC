"""Compile the actual ISO setup handler against instrumented usb:ds stubs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PREFIX = r'''
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <assert.h>
#include "source/uvc/iso_probe_protocol.h"
typedef uint8_t u8; typedef uint32_t u32; typedef uint64_t u64;
typedef unsigned Result; typedef unsigned UsbDeviceSpeed;
typedef struct {unsigned interface_index;} UsbDsInterface;
typedef struct {unsigned CompletionEvent;} UsbDsEndpoint;
typedef struct {u8 bmRequestType,bRequest; unsigned wValue,wIndex,wLength;} UsbSetupPacket;
#define UsbDeviceSpeed_High 3
#define UsbDeviceSpeed_Super 4
#define USB_REQUEST_SET_INTERFACE 11
#define USB_REQUEST_GET_INTERFACE 10
#define R_FAILED(x) ((x)!=0)
#define R_SUCCEEDED(x) ((x)==0)
#define MAKERESULT(a,b) 1
#define LOG(fmt,...) do { if (strstr((fmt), "ISO submit")) assert(acks>post_ack_count); } while(0)
static unsigned stalls,writes,acks,posts,polls,cancels,posted_size;
static unsigned post_ack_count;
static unsigned test_speed=UsbDeviceSpeed_High;
static IsoProbeStatus g_isoStatus;
static UsbDsEndpoint endpoint,*g_isoEndpoint=&endpoint;
static u8 g_isoBuffer[4096];
static void usbDsInterface_StallCtrl(UsbDsInterface *i){(void)i;stalls++;}
static void _pollIsoProbe(void){polls++;}
static void _ctrlWrite(UsbDsInterface *i,const void *b,unsigned n){(void)i;(void)b;(void)n;writes++;}
static void _ctrlAck(UsbDsInterface *i){(void)i;acks++;}
#define armGetSystemTickFreq() 19200000
#define svcGetSystemTick() 0
#define svcSleepThread(x) ((void)0)
#define armDCacheFlush(b,n) ((void)0)
#define eventClear(e) ((void)0)
#define eventWait(e,t) ((void)0)
#define usbDsGetSpeed(s) (*(s)=test_speed,0)
#define usbDsEndpoint_PostBufferAsync(e,b,n,id) (*(id)=1,posted_size=(n),post_ack_count=acks,posts++,0)
#define usbDsEndpoint_Cancel(e) ((void)cancels++)
'''
SUFFIX = r'''
int main(void){
 UsbDsInterface iso={2};
 UsbSetupPacket requests[]={
  {0x21,1,0x100,1,34},{0xa1,0x81,0x100,1,34},
  {0x21,1,0x200,1,34},{0xa1,0x81,0x200,1,48},
  {0x01,11,0,1,0},{0x81,10,0,0,1}};
 for(unsigned j=0;j<sizeof(requests)/sizeof(requests[0]);j++)
  _handleIsoSetup(&iso,&requests[j]);
 assert(stalls==0 && writes==0 && acks==0 && posts==0 && polls==0);
 UsbSetupPacket status={0xc1,ISO_PROBE_STATUS,0,2,sizeof(g_isoStatus)};
 _handleIsoSetup(&iso,&status); assert(writes==1 && polls==1 && stalls==0);
 UsbSetupPacket invalid={0xc1,0xff,0,2,0};
 _handleIsoSetup(&iso,&invalid); assert(stalls==1);
#ifdef ISO_PROBE_BURST_MODE
 UsbSetupPacket trigger={0x41,ISO_PROBE_BURST,65530,2,0};
 unsigned count=16;
#else
 UsbSetupPacket trigger={0x41,ISO_PROBE_TRIGGER,65530,2,0};
 unsigned count=1;
#endif
 _handleIsoSetup(&iso,&trigger);
 assert(posts==1 && posted_size==count*192 && g_isoStatus.state==ISO_PROBE_PENDING);
 for(unsigned p=0;p<count;p++) for(unsigned i=0;i<192;i++)
  assert(g_isoBuffer[p*192+i]==isoProbeByte((uint16_t)(65530+p),i));
 _handleIsoSetup(&iso,&trigger); assert(posts==1 && stalls==2);
 g_isoStatus.state=ISO_PROBE_RETAINED;
 _handleIsoSetup(&iso,&trigger); assert(posts==1 && stalls==3);
#ifdef ISO_PROBE_BURST_MODE
 g_isoStatus.state=ISO_PROBE_IDLE; test_speed=UsbDeviceSpeed_Super;
 _handleIsoSetup(&iso,&trigger); assert(posts==1 && stalls==4);
#endif
 return 0;
}
'''


class Ep0OwnershipTests(unittest.TestCase):
    def test_foreign_uvc_setup_never_stalls_shared_ep0(self):
        source = (ROOT/'source/uvc/uvc_device.c').read_text()
        start = source.index('static void _handleIsoSetup(')
        end = source.index('\n#endif\n\nstatic void _handleSetupPacket', start)
        handler = source[start:end]
        with tempfile.TemporaryDirectory() as directory:
            c = Path(directory)/'ownership.c'
            binary = Path(directory)/'ownership'
            c.write_text(PREFIX+handler+SUFFIX)
            for flags in ([],['-DISO_PROBE_BURST_MODE'],['-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT'],
                          ['-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_PUBLICATION_AUDIT'],
                          ['-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_PUBLICATION_AUDIT','-DISO_PROBE_DOORBELL_AUDIT'],
                          ['-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_CONTEXT_AUDIT'],
                          ['-DISO_PROBE_BURST_MODE','-DISO_PROBE_EVENT_AUDIT','-DISO_PROBE_CONTEXT_AUDIT','-DISO_PROBE_FOLLOWUP_SIA']):
                subprocess.run(['cc','-std=c11','-I'+str(ROOT),*flags,str(c),'-o',str(binary)],check=True)
                subprocess.run([str(binary)],check=True)
