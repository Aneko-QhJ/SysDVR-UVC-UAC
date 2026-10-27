/* Offline link validation executable. Never run on a console. No USB or FS
 * calls. Native coverage is in ep0_trace_owner_test.c; this binds libnx ABI. */
#include "research/usb-ds-iso/device/ep0_trace_libnx.h"
static Ep0TraceOwner storage;
static uint8_t bytes[EP0_TRACE_EXPORT_MAX];
void __appInit(void) {}
void __appExit(void) {}
/* External linkage keeps the adapter available in the linked ELF for audit. */
__attribute__((noinline)) bool checked_adapter(Ep0TraceOwner *s,uint64_t who,unsigned channel,
                                             Result rc,const UsbDsReportData *r) {
    return ep0_trace_libnx_reports(s,who,channel,rc,r);
}
int main(int argc,char **argv) {
    (void)argc;(void)argv;
    const uint8_t boot[16]={1},session[16]={2};
    if(!ep0_owner_init(&storage,1,armGetSystemTickFreq(),0,boot,session))return 1;
    UsbDsReportData report={.report_count=1,.report={{.id=0,.urb_status=3}}};
    if(!ep0_owner_post(&storage,1,8,0,true,0) || !checked_adapter(&storage,1,8,0,&report))return 2;
    if(!ep0_owner_freeze(&storage,1,0,EP0_TRACE_STOPPED) || !ep0_owner_stop(&storage,1) ||
       !ep0_owner_handoff(&storage,2,0))return 3;
    return ep0_owner_export(&storage,2,bytes,sizeof(bytes))==128 ? 0 : 4;
}
