#pragma once
#include "ep0_execution_v3.h"
/* Independent sink: never changes the normal/DIA2/REL2 acceptance policies. */
static inline bool ep0_execution_sink_once(Ep0SinkState *s,const Ep0SinkIo *io,
    const char *path,const uint8_t *bytes,size_t n) {
    if(!s || s->attempted)return false;
    s->attempted=true;s->phase=EP0_SINK_INPUT;
    if(!io || !path || !path[0] || !bytes || n<EP0_EXEC_HEADER || n>EP0_EXEC_MAX ||
       memcmp(bytes,"EP0EXE3\0",8) || !io->create_open || !io->write || !io->flush ||
       !io->size || !io->read || !io->close || !io->commit)return false;
    s->phase=EP0_SINK_CREATE;s->file_may_exist=true;
    s->result=io->create_open(io->context,path,n);
    if(s->result)return false;
    s->phase=EP0_SINK_WRITE;s->result=io->write(io->context,0,bytes,n);
    if(s->result)goto failed;
    s->phase=EP0_SINK_FLUSH;s->result=io->flush(io->context);
    if(s->result)goto failed;
    uint64_t size=0;s->phase=EP0_SINK_SIZE;s->result=io->size(io->context,&size);
    if(s->result || size!=n)goto failed;
    uint8_t check[256];size_t at=0;
    while(at<n) {
        size_t want=n-at;if(want>sizeof(check))want=sizeof(check);
        size_t got=0;s->phase=EP0_SINK_READ;s->result=io->read(io->context,at,check,want,&got);
        if(s->result || !got || got>want)goto failed;
        s->phase=EP0_SINK_COMPARE;if(memcmp(check,bytes+at,got))goto failed;
        at+=got;s->verified_bytes=at;
    }
    s->content_verified=true;io->close(io->context);s->phase=EP0_SINK_COMMIT;
    s->result=io->commit(io->context);if(s->result)return false;
    s->commit_acknowledged=true;s->phase=EP0_SINK_ACKNOWLEDGED;return true;
failed:
    io->close(io->context);return false;
}
