/* Injected services only. Actual EP0/dispatch source is inserted at the marker.
 * Virtual deadlines and event loss are hypotheses, never hardware observations. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "source/uvc/iso_probe_protocol.h"
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
typedef uint64_t u64; typedef int32_t s32; typedef unsigned Result;
typedef unsigned UsbDeviceSpeed;
typedef struct { unsigned kind; bool signaled; } Event;
typedef struct { unsigned interface_index; Event SetupEvent, CtrlInCompletionEvent, CtrlOutCompletionEvent; } UsbDsInterface;
typedef struct { Event CompletionEvent; } UsbDsEndpoint;
typedef struct { u8 bmRequestType, bRequest; u16 wValue, wIndex, wLength; } UsbSetupPacket;
typedef struct { unsigned unused; } UsbDsReportData;
#define R_FAILED(x) ((x)!=0)
#define R_SUCCEEDED(x) ((x)==0)
#define MAKERESULT(a,b) 99
#define UsbDeviceSpeed_High 3
#define UsbDeviceSpeed_Super 4
#define UsbState_Configured 5
#define UVC_STATE_DISCONNECTED 0
#define UVC_STATE_CONNECTED 1
#define USB_REQUEST_SET_INTERFACE 11
#define USB_REQUEST_GET_INTERFACE 10
#define USB_REQTYPE_DIR_MASK 0x80
#define USB_REQTYPE_DIR_TO_HOST 0x80
#define EP0_XFER_TIMEOUT 1000000000ULL
static UsbDsInterface interfaces[3];
static UsbDsInterface *g_isoInterface = &interfaces[2];
static UsbDsEndpoint endpoint, *g_isoEndpoint = &endpoint;
static struct { UsbDsInterface *controlInterface, *streamingInterface; unsigned state, frameId, frameNumber; } g_uvcCtx;
static struct { bool streaming; } g_uacCtx;
static IsoProbeStatus g_isoStatus;
static u8 g_isoBuffer[4096], g_vcControlBuffer[4096], g_controlBuffer[4096], g_lastErrorCode;
#define UVC_ERROR_NONE 0
static unsigned posts, stalls, in_posts, status_writes, submits, broadcasts, iso_gets;
static unsigned speed=3, speed_rc, post_rc, ack_post_rc, ack_wait_rc, ack_report_rc, ack_parse_rc;
static unsigned device_state=5;
static u64 now_ns, log_ns, entered_ns;
static bool drop_iso, replace_iso, get_setup_fail;
static UsbSetupPacket burst={0x41,ISO_PROBE_BURST,1,2,0};
static UsbSetupPacket status={0xc1,ISO_PROBE_STATUS,0,2,168};
static void record_log(const char *format, ...) {
    if (strstr(format,"EP0[%u]")) { broadcasts++; now_ns+=log_ns; }
    if (strstr(format,"ISO submit")) submits++;
}
#define LOG(...) record_log(__VA_ARGS__)
static Result eventWait(Event *e, u64 timeout) {
    if (e->kind==1 && ack_wait_rc) { now_ns+=timeout; return ack_wait_rc; }
    if (e==&interfaces[2].SetupEvent && drop_iso && now_ns>=16000000) return 1;
    return e->signaled ? 0 : 1;
}
static Result eventClear(Event *e) { e->signaled=false; return 0; }
#define waiterForEvent(e) (e)
static Result waitMulti(s32 *index, u64 timeout, Event *a, Event *b, Event *c) {
    (void)index;(void)a;(void)b;(void)c;now_ns+=timeout;return 1;
}
static void _pollIsoProbe(void) { /* No device reports in this fixture. */ }
static u64 svcGetSystemTick(void) { return now_ns; }
static unsigned armGetSystemTickFreq(void) { return 1000000000; }
static void svcSleepThread(u64 t) { now_ns+=t; }
static void armDCacheFlush(void *b, size_t n) { (void)b;(void)n; }
static Result usbDsGetState(u32 *state) { *state=device_state;return 0; }
static Result usbDsGetSpeed(UsbDeviceSpeed *out) { *out=speed;return speed_rc; }
static Result usbDsInterface_StallCtrl(UsbDsInterface *i) { (void)i;stalls++;return 0; }
static Result usbDsEndpoint_PostBufferAsync(UsbDsEndpoint *e, void *b, size_t n, u32 *id) {
    (void)e;(void)b;assert(n==3072);posts++;*id=17;return post_rc;
}
static Result usbDsEndpoint_Cancel(UsbDsEndpoint *e) { (void)e;return 0; }
static Result usbDsInterface_CtrlInPostBufferAsync(UsbDsInterface *i, void *b, size_t n, u32 *id) {
    (void)b;in_posts++;*id=23;if(n==168)status_writes++;
    if(n==0 && ack_post_rc)return ack_post_rc;
    i->CtrlInCompletionEvent.signaled=true;return 0;
}
static Result usbDsInterface_CtrlOutPostBufferAsync(UsbDsInterface *i, void *b, size_t n, u32 *id) {
    (void)b;(void)n;*id=24;i->CtrlOutCompletionEvent.signaled=true;return 0;
}
static Result usbDsInterface_GetCtrlInReportData(UsbDsInterface *i, UsbDsReportData *r) {
    (void)i;(void)r;return ack_report_rc;
}
static Result usbDsInterface_GetCtrlOutReportData(UsbDsInterface *i, UsbDsReportData *r) {
    (void)i;(void)r;return 0;
}
static Result usbDsParseReportData(UsbDsReportData *r, u32 id, u32 *requested, u32 *actual) {
    (void)r;(void)id;(void)requested;if(actual)*actual=0;return ack_parse_rc;
}
static Result usbDsInterface_GetSetupPacket(UsbDsInterface *i, void *b, size_t n) {
    assert(n==8);
    if(i->interface_index==2) {
        iso_gets++;entered_ns=now_ns;
        if(get_setup_fail)return 98;
    }
    memcpy(b, (i->interface_index==2 && replace_iso && now_ns>=16000000) ? &status : &burst, n);
    return 0;
}
static void _handleVsSetup(UsbDsInterface *i, const UsbSetupPacket *s) { (void)i;(void)s;assert(false); }
static void _handleVcSetup(UsbDsInterface *i, const UsbSetupPacket *s) { (void)i;(void)s;assert(false); }

