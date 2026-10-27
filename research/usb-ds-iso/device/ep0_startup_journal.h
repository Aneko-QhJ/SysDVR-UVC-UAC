#pragma once
/* Independent simulation-only startup journal. One initializer, immutable
 * configuration, one caller-designated writer, append-only published prefix.
 * Readers may run concurrently; no owner/payload reads or cleanup authority. */
#include <stdatomic.h>
#include "ep0_trace.h"
#define EP0_INIT_CAPACITY 64u
#define EP0_INIT_HEADER 96u
#define EP0_INIT_ENTRY 16u
#define EP0_INIT_MAX (EP0_INIT_HEADER+EP0_INIT_CAPACITY*EP0_INIT_ENTRY)
enum Ep0InitStep {
    EP0_I_FS_INIT=1,EP0_I_SD_OPEN,EP0_I_LOG_DELETE,EP0_I_LOG_CREATE,
    EP0_I_VIDEO_OPEN,EP0_I_AUDIO_OPEN,EP0_I_USB_INIT,EP0_I_DESCRIPTORS,
    EP0_I_INTERFACES,EP0_I_ISO_SETUP,EP0_I_USB_ENABLE,EP0_I_VIDEO_CREATE,
    EP0_I_VIDEO_START,EP0_I_AUDIO_CREATE,EP0_I_AUDIO_START,EP0_I_SM_INIT,
    EP0_I_SETSYS_INIT,EP0_I_FW_GET,EP0_I_SERIAL_GET,EP0_I_CORE_INIT,
    EP0_I_USB_DEVICE_INIT,EP0_I_FS_EXIT,EP0_I_SD_CLOSE,EP0_I_VIDEO_CLOSE,
    EP0_I_AUDIO_CLOSE,EP0_I_FATAL
};
enum Ep0InitEvent { EP0_I_CALL=1,EP0_I_RESULT,EP0_I_VOID_RETURN,EP0_I_FATAL_RESULT };
enum { EP0_IN_COUNT=127u,EP0_IN_READY=256u,EP0_IN_BUSY=512u,
       EP0_IN_SEALED=1024u,EP0_IN_OVERFLOW=2048u,EP0_IN_INVALID=4096u,EP0_IN_FATAL=8192u,
       EP0_IN_INITIALIZING=0x80000000u };
