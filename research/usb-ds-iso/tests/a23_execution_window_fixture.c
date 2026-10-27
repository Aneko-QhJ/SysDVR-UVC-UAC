/* Actual VideoStreamThread body is appended by the offline audit. All services
 * below are simulated; no ARM, USB, SD or real Switch thread is executed. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ep0_candidate_window.h"
typedef int Result;
typedef struct { void *Data; unsigned DataSize; uint64_t Timestamp; bool IsKeyframe; } VideoFrame;
#define CUR_THREAD_HANDLE 0
#define R_FAILED(rc) ((rc)!=0)
#define R_SUCCEEDED(rc) ((rc)==0)
#define LOG(...) ((void)0)
static bool g_running=true,stop_requested;
static unsigned process_calls,after_expiry_calls,capture_calls;
static uint64_t clock_tick=1000,trace_start,window_start,stop_tick;
static uint64_t ready_ms,process_ms,bind_ms,capture_ms;
static const unsigned char ep0CandidateRecipe[32]={1};
static Result svcGetThreadId(uint64_t *out,int handle) { (void)handle;*out=11;return 0; }
static void randomGet(void *out,size_t size) { memset(out,1,size); }
static uint64_t armGetSystemTickFreq(void) { return 1000; }
static uint64_t svcGetSystemTick(void) { return clock_tick; }
static bool Ep0CandidateStart(uint64_t writer,uint64_t freq,uint64_t tick,
    const uint8_t *boot,const uint8_t *session,const unsigned char *recipe) {
    (void)writer;(void)freq;(void)boot;(void)session;(void)recipe;trace_start=tick;return true;
}
static bool Ep0SessionBind(uint64_t writer,const uint8_t *boot,const uint8_t *session,const unsigned char *recipe) {
    (void)writer;(void)boot;(void)session;(void)recipe;clock_tick+=bind_ms;window_start=clock_tick;return true;
}
static void Ep0CandidateRequestStop(void) { stop_requested=true; }
static bool Ep0CandidateStopRequested(void) { return stop_requested; }
static bool Ep0CandidateStop(uint64_t tick) { stop_tick=tick;return true; }
static Result UvcDeviceWaitReady(double timeout) { (void)timeout;clock_tick+=ready_ms;return 0; }
static void UvcDeviceProcessRequests(void) {
    ++process_calls;if(clock_tick-window_start>=30000)++after_expiry_calls;clock_tick+=process_ms;
}
static void svcSleepThread(double ns) { clock_tick+=(uint64_t)(ns/1000000); }
static bool UvcDeviceIsStreaming(void) { return capture_ms!=0; }
static bool CaptureReadVideoFrame(VideoFrame *frame) { (void)frame;++capture_calls;clock_tick+=capture_ms;return false; }
static bool UvcDeviceSendFrame(void *data,unsigned size,uint64_t timestamp,bool keyframe) {
    (void)data;(void)size;(void)timestamp;(void)keyframe;return true;
}
/* INSERT_ACTUAL_VIDEO_THREAD */
int main(int argc,char **argv) {
    assert(argc==5);ready_ms=strtoull(argv[1],NULL,10);process_ms=strtoull(argv[2],NULL,10);
    bind_ms=strtoull(argv[3],NULL,10);capture_ms=strtoull(argv[4],NULL,10);
    VideoStreamThread(NULL);assert(stop_requested && !g_running && stop_tick>=window_start+30000);
    printf("{\"ready_ms\":%llu,\"process_ms\":%llu,\"bind_ms\":%llu,\"capture_ms\":%llu,"
        "\"trace_start\":%llu,\"window_start\":%llu,\"stop_tick\":%llu,\"elapsed_ms\":%llu,"
        "\"process_calls\":%u,\"process_calls_started_after_expiry\":%u,\"capture_calls\":%u,\"simulation\":true}\n",
        (unsigned long long)ready_ms,(unsigned long long)process_ms,(unsigned long long)bind_ms,
        (unsigned long long)capture_ms,(unsigned long long)trace_start,(unsigned long long)window_start,
        (unsigned long long)stop_tick,(unsigned long long)(stop_tick-window_start),process_calls,after_expiry_calls,capture_calls);
}
