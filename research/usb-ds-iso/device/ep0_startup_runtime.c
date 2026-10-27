#ifndef EP0_CANDIDATE_NATIVE
#include <switch.h>
#endif
#include "ep0_startup_runtime.h"
static Ep0StartupJournal startup;
static atomic_uint startup_status,identity_result;
static uint64_t startup_writer;
static const void *video_thread,*audio_thread; /* Startup-writer-only role map, never read by snapshot. */
bool Ep0StartupBegin(const uint8_t recipe[32]) {
    unsigned expected=0;
    if(!atomic_compare_exchange_strong_explicit(&startup_status,&expected,1,memory_order_acq_rel,memory_order_acquire))return false;
    uint64_t writer=0;uint32_t rc=svcGetThreadId(&writer,CUR_THREAD_HANDLE);
    atomic_store_explicit(&identity_result,rc,memory_order_relaxed);
    bool ok=!rc && writer && ep0_startup_init(&startup,writer,recipe);
    if(ok)startup_writer=writer;
    atomic_store_explicit(&startup_status,ok ? 2:3,memory_order_release);return ok;
}
static void startup_emit(unsigned step,unsigned event,uint32_t result) {
    if(atomic_load_explicit(&startup_status,memory_order_acquire)==2)
        (void)ep0_startup_record(&startup,startup_writer,step,event,result);
}
void Ep0StartupCall(unsigned step) { startup_emit(step,EP0_I_CALL,0); }
void Ep0StartupResult(unsigned step,uint32_t result) { startup_emit(step,EP0_I_RESULT,result); }
void Ep0StartupVoid(unsigned step) { startup_emit(step,EP0_I_VOID_RETURN,0); }
bool Ep0StartupSeal(void) {
    if(atomic_load_explicit(&startup_status,memory_order_acquire)!=2)return false;
    return ep0_startup_seal(&startup,startup_writer);
}
void Ep0StartupFatal(uint32_t result) { startup_emit(EP0_I_FATAL,EP0_I_FATAL_RESULT,result);(void)Ep0StartupSeal(); }
void Ep0StartupBindThreads(const void *video,const void *audio) {
    /* Lexically called once by main before either LaunchThread. No payload reads. */
    if(video && audio && video!=audio && !video_thread && !audio_thread) { video_thread=video;audio_thread=audio; }
}
unsigned Ep0StartupCreateStep(const void *thread) { return thread && thread==video_thread ? EP0_I_VIDEO_CREATE:thread && thread==audio_thread ? EP0_I_AUDIO_CREATE:0; }
unsigned Ep0StartupStartStep(const void *thread) { return thread && thread==video_thread ? EP0_I_VIDEO_START:thread && thread==audio_thread ? EP0_I_AUDIO_START:0; }
size_t Ep0StartupSnapshot(uint8_t *out,size_t cap) { return ep0_startup_snapshot(&startup,out,cap); }
unsigned Ep0StartupStatus(void) { return atomic_load_explicit(&startup_status,memory_order_acquire); }
uint32_t Ep0StartupIdentityResult(void) { return atomic_load_explicit(&identity_result,memory_order_relaxed); }
