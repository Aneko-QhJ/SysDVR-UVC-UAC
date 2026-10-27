#pragma once
/* Offline prototype. One owner thread initializes, appends, freezes and exports.
 * Storage MUST be zero-initialized. No allocation, clocks, USB, locks or file I/O.
 * No reset/reuse operation: each session gets a fresh storage object.
 * The wire format is explicitly little endian and always labeled simulation.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <limits.h>

#define EP0_TRACE_CAPACITY 128u
#define EP0_TRACE_HEADER_BYTES 128u
#define EP0_TRACE_RECORD_BYTES 48u
#define EP0_TRACE_EXPORT_MAX (EP0_TRACE_HEADER_BYTES+EP0_TRACE_CAPACITY*EP0_TRACE_RECORD_BYTES)
#define EP0_TRACE_SIMULATION 1u
#define EP0_TRACE_SETUP_VALID 1u
#define EP0_TRACE_ARG0_VALID 2u
#define EP0_TRACE_ARG1_VALID 4u
#define EP0_TRACE_IN 8u

enum Ep0TraceStage {
    EP0_T_EVENT=1, EP0_T_CLEAR, EP0_T_SETUP, EP0_T_ISO_ENTER, EP0_T_SPEED,
    EP0_T_SEQUENCE, EP0_T_ISO_POST, EP0_T_CTRL_CLEAR_PRE, EP0_T_CTRL_POST,
    EP0_T_CTRL_WAIT, EP0_T_CTRL_CLEAR_DONE, EP0_T_CTRL_REPORT, EP0_T_CTRL_PARSE,
    EP0_T_ACK, EP0_T_STATUS, EP0_T_GUARD, EP0_T_DEVICE_STATE
};
enum Ep0TraceFreeze { EP0_TRACE_FINISHED=1, EP0_TRACE_STOPPED=2 };
enum Ep0TraceGuard { EP0_G_WRONG_INTERFACE=1, EP0_G_BUSY=2, EP0_G_SPEED=3, EP0_G_NOT_HS=4 };

typedef struct {
    uint64_t begin, end;
    uint32_t ordinal, request_id, result, arg0, arg1;
    uint16_t stage;
    uint8_t interface_index, flags;
    uint8_t setup[8];
} Ep0TraceRecord;
_Static_assert(sizeof(Ep0TraceRecord)==EP0_TRACE_RECORD_BYTES,"trace record layout");

typedef struct {
    uint32_t lifecycle, count, dropped, invalid, freeze_reason;
    uint64_t frequency, start, frozen_at, last_end;
    uint8_t boot_id[16], session_id[16];
    uint16_t polls[4];
    uint32_t last_poll_result[4];
    Ep0TraceRecord records[EP0_TRACE_CAPACITY];
} Ep0Trace;

static inline void ep0_trace_sat_inc(uint32_t *v) { if(*v!=UINT32_MAX)++*v; }
static inline bool ep0_trace_nonzero(const uint8_t *p,size_t n) {
    uint8_t value=0;for(size_t i=0;i<n;i++)value|=p[i];return value!=0;
}
static inline bool ep0_trace_init(Ep0Trace *t,uint64_t frequency,uint64_t start,
                                 const uint8_t boot[16],const uint8_t session[16]) {
    if(!t || t->lifecycle || !frequency || !boot || !session ||
       !ep0_trace_nonzero(boot,16) || !ep0_trace_nonzero(session,16))return false;
    memset(t,0,sizeof(*t));t->frequency=frequency;t->start=start;t->last_end=start;
    memcpy(t->boot_id,boot,16);memcpy(t->session_id,session,16);t->lifecycle=1;
    return true;
}
/* All polls are counted without consuming record slots. Saturated counts mean
 * at least UINT16_MAX; the last native result remains exact. Frozen is immutable. */
