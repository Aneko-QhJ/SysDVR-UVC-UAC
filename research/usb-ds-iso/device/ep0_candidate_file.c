#include "ep0_candidate.h"
#include "ep0_candidate_file.h"
#include <stdio.h>

typedef struct { FsFileSystem fs;FsFile file; } Ep0FileIo;
static Ep0SinkState sink;
static uint32_t create_open(void *p,const char *path,size_t n) {
    Ep0FileIo *io=p;
    Result rc=fsFsCreateFile(&io->fs,path,n,0); /* SDK create, no delete/truncate fallback */
    if(R_FAILED(rc))return rc;
    return fsFsOpenFile(&io->fs,path,FsOpenMode_Read|FsOpenMode_Write,&io->file);
}
static uint32_t write_at(void *p,size_t at,const void *bytes,size_t n) {
    return fsFileWrite(&((Ep0FileIo *)p)->file,at,bytes,n,FsWriteOption_None);
}
static uint32_t flush(void *p) { return fsFileFlush(&((Ep0FileIo *)p)->file); }
static uint32_t file_size(void *p,uint64_t *size) {
    s64 n=0;Result rc=fsFileGetSize(&((Ep0FileIo *)p)->file,&n);
    if(R_SUCCEEDED(rc))*size=(uint64_t)n;
    return rc;
}
static uint32_t read_at(void *p,size_t at,void *bytes,size_t n,size_t *got) {
    u64 count=0;Result rc=fsFileRead(&((Ep0FileIo *)p)->file,at,bytes,n,FsReadOption_None,&count);
    if(R_SUCCEEDED(rc))*got=(size_t)count;
    return rc;
}
static void close_file(void *p) { fsFileClose(&((Ep0FileIo *)p)->file); }
static uint32_t commit(void *p) { return fsFsCommit(&((Ep0FileIo *)p)->fs); }
const Ep0SinkState *Ep0CandidateFileObservation(void) { return &sink; }
bool Ep0CandidateSaveCapture(void) {
    size_t n=0;const uint8_t *bytes=Ep0CandidateBytes(&n);
    const Ep0TraceOwner *o=Ep0CandidateObservation();
    /* Crucially, rejected ownership reaches NO filesystem API. */
    if(!bytes || !n || !o->joined || !o->stopped || !o->exporter ||
       o->processing || o->fault || ep0_owner_pending(o) || sink.attempted)return false;
    char path[96];char nonce[65];static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<32;i++) {
        uint8_t x=i<16 ? o->trace.boot_id[i] : o->trace.session_id[i-16];
        nonce[i*2]=hex[x>>4];nonce[i*2+1]=hex[x&15];
    }
    nonce[64]=0;(void)snprintf(path,sizeof(path),"/ep0-%s.capture.bin",nonce);
    Ep0FileIo io={0};Result rc=fsOpenSdCardFileSystem(&io.fs);
    if(R_FAILED(rc)) { sink.attempted=true;sink.phase=EP0_SINK_CREATE;sink.result=rc;return false; }
    Ep0SinkIo ops={&io,create_open,write_at,flush,file_size,read_at,close_file,commit};
    bool ok=ep0_sink_once(&sink,&ops,path,bytes,n);
    fsFsClose(&io.fs);return ok; /* Core owns fsInitialize/fsExit. */
}
