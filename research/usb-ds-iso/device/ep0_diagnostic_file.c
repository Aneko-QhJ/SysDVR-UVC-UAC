#include "ep0_candidate.h"
#include "ep0_diagnostic_file.h"
#include <stdio.h>

typedef struct { FsFileSystem fs;FsFile file; } Ep0DiagnosticFileIo;
static Ep0SinkState diagnostic_sink;
static uint32_t diagnostic_create_open(void *p,const char *path,size_t n) {
    Ep0DiagnosticFileIo *io=p;
    Result rc=fsFsCreateFile(&io->fs,path,n,0); /* SDK create, no delete/truncate fallback */
    if(R_FAILED(rc))return rc;
    return fsFsOpenFile(&io->fs,path,FsOpenMode_Read|FsOpenMode_Write,&io->file);
}
static uint32_t diagnostic_write_at(void *p,size_t at,const void *bytes,size_t n) {
    return fsFileWrite(&((Ep0DiagnosticFileIo *)p)->file,at,bytes,n,FsWriteOption_None);
}
static uint32_t diagnostic_flush(void *p) { return fsFileFlush(&((Ep0DiagnosticFileIo *)p)->file); }
static uint32_t diagnostic_file_size(void *p,uint64_t *size) {
    s64 n=0;Result rc=fsFileGetSize(&((Ep0DiagnosticFileIo *)p)->file,&n);
    if(R_SUCCEEDED(rc))*size=(uint64_t)n;
    return rc;
}
static uint32_t diagnostic_read_at(void *p,size_t at,void *bytes,size_t n,size_t *got) {
    u64 count=0;Result rc=fsFileRead(&((Ep0DiagnosticFileIo *)p)->file,at,bytes,n,FsReadOption_None,&count);
    if(R_SUCCEEDED(rc))*got=(size_t)count;
    return rc;
}
static void diagnostic_close_file(void *p) { fsFileClose(&((Ep0DiagnosticFileIo *)p)->file); }
static uint32_t diagnostic_commit(void *p) { return fsFsCommit(&((Ep0DiagnosticFileIo *)p)->fs); }
static uint8_t diagnostic_bytes[EP0_DIAGNOSTIC_MAX];
static size_t diagnostic_size;
const Ep0SinkState *Ep0CandidateDiagnosticFileObservation(void) { return &diagnostic_sink; }
const uint8_t *Ep0CandidateDiagnosticBytes(size_t *size) {
    if(size)*size=diagnostic_size;
    return diagnostic_size ? diagnostic_bytes : NULL;
}
bool Ep0CandidateSaveDiagnostic(uint64_t exporter,uint32_t video_join,uint32_t audio_join,const uint8_t recipe[32]) {
    /* Reject failed joins BEFORE observing possibly live owner/guard storage. */
    if(video_join || audio_join || !exporter || !recipe || diagnostic_sink.attempted)return false;
    size_t normal_size=0;
    if(Ep0CandidateBytes(&normal_size) || normal_size)return false;
    const Ep0TraceOwner *o=Ep0CandidateObservation();
    const Ep0GuardObservation *g=Ep0CandidateGuardObservation();
    diagnostic_size=ep0_diagnostic_capture(o,g,exporter,video_join,audio_join,recipe,diagnostic_bytes,sizeof(diagnostic_bytes));
    if(!diagnostic_size)return false;
    char path[96],nonce[65];static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<32;i++) {
        uint8_t x=i<16 ? o->trace.boot_id[i] : o->trace.session_id[i-16];
        nonce[2*i]=hex[x>>4];nonce[2*i+1]=hex[x&15];
    }
    nonce[64]=0;(void)snprintf(path,sizeof(path),"/ep0-%s.diagnostic.bin",nonce);
    Ep0DiagnosticFileIo io={0};Result rc=fsOpenSdCardFileSystem(&io.fs);
    if(R_FAILED(rc)) { diagnostic_sink.attempted=true;diagnostic_sink.phase=EP0_SINK_CREATE;diagnostic_sink.result=rc;return false; }
    Ep0SinkIo ops={&io,diagnostic_create_open,diagnostic_write_at,diagnostic_flush,diagnostic_file_size,diagnostic_read_at,diagnostic_close_file,diagnostic_commit};
    bool ok=ep0_diagnostic_sink_once(&diagnostic_sink,&ops,path,diagnostic_bytes,diagnostic_size);
    fsFsClose(&io.fs);return ok;
}
