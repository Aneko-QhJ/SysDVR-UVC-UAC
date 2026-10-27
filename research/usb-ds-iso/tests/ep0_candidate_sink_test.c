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
static uint8_t image[6641];static size_t image_n;static bool opened;
static bool is(const char *s) { return strcmp(scenario,s)==0; }
static Result fsOpenSdCardFileSystem(FsFileSystem *f) { (void)f;fs_open++;return is("fs-open-error") ? 91 : 0; }
static void fsFsClose(FsFileSystem *f) { (void)f;fs_close++; }
static Result fsFsCreateFile(FsFileSystem *f,const char *path,s64 n,u32 option) {
    (void)f;assert(strncmp(path,"/ep0-",5)==0);assert(strlen(path)==81);assert(option==0);create++;
    if(is("create-error") || is("collision")) { image[0]=0x7a;image_n=1;return 92; }
    assert(n>0 && n<=6640);image_n=(size_t)n;memset(image,0,image_n);return 0;
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
#include "research/usb-ds-iso/device/ep0_candidate.c"
#include "research/usb-ds-iso/device/ep0_candidate_file.c"
#include "research/usb-ds-iso/device/ep0_candidate_window.h"

static unsigned test_windows(void) {
    unsigned tests=0;Ep0CandidateWindow w={0};
    assert(ep0_window_init(&w,100,19200000,0));assert(!ep0_window_expired(&w,UINT64_MAX));
    assert(!ep0_window_init(&w,0,19200000,30000));tests++;
    w=(Ep0CandidateWindow){0};assert(ep0_window_init(&w,100,19200000,1000));
    assert(!ep0_window_expired(&w,19200099));assert(ep0_window_expired(&w,19200100));tests++;
    assert(ep0_window_expired(&w,101));assert(!ep0_window_init(&w,0,1,1));tests++;
    w=(Ep0CandidateWindow){0};assert(ep0_window_init(&w,100,1,1));assert(w.ticks==1);
    assert(ep0_window_expired(&w,101));tests++;
    w=(Ep0CandidateWindow){0};assert(ep0_window_init(&w,100,999,2));assert(w.ticks==2);tests++;
    w=(Ep0CandidateWindow){0};assert(!ep0_window_init(&w,0,0,1000));tests++;
    assert(!ep0_window_init(&w,0,1,60001));tests++;
    assert(!ep0_window_init(&w,0,UINT64_MAX,60000));tests++;
    assert(ep0_window_init(&w,0,UINT64_MAX,1000));assert(w.ticks==UINT64_MAX);tests++;
    w=(Ep0CandidateWindow){0};assert(ep0_window_init(&w,UINT64_MAX-2,1000,5));
    assert(ep0_window_expired(&w,1));tests++;
    assert(!ep0_window_init(NULL,0,1,1));assert(!ep0_window_expired(NULL,0));tests++;
    return tests;
}
int main(int argc,char **argv) {
    assert(argc==3 || argc==4);scenario=argv[1];unsigned windows=test_windows();
    if(argc==4) {
        uint8_t input[6641];FILE *f=fopen(argv[3],"rb");assert(f);
        size_t n=fread(input,1,sizeof(input),f);assert(n && n<=6640 && feof(f));assert(fclose(f)==0);
        Ep0FileIo io={0};Ep0SinkIo ops={&io,create_open,write_at,flush,file_size,read_at,close_file,commit};
        Ep0SinkState state={0};bool ok=ep0_sink_once(&state,&ops,"/ep0-0000000000000000000000000000000000000000000000000000000000000000.capture.bin",input,n);
        unsigned calls=write_file+read_file+create+commit_fs;
        assert(!ep0_sink_once(&state,&ops,"ignored",input,n));
        assert(calls==write_file+read_file+create+commit_fs);assert(!opened);
        f=fopen(argv[2],"wb");assert(f);assert(fwrite(image,1,image_n,f)==image_n);assert(fclose(f)==0);
        printf("{\"ok\":%s,\"phase\":%u,\"content_verified\":%s,\"commit_acknowledged\":%s,\"verified_bytes\":%zu,\"capture_size\":%zu,\"read\":%u,\"commit\":%u,\"debug_sink_input\":true,\"no_retry\":true}\n",
            ok ? "true":"false",state.phase,state.content_verified ? "true":"false",state.commit_acknowledged ? "true":"false",state.verified_bytes,n,read_file,commit_fs);
        return 0;
    }
    uint8_t boot[16]={1},session[16]={2},recipe[32]={3};
    assert(Ep0CandidateStart(11,19200000,10,boot,session,recipe));
    if(is("pending"))Ep0CandidateObservePost(8,0,true,100);
    if(is("fault"))Ep0CandidateObservePost(8,99,false,0);
    if(!is("not-finished")) {
        Ep0CandidateRequestStop();assert(Ep0CandidateStop(20));
        bool finished=Ep0CandidateFinish(22,is("join-error") ? 99 : 0);
        assert(finished==!(is("pending") || is("fault") || is("join-error")));
    }
    size_t n=0;const uint8_t *capture=Ep0CandidateBytes(&n);uint8_t original[6640];
    if(capture)memcpy(original,capture,n);
    bool ok=Ep0CandidateSaveCapture();const Ep0SinkState *s=Ep0CandidateFileObservation();
    unsigned calls=fs_open+fs_close+create+open_file+write_file+read_file+commit_fs;
    assert(!Ep0CandidateSaveCapture());
    assert(calls==fs_open+fs_close+create+open_file+write_file+read_file+commit_fs);
    if(capture)assert(memcmp(original,capture,n)==0);
    bool blocked=is("not-finished") || is("pending") || is("fault") || is("join-error");
    if(blocked)assert(calls==0 && !s->attempted);
    assert(!opened);
    if(image_n) { FILE *f=fopen(argv[2],"wb");assert(f);assert(fwrite(image,1,image_n,f)==image_n);assert(fclose(f)==0); }
    printf("{\"ok\":%s,\"attempted\":%s,\"phase\":%u,\"result\":%u,\"file_may_exist\":%s,\"content_verified\":%s,\"commit_acknowledged\":%s,\"verified_bytes\":%zu,\"capture_size\":%zu,\"fs_open\":%u,\"fs_close\":%u,\"create\":%u,\"write\":%u,\"flush\":%u,\"read\":%u,\"close\":%u,\"commit\":%u,\"window_cases\":%u,\"immutable_capture\":true,\"no_retry\":true}\n",
        ok ? "true":"false",s->attempted ? "true":"false",s->phase,s->result,
        s->file_may_exist ? "true":"false",s->content_verified ? "true":"false",s->commit_acknowledged ? "true":"false",
        s->verified_bytes,n,fs_open,fs_close,create,write_file,flush_file,read_file,closed_count,commit_fs,windows);
    return 0;
}
