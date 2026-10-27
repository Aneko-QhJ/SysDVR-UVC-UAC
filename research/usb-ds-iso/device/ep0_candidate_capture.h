#pragma once
#include "ep0_trace_owner.h"
#define EP0_CAPTURE_HEADER 112u
#define EP0_CAPTURE_ENTRY 16u
#define EP0_CAPTURE_MAX (EP0_CAPTURE_HEADER+EP0_OWNER_SLOTS*EP0_CAPTURE_ENTRY+EP0_TRACE_EXPORT_MAX)

/* Only successful ownership-gated memory exports are wrapped. Explicit endian,
 * source recipe digest, immutable ledger snapshot, CRCs and inner trace identity.
 * Recipe/CRCs are correlation fields, never runtime or hardware authentication. */
static inline size_t ep0_candidate_capture(const Ep0TraceOwner *s,uint64_t exporter,
                                          const uint8_t recipe[32],uint8_t *out,size_t cap) {
    if(!s || !out || !recipe || !ep0_trace_nonzero(recipe,32) || s->used>EP0_OWNER_SLOTS ||
       s->trace.count>EP0_TRACE_CAPACITY)return 0;
    size_t ledger=s->used*EP0_CAPTURE_ENTRY;
    size_t offset=EP0_CAPTURE_HEADER+ledger;
    size_t needed=offset+EP0_TRACE_HEADER_BYTES+s->trace.count*EP0_TRACE_RECORD_BYTES;
    if(cap<needed)return 0;
    size_t trace=ep0_owner_export(s,exporter,out+offset,cap-offset);if(!trace)return 0;
    memset(out,0,offset);memcpy(out,"EP0OWN1",7);
    ep0_trace_u16(out+8,1);ep0_trace_u16(out+10,EP0_CAPTURE_HEADER);
    ep0_trace_u16(out+12,EP0_CAPTURE_ENTRY);ep0_trace_u16(out+14,EP0_OWNER_SLOTS);
    ep0_trace_u32(out+16,1);ep0_trace_u32(out+20,s->used);
    ep0_trace_u32(out+24,s->fault);ep0_trace_u32(out+28,ep0_owner_pending(s));
    ep0_trace_u64(out+32,s->writer);ep0_trace_u64(out+40,s->exporter);memcpy(out+48,recipe,32);
    ep0_trace_u32(out+80,(uint32_t)trace);ep0_trace_u32(out+96,s->unmatched);
    for(uint32_t i=0;i<s->used;i++) {
        uint8_t *p=out+EP0_CAPTURE_HEADER+i*EP0_CAPTURE_ENTRY;
        p[0]=s->urbs[i].channel;p[1]=s->urbs[i].active;
        ep0_trace_u32(p+4,s->urbs[i].id);ep0_trace_u32(p+8,s->urbs[i].status);
    }
    ep0_trace_u32(out+84,ep0_trace_crc32(out+EP0_CAPTURE_HEADER,ledger));
    ep0_trace_u32(out+88,ep0_trace_crc32(out+offset,trace));
    ep0_trace_u32(out+92,ep0_trace_crc32(out,EP0_CAPTURE_HEADER));return offset+trace;
}
