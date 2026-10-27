/* Computer-only serialization and actual file adapters. FS, joins, terminal
 * observations and maximal trace metadata are injected; no USB/SD access. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define EP0_CANDIDATE_NATIVE
#define R_SUCCEEDED(x) ((x)==0)
#define R_FAILED(x) ((x)!=0)
typedef uint32_t Result,u32;typedef int64_t s64;typedef uint64_t u64;
typedef struct { unsigned interface_index; } UsbDsInterface;
typedef struct { unsigned unused; } UsbDsReportData;
typedef struct { unsigned unused; } FsFileSystem,FsFile;
enum { FsOpenMode_Read=1,FsOpenMode_Write=2,FsWriteOption_None=0,FsReadOption_None=0 };
#include "ep0_session_capture.h"
#include "ep0_candidate_file.h"
#include "ep0_diagnostic_file.h"
#include "ep0_session_file.h"
static Ep0TraceOwner owner;
static Ep0GuardObservation guard;
static Ep0AdmissionObservation admission;
static Ep0StartupJournal journal;
static Ep0SessionContext context;
static Ep0SessionWork work;
static uint8_t normal_bytes[EP0_CAPTURE_MAX],dia_bytes[EP0_DIAGNOSTIC_MAX],rel_bytes[EP0_REL_MAX];
static uint8_t recipe[32]={3},boot[16]={1},session[16]={2};
static size_t normal_n,dia_n,rel_n;
static bool normal_available,poison;
static unsigned owner_reads,normal_reads,guard_reads,session_reads;
const Ep0TraceOwner *Ep0CandidateObservation(void) { assert(!poison);owner_reads++;return &owner; }
const Ep0GuardObservation *Ep0CandidateGuardObservation(void) { assert(!poison);guard_reads++;return &guard; }
const uint8_t *Ep0CandidateBytes(size_t *n) { assert(!poison);normal_reads++;*n=normal_available?normal_n:0;return *n?normal_bytes:NULL; }
const uint8_t *Ep0SessionBytes(size_t *n) { assert(!poison);session_reads++;*n=rel_n;return rel_n?rel_bytes:NULL; }

static const char *fault;
static unsigned fs_open,fs_close,creates,opens,writes,flushes,sizes,reads,closes,commits;
static bool opened;
static uint8_t image[EP0_REL_MAX+1];
static size_t image_n;
static bool is(const char *s) { return !strcmp(fault,s); }
static Result fsOpenSdCardFileSystem(FsFileSystem *f) { (void)f;fs_open++;return is("fs-open-error")?91:0; }
static void fsFsClose(FsFileSystem *f) { (void)f;fs_close++; }
static Result fsFsCreateFile(FsFileSystem *f,const char *path,s64 n,u32 options) {
    (void)f;assert(path && n>0 && n<=EP0_REL_MAX && options==0);creates++;
    if(is("create-error") || is("collision"))return 92;
    image_n=(size_t)n;memset(image,0,image_n);return 0;
}
static Result fsFsOpenFile(FsFileSystem *f,const char *path,u32 mode,FsFile *file) {
    (void)f;(void)path;(void)file;assert(mode==3);opens++;
    if(is("file-open-error"))return 93;opened=true;return 0;
}
static Result fsFileWrite(FsFile *f,s64 offset,const void *bytes,u64 n,u32 options) {
    (void)f;assert(opened && offset==0 && n==image_n && options==0);writes++;
    memcpy(image,bytes,is("write-error") || is("silent-short-write") ? (size_t)n/2:(size_t)n);
    if(is("corrupt-write"))image[n-1]^=1;
    return is("write-error")?94:0;
}
static Result fsFileFlush(FsFile *f) { (void)f;assert(opened);flushes++;return is("flush-error")?95:0; }
static Result fsFileGetSize(FsFile *f,s64 *n) {
    (void)f;assert(opened);sizes++;
    if(is("size-error"))return 96;
    *n=(s64)image_n+(is("extra-byte")?1:is("short-size")?-1:0);return 0;
}
static Result fsFileRead(FsFile *f,s64 offset,void *bytes,u64 n,u32 options,u64 *got) {
    (void)f;assert(opened && offset>=0 && (u64)offset+n<=image_n && options==0);reads++;
    if(is("read-error") || (is("late-read-error") && reads==2))return 97;
    if(is("zero-read")) { *got=0;return 0; }
    if(is("oversize-read")) { *got=n+1;return 0; }
    *got=is("short-read") && n>7?7:n;memcpy(bytes,image+offset,(size_t)*got);return 0;
}
static void fsFileClose(FsFile *f) { (void)f;assert(opened);opened=false;closes++; }
static Result fsFsCommit(FsFileSystem *f) { (void)f;assert(!opened);commits++;return is("commit-error")?98:0; }
#include "ep0_candidate_file.c"
#include "ep0_diagnostic_file.c"
#include "ep0_session_file.c"

static void append(unsigned stage,unsigned request,unsigned flags,unsigned arg0,unsigned arg1,const uint8_t *setup) {
    Ep0TraceRecord r={.stage=(uint16_t)stage,.interface_index=stage==EP0_T_DEVICE_STATE?255:0,
        .request_id=request,.begin=1,.end=1,.flags=(uint8_t)flags,.arg0=arg0,.arg1=arg1};
    if(setup)memcpy(r.setup,setup,8);
    assert(ep0_trace_append(&owner.trace,&r));
}
static void maxima(void) {
    assert(EP0_CAPTURE_MAX==13040 && EP0_DIAGNOSTIC_MAX==13056 && EP0_REL_MAX==14368);
    assert(ep0_owner_init(&owner,11,1000,0,boot,session));
    /* Sixteen standard GET requests, two six-stage helpers per request:
     * 16*15 rows plus 16 device-state rows = 256. IDs are never reused.
     * This is valid serialization metadata, not an actual handler replay. */
    const uint8_t setup[8]={0x81,10,0,0,0,0,1,0};
    for(unsigned req=1;req<=16;req++) {
        assert(ep0_trace_poll(&owner.trace,0,0));
        append(EP0_T_EVENT,req,0,0,0,NULL);append(EP0_T_CLEAR,req,0,0,0,NULL);
        append(EP0_T_SETUP,req,EP0_TRACE_SETUP_VALID,0,0,setup);
        for(unsigned direction=0;direction<2;direction++) {
            unsigned id=(req-1)*2+direction+100;
            unsigned flags=direction?0:EP0_TRACE_IN;
            append(EP0_T_CTRL_CLEAR_PRE,req,flags,0,0,NULL);
            assert(ep0_owner_post(&owner,11,direction,0,true,id));
            append(EP0_T_CTRL_POST,req,flags|EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,1,id,NULL);
            append(EP0_T_CTRL_WAIT,req,flags|EP0_TRACE_ARG0_VALID,id,0,NULL);
            append(EP0_T_CTRL_CLEAR_DONE,req,flags,0,0,NULL);
            append(EP0_T_CTRL_REPORT,req,flags,0,0,NULL);
            Ep0OwnerReport report={id,3};assert(ep0_owner_reports(&owner,11,direction,0,&report,1));
            append(EP0_T_CTRL_PARSE,req,flags|EP0_TRACE_ARG0_VALID|EP0_TRACE_ARG1_VALID,1,id,NULL);
        }
    }
    for(unsigned i=0;i<16;i++)append(EP0_T_DEVICE_STATE,0,0,0,0,NULL);
    assert(owner.trace.count==256 && owner.used==32 && !ep0_owner_pending(&owner));
    assert(ep0_owner_freeze(&owner,11,10,EP0_TRACE_STOPPED));
    assert(ep0_owner_stop(&owner,11));assert(ep0_owner_handoff(&owner,22,0));
    normal_n=ep0_candidate_capture(&owner,22,recipe,normal_bytes,sizeof(normal_bytes));assert(normal_n==EP0_CAPTURE_MAX);
    owner.fault=1; /* Explicit injected fault for maximum diagnostic envelope. */
    dia_n=ep0_diagnostic_capture(&owner,&guard,22,0,0,recipe,dia_bytes,sizeof(dia_bytes));assert(dia_n==EP0_DIAGNOSTIC_MAX);
    assert(ep0_startup_init(&journal,22,recipe));
    for(unsigned i=0;i<64;i++)assert(ep0_startup_record(&journal,22,EP0_I_FS_INIT,(i&1)?EP0_I_RESULT:EP0_I_CALL,0));
    assert(ep0_startup_seal(&journal,22));assert(ep0_session_publish(&context,22,11,boot,session,recipe));
    Ep0SinkState acknowledged={.phase=EP0_SINK_ACKNOWLEDGED,.attempted=true,.file_may_exist=true,
        .content_verified=true,.commit_acknowledged=true,.verified_bytes=dia_n};
    Ep0SaveReceipt receipt={0};assert(ep0_save_receipt_publish(&receipt,true,&acknowledged,dia_bytes,dia_n));
    rel_n=ep0_session_capture(&journal,&context,2,0,recipe,true,0,0,22,&owner,&guard,&admission,true,&receipt,&work,rel_bytes,sizeof(rel_bytes));
    assert(rel_n==EP0_REL_MAX);
}
static void save(const char *prefix,const char *suffix,const void *bytes,size_t n) {
    char path[1024];assert(snprintf(path,sizeof(path),"%s.%s",prefix,suffix)<(int)sizeof(path));
    FILE *f=fopen(path,"wb");assert(f);assert(fwrite(bytes,1,n,f)==n);assert(!fclose(f));
}
int main(int argc,char **argv) {
    assert(argc==4);const char *kind=argv[1];fault=argv[2];maxima();
    if(!strcmp(kind,"serialize")) {
        static uint8_t output[EP0_REL_MAX];memset(output,0xa5,sizeof(output));
        owner.fault=0;assert(!ep0_candidate_capture(&owner,22,recipe,output,normal_n-1));
        owner.fault=1;assert(!ep0_diagnostic_capture(&owner,&guard,22,0,0,recipe,output,dia_n-1));
        assert(!ep0_session_capture(&journal,&context,2,0,recipe,true,0,0,22,&owner,&guard,&admission,false,NULL,&work,output,rel_n-1));
        for(unsigned i=0;i<sizeof(output);i++)assert(output[i]==0xa5);
        Ep0SaveReceipt invalid={0};uint8_t first=dia_bytes[6];dia_bytes[6]='1';
        Ep0SinkState state={0};assert(!ep0_save_receipt_publish(&invalid,true,&state,dia_bytes,dia_n));dia_bytes[6]=first;
        assert(!atomic_load(&invalid.phase));
        Ep0FileIo io={0};Ep0SinkIo ops={&io,create_open,write_at,flush,file_size,read_at,close_file,commit};
        Ep0SinkState normal_over={0},normal_zero={0},dia_over={0},rel_over={0},rel_short={0},old_rel={0};
        assert(!ep0_sink_once(&normal_over,&ops,"unused",normal_bytes,normal_n+1));
        assert(!ep0_sink_once(&normal_zero,&ops,"unused",normal_bytes,0));
        assert(!ep0_diagnostic_sink_once(&dia_over,&ops,"unused",dia_bytes,dia_n+1));
        assert(!ep0_session_sink_once(&rel_over,&ops,"unused",rel_bytes,rel_n+1));
        assert(!ep0_session_sink_once(&rel_short,&ops,"unused",(void*)1,EP0_REL_HEADER-1));
        uint8_t version=rel_bytes[6];rel_bytes[6]='1';
        assert(!ep0_session_sink_once(&old_rel,&ops,"unused",rel_bytes,rel_n));rel_bytes[6]=version;
        assert(!creates && !fs_open);
        save(argv[3],"ownership.bin",normal_bytes,normal_n);save(argv[3],"diagnostic.bin",dia_bytes,dia_n);
        save(argv[3],"session.bin",rel_bytes,rel_n);
        printf("{\"normal\":%zu,\"diagnostic\":%zu,\"session\":%zu,\"one_short_untouched\":true,"
            "\"old_receipt_rejected\":true,\"sink_limit_rejections_before_create\":6}\n",normal_n,dia_n,rel_n);return 0;
    }
    image[0]=0x7a;image_n=1;
    bool ok=false;const Ep0SinkState *state=NULL;
    uint32_t normal_crc=ep0_trace_crc32(normal_bytes,normal_n),dia_crc=ep0_trace_crc32(dia_bytes,dia_n),rel_crc=ep0_trace_crc32(rel_bytes,rel_n);
    unsigned video=is("video-join-error")?78:0,audio=is("audio-join-error")?79:0;
    if(!strcmp(kind,"normal")) {
        owner.fault=0;normal_available=true;
        ok=Ep0CandidateSaveCapture();state=Ep0CandidateFileObservation();
        unsigned before=fs_open+creates+writes+reads+commits;
        assert(!Ep0CandidateSaveCapture());assert(before==fs_open+creates+writes+reads+commits);
    } else if(!strcmp(kind,"diagnostic")) {
        poison=video || audio;
        ok=Ep0CandidateSaveDiagnostic(22,video,audio,recipe);state=Ep0CandidateDiagnosticFileObservation();
        unsigned before=fs_open+creates+writes+reads+commits;
        assert(!Ep0CandidateSaveDiagnostic(22,video,audio,recipe));assert(before==fs_open+creates+writes+reads+commits);
    } else {
        assert(!strcmp(kind,"session"));poison=video || audio;
        ok=Ep0SessionSaveJoined(video,audio);state=Ep0SessionFileObservation();
        unsigned before=fs_open+creates+writes+reads+commits;
        assert(!Ep0SessionSaveJoined(video,audio));assert(before==fs_open+creates+writes+reads+commits);
    }
    assert(!opened);
    if(poison)assert(!owner_reads && !guard_reads && !normal_reads && !session_reads && !fs_open);
    bool expected=is("ok") || is("short-read");assert(ok==expected);
    if(is("collision"))assert(image_n==1 && image[0]==0x7a && !writes);
    if(is("commit-error"))assert(state->content_verified && !state->commit_acknowledged);
    assert(ep0_trace_crc32(normal_bytes,normal_n)==normal_crc && ep0_trace_crc32(dia_bytes,dia_n)==dia_crc && ep0_trace_crc32(rel_bytes,rel_n)==rel_crc);
    if(ok) {
        const uint8_t *expected_bytes=!strcmp(kind,"normal")?normal_bytes:!strcmp(kind,"diagnostic")?dia_bytes:rel_bytes;
        size_t expected_n=!strcmp(kind,"normal")?normal_n:!strcmp(kind,"diagnostic")?dia_n:rel_n;
        assert(image_n==expected_n && !memcmp(image,expected_bytes,image_n));
    }
    /* Preserve partial/corrupt/commit-failed modeled disk images too. */
    if(image_n)save(argv[3],"disk.bin",image,image_n);
    printf("{\"kind\":\"%s\",\"fault\":\"%s\",\"ok\":%s,\"image_bytes\":%zu,"
        "\"phase\":%u,\"verified_bytes\":%zu,\"content_verified\":%s,\"commit_acknowledged\":%s,"
        "\"fs_open\":%u,\"create\":%u,\"write\":%u,\"read\":%u,\"close\":%u,\"commit\":%u,\"no_retry\":true}\n",
        kind,fault,ok?"true":"false",image_n,state->phase,state->verified_bytes,
        state->content_verified?"true":"false",state->commit_acknowledged?"true":"false",
        fs_open,creates,writes,reads,closes,commits);
}
