#include "ep0_session_runtime.h"
#include "ep0_session_file.h"
#include "ep0_session_sink.h"
#include <stdio.h>

typedef struct { FsFileSystem fs;FsFile file; } Ep0SessionFileIo;
static Ep0SinkState session_file_sink;
static uint32_t session_file_create_open(void *p,const char *path,size_t n) {
    Ep0SessionFileIo *io=p;
    Result rc=fsFsCreateFile(&io->fs,path,n,0); /* SDK create, no delete/truncate fallback */
    if(R_FAILED(rc))return rc;
    return fsFsOpenFile(&io->fs,path,FsOpenMode_Read|FsOpenMode_Write,&io->file);
}
static uint32_t session_file_write_at(void *p,size_t at,const void *bytes,size_t n) {
    return fsFileWrite(&((Ep0SessionFileIo *)p)->file,at,bytes,n,FsWriteOption_None);
}
static uint32_t session_file_flush(void *p) { return fsFileFlush(&((Ep0SessionFileIo *)p)->file); }
static uint32_t session_file_file_size(void *p,uint64_t *size) {
    s64 n=0;Result rc=fsFileGetSize(&((Ep0SessionFileIo *)p)->file,&n);
    if(R_SUCCEEDED(rc))*size=(uint64_t)n;
    return rc;
}
static uint32_t session_file_read_at(void *p,size_t at,void *bytes,size_t n,size_t *got) {
    u64 count=0;Result rc=fsFileRead(&((Ep0SessionFileIo *)p)->file,at,bytes,n,FsReadOption_None,&count);
    if(R_SUCCEEDED(rc))*got=(size_t)count;
    return rc;
}
static void session_file_close_file(void *p) { fsFileClose(&((Ep0SessionFileIo *)p)->file); }
static uint32_t session_file_commit(void *p) { return fsFsCommit(&((Ep0SessionFileIo *)p)->fs); }
const Ep0SinkState *Ep0SessionFileObservation(void) { return &session_file_sink; }
bool Ep0SessionSaveJoined(uint32_t video,uint32_t audio) {
    /* Call only after old DIA1 save succeeded. Failed joins precede all reads. */
    if(video || audio)return false;
    if(session_file_sink.attempted)return false;
    size_t n=0;const uint8_t *bytes=Ep0SessionBytes(&n);
    if(!bytes || n<EP0_REL_HEADER || n>EP0_REL_MAX || memcmp(bytes,"EP0REL1\0",8) ||
       !(bytes[16]&16) || !(bytes[16]&8) || !(bytes[16]&64) ||
       bytes[72]!=EP0_SINK_ACKNOWLEDGED || !(bytes[80]&8) || ep0_rel_u64(bytes+36))return false;
    char path[96],nonce[65];static const char hex[]="0123456789abcdef";
    for(unsigned i=0;i<32;i++) { uint8_t x=bytes[112+i];nonce[2*i]=hex[x>>4];nonce[2*i+1]=hex[x&15]; }
    nonce[64]=0;(void)snprintf(path,sizeof(path),"/ep0-%s.session.bin",nonce);
    Ep0SessionFileIo io={0};Result rc=fsOpenSdCardFileSystem(&io.fs);
    if(R_FAILED(rc)) { session_file_sink.attempted=true;session_file_sink.phase=EP0_SINK_CREATE;session_file_sink.result=rc;return false; }
    Ep0SinkIo ops={&io,session_file_create_open,session_file_write_at,session_file_flush,session_file_file_size,session_file_read_at,session_file_close_file,session_file_commit};
    bool ok=ep0_session_sink_once(&session_file_sink,&ops,path,bytes,n);
    fsFsClose(&io.fs);return ok;
}
