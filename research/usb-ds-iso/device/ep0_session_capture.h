#pragma once
/* Independent correlation prototype. Same nonces/IDs are local observations,
 * not authentication. One context publisher, one immutable session lifetime.
 * Sink may be read only when caller confirms its save call has returned. */
#include "ep0_startup_journal.h"
#include "ep0_diagnostic_capture.h"
#include "ep0_request_admission.h"
#include "ep0_candidate_sink.h"
#define EP0_REL_HEADER 192u
#define EP0_REL_MAX (EP0_REL_HEADER+EP0_INIT_MAX+EP0_DIAGNOSTIC_MAX)
typedef struct {
    atomic_uint phase; /* 0 empty, 1 publishing, 2 immutable */
    uint64_t startup_writer,ep0_writer;
    uint8_t boot[16],session[16],recipe[32];
} Ep0SessionContext;
typedef struct { uint8_t startup[EP0_INIT_MAX],diagnostic[EP0_DIAGNOSTIC_MAX]; } Ep0SessionWork;
typedef struct {
    atomic_uint phase; /* One publisher after save returns, then immutable. */
    Ep0SinkState state;uint32_t input_bytes,input_crc;
} Ep0SaveReceipt;
static inline bool ep0_save_receipt_publish(Ep0SaveReceipt *r,bool returned,const Ep0SinkState *state,const uint8_t *input,size_t n) {
    if(!returned || !r || !state || !input || n<EP0_DIAGNOSTIC_HEADER || n>EP0_DIAGNOSTIC_MAX)return false;
    if(!ep0_init_range((uintptr_t)r,sizeof(*r)) || !ep0_init_range((uintptr_t)state,sizeof(*state)) || !ep0_init_range((uintptr_t)input,n) ||
       ep0_init_overlap((uintptr_t)r,sizeof(*r),(uintptr_t)state,sizeof(*state)) || ep0_init_overlap((uintptr_t)r,sizeof(*r),(uintptr_t)input,n) ||
       memcmp(input,"EP0DIA1\0",8))return false;
    unsigned expected=0;
    if(!atomic_compare_exchange_strong_explicit(&r->phase,&expected,1,memory_order_acq_rel,memory_order_acquire))return false;
    r->state=*state;r->input_bytes=(uint32_t)n;r->input_crc=ep0_trace_crc32(input,n);
    atomic_store_explicit(&r->phase,2,memory_order_release);return true;
}
enum { EP0_REL_JOIN_FAILED=1,EP0_REL_NO_CONTEXT=2,EP0_REL_DIA_REJECTED=3 };
static inline bool ep0_session_publish(Ep0SessionContext *c,uint64_t starter,uint64_t writer,
        const uint8_t boot[16],const uint8_t session[16],const uint8_t recipe[32]) {
    if(!c || !ep0_init_range((uintptr_t)c,sizeof(*c)) || !writer || !boot || !session || !recipe ||
       !ep0_trace_nonzero(boot,16) || !ep0_trace_nonzero(session,16) || !ep0_trace_nonzero(recipe,32))return false;
    const void *sources[]={boot,session,recipe};const size_t sizes[]={16,16,32};
    for(unsigned i=0;i<3;i++)if(!ep0_init_range((uintptr_t)sources[i],sizes[i]) ||
        ep0_init_overlap((uintptr_t)c,sizeof(*c),(uintptr_t)sources[i],sizes[i]))return false;
    unsigned expected=0;
    if(!atomic_compare_exchange_strong_explicit(&c->phase,&expected,1,memory_order_acq_rel,memory_order_acquire))return false;
    c->startup_writer=starter;c->ep0_writer=writer;memcpy(c->boot,boot,16);memcpy(c->session,session,16);memcpy(c->recipe,recipe,32);
    atomic_store_explicit(&c->phase,2,memory_order_release);return true;
}
static inline uint64_t ep0_rel_u64(const uint8_t *p) { uint64_t n=0;for(unsigned i=0;i<8;i++)n|=(uint64_t)p[i]<<(8*i);return n; }
static inline bool ep0_rel_alias(const void *a,size_t n,const void *b,size_t m) {
    return b && (!ep0_init_range((uintptr_t)b,m) || ep0_init_overlap((uintptr_t)a,n,(uintptr_t)b,m));
}
static inline size_t ep0_session_capture(const Ep0StartupJournal *j,const Ep0SessionContext *context,
        unsigned startup_status,uint32_t identity_result,const uint8_t recipe[32],bool request_ep0,
        uint32_t video_join,uint32_t audio_join,uint64_t exporter,
        const Ep0TraceOwner *owner,const Ep0GuardObservation *guard,const Ep0AdmissionObservation *admission,
        bool save_returned,const Ep0SaveReceipt *receipt,Ep0SessionWork *work,uint8_t *out,size_t cap) {
    if(!work || !out || !recipe || cap<EP0_REL_HEADER || startup_status>3 ||
       !ep0_trace_nonzero(recipe,32) || ((startup_status==0 || startup_status==1) && identity_result))return 0;
    size_t span=cap<EP0_REL_MAX ? cap:EP0_REL_MAX;
    if(!ep0_init_range((uintptr_t)out,span) || !ep0_init_range((uintptr_t)work,sizeof(*work)) ||
       ep0_rel_alias(out,span,work,sizeof(*work)) || ep0_rel_alias(out,span,j,sizeof(*j)) ||
       ep0_rel_alias(out,span,context,sizeof(*context)) || ep0_rel_alias(out,span,recipe,32) ||
       ep0_rel_alias(work,sizeof(*work),j,sizeof(*j)) || ep0_rel_alias(work,sizeof(*work),context,sizeof(*context)) ||
       ep0_rel_alias(work,sizeof(*work),recipe,32))return 0;
    bool bound=context && atomic_load_explicit(&context->phase,memory_order_acquire)==2;
    uint64_t starter=0,writer=0;uint8_t boot[16]={0},session[16]={0};
    if(bound) {
        if(memcmp(context->recipe,recipe,32))return 0;
        starter=context->startup_writer;writer=context->ep0_writer;memcpy(boot,context->boot,16);memcpy(session,context->session,16);
    }
    size_t ini=ep0_startup_snapshot(j,work->startup,sizeof(work->startup));
    if(ini) {
        uint64_t observed=ep0_rel_u64(work->startup+32);
        if(startup_status!=2 || identity_result || memcmp(work->startup+40,recipe,32) || (bound && starter!=observed))return 0;
        starter=observed;
    } else if(startup_status==2 || (bound && (starter || startup_status!=3)))return 0;
    size_t dia=0;unsigned reason=0;bool with_admission=false,with_sink=false;const Ep0SinkState *sink=NULL;
    /* Failed joins or missing context never dereference any EP0/sink input. */
    if(request_ep0) {
        if(video_join || audio_join)reason=EP0_REL_JOIN_FAILED;
        else if(!bound)reason=EP0_REL_NO_CONTEXT;
        else {
            const void *sources[]={owner,guard,admission,save_returned ? receipt:NULL};
            const size_t sizes[]={sizeof(*owner),sizeof(*guard),sizeof(*admission),sizeof(*receipt)};
            for(unsigned i=0;i<4;i++)if(ep0_rel_alias(out,span,sources[i],sizes[i]) ||
                ep0_rel_alias(work,sizeof(*work),sources[i],sizes[i]))return 0;
            dia=ep0_diagnostic_capture(owner,guard,exporter,video_join,audio_join,recipe,work->diagnostic,sizeof(work->diagnostic));
            if(!dia)reason=EP0_REL_DIA_REJECTED;
            else {
                size_t trace=EP0_DIAGNOSTIC_HEADER+owner->used*EP0_DIAGNOSTIC_ENTRY;
                if(owner->writer!=writer || (starter && exporter!=starter) ||
                   memcmp(work->diagnostic+trace+64,boot,16) || memcmp(work->diagnostic+trace+80,session,16))return 0;
                if(admission) {
                    if(admission->active || admission->largest_request>EP0_TRACE_CAPACITY ||
                       (admission->largest_request>EP0_REQUEST_RECORD_RESERVE && !admission->bound_violations) ||
                       ((admission->trace_refusals || admission->bound_violations) && !owner->fault))return 0;
                    with_admission=true;
                }
                if(save_returned && receipt && atomic_load_explicit(&receipt->phase,memory_order_acquire)==2) {
                    if(receipt->input_bytes!=dia || receipt->input_crc!=ep0_trace_crc32(work->diagnostic,dia))return 0;
                    sink=&receipt->state;
                    if(sink->phase>EP0_SINK_ACKNOWLEDGED || sink->verified_bytes>dia ||
                       (!sink->attempted && (sink->phase || sink->result || sink->file_may_exist || sink->content_verified || sink->commit_acknowledged || sink->verified_bytes)) ||
                       (sink->file_may_exist && !sink->attempted) ||
                       (sink->content_verified && (!sink->attempted || !sink->file_may_exist || sink->verified_bytes!=dia || sink->phase<EP0_SINK_COMMIT)) ||
                       (sink->commit_acknowledged && (!sink->content_verified || sink->phase!=EP0_SINK_ACKNOWLEDGED || sink->result)) ||
                       (sink->phase==EP0_SINK_ACKNOWLEDGED && !sink->commit_acknowledged))return 0;
                    with_sink=true;
                }
            }
        }
    }
    size_t need=EP0_REL_HEADER+ini+dia;if(cap<need)return 0;
    memset(out,0,EP0_REL_HEADER);memcpy(out,"EP0REL1",7);
    ep0_trace_u16(out+8,1);ep0_trace_u16(out+10,EP0_REL_HEADER);ep0_trace_u16(out+12,EP0_INIT_MAX);ep0_trace_u16(out+14,EP0_DIAGNOSTIC_MAX);
    unsigned flags=3|(ini ? 4:0)|(dia ? 8:0)|(bound ? 16:0)|(request_ep0 ? 32:0)|(with_sink ? 64:0)|(with_admission ? 128:0);
    unsigned mode=dia ? (ini ? 2:3):(ini ? 1:0);
    ep0_trace_u32(out+16,flags);ep0_trace_u32(out+20,mode);ep0_trace_u32(out+24,reason);
    ep0_trace_u32(out+28,(uint32_t)ini);ep0_trace_u32(out+32,(uint32_t)dia);
    if(request_ep0) { ep0_trace_u32(out+36,video_join);ep0_trace_u32(out+40,audio_join); }
    ep0_trace_u32(out+44,startup_status);ep0_trace_u32(out+48,identity_result);
    if(with_admission) {
        ep0_trace_u32(out+52,admission->admitted);ep0_trace_u32(out+56,admission->trace_refusals);ep0_trace_u32(out+60,admission->stop_skips);
        ep0_trace_u32(out+64,admission->bound_violations);ep0_trace_u32(out+68,admission->largest_request);
    }
    if(with_sink) {
        ep0_trace_u32(out+72,sink->phase);ep0_trace_u32(out+76,sink->result);
        ep0_trace_u32(out+80,(sink->attempted ? 1:0)|(sink->file_may_exist ? 2:0)|(sink->content_verified ? 4:0)|(sink->commit_acknowledged ? 8:0));
        ep0_trace_u64(out+88,sink->verified_bytes);ep0_trace_u32(out+188,receipt->input_crc);
    }
    ep0_trace_u64(out+96,starter);ep0_trace_u64(out+104,writer);memcpy(out+112,boot,16);memcpy(out+128,session,16);memcpy(out+144,recipe,32);
    if(ini)memcpy(out+EP0_REL_HEADER,work->startup,ini);
    if(dia)memcpy(out+EP0_REL_HEADER+ini,work->diagnostic,dia);
    ep0_trace_u32(out+176,ep0_trace_crc32(out+EP0_REL_HEADER,ini));
    ep0_trace_u32(out+180,ep0_trace_crc32(out+EP0_REL_HEADER+ini,dia));
    ep0_trace_u32(out+184,ep0_trace_crc32(out,EP0_REL_HEADER));return need;
}
