#import <Foundation/Foundation.h>
#import "a23_scope_verifier.h"
#include "a23_service_observation.h"
#include <assert.h>
#include <errno.h>
#include <time.h>

static A23ServiceObservation observation;
static dispatch_queue_t serialQueue,workerQueue;
static dispatch_source_t timer;
static NSString *mode;
static BOOL workerReturned,workerPassed,windowDone,windowStarted,blockObserved;
static uint64_t fullCheckNS;
static unsigned fullChecks;
static uint64_t nowNS(void){struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC_RAW,&t));return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}
static void pauseNS(long ns){struct timespec t={0,ns};while(nanosleep(&t,&t) && errno==EINTR){}}

static void finish(void) {
    dispatch_assert_queue(serialQueue);if(!workerReturned || !windowDone)return;
    BOOL positive=[mode isEqual:@"worker-before"] || [mode isEqual:@"worker-during"];
    if(positive){assert(workerPassed && observation.stage==A23ServicePassed && observation.count>=9);}
    else if([mode isEqual:@"bad-guard"]){assert(!workerPassed && !windowStarted);}
    else if([mode isEqual:@"fault"]){assert(observation.failure==A23ServiceFault);}
    else {assert(observation.stage==A23ServiceFailed && observation.failure==A23ServiceGap);}
    NSMutableArray *samples=[NSMutableArray new];for(size_t i=0;i<observation.count;i++)[samples addObject:@(observation.samples[i])];
    NSDictionary *row=@{@"mode":mode,@"passed":@YES,@"full_checks":@(fullChecks),@"full_check_passed":@(workerPassed),@"full_check_ns":@(fullCheckNS),
        @"worker_return_observed":@(workerReturned),@"window_started":@(windowStarted),@"stage":@(observation.stage),@"failure":@(observation.failure),
        @"samples_ns":samples,@"sample_count":@(observation.count),@"max_gap_ns":@(observation.max_gap_ns),@"block_observed":@(blockObserved),
        @"observed_elapsed_ns":@(observation.last_ns-observation.start_ns),@"legacy_elapsed_eligible":@((BOOL)(observation.last_ns>=observation.start_ns && observation.last_ns-observation.start_ns>=A23_SERVICE_DURATION_NS)),
        @"local_service_window_passed":@((BOOL)(observation.stage==A23ServicePassed)),@"callback_drain_verified":@NO,@"future_events_excluded":@NO,
        @"safe_buffer_release":@NO,@"sdk_objects":@0,@"usb_requests":@0};
    NSData *raw=[NSJSONSerialization dataWithJSONObject:row options:NSJSONWritingSortedKeys error:NULL];assert(raw);fwrite(raw.bytes,1,raw.length,stdout);puts("");exit(0);
}
static void startWindow(void) {
    dispatch_assert_queue(serialQueue);assert(!windowStarted);a23_service_init(&observation);
    assert(a23_service_begin(&observation,nowNS()));windowStarted=YES;
    timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,serialQueue);
    dispatch_source_set_timer(timer,dispatch_time(DISPATCH_TIME_NOW,0),1000000,100000);
    dispatch_source_set_event_handler(timer,^{
        a23_service_tick(&observation,nowNS());
        if(observation.stage!=A23ServiceRunning){windowDone=YES;dispatch_source_cancel(timer);finish();}
    });dispatch_resume(timer);
    if([mode isEqual:@"blocked-start"]){blockObserved=YES;pauseNS(50000000);}
    if([mode isEqual:@"blocked-tail"]){dispatch_after(dispatch_time(DISPATCH_TIME_NOW,200000000),serialQueue,^{
        if(observation.stage==A23ServiceRunning){blockObserved=YES;pauseNS(80000000);}
    });}
    if([mode isEqual:@"fault"]){dispatch_after(dispatch_time(DISPATCH_TIME_NOW,100000000),serialQueue,^{
        a23_service_fault(&observation);windowDone=YES;dispatch_source_cancel(timer);finish();
    });}
}
static void edges(void) {
    A23ServiceObservation s;a23_service_init(&s);uint64_t start=1000000000;
    assert(!a23_service_begin(&s,UINT64_MAX-1) && s.failure==A23ServiceClock);
    a23_service_init(&s);assert(a23_service_begin(&s,start));
    for(unsigned i=1;i<=24;i++)assert(a23_service_tick(&s,start+i*10000000ULL)==A23ServiceRunning);
    assert(a23_service_tick(&s,start+300000000)==A23ServiceFailed && s.failure==A23ServiceGap);
    assert(!a23_service_begin(&s,start+400000000) && s.failure==A23ServiceGap);
    a23_service_init(&s);assert(a23_service_begin(&s,start));assert(a23_service_tick(&s,start-1)==A23ServiceFailed && s.failure==A23ServiceClock);
    a23_service_init(&s);assert(a23_service_begin(&s,start));
    for(unsigned i=1;i<A23_SERVICE_MAX_SAMPLES;i++)assert(a23_service_tick(&s,start+i)==A23ServiceRunning);
    assert(a23_service_tick(&s,start+A23_SERVICE_MAX_SAMPLES)==A23ServiceFailed && s.failure==A23ServiceCapacity);
    a23_service_init(&s);assert(a23_service_begin(&s,start));for(unsigned i=1;i<=25;i++)a23_service_tick(&s,start+i*10000000ULL);
    assert(s.stage==A23ServicePassed);a23_service_fault(&s);assert(s.stage==A23ServiceFailed && s.failure==A23ServiceFault);
    assert(!a23_service_begin(&s,start+500000000));
    puts("{\"mode\":\"edges\",\"passed\":true,\"arrangements\":6,\"usb_requests\":0}");
}
int main(int argc,const char *argv[]){@autoreleasepool {
    assert(argc==4);mode=@(argv[3]);if([mode isEqual:@"edges"]){edges();return 0;}
    NSString *build=@(argv[1]),*root=@(argv[2]);serialQueue=dispatch_queue_create("a23.service.fixture",DISPATCH_QUEUE_SERIAL);
    workerQueue=dispatch_queue_create("a23.service.guard",DISPATCH_QUEUE_SERIAL);
    dispatch_async(serialQueue,^{@autoreleasepool {
        BOOL hasGuard=[@[@"serial-guard",@"worker-before",@"worker-during",@"bad-guard"] containsObject:mode];
        if(!hasGuard){workerReturned=YES;startWindow();return;}
        A23ModelScopeVerifier *v=[[A23ModelScopeVerifier alloc] initWithBuild:build repository:[root stringByAppendingPathComponent:@"repository"] cards:[root stringByAppendingPathComponent:@"cards"] ledger:[root stringByAppendingPathComponent:@"ledger"] records:[root stringByAppendingPathComponent:@"records"]];assert(v);
        if([mode isEqual:@"serial-guard"]){
            workerReturned=YES;startWindow();uint64_t a=nowNS();fullChecks++;workerPassed=[v verifyCore];fullCheckNS=nowNS()-a;assert(workerPassed);return;
        }
        if([mode isEqual:@"worker-during"])startWindow();
        dispatch_group_t group=dispatch_group_create();
        dispatch_group_async(group,workerQueue,^{@autoreleasepool{uint64_t a=nowNS();fullChecks++;workerPassed=[v verifyCore];fullCheckNS=nowNS()-a;}});
        dispatch_group_notify(group,serialQueue,^{workerReturned=YES;
            if([mode isEqual:@"bad-guard"]){assert(!workerPassed);windowDone=YES;finish();}
            else if([mode isEqual:@"worker-before"]){assert(workerPassed);startWindow();}
            else finish();
        });
    }});dispatch_main();
}}