typedef struct { uint16_t step,event;uint32_t result; } Ep0InitRecord;
typedef struct {
    atomic_uint published;
    uint64_t writer;
    uint8_t recipe[32];
    Ep0InitRecord records[EP0_INIT_CAPACITY];
    unsigned depth;uint16_t stack[EP0_INIT_CAPACITY]; /* Writer-only; never read by snapshot. */
} Ep0StartupJournal;
_Static_assert(sizeof(unsigned)==4,"32-bit atomic token required");
static inline bool ep0_init_range(uintptr_t a,size_t n) { return a && n && n<=UINTPTR_MAX-a; }
static inline bool ep0_init_overlap(uintptr_t a,size_t n,uintptr_t b,size_t m) { return a<b+m && b<a+n; }
static inline bool ep0_startup_init(Ep0StartupJournal *s,uint64_t writer,const uint8_t recipe[32]) {
    if(!s || !writer || !recipe || !ep0_trace_nonzero(recipe,32) ||
       !ep0_init_range((uintptr_t)s,sizeof(*s)) || !ep0_init_range((uintptr_t)recipe,32) ||
       ep0_init_overlap((uintptr_t)s,sizeof(*s),(uintptr_t)recipe,32))return false;
    unsigned expected=0;
    if(!atomic_compare_exchange_strong_explicit(&s->published,&expected,EP0_IN_INITIALIZING,memory_order_acq_rel,memory_order_acquire))return false;
    s->depth=0;s->writer=writer;memcpy(s->recipe,recipe,32);
    atomic_store_explicit(&s->published,EP0_IN_READY,memory_order_release);return true;
}
static inline void ep0_startup_mark(Ep0StartupJournal *s,unsigned flag) {
    unsigned state=atomic_load_explicit(&s->published,memory_order_acquire);
    while((state&EP0_IN_READY) && !(state&(EP0_IN_SEALED|EP0_IN_INITIALIZING))) {
        if(atomic_compare_exchange_weak_explicit(&s->published,&state,state|flag,memory_order_acq_rel,memory_order_acquire))return;
    }
}
static inline bool ep0_startup_record(Ep0StartupJournal *s,uint64_t writer,unsigned step,unsigned event,uint32_t result) {
    if(!s)return false;
    unsigned state=atomic_load_explicit(&s->published,memory_order_acquire);
    if(!(state&EP0_IN_READY) || (state&(EP0_IN_INITIALIZING|EP0_IN_SEALED|EP0_IN_OVERFLOW|EP0_IN_INVALID|EP0_IN_FATAL)))return false;
    if(writer!=s->writer || !step || step>EP0_I_FATAL || !event || event>EP0_I_FATAL_RESULT ||
       ((event==EP0_I_CALL || event==EP0_I_VOID_RETURN) && result) ||
       ((event==EP0_I_FATAL_RESULT) && (step!=EP0_I_FATAL || !result)) ||
       ((step==EP0_I_FATAL)!=(event==EP0_I_FATAL_RESULT)) ||
       (event==EP0_I_VOID_RETURN && (step<EP0_I_FS_EXIT || step>EP0_I_AUDIO_CLOSE)) ||
       (event==EP0_I_RESULT && step>=EP0_I_FS_EXIT) || (state&EP0_IN_BUSY)) {
        ep0_startup_mark(s,EP0_IN_INVALID);return false;
    }
    unsigned n=state&EP0_IN_COUNT;
    if(n>=EP0_INIT_CAPACITY) { ep0_startup_mark(s,EP0_IN_OVERFLOW);return false; }
    if(!atomic_compare_exchange_strong_explicit(&s->published,&state,state|EP0_IN_BUSY,memory_order_acq_rel,memory_order_acquire)) {
        ep0_startup_mark(s,EP0_IN_INVALID);return false;
    }
    if((event==EP0_I_RESULT || event==EP0_I_VOID_RETURN) &&
       (!s->depth || s->stack[s->depth-1]!=step)) {
        ep0_startup_mark(s,EP0_IN_INVALID);
        atomic_fetch_and_explicit(&s->published,~EP0_IN_BUSY,memory_order_release);return false;
    }
    if(event==EP0_I_CALL)s->stack[s->depth++]=(uint16_t)step;
    else if(event==EP0_I_RESULT || event==EP0_I_VOID_RETURN)s->depth--;
    s->records[n]=(Ep0InitRecord){(uint16_t)step,(uint16_t)event,result};
    /* Preserve a sticky invalid bit set by a reentrant/rejected caller. */
    state=atomic_load_explicit(&s->published,memory_order_relaxed);
    unsigned next;
    do { next=((state&~(EP0_IN_BUSY|EP0_IN_COUNT)) | (n+1) | (event==EP0_I_FATAL_RESULT ? EP0_IN_FATAL:0)); }
    while(!atomic_compare_exchange_weak_explicit(&s->published,&state,next,memory_order_release,memory_order_relaxed));
    return true;
}
static inline bool ep0_startup_seal(Ep0StartupJournal *s,uint64_t writer) {
    if(!s)return false;
    unsigned state=atomic_load_explicit(&s->published,memory_order_acquire);
    if(!(state&EP0_IN_READY) || (state&(EP0_IN_BUSY|EP0_IN_INITIALIZING|EP0_IN_SEALED)) || writer!=s->writer)return false;
    return atomic_compare_exchange_strong_explicit(&s->published,&state,state|EP0_IN_SEALED,memory_order_release,memory_order_relaxed);
}
static inline size_t ep0_startup_snapshot(const Ep0StartupJournal *s,uint8_t *out,size_t cap) {
    if(!s || !out)return 0;
    unsigned state=atomic_load_explicit(&s->published,memory_order_acquire),n=state&EP0_IN_COUNT;
    if(!(state&EP0_IN_READY) || (state&EP0_IN_INITIALIZING) || n>EP0_INIT_CAPACITY ||
       (state&~(EP0_IN_COUNT|EP0_IN_READY|EP0_IN_BUSY|EP0_IN_SEALED|EP0_IN_OVERFLOW|EP0_IN_INVALID|EP0_IN_FATAL)))return 0;
    size_t need=EP0_INIT_HEADER+n*EP0_INIT_ENTRY;
    if(cap<need || !ep0_init_range((uintptr_t)out,need) || !ep0_init_range((uintptr_t)s,sizeof(*s)) ||
       ep0_init_overlap((uintptr_t)out,need,(uintptr_t)s,sizeof(*s)))return 0;
    memset(out,0,need);memcpy(out,"EP0INI1",7);
    ep0_trace_u16(out+8,1);ep0_trace_u16(out+10,EP0_INIT_HEADER);
    ep0_trace_u16(out+12,EP0_INIT_ENTRY);ep0_trace_u16(out+14,EP0_INIT_CAPACITY);
    ep0_trace_u32(out+16,3); /* simulation AND startup-only */
    unsigned flags=((state&EP0_IN_SEALED)?1:0)|((state&EP0_IN_OVERFLOW)?2:0)|((state&EP0_IN_INVALID)?4:0)|((state&EP0_IN_BUSY)?8:0);
    ep0_trace_u32(out+20,flags);ep0_trace_u32(out+24,n);ep0_trace_u64(out+32,s->writer);memcpy(out+40,s->recipe,32);
    for(unsigned i=0;i<n;i++) {
        uint8_t *p=out+EP0_INIT_HEADER+i*EP0_INIT_ENTRY;
        ep0_trace_u16(p,s->records[i].step);ep0_trace_u16(p+2,s->records[i].event);
        ep0_trace_u32(p+4,s->records[i].result);ep0_trace_u32(p+8,i+1);
    }
    ep0_trace_u32(out+72,ep0_trace_crc32(out+EP0_INIT_HEADER,n*EP0_INIT_ENTRY));
    ep0_trace_u32(out+76,ep0_trace_crc32(out,EP0_INIT_HEADER));return need;
}
