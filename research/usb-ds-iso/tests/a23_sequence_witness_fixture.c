/* The frozen device handler is inserted verbatim. Services below are injected.
 * Completion is explicitly modeled; no HOS, DMA, ARM or physical bus execution. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "iso_probe_protocol.h"
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
typedef uint64_t u64; typedef unsigned Result; typedef unsigned UsbDeviceSpeed;
typedef struct { unsigned unused; } Event;
typedef struct { unsigned interface_index; } UsbDsInterface;
typedef struct { Event CompletionEvent; } UsbDsEndpoint;
typedef struct { u8 bmRequestType,bRequest; u16 wValue,wIndex,wLength; } UsbSetupPacket;
#define R_SUCCEEDED(x) ((x)==0)
#define R_FAILED(x) ((x)!=0)
#define MAKERESULT(a,b) 99
#define UsbDeviceSpeed_High 3
#define UsbDeviceSpeed_Super 4
#define USB_REQUEST_SET_INTERFACE 11
#define USB_REQUEST_GET_INTERFACE 10
#define EP0_TRACE_ARG0_VALID 1
#define EP0_TRACE_ARG1_VALID 2
enum { EP0_T_ISO_ENTER,EP0_T_GUARD,EP0_T_STATUS,EP0_T_SPEED,EP0_T_SEQUENCE,EP0_T_ISO_POST };
enum { EP0_G_WRONG_INTERFACE,EP0_G_BUSY,EP0_G_SPEED,EP0_G_NOT_HS };
static IsoProbeStatus g_isoStatus, reply;
static UsbDsEndpoint endpoint,*g_isoEndpoint=&endpoint;
static u8 g_isoBuffer[4096],control[4096],posted[3072];
static unsigned posts,acks,stalls,post_result,speed_result,sequence_events,sequence_value;
static bool admit=true;
static u64 ticks;
static u64 svcGetSystemTick(void) { return ++ticks; }
static unsigned armGetSystemTickFreq(void) { return 19200000; }
static void svcSleepThread(u64 n) { ticks+=n; }
static void record_log(const char *s,...) { (void)s; }
#define LOG(...) record_log(__VA_ARGS__)
static void _pollIsoProbe(void) {}
static u8 *_ctrlBufferFor(UsbDsInterface *i) { (void)i;return control; }
static bool Ep0CandidateAdmissionBurst(void *p,unsigned n,void *c) { assert(p==g_isoBuffer && n==3072 && c==control);return admit; }
static Result usbDsGetSpeed(UsbDeviceSpeed *s) { *s=3;return speed_result; }
static void armDCacheFlush(void *p,unsigned n) { (void)p;(void)n; }
static Result eventClear(Event *e) { (void)e;return 0; }
static Result eventWait(Event *e,u64 n) { (void)e;(void)n;return 0; }
static Result usbDsEndpoint_PostBufferAsync(UsbDsEndpoint *e,void *p,unsigned n,u32 *id) {
    assert(e==g_isoEndpoint && n==3072);++posts;memcpy(posted,p,n);*id=387;return post_result;
}
static void Ep0CandidateObservePost(unsigned c,Result r,bool valid,u32 id) { (void)c;(void)r;(void)valid;(void)id; }
static void Ep0CandidateGuardPost(unsigned c,Result r,bool valid,u32 id,void *p,unsigned n) { (void)c;(void)r;(void)valid;(void)id;(void)p;(void)n; }
static void _ctrlAck(UsbDsInterface *i) { (void)i;++acks; }
static void _ctrlWrite(UsbDsInterface *i,const void *p,unsigned n) { (void)i;assert(n==sizeof(reply));memcpy(&reply,p,n); }
static Result usbDsInterface_StallCtrl(UsbDsInterface *i) { (void)i;++stalls;return 0; }
static Result usbDsEndpoint_Cancel(UsbDsEndpoint *e) { (void)e;return 0; }
static void trace_emit(unsigned stage,UsbDsInterface *i,Result r,u32 a,u32 b,unsigned f,const void *s,u64 begin,u64 end) {
    (void)i;(void)r;(void)b;(void)f;(void)s;(void)begin;(void)end;
    if(stage==EP0_T_SEQUENCE) { ++sequence_events;sequence_value=a; }
}

/* INSERT_FROZEN_HANDLER */

int main(int argc,char **argv) {
    assert(argc==4);char *end;unsigned long value=strtoul(argv[1],&end,10);
    assert(*argv[1] && !*end && value<=65535);const char *mode=argv[2];
    UsbDsInterface iface={2};UsbSetupPacket setup={0x41,ISO_PROBE_BURST,(u16)value,2,0};
    g_isoStatus.magic=ISO_PROBE_STATUS_MAGIC;g_isoStatus.version=1;
    if(!strcmp(mode,"pending"))g_isoStatus.state=ISO_PROBE_PENDING;
    else if(!strcmp(mode,"retained"))g_isoStatus.state=ISO_PROBE_RETAINED;
    else if(!strcmp(mode,"wrong-interface"))setup.wIndex=1;
    else if(!strcmp(mode,"admission-denied"))admit=false;
    else if(!strcmp(mode,"speed-error"))speed_result=1;
    else if(!strcmp(mode,"post-failed"))post_result=1;
    else assert(!strcmp(mode,"normal"));
    _handleIsoSetup(&iface,&setup);
    bool completion_injected=!strcmp(mode,"normal");
    if(completion_injected) {
        assert(posts==1 && acks==1 && !stalls && sequence_events==1 && sequence_value==value);
        g_isoStatus.state=ISO_PROBE_COMPLETE; /* Injected completion, not hardware. */
        UsbSetupPacket status={0xc1,ISO_PROBE_STATUS,0,2,168};_handleIsoSetup(&iface,&status);
        assert(reply.sequence==value && reply.state==ISO_PROBE_COMPLETE);
    } else if(!strcmp(mode,"post-failed"))assert(posts==1 && g_isoStatus.state==ISO_PROBE_FAILED);
    else assert(posts==0 && sequence_events==0);
    FILE *f=fopen(argv[3],"wb");assert(f);assert(fwrite(posted,1,posts ? 3072 : 0,f)==(posts ? 3072u : 0u));assert(!fclose(f));
    printf("{\"seed\":%lu,\"posts\":%u,\"acks\":%u,\"stalls\":%u,\"trace_sequence\":%u,\"status_sequence\":%u,\"state\":%u,\"completion_injected\":%s,\"hardware_verified\":false}\n",value,posts,acks,stalls,sequence_value,reply.sequence,g_isoStatus.state,completion_injected ? "true" : "false");
}
