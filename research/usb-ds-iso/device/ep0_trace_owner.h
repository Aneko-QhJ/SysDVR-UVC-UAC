#pragma once
/* Offline integration policy, not deployed firmware. Caller supplies thread
 * identities and observed join/report results; these inputs are not authenticated.
 * One writer, no reset, no allocation, locks, USB calls or file I/O.
 * A frozen trace does NOT establish USB buffer ownership. */
#include "ep0_trace.h"

#define EP0_OWNER_SLOTS 16u
#define EP0_OWNER_CHANNELS 9u /* interface * 2 + IN(0)/OUT(1), ISO = 8 */

typedef struct {
    uint32_t id, status;
    uint8_t channel, active;
} Ep0OwnedUrb;
typedef struct { uint32_t id, status; } Ep0OwnerReport;
typedef struct {
    Ep0Trace trace;
    uint64_t writer, exporter;
    uint32_t used, fault, unmatched;
    uint8_t processing, stopped, joined;
    Ep0OwnedUrb urbs[EP0_OWNER_SLOTS];
} Ep0TraceOwner;

static inline bool ep0_owner_writer(const Ep0TraceOwner *s,uint64_t who) {
    return s && who && who==s->writer && !s->stopped && !s->joined;
}
static inline bool ep0_owner_init(Ep0TraceOwner *s,uint64_t writer,uint64_t frequency,
                                  uint64_t start,const uint8_t boot[16],const uint8_t session[16]) {
    if(!s || !writer || s->writer || !ep0_trace_init(&s->trace,frequency,start,boot,session))return false;
    s->writer=writer;return true;
}
static inline bool ep0_owner_enter(Ep0TraceOwner *s,uint64_t who) {
    if(!ep0_owner_writer(s,who))return false;
    if(s->processing) { s->fault=1;return false; }
    s->processing=1;return true;
}
static inline bool ep0_owner_leave(Ep0TraceOwner *s,uint64_t who) {
    if(!ep0_owner_writer(s,who) || !s->processing)return false;
    s->processing=0;return true;
}
/* Observe EVERY post after it returns, independently of trace capacity/freeze.
 * Failed post IPC has no proven ownership outcome here: permanently fail closed.
 * Never reuse a (channel,id) within a session; a late old terminal cannot release
 * a new buffer. Even completed identities consume slots until the session ends. */
static inline bool ep0_owner_post(Ep0TraceOwner *s,uint64_t who,unsigned channel,
                                  uint32_t result,bool id_valid,uint32_t id) {
    if(!ep0_owner_writer(s,who))return false;
    if(channel>=EP0_OWNER_CHANNELS || result || !id_valid || s->used==EP0_OWNER_SLOTS) {
        s->fault=1;return false;
    }
    for(uint32_t i=0;i<s->used;i++)if(s->urbs[i].channel==channel && s->urbs[i].id==id) {
        s->fault=1;return false;
    }
    s->urbs[s->used++]=(Ep0OwnedUrb){.id=id,.channel=(uint8_t)channel,.active=1};return true;
}
/* Report IPC failure leaves all ownership unchanged. Validate the WHOLE batch
 * before acting, including duplicate IDs. A wait/parse/cancel/stall/disconnect
 * return is deliberately not an ownership operation. States 3/4/5 are terminal
 * under the frozen A23 assumption; 1/2 and unknown states keep the buffer active. */
static inline bool ep0_owner_reports(Ep0TraceOwner *s,uint64_t who,unsigned channel,
                                     uint32_t result,const Ep0OwnerReport *r,size_t count) {
    if(!ep0_owner_writer(s,who))return false;
    if(result)return false;
    if(channel>=EP0_OWNER_CHANNELS || count>8 || (count && !r)) { s->fault=1;return false; }
    for(size_t i=0;i<count;i++)for(size_t j=0;j<i;j++)if(r[i].id==r[j].id) {
        s->fault=1;return false;
    }
    for(size_t i=0;i<count;i++) {
        Ep0OwnedUrb *found=NULL;
        for(uint32_t j=0;j<s->used;j++)if(s->urbs[j].channel==channel && s->urbs[j].id==r[i].id) {
            found=&s->urbs[j];break;
        }
        if(!found) { ep0_trace_sat_inc(&s->unmatched);continue; }
        if(!found->active)continue;
        found->status=r[i].status;
        if(r[i].status>=3 && r[i].status<=5)found->active=0;
    }
    return true;
}
static inline uint32_t ep0_owner_pending(const Ep0TraceOwner *s) {
    uint32_t n=0;if(s)for(uint32_t i=0;i<s->used;i++)n+=!!s->urbs[i].active;return n;
}
/* Freeze at a ProcessRequests boundary. The owner may still observe reports,
 * with recording disabled. Freeze does not stop the thread or drain URBs. */
static inline bool ep0_owner_freeze(Ep0TraceOwner *s,uint64_t who,uint64_t at,uint32_t reason) {
    return ep0_owner_writer(s,who) && !s->processing && ep0_trace_freeze(&s->trace,at,reason);
}
/* Last writer action immediately before returning from the owner thread. */
static inline bool ep0_owner_stop(Ep0TraceOwner *s,uint64_t who) {
    if(!ep0_owner_writer(s,who) || s->processing || s->trace.lifecycle!=2)return false;
    s->stopped=1;return true;
}
/* Only call after threadWaitForExit on THIS writer returned success. No polling
 * or USB closure is requested here. A nonzero join result permits no takeover. */
static inline bool ep0_owner_handoff(Ep0TraceOwner *s,uint64_t exporter,uint32_t join_result) {
    if(!s || !exporter || exporter==s->writer || join_result || !s->stopped ||
       s->processing || s->joined || s->trace.lifecycle!=2)return false;
    s->exporter=exporter;s->joined=1;return true;
}
/* Memory serialization only. An FS sink is a separate, still unimplemented
 * operation. Rejected calls leave the caller's output untouched. */
static inline size_t ep0_owner_export(const Ep0TraceOwner *s,uint64_t who,uint8_t *out,size_t capacity) {
    if(!s || !s->joined || !s->stopped || who!=s->exporter || !who ||
       s->processing || s->fault || ep0_owner_pending(s))return 0;
    return ep0_trace_export(&s->trace,out,capacity);
}
