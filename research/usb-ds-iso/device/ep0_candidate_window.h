#pragma once
/* Local elapsed window, checked ONLY between synchronous owner calls.
 * Zero disables expiry. There is no interrupt, cancellation or time bound on
 * ProcessRequests; no stop implies that outstanding URBs have terminated. */
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
typedef struct { uint64_t start,ticks;bool initialized,enabled,expired; } Ep0CandidateWindow;
static inline bool ep0_window_init(Ep0CandidateWindow *w,uint64_t start,uint64_t frequency,uint32_t ms) {
    if(!w || w->initialized || !frequency || ms>60000)return false;
    if(!ms) { w->start=start;w->initialized=true;return true; }
    uint64_t q=frequency/1000,r=frequency%1000;
    if(q>UINT64_MAX/ms)return false;
    uint64_t base=q*ms,extra=(r*ms+999)/1000;
    if(base>UINT64_MAX-extra)return false;
    w->start=start;w->ticks=base+extra;w->enabled=true;w->initialized=true;return true;
}
static inline bool ep0_window_expired(Ep0CandidateWindow *w,uint64_t now) {
    if(!w || !w->enabled)return false;
    /* Backwards/wrapped ticks cannot extend a running window indefinitely. */
    if(now<w->start || now-w->start>=w->ticks)w->expired=true;
    return w->expired;
}
