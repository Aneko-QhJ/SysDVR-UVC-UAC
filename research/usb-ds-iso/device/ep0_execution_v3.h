#pragma once
/* Independent EXE3 sidecar. Inner INI1/OWN2/DIA2 and REL2 remain unchanged.
 * Called by the exporter only after BOTH joins. CRCs/IDs do not authenticate
 * hardware, thread handoff, save results or power-loss durability. */
#include "ep0_session_capture.h"
#include "ep0_candidate_window.h"
#define EP0_EXEC_HEADER 256u
#define EP0_EXEC_MAX (EP0_EXEC_HEADER+EP0_INIT_MAX+EP0_DIAGNOSTIC_MAX)
typedef struct {
    atomic_uint phase; /* 0 unused, 3 publishing, 1 video owner, 2 stopped */
    uint64_t frequency,start,ready,stop;
    uint32_t window_ms,reason;
    bool ready_seen;
} Ep0ExecutionWindow;
static inline uint32_t ep0_exec_u32(const uint8_t *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static inline bool ep0_exec_start(Ep0ExecutionWindow *w,uint64_t start,uint64_t freq,uint32_t ms) {
    if(!w || !freq || ms>60000)return false;
    unsigned expected=0;
    if(!atomic_compare_exchange_strong_explicit(&w->phase,&expected,3,memory_order_acq_rel,memory_order_acquire))return false;
    w->frequency=freq;w->start=start;w->window_ms=ms;
    atomic_store_explicit(&w->phase,1,memory_order_release);return true;
}
static inline bool ep0_exec_ready(Ep0ExecutionWindow *w,uint64_t at) {
    if(!w || atomic_load_explicit(&w->phase,memory_order_acquire)!=1 || w->ready_seen || at<w->start)return false;
    w->ready=at;w->ready_seen=true;return true;
}
static inline bool ep0_exec_stop(Ep0ExecutionWindow *w,uint64_t at,uint32_t reason) {
    if(!w || atomic_load_explicit(&w->phase,memory_order_acquire)!=1 || at<w->start ||
       (w->ready_seen && at<w->ready) || reason<1 || reason>2)return false;
    w->stop=at;w->reason=reason;
    atomic_store_explicit(&w->phase,2,memory_order_release);return true;
}
static inline bool ep0_exec_receipt(const Ep0SinkState *s,size_t n,bool saved) {
    if(!s || s->phase>9 || s->verified_bytes>n || saved!=s->commit_acknowledged)return false;
    if(!s->attempted && (s->phase || s->result || s->file_may_exist || s->content_verified ||
                        s->commit_acknowledged || s->verified_bytes))return false;
    if(s->file_may_exist && !s->attempted)return false;
    if(s->content_verified && (!s->attempted || !s->file_may_exist || s->verified_bytes!=n || s->phase<8))return false;
    if(s->commit_acknowledged && (!s->content_verified || s->phase!=9 || s->result))return false;
    return s->phase!=9 || s->commit_acknowledged;
}
static inline size_t ep0_exec_capture(const Ep0SessionContext *context,const Ep0ExecutionWindow *w,
    const Ep0StartupJournal *journal,unsigned startup_status,uint32_t identity_result,
    uint64_t exporter,uint32_t video,uint32_t audio,unsigned kind,const uint8_t *primary,size_t n,
    const Ep0SinkState *receipt,bool saved,uint8_t *work,uint8_t *out,size_t cap) {
    /* Failed joins precede any context/owner/primary/sink dereference. */
    if(video || audio || !context || !w || !exporter || !primary || !receipt || !out || !work ||
       cap<EP0_EXEC_HEADER || kind<1 || kind>2)return 0;
    size_t header=kind==1 ? 112:128,maximum=kind==1 ? EP0_CAPTURE_MAX:EP0_DIAGNOSTIC_MAX;
    if(n<header || n>maximum || atomic_load_explicit(&context->phase,memory_order_acquire)!=2 ||
       atomic_load_explicit(&w->phase,memory_order_acquire)!=2 ||
       memcmp(primary,kind==1 ? "EP0OWN2\0":"EP0DIA2\0",8) ||
       memcmp(primary+48,context->recipe,32) || ep0_rel_u64(primary+32)!=context->ep0_writer ||
       ep0_rel_u64(primary+40)!=exporter || (context->startup_writer && exporter!=context->startup_writer) ||
       !ep0_exec_receipt(receipt,n,saved))return 0;
    Ep0CandidateWindow check={0};
    if(!ep0_window_init(&check,w->start,w->frequency,w->window_ms) ||
       (w->reason==1 && !ep0_window_expired(&check,w->stop)))return 0;
    size_t trace_at=header+(size_t)ep0_exec_u32(primary+20)*16;
    if(trace_at>n || n-trace_at<EP0_TRACE_HEADER_BYTES || memcmp(primary+trace_at,"EP0TRC2\0",8) ||
       memcmp(primary+trace_at+64,context->boot,16) || memcmp(primary+trace_at+80,context->session,16) ||
       ep0_rel_u64(primary+trace_at+40)!=w->frequency || ep0_rel_u64(primary+trace_at+48)>w->start ||
       ep0_rel_u64(primary+trace_at+56)!=w->stop)return 0;
    if(!ep0_init_range((uintptr_t)out,cap) || !ep0_init_range((uintptr_t)work,EP0_INIT_MAX) ||
       !ep0_init_range((uintptr_t)primary,n) || ep0_init_overlap((uintptr_t)out,cap,(uintptr_t)primary,n) ||
       ep0_init_overlap((uintptr_t)out,cap,(uintptr_t)work,EP0_INIT_MAX))return 0;
    const void *inputs[]={context,w,receipt,journal};
    const size_t sizes[]={sizeof(*context),sizeof(*w),sizeof(*receipt),sizeof(*journal)};
    for(unsigned i=0;i<4;i++)if(inputs[i] &&
       (ep0_init_overlap((uintptr_t)out,cap,(uintptr_t)inputs[i],sizes[i]) ||
        ep0_init_overlap((uintptr_t)work,EP0_INIT_MAX,(uintptr_t)inputs[i],sizes[i])))return 0;
    if(ep0_init_overlap((uintptr_t)work,EP0_INIT_MAX,(uintptr_t)primary,n))return 0;
    size_t ini=ep0_startup_snapshot(journal,work,EP0_INIT_MAX);
    if(ini) {
        if(startup_status!=2 || identity_result || ep0_rel_u64(work+32)!=context->startup_writer ||
           memcmp(work+40,context->recipe,32))return 0;
    } else if(startup_status!=3 || context->startup_writer)return 0;
    if(cap<EP0_EXEC_HEADER+ini+n)return 0;
    memset(out,0,EP0_EXEC_HEADER);memcpy(out,"EP0EXE3",7);
    ep0_trace_u16(out+8,3);ep0_trace_u16(out+10,EP0_EXEC_HEADER);
    ep0_trace_u16(out+12,EP0_INIT_MAX);ep0_trace_u16(out+14,EP0_DIAGNOSTIC_MAX);
    ep0_trace_u32(out+16,27u|(w->ready_seen ? 4u:0u));ep0_trace_u32(out+20,kind);
    ep0_trace_u32(out+24,(uint32_t)ini);ep0_trace_u32(out+28,(uint32_t)n);
    ep0_trace_u32(out+32,receipt->phase);ep0_trace_u32(out+36,receipt->result);
    ep0_trace_u32(out+40,(receipt->attempted?1u:0u)|(receipt->file_may_exist?2u:0u)|
        (receipt->content_verified?4u:0u)|(receipt->commit_acknowledged?8u:0u));
    ep0_trace_u32(out+44,saved?1u:0u);ep0_trace_u64(out+48,receipt->verified_bytes);
    ep0_trace_u64(out+56,w->frequency);ep0_trace_u64(out+64,w->start);
    ep0_trace_u64(out+72,w->ready);ep0_trace_u64(out+80,w->stop);
    ep0_trace_u32(out+88,w->window_ms);ep0_trace_u32(out+92,w->reason);
    ep0_trace_u64(out+96,context->ep0_writer);ep0_trace_u64(out+104,exporter);
    memcpy(out+112,context->boot,16);memcpy(out+128,context->session,16);memcpy(out+144,context->recipe,32);
    ep0_trace_u32(out+192,startup_status);ep0_trace_u32(out+196,identity_result);
    ep0_trace_u64(out+200,context->startup_writer);
    if(ini)memcpy(out+EP0_EXEC_HEADER,work,ini);
    memcpy(out+EP0_EXEC_HEADER+ini,primary,n);
    ep0_trace_u32(out+176,ep0_trace_crc32(out+EP0_EXEC_HEADER,ini));
    ep0_trace_u32(out+180,ep0_trace_crc32(primary,n));
    ep0_trace_u32(out+184,ep0_trace_crc32(out,EP0_EXEC_HEADER));return EP0_EXEC_HEADER+ini+n;
}
bool Ep0ExecutionWindowStarted(uint64_t start,uint64_t frequency,uint32_t window_ms);
bool Ep0ExecutionWindowReady(uint64_t at);
bool Ep0ExecutionWindowStopped(uint64_t at,uint32_t reason);
bool Ep0ExecutionBuildJoined(uint64_t exporter,uint32_t video,uint32_t audio,unsigned kind,bool saved);
const uint8_t *Ep0ExecutionBytes(size_t *size);
bool Ep0ExecutionSaveJoined(uint32_t video,uint32_t audio);
const Ep0SinkState *Ep0ExecutionFileObservation(void);