/* INSERT_ACTUAL_SOURCE */

int main(int argc, char **argv) {
    assert(argc==2);const char *name=argv[1];
    g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];g_uvcCtx.state=1;
    for(unsigned i=0;i<3;i++) {
        interfaces[i].interface_index=i;interfaces[i].SetupEvent=(Event){0,true};
        interfaces[i].CtrlInCompletionEvent.kind=1;interfaces[i].CtrlOutCompletionEvent.kind=2;
    }
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;g_isoStatus.endpoint=0x83;
    if(!strcmp(name,"no-iso-event"))interfaces[2].SetupEvent.signaled=false;
    else if(!strcmp(name,"speed-error"))speed_rc=97;
    else if(!strcmp(name,"full-speed"))speed=2;
    else if(!strcmp(name,"super-speed"))speed=4;
    else if(!strcmp(name,"pending"))g_isoStatus.state=ISO_PROBE_PENDING;
    else if(!strcmp(name,"retained"))g_isoStatus.state=ISO_PROBE_RETAINED;
    else if(!strcmp(name,"post-failed"))post_rc=96;
    else if(!strcmp(name,"ack-post-failed"))ack_post_rc=95;
    else if(!strcmp(name,"ack-timeout"))ack_wait_rc=94;
    else if(!strcmp(name,"ack-report-failed"))ack_report_rc=93;
    else if(!strcmp(name,"ack-urb-failed"))ack_parse_rc=92;
    else if(!strcmp(name,"get-setup-failed"))get_setup_fail=true;
    else if(!strcmp(name,"slow-log-kept"))log_ns=5000000;
    else if(!strcmp(name,"slow-log-dropped")){log_ns=5000000;drop_iso=true;}
    else if(!strcmp(name,"slow-log-replaced")){log_ns=5000000;replace_iso=true;}
    else assert(!strcmp(name,"normal") || !strcmp(name,"disconnect-after-post"));
    IsoProbeStatus before=g_isoStatus;
    UvcDeviceProcessRequests();
    assert(broadcasts==4);
    bool posted=!strcmp(name,"normal") || !strcmp(name,"disconnect-after-post") ||
        !strcmp(name,"post-failed") || !strncmp(name,"ack-",4) || !strcmp(name,"slow-log-kept");
    if(posted) {
        assert(posts==1 && submits==1 && g_isoStatus.sequence==1);
        assert(g_isoStatus.state==(post_rc ? ISO_PROBE_FAILED : ISO_PROBE_PENDING));
        assert(memcmp(&before,&g_isoStatus,sizeof(before))!=0);
        for(unsigned p=0;p<16;p++)for(unsigned j=0;j<192;j++)
            assert(g_isoBuffer[p*192+j]==isoProbeByte((uint16_t)(1+p),j));
    } else assert(posts==0 && submits==0 && !memcmp(&before,&g_isoStatus,sizeof(before)));
    bool early_stall=speed_rc || speed!=3 || before.state==1 || before.state==4;
    assert(stalls==(unsigned)(early_stall || ack_post_rc || ack_wait_rc || ack_report_rc || ack_parse_rc));
    if(!strcmp(name,"slow-log-kept"))assert(entered_ns==20000000 && posts==1);
    if(!strcmp(name,"slow-log-dropped"))assert(iso_gets==0);
    if(!strcmp(name,"slow-log-replaced"))assert(status_writes==1 && iso_gets==1);
    if(!strcmp(name,"ack-timeout"))assert(now_ns>=1000000000 && submits==1);
    if(!strcmp(name,"disconnect-after-post")) {
        device_state=0;UvcDeviceProcessRequests();assert(g_isoStatus.sequence==1 && g_isoStatus.state==ISO_PROBE_RETAINED);
    }
    printf("{\"scenario\":\"%s\",\"posts\":%u,\"stalls\":%u,\"submit_logs\":%u,\"broadcast_logs\":%u,"
        "\"sequence\":%u,\"state\":%u,\"iso_setup_reads\":%u,\"status_writes\":%u,\"entered_ns\":%llu,"
        "\"virtual_end_ns\":%llu,\"status_unchanged\":%s,\"hardware_observation\":false}\n",
        name,posts,stalls,submits,broadcasts,g_isoStatus.sequence,g_isoStatus.state,iso_gets,status_writes,
        (unsigned long long)entered_ns,(unsigned long long)now_ns,
        !memcmp(&before,&g_isoStatus,sizeof(before)) ? "true" : "false");
    return 0;
}
