#pragma once
/* Offline diagnostic serialization only. Both real joins must have succeeded
 * BEFORE reading owner/guard. Caller inputs are observations, not authentication.
 * Does not hand off, clear faults, release URBs, authorize cleanup or save files. */
#include "ep0_candidate_guard.h"
#define EP0_DIAGNOSTIC_HEADER 128u
#define EP0_DIAGNOSTIC_ENTRY 16u
#define EP0_DIAGNOSTIC_MAX (EP0_DIAGNOSTIC_HEADER+EP0_OWNER_SLOTS*EP0_DIAGNOSTIC_ENTRY+EP0_TRACE_EXPORT_MAX)
static inline size_t ep0_diagnostic_capture(const Ep0TraceOwner *s,const Ep0GuardObservation *g,
        uint64_t exporter,uint32_t video_join,uint32_t audio_join,const uint8_t recipe[32],uint8_t *out,size_t cap) {
    /* Join failures reject before accessing potentially mutable storage. */
    if(video_join || audio_join || !s || !g || !out || !recipe)return 0;
    if(!s->joined || !s->stopped || s->processing || !exporter || exporter!=s->exporter ||
       exporter==s->writer || !s->writer || s->used>EP0_OWNER_SLOTS || s->fault>1 ||
       s->trace.lifecycle!=2 || s->trace.freeze_reason!=EP0_TRACE_STOPPED ||
       s->trace.count>EP0_TRACE_CAPACITY || !ep0_trace_nonzero(recipe,32) ||
       g->last_reason>EP0_BG_OVERLAP || ((!g->denials)!=(g->last_reason==0)) ||
       (g->denials && !s->fault))return 0;
    uint32_t pending=ep0_owner_pending(s);
    if(!s->fault && !pending && !g->denials && !s->trace.dropped && !s->trace.invalid)return 0;
    for(uint32_t i=0;i<s->used;i++) {
        const Ep0OwnedUrb *u=&s->urbs[i];
        if(u->channel>=EP0_OWNER_CHANNELS || u->active>1 ||
           (!u->active && (u->status<3 || u->status>5)) ||
           (u->active && u->status>=3 && u->status<=5))return 0;
        for(uint32_t j=0;j<i;j++)if(u->channel==s->urbs[j].channel && u->id==s->urbs[j].id)return 0;
    }
    size_t ledger=s->used*EP0_DIAGNOSTIC_ENTRY,offset=EP0_DIAGNOSTIC_HEADER+ledger;
    size_t needed=offset+EP0_TRACE_HEADER_BYTES+s->trace.count*EP0_TRACE_RECORD_BYTES;
    if(cap<needed)return 0;
    uintptr_t target=(uintptr_t)out;
    if(!ep0_bg_range(target,needed) ||
       !ep0_bg_range((uintptr_t)s,sizeof(*s)) || !ep0_bg_range((uintptr_t)g,sizeof(*g)) ||
       !ep0_bg_range((uintptr_t)recipe,32) ||
       ep0_bg_overlap(target,needed,(uintptr_t)s,sizeof(*s)) ||
       ep0_bg_overlap(target,needed,(uintptr_t)g,sizeof(*g)) ||
       ep0_bg_overlap(target,needed,(uintptr_t)recipe,32))return 0;
    size_t trace=ep0_trace_export(&s->trace,out+offset,cap-offset);if(!trace)return 0;
    memset(out,0,offset);memcpy(out,"EP0DIA1",7);
    ep0_trace_u16(out+8,1);ep0_trace_u16(out+10,EP0_DIAGNOSTIC_HEADER);
    ep0_trace_u16(out+12,EP0_DIAGNOSTIC_ENTRY);ep0_trace_u16(out+14,EP0_OWNER_SLOTS);
    ep0_trace_u32(out+16,3); /* simulation AND diagnostic-only */
    ep0_trace_u32(out+20,s->used);ep0_trace_u32(out+24,s->fault);ep0_trace_u32(out+28,pending);
    ep0_trace_u64(out+32,s->writer);ep0_trace_u64(out+40,s->exporter);memcpy(out+48,recipe,32);
    ep0_trace_u32(out+80,(uint32_t)trace);ep0_trace_u32(out+96,s->unmatched);
    ep0_trace_u32(out+100,g->denials);ep0_trace_u32(out+104,g->last_reason);
    ep0_trace_u32(out+108,video_join);ep0_trace_u32(out+112,audio_join);
    ep0_trace_u32(out+116,3); /* stopped AND joined */
    for(uint32_t i=0;i<s->used;i++) {
        uint8_t *p=out+EP0_DIAGNOSTIC_HEADER+i*EP0_DIAGNOSTIC_ENTRY;
        p[0]=s->urbs[i].channel;p[1]=s->urbs[i].active;
        ep0_trace_u32(p+4,s->urbs[i].id);ep0_trace_u32(p+8,s->urbs[i].status);
    }
    ep0_trace_u32(out+84,ep0_trace_crc32(out+EP0_DIAGNOSTIC_HEADER,ledger));
    ep0_trace_u32(out+88,ep0_trace_crc32(out+offset,trace));
    ep0_trace_u32(out+92,ep0_trace_crc32(out,EP0_DIAGNOSTIC_HEADER));return offset+trace;
}