static inline bool ep0_trace_poll(Ep0Trace *t,unsigned index,uint32_t result) {
    if(!t || t->lifecycle!=1)return false;
    if(index>=4) { ep0_trace_sat_inc(&t->invalid);return false; }
    if(t->polls[index]!=UINT16_MAX)++t->polls[index];
    t->last_poll_result[index]=result;return true;
}
static inline bool ep0_trace_record_valid(const Ep0TraceRecord *r,uint64_t start,uint64_t last_end) {
    if(!r || r->stage<EP0_T_EVENT || r->stage>EP0_T_DEVICE_STATE || (r->flags&~15u) ||
       r->begin<start || r->end<r->begin || r->end<last_end)return false;
    if(r->stage==EP0_T_DEVICE_STATE) {
        if(r->interface_index!=255 || r->request_id)return false;
    } else if(r->interface_index>=4 || !r->request_id)return false;
    if(!(r->flags&EP0_TRACE_ARG0_VALID) && r->arg0)return false;
    if(!(r->flags&EP0_TRACE_ARG1_VALID) && r->arg1)return false;
    if(!(r->flags&EP0_TRACE_SETUP_VALID) && ep0_trace_nonzero(r->setup,8))return false;
    if((r->flags&EP0_TRACE_SETUP_VALID) && r->stage!=EP0_T_SETUP &&
       r->stage!=EP0_T_ISO_ENTER && r->stage!=EP0_T_GUARD)return false;
    if((r->flags&EP0_TRACE_IN) && (r->stage<EP0_T_CTRL_CLEAR_PRE || r->stage>EP0_T_ACK))return false;
    if(r->stage==EP0_T_SETUP && ((r->result==0)!=(bool)(r->flags&EP0_TRACE_SETUP_VALID)))return false;
    if(r->stage==EP0_T_SPEED && ((r->result==0)!=(bool)(r->flags&EP0_TRACE_ARG0_VALID)))return false;
    if((r->stage==EP0_T_ISO_POST || r->stage==EP0_T_CTRL_POST) &&
       (!(r->flags&EP0_TRACE_ARG0_VALID) || ((r->result==0)!=(bool)(r->flags&EP0_TRACE_ARG1_VALID))))return false;
    if(r->stage==EP0_T_CTRL_PARSE && ((r->result==0)!=(bool)(r->flags&EP0_TRACE_ARG0_VALID)))return false;
    return true;
}
static inline bool ep0_trace_append(Ep0Trace *t,const Ep0TraceRecord *r) {
    if(!t || t->lifecycle!=1)return false;
    if(!ep0_trace_record_valid(r,t->start,t->last_end)) { ep0_trace_sat_inc(&t->invalid);return false; }
    t->last_end=r->end;
    if(t->count==EP0_TRACE_CAPACITY) { ep0_trace_sat_inc(&t->dropped);return false; }
    t->records[t->count]=*r;t->records[t->count].ordinal=t->count+1;++t->count;return true;
}
static inline bool ep0_trace_freeze(Ep0Trace *t,uint64_t at,uint32_t reason) {
    if(!t || t->lifecycle!=1 || at<t->last_end ||
       (reason!=EP0_TRACE_FINISHED && reason!=EP0_TRACE_STOPPED))return false;
    t->frozen_at=at;t->freeze_reason=reason;t->lifecycle=2;return true;
}
static inline void ep0_trace_u16(uint8_t *p,uint16_t v) {
    p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);
}
static inline void ep0_trace_u32(uint8_t *p,uint32_t v) {
    for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));
}
static inline void ep0_trace_u64(uint8_t *p,uint64_t v) {
    for(unsigned i=0;i<8;i++)p[i]=(uint8_t)(v>>(8*i));
}
static inline uint32_t ep0_trace_crc32(const uint8_t *data,size_t size) {
    uint32_t crc=UINT32_MAX;
    for(size_t i=0;i<size;i++) {
        crc^=data[i];for(unsigned j=0;j<8;j++)crc=(crc>>1)^(0xedb88320u & (0u-(crc&1u)));
    }
    return ~crc;
}
/* Export is memory-only, after freeze, outside the recording path. Short outputs
 * and live storage return 0 without touching the caller's output buffer. */
static inline size_t ep0_trace_export(const Ep0Trace *t,uint8_t *out,size_t capacity) {
    if(!t || t->lifecycle!=2 || !out || t->count>EP0_TRACE_CAPACITY)return 0;
    size_t bytes=EP0_TRACE_HEADER_BYTES+t->count*EP0_TRACE_RECORD_BYTES;
    if(capacity<bytes)return 0;
    memset(out,0,bytes);memcpy(out,"EP0TRC1",7);
    ep0_trace_u16(out+8,1);ep0_trace_u16(out+10,EP0_TRACE_HEADER_BYTES);
    ep0_trace_u16(out+12,EP0_TRACE_RECORD_BYTES);ep0_trace_u16(out+14,EP0_TRACE_CAPACITY);
    ep0_trace_u32(out+16,EP0_TRACE_SIMULATION);ep0_trace_u32(out+20,t->count);
    ep0_trace_u32(out+24,t->dropped);ep0_trace_u32(out+28,t->invalid);
    ep0_trace_u32(out+32,t->freeze_reason);
    ep0_trace_u64(out+40,t->frequency);ep0_trace_u64(out+48,t->start);ep0_trace_u64(out+56,t->frozen_at);
    memcpy(out+64,t->boot_id,16);memcpy(out+80,t->session_id,16);
    for(uint32_t i=0;i<t->count;i++) {
        const Ep0TraceRecord *r=&t->records[i];uint8_t *p=out+EP0_TRACE_HEADER_BYTES+i*EP0_TRACE_RECORD_BYTES;
        ep0_trace_u64(p,r->begin);ep0_trace_u64(p+8,r->end);
        ep0_trace_u32(p+16,r->ordinal);ep0_trace_u32(p+20,r->request_id);
        ep0_trace_u32(p+24,r->result);ep0_trace_u32(p+28,r->arg0);ep0_trace_u32(p+32,r->arg1);
        ep0_trace_u16(p+36,r->stage);p[38]=r->interface_index;p[39]=r->flags;memcpy(p+40,r->setup,8);
    }
    ep0_trace_u32(out+96,ep0_trace_crc32(out+EP0_TRACE_HEADER_BYTES,bytes-EP0_TRACE_HEADER_BYTES));
    for(unsigned i=0;i<4;i++) {
        ep0_trace_u16(out+104+i*2,t->polls[i]);ep0_trace_u32(out+112+i*4,t->last_poll_result[i]);
    }
    ep0_trace_u32(out+100,ep0_trace_crc32(out,EP0_TRACE_HEADER_BYTES));return bytes;
}
