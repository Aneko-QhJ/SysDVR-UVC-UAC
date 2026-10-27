/* Actual extracted functions; all services, kernel results, thread scheduling
 * and automatic USB close are explicit CPU models. No USB/SD or real threads. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>
#include "research/usb-ds-iso/device/ep0_cleanup_gate.h"
typedef uint32_t Result;typedef unsigned u32;typedef uint8_t u8;
#define R_FAILED(x) ((x)!=0)
#define R_SUCCEEDED(x) ((x)==0)
#define LOG(...) ((void)0)
#define FILE_LOGGING 1
#define UDP_LOGGING 0
#define ISO_PROBE 1
#define R_RET_ON_FAIL(x) do { Result rc=x;if(R_FAILED(rc))return rc; } while(0)
#define R_THROW(x) do { Result r=x;if(R_FAILED(r))fatalThrow(r); } while(0)
#define MAKERESULT(a,b) 99
#define UVC_STATE_DISCONNECTED 0
#define UVC_FORMAT_H264 1
#define MAKEHOSVERSION(a,b,c) ((a)*100+(b)*10+(c))
typedef struct { bool active; } Service;
typedef struct { unsigned unused; } Mutex;
typedef struct { unsigned id; } FsFileSystem;
typedef struct { char number[32]; } SetSysSerialNumber;
typedef struct { unsigned major,minor,micro; } SetSysFirmwareVersion;
typedef struct { bool created,live;unsigned index; } Thread;
typedef void (*ThreadFunc)(void *);
typedef struct { unsigned interface_index;bool active; } UsbDsInterface;
typedef struct { bool active; } UsbDsEndpoint;
typedef struct { unsigned value; } UvcProbeCommitControl;
typedef struct { unsigned vendorId,productId;const char *manufacturer,*product,*serialNumber; } UvcDeviceConfig;
static const char *scenario;static jmp_buf interrupted;
static unsigned fs_refs,fs_init,fs_exit,sd_open,sd_close,log_delete,log_create,serial_init,serial_exit;
static unsigned video_open,audio_open,video_close,audio_close,sm_refs,sm_init,sm_exit,fatals,sleeps;
static Result fatal_result;
static unsigned thread_creates,thread_starts,thread_closes,joins,callback_uvc,callback_core,stop_requests;
static unsigned usb_init,usb_exit,registered,auto_closed,endpoints,descriptor_calls,iface_calls,iso_calls;
static bool mounts[8],usb_active;static Service g_grcdVideo,g_grcdAudio;static Mutex g_grcdBeginMutex;
static UsbDsInterface ifaces[3],*g_isoInterface;static UsbDsEndpoint ep,*g_isoEndpoint;
static unsigned g_videoBuffer[1],g_controlBuffer[1];static bool g_running;
static Ep0CleanupGate ep0Cleanup;static Thread g_videoThread={.index=0},g_audioThread={.index=1};
static u8 g_videoThreadStack[16],g_audioThreadStack[16];
#define VIDEO_THREAD_STACK_SIZE 16
#define AUDIO_THREAD_STACK_SIZE 16
#define STREAM_THREAD_PRIORITY 44
static struct { bool initialized;unsigned lock,streamingMutex,state;void *videoBuffer,*controlBuffer;UvcProbeCommitControl probeControl,commitControl;UsbDsInterface *controlInterface,*streamingInterface; } g_uvcCtx;
static struct { unsigned audioMutex; } g_uacCtx;
static bool is(const char *s) { return !strcmp(scenario,s); }
static void mutexInit(void *m) { (void)m; }
static bool serviceIsActive(Service *s) { return s->active; }
static Result smGetService(Service *s,const char *name) {
    assert(!strcmp(name,"grc:d"));bool video=s==&g_grcdVideo;
    if(video)video_open++;else audio_open++;
    if((video && (is("core-video-error") || is("capture-video-error") || is("app-core-video-error"))) ||
       (!video && (is("core-audio-error") || is("capture-audio-error") || is("retry-partial") || is("core-fs-audio-error") || is("core-sd-audio-error") || is("app-core-audio-error"))))return video ? 71:72;
    s->active=true;return 0;
}
static void serviceClose(Service *s) { if(s->active) { if(s==&g_grcdVideo)video_close++;else audio_close++;s->active=false; } }
static Result fsInitialize(void) { fs_init++;if(is("core-fs-error") || is("core-fs-audio-error"))return 73;fs_refs++;return 0; }
static void fsExit(void) { fs_exit++;if(fs_refs)fs_refs--; /* Modeled no-op if unowned, not a real service guard. */ }
static Result fsOpenSdCardFileSystem(FsFileSystem *s) { sd_open++;if(is("core-sd-error") || is("core-sd-audio-error"))return 74;s->id=sd_open;assert(s->id<8);mounts[s->id]=true;return 0; }
static void fsFsClose(FsFileSystem *s) { assert(mounts[s->id]);mounts[s->id]=false;sd_close++; }
static Result fsFsDeleteFile(FsFileSystem *s,const char *p) { (void)s;assert(!strcmp(p,"/logfile.txt"));log_delete++;return is("log-delete-error") ? 75:0; }
static Result fsFsCreateFile(FsFileSystem *s,const char *p,unsigned n,unsigned opt) { (void)s;assert(!strcmp(p,"/logfile.txt") && !n && !opt);log_create++;return is("log-create-error") ? 76:0; }
static Result setsysInitialize(void) { serial_init++;return is("serial-init-error") || is("app-setsys-error") ? 77:0; }
static void setsysExit(void) { serial_exit++; }
static Result setsysGetSerialNumber(SetSysSerialNumber *s) { strcpy(s->number,"MODEL");return is("serial-get-error") ? 78:0; }
static Result setsysGetFirmwareVersion(SetSysFirmwareVersion *s) { s->major=22;s->minor=5;s->micro=0;return is("app-fw-error") ? 79:0; }
static void hosversionSet(unsigned v) { assert(v==2250); }
static Result smInitialize(void) { sm_init++;if(is("app-sm-error"))return 80;sm_refs++;return 0; }
static void smExit(void) { sm_exit++;if(sm_refs)sm_refs--; }
static void fatalThrow(Result rc) { assert(rc);fatals++;fatal_result=rc;longjmp(interrupted,1); }
static void svcSleepThread(uint64_t n) { sleeps++;if(n<20000000000ULL)longjmp(interrupted,2); }
static Result threadCreate(Thread *t,ThreadFunc f,void *a,void *stack,u32 sz,u32 prio,int cpu) {
    (void)f;(void)a;(void)stack;assert(sz==16 && prio==44 && cpu==-2);thread_creates++;
    if((!t->index && is("video-create-error")) || (t->index && is("audio-create-error")))return 81;
    t->created=true;return 0;
}
static Result threadStart(Thread *t) { thread_starts++;assert(t->created);if((!t->index && is("video-start-error")) || (t->index && is("audio-start-error")))return 82;t->live=true;return 0; }
static void threadClose(Thread *t) { thread_closes++;t->created=false; }
static Result threadWaitForExit(Thread *t) { joins++;t->live=false;return 0; }
static void rwlockInit(unsigned *p) { *p=0; }
static void modelMutexInit(unsigned *p) { *p=0; }
static bool hosversionAtLeast(unsigned a,unsigned b,unsigned c) { (void)a;(void)b;(void)c;return !is("usb-unsupported"); }
static Result usbDsInitialize(void) { usb_init++;if(is("usb-init-error"))return 83;usb_active=true;return 0; }
static void usbDsExit(void) { usb_exit++;usb_active=false;for(unsigned i=0;i<3;i++)if(ifaces[i].active) { ifaces[i].active=false;auto_closed++; }ep.active=false; }
static Result _setupDescriptors5x(const UvcDeviceConfig *c) { (void)c;descriptor_calls++;return is("usb-descriptor-error") ? 84:0; }
static Result _setupInterfaces5x(void) {
    iface_calls++;if(is("usb-vc-error"))return 85;
    ifaces[0].active=true;registered++;g_uvcCtx.controlInterface=&ifaces[0];
    if(is("usb-vs-error"))return 86;
    ifaces[1].active=true;registered++;g_uvcCtx.streamingInterface=&ifaces[1];
    if(is("usb-append-error") || is("usb-video-ep-error"))return 87;
    ep.active=true;endpoints++;return 0;
}
static Result _setupAudioInterfaces5x(void) { assert(false);return 0; }
static Result _setupIsoProbe(void) {
    iso_calls++;if(is("usb-iso-register-error"))return 88;
    ifaces[2].active=true;registered++;g_isoInterface=&ifaces[2];
    if(is("usb-iso-append-error") || is("usb-iso-ep-error"))return 89;
    g_isoEndpoint=&ep;ep.active=true;endpoints++;
    return is("usb-iso-enable-error") ? 90:0;
}
static Result usbDsEnable(void) { return is("usb-enable-error") ? 91:0; }
static void UvcBuildDefaultProbeControl(UvcProbeCommitControl *c,unsigned f) { c->value=f; }
static void Ep0CandidateRequestStop(void) { stop_requests++; }
static void UvcDeviceExit(void) { callback_uvc++; }
/* INSERT_GRCD */
/* INSERT_CAPTURE */
/* INSERT_CORE */
/* INSERT_USB */
/* INSERT_APP_INIT */
/* INSERT_APP_EXIT */
static void VideoStreamThread(void *p) { (void)p; }
static void AudioStreamThread(void *p) { (void)p; }
static void launch_pair(void) {
/* INSERT_LAUNCH */
}
static unsigned mounted(void) { unsigned n=0;for(unsigned i=0;i<8;i++)n+=mounts[i];return n; }
int main(int argc,char **argv) {
    assert(argc==2);const char *name=argv[1];scenario=name;Result rc=0;unsigned exit_reason=0;
    bool core=!strncmp(name,"core-",5) || !strncmp(name,"serial-",7) || !strncmp(name,"log-",4) || is("retry-partial");
    bool usb=!strncmp(name,"usb-",4);
    if(core) {
        rc=CoreInit();if(is("core-reentry"))assert(!CoreInit());
        if(is("retry-partial")) { assert(rc==72);scenario="core-ok";rc=CoreInit(); }
        CoreExit();CoreExit();
    } else if(!strncmp(name,"capture-",8)) { rc=CaptureInitialize(); }
    else if(usb) {
        UvcDeviceConfig config={0};rc=UvcDeviceInitialize(&config);if(is("usb-reentry"))assert(UvcDeviceInitialize(&config)==99);
    } else {
        int signal=setjmp(interrupted);
        if(signal)exit_reason=(unsigned)signal;
        else if(!strncmp(name,"app-",4))__appInit();
        else { assert(!CoreInit());UvcDeviceConfig c={0};assert(!UvcDeviceInitialize(&c));launch_pair(); }
        if(is("audio-start-error") || is("audio-create-error") || is("video-start-error") || is("video-create-error")) {
            int signal=setjmp(interrupted);if(signal)exit_reason=(unsigned)signal;else __appExit();
        }
    }
    /* CoreExit successful body is counted only in this generated fixture. */
    printf("{\"case\":\"%s\",\"result\":%u,\"exit_reason\":%u,\"core_initialized\":%s,\"video_active\":%s,\"audio_active\":%s,"
           "\"video_open\":%u,\"audio_open\":%u,\"video_close\":%u,\"audio_close\":%u,\"fs_init\":%u,\"fs_exit\":%u,\"fs_refs\":%u,\"sd_mounts\":%u,"
           "\"log_delete\":%u,\"log_create\":%u,\"serial_exit\":%u,\"sm_refs\":%u,\"fatals\":%u,\"fatal_result\":%u,\"usb_initialized\":%s,\"usb_active\":%s,\"usb_exit\":%u,\"registered\":%u,\"auto_closed\":%u,"
           "\"video_created\":%s,\"video_live\":%s,\"audio_created\":%s,\"audio_live\":%s,\"thread_creates\":%u,\"thread_starts\":%u,\"thread_closes\":%u,\"joins\":%u,\"callback_uvc\":%u,\"core_exit_body\":%u,\"cleanup_phase\":%u,"
           "\"usb_exit_auto_close_is_model\":true,\"fatal_callback_reachability_verified\":false,\"hardware_verified\":false}\n",
           name,rc,exit_reason,g_coreInitialized?"true":"false",g_grcdVideo.active?"true":"false",g_grcdAudio.active?"true":"false",video_open,audio_open,video_close,audio_close,fs_init,fs_exit,fs_refs,mounted(),log_delete,log_create,serial_exit,sm_refs,fatals,fatal_result,g_uvcCtx.initialized?"true":"false",usb_active?"true":"false",usb_exit,registered,auto_closed,g_videoThread.created?"true":"false",g_videoThread.live?"true":"false",g_audioThread.created?"true":"false",g_audioThread.live?"true":"false",thread_creates,thread_starts,thread_closes,joins,callback_uvc,callback_core,atomic_load(&ep0Cleanup.phase));
    return 0;
}
