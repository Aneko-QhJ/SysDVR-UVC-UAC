#pragma once
/* Offline candidate only. A one-shot, exclusive file creation followed by
 * full readback. Result success is an API acknowledgement, not power-loss proof.
 * write follows libnx ABI: success has NO returned byte count. */
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

typedef struct {
    void *context;
    uint32_t (*create_open)(void *,const char *,size_t);
    uint32_t (*write)(void *,size_t,const void *,size_t);
    uint32_t (*flush)(void *);
    uint32_t (*size)(void *,uint64_t *);
    uint32_t (*read)(void *,size_t,void *,size_t,size_t *);
    void (*close)(void *);
    uint32_t (*commit)(void *);
} Ep0SinkIo;
enum { EP0_SINK_UNTRIED,EP0_SINK_INPUT,EP0_SINK_CREATE,EP0_SINK_WRITE,
       EP0_SINK_FLUSH,EP0_SINK_SIZE,EP0_SINK_READ,EP0_SINK_COMPARE,
       EP0_SINK_COMMIT,EP0_SINK_ACKNOWLEDGED };
typedef struct {
    uint32_t phase,result;
    bool attempted,file_may_exist,content_verified,commit_acknowledged;
    size_t verified_bytes;
} Ep0SinkState;

static inline bool ep0_sink_once(Ep0SinkState *s,const Ep0SinkIo *io,
                                  const char *path,const uint8_t *bytes,size_t n) {
    if(!s || s->attempted)return false;
    s->attempted=true;s->phase=EP0_SINK_INPUT;
    if(!io || !path || !path[0] || !bytes || !n || n>6640 ||
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
