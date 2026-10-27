/* Actual capture functions, injected GRCD results and host mutexes only. */
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdalign.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;typedef uint32_t u32;typedef uint64_t u64;typedef uint32_t Result;
typedef struct { unsigned unused; } Service;
typedef pthread_mutex_t Mutex;
typedef enum { GrcStream_Video,GrcStream_Audio } GrcStream;
#define R_FAILED(r) ((r)!=0)
#define R_RET_ON_FAIL(x) do { Result rc=(x);if(R_FAILED(rc))return rc; } while(0)
#define LOG(...) do {} while(0)
#define VbufSz 0x54000
#define AbufSz 0x1000
typedef struct { u8 *Data;u32 DataSize;u64 Timestamp;bool IsKeyframe; } VideoFrame;
typedef struct { u8 *Data;u32 DataSize;u64 Timestamp; } AudioFrame;
static const char *scenario;
static atomic_uint transfers[2],begins,opens,closes;
#ifndef CAPTURE_LOCKED_CONTROL
#define CAPTURE_LOCKED_CONTROL 0
#endif
/* Keep scheduling atomics off the captured flag's TSAN shadow granule. */
static alignas(64) atomic_bool begin_entered;
static alignas(64) atomic_bool second_transferred;
static alignas(64) atomic_bool second_completed;
static bool concurrent;
static unsigned first_stream;
static void mutexInit(Mutex *m) { assert(!pthread_mutex_init(m,NULL)); }
static void mutexLock(Mutex *m) { assert(!pthread_mutex_lock(m)); }
static void mutexUnlock(Mutex *m) { assert(!pthread_mutex_unlock(m)); }
static Result grcdServiceOpen(Service *s) { (void)s;atomic_fetch_add(&opens,1);return 0; }
static void grcdServiceClose(Service *s) { (void)s;atomic_fetch_add(&closes,1); }
static Result grcdServiceBegin(Service *s) {
    (void)s;assert(atomic_fetch_add(&begins,1)==0);
    if(concurrent) {
        /* Deliberately relaxed: timing control supplies no publication edge
           for the unprotected flag. The tested flag itself is unchanged. */
        atomic_store_explicit(&begin_entered,true,memory_order_relaxed);
        while(!atomic_load_explicit(&second_transferred,memory_order_relaxed))sched_yield();
        if(!CAPTURE_LOCKED_CONTROL)
            while(!atomic_load_explicit(&second_completed,memory_order_relaxed))sched_yield();
    }
    return !strcmp(scenario,"init-error") ? 71:0;
}
static Result grcdServiceTransfer(Service *s,GrcStream stream,void *buf,size_t size,u32 *frames,u32 *n,u64 *tick) {
    (void)s;(void)size;(void)frames;
    unsigned index=atomic_fetch_add(&transfers[stream],1);
    if(concurrent && (unsigned)stream!=first_stream && !index) {
        while(!atomic_load_explicit(&begin_entered,memory_order_relaxed))sched_yield();
        atomic_store_explicit(&second_transferred,true,memory_order_relaxed);
    }
    memset(buf,0,8);((u8*)buf)[4]=1;*n=8;*tick=123;
    if(!strcmp(scenario,"transfer-error"))return 72;
    if(!strcmp(scenario,"small"))*n=4;
    if(concurrent || !strncmp(scenario,"init-",5)) {
        if(!index || !strcmp(scenario,"init-repeated-error"))return 0x3e8d4;
        if(!strcmp(scenario,"init-retry-error"))return 73;
    }
    return 0;
}
/* INSERT_CAPTURE */
static bool read_stream(unsigned stream) {
    if(!stream) { VideoFrame frame={0};return CaptureReadVideoFrame(&frame); }
    AudioFrame frame={0};return CaptureReadAudioFrame(&frame);
}
static void *worker(void *arg) {
    unsigned stream=(unsigned)(uintptr_t)arg;bool ok=read_stream(stream);
    if(stream!=first_stream)atomic_store_explicit(&second_completed,true,memory_order_relaxed);
    return (void*)(uintptr_t)ok;
}
int main(int argc,char **argv) {
    assert(argc==3);scenario=argv[1];first_stream=(unsigned)strtoul(argv[2],NULL,10);assert(first_stream<2);
    assert(!CaptureInitialize());
    bool ok;
    if(!strcmp(scenario,"concurrent")) {
        concurrent=true;pthread_t a,b;void *ar,*br;
        assert(!pthread_create(&a,NULL,worker,(void*)(uintptr_t)first_stream));
        assert(!pthread_create(&b,NULL,worker,(void*)(uintptr_t)(1-first_stream)));
        assert(!pthread_join(a,&ar));assert(!pthread_join(b,&br));
        assert((uintptr_t)ar==1 && (uintptr_t)br==0);ok=true;
    } else if(!strcmp(scenario,"cross-stream")) {
        scenario="init-ok";assert(read_stream(first_stream));assert(!read_stream(1-first_stream));ok=true;
    } else {
        ok=read_stream(first_stream);
        bool expected=!strcmp(scenario,"direct-ok") || !strcmp(scenario,"init-ok") || (!strcmp(scenario,"small") && first_stream==1);
        assert(ok==expected);
    }
    unsigned n=atomic_load(&transfers[first_stream]);assert(n<=2);assert(atomic_load(&begins)<=1);
    CaptureFinalize();assert(atomic_load(&opens)==2 && atomic_load(&closes)==2);
    printf("{\"passed\":true,\"stream\":%u,\"ok\":%s,\"video_transfers\":%u,\"audio_transfers\":%u,\"begin_calls\":%u,\"usb_calls\":0,\"fs_calls\":0}\n",first_stream,ok?"true":"false",atomic_load(&transfers[0]),atomic_load(&transfers[1]),atomic_load(&begins));
    return 0;
}
