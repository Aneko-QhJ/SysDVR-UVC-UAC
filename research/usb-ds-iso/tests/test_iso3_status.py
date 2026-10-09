"""Compile the real polling function to check retention with ISO3 reports."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "source/uvc/iso_probe_protocol.h"
typedef uint32_t u32; typedef unsigned Result;
typedef struct {unsigned id,requestedSize,transferredSize,urb_status;} UsbDsReportEntry;
typedef struct {UsbDsReportEntry report[8];u32 report_count;} UsbDsReportData;
typedef struct {unsigned CompletionEvent;} UsbDsEndpoint;
static UsbDsEndpoint endpoint,*g_isoEndpoint=&endpoint;
static IsoProbeStatus g_isoStatus;
static UsbDsReportData next_report;
static unsigned clears;
#define LOG(...) ((void)0)
#define R_FAILED(x) ((x)!=0)
#define eventClear(e) ((void)(e),++clears)
static Result usbDsEndpoint_GetReportData(UsbDsEndpoint *e,UsbDsReportData *r) {
 (void)e;*r=next_report;return 0;
}
'''
SUFFIX = r'''
static void setup(unsigned magic,unsigned terminal,unsigned state,unsigned count) {
 memset(&next_report,0,sizeof(next_report));memset(&g_isoStatus,0,sizeof(g_isoStatus));
 IsoProbeDiagnostics diag={0};diag.magic=magic;diag.terminal=terminal;
 if(count<=1)memcpy(&next_report.report[1],&diag,sizeof(diag));
 next_report.report_count=count;g_isoStatus.state=state;g_isoStatus.urb_id=387;clears=0;
}
int main(void) {
 unsigned magics[]={ISO_PROBE_DIAG_MAGIC,ISO_PROBE_BURST_DIAG_MAGIC,ISO_PROBE_BURST_AUDIT_MAGIC,ISO_PROBE_BURST_PUBLICATION_MAGIC,ISO_PROBE_BURST_DOORBELL_MAGIC,ISO_PROBE_BURST_CONTEXT_MAGIC,ISO_PROBE_BURST_INTERVAL_MAGIC};
 for(unsigned i=0;i<sizeof(magics)/sizeof(magics[0]);i++) {
  setup(magics[i],0x80000017,ISO_PROBE_PENDING,0);_pollIsoProbe();
  assert(g_isoStatus.state==ISO_PROBE_RETAINED && g_isoStatus.diagnostics.magic==magics[i] && clears==0);
  setup(magics[i],1,ISO_PROBE_PENDING,0);_pollIsoProbe();
  assert(g_isoStatus.state==ISO_PROBE_PENDING && clears==0);
 }
 setup(0xdeadbeef,0x80000017,ISO_PROBE_PENDING,0);_pollIsoProbe();
 assert(g_isoStatus.state==ISO_PROBE_PENDING && g_isoStatus.diagnostics.magic==0 && clears==0);
 setup(ISO_PROBE_BURST_AUDIT_MAGIC,0x80000017,ISO_PROBE_COMPLETE,0);_pollIsoProbe();
 assert(g_isoStatus.state==ISO_PROBE_COMPLETE && clears==0);
 setup(ISO_PROBE_BURST_AUDIT_MAGIC,1,ISO_PROBE_PENDING,1);
 next_report.report[0]=(UsbDsReportEntry){403,3072,3072,3};_pollIsoProbe();
 assert(g_isoStatus.state==ISO_PROBE_PENDING && clears==0);
 for(unsigned status=1;status<=5;status++) {
  setup(ISO_PROBE_BURST_AUDIT_MAGIC,1,ISO_PROBE_PENDING,1);
  next_report.report[0]=(UsbDsReportEntry){387,3072,3072,status};_pollIsoProbe();
  assert(g_isoStatus.state==(status<3?ISO_PROBE_PENDING:status==3?ISO_PROBE_COMPLETE:ISO_PROBE_FAILED));
  assert(clears==(status>=3));assert(g_isoStatus.urb_status==status);
 }
 setup(0,0,ISO_PROBE_PENDING,2);
 next_report.report[1]=(UsbDsReportEntry){ISO_PROBE_BURST_AUDIT_MAGIC,0x80000017,0,1};
 _pollIsoProbe();assert(g_isoStatus.diagnostics.magic==0 && g_isoStatus.state==ISO_PROBE_PENDING && clears==0);
 return 0;
}
'''


class Iso3StatusTests(unittest.TestCase):
    def test_reports_keep_retention_and_require_own_terminal_urb(self):
        source = (ROOT/'source/uvc/uvc_device.c').read_text()
        start = source.index('static void _pollIsoProbe(void)')
        end = source.index('\n#endif\n\n// UAC', start)
        with tempfile.TemporaryDirectory() as directory:
            c, binary = Path(directory)/'poll.c', Path(directory)/'poll'
            c.write_text(PREFIX+source[start:end]+SUFFIX)
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-DISO_PROBE_BURST_MODE',
                            '-I'+str(ROOT),str(c),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
