#pragma once
/* Independent diagnostic size policy; earlier normal sink stays sealed. */
#include "ep0_candidate_sink.h"
#include "ep0_diagnostic_capture.h"
static inline bool ep0_diagnostic_sink_once(Ep0SinkState *s,const Ep0SinkIo *io,
                                  const char *path,const uint8_t *bytes,size_t n) {
    if(!s || s->attempted)return false;
    s->attempted=true;s->phase=EP0_SINK_INPUT;
    if(!io || !path || !path[0] || !bytes || !n || n>EP0_DIAGNOSTIC_MAX ||
       !io->create_open || !io->write || !io->flush || !io->size ||
       !io->read || !io->close || !io->commit)return false;
    s->phase=EP0_SINK_CREATE;s->file_may_exist=true;
    s->result=io->create_open(io->context,path,n);
    if(s->result)return false; /* create_open closes a handle on its own failure. */
    s->phase=EP0_SINK_WRITE;s->result=io->write(io->context,0,bytes,n);
    if(s->result)goto failed;
    s->phase=EP0_SINK_FLUSH;s->result=io->flush(io->context);
    if(s->result)goto failed;
    uint64_t size=0;s->phase=EP0_SINK_SIZE;
    s->result=io->size(io->context,&size);
    if(s->result || size!=n)goto failed;
    uint8_t check[256];size_t offset=0;
    while(offset<n) {
        size_t want=n-offset;if(want>sizeof(check))want=sizeof(check);
        size_t got=0;s->phase=EP0_SINK_READ;
        s->result=io->read(io->context,offset,check,want,&got);
        if(s->result || !got || got>want)goto failed;
        s->phase=EP0_SINK_COMPARE;
        if(memcmp(check,bytes+offset,got))goto failed;
        offset+=got;s->verified_bytes=offset;
    }
    s->content_verified=true;io->close(io->context);
    s->phase=EP0_SINK_COMMIT;s->result=io->commit(io->context);
    if(s->result)return false; /* retain file AND immutable capture, never retry */
    s->commit_acknowledged=true;s->phase=EP0_SINK_ACKNOWLEDGED;return true;
failed:
    io->close(io->context);return false;
}
