#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define EP0_CANDIDATE_NATIVE
#define R_FAILED(x) ((x)!=0)
#define R_SUCCEEDED(x) ((x)==0)
typedef uint32_t Result;
typedef int64_t s64;
typedef uint64_t u64;
typedef uint32_t u32;
typedef struct { unsigned interface_index; } UsbDsInterface;
typedef struct { u32 id,requestedSize,transferredSize,urb_status; } UsbDsReportEntry;
typedef struct { UsbDsReportEntry report[8];u32 report_count; } UsbDsReportData;
typedef struct { unsigned unused; } FsFileSystem;
typedef struct { unsigned unused; } FsFile;
enum { FsOpenMode_Read=1,FsOpenMode_Write=2,FsReadOption_None=0,FsWriteOption_None=0 };
static const char *scenario;
static unsigned fs_open,fs_close,create,open_file,write_file,flush_file,size_file,read_file,closed_count,commit_fs;
static char last_path[96];static uint8_t image[6657];static size_t image_n;static bool opened;
static bool is(const char *s) { return strcmp(scenario,s)==0; }
static Result fsOpenSdCardFileSystem(FsFileSystem *f) { (void)f;fs_open++;return is("fs-open-error") ? 91 : 0; }
static void fsFsClose(FsFileSystem *f) { (void)f;fs_close++; }
static Result fsFsCreateFile(FsFileSystem *f,const char *path,s64 n,u32 option) {
    (void)f;assert(strncmp(path,"/ep0-",5)==0);assert(strlen(path)==81 || strlen(path)==84);strcpy(last_path,path);assert(option==0);create++;
    if(is("create-error") || is("collision")) { image[0]=0x7a;image_n=1;return 92; }
    assert(n>0 && n<=6656);image_n=(size_t)n;memset(image,0,image_n);return 0;
}
static Result fsFsOpenFile(FsFileSystem *f,const char *p,u32 mode,FsFile *out) {
    (void)f;(void)p;(void)out;assert(mode==3);open_file++;
    if(is("file-open-error"))return 93;
    opened=true;return 0;
}
static Result fsFileWrite(FsFile *f,s64 off,const void *p,u64 n,u32 option) {
    (void)f;assert(opened && off==0 && option==0 && n==image_n);write_file++;
    if(is("write-error")) { memcpy(image,p,n/2);return 94; }
    memcpy(image,p,is("silent-short-write") ? n/2 : n);
    if(is("corrupt-write"))image[n-1]^=1;
    return 0;
}
static Result fsFileFlush(FsFile *f) { (void)f;assert(opened);flush_file++;return is("flush-error") ? 95 : 0; }
static Result fsFileGetSize(FsFile *f,s64 *n) {
    (void)f;assert(opened);size_file++;
    if(is("size-error"))return 96;
    *n=(s64)image_n+(is("extra-byte") ? 1 : is("short-size") ? -1 : 0);return 0;
}
static Result fsFileRead(FsFile *f,s64 off,void *p,u64 n,u32 option,u64 *got) {
    (void)f;assert(opened && option==0 && off>=0 && (u64)off+n<=image_n);read_file++;
    if(is("read-error") || (is("late-read-error") && read_file==2))return 97;
    if(is("zero-read")) { *got=0;return 0; }
    if(is("oversize-read")) { *got=n+1;return 0; }
    *got=is("short-read") && n>7 ? 7 : n;memcpy(p,image+off,*got);return 0;
}
static void fsFileClose(FsFile *f) { (void)f;assert(opened);opened=false;closed_count++; }
static Result fsFsCommit(FsFileSystem *f) { (void)f;assert(!opened);commit_fs++;return is("commit-error") ? 98 : 0; }
#include <setjmp.h>
/* INSERT_RUNTIME */
#include "research/usb-ds-iso/device/ep0_candidate_guard.c"
#include "research/usb-ds-iso/device/ep0_cleanup_gate.h"
#include "research/usb-ds-iso/device/ep0_diagnostic_file.h"
static unsigned owner_reads,guard_reads,normal_reads;
static bool poison;
static const Ep0TraceOwner *tracked_owner(void) { owner_reads++;assert(!poison);return Ep0CandidateObservation(); }
static const Ep0GuardObservation *tracked_guard(void) { guard_reads++;assert(!poison);return Ep0CandidateGuardObservation(); }
static const uint8_t *tracked_bytes(size_t *n) { normal_reads++;assert(!poison);return Ep0CandidateBytes(n); }
#define Ep0CandidateObservation tracked_owner
#define Ep0CandidateGuardObservation tracked_guard
#define Ep0CandidateBytes tracked_bytes
#include "research/usb-ds-iso/device/ep0_diagnostic_file.c"
#undef Ep0CandidateObservation
#undef Ep0CandidateGuardObservation
#undef Ep0CandidateBytes
#include "research/usb-ds-iso/device/ep0_candidate_file.c"
/* INSERT_RECIPE */
static Ep0CleanupGate ep0Cleanup;
typedef struct { Result result; } Thread;
static Thread g_videoThread,g_audioThread;
static bool g_running;
static unsigned joins,thread_closes,uvc_closes,core_closes,sm_closes;
static jmp_buf retained;
#define CUR_THREAD_HANDLE 0
#define LOG(...) ((void)0)
static Result threadWaitForExit(Thread *t) { joins++;return t->result; }
static void threadClose(Thread *t) { (void)t;thread_closes++; }
static Result svcGetThreadId(uint64_t *id,unsigned h) { (void)h;*id=22;return is("exporter-error") ? 99:0; }
static void svcSleepThread(uint64_t n) { (void)n;longjmp(retained,1); }
static void UvcDeviceExit(void) { uvc_closes++; }
static void CoreExit(void) { core_closes++; }
static void smExit(void) { sm_closes++; }
/* INSERT_APP_EXIT */
static void native_shutdown(void) {
/* INSERT_SHUTDOWN */
}
static void pending_post(void) {
    UsbDsInterface iface={2};uint8_t setup[8]={0xc1,0x53,0,0,2,0,0xa8,0};
    trace_poll(&iface,0);trace_request(&iface);
    trace_emit(EP0_T_EVENT,&iface,0,0,0,0,NULL,1,1);
    trace_emit(EP0_T_CLEAR,&iface,0,0,0,0,NULL,1,1);
    trace_emit(EP0_T_SETUP,&iface,0,0,0,EP0_TRACE_SETUP_VALID,setup,1,1);
    trace_emit(EP0_T_CTRL_CLEAR_PRE,&iface,0,0,0,EP0_TRACE_IN,NULL,1,1);
    Ep0CandidateObservePost(4,0,true,100);
    static uint8_t payload[32];Ep0CandidateGuardPost(4,0,true,100,payload,sizeof(payload));
    trace_emit(EP0_T_CTRL_POST,&iface,0,32,100,EP0_TRACE_IN|EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,NULL,1,1);
    trace_emit(EP0_T_CTRL_WAIT,&iface,94,0,0,EP0_TRACE_IN,NULL,1,2);
}
int main(int argc,char **argv) {
    assert(argc==4 || argc==5);scenario=argv[1];bool shutdown=!strcmp(argv[2],"shutdown");
    if(is("limits")) {
        uint8_t input[6657];memset(input,0x5a,sizeof(input));
        Ep0DiagnosticFileIo io={0};Ep0SinkIo ops={&io,diagnostic_create_open,diagnostic_write_at,diagnostic_flush,diagnostic_file_size,diagnostic_read_at,diagnostic_close_file,diagnostic_commit};
        Ep0SinkState over={0},zero={0},normal={0},valid={0};
        assert(!ep0_diagnostic_sink_once(&over,&ops,"test",input,6657) && !create);
        assert(!ep0_diagnostic_sink_once(&zero,&ops,"test",input,0) && !create);
        assert(!ep0_sink_once(&normal,&ops,"test",input,6656) && !create);
        assert(ep0_diagnostic_sink_once(&valid,&ops,"/ep0-0000000000000000000000000000000000000000000000000000000000000000.diagnostic.bin",input,6656));
        assert(valid.verified_bytes==6656 && !memcmp(input,image,6656));
        printf("{\"passed\":true,\"cases\":4,\"maximum\":6656,\"oversize_rejected_before_create\":true,\"normal_limit_unchanged\":true}\n");return 0;
    }
    if(argc==5) {
        uint8_t input[6657];FILE *f=fopen(argv[4],"rb");assert(f);size_t n=fread(input,1,sizeof(input),f);assert(n && n<=6656 && feof(f));assert(!fclose(f));
        Ep0DiagnosticFileIo io={0};Ep0SinkIo ops={&io,diagnostic_create_open,diagnostic_write_at,diagnostic_flush,diagnostic_file_size,diagnostic_read_at,diagnostic_close_file,diagnostic_commit};
        Ep0SinkState state={0};bool ok=ep0_diagnostic_sink_once(&state,&ops,"/ep0-0000000000000000000000000000000000000000000000000000000000000000.diagnostic.bin",input,n);
        unsigned calls=create+write_file+read_file+commit_fs;assert(!ep0_diagnostic_sink_once(&state,&ops,"ignored",input,n));assert(calls==create+write_file+read_file+commit_fs && !opened);
        f=fopen(argv[3],"wb");assert(f);assert(fwrite(image,1,image_n,f)==image_n);assert(!fclose(f));
        printf("{\"ok\":%s,\"content_verified\":%s,\"commit_acknowledged\":%s,\"phase\":%u,\"verified_bytes\":%zu,\"size\":%zu,\"no_retry\":true}\n",ok?"true":"false",state.content_verified?"true":"false",state.commit_acknowledged?"true":"false",state.phase,state.verified_bytes,n);return 0;
    }
    uint8_t b[16]={1},s[16]={2};
    bool unstarted=is("unstarted") || is("callback-unstarted");
    if(!unstarted)assert(Ep0CandidateStart(11,1000,0,b,s,ep0CandidateRecipe));
    bool healthy=is("healthy") || is("normal-sink-error");
    if(is("maximum")) {
        for(unsigned i=0;i<16;i++)assert(ep0_owner_post(&storage,11,4,0,true,100+i));
        for(unsigned i=0;i<128;i++)trace_emit(EP0_T_DEVICE_STATE,NULL,0,0,0,EP0_TRACE_ARG0_VALID,NULL,1,1);
        storage.trace.dropped=1; /* Injected maximum-size metadata fixture. */
    } else if(!unstarted && !healthy)pending_post();
    if(is("fault"))Ep0CandidateGuardFault();
    if(!unstarted && !is("live") && !is("callback-live")) { Ep0CandidateRequestStop();assert(Ep0CandidateStop(10)); }
    if(is("video-join-error"))g_videoThread.result=78;
    if(is("audio-join-error"))g_audioThread.result=79;
    if(healthy && is("normal-sink-error"))scenario="write-error";
    bool held=false,ok=false;
    if(shutdown) {
        if(setjmp(retained))held=true;else {
            if(is("callback-live") || is("callback-unstarted"))__appExit();
            else { native_shutdown();__appExit();__appExit(); }
        }
    } else {
        if(!unstarted && !is("live") && !is("not-finished")) (void)Ep0CandidateFinish(22,g_videoThread.result | g_audioThread.result);
        Ep0TraceOwner before=storage;Ep0GuardObservation guard_before=*Ep0CandidateGuardObservation();
        poison=g_videoThread.result || g_audioThread.result;
        ok=Ep0CandidateSaveDiagnostic(is("wrong-exporter") ? 11:22,g_videoThread.result,g_audioThread.result,ep0CandidateRecipe);
        unsigned calls=fs_open+create+open_file+write_file+read_file+commit_fs;
        assert(!Ep0CandidateSaveDiagnostic(is("wrong-exporter") ? 11:22,g_videoThread.result,g_audioThread.result,ep0CandidateRecipe));
        assert(calls==fs_open+create+open_file+write_file+read_file+commit_fs);
        assert(!memcmp(&storage,&before,sizeof(before)) && !memcmp(Ep0CandidateGuardObservation(),&guard_before,sizeof(guard_before)));
        if(poison)assert(!owner_reads && !guard_reads && !normal_reads);
    }
    assert(!opened);size_t n=0;const uint8_t *bytes=Ep0CandidateDiagnosticBytes(&n);
    if(bytes) { FILE *f=fopen(argv[3],"wb");assert(f);assert(fwrite(bytes,1,n,f)==n);assert(!fclose(f)); }
    if(image_n) { char path[1024];assert(strlen(argv[3])+5<sizeof(path));snprintf(path,sizeof(path),"%s.disk",argv[3]);FILE *f=fopen(path,"wb");assert(f);assert(fwrite(image,1,image_n,f)==image_n);assert(!fclose(f)); }
    const Ep0SinkState *o=Ep0CandidateDiagnosticFileObservation();
    printf("{\"ok\":%s,\"held\":%s,\"attempted\":%s,\"phase\":%u,\"content_verified\":%s,\"commit_acknowledged\":%s,\"diagnostic_bytes\":%zu,\"fs_open\":%u,\"fs_close\":%u,\"create\":%u,\"read\":%u,\"commit\":%u,\"file_close\":%u,\"joins\":%u,\"thread_closes\":%u,\"uvc_closes\":%u,\"core_closes\":%u,\"sm_closes\":%u,\"cleanup_phase\":%u,\"pending\":%u,\"fault\":%u,\"owner_reads\":%u,\"path\":\"%s\",\"no_retry\":true}\n",
        ok?"true":"false",held?"true":"false",o->attempted?"true":"false",o->phase,o->content_verified?"true":"false",o->commit_acknowledged?"true":"false",n,fs_open,fs_close,create,read_file,commit_fs,closed_count,joins,thread_closes,uvc_closes,core_closes,sm_closes,atomic_load(&ep0Cleanup.phase),ep0_owner_pending(&storage),storage.fault,owner_reads,last_path);
    return 0;
}
