#import <Foundation/Foundation.h>
#import "a23_terminal_observation.h"
#import "a23_scope_verifier.h"
#include <assert.h>
#include <errno.h>
#include <time.h>

static uint64_t nowNS(void) {struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC_RAW,&t));return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}
static void pauseNS(long ns) {struct timespec t={0,ns};while(nanosleep(&t,&t) && errno==EINTR){}}
static dispatch_queue_t queue;
static dispatch_source_t timer;
static A23TerminalObservation *terminal;
static NSString *mode;
static BOOL notified,observedBusyGate,pendingSnapshotRejected,tailBlocked;
static unsigned pollCalls;
static uint64_t firstPoll;
static NSDictionary *boundary(void) {return @{@"saved_epochs":@3,@"iso_attempts":@3,@"durable":@YES,@"pending":@NO,@"stopped":@NO};}
static void finish(void) {
    dispatch_assert_queue(queue);assert(notified && !terminal.busy && terminal.exitAllowed);
    NSDictionary *r=terminal.result;BOOL positive=[mode isEqual:@"normal"];
    // Preserve the terminal record even when an unexpected scheduler/fault path
    // makes a fixture assertion fail; never leave only an abort message.
    NSData *raw=[NSJSONSerialization dataWithJSONObject:r options:NSJSONWritingSortedKeys error:NULL];
    assert(raw);fwrite(raw.bytes,1,raw.length,stdout);puts("");fflush(stdout);
    assert([r[@"accepted"] boolValue]==positive);
    if([mode isEqual:@"invalid-boundary"])assert([r[@"full_checks"] unsignedIntValue]==0);
    else assert([r[@"full_checks"] unsignedIntValue]==1 && [r[@"worker_returns"] unsignedIntValue]==1);
    if([mode isEqual:@"worker-stop"] || [mode isEqual:@"duplicate"]){
        assert(observedBusyGate && pendingSnapshotRejected && [r[@"polls"] unsignedIntValue]==0);
    }
    if([mode isEqual:@"blocked-tail"])assert(tailBlocked && [r[@"max_gap_ns"] unsignedLongLongValue]>32000000ULL);
    if([mode isEqual:@"bad-guard"] || [mode isEqual:@"deadline"] || [mode isEqual:@"guard-exception"])
        assert([r[@"polls"] unsignedIntValue]==0 && [r[@"sample_count"] unsignedIntValue]==0);
    if(timer)dispatch_source_cancel(timer);
    exit(0);
}
int main(int argc,const char *argv[]) {@autoreleasepool {
    assert(argc==5);mode=@(argv[3]);NSString *build=@(argv[1]),*root=@(argv[2]);
    NSData *raw=[NSData dataWithContentsOfFile:@(argv[4])];
    NSDictionary *binding=[NSJSONSerialization JSONObjectWithData:raw options:0 error:NULL];assert(binding);
    queue=dispatch_queue_create("a23.terminal.fixture",DISPATCH_QUEUE_SERIAL);
    dispatch_async(queue,^{@autoreleasepool {
        A23ModelScopeVerifier *v=[[A23ModelScopeVerifier alloc] initWithBuild:build
            repository:[root stringByAppendingPathComponent:@"repository"] cards:[root stringByAppendingPathComponent:@"cards"]
            ledger:[root stringByAppendingPathComponent:@"ledger"] records:[root stringByAppendingPathComponent:@"records"]];assert(v);
        terminal=[[A23TerminalObservation alloc] initWithQueue:queue binding:binding fullCheck:^BOOL{
            if([mode isEqual:@"guard-exception"])[NSException raise:@"fixture" format:@"guard failure"];
            return [v verifyCore];
        } recheck:^BOOL{
            if([mode isEqual:@"recheck-stop"])[terminal requestStop];
            return ![mode isEqual:@"recheck-fail"];
        } poll:^BOOL{
            // Explicit model health completion; no SDK object, callback or ISO.
            pollCalls++;if(!firstPoll)firstPoll=nowNS();
            if([mode isEqual:@"poll-stop"] && pollCalls==3)[terminal requestStop];
            if([mode isEqual:@"poll-fail"] && pollCalls==3)return NO;
            if([mode isEqual:@"blocked-tail"] && !tailBlocked && nowNS()-firstPoll>=200000000ULL){tailBlocked=YES;pauseNS(80000000);}
            return YES;
        } finalCheck:^BOOL{
            if([mode isEqual:@"final-stop"])[terminal requestStop];
            return ![mode isEqual:@"final-fail"];
        } finished:^{
            assert(!notified);notified=YES;
            dispatch_async(queue,^{
                if([mode isEqual:@"postpass-stop"])[terminal requestStop];
                finish();
            });
        }];assert(terminal);
        uint64_t deadline=nowNS()+([mode isEqual:@"deadline"]?1000000ULL:10000000000ULL);
        NSDictionary *b=boundary();if([mode isEqual:@"invalid-boundary"]){NSMutableDictionary *bad=[b mutableCopy];bad[@"pending"]=@1;b=bad;}
        BOOL started=[terminal requestBoundary:b deadlineNS:deadline];
        assert(started!=[mode isEqual:@"invalid-boundary"]);
        if(started){
            NSDictionary *pending=terminal.result;
            pendingSnapshotRejected=![pending[@"accepted"] boolValue] && ![pending[@"verifier_on_serial_queue"] boolValue];
            if([mode isEqual:@"worker-stop"] || [mode isEqual:@"duplicate"]){
                observedBusyGate=terminal.busy && !terminal.exitAllowed;
                if([mode isEqual:@"worker-stop"])[terminal requestStop];
                else assert(![terminal requestBoundary:boundary() deadlineNS:nowNS()+10000000000ULL]);
                assert(terminal.busy && !terminal.exitAllowed);
            }
        }
        timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,queue);
        dispatch_source_set_timer(timer,dispatch_time(DISPATCH_TIME_NOW,0),1000000,100000);
        dispatch_source_set_event_handler(timer,^{[terminal tick];});dispatch_resume(timer);
    }});dispatch_main();
}}
