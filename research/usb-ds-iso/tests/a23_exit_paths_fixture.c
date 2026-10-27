/* Single-thread native inspection of extracted cleanup functions. Live threads,
 * failed joins and URBs are injected; no runtime callback reachability claim. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#define EP0_CANDIDATE_NATIVE
#define R_FAILED(x) ((x)!=0)
typedef uint32_t Result;
typedef struct { unsigned interface_index; } UsbDsInterface;
typedef struct { unsigned unused; } UsbDsEndpoint;
typedef struct { uint32_t id,urb_status; } UsbDsReportEntry;
typedef struct { UsbDsReportEntry report[8];uint32_t report_count; } UsbDsReportData;
#include "research/usb-ds-iso/device/ep0_candidate.c"
typedef struct { bool live;Result join_rc; } Thread;
static Thread g_videoThread={true,0},g_audioThread={true,0};static bool g_running=true;
static UsbDsInterface interfaces[5],*g_isoInterface=&interfaces[2];static UsbDsEndpoint endpoint,*g_isoEndpoint=&endpoint;
static struct { bool initialized;unsigned state,lock;UsbDsInterface *streamingInterface,*controlInterface; } g_uvcCtx;
static struct { bool initialized,streaming;UsbDsInterface *asInterface,*acInterface; } g_uacCtx;
#define UVC_STATE_DISCONNECTED 0
#define CUR_THREAD_HANDLE 0
#define LOG(...) ((void)0)
static unsigned joins,thread_closes,live_thread_closes,interface_closes,live_interface_closes,pending_interface_closes,ds_exit,core_exit,sm_exit,saves,sleeps;
static bool save_ok=true;static jmp_buf retained;
static Result threadWaitForExit(Thread *t) { joins++;if(!t->join_rc)t->live=false;return t->join_rc; }
static void threadClose(Thread *t) { thread_closes++;if(t->live)live_thread_closes++; }
static void usbDsInterface_Close(UsbDsInterface *i) {
    (void)i;interface_closes++;if(g_videoThread.live || g_audioThread.live)live_interface_closes++;
    if(ep0_owner_pending(Ep0CandidateObservation()))pending_interface_closes++;
}
static void usbDsExit(void) { ds_exit++; }
static void CoreExit(void) { core_exit++; }
static void smExit(void) { sm_exit++; }
static void rwlockWriteLock(unsigned *p) { (void)p; }
static void rwlockWriteUnlock(unsigned *p) { (void)p; }
static Result svcGetThreadId(uint64_t *id,unsigned handle) { (void)handle;*id=22;return 0; }
static bool Ep0CandidateSaveCapture(void) { saves++;return save_ok; }
static void svcSleepThread(uint64_t ticks) { (void)ticks;sleeps++;longjmp(retained,1); }
/* INSERT_DEVICE_EXIT */
/* INSERT_ORIGINAL_JOIN */
/* INSERT_APP_EXIT */
static void original_normal(void) {
/* INSERT_ORIGINAL_NORMAL */
}
static void candidate_normal(void) {
/* INSERT_CANDIDATE_NORMAL */
}
int main(int argc,char **argv) {
    assert(argc==2);const char *name=argv[1];
    g_uvcCtx.initialized=true;g_uvcCtx.controlInterface=&interfaces[0];g_uvcCtx.streamingInterface=&interfaces[1];
    g_uacCtx.initialized=true; /* A23 UAC interfaces are disabled/null. */
    uint8_t boot[16]={1},session[16]={2},recipe[32]={3};assert(Ep0CandidateStart(11,19200000,0,boot,session,recipe));
    bool pending=strstr(name,"pending")!=NULL;
    if(pending)Ep0CandidateObservePost(4,0,true,100);
    if(strstr(name,"video-join-error"))g_videoThread.join_rc=91;
    if(strstr(name,"audio-join-error"))g_audioThread.join_rc=92;
    if(strstr(name,"sink-error"))save_ok=false;
    bool active=!strcmp(name,"callback-live");
    if(!active) { Ep0CandidateRequestStop();assert(Ep0CandidateStop(10)); }
    bool callback=!strncmp(name,"callback",8);
    if(callback && !active)g_videoThread.live=g_audioThread.live=false;
    bool held=false;
    if(setjmp(retained))held=true;
    else if(callback)__appExit();
    else if(!strncmp(name,"original",8)) { original_normal();__appExit(); }
    else { candidate_normal();__appExit(); }
    printf("{\"case\":\"%s\",\"held\":%s,\"joins\":%u,\"thread_closes\":%u,\"live_thread_closes\":%u,"
           "\"interface_closes\":%u,\"live_interface_closes\":%u,\"pending_interface_closes\":%u,\"ds_exit\":%u,"
           "\"core_exit\":%u,\"sm_exit\":%u,\"saves\":%u,\"sleeps\":%u,\"pending\":%u,\"hardware_verified\":false}\n",
           name,held ? "true":"false",joins,thread_closes,live_thread_closes,interface_closes,live_interface_closes,
           pending_interface_closes,ds_exit,core_exit,sm_exit,saves,sleeps,ep0_owner_pending(Ep0CandidateObservation()));
    return 0;
}
