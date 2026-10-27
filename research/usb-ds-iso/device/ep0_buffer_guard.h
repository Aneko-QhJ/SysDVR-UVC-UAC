#pragma once
/* Offline conservative policy. Ranges/terminal statuses are caller observations,
 * not authenticated DMA ownership. All spans share the existing 16-slot budget. */
#include "ep0_trace_owner.h"
typedef struct { uintptr_t begin;size_t length;uint32_t id;uint8_t channel,known; } Ep0BufferSpan;
enum { EP0_BG_OK,EP0_BG_OWNER,EP0_BG_FAULT,EP0_BG_RANGE,EP0_BG_CAPACITY,EP0_BG_UNTRACKED,EP0_BG_OVERLAP };
static inline bool ep0_bg_range(uintptr_t begin,size_t n) { return begin && n<=UINTPTR_MAX-begin; }
static inline bool ep0_bg_overlap(uintptr_t a,size_t an,uintptr_t b,size_t bn) {
    if(!an && !bn)return a==b;
    if(!an)return a>=b && a<b+bn;
    if(!bn)return b>=a && b<a+an;
    return a<b+bn && b<a+an;
}
static inline unsigned ep0_bg_allow(const Ep0TraceOwner *o,const Ep0BufferSpan spans[EP0_OWNER_SLOTS],
                                    uintptr_t start,size_t n,unsigned reserve) {
    if(!o || !o->writer || o->stopped || o->joined || !o->processing)return EP0_BG_OWNER;
    if(o->fault)return EP0_BG_FAULT;
    if(!spans || !ep0_bg_range(start,n) || n>4096 || !reserve || reserve>EP0_OWNER_SLOTS)return EP0_BG_RANGE;
    if(o->used>EP0_OWNER_SLOTS-reserve)return EP0_BG_CAPACITY;
    for(uint32_t i=0;i<o->used;i++) {
        const Ep0OwnedUrb *u=&o->urbs[i];const Ep0BufferSpan *s=&spans[i];
        if(!u->active)continue;
        if(!s->known || s->id!=u->id || s->channel!=u->channel || !ep0_bg_range(s->begin,s->length))return EP0_BG_UNTRACKED;
        if(ep0_bg_overlap(start,n,s->begin,s->length))return EP0_BG_OVERLAP;
    }
    return EP0_BG_OK;
}
